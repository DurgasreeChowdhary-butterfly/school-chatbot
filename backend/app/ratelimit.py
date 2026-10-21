"""A simple in-memory rate limiter: at most `limit` events per key in a sliding time window."""
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60):
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record one event for `key`; False if the key is over its limit."""
        now = time.time()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - self.window:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            if len(self._events) > 50_000:  # keep memory bounded
                self._events = defaultdict(deque, {k: v for k, v in self._events.items() if v})
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
