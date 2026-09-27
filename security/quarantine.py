"""
Quarantine manager for Lexus Security Engine.
Provides isolated containment of compromised or suspicious actors, saves previous roles
for seamless release, and implements quarantine hold protection against unauthorized tampering.
"""

from __future__ import annotations
import time
import logging
from typing import Optional, Any
import discord
from security.models import ActionResult, SecurityActionType, GuildSecurityConfig
from core.permissions import can_bot_act_on_member, can_bot_manage_role
from core.logging import security_logger
from services.database import security_db

logger = logging.getLogger(__name__)


class QuarantineManager:
    """Manages member quarantine states, role stripping, and role restoration."""

    async def setup_quarantine_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Ensure a dedicated, isolated Quarantine role exists in the guild."""
        bot = guild.me
        if not bot.guild_permissions.manage_roles:
            return None

        # Look for existing role
        for r in guild.roles:
            if r.name.lower() == "lexus-quarantine":
                return r

        # Create isolated quarantine role
        try:
            role = await guild.create_role(
                name="lexus-quarantine",
                color=discord.Color.dark_grey(),
                permissions=discord.Permissions.none(),
                reason="Lexus Security Quarantine System Setup"
            )
            # Apply overwrites to all channels
            for ch in guild.channels:
                try:
                    await ch.set_permissions(
                        role,
                        send_messages=False,
                        send_messages_in_threads=False,
                        create_public_threads=False,
                        create_private_threads=False,
                        speak=False,
                        add_reactions=False
                    )
                except Exception:
                    pass
            return role
        except Exception as e:
            logger.error(f"Failed to create quarantine role in {guild.name}: {e}")
            return None

    async def quarantine_member(
        self,
        guild: discord.Guild,
        member: discord.Member,
        reason: str,
        config: GuildSecurityConfig
    ) -> ActionResult:
        """Quarantine a member by saving their roles and applying the quarantine role."""
        bot = guild.me
        can_act, check_reason = can_bot_act_on_member(bot, member, "manage_roles")
        if not can_act:
            return ActionResult(
                success=False,
                action=SecurityActionType.QUARANTINE,
                target_id=member.id,
                error=check_reason
            )

        # Check if already quarantined in DB
        existing_record = await security_db.get_quarantine(guild.id, member.id)
        if existing_record:
            return ActionResult(
                success=True,
                action=SecurityActionType.QUARANTINE,
                target_id=member.id,
                reason="Member is already quarantined",
                idempotent_skip=True
            )

        # Get or create quarantine role
        role_id = config.quarantine_role_id
        q_role = guild.get_role(role_id) if role_id else None
        if not q_role:
            q_role = await self.setup_quarantine_role(guild)
            if q_role:
                config.quarantine_role_id = q_role.id
                await security_db.save_config(guild.id, {"quarantine_role_id": q_role.id})

        if not q_role:
            return ActionResult(
                success=False,
                action=SecurityActionType.QUARANTINE,
                target_id=member.id,
                error="Could not establish quarantine role"
            )

        # Save previous non-default roles
        previous_role_ids = [r.id for r in member.roles if not r.is_default() and r.id != q_role.id]

        try:
            # Strip manageable roles and add quarantine role
            roles_to_keep = [r for r in member.roles if r.position >= bot.top_role.position or r.managed]
            roles_to_keep.append(q_role)

            await member.edit(roles=roles_to_keep, reason=f"Lexus Security Quarantine: {reason}")

            # Record in database
            await security_db.save_quarantine(guild.id, member.id, {
                "guild_id": guild.id,
                "user_id": member.id,
                "previous_roles": previous_role_ids,
                "reason": reason,
                "quarantined_at": time.time()
            })

            return ActionResult(
                success=True,
                action=SecurityActionType.QUARANTINE,
                target_id=member.id,
                reason=reason
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action=SecurityActionType.QUARANTINE,
                target_id=member.id,
                error=str(e)
            )

    async def release_member(
        self,
        guild: discord.Guild,
        member: discord.Member,
        config: GuildSecurityConfig
    ) -> ActionResult:
        """Release member from quarantine and restore their saved roles."""
        record = await security_db.get_quarantine(guild.id, member.id)
        saved_role_ids = record.get("previous_roles", []) if record else []

        q_role_id = config.quarantine_role_id
        q_role = guild.get_role(q_role_id) if q_role_id else None

        # Build list of restored roles
        restored_roles = [r for r in member.roles if q_role and r.id != q_role.id]
        for rid in saved_role_ids:
            role_obj = guild.get_role(rid)
            if role_obj and role_obj not in restored_roles:
                restored_roles.append(role_obj)

        try:
            await member.edit(roles=restored_roles, reason="Lexus Security: Released from quarantine")
            await security_db.remove_quarantine(guild.id, member.id)
            return ActionResult(
                success=True,
                action=SecurityActionType.QUARANTINE,
                target_id=member.id,
                reason="Released from quarantine and restored roles"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=SecurityActionType.QUARANTINE,
                target_id=member.id,
                error=str(e)
            )


# Global quarantine manager instance
quarantine_manager = QuarantineManager()
