import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from services.discord_output import send_reply
from services.reply_layout import choose_layout


class ReplyLayoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_simple_code_and_stats(self):
        self.assertFalse(choose_layout("Hey!"))
        self.assertFalse(choose_layout("```py\nprint(1)\n```"))
        embed = choose_layout("## Yesterday\nJoined: 4\nLeft: 1")["embed"]
        self.assertEqual([(f.name, f.value) for f in embed.fields], [("Joined", "4"), ("Left", "1")])

    async def test_comparison_fields(self):
        reply = "## Headsets\n| Model | Mic | Price |\n|---|---|---|\n| A | USB | ₹900 |\n| B | Analog | ₹800 |"
        embed = choose_layout(reply)["embed"]
        self.assertEqual(embed.title, "Headsets")
        self.assertEqual(embed.fields[0].name, "A")
        self.assertIn("**Price** · ₹900", embed.fields[0].value)

    async def test_one_story_with_publisher_link(self):
        report = "A finding [1].\n\n### Sources\n\n[1] [A title](<https://example.com/a>)"
        self.assertIn("A finding [example.com](<https://example.com/a>)", choose_layout(report)["embed"].description)

    async def test_briefing_navigation_and_full_copy(self):
        answer = "## News\n" + "\n".join(f"{n}. **Story {n}**" for n in range(1, 11))
        async def capture(**kwargs):
            self.assertEqual(kwargs["file"].fp.read().decode(), answer)
            self.assertEqual(kwargs["allowed_mentions"].to_dict()["parse"], [])
            return kwargs["view"]

        view, = await send_reply(capture, answer, owner_id=42)
        next_button = view.children[0].children[-1].children[1]
        interaction = SimpleNamespace(user=SimpleNamespace(id=7), response=AsyncMock())
        await next_button.callback(interaction)
        interaction.response.edit_message.assert_not_awaited()
        interaction.user.id = 42
        await next_button.callback(interaction)
        updated = interaction.response.edit_message.await_args.kwargs["view"].to_components()
        self.assertIn("Story 10", str(updated))
        self.assertNotIn("**Story 1**", str(updated))

    async def test_rich_permission_fallback(self):
        error = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"),
                                  {"code": 50013, "message": "Missing permissions"})
        send = AsyncMock(side_effect=[error, "delivered"])
        answer = "Joined: 4\nLeft: 1"
        self.assertEqual(await send_reply(send, answer), ["delivered"])
        self.assertEqual(send.await_args.args, (answer,))
