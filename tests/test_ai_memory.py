"""Tests for local SQLite-backed Lexus AI memory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.ai_engine.memory import AIMemoryService


class TestAIMemoryService(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_roundtrip_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = AIMemoryService(db_path=Path(tmp) / "ai.sqlite3")
            await service.initialize()

            self.assertTrue(service.available)
            self.assertEqual(service.health()["backend"], "sqlite")

            self.assertTrue(
                await service.add_turn(
                    user_id=123,
                    guild_id=456,
                    channel_id=789,
                    role="user",
                    content="hello",
                    request_id="req-1",
                )
            )
            self.assertTrue(
                await service.add_turn(
                    user_id=123,
                    guild_id=456,
                    channel_id=789,
                    role="assistant",
                    content="salaam miyan",
                    request_id="req-1",
                )
            )

            turns = await service.recent_turns(123, 456, 789)
            self.assertEqual(
                turns,
                [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "salaam miyan"},
                ],
            )

            self.assertTrue(await service.remember(123, 456, "name", "Krishna"))
            self.assertEqual(
                await service.memories(123, 456),
                [{"key": "name", "value": "Krishna", "source": "explicit"}],
            )

            self.assertTrue(await service.claim_message(999))
            self.assertFalse(await service.claim_message(999))

            self.assertTrue(await service.forget(123, 456, "name"))
            self.assertEqual(await service.memories(123, 456), [])

            self.assertTrue(await service.clear_history(123, 456, 789))
            self.assertEqual(await service.recent_turns(123, 456, 789), [])

            await service.close()
            self.assertFalse(service.available)

    async def test_memory_is_bounded_per_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = AIMemoryService(max_history=2, db_path=Path(tmp) / "ai.sqlite3")
            await service.initialize()

            for index in range(10):
                await service.add_turn(
                    user_id=1,
                    guild_id=2,
                    channel_id=3,
                    role="user" if index % 2 == 0 else "assistant",
                    content=f"turn-{index}",
                    request_id=f"req-{index}",
                )

            turns = await service.recent_turns(1, 2, 3)
            self.assertEqual(
                [item["content"] for item in turns],
                ["turn-8", "turn-9"],
            )

            await service.close()


if __name__ == "__main__":
    unittest.main()
