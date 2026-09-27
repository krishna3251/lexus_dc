"""Bounded telemetry for the Lexus AI Engine."""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RequestMetric:
    duration_ms: float
    success: bool
    intent: str
    provider: str | None
    model: str | None
    tools_used: tuple[str, ...]


class AITelemetry:
    """In-memory metrics with strict bounded history."""

    def __init__(self, max_history: int = 200) -> None:
        self.requests_total = 0
        self.requests_failed = 0
        self.provider_calls = Counter()
        self.tool_calls = Counter()
        self._history: deque[RequestMetric] = deque(maxlen=max_history)

    def start(self) -> float:
        return time.perf_counter()

    def finish(
        self,
        started: float,
        *,
        success: bool,
        intent: str,
        provider: str | None,
        model: str | None,
        tools_used: list[str],
    ) -> None:
        self.requests_total += 1
        if not success:
            self.requests_failed += 1
        if provider:
            self.provider_calls[provider] += 1
        for tool in tools_used:
            self.tool_calls[tool] += 1
        self._history.append(
            RequestMetric(
                duration_ms=(time.perf_counter() - started) * 1000.0,
                success=success,
                intent=intent,
                provider=provider,
                model=model,
                tools_used=tuple(tools_used),
            )
        )

    def snapshot(self) -> dict[str, Any]:
        last = self._history[-1] if self._history else None
        return {
            "requests_total": self.requests_total,
            "requests_failed": self.requests_failed,
            "provider_calls": dict(self.provider_calls),
            "tool_calls": dict(self.tool_calls),
            "history_size": len(self._history),
            "last_request_ms": round(last.duration_ms, 2) if last else None,
        }
