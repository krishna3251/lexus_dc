"""Multi-stage web research pipeline for Lexus AI.

Pipeline:
1. deterministic query planning
2. local RAG recall from cached research/memory artifacts
3. live Google Search grounding through Gemini when available
4. Google Custom Search fallback
5. Groq browser-search emergency fallback
6. source deduplication and quality scoring
7. compact evidence packaging for the answer model
8. asynchronous caching into the local SQLite vector store

The pipeline keeps chain-of-thought private. It records only bounded, operational
research metadata such as search queries, providers, source counts, and scores.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import aiohttp

from .providers import ProviderError, ProviderManager
from .rag import RAGStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchPlan:
    original_query: str
    queries: list[str]
    freshness: str
    max_sources: int
    deep: bool = False


@dataclass(slots=True)
class ResearchSource:
    source_id: str
    title: str
    url: str
    snippet: str = ""
    domain: str = ""
    provider: str = ""
    published_at: str | None = None


@dataclass(slots=True)
class ResearchResult:
    success: bool
    answer: str = ""
    evidence: str = ""
    sources: list[ResearchSource] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    mode: str = ""
    rag_hits: int = 0
    error: str | None = None


class ResearchPlanner:
    """Create a bounded search plan without asking an LLM to reveal reasoning."""

    FRESH_TERMS = (
        "latest", "today", "current", "currently", "recent", "news",
        "now", "this week", "this month", "price", "pricing", "stock",
        "availability", "release", "launch",
    )

    @classmethod
    def plan(cls, prompt: str) -> SearchPlan:
        text = prompt.strip()
        lowered = text.casefold()
        fresh = any(term in lowered for term in cls.FRESH_TERMS)
        deep = any(
            phrase in lowered
            for phrase in (
                "deep research",
                "research thoroughly",
                "comprehensive research",
                "compare multiple sources",
                "investigate",
            )
        )
        today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        queries = [text]

        if fresh and ("today" in lowered or "news" in lowered):
            queries.append(f"{text} {today} latest")
        elif fresh:
            queries.append(f"{text} latest {today}")

        # A second formulation improves recall without exploding search cost.
        if deep:
            queries.append(f"{text} official primary sources")
            queries = queries[:3]
        else:
            queries = queries[:2]

        unique: list[str] = []
        seen: set[str] = set()
        for query in queries:
            key = query.casefold().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(query[:700])

        return SearchPlan(
            original_query=text,
            queries=unique,
            freshness="fresh" if fresh else "normal",
            max_sources=10 if deep else 8,
            deep=deep,
        )


class GeminiGoogleResearch:
    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_RESEARCH_MODEL", "gemini-3.8-flash").strip()

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def search(
        self,
        prompt: str,
        *,
        rag_context: str = "",
        deep: bool = False,
    ) -> ResearchResult:
        if not self.available:
            return ResearchResult(False, error="gemini_search_not_configured")

        instructions = f"""
Research the user's request using Google Search.
User request: {prompt}

You are the evidence-gathering stage of a production answer system.
- Search the live web for current facts.
- For news/current events, prefer multiple independent reputable sources.
- Prefer primary/official sources when they exist.
- Cross-check important claims instead of relying on one snippet.
- Do not treat cached context below as authoritative. Use it only as a lead.
- Return a concise factual answer, with uncertainty stated where evidence conflicts.
- Do not expose hidden chain-of-thought. Give only the answer and source-grounded facts.
- The application will separately display source links.

Cached RAG context:
{rag_context or "(none)"}
""".strip()
        payload = {
            "model": self.model,
            "input": instructions,
            "tools": [{"type": "google_search"}],
        }
        timeout = aiohttp.ClientTimeout(total=35)
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.ENDPOINT,
                    json=payload,
                    headers=headers,
                ) as response:
                    body = await response.json(content_type=None)
                    if response.status != 200:
                        raise RuntimeError(
                            f"Gemini search failed ({response.status}): "
                            f"{str(body)[:500]}"
                        )
        except Exception as exc:
            logger.warning("Gemini Google Search failed: %s", exc)
            return ResearchResult(False, error=f"gemini_search_failed:{type(exc).__name__}")

        answer = str(body.get("output_text") or "").strip()
        sources: list[ResearchSource] = []
        executed_queries: list[str] = []

        steps = body.get("steps") or body.get("output") or []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                step_type = step.get("type")
                if step_type == "google_search_call":
                    args = step.get("arguments") or {}
                    queries = args.get("queries") or []
                    executed_queries.extend(str(q)[:500] for q in queries)
                if step_type != "model_output":
                    continue
                blocks = step.get("content") or []
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") != "text":
                        continue
                    if not answer:
                        answer = str(block.get("text") or "").strip()
                    for annotation in block.get("annotations") or []:
                        if not isinstance(annotation, dict):
                            continue
                        if annotation.get("type") != "url_citation":
                            continue
                        url = str(annotation.get("url") or "").strip()
                        if not url:
                            continue
                        sources.append(
                            ResearchSource(
                                source_id=f"S{len(sources)+1}",
                                title=str(annotation.get("title") or self._domain(url)),
                                url=url[:1500],
                                snippet="",
                                domain=self._domain(url),
                                provider="gemini_google_search",
                            )
                        )

        deduped: list[ResearchSource] = []
        seen = set()
        for source in sources:
            key = source.url.casefold()
            if key in seen:
                continue
            seen.add(key)
            source.source_id = f"S{len(deduped)+1}"
            deduped.append(source)

        return ResearchResult(
            success=bool(answer or deduped),
            answer=answer,
            sources=deduped,
            queries=list(dict.fromkeys(executed_queries)),
            provider="gemini",
            model=self.model,
            mode="google_grounding",
        )

    @staticmethod
    def _domain(url: str) -> str:
        try:
            return urlparse(url).netloc.removeprefix("www.")
        except Exception:
            return ""


class GoogleCSEResearch:
    ENDPOINT = "https://www.googleapis.com/customsearch/v1"

    def __init__(self) -> None:
        self.cse_id = os.getenv("GOOGLE_CSE_ID", "").strip()
        self.api_key = os.getenv("GOOGLE_API_KEY", "").strip()

    @property
    def available(self) -> bool:
        return bool(self.cse_id and self.api_key)

    async def search(self, plan: SearchPlan) -> ResearchResult:
        if not self.available:
            return ResearchResult(False, error="google_cse_not_configured")

        timeout = aiohttp.ClientTimeout(total=20)
        sources: list[ResearchSource] = []
        queries: list[str] = []

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for query in plan.queries:
                    params = {
                        "q": query,
                        "cx": self.cse_id,
                        "key": self.api_key,
                        "num": min(10, plan.max_sources),
                    }
                    async with session.get(self.ENDPOINT, params=params) as response:
                        data = await response.json(content_type=None)
                        if response.status != 200:
                            logger.warning(
                                "Google CSE search failed | status=%s | query=%s",
                                response.status,
                                query,
                            )
                            continue
                    queries.append(query)
                    for item in data.get("items") or []:
                        url = str(item.get("link") or "").strip()
                        if not url:
                            continue
                        title = str(item.get("title") or self._domain(url))
                        snippet = re.sub(
                            r"<[^>]+>",
                            "",
                            str(item.get("snippet") or ""),
                        ).strip()
                        sources.append(
                            ResearchSource(
                                source_id="",
                                title=title[:300],
                                url=url[:1500],
                                snippet=snippet[:1800],
                                domain=self._domain(url),
                                provider="google_cse",
                            )
                        )
        except Exception as exc:
            logger.warning("Google CSE research failed: %s", exc)
            return ResearchResult(False, error=f"google_cse_failed:{type(exc).__name__}")

        deduped: list[ResearchSource] = []
        seen: set[str] = set()
        for source in sources:
            key = source.url.casefold().split("#", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            source.source_id = f"S{len(deduped)+1}"
            deduped.append(source)
            if len(deduped) >= plan.max_sources:
                break

        return ResearchResult(
            success=bool(deduped),
            sources=deduped,
            queries=queries,
            provider="google",
            mode="custom_search",
        )

    @staticmethod
    def _domain(url: str) -> str:
        try:
            return urlparse(url).netloc.removeprefix("www.")
        except Exception:
            return ""


class WebResearchService:
    """Production research coordinator with RAG and provider fallbacks."""

    def __init__(
        self,
        provider_manager: ProviderManager | None = None,
        rag: RAGStore | None = None,
    ) -> None:
        self.providers = provider_manager
        self.rag = rag or RAGStore()
        self.gemini = GeminiGoogleResearch()
        self.google = GoogleCSEResearch()
        self._initialized = False

    def health(self) -> dict[str, object]:
        return {
            "available": self.gemini.available or self.google.available or bool(self.providers and self.providers.available),
            "gemini_google": self.gemini.available,
            "google_cse": self.google.available,
            "rag": self.rag.health(),
        }

    async def initialize(self) -> None:
        if not self._initialized:
            self.rag.initialize()
            self._initialized = True

    @staticmethod
    def _format_rag_context(items) -> str:
        if not items:
            return ""
        blocks = []
        for index, item in enumerate(items, start=1):
            blocks.append(
                f"[RAG{index}] {item.title}\n"
                f"Source: {item.url or item.domain or 'local'}\n"
                f"{item.text[:1800]}"
            )
        return "\n\n".join(blocks)[:9000]

    @staticmethod
    def _quality_sorted(sources: list[ResearchSource]) -> list[ResearchSource]:
        preferred = {
            "reuters.com": 1.00,
            "apnews.com": 0.99,
            "bbc.com": 0.96,
            "gov.in": 1.00,
            "pib.gov.in": 1.00,
            "mha.gov.in": 1.00,
            "timesofindia.indiatimes.com": 0.88,
        }

        def key(source: ResearchSource) -> tuple[float, str]:
            base = preferred.get(source.domain.casefold(), 0.60)
            return (-base, source.domain)

        return sorted(sources, key=key)

    async def _cache_sources(self, sources: list[ResearchSource]) -> None:
        await asyncio.gather(
            *(
                self.rag.add(
                    source.title,
                    source.snippet or f"Source: {source.title}",
                    url=source.url,
                    domain=source.domain,
                    source_type="web",
                    metadata={"provider": source.provider},
                    ttl_seconds=7 * 24 * 60 * 60,
                    embed=True,
                )
                for source in sources[:4]
                if source.snippet
            ),
            return_exceptions=True,
        )

    async def research(self, prompt: str) -> ResearchResult:
        await self.initialize()
        plan = ResearchPlanner.plan(prompt)

        rag_result = await self.rag.search(prompt, limit=4)
        rag_context = self._format_rag_context(rag_result.items)

        # Primary path: live Google grounding through Gemini. This does not
        # depend on Groq being configured.
        if self.gemini.available:
            grounded = await self.gemini.search(
                prompt,
                rag_context=rag_context,
                deep=plan.deep,
            )
            if grounded.success:
                grounded.sources = self._quality_sorted(grounded.sources)
                for index, source in enumerate(grounded.sources, start=1):
                    source.source_id = f"S{index}"
                await self._cache_grounded_answer(prompt, grounded)
                grounded.rag_hits = len(rag_result.items)
                return grounded

        # Structured fallback: Google Custom Search.
        if self.google.available:
            cse = await self.google.search(plan)
            if cse.success:
                cse.sources = self._quality_sorted(cse.sources)
            for index, source in enumerate(cse.sources, start=1):
                source.source_id = f"S{index}"
                cse.evidence = self._evidence_from_sources(cse.sources)
                await self._cache_sources(cse.sources)
                cse.rag_hits = len(rag_result.items)
                return cse

        # Emergency fallback: existing Groq browser search, if configured.
        if self.providers is not None:
            try:
                reply = await self.providers.complete(
                    messages=[{
                        "role": "user",
                        "content": prompt,
                    }],
                    tools=[],
                    max_output_tokens=900,
                    web_search=True,
                )
                return ResearchResult(
                    success=bool(reply.text.strip()),
                    answer=reply.text.strip(),
                    queries=plan.queries,
                    provider=reply.provider.value,
                    model=reply.model,
                    mode="groq_browser_search",
                    rag_hits=len(rag_result.items),
                )
            except ProviderError as exc:
                logger.warning("Groq browser-search fallback failed: %s", exc)

        # Last local option: answer from cached RAG only, but explicitly mark
        # it as cached knowledge so callers can decide whether to trust it.
        if rag_result.items:
            return ResearchResult(
                success=True,
                evidence=rag_context,
                sources=[
                    ResearchSource(
                        source_id=f"R{index}",
                        title=item.title,
                        url=item.url or "",
                        snippet=item.text[:1200],
                        domain=item.domain or "",
                        provider="local_rag",
                    )
                    for index, item in enumerate(rag_result.items, start=1)
                ],
                queries=plan.queries,
                provider="sqlite",
                mode="cached_rag",
                rag_hits=len(rag_result.items),
            )

        return ResearchResult(
            success=False,
            queries=plan.queries,
            mode="unavailable",
            error="no_search_provider",
        )

    async def _cache_grounded_answer(
        self,
        prompt: str,
        result: ResearchResult,
    ) -> None:
        source_text = "\n".join(
            f"{source.title}\n{source.url}\n{source.snippet}"
            for source in result.sources[:6]
        )
        text = result.answer.strip()
        if source_text:
            text += "\n\nSources:\n" + source_text
        await self.rag.add(
            title=f"Research: {prompt[:180]}",
            text=text[:8000],
            url=None,
            domain="gemini-grounding",
            source_type="research",
            metadata={
                "queries": result.queries,
                "provider": result.provider,
                "sources": [source.url for source in result.sources[:10]],
            },
            ttl_seconds=24 * 60 * 60,
            embed=True,
        )

    @staticmethod
    def _evidence_from_sources(sources: list[ResearchSource]) -> str:
        blocks = []
        for source in sources:
            blocks.append(
                f"[{source.source_id}] {source.title}\n"
                f"URL: {source.url}\n"
                f"Snippet: {source.snippet}"
            )
        return "\n\n".join(blocks)[:12000]
