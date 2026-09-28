"""Unit tests for the Lexus Jev decision layer."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services.ai_engine.jev import JevDecisionService


class FakeResponse:
    def __init__(self, status: int, body: dict):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self, content_type=None):
        return self._body


class FakeSession:
    response_body = {
        "answers": {
            "discord_tools": {
                "type": "boolean",
                "probability": 0.03,
            }
        }
    }
    calls = 0
    last_kwargs = None

    def __init__(self, *args, **kwargs):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def post(self, *args, **kwargs):
        type(self).calls += 1
        type(self).last_kwargs = {
            "args": args,
            "kwargs": kwargs,
        }
        return FakeResponse(200, type(self).response_body)


class TestJevDecisionService(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakeSession.calls = 0
        FakeSession.last_kwargs = None

    def test_parse_boolean_and_choice_answers(self):
        body = {
            "answers": {
                "flagged": {
                    "type": "boolean",
                    "probability": 0.92,
                },
                "route": {
                    "type": "choice",
                    "choice": "review",
                    "probabilities": {
                        "allow": 0.08,
                        "review": 0.92,
                    },
                },
            }
        }
        answers = JevDecisionService._parse_answers(body)

        self.assertAlmostEqual(answers["flagged"].probability, 0.92)
        self.assertEqual(answers["route"].value, "review")
        self.assertAlmostEqual(answers["route"].probability, 0.92)

    async def test_evaluate_uses_gateway_key_and_model(self):
        with patch.dict(
            os.environ,
            {
                "AI_GATEWAY_API_KEY": "vck_test",
                "JEV_CACHE_TTL_SECONDS": "30",
            },
            clear=False,
        ), patch(
            "services.ai_engine.jev.aiohttp.ClientSession",
            FakeSession,
        ):
            service = JevDecisionService()
            result = await service.evaluate(
                state={"intent": "help", "request": "what commands exist?"},
                questions={
                    "discord_tools": {
                        "type": "boolean",
                        "instructions": "Does this require live Discord tools?",
                    }
                },
            )

            self.assertTrue(result.success)
            self.assertAlmostEqual(
                result.answers["discord_tools"].probability,
                0.03,
            )
            request = FakeSession.last_kwargs
            self.assertTrue(request["kwargs"]["headers"]["Authorization"].startswith("Bearer vck_"))
            self.assertEqual(
                request["kwargs"]["json"]["model"],
                "typesafe-ai/jev",
            )

            cached = await service.evaluate(
                state={"intent": "help", "request": "what commands exist?"},
                questions={
                    "discord_tools": {
                        "type": "boolean",
                        "instructions": "Does this require live Discord tools?",
                    }
                },
            )
            self.assertTrue(cached.cached)
            self.assertEqual(FakeSession.calls, 1)
            await service.close()

    async def test_tool_gate_is_conservative(self):
        with patch.dict(
            os.environ,
            {"AI_GATEWAY_API_KEY": "vck_test"},
            clear=False,
        ), patch(
            "services.ai_engine.jev.aiohttp.ClientSession",
            FakeSession,
        ):
            service = JevDecisionService()
            self.assertFalse(
                await service.should_use_discord_tools(
                    "what command list do you have?",
                    "help",
                )
            )
            await service.close()

    async def test_no_key_is_a_safe_noop(self):
        with patch.dict(
            os.environ,
            {"AI_GATEWAY_API_KEY": ""},
            clear=False,
        ):
            service = JevDecisionService()
            result = await service.evaluate(
                state="hello",
                questions={
                    "x": {
                        "type": "boolean",
                        "instructions": "Is this a test?",
                    }
                },
            )
            self.assertFalse(result.success)
            self.assertEqual(result.error, "jev_not_configured")
            await service.close()


if __name__ == "__main__":
    unittest.main()
