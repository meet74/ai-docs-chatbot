import time
from collections import deque


class RateLimiter:
    """Sliding window, in process. Behind several workers, put the limit at the proxy as well."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic() if now is None else now
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False, max(1, int(self.window - (now - q[0])) + 1)
        q.append(now)
        if len(self._hits) > 20000:
            self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
        return True, 0
