"""
Tests for Anti-Nuke, Permission Guard, Bot Guard, and Webhook Guard.
Validates structural threat detection, cross-action risk scoring, and privilege escalations.
"""

import time
import unittest
from security.anti_nuke import AntiNukeDetector
from security.permission_guard import PermissionGuard
from security.bot_guard import BotGuard
from security.webhook_guard import WebhookGuard
from security.models import SecurityEvent, TrustLevel, GuildSecurityConfig
from core.events import SecurityEventType


class TestAntiNukeAndGuards(unittest.TestCase):
    def setUp(self):
        self.anti_nuke = AntiNukeDetector()
        self.perm_guard = PermissionGuard()
        self.bot_guard = BotGuard()
        self.wh_guard = WebhookGuard()
        self.guild_id = 77777
        self.actor_id = 88888
        self.config = GuildSecurityConfig(guild_id=self.guild_id, trusted_bots=[99999])

    def test_single_channel_deletion_not_flagged(self):
        # A single channel deletion by an admin is not a nuke
        evt = SecurityEvent(
            guild_id=self.guild_id,
            actor_id=self.actor_id,
            target_id=1001,
            event_type=SecurityEventType.CHANNEL_DELETE,
            timestamp=time.time()
        )
        ev = self.anti_nuke.evaluate(evt)
        self.assertIsNone(ev, "Single channel deletion should not trigger false positive")

    def test_channel_deletion_burst(self):
        # Rapid channel deletion burst
        flagged = None
        for cid in (1001, 1002, 1003):
            evt = SecurityEvent(
                guild_id=self.guild_id,
                actor_id=self.actor_id,
                target_id=cid,
                event_type=SecurityEventType.CHANNEL_DELETE,
                timestamp=time.time()
            )
            ev = self.anti_nuke.evaluate(evt)
            if ev:
                flagged = ev

        self.assertIsNotNone(flagged)
        self.assertIn("structural actions", flagged.reason.lower())
        self.assertGreaterEqual(flagged.score, 70.0)

    def test_multi_vector_attack_cross_action_score(self):
        # Actor performs channel delete, role delete, and webhook create
        detector = AntiNukeDetector()
        now = time.time()
        # 1. Channel delete
        detector.evaluate(SecurityEvent(
            guild_id=self.guild_id, actor_id=self.actor_id, target_id=1,
            event_type=SecurityEventType.CHANNEL_DELETE, timestamp=now
        ))
        # 2. Role delete
        detector.evaluate(SecurityEvent(
            guild_id=self.guild_id, actor_id=self.actor_id, target_id=2,
            event_type=SecurityEventType.ROLE_DELETE, timestamp=now
        ))
        # 3. Webhook create
        ev = detector.evaluate(SecurityEvent(
            guild_id=self.guild_id, actor_id=self.actor_id, target_id=3,
            event_type=SecurityEventType.WEBHOOK_CREATE, timestamp=now
        ))
        self.assertIsNotNone(ev)
        self.assertIn("multi-vector", ev.reason.lower())
        self.assertGreaterEqual(ev.score, 90.0)

    def test_permission_guard_admin_escalation(self):
        evt = SecurityEvent(
            guild_id=self.guild_id,
            actor_id=self.actor_id,
            target_id=501,
            event_type=SecurityEventType.ROLE_UPDATE,
            timestamp=time.time()
        )
        # Grant Administrator (bit 8)
        ev = self.perm_guard.evaluate_role_update(evt, before_permissions=0, after_permissions=8)
        self.assertIsNotNone(ev)
        self.assertIn("administrator", ev.reason.lower())
        self.assertGreaterEqual(ev.score, 95.0)

    def test_permission_guard_everyone_escalation(self):
        evt = SecurityEvent(
            guild_id=self.guild_id,
            actor_id=self.actor_id,
            target_id=500,  # default @everyone role ID
            event_type=SecurityEventType.ROLE_UPDATE,
            timestamp=time.time()
        )
        # Grant Manage Guild (bit 5) to @everyone
        ev = self.perm_guard.evaluate_role_update(evt, before_permissions=0, after_permissions=(1 << 5), is_everyone_role=True)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.score, 100.0)
        self.assertIn("@everyone", ev.reason)

    def test_bot_guard_unauthorized_admin_bot(self):
        evt = SecurityEvent(
            guild_id=self.guild_id,
            actor_id=self.actor_id,
            target_id=6001,
            event_type=SecurityEventType.BOT_ADD,
            timestamp=time.time()
        )
        ev = self.bot_guard.evaluate(
            evt,
            bot_id=6001,
            installer_id=self.actor_id,
            bot_permissions_val=8,  # Admin
            installer_trust=TrustLevel.MEMBER,
            config=self.config
        )
        self.assertIsNotNone(ev)
        self.assertIn("administrator", ev.reason.lower())

    def test_bot_guard_trusted_bot_allowed(self):
        evt = SecurityEvent(
            guild_id=self.guild_id,
            actor_id=self.actor_id,
            target_id=99999,  # Trusted bot in config
            event_type=SecurityEventType.BOT_ADD,
            timestamp=time.time()
        )
        ev = self.bot_guard.evaluate(
            evt,
            bot_id=99999,
            installer_id=self.actor_id,
            bot_permissions_val=8,
            installer_trust=TrustLevel.MEMBER,
            config=self.config
        )
        self.assertIsNone(ev, "Explicitly trusted bot should be allowed without alarm")

    def test_webhook_guard_burst(self):
        flagged = None
        for i in range(3):
            evt = SecurityEvent(
                guild_id=self.guild_id,
                actor_id=self.actor_id,
                channel_id=701,
                event_type=SecurityEventType.WEBHOOK_CREATE,
                timestamp=time.time()
            )
            ev = self.wh_guard.evaluate(evt, actor_trust=TrustLevel.MEMBER, channel_id=701)
            if ev:
                flagged = ev

        self.assertIsNotNone(flagged)
        self.assertIn("webhook", flagged.reason.lower())


if __name__ == "__main__":
    unittest.main()
