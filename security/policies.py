"""
Policy engine mapping risk, guild state, trust level, and confidence to security actions.
Enforces audit mode simulation and protects trusted roles from automated overreaction.
"""

from __future__ import annotations
from typing import Optional
from security.models import (
    SecurityState,
    TrustLevel,
    Severity,
    SecurityActionType,
    SecurityProfile,
    GuildSecurityConfig
)


class PolicyEngine:
    """
    Decides appropriate security responses based on risk, server state,
    actor trust level, and profile settings.
    """

    @staticmethod
    def evaluate(
        risk_score: float,
        severity: Severity,
        confidence: float,
        guild_state: SecurityState,
        actor_trust: TrustLevel,
        is_structural: bool,
        config: GuildSecurityConfig
    ) -> list[SecurityActionType]:
        """
        Determine actions to take for an evaluated incident.
        Returns list of SecurityActionType.
        """
        # Audit mode check: never return destructive actions in audit mode
        is_audit = config.security_mode == "audit"

        # Owner and Staff protections
        if actor_trust == TrustLevel.OWNER:
            return [SecurityActionType.LOG]

        if actor_trust in (TrustLevel.TRUSTED, TrustLevel.STAFF) and not is_structural:
            if severity in (Severity.HIGH, Severity.CRITICAL):
                return [SecurityActionType.LOG, SecurityActionType.ALERT]
            return [SecurityActionType.LOG]

        actions: list[SecurityActionType] = [SecurityActionType.LOG]

        # Profile strictness adjustments
        conf_threshold = 0.60 if config.profile == SecurityProfile.STRICT else 0.70

        # CRITICAL structural attacks (Anti-Nuke / Unauthorized escalation).
        # Unknown/unattributed actors are never quarantine or lockdown targets.
        # The detector may still raise an alert, but containment requires a
        # confirmed Audit Log actor so a delayed/missing audit entry cannot turn
        # an unrelated event into a server-wide lockdown.
        if is_structural and severity == Severity.CRITICAL:
            actions.append(SecurityActionType.ALERT)

            # Structural events are high-impact by definition. Containment is
            # allowed only when Lexus can attribute the change to a concrete
            # actor. Missing audit attribution must never become permission to
            # lock the whole server.
            if actor_trust == TrustLevel.UNKNOWN:
                return actions

            # Trusted/staff actors may legitimately perform structural changes.
            # Do not automatically quarantine them from one structural signal.
            # They remain visible to alerts and incident correlation for review.
            if actor_trust in (TrustLevel.TRUSTED, TrustLevel.STAFF):
                return actions

            if not is_audit and confidence >= conf_threshold:
                actions.append(SecurityActionType.QUARANTINE)
                if guild_state == SecurityState.PANIC or risk_score >= 90.0:
                    actions.append(SecurityActionType.LOCKDOWN)
            return actions

        # Standard threat matrix
        if severity == Severity.CRITICAL:
            actions.append(SecurityActionType.ALERT)
            if not is_audit and confidence >= conf_threshold:
                if actor_trust != TrustLevel.UNKNOWN:
                    actions.append(SecurityActionType.QUARANTINE)
        elif severity == Severity.HIGH:
            actions.append(SecurityActionType.ALERT)
            if not is_audit:
                if confidence >= conf_threshold:
                    if actor_trust in (TrustLevel.NEW_MEMBER, TrustLevel.SUSPICIOUS):
                        actions.append(SecurityActionType.QUARANTINE)
                    else:
                        actions.append(SecurityActionType.TIMEOUT)
        elif severity == Severity.MEDIUM:
            if not is_audit and actor_trust in (TrustLevel.NEW_MEMBER, TrustLevel.SUSPICIOUS):
                actions.append(SecurityActionType.TIMEOUT)
            elif config.profile == SecurityProfile.STRICT and not is_audit:
                actions.append(SecurityActionType.TIMEOUT)
        elif severity == Severity.LOW:
            # Observational logging only
            pass

        return actions
