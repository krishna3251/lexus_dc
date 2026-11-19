from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import discord
from motor.motor_asyncio import AsyncIOMotorClient

from cogs.autorole import AutoroleCog
from cogs.search import YoutubeView
from security.lockdown import LockdownManager
from security.models import GuildSecurityConfig
from services.durations import parse_duration


class Journal:
    def __init__(self):
        self.entries = {}

    async def find_one_and_update(self, key, update, **kwargs):
        return self.entries.setdefault(key["_id"], {**key, **update["$setOnInsert"]})

    async def find(self, query):
        for entry in list(self.entries.values()):
            if entry["guild_id"] == query["guild_id"]:
                yield entry

    async def delete_one(self, key):
        del self.entries[key["_id"]]


class Channel:
    def __init__(self, cid):
        self.id = cid
        self.overwrite = discord.PermissionOverwrite(send_messages=True, view_channel=True)
        self.set_permissions = AsyncMock(side_effect=self.edit)

    def overwrites_for(self, role):
        return discord.PermissionOverwrite.from_pair(*self.overwrite.pair())

    async def edit(self, role, *, overwrite, reason):
        self.overwrite = overwrite or discord.PermissionOverwrite()


class LockdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_and_failed_restore_keep_original_permissions(self):
        channel = Channel(42)
        protected = Channel(43)
        cfg = GuildSecurityConfig(1, protected_channels=[43])
        guild = SimpleNamespace(
            id=1, me=SimpleNamespace(guild_permissions=discord.Permissions(manage_roles=True)),
            default_role=object(), text_channels=[channel, protected], fetch_channel=AsyncMock(return_value=channel),
        )
        journal = Journal()
        failure = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "denied")
        with patch("security.lockdown.mongo_helper.get_collection", return_value=journal):
            manager = LockdownManager()
            self.assertTrue((await manager.lock_guild(guild, "test", cfg)).success)
            self.assertFalse(channel.overwrite.send_messages)
            self.assertTrue(protected.overwrite.send_messages)
            self.assertFalse((await manager.lock_guild(guild, "test", cfg)).success)
            channel.overwrite.view_channel = False
            channel.set_permissions.side_effect = failure
            self.assertFalse((await LockdownManager().unlock_guild(guild, cfg)).success)
            self.assertIn("42", journal.entries)
            channel.set_permissions.side_effect = channel.edit
            self.assertTrue((await LockdownManager().unlock_guild(guild, cfg)).success)
            self.assertTrue(channel.overwrite.send_messages)
            self.assertFalse(channel.overwrite.view_channel)
            self.assertFalse(journal.entries)

    async def test_missing_journal_stops_before_discord_edit(self):
        channel = Channel(42)
        guild = SimpleNamespace(me=SimpleNamespace(guild_permissions=discord.Permissions(manage_roles=True)))
        with patch("security.lockdown.mongo_helper.get_collection", return_value=None):
            self.assertFalse((await LockdownManager().lock_guild(guild, "test", GuildSecurityConfig(1))).success)
        channel.set_permissions.assert_not_awaited()


class CommandTests(unittest.IsolatedAsyncioTestCase):
    def test_duration_checks_the_entire_input(self):
        self.assertEqual(parse_duration("1hour 30min"), 5400)
        self.assertEqual(parse_duration("2h30m"), 9000)
        for invalid in ("2hours", "around 2h", "-5m", "0m", "366d", ""):
            self.assertIsNone(parse_duration(invalid))

    async def test_youtube_renders_single_result(self):
        view = YoutubeView([{
            "id": {"videoId": "example"},
            "snippet": {"title": "Example", "description": "Description",
                        "channelTitle": "Channel", "publishedAt": "2026-11-19T00:00:00Z"},
        }], 1)
        self.assertTrue(view.next_button.disabled)
        self.assertEqual(view.create_embed().fields[1].name, "Published")

    async def test_role_panel_persists_with_motor_collection(self):
        client = AsyncIOMotorClient("mongodb://localhost:27017", connect=False)
        self.addCleanup(client.close)
        collection = client.test.reaction_roles
        message = SimpleNamespace(id=1, channel=SimpleNamespace(id=2))
        interaction = SimpleNamespace(
            response=SimpleNamespace(send_message=AsyncMock()), original_response=AsyncMock(return_value=message),
            guild_id=3,
        )
        role = SimpleNamespace(id=4, name="Example", mention="@Example")
        with patch("cogs.autorole.mongo_helper.get_collection", return_value=collection), \
             patch.object(type(collection), "insert_one", new_callable=AsyncMock) as insert:
            cog = AutoroleCog(None)
            await cog.reaction_role.callback(cog, interaction, "Roles", role)
        self.assertEqual(insert.await_args.args[0]["message_id"], 1)
