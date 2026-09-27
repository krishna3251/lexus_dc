"""
Lockdown and panic defense engine for Lexus Security Engine.
Provides targeted channel restriction, panic state containment, and reversible lockdown.
"""

from __future__ import annotations
import time
import logging
from typing import Optional, Any
import discord
from security.models import SecurityState, ActionResult, SecurityActionType, GuildSecurityConfig
from core.logging import security_logger
from services.cache import TTLCache

logger = logging.getLogger(__name__)


class LockdownManager:
    """Manages server lockdowns, targeted channel freezes, and emergency panic state responses."""

    def __init__(self):
        # Maps guild_id -> list[locked_channel_id]
        self._active_lockdowns: TTLCache[int, list[int]] = TTLCache(max_size=500, default_ttl=86400.0)

    def is_locked_down(self, guild_id: int) -> bool:
        return self._active_lockdowns.contains(guild_id)

    async def lock_guild(
        self,
        guild: discord.Guild,
        reason: str,
        config: GuildSecurityConfig
    ) -> ActionResult:
        """Lock public channels for default role while leaving staff/protected channels functional."""
        bot = guild.me
        if not bot.guild_permissions.manage_channels:
            return ActionResult(
                success=False,
                action=SecurityActionType.LOCKDOWN,
                error="Bot lacks Manage Channels permission"
            )

        locked_channels: list[int] = []
        everyone = guild.default_role

        for ch in guild.text_channels:
            if ch.id in config.protected_channels or ch.id == config.security_log_channel_id:
                continue

            try:
                # Check current overwrite
                current_ow = ch.overwrites_for(everyone)
                if current_ow.send_messages is False:
                    continue  # Already locked

                current_ow.send_messages = False
                current_ow.send_messages_in_threads = False
                current_ow.create_public_threads = False
                current_ow.create_private_threads = False
                await ch.set_permissions(everyone, overwrite=current_ow, reason=f"Lexus Lockdown: {reason}")
                locked_channels.append(ch.id)
            except Exception as e:
                logger.warning(f"Could not lock channel {ch.name} in {guild.name}: {e}")

        self._active_lockdowns.set(guild.id, locked_channels)
        security_logger.event(
            incident_id="LOCKDOWN",
            guild_id=guild.id,
            actor_id=None,
            event_type="LOCKDOWN_ACTIVE",
            risk="CRITICAL",
            score=95.0,
            action="LOCKDOWN",
            result="SUCCESS",
            details=f"Locked {len(locked_channels)} public channels: {reason}"
        )

        return ActionResult(
            success=True,
            action=SecurityActionType.LOCKDOWN,
            reason=f"Lockdown activated across {len(locked_channels)} channels"
        )

    async def unlock_guild(
        self,
        guild: discord.Guild,
        config: GuildSecurityConfig
    ) -> ActionResult:
        """Restore normal channel permissions after lockdown is lifted."""
        bot = guild.me
        if not bot.guild_permissions.manage_channels:
            return ActionResult(
                success=False,
                action=SecurityActionType.LOCKDOWN,
                error="Bot lacks Manage Channels permission"
            )

        locked_channel_ids = self._active_lockdowns.get(guild.id) or []
        everyone = guild.default_role
        unlocked_count = 0

        channels_to_unlock = [
            guild.get_channel(cid) for cid in locked_channel_ids
        ] if locked_channel_ids else list(guild.text_channels)

        for ch in channels_to_unlock:
            if not ch or not isinstance(ch, discord.TextChannel):
                continue
            if ch.id in config.protected_channels or ch.id == config.security_log_channel_id:
                continue

            try:
                ow = ch.overwrites_for(everyone)
                # Reset send_messages to None (neutral/inherit)
                ow.send_messages = None
                ow.send_messages_in_threads = None
                ow.create_public_threads = None
                ow.create_private_threads = None
                await ch.set_permissions(everyone, overwrite=ow, reason="Lexus Security: Lockdown released")
                unlocked_count += 1
            except Exception:
                continue

        self._active_lockdowns.delete(guild.id)
        return ActionResult(
            success=True,
            action=SecurityActionType.LOCKDOWN,
            reason=f"Lockdown released across {unlocked_count} channels"
        )


# Global lockdown manager instance
lockdown_manager = LockdownManager()
