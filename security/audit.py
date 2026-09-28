"""Audit log correlation engine for structural security events.

Discord gateway events can arrive before their corresponding Audit Log entry.
This correlator therefore uses target-strict matching and short bounded retries
instead of trusting whichever recent entry happens to be first.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional, Any

import discord

from core.logging import security_logger


class AuditLogCorrelator:
    """Reliably correlate Discord structural events with their Audit Log actor."""

    def __init__(
        self,
        max_entries: int = 10,
        max_age_seconds: float = 15.0,
        retry_delays: tuple[float, ...] = (0.0, 0.35, 0.75),
    ):
        self.max_entries = max_entries
        self.max_age_seconds = max_age_seconds
        self.retry_delays = retry_delays

    async def find_actor_for_event(
        self,
        guild: discord.Guild,
        action_type: discord.AuditLogAction,
        target_id: Optional[int] = None,
        max_age_seconds: Optional[float] = None,
        retry_delay: float = 0.35,
    ) -> Optional[tuple[int, dict[str, Any]]]:
        """
        Return (actor_id, metadata) for the audit entry matching this event.

        Matching is deliberately strict when target_id is supplied. A recent
        audit entry for a different role/member/channel must never be accepted
        as the actor for the current event.
        """
        bot = guild.me
        if bot is None or not bot.guild_permissions.view_audit_log:
            security_logger.audit_failure(
                guild.id,
                str(action_type),
                "Bot lacks View Audit Log permission",
            )
            return None

        age_limit = max_age_seconds if max_age_seconds is not None else self.max_age_seconds
        delays = self.retry_delays or (retry_delay,)

        for attempt, delay in enumerate(delays, start=1):
            if delay > 0:
                await asyncio.sleep(delay)

            try:
                entries: list[discord.AuditLogEntry] = []
                async for entry in guild.audit_logs(
                    action=action_type,
                    limit=self.max_entries,
                ):
                    entries.append(entry)

                wall_now = time.time()

                for entry in entries:
                    created_at = entry.created_at
                    entry_age = wall_now - created_at.timestamp()

                    # Ignore future/skewed entries and stale entries.
                    if entry_age < -2.0 or entry_age > age_limit:
                        continue

                    entry_target_id = getattr(entry.target, "id", None)

                    # When the gateway event identifies a target, an audit
                    # entry without that target is not a valid correlation.
                    if target_id is not None and entry_target_id != target_id:
                        continue

                    actor = entry.user
                    actor_id = getattr(actor, "id", None)
                    if not actor_id:
                        continue

                    meta = {
                        "audit_id": entry.id,
                        "action": str(entry.action),
                        "reason": entry.reason,
                        "entry_age": round(max(0.0, entry_age), 3),
                        "target_id": entry_target_id,
                        "correlation_attempt": attempt,
                        "attribution": "audit_log",
                    }
                    return actor_id, meta

            except (discord.Forbidden, discord.HTTPException) as exc:
                security_logger.audit_failure(
                    guild.id,
                    str(action_type),
                    f"Audit lookup attempt {attempt} failed: {exc}",
                )
            except Exception as exc:
                security_logger.audit_failure(
                    guild.id,
                    str(action_type),
                    f"Audit lookup attempt {attempt} failed: {exc}",
                )

        security_logger.audit_failure(
            guild.id,
            str(action_type),
            f"No matching audit entry found for target_id={target_id} after {len(delays)} attempts",
        )
        return None


audit_correlator = AuditLogCorrelator()
