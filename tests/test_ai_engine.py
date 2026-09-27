"""Unit tests for the provider-agnostic Lexus AI Engine."""

from __future__ import annotations

import asyncio
import unittest

from services.ai_engine.engine import AIEngine
from services.ai_engine.models import AIProvider, AIRequest, ProviderReply, ToolCall
from services.ai_engine.tools import ToolContext, ToolRegistry, ToolSpec


class FakeProviderManager:
    def __init__(self) -> None:
        self.providers = ["fake:test"]
        self.calls = 0

    @property
    def available(self) -> bool:
        return True

    @property
    def names(self) -> list[str]:
        return self.providers

    async def complete(self, messages, tools, max_output_tokens):
        self.calls += 1
        if self.calls == 1:
            call = ToolCall(
                call_id="call-1",
                name="echo",
                arguments={"value": "hello"},
            )
            return ProviderReply(
                provider=AIProvider.GROQ,
                model="fake",
                assistant_message={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "echo",
                                "arguments": '{"value":"hello"}',
                            },
                        }
                    ],
                },
                tool_calls=[call],
                finish_reason="tool_calls",
            )

        return ProviderReply(
            provider=AIProvider.GROQ,
            model="fake",
            assistant_message={"role": "assistant", "content": "Echo complete."},
            text="Echo complete.",
            finish_reason="stop",
        )

    async def close(self):
        return None


class FakeBot:
    pass


class FakeUser:
    id = 123


class FakeToolContext:
    bot = FakeBot()
    guild = None
    channel = None
    user = FakeUser()


class TestAIEngine(unittest.IsolatedAsyncioTestCase):
    async def test_agent_tool_loop(self):
        registry = ToolRegistry()

        async def echo(_: ToolContext, args: dict):
            return {"echo": args["value"]}

        registry.register(
            ToolSpec(
                name="echo",
                description="Echo test value",
                parameters={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                handler=echo,
            )
        )

        provider = FakeProviderManager()
        engine = AIEngine(provider_manager=provider, tool_registry=registry)

        result = await engine.ask(
            AIRequest(
                user_id=123,
                guild_id=None,
                channel_id=None,
                prompt="hello",
            ),
            FakeToolContext(),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.text, "Echo complete.")
        self.assertEqual(result.tools_used, ["echo"])
        self.assertEqual(provider.calls, 2)

    async def test_unknown_tool_is_not_executed(self):
        registry = ToolRegistry()

        async def never(_: ToolContext, args: dict):
            raise AssertionError("must not execute")

        provider = FakeProviderManager()

        async def first_then_final(*args, **kwargs):
            provider.calls += 1
            if provider.calls == 1:
                call = ToolCall(
                    call_id="bad-1",
                    name="missing",
                    arguments={},
                )
                return ProviderReply(
                    provider=AIProvider.GROQ,
                    model="fake",
                    assistant_message={
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "bad-1",
                                "type": "function",
                                "function": {
                                    "name": "missing",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    },
                    tool_calls=[call],
                )
            return ProviderReply(
                provider=AIProvider.GROQ,
                model="fake",
                assistant_message={"role": "assistant", "content": "Handled."},
                text="Handled.",
            )

        provider.complete = first_then_final

        registry.register(
            ToolSpec(
                name="safe",
                description="Safe test tool",
                parameters={"type": "object", "properties": {}},
                handler=never,
            )
        )

        engine = AIEngine(provider_manager=provider, tool_registry=registry)
        result = await engine.ask(
            AIRequest(user_id=1, guild_id=None, channel_id=None, prompt="test"),
            FakeToolContext(),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.text, "Handled.")
        self.assertEqual(provider.calls, 2)

    async def test_empty_prompt_is_rejected(self):
        engine = AIEngine(provider_manager=FakeProviderManager(), tool_registry=ToolRegistry())
        result = await engine.ask(
            AIRequest(user_id=1, guild_id=None, channel_id=None, prompt="   "),
            FakeToolContext(),
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Prompt is empty.")


if __name__ == "__main__":
    unittest.main()
