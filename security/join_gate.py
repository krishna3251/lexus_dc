"""
Join gate evaluating account age, join timing, avatar metadata, and state correlation.
Uses multi-signal evaluation to avoid false positives on legitimate new users.
"""

from __future__ import annotations
import time
from typing import Optional, Any
from security.models import Evidence, SecurityEvent, SecurityState, TrustLevel


class JoinGate:
    """
    Evaluates newly joined members against suspicious account attributes,
    contextual guild threat state, and account age profiles.
    """

    def evaluate(
        self,
        event: SecurityEvent,
        guild_state: SecurityState,
        account_created_at: Optional[float] = None,
        has_default_avatar: bool = False
    ) -> tuple[TrustLevel, Optional[Evidence]]:
        """
        Evaluate new member.
        Returns (initial_trust_level, Optional[Evidence]).
        """
        now = time.time()
        score = 0.0
        reasons: list[str] = []
        trust = TrustLevel.NEW_MEMBER

        # 1. Account age evaluation
        if account_created_at is not None:
            age_seconds = now - account_created_at
            age_hours = age_seconds / 3600.0

            if age_hours < 1.0:
                score += 35.0
                reasons.append(f"Extremely young account ({int(age_seconds / 60)} minutes old)")
            elif age_hours < 24.0:
                score += 20.0
                reasons.append(f"Account created <24h ago ({int(age_hours)}h old)")
            elif age_hours < 168.0:  # 7 days
                score += 10.0
                reasons.append("Account created <7 days ago")

        # 2. Avatar signal (secondary only, never primary alone)
        if has_default_avatar:
            score += 10.0
            reasons.append("Default Discord avatar")

        # 3. Contextual guild threat state correlation
        if guild_state == SecurityState.RAID:
            score += 45.0
            reasons.append("Member joined while server is under active RAID")
            trust = TrustLevel.SUSPICIOUS
        elif guild_state == SecurityState.ELEVATED:
            score += 20.0
            reasons.append("Member joined during ELEVATED security state")

        if score >= 45.0:
            evidence = Evidence(
                detector_name="JoinGate",
                score=min(100.0, score),
                confidence=0.75,
                reason="; ".join(reasons),
                metadata={"reasons": reasons, "guild_state": guild_state.value}
            )
            return trust, evidence

        return trust, None
