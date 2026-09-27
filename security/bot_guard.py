"""
Bot addition guard for Lexus Security Engine.
Inspects newly added bots, correlating the installer, bot permissions,
and installer trust to guard against rogue bot attacks.
"""

from __future__ import annotations
from typing import Optional, Any
from security.models import Evidence, SecurityEvent, TrustLevel, GuildSecurityConfig
from core.permissions import DANGEROUS_PERMISSIONS, permissions_to_dict


class BotGuard:
    """Evaluates bot joins and flags unauthorized or high-risk bot additions."""

    def evaluate(
        self,
        event: SecurityEvent,
        bot_id: int,
        installer_id: Optional[int],
        bot_permissions_val: int,
        installer_trust: TrustLevel,
        config: GuildSecurityConfig
    ) -> Optional[Evidence]:
        """Evaluate bot addition event."""
        # Check if bot is explicitly trusted
        if bot_id in config.trusted_bots:
            return None

        # Check if installer is owner
        if installer_trust == TrustLevel.OWNER:
            return None

        perms_dict = permissions_to_dict(bot_permissions_val)
        has_admin = perms_dict.get("administrator", False)
        dangerous_added = [p for p in DANGEROUS_PERMISSIONS if perms_dict.get(p, False)]

        score = 0.0
        reasons: list[str] = []
        confidence = 0.80

        if has_admin:
            score += 70.0
            reasons.append("Unauthorized bot added with Administrator permission")
            confidence = 0.90
        elif dangerous_added:
            score += 40.0
            reasons.append(f"Bot added with dangerous permissions: {', '.join(dangerous_added[:3])}")
        else:
            score += 25.0
            reasons.append("Unverified external bot added to server")

        if installer_trust in (TrustLevel.UNKNOWN, TrustLevel.NEW_MEMBER, TrustLevel.SUSPICIOUS):
            score += 30.0
            reasons.append(f"Installer has low trust ({installer_trust.value})")

        if score >= 35.0:
            return Evidence(
                detector_name="BotGuard",
                score=min(100.0, score),
                confidence=confidence,
                reason="; ".join(reasons),
                metadata={
                    "bot_id": bot_id,
                    "installer_id": installer_id,
                    "has_admin": has_admin,
                    "dangerous_permissions": dangerous_added
                }
            )

        return None
