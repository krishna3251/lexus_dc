"""Security regressions at the HTTP and AI mutation boundaries."""

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from api import app
from services.ai_engine.tools import ToolContext, ToolRegistry, ToolSpec


async def get(path, api_key=None):
    """Exercise the ASGI route without a live server or extra test dependency."""
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "scheme": "http", "method": "GET", "path": path, "raw_path": path.encode(),
             "root_path": "", "query_string": b"", "server": ("test", 80),
             "client": ("127.0.0.1", 1234),
             "headers": [(b"x-api-key", api_key.encode("latin-1"))] if api_key is not None else []}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return status, json.loads(body)


class StatsAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_blank_secret_denies_statistics_and_keeps_health_public(self):
        for secret in ("", "   "):
            with patch.dict(os.environ, {"API_SECRET_KEY": secret}):
                for supplied in (None, "offline-key"):
                    status, body = await get("/stats", supplied)
                    self.assertEqual(status, 503)
                    self.assertNotIn("members", body)
                for path in ("/", "/health"):
                    self.assertEqual(await get(path), (200, {"status": "ok"}))

    async def test_valid_key_is_required_and_rotated_values_are_used(self):
        with patch.dict(os.environ, {"API_SECRET_KEY": "offline-first-key"}):
            self.assertEqual((await get("/stats", "offline-first-key"))[0], 200)
            for supplied in (None, "", "wrong", "offline-first-keÿ"):
                self.assertEqual((await get("/stats", supplied))[0], 403)
            os.environ["API_SECRET_KEY"] = "offline-second-key"
            self.assertEqual((await get("/stats", "offline-first-key"))[0], 403)
            self.assertEqual((await get("/stats", "offline-second-key"))[0], 200)


class AIHierarchyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.handler = AsyncMock(return_value={"done": True})
        self.registry = ToolRegistry()
        self.registry.register(ToolSpec(
            "test_ban", "Guarded mutation", {"type": "object", "properties": {"member_id": {"type": "integer"}},
                                            "required": ["member_id"], "additionalProperties": False},
            self.handler, required_permission="ban_members", mutating=True,
        ))
        self.target = SimpleNamespace(id=200, top_role=20, roles=[])
        self.guild = SimpleNamespace(id=1, owner_id=999, me=SimpleNamespace(top_role=30),
                                     get_member=lambda _: self.target)
        self.user = MagicMock(spec=discord.Member)
        self.user.id, self.user.guild, self.user.top_role = 100, self.guild, 10
        self.user.guild_permissions = discord.Permissions(administrator=True, ban_members=True)
        self.context = ToolContext(SimpleNamespace(user=SimpleNamespace(id=400)), self.guild, None,
                                   self.user, confirmed_mutations=True)
        policy = patch("security.engine.security_engine.get_guild_config", new=AsyncMock(
            return_value=SimpleNamespace(protected_roles=[], trusted_users=[])))
        policy.start()
        self.addCleanup(policy.stop)

    async def test_lower_rank_administrator_cannot_use_bot_to_bypass_hierarchy(self):
        result = await self.registry.execute("test_ban", {"member_id": 200}, self.context)
        self.assertFalse(result["success"])
        self.assertIn("requester's highest role", result["error"])
        self.handler.assert_not_awaited()

    async def test_guild_owner_can_act_on_lower_than_bot_target(self):
        self.user.id = self.guild.owner_id
        result = await self.registry.execute("test_ban", {"member_id": 200}, self.context)
        self.assertTrue(result["success"])
        self.handler.assert_awaited_once()

    async def test_higher_rank_administrator_still_can_act(self):
        self.user.top_role = 25
        result = await self.registry.execute("test_ban", {"member_id": 200}, self.context)
        self.assertTrue(result["success"])
        self.handler.assert_awaited_once()

    async def test_guild_owner_cannot_bypass_bot_hierarchy(self):
        self.user.id = self.guild.owner_id
        self.target.top_role = 35
        result = await self.registry.execute("test_ban", {"member_id": 200}, self.context)
        self.assertFalse(result["success"])
        self.handler.assert_not_awaited()
