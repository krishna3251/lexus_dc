"""Offline regressions for the runtime failures observed in production logs."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import wavelink
from discord.ext import commands

import main
import mongo_helper
from cogs.perspective import PerspectiveCog
from cogs.security import SecurityCog
from core.interaction_response import defer_once, report_error, respond
from services.lavalink import LavalinkConnection


def http_error(code, status=400):
    return discord.HTTPException(SimpleNamespace(status=status, reason="test"), {"code": code, "message": "test"})


def interaction():
    result = MagicMock()
    result.id = 123
    result.extras = {}
    result.is_expired.return_value = False
    result.response.is_done.return_value = False
    result.response.defer = AsyncMock()
    result.response.send_message = AsyncMock()
    result.followup.send = AsyncMock()
    return result


class InteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_deferred_response_uses_private_followup(self):
        item = interaction()
        self.assertTrue(await defer_once(item))
        item.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        item.response.is_done.return_value = True
        await respond(item, "Done", ephemeral=True)
        item.response.send_message.assert_not_awaited()
        item.followup.send.assert_awaited_once_with(content="Done", ephemeral=True)

    async def test_unavailable_ack_stops_work(self):
        for code in (40060, 10062):
            item = interaction()
            item.response.defer.side_effect = http_error(code)
            self.assertFalse(await defer_once(item))
            item.followup.send.assert_not_awaited()

    async def test_unrelated_http_failure_is_not_hidden(self):
        item = interaction()
        item.response.defer.side_effect = http_error(50013, 403)
        with self.assertRaises(discord.HTTPException):
            await defer_once(item)

    async def test_local_response_race_uses_followup(self):
        item = interaction()
        item.response.send_message.side_effect = discord.InteractionResponded(item)
        self.assertTrue(await respond(item, "Done", ephemeral=True))
        item.followup.send.assert_awaited_once()

    async def test_expired_reply_and_duplicate_error_do_not_cascade(self):
        item = interaction()
        item.is_expired.return_value = True
        self.assertFalse(await respond(item, "Done", ephemeral=True))
        item.response.send_message.assert_not_awaited()
        item.is_expired.return_value = False
        for code in (40060, 10062):
            await report_error(item, commands.CommandInvokeError(http_error(code)), discord.Embed())
        item.response.send_message.assert_not_awaited()
        await report_error(item, ValueError("test"), discord.Embed())
        await report_error(item, ValueError("test"), discord.Embed())
        item.response.send_message.assert_awaited_once()

    async def test_failed_followup_is_handled(self):
        item = interaction()
        item.response.is_done.return_value = True
        item.followup.send.side_effect = http_error(10015, 404)
        self.assertFalse(await respond(item, "Done", ephemeral=True))

    async def test_security_status_acknowledges_before_database(self):
        item = interaction()
        cog = object.__new__(SecurityCog)

        async def read_config(guild_id):
            item.response.defer.assert_awaited_once()
            raise RuntimeError("stop after checking ordering")

        with patch("cogs.security.security_engine.get_guild_config", side_effect=read_config):
            with self.assertRaisesRegex(RuntimeError, "ordering"):
                await SecurityCog.security_status.callback(cog, item)

    async def test_security_mutation_aborts_when_ack_rejected(self):
        item = interaction()
        item.response.defer.side_effect = http_error(40060)
        cog = object.__new__(SecurityCog)
        with patch("cogs.security.security_db.save_config", new_callable=AsyncMock) as save:
            await SecurityCog.security_config.callback(cog, item, mode="enforce")
        save.assert_not_awaited()

    async def test_global_hybrid_handler_does_not_send_again(self):
        ctx = SimpleNamespace(interaction=interaction(), send=AsyncMock())
        await main.on_command_error(ctx, commands.CommandInvokeError(http_error(40060)))
        ctx.send.assert_not_awaited()
        ctx.interaction.response.send_message.assert_not_awaited()


class LavalinkTests(unittest.IsolatedAsyncioTestCase):
    def sdk(self, node):
        return SimpleNamespace(Node=MagicMock(return_value=node), NodeStatus=wavelink.NodeStatus,
                               Pool=SimpleNamespace(connect=AsyncMock(return_value={})))

    async def test_swallowed_pool_failure_closes_unregistered_node_and_session(self):
        node = SimpleNamespace(identifier="lexus-primary", status=wavelink.NodeStatus.DISCONNECTED,
                               close=AsyncMock())
        sdk = self.sdk(node)
        connection = LavalinkConnection(sdk)
        await connection.connect(MagicMock(), "http://unused.invalid", "test")
        session = sdk.Node.call_args.kwargs["session"]
        self.assertTrue(session.closed)
        node.close.assert_awaited_once_with(eject=True)
        self.assertIsNone(connection.node)

    async def test_repeated_ready_does_not_allocate_another_session(self):
        node = SimpleNamespace(identifier="lexus-primary", status=wavelink.NodeStatus.CONNECTING,
                               close=AsyncMock())
        sdk = self.sdk(node)
        sdk.Pool.connect.return_value = {node.identifier: node}
        connection = LavalinkConnection(sdk)
        try:
            await connection.connect(MagicMock(), "http://unused.invalid", "test")
            session = connection.session
            await connection.connect(MagicMock(), "http://unused.invalid", "test")
            sdk.Pool.connect.assert_awaited_once()
            self.assertFalse(session.closed)
        finally:
            await connection.close()
        self.assertTrue(session.closed)
        await connection.connect(MagicMock(), "http://unused.invalid", "test")
        sdk.Pool.connect.assert_awaited_once()

    async def test_cancellation_closes_http_session(self):
        node = SimpleNamespace(identifier="lexus-primary", close=AsyncMock())
        sdk = self.sdk(node)
        sdk.Pool.connect.side_effect = asyncio.CancelledError
        connection = LavalinkConnection(sdk)
        with self.assertRaises(asyncio.CancelledError):
            await connection.connect(MagicMock(), "http://unused.invalid", "test")
        self.assertTrue(sdk.Node.call_args.kwargs["session"].closed)

    async def test_node_close_failure_still_closes_session(self):
        connection = LavalinkConnection(MagicMock())
        import aiohttp
        session = connection.session = aiohttp.ClientSession()
        connection.node = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("test")))
        with self.assertRaises(RuntimeError):
            await connection.close()
        self.assertTrue(session.closed)

    async def test_real_wavelink_rejected_endpoint_releases_session(self):
        from aiohttp import web
        app = web.Application()

        async def not_lavalink(request):
            return web.Response(status=404)

        app.router.add_get("/v4/websocket", not_lavalink)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        host, port = runner.addresses[0]
        connection = LavalinkConnection(wavelink)
        sessions = []
        import aiohttp
        real_session = aiohttp.ClientSession

        def session_factory():
            session = real_session()
            sessions.append(session)
            return session

        try:
            with patch("services.lavalink.aiohttp.ClientSession", side_effect=session_factory):
                await connection.connect(MagicMock(), f"http://{host}:{port}", "test")
            self.assertTrue(sessions[0].closed)
            self.assertIsNone(connection.node)
            self.assertNotIn("lexus-primary", wavelink.Pool.nodes)
        finally:
            await connection.close()
            await runner.cleanup()


class ShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_bot_context_closes_on_cancellation(self):
        client = main.Bot()
        started = asyncio.Event()

        async def start(token):
            started.set()
            await asyncio.Event().wait()

        with patch.object(main, "bot", client), patch.object(main, "TOKEN", "test"), \
             patch.object(client, "start", side_effect=start), \
             patch("security.engine.security_engine.stop", new_callable=AsyncMock), \
             patch.object(main.mongo_helper, "disconnect", new_callable=AsyncMock):
            task = asyncio.create_task(main.start_bot())
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(client.is_closed())

    async def test_cancelled_start_closes_bot_before_loop_exits(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        started = asyncio.Event()

        async def start(token):
            started.set()
            await asyncio.Event().wait()

        client.start = AsyncMock(side_effect=start)
        with patch.object(main, "bot", client), patch.object(main, "TOKEN", "test"):
            task = asyncio.create_task(main.start_bot())
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        client.__aexit__.assert_awaited_once()

    async def test_service_failure_does_not_skip_discord_close(self):
        client = main.Bot()
        client.ai_engine = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("test")))
        client.lavalink = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("test")))
        with patch.object(commands.Bot, "close", new_callable=AsyncMock) as close, \
             patch("security.engine.security_engine.stop", new_callable=AsyncMock), \
             patch.object(main.mongo_helper, "disconnect", new_callable=AsyncMock) as disconnect:
            await client.close()
        close.assert_awaited_once()
        disconnect.assert_awaited_once()


class MongoTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_ping_closes_client_without_logging_uri(self):
        client = MagicMock()
        client.admin.command = AsyncMock(side_effect=RuntimeError("secret-uri"))
        with patch.object(mongo_helper, "_client", None), patch.object(mongo_helper, "_db", None), \
             patch.dict("os.environ", {"MONGO_URI": "mongodb://unused.invalid"}), \
             patch.object(mongo_helper, "AsyncIOMotorClient", return_value=client), \
             self.assertLogs("mongo_helper", level="ERROR") as logs:
            self.assertIsNone(await mongo_helper.connect())
            self.assertIsNone(mongo_helper.get_db())
        client.close.assert_called_once()
        self.assertNotIn("secret-uri", " ".join(logs.output))

    async def test_offline_karma_warns_once_per_outage(self):
        cog = PerspectiveCog(MagicMock())
        message = MagicMock()
        collection = SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock())
        with patch("cogs.perspective.mongo_helper.get_collection", return_value=None) as get_collection, \
             patch("cogs.perspective.logger.warning") as warning:
            self.assertEqual(await cog.update_karma(message), 0)
            await cog.update_karma(message)
            warning.assert_called_once()
            get_collection.return_value = collection
            await cog.update_karma(message)
            collection.update_one.assert_awaited_once()
            get_collection.return_value = None
            await cog.update_karma(message)
            self.assertEqual(warning.call_count, 2)
