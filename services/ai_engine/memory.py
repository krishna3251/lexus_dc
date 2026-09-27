"""Mongo-backed memory primitives for the Lexus AI Engine."""

from __future__ import annotations

import time

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
            await memories.create_index(
                [("user_id", 1), ("guild_id", 1), ("updated_at", -1)],
                name="ai_memory_lookup",
            )
        except Exception:
            return

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
