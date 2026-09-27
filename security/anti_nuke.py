"""
Anti-nuke structural defense engine for Lexus Security Engine.
Monitors rapid channel deletions, role modifications, mass bans/kicks,
and calculates cross-action composite threat scores.
"""

from __future__ import annotations
import time
from typing import Optional, Any
from security.models import Evidence, SecurityEvent
from security.event_tracker import SlidingWindow
from core.events import SecurityEventType
from services.cache import TTLCache


class AntiNukeDetector:
    """
    Detects mass structural destruction and multi-vector nuke attempts
    by correlating actions across channels, roles, webhooks, and moderation actions.
    """

    def __init__(self):
        # Action windows: (guild_id, actor_id, action_category) -> SlidingWindow
        self._action_windows: TTLCache[tuple[int, int, str], SlidingWindow] = TTLCache(max_size=5000, default_ttl=300.0)
        # Recent distinct action categories per actor: (guild_id, actor_id) -> set[action_category]
        self._actor_action_types: TTLCache[tuple[int, int], set[str]] = TTLCache(max_size=2000, default_ttl=60.0)

    def _get_window(self, guild_id: int, actor_id: int, category: str, window_sec: float) -> SlidingWindow:
        key = (guild_id, actor_id, category)
        win = self._action_windows.get(key)
        if win is None:
            win = SlidingWindow(window_seconds=window_sec, max_size=50)
            self._action_windows.set(key, win)
        return win

    def evaluate(self, event: SecurityEvent) -> Optional[Evidence]:
        """Evaluate structural action for nuke patterns and cross-action velocity."""
        guild_id = event.guild_id
        actor_id = event.actor_id
        if not actor_id:
            return None

        event_type = event.event_type
        now = time.monotonic()
        actor_key = (guild_id, actor_id)

        # Map event type to category and threshold
        category = ""
        window_sec = 10.0
        burst_threshold = 3
        base_score_per_action = 20.0

        if event_type == SecurityEventType.CHANNEL_DELETE:
            category = "channel_delete"
            window_sec = 15.0
            burst_threshold = 2
            base_score_per_action = 35.0

        elif event_type == SecurityEventType.CHANNEL_CREATE:
            category = "channel_create"
            window_sec = 15.0
            burst_threshold = 4
            base_score_per_action = 15.0

        elif event_type == SecurityEventType.ROLE_DELETE:
            category = "role_delete"
            window_sec = 15.0
            burst_threshold = 2
            base_score_per_action = 35.0

        elif event_type == SecurityEventType.ROLE_CREATE:
            category = "role_create"
            window_sec = 15.0
            burst_threshold = 4
            base_score_per_action = 15.0

        elif event_type in (SecurityEventType.MEMBER_BAN, SecurityEventType.MEMBER_KICK):
            category = "moderation_mass"
            window_sec = 15.0
            burst_threshold = 3
            base_score_per_action = 30.0

        elif event_type in (SecurityEventType.WEBHOOK_CREATE, SecurityEventType.WEBHOOK_DELETE):
            category = "webhook_mutations"
            window_sec = 15.0
            burst_threshold = 3
            base_score_per_action = 25.0

        elif event_type == SecurityEventType.BOT_ADD:
            category = "bot_add"
            window_sec = 30.0
            burst_threshold = 2
            base_score_per_action = 30.0

        else:
            return None

        # Record action in category window
        win = self._get_window(guild_id, actor_id, category, window_sec)
        count = win.add(now)

        # Track distinct action categories performed by this actor
        action_types = self._actor_action_types.get(actor_key) or set()
        action_types.add(category)
        self._actor_action_types.set(actor_key, action_types)

        # Cross-action calculation: multiple distinct destructive actions in 60s
        cross_action_count = len(action_types)
        cross_multiplier = 1.0 + (cross_action_count - 1) * 0.4 if cross_action_count > 1 else 1.0

        score = 0.0
        reasons: list[str] = []

        if count >= burst_threshold:
            raw_score = (count * base_score_per_action) * cross_multiplier
            score = min(100.0, raw_score)
            reasons.append(f"Rapid structural actions: {count} {category} in {int(window_sec)}s")

        if cross_action_count >= 3:
            score = max(score, 90.0)
            reasons.append(f"Multi-vector attack: actor engaged in {cross_action_count} distinct administrative categories ({', '.join(action_types)})")

        if score >= 35.0:
            return Evidence(
                detector_name="AntiNukeDetector",
                score=score,
                confidence=0.92,
                reason="; ".join(reasons),
                metadata={
                    "category": category,
                    "count": count,
                    "distinct_categories": list(action_types),
                    "actor_id": actor_id
                }
            )

        return None
