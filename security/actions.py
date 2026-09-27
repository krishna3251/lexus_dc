"""
Action execution engine for Lexus Security Engine.
Dispatches Discord mutations with rate limiting, circuit breaker protection,
strict idempotency, and professional alert formatting.
"""

from __future__ import annotations
import time
import datetime
import logging
from typing import Optional, Any
import discord
from security.models import (
    SecurityActionType,
    ActionResult,
    GuildSecurityConfig
)
from security.event_tracker import TokenBucket
from core.permissions import can_bot_act_on_member, can_bot_manage_role
from core.logging import security_logger
from services.cache import TTLCache

logger = logging.getLogger(__name__)


class ActionEngine:
    """
    Executes automated responses with rate limiting, idempotency checks,
    and role hierarchy verification.
    """

    def __init__(self):
        # Action budget per guild: guild_id -> TokenBucket
        self._action_budgets: TTLCache[int, TokenBucket] = TTLCache(max_size=1000, default_ttl=3600.0)
        # Idempotency caches to prevent repeating mutations
        # (guild_id, "quarantine", user_id) -> timestamp
        self._idempotency_cache: TTLCache[tuple, float] = TTLCache(max_size=5000, default_ttl=60.0)

    def _get_action_budget(self, guild_id: int, limit: int = 10, window: float = 10.0) -> TokenBucket:
        bucket = self._action_budgets.get(guild_id)
        if bucket is None:
            refill_rate = float(limit) / max(1.0, float(window))
            bucket = TokenBucket(capacity=float(limit), refill_rate=refill_rate)
            self._action_budgets.set(guild_id, bucket)
        return bucket

    async def execute(
        self,
        action: SecurityActionType,
        guild: discord.Guild,
        target_id: Optional[int],
        reason: str,
        config: GuildSecurityConfig,
        bot_member: Optional[discord.Member] = None,
        is_simulated: bool = False,
        extra_data: Optional[dict[str, Any]] = None
    ) -> ActionResult:
        """Execute a security action with circuit breaker and permission checks."""
        now = time.time()

        # Handle simulation (audit mode)
        if is_simulated or config.security_mode == "audit":
            if action not in (SecurityActionType.LOG, SecurityActionType.ALERT):
                security_logger.event(
                    incident_id="AUDIT_SIM",
                    guild_id=guild.id,
                    actor_id=target_id,
                    event_type="ACTION_SIMULATED",
                    risk="SIMULATED",
                    score=0.0,
                    action=action.value,
                    result="SIMULATED",
                    details=f"Audit mode prevented real mutation: {reason}"
                )
                return ActionResult(
                    success=True,
                    action=action,
                    target_id=target_id,
                    target_type="member",
                    reason=f"[SIMULATED in audit mode] {reason}",
                    timestamp=now
                )

        # Check circuit breaker / action budget for mutations
        if action in (
            SecurityActionType.TIMEOUT,
            SecurityActionType.QUARANTINE,
            SecurityActionType.KICK,
            SecurityActionType.BAN,
            SecurityActionType.LOCK_CHANNEL,
            SecurityActionType.LOCKDOWN
        ):
            budget = self._get_action_budget(guild.id, config.action_budget_limit, config.action_budget_window)
            if not budget.consume(1.0):
                msg = "Security action budget exhausted (circuit breaker activated to prevent API storm)."
                security_logger.action_failure(guild.id, action.value, target_id, msg)
                return ActionResult(
                    success=False,
                    action=action,
                    target_id=target_id,
                    reason=reason,
                    error=msg,
                    timestamp=now
                )

        # Dispatch action
        try:
            if action == SecurityActionType.LOG:
                return ActionResult(success=True, action=action, target_id=target_id, reason=reason, timestamp=now)

            elif action == SecurityActionType.ALERT:
                return await self._execute_alert(guild, config, reason, extra_data)

            elif action == SecurityActionType.TIMEOUT:
                return await self._execute_timeout(guild, target_id, reason, bot_member)

            elif action == SecurityActionType.QUARANTINE:
                return await self._execute_quarantine(guild, target_id, reason, config, bot_member)

            elif action == SecurityActionType.KICK:
                return await self._execute_kick(guild, target_id, reason, bot_member)

            elif action == SecurityActionType.BAN:
                return await self._execute_ban(guild, target_id, reason, bot_member)

            elif action == SecurityActionType.LOCK_CHANNEL:
                channel_id = extra_data.get("channel_id") if extra_data else None
                return await self._execute_lock_channel(guild, channel_id or target_id, reason, bot_member)

            elif action == SecurityActionType.LOCKDOWN:
                return await self._execute_lockdown(guild, reason, config, bot_member)

            else:
                return ActionResult(
                    success=True,
                    action=action,
                    target_id=target_id,
                    reason=reason,
                    timestamp=now
                )

        except Exception as e:
            security_logger.action_failure(guild.id, action.value, target_id, str(e), e)
            return ActionResult(
                success=False,
                action=action,
                target_id=target_id,
                reason=reason,
                error=f"{type(e).__name__}: {e}",
                timestamp=now
            )

    async def _execute_alert(
        self,
        guild: discord.Guild,
        config: GuildSecurityConfig,
        reason: str,
        extra_data: Optional[dict[str, Any]]
    ) -> ActionResult:
        """Send a professional security alert embed to configured log channel."""
        log_channel_id = config.security_log_channel_id
        if not log_channel_id:
            return ActionResult(success=True, action=SecurityActionType.ALERT, reason="No log channel configured")

        channel = guild.get_channel(log_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return ActionResult(success=False, action=SecurityActionType.ALERT, error="Log channel not found")

        embed = discord.Embed(
            title="Lexus Security",
            description="Security incident detected.",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        if extra_data:
            incident_id = extra_data.get("incident_id", "N/A")
            actor_mention = f"<@{extra_data['actor_id']}>" if extra_data.get("actor_id") else "Unknown"
            embed.add_field(name="Incident", value=incident_id, inline=True)
            embed.add_field(name="Actor", value=actor_mention, inline=True)
            embed.add_field(name="Risk", value=extra_data.get("risk", "High"), inline=True)
            if "event_type" in extra_data:
                embed.add_field(name="Type", value=extra_data["event_type"], inline=True)

        embed.add_field(name="Action / Reason", value=reason, inline=False)
        embed.set_footer(text="Lexus Defense System")

        try:
            await channel.send(embed=embed)
            return ActionResult(success=True, action=SecurityActionType.ALERT, target_id=log_channel_id, reason=reason)
        except Exception as e:
            return ActionResult(success=False, action=SecurityActionType.ALERT, error=str(e))

    async def _execute_timeout(
        self,
        guild: discord.Guild,
        target_id: Optional[int],
        reason: str,
        bot_member: Optional[discord.Member]
    ) -> ActionResult:
        if not target_id:
            return ActionResult(success=False, action=SecurityActionType.TIMEOUT, error="No target_id provided")

        # Idempotency check
        key = (guild.id, "timeout", target_id)
        if self._idempotency_cache.contains(key):
            return ActionResult(
                success=True,
                action=SecurityActionType.TIMEOUT,
                target_id=target_id,
                reason="Target already recently timed out",
                idempotent_skip=True
            )

        member = guild.get_member(target_id)
        if not member:
            return ActionResult(success=False, action=SecurityActionType.TIMEOUT, error="Member not found in guild")

        bot = bot_member or guild.me
        can_act, check_reason = can_bot_act_on_member(bot, member, "moderate_members")
        if not can_act:
            security_logger.hierarchy_failure(guild.id, "TIMEOUT", target_id, check_reason)
            return ActionResult(success=False, action=SecurityActionType.TIMEOUT, target_id=target_id, error=check_reason)

        try:
            duration = datetime.timedelta(minutes=15)
            await member.timeout(duration, reason=f"Lexus Security: {reason}")
            self._idempotency_cache.set(key, time.time())
            return ActionResult(success=True, action=SecurityActionType.TIMEOUT, target_id=target_id, reason=reason)
        except discord.Forbidden as e:
            security_logger.permission_failure(guild.id, "TIMEOUT", target_id, str(e))
            return ActionResult(success=False, action=SecurityActionType.TIMEOUT, target_id=target_id, error=str(e))

    async def _execute_quarantine(
        self,
        guild: discord.Guild,
        target_id: Optional[int],
        reason: str,
        config: GuildSecurityConfig,
        bot_member: Optional[discord.Member]
    ) -> ActionResult:
        if not target_id:
            return ActionResult(success=False, action=SecurityActionType.QUARANTINE, error="No target_id provided")

        key = (guild.id, "quarantine", target_id)
        if self._idempotency_cache.contains(key):
            return ActionResult(
                success=True,
                action=SecurityActionType.QUARANTINE,
                target_id=target_id,
                reason="Member already quarantined",
                idempotent_skip=True
            )

        member = guild.get_member(target_id)
        if not member:
            return ActionResult(success=False, action=SecurityActionType.QUARANTINE, error="Member not in guild")

        bot = bot_member or guild.me
        can_act, check_reason = can_bot_act_on_member(bot, member, "manage_roles")
        if not can_act:
            security_logger.hierarchy_failure(guild.id, "QUARANTINE", target_id, check_reason)
            return ActionResult(success=False, action=SecurityActionType.QUARANTINE, target_id=target_id, error=check_reason)

        # Fetch quarantine role
        role_id = config.quarantine_role_id
        role = guild.get_role(role_id) if role_id else None
        if not role:
            # Fallback to timeout if no quarantine role configured
            return await self._execute_timeout(guild, target_id, f"Quarantine role missing; applying timeout: {reason}", bot)

        can_manage, manage_reason = can_bot_manage_role(bot, role)
        if not can_manage:
            security_logger.hierarchy_failure(guild.id, "QUARANTINE", role_id, manage_reason)
            return ActionResult(success=False, action=SecurityActionType.QUARANTINE, target_id=target_id, error=manage_reason)

        try:
            await member.add_roles(role, reason=f"Lexus Security Quarantine: {reason}")
            self._idempotency_cache.set(key, time.time())
            return ActionResult(success=True, action=SecurityActionType.QUARANTINE, target_id=target_id, reason=reason)
        except Exception as e:
            return ActionResult(success=False, action=SecurityActionType.QUARANTINE, target_id=target_id, error=str(e))

    async def _execute_kick(
        self,
        guild: discord.Guild,
        target_id: Optional[int],
        reason: str,
        bot_member: Optional[discord.Member]
    ) -> ActionResult:
        if not target_id:
            return ActionResult(success=False, action=SecurityActionType.KICK, error="No target_id")

        member = guild.get_member(target_id)
        if not member:
            return ActionResult(success=False, action=SecurityActionType.KICK, error="Member not found")

        bot = bot_member or guild.me
        can_act, check_reason = can_bot_act_on_member(bot, member, "kick_members")
        if not can_act:
            return ActionResult(success=False, action=SecurityActionType.KICK, target_id=target_id, error=check_reason)

        try:
            await member.kick(reason=f"Lexus Security: {reason}")
            return ActionResult(success=True, action=SecurityActionType.KICK, target_id=target_id, reason=reason)
        except Exception as e:
            return ActionResult(success=False, action=SecurityActionType.KICK, target_id=target_id, error=str(e))

    async def _execute_ban(
        self,
        guild: discord.Guild,
        target_id: Optional[int],
        reason: str,
        bot_member: Optional[discord.Member]
    ) -> ActionResult:
        if not target_id:
            return ActionResult(success=False, action=SecurityActionType.BAN, error="No target_id")

        member = guild.get_member(target_id)
        bot = bot_member or guild.me

        if member:
            can_act, check_reason = can_bot_act_on_member(bot, member, "ban_members")
            if not can_act:
                return ActionResult(success=False, action=SecurityActionType.BAN, target_id=target_id, error=check_reason)

        try:
            await guild.ban(discord.Object(id=target_id), reason=f"Lexus Security: {reason}", delete_message_days=1)
            return ActionResult(success=True, action=SecurityActionType.BAN, target_id=target_id, reason=reason)
        except Exception as e:
            return ActionResult(success=False, action=SecurityActionType.BAN, target_id=target_id, error=str(e))

    async def _execute_lock_channel(
        self,
        guild: discord.Guild,
        channel_id: Optional[int],
        reason: str,
        bot_member: Optional[discord.Member]
    ) -> ActionResult:
        if not channel_id:
            return ActionResult(success=False, action=SecurityActionType.LOCK_CHANNEL, error="No channel_id")

        channel = guild.get_channel(channel_id)
        if not channel or not hasattr(channel, "set_permissions"):
            return ActionResult(success=False, action=SecurityActionType.LOCK_CHANNEL, error="Invalid channel")

        bot = bot_member or guild.me
        if not bot.guild_permissions.manage_channels:
            return ActionResult(success=False, action=SecurityActionType.LOCK_CHANNEL, error="Missing Manage Channels")

        try:
            everyone = guild.default_role
            await channel.set_permissions(everyone, send_messages=False, reason=f"Lexus Security Lock: {reason}")
            return ActionResult(success=True, action=SecurityActionType.LOCK_CHANNEL, target_id=channel_id, reason=reason)
        except Exception as e:
            return ActionResult(success=False, action=SecurityActionType.LOCK_CHANNEL, target_id=channel_id, error=str(e))

    async def _execute_lockdown(
        self,
        guild: discord.Guild,
        reason: str,
        config: GuildSecurityConfig,
        bot_member: Optional[discord.Member]
    ) -> ActionResult:
        """Emergency lockdown: locks default send permissions on public text channels."""
        bot = bot_member or guild.me
        if not bot.guild_permissions.manage_channels:
            return ActionResult(success=False, action=SecurityActionType.LOCKDOWN, error="Missing Manage Channels")

        locked_count = 0
        everyone = guild.default_role
        for ch in guild.text_channels:
            # Skip protected or log channels
            if ch.id in config.protected_channels or ch.id == config.security_log_channel_id:
                continue
            try:
                await ch.set_permissions(everyone, send_messages=False, reason=f"Lexus Lockdown: {reason}")
                locked_count += 1
            except Exception:
                continue

        return ActionResult(
            success=True,
            action=SecurityActionType.LOCKDOWN,
            reason=f"Lockdown enabled on {locked_count} channels: {reason}"
        )


# Global action engine instance
action_engine = ActionEngine()
