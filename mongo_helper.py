"""
Centralized MongoDB helper for Lexus bot.

Requires MONGO_URI in .env (free M0 Atlas cluster is fine).
Uses motor for async operations with discord.py.
"""

import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("MONGO_DB_NAME", "lexus_bot")

_client: AsyncIOMotorClient = None
_db = None


async def connect():
    """Connect to MongoDB. Call once at bot startup."""
    global _client, _db
    if not MONGO_URI:
        logger.warning("MONGO_URI not set – MongoDB features disabled.")
        return None
    try:
        _client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Verify connection
        await _client.admin.command("ping")
        _db = _client[DB_NAME]
        logger.info(f"✅ Connected to MongoDB database: {DB_NAME}")
        return _db
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        _client = None
        _db = None
        return None


async def disconnect():
    """Gracefully close MongoDB connection."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed.")


def get_db():
    """Return the database instance (None if not connected)."""
    return _db


def get_collection(name: str):
    """Shortcut to get a collection. Returns None if DB not connected."""
    if _db is None:
        return None
    return _db[name]


# ─── Collection helpers ────────────────────────────────────────────

async def get_guild_config(guild_id: int) -> dict:
    """Get full config document for a guild, or empty dict."""
    col = get_collection("guild_config")
    if col is None:
        return {}
    doc = await col.find_one({"guild_id": guild_id})
    return doc or {}


async def update_guild_config(guild_id: int, update: dict):
    """Upsert a guild config field."""
    col = get_collection("guild_config")
    if col is None:
        return
    await col.update_one(
        {"guild_id": guild_id},
        {"$set": update},
        upsert=True,
    )


async def get_antinuke(guild_id: int) -> dict:
    """Get antinuke settings for a guild."""
    col = get_collection("antinuke")
    if col is None:
        return {}
    doc = await col.find_one({"guild_id": guild_id})
    return doc or {}


async def update_antinuke(guild_id: int, update: dict):
    """Upsert antinuke settings."""
    col = get_collection("antinuke")
    if col is None:
        return
    await col.update_one(
        {"guild_id": guild_id},
        {"$set": update},
        upsert=True,
    )


async def get_warnings(guild_id: int, user_id: int) -> list:
    """Get all warnings for a user in a guild."""
    col = get_collection("warnings")
    if col is None:
        return []
    cursor = col.find({"guild_id": guild_id, "user_id": user_id}).sort("timestamp", -1)
    return await cursor.to_list(length=100)


async def add_warning(doc: dict):
    """Insert a warning document."""
    col = get_collection("warnings")
    if col is None:
        return
    await col.insert_one(doc)


async def get_karma(guild_id: int, user_id: int) -> dict:
    """Get karma record for a user."""
    col = get_collection("karma")
    if col is None:
        return {}
    doc = await col.find_one({"guild_id": guild_id, "user_id": user_id})
    return doc or {}


async def update_karma(guild_id: int, user_id: int, update: dict):
    """Upsert karma record."""
    col = get_collection("karma")
    if col is None:
        return
    await col.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": update},
        upsert=True,
    )


async def inc_karma(guild_id: int, user_id: int, increments: dict):
    """Increment karma fields atomically."""
    col = get_collection("karma")
    if col is None:
        return
    await col.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$inc": increments},
        upsert=True,
    )


async def get_levels(guild_id: int, user_id: int) -> dict:
    """Get XP/level record."""
    col = get_collection("levels")
    if col is None:
        return {}
    doc = await col.find_one({"guild_id": guild_id, "user_id": user_id})
    return doc or {}


async def update_levels(guild_id: int, user_id: int, update: dict):
    """Upsert level record."""
    col = get_collection("levels")
    if col is None:
        return
    await col.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": update},
        upsert=True,
    )


async def inc_levels(guild_id: int, user_id: int, increments: dict):
    """Increment XP fields atomically."""
    col = get_collection("levels")
    if col is None:
        return
    await col.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$inc": increments},
        upsert=True,
    )


async def get_economy(guild_id: int, user_id: int) -> dict:
    """Get economy record."""
    col = get_collection("economy")
    if col is None:
        return {}
    doc = await col.find_one({"guild_id": guild_id, "user_id": user_id})
    return doc or {}


async def update_economy(guild_id: int, user_id: int, update: dict):
    """Upsert economy record."""
    col = get_collection("economy")
    if col is None:
        return
    await col.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$set": update},
        upsert=True,
    )


async def inc_economy(guild_id: int, user_id: int, increments: dict):
    """Increment economy fields atomically."""
    col = get_collection("economy")
    if col is None:
        return
    await col.update_one(
        {"guild_id": guild_id, "user_id": user_id},
        {"$inc": increments},
        upsert=True,
    )
