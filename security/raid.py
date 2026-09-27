"""
Guild-wide raid detector for Lexus Security Engine.
Detects join floods, synchronized message waves, distributed content patterns,
and behavioural clustering across multiple coordinated accounts.
"""

from __future__ import annotations
import time
from typing import Optional, Any
from security.models import Evidence, SecurityEvent
from security.event_tracker import MultiWindowCounter, SlidingWindow
from services.cache import TTLCache
from core.events import SecurityEventType


class RaidDetector:
    """
    Monitors guild-level velocity and detects distributed attacks that individual
    rate limiters would miss due to load splitting across multiple accounts.
    """

    def __init__(self):
        # Join counters per guild: guild_id -> MultiWindowCounter (10s, 30s, 60s, 300s)
        self._join_counters: TTLCache[int, MultiWindowCounter] = TTLCache(max_size=500, default_ttl=600.0)
        # Recent joins with timestamp and actor_id: guild_id -> list[(actor_id, timestamp)]
        self._recent_joins: TTLCache[int, list[tuple[int, float]]] = TTLCache(max_size=500, default_ttl=300.0)
        # Distributed message patterns: guild_id -> list[(actor_id, content_hash/domain, timestamp)]
        self._guild_msg_patterns: TTLCache[int, list[tuple[int, str, float]]] = TTLCache(max_size=500, default_ttl=60.0)

    def evaluate_join(self, event: SecurityEvent) -> Optional[Evidence]:
        """Evaluate incoming member join for raid velocity signals."""
        guild_id = event.guild_id
        actor_id = event.actor_id or 0
        now = time.monotonic()

        counter = self._join_counters.get(guild_id)
        if counter is None:
            counter = MultiWindowCounter(windows={
                "10s": (10.0, 50),
                "30s": (30.0, 100),
                "60s": (60.0, 200),
                "300s": (300.0, 500)
            })
            self._join_counters.set(guild_id, counter)

        counts = counter.add(now)

        # Track recent joins
        joins = self._recent_joins.get(guild_id) or []
        joins = [j for j in joins if (now - j[1]) < 300.0]
        joins.append((actor_id, now))
        self._recent_joins.set(guild_id, joins)

        score = 0.0
        reasons: list[str] = []

        # Check velocities
        if counts["10s"] >= 10:
            score += 85.0
            reasons.append(f"Severe join flood ({counts['10s']} joins in 10s)")
        elif counts["10s"] >= 5:
            score += 50.0
            reasons.append(f"High join velocity ({counts['10s']} joins in 10s)")

        if counts["60s"] >= 25:
            score += 40.0
            reasons.append(f"Sustained join wave ({counts['60s']} joins in 60s)")

        if score >= 40.0:
            return Evidence(
                detector_name="RaidDetector",
                score=min(100.0, score),
                confidence=0.85,
                reason="; ".join(reasons),
                metadata={"counts": counts, "actor_id": actor_id}
            )

        return None

    def evaluate_message_pattern(
        self,
        event: SecurityEvent,
        normalized_content: str,
        detected_domain: Optional[str] = None
    ) -> Optional[Evidence]:
        """
        Evaluate guild-wide messages for distributed attack patterns
        (e.g., 10 distinct accounts each sending 1 identical or similar message).
        """
        guild_id = event.guild_id
        actor_id = event.actor_id or 0
        if not normalized_content and not detected_domain:
            return None

        now = time.monotonic()
        pattern_signature = detected_domain or (normalized_content[:30] if len(normalized_content) >= 8 else "")
        if not pattern_signature:
            return None

        patterns = self._guild_msg_patterns.get(guild_id) or []
        # Purge older than 20 seconds
        patterns = [p for p in patterns if (now - p[2]) < 20.0]
        patterns.append((actor_id, pattern_signature, now))
        self._guild_msg_patterns.set(guild_id, patterns)

        # Find other actors posting this exact pattern signature in the last 20 seconds
        matching_actors = {p[0] for p in patterns if p[1] == pattern_signature}

        if len(matching_actors) >= 4:
            score = min(100.0, 30.0 + len(matching_actors) * 12.0)
            return Evidence(
                detector_name="RaidDetector",
                score=score,
                confidence=0.90,
                reason=f"Distributed raid signature ({len(matching_actors)} distinct actors sharing pattern)",
                metadata={
                    "pattern": pattern_signature,
                    "distinct_actors_count": len(matching_actors),
                    "actors": list(matching_actors)[:10]
                }
            )

        return None
