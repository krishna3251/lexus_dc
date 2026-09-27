"""
Audit log correlation engine with lookup budgets, short caches, and evidence buffering.
Matches structural platform events against Discord audit logs to reliably identify actors.
"""

from __future__ import annotations
import time
import asyncio
from typing import Optional, Any
import discord
from services.cache import TTLCache
from core.logging import security_logger


class AuditLogCorrelator:
    """
    Correlates structural events with Discord audit logs while strictly enforcing
    rate limits and lookup budgets to avoid API exhaustion during raids or attacks.
    """

    def __init__(self, cache_ttl: float = 5.0, cooldown_seconds: float = 2.0):
        # Cache recent audit entries: (guild_id, action_type_value) -> (list of entry data, timestamp)
        self._cache: TTLCache[tuple[int, int], list[dict[str, Any]]] = TTLCache(max_size=500, default_ttl=cache_ttl)
        # Guild lookup cooldown: guild_id -> last_lookup_timestamp
        self._guild_cooldowns: TTLCache[int, float] = TTLCache(max_size=500, default_ttl=cooldown_seconds)

    async def find_actor_for_event(
        self,
        guild: discord.Guild,
        action_type: discord.AuditLogAction,
        target_id: Optional[int] = None,
        max_age_seconds: float = 10.0,
        retry_delay: float = 0.5
    ) -> Optional[tuple[int, dict[str, Any]]]:
        """
        Lookup audit logs to identify actor.
        Returns (actor_id, entry_metadata) or None if inconclusive.
        """
        # Bot permission check
        bot = guild.me
        if not bot.guild_permissions.view_audit_log:
            security_logger.audit_failure(guild.id, str(action_type), "Bot lacks View Audit Log permission")
            return None

        # Check cooldown to prevent hammering during fast operations
        now = time.monotonic()
        last_lookup = self._guild_cooldowns.get(guild.id)
        if last_lookup and (now - last_lookup) < 0.5:
            # Yield briefly rather than hammering API
            await asyncio.sleep(retry_delay)

        self._guild_cooldowns.set(guild.id, time.monotonic())

        # Attempt lookup
        try:
            entries: list[discord.AuditLogEntry] = []
            async for entry in guild.audit_logs(action=action_type, limit=5):
                entries.append(entry)

            # Match target and timestamp
            wall_now = time.time()
            for entry in entries:
                entry_age = wall_now - entry.created_at.timestamp()
                if entry_age > max_age_seconds:
                    continue

                if target_id is not None:
                    # Match target if available
                    entry_target_id = getattr(entry.target, "id", None)
                    if entry_target_id and entry_target_id != target_id:
                        continue

                # Found matching audit entry
                actor_id = entry.user.id if entry.user else None
                if actor_id:
                    meta = {
                        "audit_id": entry.id,
                        "action": str(entry.action),
                        "reason": entry.reason,
                        "entry_age": round(entry_age, 2)
                    }
                    return actor_id, meta

        except Exception as e:
            security_logger.audit_failure(guild.id, str(action_type), str(e))

        return None


# Global audit correlator instance
audit_correlator = AuditLogCorrelator()
