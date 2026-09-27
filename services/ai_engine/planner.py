"""Deterministic planning policy for AI requests."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AIIntent, RouteDecision


@dataclass(slots=True)
class ExecutionPlan:
    intent: AIIntent
    allow_tools: bool
    allow_mutations: bool
    max_iterations: int
    max_tool_calls: int
    max_tool_output_chars: int
    reason: str


class Planner:
    """Creates a conservative execution envelope before model inference."""

    @staticmethod
    def build(route: RouteDecision) -> ExecutionPlan:
        if route.intent is AIIntent.ACTION_REQUEST:
            return ExecutionPlan(
                intent=route.intent,
                allow_tools=True,
                allow_mutations=True,
                max_iterations=4,
                max_tool_calls=8,
                max_tool_output_chars=6000,
                reason="mutation-capable request; every mutation remains subject to application policy",
            )

        if route.intent in {
            AIIntent.SERVER_QUERY,
            AIIntent.SECURITY_QUERY,
            AIIntent.HELP,
            AIIntent.SEARCH,
        }:
            return ExecutionPlan(
                intent=route.intent,
                allow_tools=route.allow_tools,
                allow_mutations=False,
                max_iterations=4,
                max_tool_calls=6,
                max_tool_output_chars=5000,
                reason="read-oriented request",
            )

        return ExecutionPlan(
            intent=AIIntent.CHAT,
            allow_tools=False,
            allow_mutations=False,
            max_iterations=2,
            max_tool_calls=0,
            max_tool_output_chars=3000,
            reason="normal chat does not need Discord tools",
        )
