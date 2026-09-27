"""Gemini Embedding 2 client for compact semantic retrieval."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import aiohttp


class GeminiEmbeddingService:
    """Generate compact embeddings without adding heavy ML packages."""

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"

    def __init__(
        self,
        *,
        model: str | None = None,
        dimensions: int | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = (
            model
            or os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
        ).strip()
        try:
            self.dimensions = int(
                dimensions
                or os.getenv("GEMINI_EMBEDDING_DIMENSIONS", "768")
            )
        except (TypeError, ValueError):
            self.dimensions = 768
        self.dimensions = max(128, min(self.dimensions, 3072))
        self.timeout_seconds = max(3.0, float(timeout_seconds))
        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                )
            return self._session

    async def _embed(self, text: str) -> list[float]:
        if not self.available:
            raise RuntimeError("GEMINI_API_KEY is not configured for embeddings")

        payload: dict[str, Any] = {
            "model": f"models/{self.model}",
            "content": {
                "parts": [{"text": text[:8000]}],
            },
            "output_dimensionality": self.dimensions,
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        url = self.ENDPOINT.format(model=self.model)
        session = await self._get_session()
        async with session.post(url, json=payload, headers=headers) as response:
            body = await response.json(content_type=None)
            if response.status != 200:
                raise RuntimeError(
                    f"Gemini embedding failed ({response.status}): {str(body)[:500]}"
                )

        embeddings = body.get("embeddings") or []
        values: list[float] = []
        if embeddings and isinstance(embeddings[0], dict):
            values = embeddings[0].get("values") or []
        if not values:
            values = (body.get("embedding") or {}).get("values") or []
        if not values:
            raise RuntimeError("Gemini embedding response contained no vector")
        vector = [float(value) for value in values]
        if len(vector) != self.dimensions:
            raise RuntimeError(
                f"Gemini embedding dimension mismatch: expected {self.dimensions}, got {len(vector)}"
            )
        return vector

    async def embed_query(self, query: str) -> list[float]:
        """Embedding for a retrieval query using Gemini's recommended prefix."""
        return await self._embed(
            f"task: search result | query: {query.strip()[:7000]}"
        )

    async def embed_document(self, title: str, text: str) -> list[float]:
        """Embedding for a retrievable document using Gemini's recommended structure."""
        return await self._embed(
            f"title: {title.strip()[:300] or 'none'} | text: {text.strip()[:7600]}"
        )

    async def close(self) -> None:
        async with self._session_lock:
            if self._session is not None and not self._session.closed:
                await self._session.close()
            self._session = None
