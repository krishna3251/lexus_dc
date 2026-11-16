import base64
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
from cogs.ai_engine import AIEngineCog
from services.image_inputs import read_images, set_reaction
from services.ai_engine.engine import AIEngine
from services.ai_engine.models import AIRequest, AIResult, AIProvider, ProviderReply
from services.ai_engine.providers import ProviderManager
from services.ai_engine.tools import ToolContext

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZ1kAAAAASUVORK5CYII=')


class ImageInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_uploaded_bytes_are_passed_to_vision_and_never_web_research(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            'AI_SQLITE_PATH': temp + '/brain.db', 'GROQ_API_KEY': 'test-placeholder', 'AI_LOCAL_ENABLED': 'false',
        }):
            manager = ProviderManager()
            engine = AIEngine(provider_manager=manager)
            manager.vision_provider.complete = AsyncMock(return_value=ProviderReply(
                AIProvider.GROQ, 'vision-test', {'role': 'assistant', 'content': 'This diagram shows a request flow.'},
                'This diagram shows a request flow.'))
            manager.providers[0].complete = AsyncMock(side_effect=AssertionError('text model must not handle image'))
            engine.research.research = AsyncMock(side_effect=AssertionError('must not web search'))
            images = await read_images([SimpleNamespace(size=len(PNG), read=AsyncMock(return_value=PNG))])
            request = AIRequest(1, None, 2, 'samja ye', images=images)
            context = ToolContext(SimpleNamespace(is_ready=lambda: True), None, SimpleNamespace(id=2), SimpleNamespace(id=1))
            try:
                result = await engine.ask(request, context)
                self.assertTrue(result.success)
                call = manager.vision_provider.complete.await_args.kwargs
                user = next(m for m in call['messages'] if m['role'] == 'user')
                self.assertEqual(user['content'][1]['image_url']['url'], images[0])
                self.assertEqual(call['tools'], [])
                self.assertEqual(manager.calls, 1)
            finally:
                await engine.close()

    async def test_status_success_and_failure_clear_waiting_reaction(self):
        for success in (True, False):
            cog = object.__new__(AIEngineCog)
            cog.bot = SimpleNamespace()
            cog.engine = SimpleNamespace(instance_id='test', ask=AsyncMock(return_value=AIResult(success, 'Response')))
            message = SimpleNamespace(add_reaction=AsyncMock(), remove_reaction=AsyncMock(), guild=SimpleNamespace(me='bot'))
            answer = await cog._run(SimpleNamespace(id=1), None, SimpleNamespace(id=2), 'samja ye', source_message=message)
            self.assertEqual(answer, 'Response')
            self.assertEqual([c.args[0] for c in message.add_reaction.await_args_list], ['⏳', '✅' if success else '❌'])
            message.remove_reaction.assert_awaited_once_with('⏳', 'bot')

    async def test_limits_and_unsupported_uploads_give_actionable_errors(self):
        attachment = SimpleNamespace(size=7 * 1024 * 1024, read=AsyncMock())
        with self.assertRaises(ValueError):
            await read_images([attachment])
        attachment.read.assert_not_awaited()
        with self.assertRaises(ValueError):
            await read_images([SimpleNamespace(size=4, read=AsyncMock(return_value=b'file'))])
        with self.assertRaises(ValueError):
            await read_images([attachment] * 4)

    async def test_reaction_permissions_do_not_break_reply(self):
        error = discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), {'code': 50013, 'message': 'Denied'})
        await set_reaction(SimpleNamespace(add_reaction=AsyncMock(side_effect=error)), '⏳')

    async def test_discord_adapter_passes_image_and_sets_completion_status(self):
        for success in (True, False):
            cog = object.__new__(AIEngineCog)
            cog.engine = SimpleNamespace(instance_id='test', ask=AsyncMock(return_value=AIResult(success, 'Answer')))
            cog.bot = SimpleNamespace()
            author = SimpleNamespace(id=1)
            source = SimpleNamespace(guild=None, _state=SimpleNamespace(user=author),
                                     add_reaction=AsyncMock(), remove_reaction=AsyncMock())
            attachment = SimpleNamespace(size=len(PNG), read=AsyncMock(return_value=PNG))
            answer = await cog._run(author, None, SimpleNamespace(id=2), 'samja ye',
                                    source_message=source, attachments=[attachment])
            self.assertEqual(answer, 'Answer')
            self.assertTrue(cog.engine.ask.await_args.args[0].images[0].startswith('data:image/png;base64,'))
            self.assertEqual([call.args[0] for call in source.add_reaction.await_args_list],
                             ['⏳', '✅' if success else '❌'])
            source.remove_reaction.assert_awaited_once_with('⏳', author)
