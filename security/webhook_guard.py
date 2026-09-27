"""
Webhook guard for Lexus Security Engine.
Monitors creation, update, and deletion of Discord webhooks to prevent webhook spam
and stealth administrative channels.
"""

from __future__ import annotations
import time
from typing import Optional, Any
from security.models import Evidence, SecurityEvent, TrustLevel
from security.event_tracker import SlidingWindow
from services.cache import TTLCache


class WebhookGuard:
    """Detects rapid or unauthorized webhook manipulation."""

    def __init__(self):
        # (guild_id, actor_id) -> SlidingWindow
        self._actor_webhook_windows: TTLCache[tuple[int, int], SlidingWindow] = TTLCache(max_size=2000, default_ttl=300.0)

    def evaluate(
        self,
        event: SecurityEvent,
        actor_trust: TrustLevel,
        channel_id: Optional[int] = None
    ) -> Optional[Evidence]:
        actor_id = event.actor_id or 0
        guild_id = event.guild_id

        # Skip owner actions
        if actor_trust == TrustLevel.OWNER:
            return None

        key = (guild_id, actor_id)
        win = self._actor_webhook_windows.get(key)
        if win is None:
            win = SlidingWindow(window_seconds=15.0, max_size=20)
            self._actor_webhook_windows.set(key, win)

        count = win.add(time.monotonic())
        score = 0.0
        reasons: list[str] = []

        if count >= 3:
            score += 70.0
            reasons.append(f"Rapid webhook creation/mutation ({count} actions in 15s)")
        elif count >= 2:
            score += 35.0
            reasons.append(f"Elevated webhook activity ({count} actions in 15s)")

        if actor_trust in (TrustLevel.NEW_MEMBER, TrustLevel.SUSPICIOUS, TrustLevel.UNKNOWN):
            score += 25.0
            reasons.append(f"Actor has low trust ({actor_trust.value})")

        if score >= 35.0:
            return Evidence(
                detector_name="WebhookGuard",
                score=min(100.0, score),
                confidence=0.88,
                reason="; ".join(reasons),
                metadata={"count": count, "channel_id": channel_id, "actor_id": actor_id}
            )

        return None
