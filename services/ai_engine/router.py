"""Deterministic request routing for the Lexus AI Engine."""

from __future__ import annotations

import re

from .models import AIIntent, RouteDecision


class RequestRouter:
    """Classifies intent locally before an LLM is called.

    The router never executes an action. It only narrows the job the model is
    being asked to perform and supplies conservative defaults for tool access.
    """

    ACTION_PATTERNS = (
        r"\b(?:ban|kick|timeout|mute|lock|unlock)\b",
        r"\b(?:remove|delete|add|create)\b.*\b(?:member|user|role|channel|webhook)\b",
        r"\b(?:give|take|assign|remove)\b.*\brole\b",
    )

    SECURITY_PATTERNS = (
        r"\b(?:security|raid|raid mode|panic mode|antinuke|anti.nuke|quarantine)\b",
        r"\b(?:incident|audit log|audit logs|suspicious|attack)\b",
        r"\bwhy\b.*\b(?:banned|quarantined|locked|security)\b",
    )

    SERVER_PATTERNS = (
        r"\b(?:server|guild)\b",
        r"\b(?:members|users|channels|roles|bot status|latency)\b",
        r"\bhow many\b.*\b(?:members|channels|roles)\b",
    )

    HELP_PATTERNS = (
        r"\b(?:how do i|how can i|what command|which command|help me use)\b",
        r"\b(?:commands|command list|what can you do)\b",
    )

    SEARCH_PATTERNS = (
        r"\b(?:search|look up|find online|latest|current news|on the web)\b",
    )

    @classmethod
    def route(cls, prompt: str) -> RouteDecision:
        text = prompt.casefold().strip()
        if not text:
            return RouteDecision(
                intent=AIIntent.UNKNOWN,
                confidence=1.0,
                allow_tools=False,
                allow_mutations=False,
                reason="empty request",
            )

        if cls._matches(cls.ACTION_PATTERNS, text):
            return RouteDecision(
                intent=AIIntent.ACTION_REQUEST,
                confidence=0.96,
                allow_tools=True,
                allow_mutations=True,
                reason="request contains a Discord mutation verb",
            )

        if cls._matches(cls.SECURITY_PATTERNS, text):
            return RouteDecision(
                intent=AIIntent.SECURITY_QUERY,
                confidence=0.93,
                allow_tools=True,
                allow_mutations=False,
                reason="request concerns Lexus security telemetry",
            )

        if cls._matches(cls.HELP_PATTERNS, text):
            return RouteDecision(
                intent=AIIntent.HELP,
                confidence=0.90,
                allow_tools=True,
                allow_mutations=False,
                reason="request asks how Lexus features or commands work",
            )

        if cls._matches(cls.SEARCH_PATTERNS, text):
            return RouteDecision(
                intent=AIIntent.SEARCH,
                confidence=0.84,
                allow_tools=True,
                allow_mutations=False,
                reason="request appears to need external search",
            )

        if cls._matches(cls.SERVER_PATTERNS, text):
            return RouteDecision(
                intent=AIIntent.SERVER_QUERY,
                confidence=0.88,
                allow_tools=True,
                allow_mutations=False,
                reason="request asks for live server state",
            )

        return RouteDecision(
            intent=AIIntent.CHAT,
            confidence=0.72,
            allow_tools=False,
            allow_mutations=False,
            reason="normal conversational request",
        )

    @staticmethod
    def _matches(patterns: tuple[str, ...], text: str) -> bool:
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
