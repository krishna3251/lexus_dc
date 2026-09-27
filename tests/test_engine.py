"""
Integration tests for SecurityEngine, Simulator, Audit Mode vs Enforce Mode,
and Incident Correlation.
"""

import asyncio
import unittest
from security.engine import SecurityEngine
from security.simulator import SecuritySimulator
from security.models import SecurityEvent, SecurityActionType, SecurityState, GuildSecurityConfig
from core.events import SecurityEventType
from services.database import security_db


class TestSecurityEngineIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = SecurityEngine()
        self.simulator = SecuritySimulator(self.engine)
        self.guild_id = 888001

    async def asyncTearDown(self):
        await self.engine.stop()

    async def test_audit_mode_no_destructive_enforcement(self):
        # Configure guild for audit mode
        await security_db.save_config(self.guild_id, {"security_mode": "audit", "security_enabled": True})
        self.engine.invalidate_config_cache(self.guild_id)

        # Send rapid message flood
        results = await self.simulator.simulate_message_flood(
            guild_id=self.guild_id,
            user_id=101,
            message_count=10
        )

        # In audit mode, actions are either LOG/ALERT or marked as SIMULATED
        for r in results:
            if r.action not in (SecurityActionType.LOG, SecurityActionType.ALERT):
                self.assertIn("[SIMULATED", r.reason)

        # Incident should be created and recorded
        incidents = await security_db.get_recent_incidents(self.guild_id, limit=5)
        self.assertGreaterEqual(len(incidents), 1)

    async def test_enforce_mode_actions_selected(self):
        # Configure guild for enforce mode
        await security_db.save_config(self.guild_id, {"security_mode": "enforce", "security_enabled": True})
        self.engine.invalidate_config_cache(self.guild_id)

        results = await self.simulator.simulate_repeated_spam(
            guild_id=self.guild_id,
            user_id=102,
            repeat_count=6,
            content="FREE NITRO SCAM LINK AT PROMO.NET"
        )
        # Verify decisions were made and logged
        self.assertGreater(self.engine.decisions_made, 0)

    async def test_simulated_join_raid_state_transition(self):
        guild_id = 888002
        await security_db.save_config(guild_id, {"security_mode": "enforce", "security_enabled": True})
        self.engine.invalidate_config_cache(guild_id)

        final_state, _ = await self.simulator.simulate_join_raid(guild_id=guild_id, bot_count=15)
        # Should have elevated or reached RAID state
        self.assertIn(final_state, (SecurityState.ELEVATED, SecurityState.RAID))

    async def test_simulated_multi_vector_nuke(self):
        guild_id = 888003
        await security_db.save_config(guild_id, {"security_mode": "enforce", "security_enabled": True})
        self.engine.invalidate_config_cache(guild_id)

        nuke_report = await self.simulator.simulate_multi_vector_nuke(guild_id=guild_id, attacker_id=9001)
        self.assertGreater(nuke_report["structural_heat"], 60.0)
        self.assertGreater(nuke_report["actor_heat"], 50.0)
        self.assertGreaterEqual(nuke_report["events_processed"], 5)


if __name__ == "__main__":
    unittest.main()
