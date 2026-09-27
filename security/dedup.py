"""
Event deduplication module for Lexus Security Engine.
Prevents processing duplicate Discord gateway events or issuing duplicate punishments.
"""

from __future__ import annotations
import time
from typing import Optional
from services.cache import TTLCache
from security.models import SecurityEvent


class EventDeduplicator:
    """
    Tracks recent event signatures in a bounded TTL cache.
    Buckets timestamps to catch fast duplicates while preserving legitimate subsequent actions.
    """

    def __init__(self, bucket_size_seconds: float = 3.0, ttl: float = 10.0, max_size: int = 5000):
        self.bucket_size = bucket_size_seconds
        self._cache: TTLCache[tuple, float] = TTLCache(max_size=max_size, default_ttl=ttl)

    def _make_key(self, event: SecurityEvent) -> tuple:
        # Round timestamp into discrete buckets
        bucket = int(event.timestamp / self.bucket_size)
        item_id = event.metadata.get("message_id") or event.metadata.get("audit_id")
        return (
            event.guild_id,
            event.event_type.value,
            event.actor_id,
            event.target_id,
            item_id,
            bucket
        )

    def is_duplicate(self, event: SecurityEvent) -> bool:
        """Check if an equivalent event was already observed in the current bucket."""
        key = self._make_key(event)
        return self._cache.contains(key)

    def record(self, event: SecurityEvent) -> None:
        """Record the event signature to prevent re-processing."""
        key = self._make_key(event)
        self._cache.set(key, event.timestamp)

    def check_and_record(self, event: SecurityEvent) -> bool:
        """
        Atomically check and record.
        Returns True if duplicate (should be skipped), False if new (recorded).
        """
        if self.is_duplicate(event):
            return True
        self.record(event)
        return False

    def clear(self) -> None:
        self._cache.clear()
