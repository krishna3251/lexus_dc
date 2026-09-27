"""Bounded, sequential execution wrapper for AI tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging

from .models import ToolCall
from .tools import ToolContext, ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes one model-requested tool at a time with request-local dedup."""

    def __init__(self, registry: ToolRegistry, timeout_seconds: float = 12.0) -> None:
        self.registry = registry
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _fingerprint(call: ToolCall) -> str:
        raw = json.dumps(
            {"name": call.name, "arguments": call.arguments},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def execute(
        self,
        call: ToolCall,
        context: ToolContext,
        seen_calls: set[str],
    ) -> dict:
        fingerprint = self._fingerprint(call)
        if fingerprint in seen_calls:
            return {
                "success": False,
                "error": "Duplicate tool call suppressed by request deduplication.",
            }

        seen_calls.add(fingerprint)

        try:
            return await asyncio.wait_for(
                self.registry.execute(call.name, call.arguments, context),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("AI tool timed out: %s", call.name)
            return {
                "success": False,
                "error": f"Tool timed out after {self.timeout_seconds:.1f}s.",
            }
