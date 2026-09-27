"""
Structural snapshot service for Discord guilds.
Captures roles, channels, and permissions safely without secrets or member dumps.
Provides structural diff comparison between current state and trusted baselines.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, asdict, field
from typing import Optional, Any
import discord


@dataclass
class RoleSnapshot:
    id: int
    name: str
    position: int
    permissions: int
    color: int
    hoist: bool
    mentionable: bool
    is_default: bool


@dataclass
class ChannelSnapshot:
    id: int
    name: str
    type: str
    position: int
    category_id: Optional[int]
    overwrites: dict[str, dict[str, int]]  # target_id -> {"allow": int, "deny": int, "type": "role"|"member"}


@dataclass
class GuildStructureSnapshot:
    guild_id: int
    guild_name: str
    timestamp: float
    is_known_good: bool
    roles: dict[int, dict[str, Any]]  # role_id -> data
    channels: dict[int, dict[str, Any]]  # channel_id -> data
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GuildStructureSnapshot:
        # Cast key strings back to ints where applicable
        roles = {int(k): v for k, v in data.get("roles", {}).items()}
        channels = {int(k): v for k, v in data.get("channels", {}).items()}
        return cls(
            guild_id=data["guild_id"],
            guild_name=data.get("guild_name", "Unknown"),
            timestamp=data.get("timestamp", time.time()),
            is_known_good=data.get("is_known_good", True),
            roles=roles,
            channels=channels,
            metadata=data.get("metadata", {})
        )


def capture_guild_snapshot(guild: discord.Guild, is_known_good: bool = True) -> GuildStructureSnapshot:
    """Capture structural state of roles and channels from a live discord.Guild."""
    roles_data: dict[int, dict[str, Any]] = {}
    for r in guild.roles:
        roles_data[r.id] = {
            "id": r.id,
            "name": r.name,
            "position": r.position,
            "permissions": r.permissions.value,
            "color": r.color.value,
            "hoist": r.hoist,
            "mentionable": r.mentionable,
            "is_default": r.is_default(),
        }

    channels_data: dict[int, dict[str, Any]] = {}
    for c in guild.channels:
        overwrites_map: dict[str, dict[str, int]] = {}
        for target, ow in c.overwrites.items():
            overwrites_map[str(target.id)] = {
                "allow": ow.pair()[0].value,
                "deny": ow.pair()[1].value,
                "type": "role" if isinstance(target, discord.Role) else "member"
            }

        channels_data[c.id] = {
            "id": c.id,
            "name": c.name,
            "type": str(c.type),
            "position": c.position,
            "category_id": c.category.id if c.category else None,
            "overwrites": overwrites_map
        }

    return GuildStructureSnapshot(
        guild_id=guild.id,
        guild_name=guild.name,
        timestamp=time.time(),
        is_known_good=is_known_good,
        roles=roles_data,
        channels=channels_data
    )


@dataclass
class StructuralDiff:
    roles_added: list[dict[str, Any]] = field(default_factory=list)
    roles_deleted: list[dict[str, Any]] = field(default_factory=list)
    roles_modified: list[dict[str, Any]] = field(default_factory=list)

    channels_added: list[dict[str, Any]] = field(default_factory=list)
    channels_deleted: list[dict[str, Any]] = field(default_factory=list)
    channels_modified: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.roles_added or self.roles_deleted or self.roles_modified or
            self.channels_added or self.channels_deleted or self.channels_modified
        )

    def summary(self) -> str:
        return (
            f"Roles: +{len(self.roles_added)} -{len(self.roles_deleted)} ~{len(self.roles_modified)} | "
            f"Channels: +{len(self.channels_added)} -{len(self.channels_deleted)} ~{len(self.channels_modified)}"
        )


def compare_structures(
    current: GuildStructureSnapshot,
    baseline: GuildStructureSnapshot
) -> StructuralDiff:
    """Compare current guild structure against trusted baseline."""
    diff = StructuralDiff()

    # Compare roles
    curr_roles = current.roles
    base_roles = baseline.roles

    for rid, rdata in curr_roles.items():
        if rid not in base_roles:
            diff.roles_added.append(rdata)
        else:
            bdata = base_roles[rid]
            if (
                rdata["name"] != bdata["name"] or
                rdata["permissions"] != bdata["permissions"] or
                rdata["position"] != bdata["position"]
            ):
                diff.roles_modified.append({
                    "id": rid,
                    "name": rdata["name"],
                    "old": bdata,
                    "new": rdata
                })

    for rid, bdata in base_roles.items():
        if rid not in curr_roles:
            diff.roles_deleted.append(bdata)

    # Compare channels
    curr_chans = current.channels
    base_chans = baseline.channels

    for cid, cdata in curr_chans.items():
        if cid not in base_chans:
            diff.channels_added.append(cdata)
        else:
            bdata = base_chans[cid]
            if (
                cdata["name"] != bdata["name"] or
                cdata.get("overwrites") != bdata.get("overwrites") or
                cdata.get("category_id") != bdata.get("category_id")
            ):
                diff.channels_modified.append({
                    "id": cid,
                    "name": cdata["name"],
                    "old": bdata,
                    "new": cdata
                })

    for cid, bdata in base_chans.items():
        if cid not in curr_chans:
            diff.channels_deleted.append(bdata)

    return diff
