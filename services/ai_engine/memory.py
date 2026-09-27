"""Mongo-backed memory primitives for the Lexus AI Engine."""

from __future__ import annotations

import time

from pymongo.errors import DuplicateKeyError

import mongo_helper


class AIMemoryService:
    """Bounded conversation history and explicit durable memories."""

    def __init__(self, max_history: int = 12, max_memories: int = 12) -> None:
        self.max_history = max(1, min(max_history, 30))
        self.max_memories = max(1, min(max_memories, 30))

    @property
    def available(self) -> bool:
        return mongo_helper.get_db() is not None

    async def initialize(self) -> None:
        conversations = mongo_helper.get_collection("ai_conversations")
        memories = mongo_helper.get_collection("ai_memories")
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
            dedupe = mongo_helper.get_collection("ai_message_dedupe")
            if dedupe is not None:
                await dedupe.create_index(
                    [("message_id", 1)],
                    unique=True,
                    name="ai_message_unique",
                )
                await dedupe.create_index(
                    [("expires_at", 1)],
                    name="ai_message_ttl",
                    expireAfterSeconds=0,
                )
            await memories.create_index(
                [("user_id", 1), ("guild_id", 1), ("updated_at", -1)],
                name="ai_memory_lookup",
            )
        except Exception:
            return

    async def claim_message(self, message_id: int) -> bool | None:
        """Claim a Discord message across bot processes when Mongo is available.

        Returns True for the first claimant, False for a duplicate, and None
        when Mongo is unavailable so the caller can fall back to local dedupe.
        """
        col = mongo_helper.get_collection("ai_message_dedupe")
        if col is None:
            return None
        now = time.time()
        try:
            await col.insert_one({
                "message_id": int(message_id),
                "created_at": now,
                "expires_at": now + 120,
            })
            return True
        except DuplicateKeyError:
            return False
        except Exception:
            return None
    async def add_turn(self, user_id: int, guild_id: int | None, channel_id: int | None, role: str, content: str, request_id: str) -> bool:
        col = mongo_helper.get_collection("ai_conversations")
        if col is None or role not in {"user", "assistant"}:
            return False
        content = content.strip()[:4000]
        if not content:
            return False
        now = time.time()
        try:
            await col.insert_one({
                "user_id": int(user_id),
                "guild_id": int(guild_id) if guild_id is not None else None,
                "channel_id": int(channel_id) if channel_id is not None else None,
                "role": role,
                "content": content,
                "request_id": request_id[:64],
                "created_at": now,
                "expires_at": now + 7 * 24 * 60 * 60,
            })
            return True
        except Exception:
            return False

    async def recent_turns(self, user_id: int, guild_id: int | None, channel_id: int | None) -> list[dict[str, str]]:
        col = mongo_helper.get_collection("ai_conversations")
        if col is None:
            return []
        try:
            cursor = col.find({
                "user_id": int(user_id),
                "guild_id": int(guild_id) if guild_id is not None else None,
                "channel_id": int(channel_id) if channel_id is not None else None,
            }, {"_id": 0, "role": 1, "content": 1}).sort("created_at", -1).limit(self.max_history)
            rows = await cursor.to_list(length=self.max_history)
        except Exception:
            return []
        rows.reverse()
        return [{"role": r["role"], "content": str(r["content"])[:4000]} for r in rows if r.get("role") in {"user", "assistant"} and r.get("content")]

    async def remember(self, user_id: int, guild_id: int | None, key: str, value: str, source: str = "explicit") -> bool:
        col = mongo_helper.get_collection("ai_memories")
        if col is None:
            return False
        key = key.strip().lower()[:128]
        value = value.strip()[:1000]
        if not key or not value:
            return False
        try:
            await col.update_one(
                {"user_id": int(user_id), "guild_id": int(guild_id) if guild_id is not None else None, "key": key},
                {"$set": {"value": value, "source": source[:64], "updated_at": time.time()}},
                upsert=True,
            )
            return True
        except Exception:
            return False

    async def memories(self, user_id: int, guild_id: int | None) -> list[dict[str, str]]:
        """Return the newest explicit durable memories for this scope."""
        col = mongo_helper.get_collection("ai_memories")
        if col is None:
            return []
        try:
            cursor = col.find({
                "user_id": int(user_id),
                "guild_id": int(guild_id) if guild_id is not None else None,
            }, {"_id": 0, "key": 1, "value": 1, "source": 1})
            cursor = cursor.sort("updated_at", -1).limit(self.max_memories)
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

    async def forget(self, user_id: int, guild_id: int | None, key: str) -> bool:
        """Delete one explicit durable memory owned by the requester."""
        col = mongo_helper.get_collection("ai_memories")
        if col is None:
            return False
        try:
            result = await col.delete_one({
                "user_id": int(user_id),
                "guild_id": int(guild_id) if guild_id is not None else None,
                "key": key.strip().lower()[:128],
            })
            return result.deleted_count > 0
        except Exception:
            return False

    async def clear_history(self, user_id: int, guild_id: int | None, channel_id: int | None) -> bool:
        """Delete conversation history for this user/channel scope."""
        col = mongo_helper.get_collection("ai_conversations")
        if col is None:
            return False
        try:
            await col.delete_many({
                "user_id": int(user_id),
                "guild_id": int(guild_id) if guild_id is not None else None,
                "channel_id": int(channel_id) if channel_id is not None else None,
            })
            return True
        except Exception:
            return False
