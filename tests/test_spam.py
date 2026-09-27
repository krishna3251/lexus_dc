"""
Comprehensive tests for SpamDetector:
Normal conversation, burst spam, exact repeats, near duplicates,
mention floods, invite spam, link spam, attachment floods, channel hopping.
"""

import time
import unittest
from security.spam import SpamDetector, normalize_content, jaccard_similarity, text_signature
from security.models import SecurityEvent
from core.events import SecurityEventType


class TestSpamDetector(unittest.TestCase):
    def setUp(self):
        self.detector = SpamDetector()
        self.guild_id = 12345
        self.user_id = 9999

    def _make_msg_event(self, content: str, channel_id: int = 101, mentions: int = 0, attachments: int = 0, everyone: bool = False) -> SecurityEvent:
        return SecurityEvent(
            guild_id=self.guild_id,
            actor_id=self.user_id,
            channel_id=channel_id,
            event_type=SecurityEventType.MESSAGE,
            timestamp=time.time(),
            metadata={
                "content": content,
                "mentions_count": mentions,
                "attachments_count": attachments,
                "mention_everyone": everyone
            }
        )

    def test_normalization_and_similarity(self):
        text1 = "BUY FREE NITRO NOW!!!!!"
        text2 = "buy free nitro now!!"
        norm1 = normalize_content(text1)
        norm2 = normalize_content(text2)
        self.assertEqual(norm1, "buy free nitro now")
        self.assertEqual(norm2, "buy free nitro now")

        sig1 = text_signature(norm1)
        sig2 = text_signature(norm2)
        self.assertEqual(jaccard_similarity(sig1, sig2), 1.0)

    def test_normal_conversation_not_flagged(self):
        # Normal chat messages spaced out
        for text in ["Hey everyone!", "How's your day going?", "Working on a python project.", "Cool!"]:
            ev = self.detector.evaluate(self._make_msg_event(text))
            self.assertIsNone(ev, f"Normal message falsely flagged: {text}")

    def test_fast_message_burst(self):
        # 8 messages sent rapidly
        flagged = None
        for i in range(8):
            ev = self.detector.evaluate(self._make_msg_event(f"Fast message #{i}"))
            if ev:
                flagged = ev

        self.assertIsNotNone(flagged)
        self.assertIn("Fast message burst", flagged.reason)
        self.assertGreaterEqual(flagged.score, 50.0)

    def test_exact_repeated_messages(self):
        msg = "Get free steam keys at example.com"
        flagged = None
        for _ in range(4):
            ev = self.detector.evaluate(self._make_msg_event(msg))
            if ev:
                flagged = ev

        self.assertIsNotNone(flagged)
        self.assertIn("Repeated", flagged.reason)

    def test_near_duplicate_messages(self):
        # 1. Exact repeat normalized
        variations = [
            "Join my brand new server today guys",
            "join my brand new server today guys!",
            "JOIN MY BRAND NEW SERVER TODAY GUYS!!",
        ]
        flagged = None
        for v in variations:
            ev = self.detector.evaluate(self._make_msg_event(v))
            if ev:
                flagged = ev

        self.assertIsNotNone(flagged)
        self.assertTrue("repeated" in flagged.reason.lower() or "duplicate" in flagged.reason.lower())

        # 2. Near-duplicate with differing token (triggers Jaccard similarity)
        detector2 = SpamDetector()
        detector2.evaluate(self._make_msg_event("Buy cheap discord nitro subscriptions right now"))
        ev2 = detector2.evaluate(self._make_msg_event("Buy cheap discord nitro memberships right now"))
        self.assertIsNotNone(ev2)
        self.assertIn("near-duplicate", ev2.reason.lower())

    def test_mention_flood(self):
        ev = self.detector.evaluate(self._make_msg_event("Check this out", mentions=12))
        self.assertIsNotNone(ev)
        self.assertIn("mention flood", flagged_reason := ev.reason.lower())

    def test_everyone_mention(self):
        ev = self.detector.evaluate(self._make_msg_event("@everyone check this", everyone=True))
        self.assertIsNotNone(ev)
        self.assertIn("@everyone", ev.reason)

    def test_invite_link_detection(self):
        ev = self.detector.evaluate(self._make_msg_event("Join here discord.gg/superpromo123 now"))
        self.assertIsNotNone(ev)
        self.assertIn("invite", ev.reason.lower())

    def test_link_burst(self):
        text = "Visit http://a.com http://b.com http://c.com http://d.com"
        ev = self.detector.evaluate(self._make_msg_event(text))
        self.assertIsNotNone(ev)
        self.assertIn("link burst", ev.reason.lower())

    def test_attachment_flood(self):
        ev = self.detector.evaluate(self._make_msg_event("", attachments=6))
        self.assertIsNotNone(ev)
        self.assertIn("attachment burst", ev.reason.lower())

    def test_channel_hopping(self):
        flagged = None
        # Hop across 4 different channels rapidly
        for ch_id in (201, 202, 203, 204):
            ev = self.detector.evaluate(self._make_msg_event("Spam in channel", channel_id=ch_id))
            if ev:
                flagged = ev

        self.assertIsNotNone(flagged)
        self.assertIn("hopping", flagged.reason.lower())


if __name__ == "__main__":
    unittest.main()
