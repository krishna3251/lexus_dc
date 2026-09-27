"""Guarded tool registry and Discord tools for Lexus AI Engine.

The model can request a tool, but the application is the authority:
permission checks, role hierarchy, protected assets, and input validation all
happen before a mutating Discord API call is made.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import discord

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolContext:
    bot: discord.Client
    guild: Optional[discord.Guild]
    channel: Optional[discord.abc.GuildChannel]
    user: discord.Member | discord.User


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[ToolContext, dict[str, Any]], Awaitable[Any]]
    required_permission: Optional[str] = None
    mutating: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Duplicate AI tool: {spec.name}")
        self._tools[spec.name] = spec

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    def names(self) -> list[str]:
        return list(self._tools)

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        spec = self._tools.get(name)
        if spec is None:
            return {"success": False, "error": f"Unknown tool: {name}"}

        if not isinstance(arguments, dict):
            return {"success": False, "error": "Tool arguments must be an object"}

        missing = [
            item
            for item in spec.parameters.get("required", [])
            if item not in arguments
        ]
        if missing:
            return {
                "success": False,
                "error": f"Missing required arguments: {', '.join(missing)}",
            }

        if spec.mutating:
            authorized, reason = await self._authorize_mutation(spec, context, arguments)
            if not authorized:
                return {"success": False, "error": reason}

        try:
            output = await spec.handler(context, arguments)
            return {"success": True, "result": output}
        except discord.Forbidden:
            return {"success": False, "error": "Discord rejected the action (permissions or hierarchy)."}
        except discord.NotFound:
            return {"success": False, "error": "The requested Discord object no longer exists."}
        except discord.HTTPException as exc:
            return {"success": False, "error": f"Discord API error: {exc.status}."}
        except Exception:
            logger.exception("AI tool %s failed", name)
            return {"success": False, "error": "Internal tool failure."}

    async def _authorize_mutation(
        self,
        spec: ToolSpec,
        context: ToolContext,
        arguments: dict[str, Any],
    ) -> tuple[bool, str]:
        guild = context.guild
        user = context.user

        if guild is None or not isinstance(user, discord.Member):
            return False, "Mutating tools require a guild member context."

        required = spec.required_permission
        if required and not getattr(user.guild_permissions, required, False):
            return False, f"User lacks required permission: {required}."

        # Targeted actions must never outrank the human requester.
        target_id = _optional_int(arguments.get("member_id"))
        if target_id:
            member = guild.get_member(target_id)
            if member is None:
                try:
                    member = await guild.fetch_member(target_id)
                except (discord.NotFound, discord.HTTPException):
                    member = None

            if member is None:
                return False, "Target member was not found."
            if member.id == guild.owner_id:
                return False, "The server owner is protected from AI moderation actions."
            if member.id == getattr(context.bot.user, "id", None):
                return False, "The bot cannot moderate itself."
            if not user.guild_permissions.administrator and member.top_role >= user.top_role:
                return False, "Target is at or above the requester's highest role."

            bot_member = guild.me
            if bot_member is None:
                return False, "Bot member context is unavailable."
            if member.top_role >= bot_member.top_role and member.id != guild.owner_id:
                return False, "Target is at or above the bot's highest role."

        channel_id = _optional_int(arguments.get("channel_id"))
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel is None:
                return False, "Target channel was not found."

            # AI must not alter protected security channels.
            try:
                from security.engine import security_engine

                cfg = await security_engine.get_guild_config(guild.id)
                protected = set(cfg.protected_channels)
                if cfg.security_log_channel_id:
                    protected.add(cfg.security_log_channel_id)
                if channel.id in protected:
                    return False, "Protected security channel cannot be modified by AI tools."
            except Exception:
                logger.warning("Security policy lookup failed during AI mutation authorization.")

        return True, "authorized"


def _optional_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_member(guild: discord.Guild, query: str) -> Optional[discord.Member]:
    query = query.strip()
    mention = re.fullmatch(r"<@!?(d+)>", query)
    if mention:
        query = mention.group(1)

    member_id = _optional_int(query)
    if member_id:
        return guild.get_member(member_id)

    lowered = query.casefold()
    for member in guild.members:
        if (
            member.name.casefold() == lowered
            or member.display_name.casefold() == lowered
            or str(member).casefold() == lowered
        ):
            return member
    return None


def _require_guild(context: ToolContext) -> discord.Guild:
    if context.guild is None:
        raise ValueError("This tool requires a server context.")
    return context.guild


def _safe_member(member: discord.Member) -> dict[str, Any]:
    return {
        "id": member.id,
        "name": member.name,
        "display_name": member.display_name,
        "bot": member.bot,
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        "created_at": member.created_at.isoformat(),
        "top_role": member.top_role.name,
        "top_role_position": member.top_role.position,
        "administrator": member.guild_permissions.administrator,
        "manage_guild": member.guild_permissions.manage_guild,
        "moderate_members": member.guild_permissions.moderate_members,
        "kick_members": member.guild_permissions.kick_members,
        "ban_members": member.guild_permissions.ban_members,
    }


def register_discord_tools(registry: ToolRegistry) -> None:
    """Register the initial read-only and narrowly scoped mutation tools."""

    registry.register(
        ToolSpec(
            name="get_server_overview",
            description="Inspect basic information about the current Discord server.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=_get_server_overview,
        )
    )

    registry.register(
        ToolSpec(
            name="get_member",
            description="Look up one server member by Discord ID, mention, username, or display name.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_get_member,
        )
    )

    registry.register(
        ToolSpec(
            name="list_channels",
            description="List server text, announcement, voice, stage, and forum channels.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "additionalProperties": False,
            },
            handler=_list_channels,
        )
    )

    registry.register(
        ToolSpec(
            name="list_roles",
            description="List server roles and their hierarchy positions.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "additionalProperties": False,
            },
            handler=_list_roles,
        )
    )

    registry.register(
        ToolSpec(
            name="get_bot_status",
            description="Check Lexus bot latency, guild count, and uptime.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=_get_bot_status,
        )
    )

    registry.register(
        ToolSpec(
            name="get_security_status",
            description="Inspect Lexus V3 security state, heat telemetry, mode, and protection switches.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=_get_security_status,
        )
    )

    registry.register(
        ToolSpec(
            name="get_recent_security_incidents",
            description="Read recent Lexus security incidents for the current server.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "additionalProperties": False,
            },
            handler=_get_recent_security_incidents,
        )
    )

    registry.register(
        ToolSpec(
            name="get_recent_audit_logs",
            description="Inspect recent Discord audit log entries. This requires View Audit Log.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "additionalProperties": False,
            },
            handler=_get_recent_audit_logs,
            required_permission="view_audit_log",
        )
    )

    registry.register(
        ToolSpec(
            name="timeout_member",
            description="Timeout one member for a bounded duration. Requires Moderate Members.",
            parameters={
                "type": "object",
                "properties": {
                    "member_id": {"type": "integer"},
                    "minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
                    "reason": {"type": "string", "maxLength": 300},
                },
                "required": ["member_id", "minutes", "reason"],
                "additionalProperties": False,
            },
            handler=_timeout_member,
            required_permission="moderate_members",
            mutating=True,
        )
    )

    registry.register(
        ToolSpec(
            name="kick_member",
            description="Kick one member from the server. Requires Kick Members.",
            parameters={
                "type": "object",
                "properties": {
                    "member_id": {"type": "integer"},
                    "reason": {"type": "string", "maxLength": 300},
                },
                "required": ["member_id", "reason"],
                "additionalProperties": False,
            },
            handler=_kick_member,
            required_permission="kick_members",
            mutating=True,
        )
    )

    registry.register(
        ToolSpec(
            name="ban_member",
            description="Ban one member from the server. Requires Ban Members.",
            parameters={
                "type": "object",
                "properties": {
                    "member_id": {"type": "integer"},
                    "reason": {"type": "string", "maxLength": 300},
                },
                "required": ["member_id", "reason"],
                "additionalProperties": False,
            },
            handler=_ban_member,
            required_permission="ban_members",
            mutating=True,
        )
    )

    registry.register(
        ToolSpec(
            name="lock_channel",
            description="Lock one non-protected text channel by denying @everyone Send Messages. Requires Manage Channels.",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "integer"},
                    "reason": {"type": "string", "maxLength": 300},
                },
                "required": ["channel_id", "reason"],
                "additionalProperties": False,
            },
            handler=_lock_channel,
            required_permission="manage_channels",
            mutating=True,
        )
    )


async def _get_server_overview(
    context: ToolContext,
    _: dict[str, Any],
) -> dict[str, Any]:
    guild = _require_guild(context)
    return {
        "id": guild.id,
        "name": guild.name,
        "owner_id": guild.owner_id,
        "member_count": guild.member_count,
        "channel_count": len(guild.channels),
        "role_count": len(guild.roles),
        "text_channels": len(guild.text_channels),
        "voice_channels": len(guild.voice_channels),
        "created_at": guild.created_at.isoformat(),
    }


async def _get_member(
    context: ToolContext,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    guild = _require_guild(context)
    query = str(arguments["query"])
    member = _resolve_member(guild, query)
    if member is None:
        try:
            member = await guild.fetch_member(int(query))
        except (ValueError, discord.NotFound, discord.HTTPException):
            member = None

    if member is None:
        return {"found": False, "query": query}
    return {"found": True, "member": _safe_member(member)}


async def _list_channels(
    context: ToolContext,
    arguments: dict[str, Any],
) -> list[dict[str, Any]]:
    guild = _require_guild(context)
    limit = max(1, min(int(arguments.get("limit", 50)), 50))
    items = []
    for channel in sorted(guild.channels, key=lambda item: getattr(item, "position", 0))[:limit]:
        items.append(
            {
                "id": channel.id,
                "name": channel.name,
                "type": str(channel.type),
                "position": getattr(channel, "position", 0),
                "category_id": getattr(channel, "category_id", None),
            }
        )
    return items


async def _list_roles(
    context: ToolContext,
    arguments: dict[str, Any],
) -> list[dict[str, Any]]:
    guild = _require_guild(context)
    limit = max(1, min(int(arguments.get("limit", 50)), 50))
    return [
        {
            "id": role.id,
            "name": role.name,
            "position": role.position,
            "managed": role.managed,
            "mentionable": role.mentionable,
            "administrator": role.permissions.administrator,
            "manage_guild": role.permissions.manage_guild,
            "manage_roles": role.permissions.manage_roles,
        }
        for role in sorted(guild.roles, key=lambda item: item.position, reverse=True)[:limit]
    ]


async def _get_bot_status(
    context: ToolContext,
    _: dict[str, Any],
) -> dict[str, Any]:
    bot = context.bot
    start_time = getattr(bot, "start_time", None)
    uptime_seconds = None
    if isinstance(start_time, (int, float)):
        uptime_seconds = max(0.0, __import__("time").time() - start_time)

    return {
        "latency_ms": round(bot.latency * 1000, 1) if bot.latency is not None else None,
        "guild_count": len(getattr(bot, "guilds", [])),
        "user_cache_count": len(getattr(bot, "users", [])),
        "uptime_seconds": round(uptime_seconds, 1) if uptime_seconds is not None else None,
        "ready": bool(getattr(bot, "is_ready", lambda: False)()),
    }


async def _get_security_status(
    context: ToolContext,
    _: dict[str, Any],
) -> dict[str, Any]:
    guild = _require_guild(context)
    try:
        from security.engine import security_engine

        cfg = await security_engine.get_guild_config(guild.id)
        sm = security_engine.get_state_machine(guild.id)
        hm = security_engine.get_heat_manager(guild.id)
        health = security_engine.get_health_status()
        return {
            "state": sm.current_state.value,
            "mode": cfg.security_mode,
            "profile": cfg.profile.value,
            "security_enabled": cfg.security_enabled,
            "spam_enabled": cfg.spam_enabled,
            "raid_enabled": cfg.raid_enabled,
            "antinuke_enabled": cfg.antinuke_enabled,
            "join_gate_enabled": cfg.join_gate_enabled,
            "quarantine_configured": bool(cfg.quarantine_role_id),
            "lockdown_enabled": cfg.lockdown_enabled,
            "guild_heat": round(hm.guild_heat.get_heat(), 2),
            "raid_heat": round(hm.raid_heat.get_heat(), 2),
            "structural_heat": round(hm.structural_heat.get_heat(), 2),
            "events_processed": health.get("events_processed", 0),
            "actions_executed": health.get("actions_executed", 0),
        }
    except Exception as exc:
        return {"available": False, "error": f"Security status unavailable: {type(exc).__name__}"}


async def _get_recent_security_incidents(
    context: ToolContext,
    arguments: dict[str, Any],
) -> list[dict[str, Any]]:
    guild = _require_guild(context)
    from services.database import security_db

    limit = max(1, min(int(arguments.get("limit", 5)), 10))
    incidents = await security_db.get_recent_incidents(guild.id, limit=limit)
    return [
        {
            "incident_id": item.get("incident_id"),
            "state": item.get("state"),
            "severity": item.get("severity"),
            "primary_actor": item.get("primary_actor"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        for item in incidents
    ]


async def _get_recent_audit_logs(
    context: ToolContext,
    arguments: dict[str, Any],
) -> list[dict[str, Any]]:
    guild = _require_guild(context)
    limit = max(1, min(int(arguments.get("limit", 10)), 10))
    items: list[dict[str, Any]] = []

    async for entry in guild.audit_logs(limit=limit):
        target = getattr(entry.target, "id", None)
        actor = getattr(entry.user, "id", None)
        items.append(
            {
                "id": entry.id,
                "action": str(entry.action),
                "actor_id": actor,
                "target_id": target,
                "created_at": entry.created_at.isoformat(),
                "reason": entry.reason,
            }
        )
    return items


async def _timeout_member(
    context: ToolContext,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    guild = _require_guild(context)
    member = guild.get_member(int(arguments["member_id"]))
    if member is None:
        raise ValueError("Member not found.")

    minutes = max(1, min(int(arguments["minutes"]), 1440))
    reason = str(arguments["reason"]).strip()[:300]
    await member.timeout(
        datetime.timedelta(minutes=minutes),
        reason=f"Lexus AI: {reason}",
    )
    _audit_ai_action(guild, context.user, "timeout_member", member.id, reason)
    return {"member_id": member.id, "minutes": minutes, "action": "timeout"}


async def _kick_member(
    context: ToolContext,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    guild = _require_guild(context)
    member = guild.get_member(int(arguments["member_id"]))
    if member is None:
        raise ValueError("Member not found.")

    reason = str(arguments["reason"]).strip()[:300]
    await member.kick(reason=f"Lexus AI: {reason}")
    _audit_ai_action(guild, context.user, "kick_member", member.id, reason)
    return {"member_id": member.id, "action": "kick"}


async def _ban_member(
    context: ToolContext,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    guild = _require_guild(context)
    member = guild.get_member(int(arguments["member_id"]))
    if member is None:
        raise ValueError("Member not found.")

    reason = str(arguments["reason"]).strip()[:300]
    await guild.ban(
        member,
        reason=f"Lexus AI: {reason}",
        delete_message_seconds=86400,
    )
    _audit_ai_action(guild, context.user, "ban_member", member.id, reason)
    return {"member_id": member.id, "action": "ban"}


async def _lock_channel(
    context: ToolContext,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    guild = _require_guild(context)
    channel_id = int(arguments["channel_id"])
    channel = guild.get_channel(channel_id)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise ValueError("Only text channels can be locked by this tool.")

    reason = str(arguments["reason"]).strip()[:300]
    overwrite = channel.overwrites_for(guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(
        guild.default_role,
        overwrite=overwrite,
        reason=f"Lexus AI: {reason}",
    )
    _audit_ai_action(guild, context.user, "lock_channel", channel.id, reason)
    return {"channel_id": channel.id, "action": "lock_channel"}


def _audit_ai_action(
    guild: discord.Guild,
    user: discord.Member | discord.User,
    action: str,
    target_id: int,
    reason: str,
) -> None:
    try:
        from core.logging import security_logger

        security_logger.event(
            incident_id=f"AI-{guild.id}",
            guild_id=guild.id,
            actor_id=getattr(user, "id", None),
            event_type="AI_TOOL_ACTION",
            risk="MANUAL",
            score=0.0,
            action=action,
            result="SUCCESS",
            details=f"target={target_id}; reason={reason}",
        )
    except Exception:
        logger.exception("Failed to write AI action security log")
