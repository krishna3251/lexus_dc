"""Tests for deterministic research planning."""

from __future__ import annotations

import unittest

from services.ai_engine.research import ResearchPlanner


class TestResearchPlanner(unittest.TestCase):
    def test_today_news_gets_fresh_queries(self):
        plan = ResearchPlanner.plan("what are today's main news stories")
        self.assertEqual(plan.freshness, "fresh")
        self.assertGreaterEqual(len(plan.queries), 1)
        self.assertTrue(any("latest" in q.casefold() for q in plan.queries))

    def test_deep_research_is_bounded(self):
        plan = ResearchPlanner.plan("deep research and compare multiple sources on AI agents")
        self.assertTrue(plan.deep)
        self.assertLessEqual(len(plan.queries), 3)
        self.assertGreaterEqual(plan.max_sources, 10)


if __name__ == "__main__":
    unittest.main()