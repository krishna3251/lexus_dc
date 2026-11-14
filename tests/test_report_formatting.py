"""Presentation regressions based on the pasted Discord report's structure."""
import unittest

from services.ai_engine.engine import _format_research_answer
from services.ai_engine.research import ResearchResult, ResearchSource
from services.discord_output import discord_length, prepare_reply, split_reply
from services.report_formatting import format_research_report, normalize_report


def source(number, title="Official announcement", domain="example.com"):
    return ResearchSource(f"S{number}", title, f"https://{domain}/article-{number}", domain=domain)


class ReportFormattingTests(unittest.TestCase):
    def test_pasted_layout_gets_spacing_citations_and_compact_sources(self):
        text = (
            "1. **Nvidia – last\u202f6\u202fdays (Nov 9–14, 2026)**\\\n&#x20;\n"
            "- **Leadership update** – A reported development [ S1 ][ S4 ].\n"
            "- **Market context** – A six-week measurement, not six days [S4].\n"
            "**Bottom line:** Preserve this conclusion.\n"
            "2. Sources: [S1] duplicated title https://example.com/article-1"
        )
        report = _format_research_answer(ResearchResult(True, answer=text, sources=[source(1), source(4)]))
        self.assertTrue(report.startswith("## Nvidia – last 6 days"))
        self.assertNotIn("&#x20;", report)
        self.assertNotIn("[ S", report)
        self.assertIn("development [1] [2].", report)
        self.assertIn("\n\n- **Market context**", report)
        self.assertIn("**Impact:** Preserve this conclusion.", report)
        self.assertNotIn("duplicated title", report)
        self.assertEqual(report.count("### Sources"), 1)
        self.assertIn("[1] [example.com · Official announcement](<https://example.com/article-1>)", report)
        self.assertIn("six-week measurement, not six days", report)

    def test_numbered_procedures_are_retained(self):
        report = normalize_report("1. **Open settings** and choose a channel.\n2. **Save changes** to finish.")
        self.assertIn("1. **Open settings** and", report)
        self.assertIn("2. **Save changes** to", report)

    def test_code_literals_and_fake_source_heading_in_code_are_preserved(self):
        code = "```text\nSources:\n[ S99 ]\n&#x20;\n```"
        report = format_research_report("## Report\n" + code + "\nA finding [ S1 ].", [source(1)])
        self.assertIn(code, report)
        self.assertIn("A finding [1].", report)
        self.assertIn("### Sources", report)

    def test_inline_code_is_not_changed(self):
        self.assertEqual(normalize_report("Use `[ S1 ]` and `&#x20;`."), "Use `[ S1 ]` and `&#x20;`.")

    def test_grouped_and_unknown_citations_are_explicit(self):
        report = format_research_report("Facts [ S1, S2 ] and [ S99 ].", [source(1), source(2)])
        self.assertIn("Facts [1] [2]", report)
        self.assertIn("[source unverified]", report)
        self.assertNotIn("S99", report)

    def test_all_ten_source_ids_have_references(self):
        report = format_research_report("Details [S9] [S10].", [source(i) for i in range(1, 11)])
        self.assertIn("[10] [example.com", report)
        self.assertIn("article-10", report)

    def test_source_labels_cannot_inject_markdown(self):
        report = format_research_report("Fact [S1].", [source(1, "Bad ](https://elsewhere.test) **title**\nnext")])
        self.assertNotIn("](https://elsewhere.test)", report)
        self.assertNotIn("**title**", report)
        self.assertEqual(report.count("](<https://example.com/"), 1)

    def test_split_does_not_leave_heading_at_end_of_message(self):
        report = "Intro. " * 210 + "\n\n### Impact\n\n" + "Explanation. " * 120
        parts = split_reply(report)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(not p.rstrip().endswith("### Impact") for p in parts))
        self.assertTrue(any(p.startswith("### Impact\n\nExplanation") for p in parts))
        self.assertTrue(all(discord_length(p) <= 1900 for p in parts))

    def test_split_keeps_clickable_sources_intact(self):
        link = "[An official source](<https://example.com/" + "a" * 1350 + ">)"
        text = "Summary. " * 170 + "\n\n" + link
        parts = split_reply(text)
        self.assertTrue(any(link in part for part in parts))
        self.assertTrue(all(discord_length(p) <= 1900 for p in parts))

    def test_oversized_link_is_attached_without_a_broken_preview(self):
        text = "[Source](<https://example.com/" + "a" * 2400 + ">)"
        parts, attachment = prepare_reply(text)
        self.assertIsNotNone(attachment)
        self.assertNotIn("https://", parts[0])
        self.assertEqual(attachment.fp.read().decode(), text)
        attachment.close()
