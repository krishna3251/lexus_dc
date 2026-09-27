"""
Bounded in-memory caching with TTL expiration and LRU eviction.
Guarantees bounded memory usage so no attacker or guild can exhaust bot RAM.
"""

from __future__ import annotations
import time
from collections import OrderedDict
from typing import Generic, TypeVar, Optional, Any

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """
    Thread-safe, bounded LRU cache with per-item TTL expiration.
    Automatically evicts the oldest items when max_size is reached,
    and strips expired entries on retrieval or explicit cleanup.
    """

    def __init__(self, max_size: int = 10000, default_ttl: float = 60.0):
        self._max_size = max(1, max_size)
        self._default_ttl = default_ttl
        # Maps key -> (value, expiry_timestamp)
        self._store: OrderedDict[K, tuple[V, float]] = OrderedDict()

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        now = time.monotonic()
        if key not in self._store:
            return default

        val, expiry = self._store[key]
        if expiry <= now:
            del self._store[key]
            return default

        # Move to end (most recently used)
        self._store.move_to_end(key)
        return val

    def set(self, key: K, value: V, ttl: Optional[float] = None) -> None:
        now = time.monotonic()
        item_ttl = self._default_ttl if ttl is None else ttl
        expiry = now + item_ttl

        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, expiry)

        # Evict oldest if exceeding capacity
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def delete(self, key: K) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def contains(self, key: K) -> bool:
        return self.get(key) is not None

    def __contains__(self, key: K) -> bool:
        return self.contains(key)

    def __len__(self) -> int:
        return len(self._store)

    def cleanup_expired(self) -> int:
        """Purge all expired items. Returns count of purged items."""
        now = time.monotonic()
        expired_keys = [k for k, (_, exp) in self._store.items() if exp <= now]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)

    def clear(self) -> None:
        self._store.clear()
