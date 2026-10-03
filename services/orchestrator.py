"""High-level Lexus conversation orchestrator.

Rukiya's V2 architecture is adapted here for Discord-only use. The orchestrator
owns lifecycle decisions and behavioral context; AIEngine remains responsible
for model calls, tool validation, permissions, execution, memory persistence,
and provider failover.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any

from services.cache import TTLCache

from .ai_engine.behavior import BehaviorAnalyzer, BehaviorSession
from .ai_engine.engine import AIEngine, DEFAULT_SYSTEM_PROMPT
from .ai_engine.models import AIRequest, AIResult
from .ai_engine.tools import ToolContext

logger = logging.getLogger(__name__)


class LexusOrchestrator:
    """Coordinates behavioral decisioning before generation."""

    def __init__(self, engine: AIEngine | None = None) -> None:
        self.engine = engine or AIEngine()
        self.behavior = BehaviorAnalyzer()
        self._sessions: TTLCache[tuple[int, int, int], BehaviorSession] = TTLCache(
            max_size=5000,
            default_ttl=1800.0,
        )
        self._session_lock = asyncio.Lock()
        self._closed = False

    @property
    def ai_engine(self) -> AIEngine:
        return self.engine

    @property
    def active_behavior_sessions(self) -> int:
        return self._sessions.size

    def _session_key(self, request: AIRequest) -> tuple[int, int, int]:
        return (
            int(request.guild_id or -1),
            int(request.channel_id or -1),
            int(request.user_id),
        )

    async def ask(self, request: AIRequest, context: ToolContext) -> AIResult:
        """Run normalize -> behavior decision -> AI generation -> memory pipeline."""
        prompt = request.prompt.strip()
        if not prompt:
            return await self.engine.ask(request, context)

        async with self._session_lock:
            key = self._session_key(request)
            session = self._sessions.get(key)
            if session is None:
                session = BehaviorSession()
                self._sessions.set(key, session)
            behavior = self.behavior.analyze(prompt, session)

        target_tokens = {
            "minimal": 320,
            "moderate": 520,
            "detailed": 800,
        }.get(behavior.response_length_target, request.max_output_tokens)
        max_tokens = min(max(1, request.max_output_tokens), target_tokens)

        base_system = request.system_prompt.strip() if request.system_prompt else DEFAULT_SYSTEM_PROMPT
        system_prompt = f"{base_system}\n\n{behavior.as_prompt_fragment()}"

        routed_request = replace(
            request,
            prompt=prompt,
            system_prompt=system_prompt,
            max_output_tokens=max_tokens,
        )

        result = await self.engine.ask(routed_request, context)
        logger.debug(
            "Lexus orchestration complete | user=%s guild=%s intent=%s mood=%s "
            "phase=%s sarcasm=%s length=%s success=%s",
            request.user_id,
            request.guild_id,
            behavior.intent.value,
            behavior.mood.value,
            behavior.phase.value,
            behavior.sarcasm_permitted,
            behavior.response_length_target,
            result.success,
        )
        return result

    async def evaluate_decision(self, state: Any, questions: dict[str, Any]):
        """Expose the typed decision service without coupling callers to AIEngine."""
        return await self.engine.evaluate_decision(state, questions)

    async def reload_providers(self) -> None:
        await self.engine.reload_providers()

    def health(self) -> dict[str, Any]:
        health = self.engine.health()
        health["orchestrator"] = {
            "active_behavior_sessions": self.active_behavior_sessions,
            "behavior_engine": "deterministic",
            "decision_generation_separated": True,
        }
        return health

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self.engine.close()
        finally:
            logger.info("🧭 Lexus Orchestrator shut down")


__all__ = ["LexusOrchestrator"]
