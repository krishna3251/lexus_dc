"""
Comprehensive tests for RaidDetector and JoinGate:
Join velocity, distributed multi-actor pattern correlation,
account age scoring, and state machine transitions.
"""

import time
import unittest
from security.raid import RaidDetector
from security.join_gate import JoinGate
from security.models import SecurityEvent, SecurityState, TrustLevel
from core.events import SecurityEventType


class TestRaidAndJoinGate(unittest.TestCase):
    def setUp(self):
        self.raid_detector = RaidDetector()
        self.join_gate = JoinGate()
        self.guild_id = 55555

    def test_normal_join_rate(self):
        # 2 joins spaced out
        for i in range(2):
            evt = SecurityEvent(
                guild_id=self.guild_id,
                actor_id=1000 + i,
                event_type=SecurityEventType.MEMBER_JOIN,
                timestamp=time.time()
            )
            ev = self.raid_detector.evaluate_join(evt)
            self.assertIsNone(ev, "Normal join should not trigger raid alarm")

    def test_rapid_join_flood(self):
        # 12 joins in rapid succession
        flagged = None
        for i in range(12):
            evt = SecurityEvent(
                guild_id=self.guild_id,
                actor_id=2000 + i,
                event_type=SecurityEventType.MEMBER_JOIN,
                timestamp=time.time()
            )
            ev = self.raid_detector.evaluate_join(evt)
            if ev:
                flagged = ev

        self.assertIsNotNone(flagged)
        self.assertIn("join flood", flagged.reason.lower())
        self.assertGreaterEqual(flagged.score, 80.0)

    def test_distributed_spam_raid(self):
        # 5 distinct accounts post the exact same phishing domain
        flagged = None
        domain = "http://steamcommunity-gift-auth.ru/login"
        for i in range(5):
            evt = SecurityEvent(
                guild_id=self.guild_id,
                actor_id=3000 + i,
                channel_id=401,
                event_type=SecurityEventType.MESSAGE,
                timestamp=time.time(),
                metadata={"content": f"Claim your gift now: {domain}"}
            )
            ev = self.raid_detector.evaluate_message_pattern(evt, "", detected_domain=domain)
            if ev:
                flagged = ev

        self.assertIsNotNone(flagged)
        self.assertIn("distributed raid signature", flagged.reason.lower())
        self.assertGreaterEqual(flagged.score, 60.0)

    def test_join_gate_normal_user(self):
        # 1 year old account, normal server state
        evt = SecurityEvent(
            guild_id=self.guild_id,
            actor_id=4001,
            event_type=SecurityEventType.MEMBER_JOIN,
            timestamp=time.time()
        )
        created_at = time.time() - (365 * 86400)
        trust, ev = self.join_gate.evaluate(evt, SecurityState.NORMAL, account_created_at=created_at, has_default_avatar=False)
        self.assertEqual(trust, TrustLevel.NEW_MEMBER)
        self.assertIsNone(ev)

    def test_join_gate_raid_state_and_young_account(self):
        # Account created 10 minutes ago, joining during active RAID
        evt = SecurityEvent(
            guild_id=self.guild_id,
            actor_id=4002,
            event_type=SecurityEventType.MEMBER_JOIN,
            timestamp=time.time()
        )
        created_at = time.time() - 600  # 10 minutes old
        trust, ev = self.join_gate.evaluate(evt, SecurityState.RAID, account_created_at=created_at, has_default_avatar=True)
        self.assertEqual(trust, TrustLevel.SUSPICIOUS)
        self.assertIsNotNone(ev)
        self.assertIn("young account", ev.reason.lower())
        self.assertIn("raid", ev.reason.lower())


if __name__ == "__main__":
    unittest.main()
