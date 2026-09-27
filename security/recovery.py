"""
Recovery analysis and conservative structural restoration engine for Lexus Security Engine.
"""

from __future__ import annotations
import logging
from typing import Optional, Any
import discord
from security.baseline import baseline_manager
from services.snapshots import StructuralDiff, GuildStructureSnapshot
from security.models import GuildSecurityConfig

logger = logging.getLogger(__name__)


class RecoveryEngine:
    """Analyzes damage following an attack or incident and prepares safe restoration."""

    async def analyze_damage(self, guild: discord.Guild) -> dict[str, Any]:
        """Generate a complete damage assessment compared against the trusted baseline."""
        diff, summary = await baseline_manager.diff_against_baseline(guild)
        if diff is None:
            return {"status": "no_baseline", "message": summary}

        deleted_roles = diff.roles_deleted
        deleted_channels = diff.channels_deleted
        modified_roles = diff.roles_modified
        modified_channels = diff.channels_modified

        return {
            "status": "success",
            "has_damage": diff.has_changes,
            "summary": summary,
            "deleted_roles_count": len(deleted_roles),
            "deleted_channels_count": len(deleted_channels),
            "modified_roles_count": len(modified_roles),
            "modified_channels_count": len(modified_channels),
            "deleted_roles": [{"id": r["id"], "name": r["name"]} for r in deleted_roles],
            "deleted_channels": [{"id": c["id"], "name": c["name"], "type": c["type"]} for c in deleted_channels],
            "modified_roles": [{"id": r["id"], "name": r["name"]} for r in modified_roles],
        }

    async def restore_missing_channels(
        self,
        guild: discord.Guild,
        config: GuildSecurityConfig
    ) -> tuple[int, list[str]]:
        """
        Conservatively recreate channels that were deleted during an incident.
        Returns (recreated_count, list of errors/notes).
        """
        bot = guild.me
        if not bot.guild_permissions.manage_channels:
            return 0, ["Bot lacks Manage Channels permission"]

        baseline = await baseline_manager.get_trusted_baseline(guild.id)
        if not baseline:
            return 0, ["No trusted baseline available"]

        current_chan_names = {c.name.lower() for c in guild.channels}
        recreated = 0
        errors: list[str] = []

        for cid, cdata in baseline.channels.items():
            name = cdata["name"]
            # Skip if already exists by name
            if name.lower() in current_chan_names:
                continue

            try:
                # Default recreate as text channel if standard text
                ctype_str = cdata.get("type", "ChannelType.text")
                if "voice" in ctype_str:
                    await guild.create_voice_channel(name=name, reason="Lexus Recovery: Restoring deleted channel")
                else:
                    await guild.create_text_channel(name=name, reason="Lexus Recovery: Restoring deleted channel")
                recreated += 1
            except Exception as e:
                errors.append(f"Failed to recreate {name}: {e}")

        return recreated, errors


# Global recovery engine instance
recovery_engine = RecoveryEngine()
