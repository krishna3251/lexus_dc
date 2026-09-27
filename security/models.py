"""
Domain models, enums, and data transfer objects for the Lexus Security Engine.
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum, unique
from typing import Optional, Any
from core.events import SecurityEventType


@unique
class SecurityState(str, Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    RAID = "RAID"
    PANIC = "PANIC"
    RECOVERY = "RECOVERY"


@unique
class RaidSubState(str, Enum):
    NONE = "NONE"
    RAID_SUSPECTED = "RAID_SUSPECTED"
    RAID_CONFIRMED = "RAID_CONFIRMED"


@unique
class TrustLevel(str, Enum):
    OWNER = "OWNER"
    TRUSTED = "TRUSTED"
    STAFF = "STAFF"
    MEMBER = "MEMBER"
    NEW_MEMBER = "NEW_MEMBER"
    UNKNOWN = "UNKNOWN"
    SUSPICIOUS = "SUSPICIOUS"
    QUARANTINED = "QUARANTINED"


@unique
class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@unique
class SecurityActionType(str, Enum):
    LOG = "LOG"
    ALERT = "ALERT"
    DELETE = "DELETE"
    TIMEOUT = "TIMEOUT"
    QUARANTINE = "QUARANTINE"
    KICK = "KICK"
    BAN = "BAN"
    LOCK_CHANNEL = "LOCK_CHANNEL"
    LOCKDOWN = "LOCKDOWN"
    PROTECT_ASSET = "PROTECT_ASSET"
    RECOVERY_ACTION = "RECOVERY_ACTION"


@unique
class SecurityProfile(str, Enum):
    STANDARD = "STANDARD"
    STRICT = "STRICT"
    CUSTOM = "CUSTOM"


@dataclass
class SecurityEvent:
    guild_id: int
    event_type: SecurityEventType
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    actor_id: Optional[int] = None
    target_id: Optional[int] = None
    channel_id: Optional[int] = None
    source: str = "discord"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_type"] = self.event_type.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecurityEvent:
        event_type_str = data.get("event_type", "MESSAGE")
        event_type = SecurityEventType(event_type_str) if isinstance(event_type_str, str) else event_type_str
        return cls(
            event_id=data.get("event_id", f"evt_{uuid.uuid4().hex[:12]}"),
            guild_id=data["guild_id"],
            actor_id=data.get("actor_id"),
            target_id=data.get("target_id"),
            channel_id=data.get("channel_id"),
            event_type=event_type,
            timestamp=data.get("timestamp", time.time()),
            source=data.get("source", "discord"),
            metadata=data.get("metadata", {})
        )


@dataclass
class Evidence:
    detector_name: str
    score: float  # 0.0 to 100.0
    confidence: float  # 0.0 to 1.0
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionResult:
    success: bool
    action: SecurityActionType
    target_id: Optional[int] = None
    target_type: str = "member"
    reason: str = ""
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    idempotent_skip: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data


@dataclass
class GuildSecurityConfig:
    guild_id: int
    security_enabled: bool = True
    security_mode: str = "enforce"  # "audit" or "enforce"
    profile: SecurityProfile = SecurityProfile.STANDARD
    quarantine_role_id: Optional[int] = None
    security_log_channel_id: Optional[int] = None
    security_admin_role_id: Optional[int] = None
    trusted_users: list[int] = field(default_factory=list)
    trusted_roles: list[int] = field(default_factory=list)
    trusted_bots: list[int] = field(default_factory=list)
    protected_roles: list[int] = field(default_factory=list)
    protected_channels: list[int] = field(default_factory=list)
    action_budget_limit: int = 10
    action_budget_window: float = 10.0
    spam_enabled: bool = True
    raid_enabled: bool = True
    antinuke_enabled: bool = True
    join_gate_enabled: bool = True
    lockdown_enabled: bool = True
    recovery_enabled: bool = True
    custom_thresholds: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["profile"] = self.profile.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GuildSecurityConfig:
        profile_str = data.get("profile", "STANDARD")
        try:
            profile = SecurityProfile(profile_str)
        except ValueError:
            profile = SecurityProfile.STANDARD

        return cls(
            guild_id=data["guild_id"],
            security_enabled=data.get("security_enabled", True),
            security_mode=data.get("security_mode", "enforce"),
            profile=profile,
            quarantine_role_id=data.get("quarantine_role_id"),
            security_log_channel_id=data.get("security_log_channel_id"),
            security_admin_role_id=data.get("security_admin_role_id"),
            trusted_users=data.get("trusted_users", []),
            trusted_roles=data.get("trusted_roles", []),
            trusted_bots=data.get("trusted_bots", []),
            protected_roles=data.get("protected_roles", []),
            protected_channels=data.get("protected_channels", []),
            action_budget_limit=data.get("action_budget_limit", 10),
            action_budget_window=data.get("action_budget_window", 10.0),
            spam_enabled=data.get("spam_enabled", True),
            raid_enabled=data.get("raid_enabled", True),
            antinuke_enabled=data.get("antinuke_enabled", True),
            join_gate_enabled=data.get("join_gate_enabled", True),
            lockdown_enabled=data.get("lockdown_enabled", True),
            recovery_enabled=data.get("recovery_enabled", True),
            custom_thresholds=data.get("custom_thresholds", {})
        )
