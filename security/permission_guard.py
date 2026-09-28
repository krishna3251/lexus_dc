"""
Permission guard for Lexus Security Engine.
Monitors role updates and channel permission overwrites for unauthorized
escalation of critical administrative privileges (e.g. Administrator, Manage Roles).
"""

from __future__ import annotations
from typing import Optional, Any
from security.models import Evidence, SecurityEvent
from core.permissions import calculate_permission_diff, DANGEROUS_PERMISSIONS
from services.cache import TTLCache


class PermissionGuard:
    """
    Evaluates role modifications and channel permission overrides.
    Treats dangerous permission additions as early warning signals or critical breaches.
    """

    def __init__(self):
        # Cache recent permission escalations per actor: (guild_id, actor_id) -> count
        self._actor_escalations: TTLCache[tuple[int, int], int] = TTLCache(max_size=2000, default_ttl=120.0)

    def evaluate_role_update(
        self,
        event: SecurityEvent,
        before_permissions: int,
        after_permissions: int,
        is_everyone_role: bool = False,
        is_quarantine_role: bool = False,
        is_bot_role: bool = False
    ) -> Optional[Evidence]:
        """Evaluate permission delta between old role and new role."""
        diff = calculate_permission_diff(before_permissions, after_permissions)

        if not diff.added_dangerous and not (is_quarantine_role or is_everyone_role):
            return None

        actor_id = event.actor_id or 0
        guild_id = event.guild_id
        reasons: list[str] = []
        score = diff.total_risk_score
        confidence = 0.85

        # A permission change without a matching Audit Log actor is evidence of
        # a dangerous mutation, but not enough evidence to identify a culprit.
        # Keep the event visible while preventing the policy layer from treating
        # an unattributed single event as a confirmed attack.
        audit_meta = event.metadata.get("audit") if isinstance(event.metadata, dict) else None
        attribution_known = bool(
            event.actor_id
            and isinstance(audit_meta, dict)
            and audit_meta.get("attribution") == "audit_log"
        )
        if not attribution_known:
            confidence = min(confidence, 0.45)
            reasons.append("Audit actor attribution unavailable; containment requires confirmed actor")


        # 1. @everyone role escalation (severe threat)
        if is_everyone_role and diff.added_dangerous:
            score = 100.0
            confidence = 0.98
            reasons.append(
                f"@everyone escalated with critical permissions: {', '.join(diff.added_dangerous)}"
            )

        # 2. Quarantine role tampering
        elif is_quarantine_role:
            score = 90.0
            confidence = 0.95
            reasons.append("Quarantine role permissions were tampered with")

        # 3. Standard dangerous role escalation
        elif diff.added_dangerous:
            reasons.append(
                f"Granted dangerous permissions ({', '.join(diff.added_dangerous)}) [max severity: {diff.max_severity}]"
            )
            if "administrator" in diff.added_dangerous:
                score = max(score, 95.0)
                confidence = 0.95

        if score >= 35.0:
            return Evidence(
                detector_name="PermissionGuard",
                score=score,
                confidence=confidence,
                reason="; ".join(reasons),
                metadata={
                    "added_dangerous": diff.added_dangerous,
                    "removed_dangerous": diff.removed_dangerous,
                    "max_severity": diff.max_severity,
                    "is_everyone": is_everyone_role,
                    "is_quarantine": is_quarantine_role
                }
            )

        return None
