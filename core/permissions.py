"""
Permission utilities, hierarchy checks, and dangerous permission diff calculation.
Works with both discord.Permissions objects and integer bitfields for testing.
"""

from __future__ import annotations
from typing import NamedTuple, Optional, Any, Union
import discord


# Dangerous Discord permission flag names and their risk weights (0 to 100)
DANGEROUS_PERMISSIONS: dict[str, int] = {
    "administrator": 100,
    "manage_guild": 75,
    "manage_roles": 75,
    "manage_channels": 70,
    "manage_webhooks": 65,
    "ban_members": 60,
    "kick_members": 50,
    "moderate_members": 45,
    "manage_messages": 40,
    "manage_threads": 40,
    "mention_everyone": 35,
}


class PermissionDiffResult(NamedTuple):
    added_permissions: list[str]
    removed_permissions: list[str]
    added_dangerous: list[str]
    removed_dangerous: list[str]
    max_severity: int
    total_risk_score: float


def permissions_to_dict(perms: Union[discord.Permissions, int]) -> dict[str, bool]:
    """Convert discord.Permissions or bitfield integer to a flag dictionary."""
    if isinstance(perms, int):
        perms = discord.Permissions(perms)
    return dict(iter(perms))


def calculate_permission_diff(
    before: Union[discord.Permissions, int, dict[str, bool]],
    after: Union[discord.Permissions, int, dict[str, bool]]
) -> PermissionDiffResult:
    """
    Calculate differences between two permission sets.
    Identifies added dangerous permissions and calculates weighted risk score.
    """
    before_dict = before if isinstance(before, dict) else permissions_to_dict(before)
    after_dict = after if isinstance(after, dict) else permissions_to_dict(after)

    added: list[str] = []
    removed: list[str] = []
    added_dangerous: list[str] = []
    removed_dangerous: list[str] = []

    all_keys = set(before_dict.keys()).union(after_dict.keys())
    for key in all_keys:
        b_val = before_dict.get(key, False)
        a_val = after_dict.get(key, False)

        if not b_val and a_val:
            added.append(key)
            if key in DANGEROUS_PERMISSIONS:
                added_dangerous.append(key)
        elif b_val and not a_val:
            removed.append(key)
            if key in DANGEROUS_PERMISSIONS:
                removed_dangerous.append(key)

    max_severity = 0
    total_risk = 0.0

    for perm in added_dangerous:
        weight = DANGEROUS_PERMISSIONS.get(perm, 20)
        if weight > max_severity:
            max_severity = weight
        total_risk += weight

    return PermissionDiffResult(
        added_permissions=added,
        removed_permissions=removed,
        added_dangerous=added_dangerous,
        removed_dangerous=removed_dangerous,
        max_severity=max_severity,
        total_risk_score=min(total_risk, 100.0)
    )


def can_bot_act_on_member(
    bot_member: discord.Member,
    target_member: discord.Member,
    required_permission: Optional[str] = None
) -> tuple[bool, str]:
    """
    Check if the bot can act on a target member according to Discord role hierarchy.
    Returns (can_act, reason).
    """
    if target_member.id == bot_member.id:
        return False, "Cannot target self."

    if target_member.guild.owner_id == target_member.id:
        return False, "Cannot target guild owner (Discord platform restriction)."

    if bot_member.guild.owner_id == bot_member.id:
        return True, "Bot is guild owner."

    if target_member.top_role.position >= bot_member.top_role.position:
        return False, (
            f"Target's highest role ({target_member.top_role.name}: pos {target_member.top_role.position}) "
            f"is higher or equal to bot's highest role ({bot_member.top_role.name}: pos {bot_member.top_role.position})."
        )

    if required_permission:
        perms = bot_member.guild_permissions
        if not getattr(perms, required_permission, False):
            return False, f"Bot is missing required permission: {required_permission}."

    return True, "Action allowed by hierarchy and permissions."


def can_bot_manage_role(
    bot_member: discord.Member,
    target_role: discord.Role
) -> tuple[bool, str]:
    """
    Check if the bot can manage or assign/remove a specific role.
    Returns (can_manage, reason).
    """
    if target_role.is_default():
        return False, "Cannot directly edit default @everyone role assignment."

    if target_role.managed:
        return False, "Role is managed by an integration/bot."

    if bot_member.guild.owner_id == bot_member.id:
        return True, "Bot is guild owner."

    if not bot_member.guild_permissions.manage_roles:
        return False, "Bot lacks Manage Roles permission."

    if target_role.position >= bot_member.top_role.position:
        return False, (
            f"Role ({target_role.name}: pos {target_role.position}) is higher or equal to "
            f"bot's highest role ({bot_member.top_role.name}: pos {bot_member.top_role.position})."
        )

    return True, "Role manageable by bot."
