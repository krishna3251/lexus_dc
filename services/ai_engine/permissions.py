"""Central preflight permission checks for Lexus AI tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import discord

from .tools import ToolContext, ToolSpec


@dataclass(slots=True)
class PermissionDecision:
    allowed: bool
    reason: str


class AIPermissionGuard:
    """Performs request-level authorization before tool-specific checks."""

    @staticmethod
    def check(spec: ToolSpec, context: ToolContext, allow_mutations: bool) -> PermissionDecision:
        if not spec.mutating:
            required = spec.required_permission
            if required:
                if not isinstance(context.user, discord.Member):
                    return PermissionDecision(False, "This tool requires a server-member context.")
                if not getattr(context.user.guild_permissions, required, False):
                    return PermissionDecision(
                        False,
                        f"Requester lacks required permission: {required}.",
                    )
            return PermissionDecision(True, "read-only tool")

        if not allow_mutations:
            return PermissionDecision(False, "Current AI execution plan is read-only.")

        guild = context.guild
        user = context.user
        if guild is None or not isinstance(user, discord.Member):
            return PermissionDecision(False, "Mutating tools require a server-member context.")

        if spec.required_permission and not getattr(user.guild_permissions, spec.required_permission, False):
            return PermissionDecision(
                False,
                f"Requester lacks required permission: {spec.required_permission}.",
            )

        if guild.owner_id == user.id or user.guild_permissions.administrator:
            return PermissionDecision(True, "administrator/owner authorized")

        return PermissionDecision(True, "granular Discord permission authorized")
