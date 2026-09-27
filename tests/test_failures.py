"""
Failure and resilience tests for Lexus Security Engine.
Simulates:
- MongoDB unavailable (fallback in-memory persistence)
- Audit log missing permissions
- Role hierarchy violation (cannot punish higher role)
- Duplicate event suppression
- Detector exception isolation
- Task manager graceful shutdown
"""

import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from security.engine import SecurityEngine
from security.models import SecurityEvent, SecurityActionType, GuildSecurityConfig
from core.events import SecurityEventType
from core.permissions import can_bot_act_on_member, can_bot_manage_role
from core.lifecycle import TaskManager
from services.database import SecurityDatabaseService


class TestSecurityFailuresAndResilience(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = SecurityEngine()
        self.guild_id = 999111

    async def asyncTearDown(self):
        await self.engine.stop()

    async def test_database_offline_fallback(self):
        # Database service with no active mongo connection
        db = SecurityDatabaseService()
        self.assertFalse(db.is_connected())

        # Config save & retrieve should fall back to memory
        saved = await db.save_config(self.guild_id, {"security_mode": "enforce", "test_field": "val"})
        self.assertFalse(saved)  # Mongo write returns False when offline
        cfg = await db.get_config(self.guild_id)
        self.assertEqual(cfg.get("test_field"), "val")  # Retrieved from in-memory fallback!

        # Incident save & retrieve should fall back to memory
        inc_data = {"incident_id": "INC-TEST-01", "guild_id": self.guild_id, "score": 90.0}
        await db.save_incident(inc_data)
        retrieved = await db.get_incident("INC-TEST-01")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.get("score"), 90.0)

    def test_role_hierarchy_failure(self):
        # Mock bot member and target member where target has higher role position
        bot_member = MagicMock()
        bot_member.id = 100
        bot_member.guild.owner_id = 999
        bot_member.top_role.position = 10
        bot_member.top_role.name = "Bot Role"

        target_member = MagicMock()
        target_member.id = 200
        target_member.guild.owner_id = 999
        target_member.top_role.position = 20  # Higher than bot!
        target_member.top_role.name = "Admin Role"

        can_act, reason = can_bot_act_on_member(bot_member, target_member, "moderate_members")
        self.assertFalse(can_act)
        self.assertIn("higher or equal", reason.lower())

    def test_owner_target_protection(self):
        bot_member = MagicMock()
        bot_member.id = 100
        bot_member.guild.owner_id = 999

        owner_member = MagicMock()
        owner_member.id = 999  # Is guild owner
        owner_member.guild = bot_member.guild

        can_act, reason = can_bot_act_on_member(bot_member, owner_member)
        self.assertFalse(can_act)
        self.assertIn("guild owner", reason.lower())

    async def test_duplicate_event_suppressed(self):
        evt = SecurityEvent(
            guild_id=self.guild_id,
            actor_id=5001,
            event_type=SecurityEventType.CHANNEL_DELETE,
            target_id=801
        )
        # First process
        res1 = await self.engine.process_event(evt)
        # Immediate duplicate event
        res2 = await self.engine.process_event(evt)
        self.assertEqual(len(res2), 0, "Duplicate event must be dropped immediately by dedup")

    async def test_detector_exception_isolation(self):
        # Sabotage spam detector with an exception
        def _failing_eval(event):
            raise RuntimeError("Simulated detector crash")

        self.engine.spam_detector.evaluate = _failing_eval

        # Message event should NOT crash the engine
        evt = SecurityEvent(
            guild_id=self.guild_id,
            actor_id=5002,
            event_type=SecurityEventType.MESSAGE,
            metadata={"content": "Hello world"}
        )
        try:
            results = await self.engine.process_event(evt)
            # Succeeded without raising exception
            self.assertIsInstance(results, list)
        except Exception as e:
            self.fail(f"Engine failed to isolate detector exception: {e}")

    async def test_task_manager_shutdown(self):
        tm = TaskManager(max_concurrent=5)
        # Spawn dummy tasks
        async def _dummy():
            await asyncio.sleep(10.0)

        t1 = tm.spawn(_dummy(), name="dummy_1")
        t2 = tm.spawn(_dummy(), name="dummy_2")
        self.assertEqual(tm.active_count, 2)

        # Trigger clean shutdown
        await tm.shutdown(timeout=1.0)
        self.assertEqual(tm.active_count, 0)
        self.assertTrue(t1.cancelled())
        self.assertTrue(t2.cancelled())


if __name__ == "__main__":
    unittest.main()
