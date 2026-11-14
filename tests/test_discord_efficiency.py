"""Regression coverage for shared spending and Discord conversation delivery."""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
import discord
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from cogs.ai_engine import AIEngineCog
from cogs.chat_lex import LexusBot
from cogs.coder_lex import APIException, Config, LLMService, OutputHandler
from cogs.help import SarcasticHelpCog
from services.ai_engine.brain import ResponseStyle
from services.ai_engine.config import BrainConfig
from services.ai_engine.engine import AIEngine
from services.ai_engine.legacy import reserve_legacy_call
from services.ai_engine.models import AIProvider, AIRequest, AIResult, ProviderReply
from services.ai_engine.providers import CompatibleProvider, ProviderError, ProviderManager
from services.ai_engine.research import ResearchResult
from services.ai_engine.tools import ToolContext
from services.discord_output import discord_length, prepare_reply, send_reply, split_reply


def reply(model="test"):
    return ProviderReply(AIProvider.GROQ, model, {"role": "assistant", "content": "All good."},
                         "All good.", input_tokens=120, output_tokens=20, cached_input_tokens=40)


class DeliveryTests(unittest.TestCase):
    def test_prose_splits_on_paragraphs_without_changing_words(self):
        text = "First paragraph. " * 70 + "\n\n" + "Second paragraph. " * 80
        parts, attachment = prepare_reply(text)
        self.assertIsNone(attachment)
        self.assertGreater(len(parts), 1)
        self.assertEqual(" ".join(" ".join(parts).split()), " ".join(text.split()))
        self.assertTrue(all(discord_length(p) <= 1900 for p in parts))

    def test_emoji_and_unbroken_text_fit_discord_limit(self):
        text = "😀" * 2500
        parts = split_reply(text)
        self.assertEqual("".join(parts), text)
        self.assertTrue(all(discord_length(p) <= 1900 for p in parts))

    def test_long_code_is_preserved_byte_for_byte_in_attachment(self):
        text = "Try this:\n```python\n" + "print('hello')\n" * 200 + "```"
        parts, attachment = prepare_reply(text)
        self.assertEqual(len(parts), 1)
        self.assertEqual(attachment.fp.read().decode(), text)
        attachment.close()

    def test_current_request_overrides_saved_brief_style(self):
        self.assertEqual(ResponseStyle.choose("explain in detail", "concise").name, "helpful")
        self.assertEqual(ResponseStyle.choose("debug Python", "casual").name, "technical")
        self.assertEqual(ResponseStyle.choose("short answer please", "technical").name, "concise")
        self.assertEqual(ResponseStyle.choose("hello", "friendly").name, "friendly")


class EfficiencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "AI_SQLITE_PATH": str(Path(self.tmp.name) / "brain.sqlite3"),
            "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "NVIDIA_API_KEY": "",
            "OPENROUTER_API_KEY": "", "AI_GATEWAY_API_KEY": "", "AI_LOCAL_ENABLED": "false",
        })
        self.env.start()
        self.manager = ProviderManager(BrainConfig(provider_retries=0, external_call_limit=8))
        self.engine = AIEngine(provider_manager=self.manager)
        self.bot = SimpleNamespace(ai_engine=self.engine, is_ready=lambda: True, commands=[])

    async def asyncTearDown(self):
        await self.engine.close()
        self.env.stop()
        self.tmp.cleanup()

    def provider(self, model):
        return SimpleNamespace(provider=AIProvider.GROQ, model=model,
                               complete=AsyncMock(return_value=reply(model)), close=AsyncMock())

    async def test_only_casual_tool_free_requests_use_economy_model(self):
        primary, economy = self.provider("primary"), self.provider("economy")
        self.manager.providers = [primary]
        self.manager.chat_provider = economy
        context = ToolContext(self.bot, None, SimpleNamespace(id=3), SimpleNamespace(id=1))
        casual = await self.engine.ask(AIRequest(1, None, 3, "hello there"), context)
        self.assertEqual(casual.model, "economy")
        primary.complete.assert_not_awaited()
        technical = await self.engine.ask(AIRequest(1, None, 3, "debug Python async code"), context)
        self.assertEqual(technical.model, "primary")
        economy.complete.assert_awaited_once()
        await self.manager.complete([], [{"type": "function"}], 100, prefer_economy=True)
        self.assertEqual(primary.complete.await_count, 2)
        self.assertEqual(self.manager.metrics()["token_usage"][0]["input_tokens"], 120)

    async def test_economy_failure_falls_back_to_primary(self):
        primary, economy = self.provider("primary"), self.provider("economy")
        economy.complete.side_effect = ProviderError("404")
        self.manager.providers, self.manager.chat_provider = [primary], economy
        result = await self.manager.complete([], [], 100, prefer_economy=True)
        self.assertEqual(result.model, "primary")
        self.assertEqual(self.manager.calls, 2)

    async def test_legacy_and_brain_use_the_same_attempt_budget(self):
        self.manager.config = BrainConfig(external_call_limit=1, provider_retries=0)
        primary = self.provider("primary")
        self.manager.providers = [primary]
        self.assertTrue(await reserve_legacy_call(self.bot, 1, None))
        with self.assertRaises(ProviderError):
            await self.manager.complete([], [], 100)
        primary.complete.assert_not_awaited()
        self.assertFalse(await reserve_legacy_call(self.bot, 1, None))

    async def test_attachment_permission_failure_still_delivers_text_without_pings(self):
        forbidden = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"),
                                      {"code": 50013, "message": "Missing permissions"})
        calls = []
        async def send(text, **kwargs):
            calls.append((text, kwargs))
            if "file" in kwargs:
                raise forbidden
            return SimpleNamespace(id=len(calls))
        text = "```python\n" + "print('hello')\n" * 200 + "```"
        sent = await send_reply(send, text)
        self.assertGreater(len(sent), 1)
        self.assertEqual(" ".join(" ".join(item[0] for item in calls[1:]).split()), " ".join(text.split()))
        self.assertTrue(all(item[1]["allowed_mentions"].to_dict()["parse"] == [] for item in calls))
        self.assertTrue(all(discord_length(item[0]) <= 1900 for item in calls))

    async def test_missing_usage_is_reported_as_unknown_and_metrics_stay_bounded(self):
        self.manager.record_usage("nvidia", "test", None)
        row = self.manager.metrics()["token_usage"][0]
        self.assertEqual(row["responses_without_usage"], 1)
        self.assertNotIn("input_tokens", row)
        for index in range(100):
            self.manager.record_usage("test", str(index), {"prompt_tokens": 1})
        self.assertLessEqual(len(self.manager.metrics()["token_usage"]), 32)

    async def test_legacy_privacy_optout_blocks_coder_before_http(self):
        await self.engine.memory.set_preferences(1, None, history_enabled=False, external_allowed=False)
        service = LLMService(Config("test-placeholder"), self.bot)
        with self.assertRaises(APIException):
            await service.call("code", "print('hi')", user_id=1)
        self.assertIsNone(service.session)
        self.assertEqual(self.manager.calls, 0)
        self.assertFalse(await reserve_legacy_call(SimpleNamespace(), 1, None))
        self.assertFalse(await reserve_legacy_call(self.bot, None, None))

    async def test_privacy_failure_fails_closed(self):
        self.engine.memory.preferences = AsyncMock(return_value={"external_allowed": False})
        self.assertFalse(await reserve_legacy_call(self.bot, 1, None))
        self.assertEqual(self.manager.calls, 0)

    async def test_reload_keeps_budget_and_usage(self):
        self.manager.reserve_external()
        self.manager.record_usage("groq", "test", {"prompt_tokens": 11, "completion_tokens": 7})
        await self.engine.reload_providers()
        metrics = self.engine.providers.metrics()
        self.assertEqual(metrics["hourly_calls_used"], 1)
        self.assertEqual(metrics["token_usage"][0]["input_tokens"], 11)

    async def test_reload_refuses_to_interrupt_active_request(self):
        async with self.engine.capacity.acquire((1, None, 3)):
            with self.assertRaises(ProviderError):
                await self.engine.reload_providers()
        self.assertIs(self.engine.providers, self.manager)

    async def test_coder_output_never_generates_more_code(self):
        service = SimpleNamespace(call=AsyncMock(side_effect=AssertionError("No generation while displaying")))
        output = OutputHandler(Config(""), service)
        destination = SimpleNamespace(send=AsyncMock())
        await output.send_code(destination, "x = 1\n" * 1000, auto_continue=True)
        service.call.assert_not_awaited()
        self.assertGreater(destination.send.await_count, 1)
        self.assertEqual(LLMService(Config(""), self.bot)._build_payload("s", "u")["max_tokens"], 2048)

    async def test_exact_command_help_is_free_and_does_not_need_ai(self):
        command = SimpleNamespace(qualified_name="purge", signature="[limit]", help="Remove recent messages.", hidden=False)
        self.bot.get_command = lambda name: command if name == "purge" else None
        help_cog = SarcasticHelpCog(self.bot)
        text = await help_cog._get_ai_response("purge", user_id=1)
        self.assertIn("Remove recent messages", text)
        self.assertEqual(self.manager.calls, 0)

    async def test_research_gets_style_and_output_policy(self):
        self.manager.providers = [self.provider("primary")]
        self.engine.research.research = AsyncMock(return_value=ResearchResult(True, answer="A current fact.", provider="groq"))
        await self.engine.memory.set_preferences(1, None, history_enabled=False, external_allowed=True, style="concise")
        context = ToolContext(self.bot, None, SimpleNamespace(id=3), SimpleNamespace(id=1))
        result = await self.engine.ask(AIRequest(1, None, 3, "latest gaming news"), context)
        self.assertTrue(result.success)
        self.assertIn("shortest", self.engine.research.research.call_args.kwargs["style_instruction"])
        self.assertEqual(self.engine.research.research.call_args.kwargs["max_output_tokens"], 2400)

    async def test_provider_reads_reported_usage_without_requiring_it(self):
        provider = CompatibleProvider(AIProvider.GROQ, "placeholder", "https://example.com/v1", "test")
        message = SimpleNamespace(content="Hi", tool_calls=[])
        response = SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                                   usage=SimpleNamespace(prompt_tokens=42, completion_tokens=5,
                                                         prompt_tokens_details=SimpleNamespace(cached_tokens=20)))
        create = AsyncMock(return_value=response)
        provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=AsyncMock())
        parsed = await provider.complete([], [], 100)
        self.assertEqual((parsed.input_tokens, parsed.output_tokens, parsed.cached_input_tokens), (42, 5, 20))
        del response.usage
        self.assertIsNone((await provider.complete([], [], 100)).input_tokens)
        await provider.close()

    async def test_wake_names_have_one_owner_even_in_legacy_ai_channel(self):
        channel = SimpleNamespace(id=3, send=AsyncMock(return_value=SimpleNamespace(id=9)), typing=MagicMock())
        author, guild = SimpleNamespace(id=1, bot=False), SimpleNamespace(id=2)
        bot = SimpleNamespace(user=SimpleNamespace(id=99), get_context=AsyncMock(return_value=SimpleNamespace(valid=False)))
        cog = AIEngineCog(bot)
        bot.ai_engine = cog.engine
        bot.get_cog = lambda name: cog if name == "AI Engine" else None
        bot.get_prefix = AsyncMock(return_value=["lx "])
        cog._run = AsyncMock(return_value="hey")
        cog.engine.memory.claim_message = AsyncMock(return_value=True)
        legacy = LexusBot(bot)
        legacy.ai_channels = {3}
        legacy.handle_intelligent_conversation = AsyncMock()
        try:
            for index, text in enumerate(("Lxeus hello", "hey Lexiya hello", "LEX hello")):
                message = SimpleNamespace(id=100+index, author=author, guild=guild, channel=channel,
                                          content=text, mentions=[], reference=None)
                await asyncio.gather(legacy.on_message(message), cog.on_message(message))
            self.assertEqual(cog._run.await_count, 3)
            legacy.handle_intelligent_conversation.assert_not_awaited()
        finally:
            await cog.engine.close()

    async def test_legacy_channel_chat_delegates_to_scoped_brain(self):
        self.engine.ask = AsyncMock(return_value=AIResult(True, "A natural reply."))
        legacy = LexusBot(self.bot)
        message = SimpleNamespace(author=SimpleNamespace(id=1), guild=SimpleNamespace(id=2), channel=SimpleNamespace(id=3))
        text = await legacy.chat_with_ai(1, "hi", None, None, discord_message=message)
        self.assertEqual(text, "A natural reply.")
        request = self.engine.ask.call_args.args[0]
        self.assertEqual((request.user_id, request.guild_id, request.channel_id), (1, 2, 3))
        self.assertEqual(legacy.get_user_session(1).last_activity, 0)
