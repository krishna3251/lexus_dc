"""Tests for the local hybrid RAG store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.ai_engine.rag import RAGStore


class TestRAGStore(unittest.IsolatedAsyncioTestCase):
    async def test_lexical_retrieval_without_embedding_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(db_path=Path(tmp) / "rag.sqlite3", max_items=20)
            store.embedder.api_key = ""
            result_a = await store.add(
                "Pal Metal farming",
                "Palworld ore and pal metal ingot farming guide",
                url="https://example.com/pal",
                domain="example.com",
                embed=False,
            )
            result_b = await store.add(
                "Minecraft guide",
                "Minecraft Java server setup and Fabric performance",
                url="https://example.com/minecraft",
                domain="example.com",
                embed=False,
            )
            self.assertTrue(result_a)
            self.assertTrue(result_b)

            results = await store.search("palworld pal metal ingot")
            self.assertEqual(len(results.items), 2)
            self.assertEqual(results.items[0].title, "Pal Metal farming")
            self.assertGreaterEqual(results.items[0].lexical_score, results.items[1].lexical_score)


if __name__ == "__main__":
    unittest.main()
