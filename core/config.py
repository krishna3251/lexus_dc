"""
Core configuration management for Lexus bot and security engine.
Centralizes environment configuration without hardcoding secrets or guild-specific IDs.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on", "enable", "enabled")


def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class CoreConfig:
    # Discord credentials & general info
    token: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", ""))
    owner_id: int = field(default_factory=lambda: _get_int("BOT_OWNER_ID", 486555340670894080))
    bot_version: str = field(default_factory=lambda: os.getenv("BOT_VERSION", "3.0.0"))

    # Web & Hosting
    port: int = field(default_factory=lambda: _get_int("PORT", 10000))
    api_secret_key: str = field(default_factory=lambda: os.getenv("API_SECRET_KEY", ""))

    # MongoDB
    mongo_uri: str = field(default_factory=lambda: os.getenv("MONGO_URI", ""))
    mongo_db_name: str = field(default_factory=lambda: os.getenv("MONGO_DB_NAME", "lexus_bot"))

    # Audio / Lavalink
    lavalink_uri: str = field(default_factory=lambda: os.getenv("LAVALINK_URI", "wss://lavalink-4-production-438b.up.railway.app"))
    lavalink_password: str = field(default_factory=lambda: os.getenv("LAVALINK_PASSWORD", "lexus123"))

    # Security engine deployment settings
    security_enabled: bool = field(default_factory=lambda: _get_bool("SECURITY_ENABLED", True))
    security_mode: str = field(default_factory=lambda: os.getenv("SECURITY_MODE", "audit").strip().lower())
    security_log_level: str = field(default_factory=lambda: os.getenv("SECURITY_LOG_LEVEL", "INFO").strip().upper())
    security_log_dir: str = field(default_factory=lambda: os.getenv("SECURITY_LOG_DIR", "logs"))

    # Action budget defaults
    action_budget_limit: int = field(default_factory=lambda: _get_int("SECURITY_ACTION_BUDGET_LIMIT", 10))
    action_budget_window: float = field(default_factory=lambda: float(os.getenv("SECURITY_ACTION_BUDGET_WINDOW", "10.0")))

    def is_audit_mode(self) -> bool:
        return self.security_mode == "audit"

    def is_enforce_mode(self) -> bool:
        return self.security_mode == "enforce"


# Global singleton instance
config = CoreConfig()
