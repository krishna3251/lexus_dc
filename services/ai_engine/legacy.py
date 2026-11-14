"""Shared privacy and attempt accounting for existing provider-specific cogs."""
from __future__ import annotations

from .providers import ProviderError


async def reserve_legacy_call(bot, user_id: int | None, guild_id: int | None) -> bool:
    """Fail closed without the Brain policy or an identifiable requesting user."""
    engine = getattr(bot, "ai_engine", None)
    if engine is None or user_id is None or not engine.config.external_enabled:
        return False
    preferences = await engine.memory.preferences(user_id, guild_id)
    if not preferences["external_allowed"]:
        return False
    try:
        engine.providers.reserve_external()
    except ProviderError:
        return False
    return True


def record_legacy_usage(bot, provider: str, model: str, usage) -> None:
    engine = getattr(bot, "ai_engine", None)
    if engine is not None:
        engine.providers.record_usage(provider, model, usage)
