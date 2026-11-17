"""Load the project's environment without replacing hosting-platform settings."""

from __future__ import annotations

import os
from collections.abc import Collection
from pathlib import Path

from dotenv import dotenv_values


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
PROVIDER_ENV_NAMES = frozenset({
    "GROQ_API_KEY", "GROQ_MODEL", "GROQ_CHAT_MODEL", "GROQ_VISION_MODEL",
    "AI_PROVIDER_COOLDOWN_SECONDS", "TAVILY_API_KEY", "GOOGLE_API_KEY",
    "GOOGLE_CSE_ID", "AI_GATEWAY_API_KEY", "JEV_API_URL", "JEV_MODEL",
    "JEV_ENABLED", "JEV_TOOL_GATE_ENABLED", "JEV_TIMEOUT_SECONDS",
    "JEV_CACHE_TTL_SECONDS", "JEV_CACHE_SIZE", "JEV_MAX_STATE_CHARS",
    "JEV_NO_TOOLS_THRESHOLD",
})

# Only values installed by this loader may be replaced on an explicit reload.
_file_values: dict[str, str] = {}


def load_environment(*, refresh: bool = False, names: Collection[str] | None = None) -> None:
    """Use a fixed .env path; preserve process values and intentional empty models.

    A blank Groq credential may fall back to the file. Reload updates/removes
    file-owned values, but never overwrites a nonempty platform credential.
    """
    if os.getenv("PYTHON_DOTENV_DISABLED", "").casefold() in {"1", "true", "t", "yes", "y"}:
        return
    values = dotenv_values(ENV_PATH, encoding="utf-8-sig")
    keys = set(names) if names is not None else set(values) | set(_file_values)
    for name in keys:
        current = os.getenv(name)
        owned = name in _file_values and current == _file_values[name]
        value = values.get(name)
        if value is None:
            if refresh and owned:
                os.environ.pop(name, None)
                _file_values.pop(name, None)
            continue
        blank_credential = name == "GROQ_API_KEY" and not (current or "").strip()
        if current is None or blank_credential or (refresh and owned):
            os.environ[name] = value
            _file_values[name] = value
        elif not owned:
            _file_values.pop(name, None)


def environment_source(name: str) -> str:
    """Describe the selected source without returning any credential data."""
    current = os.getenv(name)
    if not current or not current.strip():
        return "missing"
    return "project .env" if _file_values.get(name) == current else "process environment"
