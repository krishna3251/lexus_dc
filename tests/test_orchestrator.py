"""Regression tests for the Rukiya-style Lexus orchestration layer."""

from __future__ import annotations

import unittest

from services.ai_engine.behavior import (
    BehaviorAnalyzer,
    BehaviorContext,
    BehaviorSession,
    MoodState,
    UserIntent,
)
from services.ai_engine.models import AIIntent, AIRequest, AIResult
from services.orchestrator import LexusOrchestrator


class FakeEngine:
    def __init__(self) -> None:
        self.calls = []

    @property
    def available(self) -> bool:
        return True

    @property
    def provider_names(self) -> list[str]:
        return ["fake"]

    async def ask(self, request, context):
        self.calls.append((request, context))
        return AIResult(
            success=True,
            text="test response",
            intent=AIIntent.CHAT,
        )

    async def evaluate_decision(self, state, questions):
        return {"ok": True}

    async def reload_providers(self):
        return None

    def health(self):
        return {
            "available": True,
            "providers": self.provider_names,
            "tools": 0,
            "memory_available": True,
            "memory_backend": "fake",
            "memory_size_bytes": 0,
        }

    async def close(self):
        return None


class TestBehaviorAnalyzer(unittest.TestCase):
    def test_first_turn_is_opening(self):
        session = BehaviorSession()
        context = BehaviorAnalyzer.analyze("hey lexus", session, now=100.0)
        self.assertEqual(context.phase.value, "opening")
        self.assertEqual(context.intent, UserIntent.CASUAL_CHAT)
        self.assertEqual(context.mood, MoodState.NEUTRAL)

    def test_playful_chat_allows_sarcasm(self):
        session = BehaviorSession()
        context = BehaviorAnalyzer.analyze("lol bro 😂", session, now=100.0)
        self.assertTrue(context.sarcasm_permitted)
        self.assertEqual(context.mood, MoodState.PLAYFUL)

    def test_distress_disables_sarcasm(self):
        session = BehaviorSession()
        context = BehaviorAnalyzer.analyze(
            "I'm overwhelmed and can't handle this",
            session,
            now=100.0,
        )
        self.assertFalse(context.sarcasm_permitted)
        self.assertLess(context.emotional_safety_level, 7)
        self.assertGreaterEqual(context.crisis_level, 1)


class TestLexusOrchestrator(unittest.IsolatedAsyncioTestCase):
    async def test_behavior_decision_happens_before_generation(self):
        engine = FakeEngine()
        orchestrator = LexusOrchestrator(engine=engine)

        request = AIRequest(
            user_id=10,
            guild_id=20,
            channel_id=30,
            prompt="lol bro 😂",
            max_output_tokens=700,
        )
        result = await orchestrator.ask(request, object())

        self.assertTrue(result.success)
        self.assertEqual(len(engine.calls), 1)
        routed_request, _ = engine.calls[0]
        self.assertIn("BEHAVIORAL CONTEXT", routed_request.system_prompt)
        self.assertIn("Sarcasm: allowed", routed_request.system_prompt)
        self.assertLessEqual(routed_request.max_output_tokens, 320)
        self.assertEqual(orchestrator.active_behavior_sessions, 1)
        await orchestrator.close()

    async def test_behavior_sessions_are_scoped_by_discord_context(self):
        engine = FakeEngine()
        orchestrator = LexusOrchestrator(engine=engine)

        base = AIRequest(
            user_id=10,
            guild_id=20,
            channel_id=30,
            prompt="hello",
        )
        await orchestrator.ask(base, object())
        await orchestrator.ask(
            AIRequest(
                user_id=10,
                guild_id=20,
                channel_id=31,
                prompt="hello again",
            ),
            object(),
        )

        self.assertEqual(orchestrator.active_behavior_sessions, 2)
        await orchestrator.close()

    async def test_empty_prompt_is_delegated_to_engine(self):
        engine = FakeEngine()
        orchestrator = LexusOrchestrator(engine=engine)

        result = await orchestrator.ask(
            AIRequest(user_id=1, guild_id=None, channel_id=None, prompt="   "),
            object(),
        )

        self.assertTrue(result.success)
        self.assertEqual(len(engine.calls), 1)
        self.assertEqual(engine.calls[0][0].prompt, "   ")
        await orchestrator.close()


if __name__ == "__main__":
    unittest.main()
