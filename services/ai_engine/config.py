"""Validated, resource-bounded Brain settings; no credentials in diagnostics."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass


def enabled(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def number(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        return max(low, min(value, high)) if math.isfinite(value) else default
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class BrainConfig:
    external_enabled: bool = True
    max_concurrent: int = 8
    per_guild: int = 3
    request_timeout: float = 65.0
    context_chars: int = 10000
    prompt_chars: int = 8000
    session_ttl: float = 900.0
    session_count: int = 1000
    history_ttl: float = 86400.0
    local_enabled: bool = False
    local_url: str = "http://127.0.0.1:11434/v1"
    local_model: str = ""
    local_timeout: float = 15.0
    external_call_limit: int = 200
    provider_retries: int = 1

    @classmethod
    def from_env(cls) -> BrainConfig:
        return cls(
            external_enabled=enabled("AI_EXTERNAL_ENABLED", True),
            max_concurrent=int(number("AI_MAX_CONCURRENT", 8, 1, 64)),
            per_guild=int(number("AI_GUILD_CONCURRENT", 3, 1, 16)),
            request_timeout=number("AI_REQUEST_TIMEOUT", 65, 1, 180),
            context_chars=int(number("AI_CONTEXT_CHARS", 10000, 4000, 32000)),
            prompt_chars=int(number("AI_PROMPT_CHARS", 8000, 100, 16000)),
            session_ttl=number("AI_SESSION_TTL", 900, 1, 3600),
            session_count=int(number("AI_SESSION_COUNT", 1000, 1, 5000)),
            history_ttl=number("AI_HISTORY_TTL", 86400, 60, 604800),
            local_enabled=enabled("AI_LOCAL_ENABLED"),
            local_url=os.getenv("AI_LOCAL_URL", "http://127.0.0.1:11434/v1").strip(),
            local_model=os.getenv("AI_LOCAL_MODEL", "").strip(),
            local_timeout=number("AI_LOCAL_TIMEOUT", 15, 1, 60),
            external_call_limit=int(number("AI_EXTERNAL_CALL_LIMIT", 200, 0, 100000)),
            provider_retries=int(number("AI_PROVIDER_RETRIES", 1, 0, 2)),
        )
