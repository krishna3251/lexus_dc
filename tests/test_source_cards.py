"""Regressions for real link formats and independent source interactions."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.discord_output import discord_length, send_reply
from services.reply_layout import choose_layout
from services.report_formatting import format_research_report
from services.ai_engine.research import ResearchSource
from services.source_cards import SourceBrowser, linked_sources


def report(count=10):
    sources = [ResearchSource(f"S{i}", f"Article {i}", f"https://news.example.org/article-{i}")
               for i in range(1, count + 1)]
    answer = "## Hyderabad briefing\n\n" + "\n\n".join(
        f"{i}. **Story {i}**\nA useful detail [S{i}]." for i in range(1, count + 1))
    return format_research_report(answer, sources)


class SourceCardTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_ten_references_are_clickable_and_available(self):
        body, sources = linked_sources(report())
        self.assertEqual(len(sources), 10)
        self.assertNotIn("### Sources", body)
        for i in range(1, 11):
            self.assertIn(f"[{i} · news.example.org](<https://news.example.org/article-{i}>)", body)
        self.assertIn("Sources · 10", str(choose_layout(report(), owner_id=42)["view"].to_components()))

    async def test_markdown_bare_autolinks_fragments_and_duplicates(self):
        body, sources = linked_sources(
            "Read [guide](https://example.com/Function_(math)#usage), "
            "<https://example.com/Function_(math)#usage> and https://example.org/search?q=x&n=2."
        )
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0].url, "https://example.com/Function_%28math%29#usage")
        self.assertIn("[guide](<" + sources[0].url + ">)", body)
        self.assertTrue(body.endswith("[example.org](<https://example.org/search?q=x&n=2>)."))

    async def test_code_invalid_urls_and_numeric_link_labels_are_preserved(self):
        text = "`https://example.com/code`\n```text\nhttps://example.org/code\n```\nhttps://127.0.0.1/no"
        self.assertEqual(linked_sources(text), (text, ()))
        text = "[1](<https://example.com/a>)\n\n### Sources\n\n[1] [Other article](<https://example.org/b>)"
        body, sources = linked_sources(text)
        self.assertEqual(body, "[1](<https://example.com/a>)")
        self.assertEqual(len(sources), 2)
        malformed = "Answer\n\n### Sources\n\n[1] [Article](<https://example.com/a>)\nImportant limitation."
        self.assertIn("Important limitation.", linked_sources(malformed)[0])

    async def test_source_panel_is_private_and_selects_original_article(self):
        layout = choose_layout(report(2), owner_id=42)
        button = next(child for child in layout["view"].walk_children()
                      if getattr(child, "label", "").startswith("Sources"))
        interaction = SimpleNamespace(user=SimpleNamespace(id=99), response=AsyncMock())
        await button.callback(interaction)
        sent = interaction.response.send_message.await_args.kwargs
        self.assertTrue(sent["ephemeral"])
        self.assertEqual(sent["allowed_mentions"].to_dict()["parse"], [])
        browser = sent["view"]
        menu = next(child.children[0] for child in browser.children[0].children
                    if getattr(child, "children", None) and hasattr(child.children[0], "options"))
        menu._values = ["1"]
        await menu.callback(interaction)
        detail = interaction.response.edit_message.await_args.kwargs["view"].to_components()
        self.assertIn("Article 2", str(detail))
        self.assertIn("A useful detail", str(detail))
        self.assertIn("https://news.example.org/article-2", str(detail))

    async def test_more_than_25_links_can_all_be_reached(self):
        body, sources = linked_sources("\n".join(f"https://example.com/{i}" for i in range(31)))
        browser = SourceBrowser(sources, body)
        menu = browser.children[0].children[-2].children[0]
        self.assertEqual(len(menu.options), 25)
        next_button = browser.children[0].children[-1].children[1]
        interaction = SimpleNamespace(response=AsyncMock())
        await next_button.callback(interaction)
        updated = interaction.response.edit_message.await_args.kwargs["view"]
        menu = updated.children[0].children[-2].children[0]
        self.assertEqual([option.value for option in menu.options], [str(i) for i in range(25, 31)])

    async def test_large_unicode_titles_and_urls_fit_discord_text_budget(self):
        url = "https://example.com/" + "a" * 1350
        text = "## News\n\n" + "detail " * 300 + " [1].\n\n### Sources\n\n[1] [" + "🔥" * 100 + "](<" + url + ">)"
        layout = choose_layout(text, owner_id=42)
        self.assertIn("view", layout)
        def text_units(node):
            if isinstance(node, list):
                return sum(text_units(item) for item in node)
            if isinstance(node, dict):
                return discord_length(node.get("content", "")) + sum(
                    text_units(value) for key, value in node.items() if key != "content")
            return 0
        self.assertLessEqual(text_units(layout["view"].to_components()), 4000)
        body, sources = linked_sources(text)
        self.assertLessEqual(text_units(SourceBrowser(sources, body).to_components()), 4000)

    async def test_unstructured_prose_stays_text_and_search_uses_embed(self):
        self.assertFalse(choose_layout("Ordinary conversation. " * 30))
        layout = choose_layout("See [the guide](https://example.com/guide).")
        self.assertIn("embed", layout)
        self.assertEqual(layout["embed"].url, "https://example.com/guide")
        send = AsyncMock(return_value="message")
        self.assertEqual(await send_reply(send, "See [the guide](https://example.com/guide)."), ["message"])
        self.assertIn("view", send.await_args.kwargs)
