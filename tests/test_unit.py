"""
Unit tests for core security algorithms:
SlidingWindow, TokenBucket, HeatDecay, PermissionDiff, Dedup, Scoring, Hysteresis.
"""

import time
import unittest
from security.event_tracker import SlidingWindow, TokenBucket, MultiWindowCounter
from security.scoring import DecayingHeat, SecurityStateMachine, calculate_risk
from security.dedup import EventDeduplicator
from security.models import (
    SecurityEvent,
    SecurityState,
    TrustLevel,
    Severity,
    RaidSubState
)
from core.events import SecurityEventType
from core.permissions import calculate_permission_diff


class TestSlidingWindow(unittest.TestCase):
    def test_window_counting_and_expiry(self):
        win = SlidingWindow(window_seconds=2.0, max_size=10)
        t0 = 1000.0
        # Add 3 events at t=1000.0
        self.assertEqual(win.add(t0), 1)
        self.assertEqual(win.add(t0 + 0.5), 2)
        self.assertEqual(win.add(t0 + 1.0), 3)

        # Count at t=1001.5 (all 3 still active)
        self.assertEqual(win.count(t0 + 1.5), 3)

        # Count at t=1002.2 (first event t0 expired because cutoff is 1000.2)
        self.assertEqual(win.count(t0 + 2.2), 2)

        # Count at t=1004.0 (all expired)
        self.assertEqual(win.count(t0 + 4.0), 0)

    def test_window_max_size_bounding(self):
        win = SlidingWindow(window_seconds=10.0, max_size=5)
        for i in range(10):
            win.add(100.0 + i * 0.1)
        # Bounded to max_size 5
        self.assertLessEqual(len(win.events), 5)


class TestTokenBucket(unittest.TestCase):
    def test_burst_and_refill(self):
        # 5 tokens capacity, 2 tokens per second refill
        bucket = TokenBucket(capacity=5.0, refill_rate=2.0)
        # Consume full capacity
        self.assertTrue(bucket.consume(5.0))
        # Now empty
        self.assertFalse(bucket.consume(1.0))

        # Simulate time passage
        bucket.last_refill -= 1.0  # 1 second elapsed -> 2 tokens added
        self.assertTrue(bucket.consume(1.0))
        self.assertTrue(bucket.consume(1.0))
        self.assertFalse(bucket.consume(1.0))


class TestDecayingHeat(unittest.TestCase):
    def test_exponential_decay(self):
        # Half life 2.0 seconds
        heat = DecayingHeat(half_life_seconds=2.0, max_heat=100.0)
        t0 = 100.0
        heat.add_heat(80.0, now=t0)
        self.assertAlmostEqual(heat.get_heat(now=t0), 80.0, places=2)

        # After 1 half-life (2 seconds), heat should be approx 40.0
        h1 = heat.get_heat(now=t0 + 2.0)
        self.assertAlmostEqual(h1, 40.0, delta=1.0)

        # After 2 half-lives (4 seconds), heat should be approx 20.0
        h2 = heat.get_heat(now=t0 + 4.0)
        self.assertAlmostEqual(h2, 20.0, delta=1.0)


class TestPermissionDiff(unittest.TestCase):
    def test_dangerous_permissions_detected(self):
        # Bit 8 = Administrator, Bit 29 = Manage Roles
        before = 0
        after = 8 | (1 << 28)  # Administrator + Manage Roles
        diff = calculate_permission_diff(before, after)

        self.assertIn("administrator", diff.added_dangerous)
        self.assertIn("manage_roles", diff.added_dangerous)
        self.assertEqual(diff.max_severity, 100)
        self.assertGreater(diff.total_risk_score, 80.0)

    def test_harmless_permission_change(self):
        # Embed links (bit 14), Attach files (bit 15)
        before = 1 << 14
        after = (1 << 14) | (1 << 15)
        diff = calculate_permission_diff(before, after)

        self.assertEqual(len(diff.added_dangerous), 0)
        self.assertEqual(diff.max_severity, 0)
        self.assertEqual(diff.total_risk_score, 0.0)


class TestEventDeduplication(unittest.TestCase):
    def test_dedup_bucket(self):
        dedup = EventDeduplicator(bucket_size_seconds=2.0, ttl=10.0)
        evt1 = SecurityEvent(
            guild_id=100,
            actor_id=200,
            target_id=300,
            event_type=SecurityEventType.MESSAGE,
            timestamp=1000.0
        )
        evt2 = SecurityEvent(
            guild_id=100,
            actor_id=200,
            target_id=300,
            event_type=SecurityEventType.MESSAGE,
            timestamp=1000.5  # Same bucket
        )
        evt3 = SecurityEvent(
            guild_id=100,
            actor_id=200,
            target_id=300,
            event_type=SecurityEventType.MESSAGE,
            timestamp=1005.0  # Different bucket
        )

        self.assertFalse(dedup.is_duplicate(evt1))
        dedup.record(evt1)
        self.assertTrue(dedup.is_duplicate(evt2))
        self.assertFalse(dedup.is_duplicate(evt3))


class TestHysteresisStateMachine(unittest.TestCase):
    def test_raid_state_transitions_and_hysteresis(self):
        sm = SecurityStateMachine(guild_id=123)
        sm.min_state_dwell_time = 0.0  # Disable dwell time for test
        self.assertEqual(sm.current_state, SecurityState.NORMAL)

        # Exceed enter threshold (80.0)
        state, changed = sm.update_state(guild_heat=50.0, raid_heat=85.0, structural_heat=0.0)
        self.assertEqual(state, SecurityState.RAID)
        self.assertTrue(changed)

        # Dropping to 75.0 should STILL stay in RAID (hysteresis: exit is 40.0)
        state, changed = sm.update_state(guild_heat=40.0, raid_heat=75.0, structural_heat=0.0)
        self.assertEqual(state, SecurityState.RAID)
        self.assertFalse(changed)

        # Dropping to 35.0 (below exit threshold 40.0) should drop out of RAID to ELEVATED
        state, changed = sm.update_state(guild_heat=30.0, raid_heat=35.0, structural_heat=0.0)
        self.assertEqual(state, SecurityState.ELEVATED)
        self.assertTrue(changed)

    def test_panic_transition_to_recovery(self):
        sm = SecurityStateMachine(guild_id=123)
        sm.min_state_dwell_time = 0.0
        # Trigger panic with structural heat >= 85
        state, changed = sm.update_state(guild_heat=50.0, raid_heat=0.0, structural_heat=90.0)
        self.assertEqual(state, SecurityState.PANIC)
        self.assertTrue(changed)

        # Dropping structural heat below exit threshold transitions to RECOVERY
        state, changed = sm.update_state(guild_heat=20.0, raid_heat=0.0, structural_heat=15.0)
        self.assertEqual(state, SecurityState.RECOVERY)
        self.assertTrue(changed)


class TestRiskCalculation(unittest.TestCase):
    def test_trust_multipliers(self):
        # Owner should have very low risk for same base score
        owner_risk, owner_sev = calculate_risk(base_score=60.0, confidence=0.9, trust=TrustLevel.OWNER)
        # Member should have higher risk
        member_risk, member_sev = calculate_risk(base_score=60.0, confidence=0.9, trust=TrustLevel.MEMBER)
        # Suspicious should have even higher risk
        susp_risk, susp_sev = calculate_risk(base_score=60.0, confidence=0.9, trust=TrustLevel.SUSPICIOUS)

        self.assertLess(owner_risk, member_risk)
        self.assertLess(member_risk, susp_risk)
        self.assertEqual(owner_sev, Severity.INFO)


if __name__ == "__main__":
    unittest.main()
