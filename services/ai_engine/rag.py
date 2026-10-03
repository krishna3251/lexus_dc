"""Low-storage hybrid RAG for Lexus AI.

Uses the same local SQLite database as AI memory. Embeddings are stored as
compact float32 BLOBs. Retrieval combines semantic cosine similarity with
lexical overlap, freshness, and source-quality signals. No external vector
database is required.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SQLITE_PATH = "/home/container/data/lexus_ai.sqlite3"


@dataclass(slots=True)
class RAGItem:
    item_id: int
    title: str
    text: str
    url: str | None
    domain: str | None
    source_type: str
    semantic_score: float
    lexical_score: float
    freshness_score: float
    quality_score: float
    score: float
    metadata: dict[str, Any]


@dataclass(slots=True)
class RAGResult:
    items: list[RAGItem]
    backend: str = "sqlite"
    embedding_model: str = "lexical"
    embedding_dimensions: int = 0


class RAGStore:
    """Bounded local vector store with hybrid retrieval."""

    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        *,
        max_items: int = 1000,
        default_ttl_seconds: int = 30 * 24 * 60 * 60,
    ) -> None:
        configured = str(db_path).strip() if db_path is not None else ""
        configured = configured or os.getenv("AI_SQLITE_PATH", "").strip()
        self.db_path = Path(configured or DEFAULT_SQLITE_PATH).expanduser()
        self.max_items = max(100, int(max_items))
        self.default_ttl_seconds = max(3600, int(default_ttl_seconds))
        self._initialized = False

    @property
    def available(self) -> bool:
        return self._initialized and self.db_path.exists()

    def health(self) -> dict[str, Any]:
        try:
            size = self.db_path.stat().st_size if self.db_path.exists() else 0
        except OSError:
            size = 0
        count = 0
        if self.available:
            try:
                conn = self._connect()
                count = int(conn.execute("SELECT COUNT(*) FROM rag_items").fetchone()[0])
                conn.close()
            except Exception:
                count = 0
        return {
            "backend": "sqlite",
            "available": self.available,
            "path": str(self.db_path),
            "size_bytes": size,
            "items": count,
            "embedding_model": "lexical",
            "embedding_dimensions": 0,
        }

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def initialize(self) -> None:
        if self._initialized:
            return
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS rag_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    url TEXT,
                    domain TEXT,
                    source_type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    embedding BLOB,
                    embedding_model TEXT,
                    embedding_dimensions INTEGER,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS rag_expiry ON rag_items(expires_at);
                CREATE INDEX IF NOT EXISTS rag_domain ON rag_items(domain);
                CREATE INDEX IF NOT EXISTS rag_type ON rag_items(source_type);
                """
            )
            self._cleanup(conn, time.time())
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        finally:
            conn.close()
        self._initialized = True

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        tokens = []
        current = []
        for char in text.casefold():
            if char.isalnum() or char == "_":
                current.append(char)
            elif current:
                token = "".join(current)
                if len(token) >= 2:
                    tokens.append(token)
                current = []
        if current:
            token = "".join(current)
            if len(token) >= 2:
                tokens.append(token)
        return set(tokens)

    @classmethod
    def _lexical_score(cls, query: str, text: str) -> float:
        q = cls._tokenize(query)
        if not q:
            return 0.0
        d = cls._tokenize(text)
        return len(q & d) / len(q)

    @staticmethod
    def _cosine(a: Iterable[float], b: Iterable[float]) -> float:
        dot = norm_a = norm_b = 0.0
        for x, y in zip(a, b):
            dot += x * y
            norm_a += x * x
            norm_b += y * y
        if norm_a <= 0.0 or norm_b <= 0.0:
            return 0.0
        return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))

    @staticmethod
    def _pack(vector: list[float]) -> bytes:
        return struct.pack(f"<{len(vector)}f", *vector)

    @staticmethod
    def _unpack(blob: bytes) -> list[float]:
        if not blob:
            return []
        size = len(blob) // 4
        return list(struct.unpack(f"<{size}f", blob))

    @staticmethod
    def _freshness(created_at: float, now: float) -> float:
        age = max(0.0, now - created_at)
        if age <= 6 * 3600:
            return 1.0
        if age <= 24 * 3600:
            return 0.9
        if age <= 7 * 24 * 3600:
            return 0.65
        if age <= 30 * 24 * 3600:
            return 0.35
        return 0.05

    @staticmethod
    def _quality(domain: str | None, source_type: str) -> float:
        known = {
            "reuters.com": 1.0,
            "apnews.com": 0.98,
            "bbc.com": 0.96,
            "theguardian.com": 0.90,
            "timesofindia.indiatimes.com": 0.88,
            "indiatimes.com": 0.86,
            "gov.in": 1.0,
            "mha.gov.in": 1.0,
            "pib.gov.in": 1.0,
        }
        domain = (domain or "").casefold().removeprefix("www.")
        for host, score in known.items():
            if domain == host or domain.endswith("." + host):
                return score
        if source_type == "official":
            return 0.95
        if source_type == "web":
            return 0.65
        return 0.55

    def _cleanup(self, conn: sqlite3.Connection, now: float) -> None:
        conn.execute("DELETE FROM rag_items WHERE expires_at <= ?", (now,))
        row = conn.execute("SELECT COUNT(*) FROM rag_items").fetchone()
        count = int(row[0]) if row else 0
        if count > self.max_items:
            conn.execute(
                """
                DELETE FROM rag_items
                WHERE id IN (
                    SELECT id FROM rag_items
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (count - self.max_items,),
            )

    async def add(
        self,
        title: str,
        text: str,
        *,
        url: str | None = None,
        domain: str | None = None,
        source_type: str = "web",
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
        embed: bool = True,
    ) -> bool:
        self.initialize()
        title = str(title).strip()[:300]
        text = str(text).strip()[:8000]
        if not text:
            return False
        metadata = metadata or {}
        content_hash = hashlib.sha256(
            f"{title}\n{text}\n{url or ''}".encode("utf-8")
        ).hexdigest()
        # Gemini embeddings were removed. RAG remains available through
        # bounded lexical retrieval, which requires no external AI credential.
        embedding_blob = None
        dimensions = None
        model = "lexical"
        expires_at = time.time() + (ttl_seconds or self.default_ttl_seconds)

        def write() -> None:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO rag_items
                        (content_hash, title, text, url, domain, source_type,
                         metadata_json, embedding, embedding_model,
                         embedding_dimensions, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(content_hash) DO UPDATE SET
                        title=excluded.title,
                        text=excluded.text,
                        url=excluded.url,
                        domain=excluded.domain,
                        source_type=excluded.source_type,
                        metadata_json=excluded.metadata_json,
                        embedding=COALESCE(excluded.embedding, rag_items.embedding),
                        embedding_model=COALESCE(excluded.embedding_model, rag_items.embedding_model),
                        embedding_dimensions=COALESCE(excluded.embedding_dimensions, rag_items.embedding_dimensions),
                        created_at=excluded.created_at,
                        expires_at=excluded.expires_at
                    """,
                    (
                        content_hash,
                        title,
                        text,
                        url,
                        domain,
                        source_type,
                        json.dumps(metadata, ensure_ascii=False, default=str),
                        embedding_blob,
                        model,
                        dimensions,
                        time.time(),
                        expires_at,
                    ),
                )
                self._cleanup(conn, time.time())
            finally:
                conn.close()

        await asyncio.to_thread(write)
        return True

    async def search(self, query: str, limit: int = 6) -> RAGResult:
        import asyncio

        self.initialize()
        query = query.strip()
        if not query:
            return RAGResult([])

        # Retrieval is lexical-only after removing the external embedding service.
        query_vector: list[float] = []
        def read() -> list[sqlite3.Row]:
            conn = self._connect()
            try:
                self._cleanup(conn, time.time())
                return conn.execute(
                    """
                    SELECT id, title, text, url, domain, source_type,
                           metadata_json, embedding, embedding_model,
                           embedding_dimensions, created_at
                    FROM rag_items
                    WHERE expires_at > ?
                    LIMIT ?
                    """,
                    (time.time(), max(self.max_items, limit)),
                ).fetchall()
            finally:
                conn.close()

        rows = await asyncio.to_thread(read)
        now = time.time()
        candidates: list[RAGItem] = []
        for row in rows:
            semantic = 0.0
            blob = row["embedding"]
            if query_vector and blob and row["embedding_dimensions"] == len(query_vector):
                semantic = self._cosine(query_vector, self._unpack(blob))
            lexical = self._lexical_score(query, f"{row['title']} {row['text']}")
            freshness = self._freshness(float(row["created_at"]), now)
            quality = self._quality(row["domain"], row["source_type"])
            score = (
                0.55 * semantic
                + 0.25 * lexical
                + 0.10 * freshness
                + 0.10 * quality
            )
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except Exception:
                metadata = {}
            candidates.append(
                RAGItem(
                    item_id=int(row["id"]),
                    title=str(row["title"]),
                    text=str(row["text"]),
                    url=str(row["url"]) if row["url"] else None,
                    domain=str(row["domain"]) if row["domain"] else None,
                    source_type=str(row["source_type"]),
                    semantic_score=semantic,
                    lexical_score=lexical,
                    freshness_score=freshness,
                    quality_score=quality,
                    score=score,
                    metadata=metadata,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        selected: list[RAGItem] = []
        seen_urls: set[str] = set()
        for item in candidates:
            key = (item.url or f"item:{item.item_id}").casefold()
            if key in seen_urls:
                continue
            seen_urls.add(key)
            selected.append(item)
            if len(selected) >= max(1, limit):
                break
        return RAGResult(selected)


    async def close(self) -> None:
        return None
