"""Offline and loopback coverage for bounded Groq-only research reports."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web

from cogs.ai_engine import AIEngineCog
from services.ai_engine.config import BrainConfig
from services.ai_engine.embeddings import LexicalOnlyEmbeddingService
from services.ai_engine.engine import AIEngine
from services.ai_engine.models import AIProvider, AIRequest, AIResult, ProviderReply, ToolCall
from services.ai_engine.providers import ProviderError, ProviderManager
from services.ai_engine.research import ResearchPlanner, ResearchResult, TavilyResearch, WebResearchService, public_source_url
from services.ai_engine.router import RequestRouter
from services.ai_engine.tools import ToolContext
from services.discord_output import discord_length, prepare_reply


def packet(domain="docs.python.org"):
    return json.dumps({"findings": "The documented feature is available.", "sources": [
        {"title": "Documentation", "url": f"https://{domain}/guide", "excerpt": "Supported feature."}
    ]})


class ResearchProvider:
    available = True
    names = ["groq:test"]

    def __init__(self):
        self.config = BrainConfig(provider_retries=0)
        self.calls = []
        self.reservations = 0
        self.browser_reply = packet()
        self.final = "## Findings\nThe feature is documented [S1]."
        self.fail_pass = None
        self.final_tools = []

    def reserve_external(self):
        self.reservations += 1

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        self.reserve_external()
        if self.fail_pass == len(self.calls):
            raise ProviderError("simulated failure")
        text = self.browser_reply if kwargs.get("web_search") else self.final
        return ProviderReply(AIProvider.GROQ, "test", {"role": "assistant", "content": text}, text,
                             tool_calls=[] if kwargs.get("web_search") else self.final_tools)

    def health(self):
        return {}

    async def close(self):
        return None


class ResearchPolicyTests(unittest.TestCase):
    def test_default_research_is_detailed_and_queries_are_bounded(self):
        plan = ResearchPlanner.plan("research Discord developer updates")
        self.assertTrue(plan.deep)
        self.assertEqual(len(plan.queries), 3)
        self.assertEqual(len(set(plan.queries)), 3)
        self.assertTrue(all(len(q) < 400 for q in ResearchPlanner.plan("x" * 8000).queries))
        self.assertEqual(plan.queries[0], "Discord developer updates")
        self.assertEqual(plan.original_query, "research Discord developer updates")

    def test_explicit_brief_search_stays_brief(self):
        plan = ResearchPlanner.plan("quick search today's Hyderabad news")
        self.assertFalse(plan.deep)
        self.assertEqual(len(plan.queries), 1)
        self.assertEqual(plan.freshness, "fresh")

    def test_research_about_moderation_never_routes_to_mutations(self):
        route = RequestRouter.route("research Discord ban API changes")
        self.assertEqual(route.intent.value, "search")
        self.assertFalse(route.allow_mutations)
        self.assertFalse(route.allow_tools)

    def test_removed_keys_cannot_reenable_gemini(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "", "GEMINI_API_KEY": "old-unused-key", "AI_LOCAL_ENABLED": "false"}):
            manager = ProviderManager()
            self.assertEqual(manager.providers, [])
            self.assertFalse(LexicalOnlyEmbeddingService().available)

    def test_source_urls_reject_credentials_and_local_targets(self):
        for url in ("javascript:alert(1)", "https://user:secret@example.com/", "http://127.0.0.1/",
                    "http://169.254.169.254/", "https://server.local/path", "https://example.com/ bad"):
            self.assertIsNone(public_source_url(url), url)
        self.assertEqual(public_source_url("https://docs.python.org/3/#overview"), "https://docs.python.org/3/")

    def test_long_report_has_visible_preview_and_intact_attachment(self):
        report = "## Findings\nA useful summary.\n\n" + "More evidence. " * 1000
        chunks, attachment = prepare_reply(report)
        self.assertIn("A useful summary", chunks[0])
        self.assertLessEqual(discord_length(chunks[0]), 1900)
        self.assertEqual(attachment.fp.read().decode(), report)
        attachment.close()


class ResearchFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AI_SQLITE_PATH": str(Path(self.tmp.name) / "reports.sqlite3"),
            "TAVILY_API_KEY": "", "GOOGLE_API_KEY": "", "GROQ_API_KEY": "", "AI_GATEWAY_API_KEY": "",
            "AI_EXTERNAL_ENABLED": "true", "AI_LOCAL_ENABLED": "false"})
        self.env.start()
        self.provider = ResearchProvider()
        self.service = WebResearchService(self.provider)

    async def asyncTearDown(self):
        await self.service.close()
        self.env.stop()
        self.tmp.cleanup()

    async def test_three_evidence_passes_precede_report_generation(self):
        result = await self.service.research("research Discord updates")
        self.assertTrue(result.success)
        self.assertEqual([c["web_search"] for c in self.provider.calls], [True, True, True, False])
        self.assertEqual(self.provider.calls[-1]["max_output_tokens"], 2400)
        self.assertEqual(self.provider.calls[-1]["tools"], [])
        self.assertEqual(len(result.sources), 1)
        self.assertIn("independent corroboration is limited", result.answer)
        self.assertEqual(result.sources[0].source_id, "S1")

    async def test_brief_search_has_one_pass_and_smaller_report(self):
        result = await self.service.research("quick search Discord updates")
        self.assertTrue(result.success)
        self.assertEqual(len(self.provider.calls), 2)
        self.assertEqual(self.provider.calls[-1]["max_output_tokens"], 450)

    async def test_groq_rate_limit_retry_respects_retry_after(self):
        manager = ProviderManager(BrainConfig(provider_retries=1))
        remote = SimpleNamespace(provider=AIProvider.GROQ, model="test", close=AsyncMock(),
            complete=AsyncMock(side_effect=[ProviderError("429", status_code=429, retry_after=12),
                ProviderReply(AIProvider.GROQ, "test", {"role": "assistant", "content": "done"}, "done")]))
        manager.providers = [remote]
        try:
            with patch("services.ai_engine.providers.asyncio.sleep", AsyncMock()) as pause:
                await manager.complete([], [], 100)
            pause.assert_awaited_once_with(12)
            self.assertEqual(manager.calls, 2)
        finally:
            await manager.close()

    async def test_retry_after_over_bound_does_not_retry_early(self):
        manager = ProviderManager(BrainConfig(provider_retries=1))
        remote = SimpleNamespace(provider=AIProvider.GROQ, model="test", close=AsyncMock(),
            complete=AsyncMock(side_effect=ProviderError("429", status_code=429, retry_after=120)))
        manager.providers = [remote]
        try:
            with patch("services.ai_engine.providers.asyncio.sleep", AsyncMock()) as pause:
                with self.assertRaises(ProviderError):
                    await manager.complete([], [], 100)
            pause.assert_not_awaited()
            self.assertEqual(remote.complete.await_count, 1)
        finally:
            await manager.close()

    async def test_failed_pass_preserves_other_evidence_and_discloses_gap(self):
        self.provider.fail_pass = 2
        result = await self.service.research("research Discord updates")
        self.assertTrue(result.success)
        self.assertIn("Some search passes failed", result.answer)
        self.assertEqual(len(self.provider.calls), 4)

    async def test_unsourced_search_never_becomes_a_report(self):
        self.provider.browser_reply = "A confident answer without any source URLs."
        result = await self.service.research("research Discord updates")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "no_usable_live_sources")
        self.assertTrue(all(c["web_search"] for c in self.provider.calls))

    async def test_external_optout_does_not_announce_or_search(self):
        engine = AIEngine(provider_manager=self.provider)
        try:
            await engine.memory.set_preferences(1, None, history_enabled=False, external_allowed=False)
            engine.research.research = AsyncMock(side_effect=AssertionError("must not search"))
            progress = AsyncMock()
            context = ToolContext(SimpleNamespace(is_ready=lambda: True), None, SimpleNamespace(id=3), SimpleNamespace(id=1))
            result = await engine.ask(AIRequest(1, None, 3, "research Discord updates"), context, progress=progress)
            self.assertEqual(result.error, "external_disabled")
            progress.assert_not_awaited()
        finally:
            await engine.close()

    async def test_progress_precedes_report_and_uses_research_timeout(self):
        config = BrainConfig(request_timeout=0.001, research_timeout=1, research_output_tokens=3000)
        engine = AIEngine(provider_manager=self.provider, config=config)
        progress = AsyncMock()
        async def research(*args, **kwargs):
            progress.assert_awaited_once()
            self.assertEqual(kwargs["max_output_tokens"], 3000)
            await asyncio.sleep(0.01)
            return ResearchResult(True, answer="Checked report.", provider="groq")
        engine.research.research = research
        try:
            context = ToolContext(SimpleNamespace(is_ready=lambda: True), None, SimpleNamespace(id=3), SimpleNamespace(id=1))
            result = await engine.ask(AIRequest(1, None, 3, "research Discord updates"), context, progress=progress)
            self.assertTrue(result.success)
        finally:
            await engine.close()

    async def test_invalid_citations_and_model_tool_calls_are_not_trusted(self):
        self.provider.final = "Valid [S1], invented [S99]."
        result = await self.service.research("research Discord updates")
        self.assertNotIn("[S99]", result.answer)
        self.provider.final_tools = [ToolCall("bad", "ban_member", {})]
        result = await self.service.research("research Discord updates")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "report_synthesis_failed")

    async def test_status_message_is_cleaned_up_after_completion_and_cancel(self):
        bot = SimpleNamespace()
        cog = AIEngineCog(bot)
        notice = SimpleNamespace(delete=AsyncMock())
        channel = SimpleNamespace(id=3, send=AsyncMock(return_value=notice))
        user = SimpleNamespace(id=1)
        async def complete(*args, progress=None, **kwargs):
            await progress("Researching live sources...")
            return AIResult(True, "Report.")
        cog.engine.ask = complete
        try:
            self.assertEqual(await cog._run(user, None, channel, "research updates"), "Report.")
            notice.delete.assert_awaited_once()
            async def cancel(*args, progress=None, **kwargs):
                await progress("Researching live sources...")
                raise asyncio.CancelledError()
            cog.engine.ask = cancel
            with self.assertRaises(asyncio.CancelledError):
                await cog._run(user, None, channel, "research updates")
            self.assertEqual(notice.delete.await_count, 2)
        finally:
            await cog.engine.close()

    async def test_tavily_loopback_uses_advanced_search_and_shared_reservations(self):
        received = []
        async def search(request):
            payload = await request.json()
            received.append(payload)
            self.assertEqual(request.headers.get("Authorization"), "Bearer placeholder-test-key")
            return web.json_response({"results": [
                {"title": "Python", "url": "https://docs.python.org/3/", "content": "Relevant Python feature.", "raw_content": "Unrelated navigation."},
                {"title": "Discord", "url": "https://docs.discord.com/developers/", "content": "Discord docs."},
            ]})
        app = web.Application()
        app.router.add_post("/search", search)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.service.tavily.api_key = "placeholder-test-key"
        self.service.tavily.ENDPOINT = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/search"
        try:
            result = await self.service.research("research today's API news")
            self.assertTrue(result.success)
            self.assertEqual(len(received), 3)
            self.assertTrue(all(r["search_depth"] == "advanced" for r in received))
            self.assertTrue(all(r["max_results"] == 10 and len(r["query"]) < 400 for r in received))
            self.assertTrue(all(r["topic"] == "news" and r["time_range"] == "day" for r in received))
            self.assertEqual(len(result.sources), 2)
            self.assertEqual(result.sources[0].snippet, "Relevant Python feature.")
            self.assertEqual(len(self.provider.calls), 1)
            self.assertFalse(self.provider.calls[0]["web_search"])
            self.assertEqual(self.provider.reservations, 4)
        finally:
            await runner.cleanup()

    async def test_tavily_cannot_send_http_without_budget_reservation(self):
        tavily = TavilyResearch()
        tavily.api_key = "placeholder-test-key"
        with patch("aiohttp.ClientSession._request", AsyncMock(side_effect=AssertionError("must not request"))):
            result = await tavily.search(ResearchPlanner.plan("research updates"))
        self.assertFalse(result.success)

    async def test_hybrid_research_defers_then_completes_its_interaction(self):
        cog = AIEngineCog(SimpleNamespace())
        cog._run = AsyncMock(return_value="A sourced report.")
        cog._send_chunked = AsyncMock()
        # Match the real discord.py Context.defer API, which has no thinking argument.
        deferred = []
        async def defer(*, ephemeral=False):
            deferred.append(True)
        ctx = SimpleNamespace(interaction=object(), defer=defer, author=SimpleNamespace(id=1),
                              guild=None, channel=SimpleNamespace(id=3))
        try:
            await cog.research_command.callback(cog, ctx, query="Discord changes")
            self.assertEqual(deferred, [True])
            cog._send_chunked.assert_awaited_once_with(ctx, "A sourced report.")
            self.assertEqual(cog._run.call_args.args[-1], "research Discord changes")
        finally:
            await cog.engine.close()

    async def test_oversized_search_payload_is_rejected(self):
        async def search(request):
            return web.Response(body=b'{"results": []}' + b' ' * 1_000_001, content_type="application/json")
        app = web.Application()
        app.router.add_post("/search", search)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        tavily = TavilyResearch()
        tavily.api_key, tavily.reserve_call = "placeholder", lambda: True
        tavily.ENDPOINT = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/search"
        try:
            result = await tavily.search(ResearchPlanner.plan("quick search APIs"))
            self.assertFalse(result.success)
            self.assertEqual(result.sources, [])
        finally:
            await runner.cleanup()
