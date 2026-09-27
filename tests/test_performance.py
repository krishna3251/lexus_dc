"""
Performance and stress benchmark for Lexus Security Engine.
Measures throughput and memory boundedness across 100, 1,000, and 10,000 events.
"""

import time
import unittest
from security.engine import SecurityEngine
from security.models import SecurityEvent
from core.events import SecurityEventType


class TestSecurityPerformance(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = SecurityEngine()
        self.guild_id = 111222

    async def asyncTearDown(self):
        await self.engine.stop()

    async def test_100_events_throughput(self):
        t0 = time.perf_counter()
        for i in range(100):
            evt = SecurityEvent(
                guild_id=self.guild_id,
                actor_id=1000 + (i % 20),
                event_type=SecurityEventType.MESSAGE,
                timestamp=time.time(),
                metadata={"content": f"Message test #{i}"}
            )
            await self.engine.process_event(evt)
        duration = time.perf_counter() - t0
        self.assertLess(duration, 2.0, f"100 events took {duration:.3f}s (too slow)")

    async def test_1000_events_throughput(self):
        t0 = time.perf_counter()
        for i in range(1000):
            evt = SecurityEvent(
                guild_id=self.guild_id,
                actor_id=2000 + (i % 50),
                channel_id=3000 + (i % 5),
                event_type=SecurityEventType.MESSAGE,
                timestamp=time.time(),
                metadata={"content": f"Performance message #{i}"}
            )
            await self.engine.process_event(evt)
        duration = time.perf_counter() - t0
        rate = 1000.0 / duration
        self.assertLess(duration, 5.0, f"1000 events took {duration:.3f}s")
        # Ensure cache sizes remain bounded
        self.assertLessEqual(len(self.engine.dedup._cache), 5000)

    async def test_10000_events_memory_boundedness(self):
        t0 = time.perf_counter()
        # Stream 10,000 events through engine
        for i in range(10000):
            evt = SecurityEvent(
                guild_id=self.guild_id,
                actor_id=3000 + (i % 100),
                event_type=SecurityEventType.MESSAGE,
                timestamp=time.time(),
                metadata={"content": f"Bench {i}"}
            )
            await self.engine.process_event(evt)
        duration = time.perf_counter() - t0
        rate = 10000.0 / duration

        # Verify strict boundedness
        self.assertLessEqual(len(self.engine.dedup._cache), 5000)
        self.assertLessEqual(len(self.engine.event_tracker._counters), 5000)


if __name__ == "__main__":
    unittest.main()
