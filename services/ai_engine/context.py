"""Minimal, safe context assembly for the Lexus AI Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import discord

from .models import AIRequest, RouteDecision


@dataclass(slots=True)
class AIContext:
    user_id: int
    guild_id: Optional[int]
    channel_id: Optional[int]
    intent: str
    route_confidence: float
    guild_name: Optional[str]
    member_count: Optional[int]
    channel_name: Optional[str]
    user_permission_summary: tuple[str, ...]
    bot_ready: bool

    def as_prompt_fragment(self) -> str:
        lines = [
            "CURRENT APPLICATION CONTEXT:",
            f"- Intent: {self.intent}",
            f"- Route confidence: {self.route_confidence:.2f}",
            f"- Guild: {self.guild_name or 'DM / unavailable'}",
            f"- Channel: {self.channel_name or 'unavailable'}",
            f"- Guild member count: {self.member_count if self.member_count is not None else 'unknown'}",
            f"- Requester permissions: {', '.join(self.user_permission_summary) or 'standard member'}",
            f"- Bot ready: {'yes' if self.bot_ready else 'no'}",
        ]
        return "\n".join(lines)


class ContextBuilder:
    """Builds only stable application facts.

    Sensitive or large Discord state is fetched through tools on demand rather
    than copied into every prompt.
    """

    @staticmethod
    def build(
        request: AIRequest,
        route: RouteDecision,
        context: "ToolContext",
    ) -> AIContext:
        guild = context.guild
        user = context.user

        permission_names: list[str] = []
        if isinstance(user, discord.Member):
            permissions = user.guild_permissions
            for name in (
                "administrator",
                "manage_guild",
                "manage_channels",
                "manage_roles",
                "manage_messages",
                "moderate_members",
                "kick_members",
                "ban_members",
                "view_audit_log",
            ):
                if getattr(permissions, name, False):
                    permission_names.append(name)

        return AIContext(
            user_id=request.user_id,
            guild_id=request.guild_id,
            channel_id=request.channel_id,
            intent=route.intent.value,
            route_confidence=route.confidence,
            guild_name=guild.name if guild else None,
            member_count=guild.member_count if guild else None,
            channel_name=getattr(context.channel, "name", None),
            user_permission_summary=tuple(permission_names),
            bot_ready=bool(getattr(context.bot, "is_ready", lambda: False)()),
        )


# Imported only for type checking / runtime annotation resolution.
from .tools import ToolContext
