"""
Database persistence service for Lexus Security Engine.
Integrates with MongoDB with an automatic in-memory fallback if the database
is offline or experiencing intermittent connectivity issues.
"""

from __future__ import annotations
import logging
import time
from typing import Optional, Any
import mongo_helper
from core.logging import security_logger

logger = logging.getLogger(__name__)


class SecurityDatabaseService:
    """Provides resilient persistence for security events, incidents, baselines, and configuration."""

    def __init__(self):
        # In-memory fallbacks when MongoDB is offline
        self._fallback_config: dict[int, dict[str, Any]] = {}
        self._fallback_incidents: dict[str, dict[str, Any]] = {}
        self._fallback_baselines: dict[int, dict[str, Any]] = {}
        self._fallback_quarantine: dict[tuple[int, int], dict[str, Any]] = {}
        self._fallback_trust: dict[int, dict[str, Any]] = {}

    def is_connected(self) -> bool:
        return mongo_helper.get_db() is not None

    # ── Security Configuration ─────────────────────────────────────

    async def get_config(self, guild_id: int) -> dict[str, Any]:
        """Fetch security config for a guild or return in-memory/default."""
        try:
            col = mongo_helper.get_collection("security_config")
            if col is not None:
                doc = await col.find_one({"guild_id": guild_id})
                if doc:
                    return doc
        except Exception as e:
            security_logger.database_failure("get_config", e)

        return self._fallback_config.get(guild_id, {})

    async def save_config(self, guild_id: int, config_data: dict[str, Any]) -> bool:
        """Upsert security configuration."""
        self._fallback_config[guild_id] = {**self._fallback_config.get(guild_id, {}), **config_data}
        try:
            col = mongo_helper.get_collection("security_config")
            if col is not None:
                config_data["updated_at"] = time.time()
                await col.update_one(
                    {"guild_id": guild_id},
                    {"$set": config_data},
                    upsert=True
                )
                return True
        except Exception as e:
            security_logger.database_failure("save_config", e)
        return False

    # ── Incidents ──────────────────────────────────────────────────

    async def save_incident(self, incident_data: dict[str, Any]) -> bool:
        """Upsert a security incident document."""
        inc_id = incident_data.get("incident_id")
        if inc_id:
            self._fallback_incidents[inc_id] = incident_data

        try:
            col = mongo_helper.get_collection("security_incidents")
            if col is not None:
                await col.update_one(
                    {"incident_id": inc_id},
                    {"$set": incident_data},
                    upsert=True
                )
                return True
        except Exception as e:
            security_logger.database_failure("save_incident", e)
        return False

    async def get_incident(self, incident_id: str) -> Optional[dict[str, Any]]:
        """Retrieve an incident by ID."""
        try:
            col = mongo_helper.get_collection("security_incidents")
            if col is not None:
                doc = await col.find_one({"incident_id": incident_id})
                if doc:
                    return doc
        except Exception as e:
            security_logger.database_failure("get_incident", e)

        return self._fallback_incidents.get(incident_id)

    async def get_recent_incidents(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        """Retrieve recent incidents for a guild."""
        try:
            col = mongo_helper.get_collection("security_incidents")
            if col is not None:
                cursor = col.find({"guild_id": guild_id}).sort("created_at", -1).limit(limit)
                return await cursor.to_list(length=limit)
        except Exception as e:
            security_logger.database_failure("get_recent_incidents", e)

        # Fallback
        items = [
            inc for inc in self._fallback_incidents.values()
            if inc.get("guild_id") == guild_id
        ]
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return items[:limit]

    # ── Events & Actions (Bounded / TTL) ──────────────────────────

    async def log_event(self, event_data: dict[str, Any]) -> bool:
        """Persist a normalized security event."""
        try:
            col = mongo_helper.get_collection("security_events")
            if col is not None:
                await col.insert_one(event_data)
                return True
        except Exception as e:
            security_logger.database_failure("log_event", e)
        return False

    async def log_action(self, action_data: dict[str, Any]) -> bool:
        """Persist a security action result."""
        try:
            col = mongo_helper.get_collection("security_actions")
            if col is not None:
                await col.insert_one(action_data)
                return True
        except Exception as e:
            security_logger.database_failure("log_action", e)
        return False

    # ── Baselines & Snapshots ──────────────────────────────────────

    async def save_baseline(self, guild_id: int, baseline_data: dict[str, Any]) -> bool:
        """Store trusted server structural baseline."""
        self._fallback_baselines[guild_id] = baseline_data
        try:
            col = mongo_helper.get_collection("security_baselines")
            if col is not None:
                await col.update_one(
                    {"guild_id": guild_id},
                    {"$set": baseline_data},
                    upsert=True
                )
                return True
        except Exception as e:
            security_logger.database_failure("save_baseline", e)
        return False

    async def get_baseline(self, guild_id: int) -> Optional[dict[str, Any]]:
        """Retrieve trusted baseline."""
        try:
            col = mongo_helper.get_collection("security_baselines")
            if col is not None:
                doc = await col.find_one({"guild_id": guild_id})
                if doc:
                    return doc
        except Exception as e:
            security_logger.database_failure("get_baseline", e)

        return self._fallback_baselines.get(guild_id)

    # ── Quarantine State ───────────────────────────────────────────

    async def save_quarantine(self, guild_id: int, user_id: int, data: dict[str, Any]) -> bool:
        """Store quarantine record including member's stripped roles."""
        key = (guild_id, user_id)
        self._fallback_quarantine[key] = data
        try:
            col = mongo_helper.get_collection("security_quarantine")
            if col is not None:
                await col.update_one(
                    {"guild_id": guild_id, "user_id": user_id},
                    {"$set": data},
                    upsert=True
                )
                return True
        except Exception as e:
            security_logger.database_failure("save_quarantine", e)
        return False

    async def get_quarantine(self, guild_id: int, user_id: int) -> Optional[dict[str, Any]]:
        """Retrieve quarantine details."""
        try:
            col = mongo_helper.get_collection("security_quarantine")
            if col is not None:
                doc = await col.find_one({"guild_id": guild_id, "user_id": user_id})
                if doc:
                    return doc
        except Exception as e:
            security_logger.database_failure("get_quarantine", e)

        return self._fallback_quarantine.get((guild_id, user_id))

    async def remove_quarantine(self, guild_id: int, user_id: int) -> bool:
        """Remove quarantine record on release."""
        key = (guild_id, user_id)
        self._fallback_quarantine.pop(key, None)
        try:
            col = mongo_helper.get_collection("security_quarantine")
            if col is not None:
                await col.delete_one({"guild_id": guild_id, "user_id": user_id})
                return True
        except Exception as e:
            security_logger.database_failure("remove_quarantine", e)
        return False


# Global singleton instance
security_db = SecurityDatabaseService()
