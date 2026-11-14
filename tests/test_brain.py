"""Brain regression tests: no real Discord or external provider requests."""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.ai_engine import AIEngineCog
from services.ai_engine.brain import Calculator, ConversationState, ResponseStyle, bounded_turns
from services.ai_engine.config import BrainConfig
from services.ai_engine.engine import AIEngine
from services.ai_engine.memory import AIMemoryService
from services.ai_engine.models import AIProvider, AIRequest, ProviderReply, ToolCall
from services.ai_engine.providers import CompatibleProvider, ProviderError, ProviderManager
from services.ai_engine.rag import RAGStore
from services.ai_engine.tools import ToolContext, ToolRegistry, ToolSpec, _resolve_member


class RecordingProvider:
    available = True
    names = ["fake:model"]

    def __init__(self):
        self.calls = []
        self.reply_text = "Useful answer."
        self.callback = None
        self.closed = False

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.callback:
            return await self.callback(kwargs)
        return ProviderReply(AIProvider.GROQ, "fake", {"role": "assistant", "content": self.reply_text}, self.reply_text)

    async def close(self):
        self.closed = True

    def health(self):
        return {}


class BrainTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AI_SQLITE_PATH": str(Path(self.tmp.name) / 'brain.sqlite3'),
                                          "AI_GATEWAY_API_KEY": "", "GROQ_API_KEY": "", "GEMINI_API_KEY": "",
                                          "GOOGLE_API_KEY": "", "AI_LOCAL_ENABLED": "false"})
        self.env.start()
        self.provider = RecordingProvider()
        self.engine = AIEngine(provider_manager=self.provider)
        self.context = ToolContext(SimpleNamespace(is_ready=lambda: True, commands=[]), None,
                                   SimpleNamespace(id=789), SimpleNamespace(id=123))

    async def asyncTearDown(self):
        await self.engine.close()
        self.env.stop()
        self.tmp.cleanup()

    def request(self, prompt, user=123, guild=None, channel=789):
        return AIRequest(user, guild, channel, prompt)

    async def test_deterministic_request_never_invokes_provider(self):
        result = await self.engine.ask(self.request("calculate (25 + 5) * 4"), self.context)
        self.assertTrue(result.success)
        self.assertEqual(result.text, "120")
        self.assertEqual(self.provider.calls, [])
        again = await self.engine.ask(self.request("calculate (25 + 5) * 4"), self.context)
        self.assertEqual(again.text, "120")
        self.assertEqual(self.engine.local_skills.hits, 1)

    async def test_offline_chat_and_commands_survive(self):
        self.provider.available = False
        self.assertEqual((await self.engine.ask(self.request("12 / 3"), self.context)).text, "4")
        result = await self.engine.ask(self.request("tell me a story"), self.context)
        self.assertEqual(result.error, "no_provider")
        self.assertTrue(self.engine.available)

    async def test_followup_uses_only_same_conversation(self):
        await self.engine.ask(self.request("I was discussing Stardew Valley"), self.context)
        await self.engine.ask(self.request("what about multiplayer?"), self.context)
        self.assertIn("Stardew Valley", json.dumps(self.provider.calls[-1]['messages']))
        await self.engine.ask(self.request("what about multiplayer?", channel=790), self.context)
        self.assertNotIn("Stardew Valley", json.dumps(self.provider.calls[-1]['messages']))
        await self.engine.ask(self.request("what about multiplayer?", user=124), self.context)
        self.assertNotIn("Stardew Valley", json.dumps(self.provider.calls[-1]['messages']))
        await self.engine.ask(self.request("what about multiplayer?", guild=1), self.context)
        self.assertNotIn("Stardew Valley", json.dumps(self.provider.calls[-1]['messages']))

    async def test_history_is_persistent_only_with_consent(self):
        await self.engine.ask(self.request("hello friend"), self.context)
        self.assertEqual(await self.engine.memory.recent_turns(123, None, 789), [])
        await self.engine.memory.set_preferences(123, None, history_enabled=True, external_allowed=True)
        await self.engine.ask(self.request("another message"), self.context)
        self.assertEqual(len(await self.engine.memory.recent_turns(123, None, 789)), 2)
        await self.engine.memory.set_preferences(123, None, history_enabled=False, external_allowed=True)
        self.assertEqual(await self.engine.memory.recent_turns(123, None, 789), [])

    async def test_external_optout_blocks_generation_and_research(self):
        await self.engine.memory.set_preferences(123, None, history_enabled=False, external_allowed=False)
        self.engine.research.research = AsyncMock(side_effect=AssertionError("must not search"))
        result = await self.engine.ask(self.request("latest news"), self.context)
        self.assertEqual(result.error, "external_disabled")
        result = await self.engine.ask(self.request("tell a story"), self.context)
        self.assertEqual(result.error, "provider_unavailable")
        self.assertEqual(self.provider.calls, [])

    async def test_memory_retrieval_and_clear_are_isolated(self):
        for user, guild, value in [(123, None, "Hinglish"), (124, None, "French"), (123, 1, "German")]:
            await self.engine.memory.remember(user, guild, "language", value)
        await self.engine.ask(self.request("hello friend"), self.context)
        messages = json.dumps(self.provider.calls[-1]['messages'])
        self.assertIn("Hinglish", messages)
        self.assertNotIn("French", messages)
        self.assertNotIn("German", messages)
        self.assertTrue(await self.engine.clear_user(123, None))
        self.assertEqual(await self.engine.memory.memories(123, None), [])
        self.assertEqual(self.engine.conversations.recent((123, None, 789)), [])
        self.assertEqual((await self.engine.memory.memories(124, None))[0]['value'], "French")

    async def test_same_user_is_bounded_other_user_keeps_working(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def delayed(kwargs):
            started.set()
            await release.wait()
            return ProviderReply(AIProvider.GROQ, "fake", {'role': 'assistant', 'content': 'done'}, "done")
        self.provider.callback = delayed
        active = asyncio.create_task(self.engine.ask(self.request("long task"), self.context))
        await started.wait()
        self.assertEqual((await self.engine.ask(self.request("another task"), self.context)).error, "busy")
        other = await self.engine.ask(self.request("2+2", user=124), self.context)
        self.assertEqual(other.text, "4")
        release.set()
        await active
        self.assertEqual(len(self.engine.capacity.scopes), 0)

    async def test_guild_and_global_capacity_have_no_wait_queue(self):
        self.engine.capacity.config = replace(self.engine.config, max_concurrent=2, per_guild=1)
        async with self.engine.capacity.acquire((1, 10, 20)):
            result = await self.engine.ask(self.request('2+2', user=2, guild=10), self.context)
            self.assertEqual(result.error, 'busy')
            result = await self.engine.ask(self.request('2+2', user=2, guild=11), self.context)
            self.assertTrue(result.success)

    async def test_cancel_and_shutdown_release_capacity(self):
        started = asyncio.Event()
        async def stuck(kwargs):
            started.set()
            await asyncio.Event().wait()
        self.provider.callback = stuck
        task = asyncio.create_task(self.engine.ask(self.request("wait for model"), self.context))
        await started.wait()
        await self.engine.capacity.cancel_user(123, None)
        self.assertTrue(task.cancelled())
        self.assertEqual(self.engine.capacity.by_scope, {})
        await self.engine.close()
        self.assertEqual((await self.engine.ask(self.request("2+2"), self.context)).error, "busy")

    async def test_total_timeout_is_visible(self):
        self.engine.config = replace(self.engine.config, request_timeout=.03)
        self.provider.callback = AsyncMock(side_effect=lambda _: None)
        async def stuck(kwargs):
            await asyncio.sleep(5)
        self.provider.callback = stuck
        result = await self.engine.ask(self.request('explain asyncio'), self.context)
        self.assertEqual(result.error, "request_timeout")
        self.assertEqual(self.engine.capacity.by_scope, {})

    async def test_empty_and_overlong_outputs_are_not_fake_successes(self):
        self.provider.reply_text = " "
        self.assertEqual((await self.engine.ask(self.request("hello"), self.context)).error, "empty_response")
        self.assertEqual((await self.engine.ask(self.request("a" * 9000), self.context)).error, "prompt_limit")

    async def test_request_failure_and_nonblocking_worker(self):
        self.provider.callback = AsyncMock(side_effect=ProviderError('503'))
        self.assertEqual((await self.engine.ask(self.request('hello friend'), self.context)).error, 'provider_unavailable')
        original = self.engine.memory._memories_sync
        def slow(*args):
            time.sleep(.05)
            return original(*args)
        self.engine.memory._memories_sync = slow
        ticks = 0
        async def heartbeat():
            nonlocal ticks
            for _ in range(5):
                ticks += 1
                await asyncio.sleep(.005)
        await asyncio.gather(self.engine.memory.memories(123, None), heartbeat())
        self.assertEqual(ticks, 5)

    async def test_deletion_waits_for_cancelled_sqlite_worker(self):
        await self.engine.memory.initialize()
        original = self.engine.memory._add_turn_sync
        entered = asyncio.Event()
        loop = asyncio.get_running_loop()
        def slow(*args):
            loop.call_soon_threadsafe(entered.set)
            time.sleep(.03)
            return original(*args)
        self.engine.memory._add_turn_sync = slow
        writing = asyncio.create_task(self.engine.memory.add_turn(123, None, 789, 'user', 'erase me', 'r1'))
        await entered.wait()
        writing.cancel()
        cleared = asyncio.create_task(self.engine.memory.clear_user(123, None))
        await asyncio.gather(writing, return_exceptions=True)
        self.assertTrue(await cleared)
        self.assertEqual(await self.engine.memory.recent_turns(123, None, 789), [])

    async def test_knowledge_uses_local_lexical_retrieval(self):
        store = self.engine.research.rag
        await store.add('Palworld crafting', 'Palworld pal metal ingot crafting guide', embed=False)
        store.embedder.embed_query = AsyncMock(side_effect=AssertionError('no network'))
        result = await self.engine.ask(self.request('knowledge: palworld metal ingot'), self.context)
        self.assertIn('Palworld crafting', result.text)
        self.assertEqual(self.provider.calls, [])

    async def test_natural_gateway_requires_direction_and_scopes_replies(self):
        bot = SimpleNamespace(user=SimpleNamespace(id=9), get_prefix=AsyncMock(return_value=['lx ']))
        cog = object.__new__(AIEngineCog)
        cog.bot = bot
        from services.cache import TTLCache
        cog._reply_owners = TTLCache(10, 90)
        message = SimpleNamespace(id=101, content='random conversation', guild=SimpleNamespace(id=3),
                                  author=SimpleNamespace(id=123), channel=SimpleNamespace(id=789), mentions=[], reference=None)
        self.assertIsNone(await cog._extract_natural_prompt(message))
        message.content = 'lxeus explain Python'
        self.assertEqual(await cog._extract_natural_prompt(message), 'explain Python')
        message.content = 'lex code make a bot'
        self.assertIsNone(await cog._extract_natural_prompt(message))
        message.content = 'and multiplayer?'
        message.reference = SimpleNamespace(message_id=55)
        cog._reply_owners.set(55, (123, 3, 789))
        self.assertEqual(await cog._extract_natural_prompt(message), 'and multiplayer?')
        message.author = SimpleNamespace(id=124)
        self.assertIsNone(await cog._extract_natural_prompt(message))

    async def test_mutation_requires_single_use_scoped_confirmation(self):
        user = MagicMock(spec=discord.Member)
        user.id, user.guild_permissions, user.top_role = 123, discord.Permissions(moderate_members=True), 10
        guild = SimpleNamespace(id=456, name='test', owner_id=999, member_count=3)
        user.guild = guild
        context = ToolContext(self.context.bot, guild, self.context.channel, user)
        handler = AsyncMock(return_value={'done': True})
        self.engine.tools.register(ToolSpec('mark', 'test mutation', {'type': 'object', 'properties': {}, 'additionalProperties': False},
                                            handler, required_permission='moderate_members', mutating=True))
        call = ToolCall('c1', 'mark', {})
        async def action(kwargs):
            return ProviderReply(AIProvider.GROQ, 'fake', {'role': 'assistant', 'content': None}, tool_calls=[call])
        self.provider.callback = action
        result = await self.engine.ask(self.request('timeout a member', guild=456), context)
        self.assertIn('Nothing executed', result.text)
        handler.assert_not_awaited()
        token = re.search(r'aiconfirm ([\w-]+)', result.text).group(1)
        wrong = replace(context, channel=SimpleNamespace(id=790))
        self.assertEqual((await self.engine.confirm(token, wrong)).error, 'confirmation_missing')
        self.assertTrue((await self.engine.confirm(token, context)).success)
        self.assertEqual(handler.await_count, 1)
        self.assertEqual((await self.engine.confirm(token, context)).error, 'confirmation_missing')

    async def test_registry_permission_and_schema_enforced_at_boundary(self):
        handler = AsyncMock()
        spec = ToolSpec('private', 'private', {'type': 'object', 'properties': {}}, handler, required_permission='manage_guild')
        self.engine.tools.register(spec)
        result = await self.engine.tools.execute('private', {}, self.context)
        self.assertFalse(result['success'])
        handler.assert_not_awaited()
        spec.required_permission = None
        spec.parameters = {'type': 'object', 'properties': {'n': {'type':'integer','minimum':1,'maximum':5}}, 'required':['n'], 'additionalProperties':False}
        for args in [{'n':True}, {'n':6}, {'n':1,'extra':'x'}, {}]:
            self.assertFalse((await self.engine.tools.execute('private', args, self.context))['success'])
        handler.assert_not_awaited()

    async def test_confirmation_expiry_and_revoked_permissions(self):
        user = MagicMock(spec=discord.Member)
        guild = SimpleNamespace(id=456, owner_id=999)
        user.id, user.guild, user.guild_permissions = 123, guild, discord.Permissions.none()
        context = ToolContext(self.context.bot, guild, self.context.channel, user)
        handler = AsyncMock()
        self.engine.tools.register(ToolSpec('restricted', 'restricted', {}, handler,
                                           required_permission='ban_members', mutating=True))
        scope = (123, 456, 789)
        self.engine.pending_actions.set('revoked', (scope, ToolCall('c1','restricted',{})))
        self.assertEqual((await self.engine.confirm('revoked',context)).error, 'permission_denied')
        self.engine.pending_actions.set('expired', (scope, ToolCall('c2','restricted',{})), ttl=-1)
        self.assertEqual((await self.engine.confirm('expired',context)).error, 'confirmation_missing')
        handler.assert_not_awaited()

    async def test_private_memory_interface_never_posts_contents_publicly(self):
        cog = object.__new__(AIEngineCog)
        ctx = SimpleNamespace(interaction=None, author=SimpleNamespace(send=AsyncMock()), send=AsyncMock())
        await cog._private(ctx, 'my private preference')
        ctx.author.send.assert_awaited_once()
        ctx.send.assert_not_awaited()
        ctx.interaction = object()
        await cog._private(ctx, 'private slash reply')
        self.assertTrue(ctx.send.call_args.kwargs['ephemeral'])

    async def test_read_tools_filter_private_channels(self):
        from services.ai_engine.tools import _list_channels
        user = MagicMock(spec=discord.Member)
        visible = SimpleNamespace(id=1, name='general', type='text', position=0,
                                  permissions_for=lambda _: SimpleNamespace(view_channel=True))
        private = SimpleNamespace(id=2, name='staff secrets', type='text', position=1,
                                  permissions_for=lambda _: SimpleNamespace(view_channel=False))
        context = replace(self.context, user=user, guild=SimpleNamespace(channels=[visible,private]))
        results = await _list_channels(context,{})
        self.assertEqual([item['name'] for item in results], ['general'])

    async def test_model_cannot_execute_unadvertised_tools(self):
        handler = AsyncMock()
        self.engine.tools.register(ToolSpec('hidden', 'read', {'type':'object','properties':{}}, handler))
        async def unrequested(kwargs):
            return ProviderReply(AIProvider.GROQ, 'fake', {'role':'assistant','content':None},
                                 tool_calls=[ToolCall('c1','hidden',{})])
        self.provider.callback = unrequested
        result = await self.engine.ask(self.request('casual chat'), self.context)
        self.assertFalse(result.success)
        handler.assert_not_awaited()



class BrainPrimitivesTests(unittest.TestCase):
    def test_arithmetic_does_not_evaluate_code_or_unbounded_powers(self):
        self.assertEqual(Calculator.calculate('2**3 + 5 % 2'), '9')
        for expression in ["__import__('os').system('true')", '2**999999', '(1).__class__', 'True+1', '1/0', '9'*200]:
            with self.subTest(expression=expression):
                with self.assertRaises((ValueError, ArithmeticError, SyntaxError)):
                    Calculator.calculate(expression)

    def test_style_is_stable_and_serious_overrides_playfulness(self):
        self.assertEqual(ResponseStyle.choose('debug Python asyncio').name, 'technical')
        self.assertEqual(ResponseStyle.choose('feeling depressed', 'sarcastic').name, 'serious')
        self.assertEqual(ResponseStyle.choose('hi there').name, 'casual')
        self.assertEqual(ResponseStyle.clean('As an AI assistant, Here is code.'), 'Here is code.')

    def test_context_and_session_bounds(self):
        config = BrainConfig(session_count=2, context_chars=1000, session_ttl=.01)
        state = ConversationState(config)
        for user in range(4):
            state.append((user, 2, 3), 'a'*100, 'b'*100)
        self.assertLessEqual(len(state._sessions), 2)
        self.assertEqual(state.recent((0,2,3)), [])
        self.assertEqual(bounded_turns([{'role':'user','content':'a'*100}], 10), [])
        time.sleep(.02)
        self.assertEqual(state.recent((3,2,3)), [])

    def test_member_mention_parsing(self):
        member = object()
        guild = SimpleNamespace(get_member=lambda mid: member if mid == 123 else None, members=[])
        self.assertIs(_resolve_member(guild, '<@123>'), member)
        self.assertIs(_resolve_member(guild, '<@!123>'), member)


class HybridProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'GROQ_API_KEY': '', 'GEMINI_API_KEY': ''})
        self.env.start()
        self.manager = ProviderManager(BrainConfig())

    async def asyncTearDown(self):
        await self.manager.close()
        self.env.stop()

    def reply(self, text='ok', provider=AIProvider.GROQ):
        return ProviderReply(provider, 'fake', {'role':'assistant','content':text}, text)

    async def test_local_adapter_over_real_loopback_http(self):
        from aiohttp import web
        received = []
        async def completion(request):
            received.append(await request.json())
            response = web.StreamResponse(headers={'Content-Type':'application/json'})
            await response.prepare(request)
            body = json.dumps({'choices':[{'message':{'content':'Haan, bolo.'}}]}).encode()
            await response.write(body[:20])
            await asyncio.sleep(.01)
            await response.write(body[20:])
            await response.write_eof()
            return response
        app = web.Application()
        app.router.add_post('/v1/chat/completions', completion)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        config = BrainConfig(local_enabled=True, local_url=f'http://127.0.0.1:{port}/v1', local_model='test-runtime', external_enabled=False)
        manager = ProviderManager(config)
        try:
            self.assertIsNone(manager.local.session)
            result = await manager.complete([{'role':'user','content':'hello'}], [], 100, allow_external=False)
            self.assertEqual(result.provider, AIProvider.LOCAL)
            self.assertEqual(result.text, 'Haan, bolo.')
            self.assertEqual(received[0]['max_tokens'], 100)
            self.assertEqual(manager.calls, 0)
            self.assertEqual(manager.local_calls, 1)
        finally:
            await manager.close()
            await runner.cleanup()

    async def test_local_failure_falls_back_only_with_permission(self):
        self.manager.local = SimpleNamespace(provider=AIProvider.LOCAL, model='local',
                                             complete=AsyncMock(side_effect=ProviderError('offline')), close=AsyncMock())
        remote = SimpleNamespace(provider=AIProvider.GROQ, model='remote', complete=AsyncMock(return_value=self.reply()), close=AsyncMock())
        self.manager.providers = [remote]
        self.assertEqual((await self.manager.complete([], [], 100)).provider, AIProvider.GROQ)
        self.assertEqual(remote.complete.await_count, 1)
        with self.assertRaises(ProviderError):
            await self.manager.complete([], [], 100, allow_external=False)
        self.assertEqual(remote.complete.await_count, 1)

    async def test_local_cannot_run_tools_or_live_search(self):
        self.manager.local = SimpleNamespace(provider=AIProvider.LOCAL, model='local', complete=AsyncMock(), close=AsyncMock())
        for kwargs in [{'tools':[{'name':'danger'}]}, {'tools':[], 'web_search':True}]:
            with self.assertRaises(ProviderError):
                await self.manager.complete(messages=[], max_output_tokens=100, allow_external=False, **kwargs)
        self.manager.local.complete.assert_not_awaited()

    async def test_retry_budget_includes_failed_attempts(self):
        self.manager = ProviderManager(BrainConfig(external_call_limit=2, provider_retries=1))
        remote = SimpleNamespace(provider=AIProvider.GROQ, model='test',
                                 complete=AsyncMock(side_effect=ProviderError('503')), close=AsyncMock())
        self.manager.providers = [remote]
        with self.assertRaises(ProviderError):
            await self.manager.complete([], [], 100)
        self.assertEqual(self.manager.calls, 2)
        self.assertEqual(remote.complete.await_count, 2)
        with self.assertRaises(ProviderError):
            await self.manager.complete([], [], 100)
        self.assertEqual(remote.complete.await_count, 2)

    async def test_external_disabled_even_when_keys_exist(self):
        with patch.dict(os.environ, {'GROQ_API_KEY':'test'}):
            manager = ProviderManager(BrainConfig(external_enabled=False))
            try:
                self.assertEqual(manager.providers, [])
                with self.assertRaises(ProviderError):
                    await manager.complete([], [], 100)
            finally:
                await manager.close()

    async def test_non_loopback_runtime_is_rejected(self):
        for url in ['https://example.com/v1', 'http://127.0.0.1.evil.test/v1', 'http://user:pass@localhost/v1']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                ProviderManager(BrainConfig(local_enabled=True, local_model='test', local_url=url))

    async def test_sdk_client_is_lazy_and_errors_do_not_expose_secrets(self):
        provider = CompatibleProvider(AIProvider.GROQ, 'private-test-key', 'https://example.com/v1', 'test')
        self.assertIsNone(provider.client)
        provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=AsyncMock(side_effect=RuntimeError('private-test-key in response body')))), close=AsyncMock())
        with self.assertRaises(ProviderError) as raised:
            await provider.complete([], [], 100)
        self.assertNotIn('private-test-key', str(raised.exception))
        await provider.close()


class MemoryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_correction_ttl_feedback_and_privacy_survive_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = AIMemoryService(db_path=Path(tmp) / 'mem.sqlite3')
            await mem.remember(1, 2, 'language', 'English')
            await mem.remember(1, 2, 'language', 'Hinglish')
            await mem.remember(1, 3, 'language', 'German')
            self.assertEqual(len(await mem.memories(1, 2)), 1)
            self.assertEqual((await mem.memories(1,2))[0]['value'], 'Hinglish')
            await mem.feedback(1, 2, False)
            await mem.set_preferences(1, 2, history_enabled=True, external_allowed=False)
            await mem.clear_user(1, 2)
            self.assertFalse((await mem.preferences(1, 2))['external_allowed'])
            self.assertEqual(len(await mem.memories(1, 3)), 1)
            self.assertTrue(await mem.remember(1, 2, 'food', 'rice'))
            with patch('services.ai_engine.memory.time.time', return_value=time.time() + 366*86400):
                self.assertEqual(await mem.memories(1,2), [])
            await mem.close()
            self.assertFalse(await mem.remember(1,2,'closed','cannot reopen'))

    async def test_history_expiry_and_privacy_failure_are_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = AIMemoryService(db_path=Path(tmp)/'memory.sqlite3')
            await mem.add_turn(1,2,3,'user','temporary','r1')
            with patch('services.ai_engine.memory.time.time', return_value=time.time() + 8*86400):
                self.assertEqual(await mem.recent_turns(1,2,3), [])
            await mem.close()
            prefs = await mem.preferences(1,2)
            self.assertFalse(prefs['external_allowed'])

    async def test_legacy_research_answers_are_removed_from_shared_rag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'memory.sqlite3'
            store = RAGStore(db_path=path)
            await store.add('User private prompt', 'sensitive generated answer', source_type='research', embed=False)
            await store.add('Public guide', 'public guide text', source_type='local', embed=False)
            await store.close()
            migrated = RAGStore(db_path=path)
            results = await migrated.search('private prompt', embed=False)
            self.assertEqual([item.title for item in results.items], ['Public guide'])
            await migrated.close()


class FeatureIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_feature_cogs_register_and_unload_without_network(self):
        from discord.ext import commands
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'AI_SQLITE_PATH':str(Path(tmp)/'smoke.sqlite3'), 'MONGO_URI':'', 'GROQ_API_KEY':'',
            'GEMINI_API_KEY':'', 'AI_GATEWAY_API_KEY':'', 'NVIDIA_API_KEY':'', 'OPENROUTER_API_KEY':''
        }), patch('aiohttp.ClientSession._request', AsyncMock(side_effect=AssertionError('network disabled'))):
            async with commands.Bot(command_prefix='lx ', intents=discord.Intents.none()) as bot:
                paths = sorted(Path('cogs').glob('*.py'), key=lambda p:(p.stem!='ai_engine', p.stem))
                for path in paths:
                    if path.stem != '__init__':
                        await bot.load_extension('cogs.'+path.stem)
                self.assertEqual(len(bot.extensions), 29)
                for name in ['ask', 'kick', 'ban', 'timeout', 'resetprefix', 'aimemory', 'aiconfirm']:
                    self.assertIsNotNone(bot.get_command(name), name)
                for name in ['security', 'ask', 'aimemory', 'aiconfirm']:
                    self.assertIsNotNone(bot.tree.get_command(name), name)
                for name in list(bot.extensions):
                    await bot.unload_extension(name)
                self.assertEqual(len(bot.extensions), 0)


class SecretLoggingTests(unittest.TestCase):
    def test_secret_values_and_exception_text_are_redacted(self):
        import io
        import logging
        from core.logging import SecretRedactionFilter
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(SecretRedactionFilter())
        logger = logging.getLogger('brain-redaction-test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        try:
            with patch.dict(os.environ, {'GROQ_API_KEY':'test-private-credential'}):
                try:
                    raise ValueError('failure includes test-private-credential')
                except ValueError:
                    logger.exception('Authorization: Bearer token123; key=%s', 'test-private-credential')
            text = stream.getvalue()
            self.assertNotIn('test-private-credential', text)
            self.assertNotIn('token123', text)
            self.assertIn('[REDACTED]', text)
            self.assertIn('ValueError', text)
        finally:
            logger.removeHandler(handler)
            handler.close()
