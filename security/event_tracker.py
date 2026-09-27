"""
Sliding-window counters, token buckets, and multi-window event trackers.
All tracking structures are strictly bounded and memory-safe with automatic expiration.
"""

from __future__ import annotations
import time
from collections import deque
from typing import Optional, Any
from services.cache import TTLCache


class SlidingWindow:
    """
    Bounded sliding-window counter using collections.deque and monotonic time.
    Removes events older than window_seconds on access and bounds total stored events.
    """

    def __init__(self, window_seconds: float, max_size: int = 100):
        self.window = float(window_seconds)
        self.max_size = max(1, max_size)
        self.events: deque[float] = deque(maxlen=self.max_size)

    def add(self, timestamp: Optional[float] = None) -> int:
        """Add event timestamp (defaults to monotonic now) and return active count."""
        now = time.monotonic() if timestamp is None else timestamp
        cutoff = now - self.window

        while self.events and self.events[0] < cutoff:
            self.events.popleft()

        self.events.append(now)
        return len(self.events)

    def count(self, now: Optional[float] = None) -> int:
        """Return number of events currently within the window without adding new event."""
        current = time.monotonic() if now is None else now
        cutoff = current - self.window

        while self.events and self.events[0] < cutoff:
            self.events.popleft()

        return len(self.events)

    def clear(self) -> None:
        self.events.clear()


class MultiWindowCounter:
    """
    Multi-window rate detector evaluating activity across multiple time horizons:
    e.g. 5 seconds, 15 seconds, 60 seconds, and 300 seconds (5 minutes).
    """

    def __init__(
        self,
        windows: Optional[dict[str, tuple[float, int]]] = None
    ):
        # window_name -> (window_seconds, max_size)
        self.config = windows or {
            "5s": (5.0, 50),
            "15s": (15.0, 100),
            "60s": (60.0, 200),
            "300s": (300.0, 500)
        }
        self.windows: dict[str, SlidingWindow] = {
            name: SlidingWindow(sec, max_sz)
            for name, (sec, max_sz) in self.config.items()
        }

    def add(self, timestamp: Optional[float] = None) -> dict[str, int]:
        now = time.monotonic() if timestamp is None else timestamp
        return {name: win.add(now) for name, win in self.windows.items()}

    def get_counts(self, now: Optional[float] = None) -> dict[str, int]:
        current = time.monotonic() if now is None else now
        return {name: win.count(current) for name, win in self.windows.items()}


class TokenBucket:
    """
    Token-bucket rate limiter.
    Tolerates transient bursts up to capacity while enforcing a sustained refill rate.
    """

    def __init__(self, capacity: float, refill_rate: float):
        """
        :param capacity: Max burst capacity in tokens.
        :param refill_rate: Rate in tokens per second.
        """
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Attempt to consume tokens. Returns True if consumed, False if insufficient."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self.tokens


class EventTracker:
    """
    Central event tracker managing sliding windows and rate limits across guilds,
    users, channels, and structural action categories.
    Memory is bounded using TTLCache to prevent unbounded growth.
    """

    def __init__(self, cache_size: int = 5000, ttl: float = 300.0):
        # Stores keys like ("user_msg", guild_id, user_id) -> MultiWindowCounter
        self._counters: TTLCache[tuple[str, int, int], MultiWindowCounter] = TTLCache(
            max_size=cache_size, default_ttl=ttl
        )
        # Stores action-specific sliding windows, e.g. ("chan_del", guild_id, actor_id) -> SlidingWindow
        self._action_windows: TTLCache[tuple[str, int, int], SlidingWindow] = TTLCache(
            max_size=cache_size, default_ttl=ttl
        )

    def record_user_message(self, guild_id: int, user_id: int) -> dict[str, int]:
        """Record a user message and return counts over [5s, 15s, 60s, 300s]."""
        key = ("user_msg", guild_id, user_id)
        counter = self._counters.get(key)
        if counter is None:
            counter = MultiWindowCounter()
            self._counters.set(key, counter)
        return counter.add()

    def get_user_message_counts(self, guild_id: int, user_id: int) -> dict[str, int]:
        key = ("user_msg", guild_id, user_id)
        counter = self._counters.get(key)
        if counter is None:
            return {"5s": 0, "15s": 0, "60s": 0, "300s": 0}
        return counter.get_counts()

    def record_structural_action(
        self,
        action_type: str,
        guild_id: int,
        actor_id: int,
        window_seconds: float = 10.0,
        max_size: int = 50
    ) -> int:
        """Record an administrative or structural action for an actor."""
        key = (action_type, guild_id, actor_id)
        win = self._action_windows.get(key)
        if win is None:
            win = SlidingWindow(window_seconds=window_seconds, max_size=max_size)
            self._action_windows.set(key, win, ttl=window_seconds * 2)
        return win.add()

    def get_structural_action_count(
        self,
        action_type: str,
        guild_id: int,
        actor_id: int
    ) -> int:
        key = (action_type, guild_id, actor_id)
        win = self._action_windows.get(key)
        if win is None:
            return 0
        return win.count()

    def cleanup(self) -> None:
        self._counters.cleanup_expired()
        self._action_windows.cleanup_expired()
