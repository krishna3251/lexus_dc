"""Low-storage local SQLite memory primitives for the Lexus AI Engine V3.

SQLite is used intentionally for AI memory so the engine does not depend on an
external database service. The database lives on the bot's local WispByte
filesystem and is bounded, TTL-cleaned, WAL-backed, and safe across processes.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
import re
from pathlib import Path
from typing import Any
from .config import number

import logging

logger = logging.getLogger(__name__)


DEFAULT_SQLITE_PATH = "/home/container/data/lexus_ai.sqlite3"


class AIMemoryService:
    """Bounded conversation history, durable memories, and message dedupe."""

    def __init__(
        self,
        max_history: int = 12,
        max_memories: int = 12,
        db_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self.max_history = max(1, min(max_history, 30))
        self.max_memories = max(1, min(max_memories, 30))
        configured_path = str(db_path).strip() if db_path is not None else ""
        configured_path = configured_path or os.getenv("AI_SQLITE_PATH", "").strip()
        self.db_path = Path(configured_path or DEFAULT_SQLITE_PATH).expanduser()
        self._initialized = False
        self._closed = False
        self._operation_lock = asyncio.Lock()
        self.history_ttl = number("AI_HISTORY_TTL", 86400, 60, 604800)
        self.memory_ttl = number("AI_MEMORY_TTL", 90 * 86400, 60, 365 * 86400)

    @staticmethod
    async def _run_sync(function, *args):
        # SQLite worker operations cannot be interrupted mid-transaction. Keep
        # the operation lock until they finish, even when a request is cancelled.
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    @property
    def backend(self) -> str:
        return "sqlite"

    @property
    def available(self) -> bool:
        return self._initialized and not self._closed and self.db_path.exists()

    def health(self) -> dict[str, Any]:
        try:
            size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        except OSError:
            size_bytes = 0
        return {
            "backend": self.backend,
            "available": self.available,
            "path": str(self.db_path),
            "size_bytes": size_bytes,
        }

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self.db_path,
            timeout=5.0,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize_sync(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA wal_autocheckpoint=1000")
            conn.execute("PRAGMA journal_size_limit=262144")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS ai_conversation_lookup
                    ON ai_conversations(user_id, guild_id, channel_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS ai_conversation_expiry
                    ON ai_conversations(expires_at);

                CREATE TABLE IF NOT EXISTS ai_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(user_id, guild_id, key)
                );

                CREATE INDEX IF NOT EXISTS ai_memory_lookup
                    ON ai_memories(user_id, guild_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS ai_message_dedupe (
                    message_id INTEGER PRIMARY KEY,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS ai_message_expiry
                    ON ai_message_dedupe(expires_at);

                CREATE TABLE IF NOT EXISTS ai_preferences (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    history_enabled INTEGER NOT NULL DEFAULT 0,
                    external_allowed INTEGER NOT NULL DEFAULT 1,
                    style TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(user_id, guild_id)
                );
                CREATE TABLE IF NOT EXISTS ai_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    helpful INTEGER NOT NULL CHECK(helpful IN (0, 1)),
                    created_at REAL NOT NULL
                );
                """
            )
            self._cleanup_sync(conn, time.time())
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        finally:
            conn.close()

    @staticmethod
    def _scope_id(value: int | None) -> int:
        return int(value) if value is not None else -1

    @staticmethod
    def _cleanup_sync(conn: sqlite3.Connection, now: float) -> None:
        conn.execute("DELETE FROM ai_conversations WHERE expires_at <= ?", (now,))
        conn.execute("DELETE FROM ai_message_dedupe WHERE expires_at <= ?", (now,))

    async def initialize(self) -> None:
        if self._initialized and not self._closed:
            return
        async with self._operation_lock:
            if self._initialized and not self._closed:
                return
            try:
                await self._run_sync(self._initialize_sync)
            except Exception:
                logger.exception("SQLite AI memory initialization failed | path=%s", self.db_path)
                self._initialized = False
                return
            self._closed = False
            self._initialized = True
            logger.info("🗃️ Lexus AI memory ready | SQLite=%s", self.db_path)

    async def _ensure_ready(self) -> bool:
        if self._closed:
            return False
        if not self._initialized or self._closed:
            await self.initialize()
        return self.available

    def _claim_message_sync(self, message_id: int) -> bool:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._cleanup_sync(conn, now)
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO ai_message_dedupe
                    (message_id, created_at, expires_at)
                VALUES (?, ?, ?)
                """,
                (int(message_id), now, now + 120),
            )
            conn.execute("COMMIT")
            return cursor.rowcount == 1
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    async def claim_message(self, message_id: int) -> bool | None:
        """Return True for first claimant, False for duplicate, None on local DB failure."""
        if not await self._ensure_ready():
            return None
        try:
            async with self._operation_lock:
                return await self._run_sync(self._claim_message_sync, int(message_id))
        except Exception:
            logger.exception("SQLite message dedupe failed | message=%s", message_id)
            return None

    def _add_turn_sync(
        self,
        user_id: int,
        guild_id: int,
        channel_id: int,
        role: str,
        content: str,
        request_id: str,
    ) -> bool:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._cleanup_sync(conn, now)
            conn.execute(
                """
                INSERT INTO ai_conversations
                    (user_id, guild_id, channel_id, role, content, request_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(user_id),
                    guild_id,
                    channel_id,
                    role,
                    content,
                    request_id[:64],
                    now,
                    now + self.history_ttl,
                ),
            )
            keep = self.max_history * 4
            conn.execute(
                """
                DELETE FROM ai_conversations
                WHERE user_id = ? AND guild_id = ? AND channel_id = ?
                  AND id NOT IN (
                      SELECT id FROM ai_conversations
                      WHERE user_id = ? AND guild_id = ? AND channel_id = ?
                      ORDER BY created_at DESC
                      LIMIT ?
                  )
                """,
                (
                    int(user_id), guild_id, channel_id,
                    int(user_id), guild_id, channel_id,
                    keep,
                ),
            )
            conn.execute("DELETE FROM ai_conversations WHERE id NOT IN (SELECT id FROM ai_conversations ORDER BY id DESC LIMIT 20000)")
            conn.execute("COMMIT")
            return True
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    async def add_turn(
        self,
        user_id: int,
        guild_id: int | None,
        channel_id: int | None,
        role: str,
        content: str,
        request_id: str,
    ) -> bool:
        if role not in {"user", "assistant"}:
            return False
        content = content.strip()[:4000]
        if not content or not await self._ensure_ready():
            return False
        try:
            async with self._operation_lock:
                return await self._run_sync(
                    self._add_turn_sync,
                    int(user_id),
                    self._scope_id(guild_id),
                    self._scope_id(channel_id),
                    role,
                    content,
                    request_id,
                )
        except Exception:
            logger.exception("SQLite conversation write failed | user=%s", user_id)
            return False

    def _recent_turns_sync(
        self,
        user_id: int,
        guild_id: int,
        channel_id: int,
    ) -> list[dict[str, str]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT role, content
                FROM ai_conversations
                WHERE user_id = ? AND guild_id = ? AND channel_id = ?
                  AND expires_at > ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (int(user_id), guild_id, channel_id, time.time(), self.max_history),
            ).fetchall()
            rows = list(reversed(rows))
            return [
                {"role": row["role"], "content": str(row["content"])[:4000]}
                for row in rows
                if row["role"] in {"user", "assistant"} and row["content"]
            ]
        finally:
            conn.close()

    async def recent_turns(
        self,
        user_id: int,
        guild_id: int | None,
        channel_id: int | None,
    ) -> list[dict[str, str]]:
        if not await self._ensure_ready():
            return []
        try:
            async with self._operation_lock:
                return await self._run_sync(
                    self._recent_turns_sync,
                    int(user_id),
                    self._scope_id(guild_id),
                    self._scope_id(channel_id),
                )
        except Exception:
            logger.exception("SQLite conversation read failed | user=%s", user_id)
            return []

    def _remember_sync(
        self,
        user_id: int,
        guild_id: int,
        key: str,
        value: str,
        source: str,
    ) -> bool:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM ai_memories WHERE updated_at <= ?", (now - self.memory_ttl,))
            conn.execute(
                """
                INSERT INTO ai_memories(user_id, guild_id, key, value, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id, key)
                DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (int(user_id), guild_id, key, value, source[:64], now),
            )
            conn.execute(
                """
                DELETE FROM ai_memories
                WHERE user_id = ? AND guild_id = ?
                  AND id NOT IN (
                      SELECT id FROM ai_memories
                      WHERE user_id = ? AND guild_id = ?
                      ORDER BY updated_at DESC
                      LIMIT ?
                  )
                """,
                (
                    int(user_id), guild_id,
                    int(user_id), guild_id,
                    self.max_memories,
                ),
            )
            conn.execute("COMMIT")
            return True
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    async def remember(
        self,
        user_id: int,
        guild_id: int | None,
        key: str,
        value: str,
        source: str = "explicit",
    ) -> bool:
        key = key.strip().lower()[:128]
        value = value.strip()[:1000]
        if not key or not value or not await self._ensure_ready():
            return False
        try:
            async with self._operation_lock:
                return await self._run_sync(
                    self._remember_sync,
                    int(user_id),
                    self._scope_id(guild_id),
                    key,
                    value,
                    source,
                )
        except Exception:
            logger.exception("SQLite durable memory write failed | user=%s", user_id)
            return False

    def _memories_sync(self, user_id: int, guild_id: int) -> list[dict[str, str]]:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM ai_memories WHERE updated_at <= ?", (time.time() - self.memory_ttl,))
            rows = conn.execute(
                """
                SELECT key, value, source
                FROM ai_memories
                WHERE user_id = ? AND guild_id = ?
                  AND updated_at > ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(user_id), guild_id, time.time() - self.memory_ttl, self.max_memories),
            ).fetchall()
            return [
                {
                    "key": str(row["key"])[:128],
                    "value": str(row["value"])[:1000],
                    "source": str(row["source"])[:64],
                }
                for row in rows
                if row["key"] and row["value"]
            ]
        finally:
            conn.close()

    async def memories(self, user_id: int, guild_id: int | None) -> list[dict[str, str]]:
        if not await self._ensure_ready():
            return []
        try:
            async with self._operation_lock:
                return await self._run_sync(
                    self._memories_sync,
                    int(user_id),
                    self._scope_id(guild_id),
                )
        except Exception:
            logger.exception("SQLite durable memory read failed | user=%s", user_id)
            return []

    def _forget_sync(self, user_id: int, guild_id: int, key: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM ai_memories WHERE user_id = ? AND guild_id = ? AND key = ?",
                (int(user_id), guild_id, key),
            )
            return cursor.rowcount > 0
        finally:
            conn.close()

    async def forget(self, user_id: int, guild_id: int | None, key: str) -> bool:
        if not await self._ensure_ready():
            return False
        try:
            async with self._operation_lock:
                return await self._run_sync(
                    self._forget_sync,
                    int(user_id),
                    self._scope_id(guild_id),
                    key.strip().lower()[:128],
                )
        except Exception:
            logger.exception("SQLite durable memory delete failed | user=%s", user_id)
            return False

    def _clear_history_sync(self, user_id: int, guild_id: int, channel_id: int) -> bool:
        conn = self._connect()
        try:
            conn.execute(
                """
                DELETE FROM ai_conversations
                WHERE user_id = ? AND guild_id = ? AND channel_id = ?
                """,
                (int(user_id), guild_id, channel_id),
            )
            return True
        finally:
            conn.close()

    async def clear_history(
        self,
        user_id: int,
        guild_id: int | None,
        channel_id: int | None,
    ) -> bool:
        if not await self._ensure_ready():
            return False
        try:
            async with self._operation_lock:
                return await self._run_sync(
                    self._clear_history_sync,
                    int(user_id),
                    self._scope_id(guild_id),
                    self._scope_id(channel_id),
                )
        except Exception:
            logger.exception("SQLite conversation cleanup failed | user=%s", user_id)
            return False

    async def close(self) -> None:
        self._closed = True

    async def relevant_memories(self, user_id: int, guild_id: int | None,
                                query: str, max_chars: int = 3000) -> list[dict[str, str]]:
        """Rank only this owner's bounded approved records; no embedding API."""
        memories = await self.memories(user_id, guild_id)
        tokens = set(re.findall(r"\w+", query.casefold()))
        def score(item):
            words = set(re.findall(r"\w+", f"{item['key']} {item['value']}".casefold()))
            return len(words & tokens) + (0.5 if item['key'] in {"language", "style"} else 0)
        result = []
        for item in sorted(memories, key=score, reverse=True):
            size = len(item['key']) + len(item['value'])
            if size <= max_chars:
                result.append(item)
                max_chars -= size
        return result

    async def _operation(self, operation, fallback):
        if not await self._ensure_ready():
            return fallback
        def run():
            conn = self._connect()
            try:
                return operation(conn)
            finally:
                conn.close()
        try:
            async with self._operation_lock:
                return await self._run_sync(run)
        except Exception as exc:
            logger.warning("Memory operation failed | type=%s", type(exc).__name__)
            return fallback

    async def preferences(self, user_id: int, guild_id: int | None) -> dict:
        def read(conn):
            row = conn.execute("SELECT history_enabled, external_allowed, style FROM ai_preferences WHERE user_id=? AND guild_id=?",
                               (user_id, self._scope_id(guild_id))).fetchone()
            return dict(row) if row else {"history_enabled": False, "external_allowed": True, "style": ""}
        # Fail closed on a storage failure; unknown privacy policy cannot authorize egress.
        return await self._operation(read, {"history_enabled": False, "external_allowed": False, "style": ""})

    async def set_preferences(self, user_id: int, guild_id: int | None, *,
                              history_enabled: bool, external_allowed: bool, style: str = "") -> bool:
        from .brain import ResponseStyle
        if style and style not in ResponseStyle.STYLES:
            return False
        def write(conn):
            conn.execute("INSERT INTO ai_preferences VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, guild_id) DO UPDATE SET history_enabled=excluded.history_enabled, external_allowed=excluded.external_allowed, style=excluded.style",
                         (user_id, self._scope_id(guild_id), bool(history_enabled), bool(external_allowed), style))
            if not history_enabled:
                conn.execute("DELETE FROM ai_conversations WHERE user_id=? AND guild_id=?",
                             (user_id, self._scope_id(guild_id)))
            return True
        return await self._operation(write, False)

    async def clear_user(self, user_id: int, guild_id: int | None) -> bool:
        def delete(conn):
            conn.execute("BEGIN IMMEDIATE")
            for table in ("ai_conversations", "ai_memories", "ai_feedback"):
                conn.execute(f"DELETE FROM {table} WHERE user_id=? AND guild_id=?", (user_id, self._scope_id(guild_id)))
            # Retain privacy choices so deletion does not re-enable external inference.
            conn.execute("COMMIT")
            return True
        return await self._operation(delete, False)

    async def clear_history_user(self, user_id: int, guild_id: int | None) -> bool:
        def delete(conn):
            conn.execute("DELETE FROM ai_conversations WHERE user_id=? AND guild_id=?",
                         (user_id, self._scope_id(guild_id)))
            return True
        return await self._operation(delete, False)

    async def feedback(self, user_id: int, guild_id: int | None, helpful: bool) -> bool:
        def write(conn):
            conn.execute("INSERT INTO ai_feedback(user_id,guild_id,helpful,created_at) VALUES(?,?,?,?)",
                         (user_id, self._scope_id(guild_id), bool(helpful), time.time()))
            conn.execute("DELETE FROM ai_feedback WHERE created_at < ? OR id NOT IN (SELECT id FROM ai_feedback ORDER BY id DESC LIMIT 1000)",
                         (time.time() - 30 * 86400,))
            return True
        return await self._operation(write, False)
