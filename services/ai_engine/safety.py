"""Prompt and action safety checks for the Lexus AI Engine."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import AIIntent


@dataclass(slots=True)
class SafetyAssessment:
    allowed: bool
    risk: str
    reasons: tuple[str, ...]


class SafetyGate:
    """Reject obvious attempts to bypass application security or exfiltrate secrets."""

    SECRET_PATTERNS = (
        r"\b(?:show|reveal|print|give|send)\b.*\b(?:api key|token|secret|password)\b",
        r"\b(?:environment variables?|\.env)\b.*\b(?:show|dump|print|reveal)\b",
    )

    BYPASS_PATTERNS = (
        r"\bignore\b.*\b(?:previous|system|developer)\b.*\b(?:rules?|instructions?|permissions?|security)\b",
        r"\bbypass\b.*\b(?:permission|security|role|safety)\b",
        r"\bdisable\b.*\b(?:security|antinuke|anti.nuke|quarantine)\b",
    )

    BULK_MUTATION_PATTERNS = (
        r"\b(?:ban|kick|timeout|remove|delete)\b.*\b(?:everyone|everybody|all members|all users)\b",
        r"\b(?:lock|delete|remove)\b.*\b(?:all channels|every channel|server)\b",
    )

    @classmethod
    def assess(cls, prompt: str, intent: AIIntent) -> SafetyAssessment:
        text = prompt.casefold().strip()
        reasons: list[str] = []

        for pattern in cls.SECRET_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                reasons.append("secret_exfiltration_request")

        for pattern in cls.BYPASS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                reasons.append("security_bypass_attempt")

        if intent is AIIntent.ACTION_REQUEST:
            for pattern in cls.BULK_MUTATION_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    reasons.append("bulk_mutation_request")

        if reasons:
            return SafetyAssessment(
                allowed=False,
                risk="critical",
                reasons=tuple(reasons),
            )

        return SafetyAssessment(
            allowed=True,
            risk="normal" if intent is not AIIntent.ACTION_REQUEST else "elevated",
            reasons=(),
        )
