"""Regression tests for security attribution and containment policy."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import discord

from core.events import SecurityEventType
from security.audit import AuditLogCorrelator
from security.models import SecurityActionType, SecurityEvent, Severity, TrustLevel
from security.permission_guard import PermissionGuard
from security.policies import PolicyEngine
from security.models import GuildSecurityConfig, SecurityProfile, SecurityState


class TestSecurityAttribution(unittest.TestCase):
    def _config(self) -> GuildSecurityConfig:
        return GuildSecurityConfig(
            guild_id=1,
            security_mode="enforce",
            profile=SecurityProfile.STANDARD,
        )

    def test_unattributed_critical_structural_event_cannot_quarantine_or_lockdown(self):
        actions = PolicyEngine.evaluate(
            risk_score=100.0,
            severity=Severity.CRITICAL,
            confidence=0.98,
            guild_state=SecurityState.PANIC,
            actor_trust=TrustLevel.UNKNOWN,
            is_structural=True,
            config=self._config(),
        )
        self.assertEqual(actions, [SecurityActionType.LOG, SecurityActionType.ALERT])

    def test_attributed_critical_structural_event_can_contain(self):
        actions = PolicyEngine.evaluate(
            risk_score=100.0,
            severity=Severity.CRITICAL,
            confidence=0.98,
            guild_state=SecurityState.PANIC,
            actor_trust=TrustLevel.MEMBER,
            is_structural=True,
            config=self._config(),
        )
        self.assertEqual(
            actions,
            [
                SecurityActionType.LOG,
                SecurityActionType.ALERT,
                SecurityActionType.QUARANTINE,
                SecurityActionType.LOCKDOWN,
            ],
        )

    def test_unattributed_everyone_admin_change_is_downgraded(self):
        event = SecurityEvent(
            guild_id=1,
            actor_id=None,
            target_id=2,
            event_type=SecurityEventType.ROLE_UPDATE,
            metadata={"audit": {"attribution": "unavailable"}},
        )
        guard = PermissionGuard()

        before = discord.Permissions.none()
        after = discord.Permissions(administrator=True)

        evidence = guard.evaluate_role_update(
            event,
            before.value,
            after.value,
            is_everyone_role=True,
        )

        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.score, 100.0)
        self.assertEqual(evidence.confidence, 0.45)
        self.assertIn("Audit actor attribution unavailable", evidence.reason)


class _FakeAuditGuild:
    def __init__(self, entries):
        self.entries = entries
        perms = MagicMock()
        perms.view_audit_log = True
        self.me = MagicMock()
        self.me.guild_permissions = perms
        self.id = 123

    def audit_logs(self, **kwargs):
        async def iterator():
            for entry in self.entries:
                yield entry
        return iterator()


class _FakeAuditEntry:
    def __init__(self, target_id: int, actor_id: int):
        self.id = "audit-1"
        self.target = MagicMock(id=target_id)
        self.user = MagicMock(id=actor_id)
        self.action = discord.AuditLogAction.role_update
        self.reason = "test"
        self.created_at = discord.utils.utcnow()


class TestAuditCorrelation(unittest.IsolatedAsyncioTestCase):
    async def test_correlation_requires_matching_target(self):
        correlator = AuditLogCorrelator(
            max_entries=10,
            max_age_seconds=15.0,
            retry_delays=(0.0,),
        )
        guild = _FakeAuditGuild([_FakeAuditEntry(target_id=999, actor_id=42)])

        result = await correlator.find_actor_for_event(
            guild,
            discord.AuditLogAction.role_update,
            target_id=123,
        )

        self.assertIsNone(result)

    async def test_correlation_returns_matching_actor(self):
        correlator = AuditLogCorrelator(
            max_entries=10,
            max_age_seconds=15.0,
            retry_delays=(0.0,),
        )
        guild = _FakeAuditGuild([_FakeAuditEntry(target_id=123, actor_id=42)])

        result = await correlator.find_actor_for_event(
            guild,
            discord.AuditLogAction.role_update,
            target_id=123,
        )

        self.assertIsNotNone(result)
        assert result is not None
        actor_id, metadata = result
        self.assertEqual(actor_id, 42)
        self.assertEqual(metadata["attribution"], "audit_log")
        self.assertEqual(metadata["target_id"], 123)


if __name__ == "__main__":
    unittest.main()
