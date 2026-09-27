"""
Trusted structural baseline manager for Lexus Security Engine.
Enforces baseline safety rules so baselines cannot be captured or overwritten
during RAID, PANIC, or RECOVERY states.
"""

from __future__ import annotations
import logging
from typing import Optional, Any
import discord
from security.models import SecurityState
from services.snapshots import (
    GuildStructureSnapshot,
    StructuralDiff,
    capture_guild_snapshot,
    compare_structures
)
from services.database import security_db

logger = logging.getLogger(__name__)


class BaselineManager:
    """Manages trusted structural baselines and ensures baseline safety invariants."""

    def can_update_baseline(self, current_state: SecurityState) -> bool:
        """Baseline updates are forbidden during threat states (RAID, PANIC, RECOVERY)."""
        return current_state == SecurityState.NORMAL

    async def capture_and_save_baseline(
        self,
        guild: discord.Guild,
        current_state: SecurityState,
        force: bool = False
    ) -> tuple[bool, str, Optional[GuildStructureSnapshot]]:
        """
        Capture current server structure as the new trusted baseline.
        Fails safely if the server is in an elevated or threat state unless force is True.
        """
        if not force and not self.can_update_baseline(current_state):
            return (
                False,
                f"Cannot update baseline while server security state is {current_state.value}. "
                "Baselines may only be captured during NORMAL state to prevent normalizing attack conditions.",
                None
            )

        snapshot = capture_guild_snapshot(guild, is_known_good=True)
        success = await security_db.save_baseline(guild.id, snapshot.to_dict())
        if success:
            return True, f"Baseline successfully captured ({len(snapshot.roles)} roles, {len(snapshot.channels)} channels).", snapshot
        return False, "Failed to persist baseline to database.", None

    async def get_trusted_baseline(self, guild_id: int) -> Optional[GuildStructureSnapshot]:
        """Fetch the trusted baseline for a guild."""
        doc = await security_db.get_baseline(guild_id)
        if doc:
            return GuildStructureSnapshot.from_dict(doc)
        return None

    async def diff_against_baseline(
        self,
        guild: discord.Guild
    ) -> tuple[Optional[StructuralDiff], str]:
        """Compare current live guild structure with the trusted baseline."""
        baseline = await self.get_trusted_baseline(guild.id)
        if not baseline:
            return None, "No trusted baseline exists for this server. Run `/security baseline capture` first."

        current = capture_guild_snapshot(guild, is_known_good=False)
        diff = compare_structures(current, baseline)
        return diff, diff.summary()


# Global baseline manager instance
baseline_manager = BaselineManager()
