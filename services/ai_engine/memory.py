"""Persistent, bounded AI memory backed by MongoDB.

The memory layer deliberately separates conversation history from durable user
memories. Durable memories are not inferred automatically by the model; they
must be written through an explicit application flow or a trusted future tool.
"""

from __future__ import annotations

import time
from typing import Any

import mongo_helper


class AIMemoryService:
    """Mongo-backed memory service with safe no-database behavior."""

    CONVERSATIONS = "ai_conversations"
    MEMORIES = "ai_memories"

    def __init__(self, *, max_history: int = 12, max_memories: int = 12) -> None:
        self.max_history = max(1, min(max_history, 30))
        self.max_memories = max(1, min(max_memories, 30))

    @property
    def available(self) -> bool:
        return mongo_helper.get_db() is not None

    async def initialize(self) -> None:
        """Create the small set of indexes used by the AI memory layer."""
        conversations = mongo_helper.get_collection(self.CONVERSATIONS)
        memories = mongo_helper.get_collection(self.MEMORIES)
        if conversations is None or memories is None:
            return

        try:
            await conversations.create_index(
                [("user_id", 1), ("guild_id", 1), ("channel_id", 1), ("created_at", -1)],
                name="ai_conversation_lookup",
            )
            await conversations.create_index(
                [("expires_at", 1)],
                name="ai_conversation_ttl",
                expireAfterSeconds=0,
            )
            await memories.create_index(
                [("user_id", 1), ("guild_id", 1), ("updated_at", -1)],
                name="ai_memory_lookup",
            )
            await memories.create_index(
                [("expires_at", 1)],
                name="ai_memory_ttl",
                expireAfterSeconds=0,
                sparse=True,
            )
        except Exception:
            # Index creation must never prevent the bot from starting.
            return

    async def add_turn(
        self,
        *,
        user_id: int,
        guild_id: int | None,
        channel_id: int | None,
        role: str,
        content: str,
        request_id: str,
        ttl_seconds: int = 7 * 24 * 60 * 60,
    ) -> bool:
        """Store one user/assistant turn with bounded content."""
        col = mongo_helper.get_collection(self.CONVERSATIONS)
        if col is None:
            return False

        content = content.strip()
        if not content or role not in {"user", "assistant"}:
            return False

        document: dict[str, Any] = {
            "user_id": int(user_id),
            "guild_id": int(guild_id) if guild_id is not None else None,
            "channel_id": int(channel_id) if channel_id is not None else None,
            "role": role,
            "content": content[:4000],
            "request_id": request_id[:64],
            "created_at": time.time(),
            "expires_at": time.time() + max(3600, ttl_seconds),
        }
        try:
            await col.insert_one(document)
            return True
        except Exception:
            return False

    async def recent_turns(
        self,
        *,
        user_id: int,
        guild_id: int | None,
        channel_id: int | None,
    ) -> list[dict[str, str]]:
        """Return the newest conversation turns in chronological order."""
        col = mongo_helper.get_collection(self.CONVERSATIONS)
        if col is None:
            return []

        query = {
            "user_id": int(user_id),
            "guild_id": int(guild_id) if guild_id is not None else None,
            "channel_id": int(channel_id) if channel_id is not None else None,
        }
        try:
            cursor = (
                col.find(query, {"_id": 0, "role": 1, "content": 1})
                .sort("created_at", -1)
                .limit(self.max_history)
            )
            rows = await cursor.to_list(length=self.max_history)
        except Exception:
            return []

        rows.reverse()
        return [
            {"role": row["role"], "content": str(row["content"])[:4000]}
            for row in rows
            if row.get("role") in {"user", "assistant"} and row.get("content")
        ]

    async def remember(
        self,
        *,
        user_id: int,
        guild_id: int | None,
        key: str,
        value: str,
        source: str = "explicit",
        ttl_seconds: int | None = None,
    ) -> bool:
        """Upsert one explicit durable memory."""
        col = mongo_helper.get_collection(self.MEMORIES)
        if col is None:
            return False

        key = key.strip().lower()[:128]
        value = value.strip()[:1000]
        if not key or not value:
            return False

        now = time.time()
        document: dict[str, Any] = {
            "user_id": int(user_id),
            "guild_id": int(guild_id) if guild_id is not None else None,
            "key": key,
            "value": value,
            "source": source[:64],
            "updated_at": now,
            "created_at": now,
        }
        if ttl_seconds is not None:
            document["expires_at"] = now + max(3600, ttl_seconds)

        try:
            await col.update_one(
                {
                    "user_id": int(user_id),
                    "guild_id": int(guild_id) if guild_id is not None else None,
                    "key": key,
                },
                {"$set": document, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            return True
        except Exception:
            return False

    async def memories(
        self,
        *,
        user_id: int,
        guild_id: int | None,
    ) -> list[dict[str, str]]:
        """Return durable memories for this user/scope."""
        col = mongo_helper.get_collection(self.MEMORIES)
        if col is None:
            return []

        query = {
            "user_id": int(user_id),
            "guild_id": int(guild_id) if guild_id is not None else None,
        }
        try:
            cursor = (
                col.find(query, {"_id": 0, "key": 1, "value": 1, "source": 1})
                .sort("updated_at", -1)
                .limit(self.max_memories)
            )
            rows = await cursor.to_list(length=self.max_memories)
        except Exception:
            return []

        return [
            {
                "key": str(row.get("key", ""))[:128],
                "value": str(row.get("value", ""))[:1000],
                "source": str(row.get("source", "unknown"))[:64],
            }
            for row in rows
            if row.get("key") and row.get("value")
        ]

    async def forget(
        self,
        *,
        user_id: int,
        guild_id: int | None,
        key: str,
    ) -> bool:
        """Delete one durable memory owned by the requesting user."""
        col = mongo_helper.get_collection(self.MEMORIES)
        if col is None:
            return False

        try:
            result = await col.delete_one(
                {
                    "user_id": int(user_id),
                    "guild_id": int(guild_id) if guild_id is not None else None,
                    "key": key.strip().lower()[:128],
                }
            )
            return result.deleted_count > 0
        except Exception:
            return False

    async def clear_history(
        self,
        *,
        user_id: int,
        guild_id: int | None,
        channel_id: int | None,
    ) -> bool:
        """Delete conversation history for one user/channel scope."""
        col = mongo_helper.get_collection(self.CONVERSATIONS)
        if col is None:
            return False

        try:
            await col.delete_many(
                {
                    "user_id": int(user_id),
                    "guild_id": int(guild_id) if guild_id is not None else None,
                    "channel_id": int(channel_id) if channel_id is not None else None,
                }
            )
            return True
        except Exception:
            return False
