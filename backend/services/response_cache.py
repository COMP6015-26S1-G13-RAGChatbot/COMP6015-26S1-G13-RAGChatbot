from collections import OrderedDict
from copy import deepcopy
from threading import RLock
import time
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Bounded, thread-safe LRU cache with automatic expiration."""

    def __init__(self, *, max_entries: int, ttl_seconds: float):
        if max_entries < 1 or ttl_seconds <= 0:
            raise ValueError("Cache size and TTL must be positive")
        self.max_entries, self.ttl_seconds = max_entries, ttl_seconds
        self._items: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = RLock()

    def get(self, key: str) -> T | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= time.monotonic():
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return deepcopy(value)

    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + self.ttl_seconds, deepcopy(value))
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
