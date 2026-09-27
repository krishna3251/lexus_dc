"""Validation layer for model-produced tool calls."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .models import ToolCall
from .planner import ExecutionPlan
from .tools import ToolRegistry


@dataclass(slots=True)
class ToolValidation:
    allowed: bool
    reason: str


class ToolCallValidator:
    """Validates tool identity, risk envelope, and bounded arguments."""

    MAX_ARGUMENT_BYTES = 8000

    @classmethod
    def validate(
        cls,
        call: ToolCall,
        registry: ToolRegistry,
        plan: ExecutionPlan,
    ) -> ToolValidation:
        spec = registry.get(call.name)
        if spec is None:
            return ToolValidation(False, f"Unknown tool: {call.name}")

        if spec.mutating and not plan.allow_mutations:
            return ToolValidation(False, "This request is restricted to read-only tools.")

        try:
            raw = json.dumps(call.arguments, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return ToolValidation(False, "Tool arguments are not JSON serializable.")

        if len(raw.encode("utf-8")) > cls.MAX_ARGUMENT_BYTES:
            return ToolValidation(False, "Tool arguments exceed the safety size limit.")

        return ToolValidation(True, "validated")
