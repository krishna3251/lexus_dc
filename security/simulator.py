"""
Security attack simulator for Lexus Security Engine.
Internal testing harness to stress test detectors, state transitions,
multi-vector nuke detection, and distributed raid correlation with fake events.
"""

from __future__ import annotations
import time
import asyncio
from typing import Optional, Any
from core.events import SecurityEventType
from security.models import SecurityEvent, SecurityState
from security.engine import SecurityEngine


class SecuritySimulator:
    """Simulates realistic attack vectors to validate the security engine offline."""

    def __init__(self, engine: SecurityEngine):
        self.engine = engine

    async def simulate_message_flood(
        self,
        guild_id: int = 999001,
        user_id: int = 1001,
        message_count: int = 10,
        content: str = "Test rapid chatter"
    ) -> list[Any]:
        """Simulate a single actor sending messages in rapid succession."""
        results = []
        for i in range(message_count):
            evt = SecurityEvent(
                guild_id=guild_id,
                actor_id=user_id,
                channel_id=5001,
                event_type=SecurityEventType.MESSAGE,
                timestamp=time.time(),
                metadata={"message_id": 100000 + i, "content": f"{content} {i}"}
            )
            res = await self.engine.process_event(evt)
            results.extend(res)
        return results

    async def simulate_repeated_spam(
        self,
        guild_id: int = 999001,
        user_id: int = 1002,
        repeat_count: int = 5,
        content: str = "BUY FREE NITRO NOW!!"
    ) -> list[Any]:
        """Simulate exact and near-duplicate text spam."""
        results = []
        for i in range(repeat_count):
            evt = SecurityEvent(
                guild_id=guild_id,
                actor_id=user_id,
                channel_id=5001,
                event_type=SecurityEventType.MESSAGE,
                timestamp=time.time(),
                metadata={"message_id": 200000 + i, "content": content}
            )
            res = await self.engine.process_event(evt)
            results.extend(res)
        return results

    async def simulate_join_raid(
        self,
        guild_id: int = 999002,
        bot_count: int = 20
    ) -> tuple[SecurityState, list[Any]]:
        """
        Simulate a rapid join flood across 20 distinct accounts.
        Verifies transition from NORMAL -> ELEVATED -> RAID.
        """
        results = []
        for i in range(bot_count):
            actor_id = 20000 + i
            evt = SecurityEvent(
                guild_id=guild_id,
                actor_id=actor_id,
                event_type=SecurityEventType.MEMBER_JOIN,
                timestamp=time.time(),
                metadata={"account_age_hours": 0.5}
            )
            res = await self.engine.process_event(
                evt,
                extra_context={"created_at": time.time() - 1800, "has_default_avatar": True}
            )
            results.extend(res)

        final_state = self.engine.get_state_machine(guild_id).current_state
        return final_state, results

    async def simulate_distributed_spam_raid(
        self,
        guild_id: int = 999003,
        actors_count: int = 15,
        spam_phrase: str = "join discord.gg/fake-scam-server"
    ) -> tuple[SecurityState, list[Any]]:
        """
        Simulate a distributed raid where multiple distinct actors each post
        1-2 messages containing the same link/phrase.
        """
        results = []
        for i in range(actors_count):
            actor_id = 30000 + i
            evt = SecurityEvent(
                guild_id=guild_id,
                actor_id=actor_id,
                channel_id=5002,
                event_type=SecurityEventType.MESSAGE,
                timestamp=time.time(),
                metadata={"message_id": 300000 + i, "content": spam_phrase}
            )
            res = await self.engine.process_event(evt)
            results.extend(res)

        final_state = self.engine.get_state_machine(guild_id).current_state
        return final_state, results

    async def simulate_multi_vector_nuke(
        self,
        guild_id: int = 999004,
        attacker_id: int = 40001
    ) -> dict[str, Any]:
        """
        Simulate a multi-stage destructive server nuke:
        1. Role creation
        2. Escalation with Administrator permission
        3. Channel deletion burst
        4. Role deletion burst
        5. Webhook creation
        """
        events_results = []

        # 1. Role Create
        evt_rc = SecurityEvent(
            guild_id=guild_id,
            actor_id=attacker_id,
            target_id=8001,
            event_type=SecurityEventType.ROLE_CREATE,
            timestamp=time.time()
        )
        events_results.append(await self.engine.process_event(evt_rc))

        # 2. Permission Escalation (Admin grant)
        evt_perm = SecurityEvent(
            guild_id=guild_id,
            actor_id=attacker_id,
            target_id=8001,
            event_type=SecurityEventType.ROLE_UPDATE,
            timestamp=time.time()
        )
        events_results.append(await self.engine.process_event(
            evt_perm,
            extra_context={"before_permissions": 0, "after_permissions": 8}  # 8 = Administrator bit
        ))

        # 3. Channel Deletions (3 in 2 seconds)
        for ch_id in (7001, 7002, 7003):
            evt_cd = SecurityEvent(
                guild_id=guild_id,
                actor_id=attacker_id,
                target_id=ch_id,
                event_type=SecurityEventType.CHANNEL_DELETE,
                timestamp=time.time()
            )
            events_results.append(await self.engine.process_event(evt_cd))

        # 4. Role Deletions
        for rid in (8002, 8003):
            evt_rd = SecurityEvent(
                guild_id=guild_id,
                actor_id=attacker_id,
                target_id=rid,
                event_type=SecurityEventType.ROLE_DELETE,
                timestamp=time.time()
            )
            events_results.append(await self.engine.process_event(evt_rd))

        # 5. Webhook creation
        evt_wh = SecurityEvent(
            guild_id=guild_id,
            actor_id=attacker_id,
            channel_id=7004,
            event_type=SecurityEventType.WEBHOOK_CREATE,
            timestamp=time.time()
        )
        events_results.append(await self.engine.process_event(evt_wh))

        heat_mgr = self.engine.get_heat_manager(guild_id)
        state_mgr = self.engine.get_state_machine(guild_id)

        return {
            "final_state": state_mgr.current_state,
            "structural_heat": heat_mgr.structural_heat.get_heat(),
            "actor_heat": heat_mgr.get_actor_heat(attacker_id),
            "events_processed": len(events_results)
        }
