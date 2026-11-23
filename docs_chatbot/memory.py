import time
from dataclasses import dataclass, field

from .prompt import Turn


@dataclass
class Session:
    turns: list[Turn] = field(default_factory=list)
    touched: float = field(default_factory=time.time)
    handoff_id: str | None = None
    handoff_at: float = 0.0


class SessionStore:
    """In-memory, short window, expires on idle. Nothing here is written to disk."""

    def __init__(self, max_turns: int = 4, ttl: int = 1800, max_sessions: int = 5000):
        self.max_turns, self.ttl, self.max_sessions = max_turns, ttl, max_sessions
        self._s: dict[str, Session] = {}

    def get(self, sid: str) -> Session:
        self._purge()
        s = self._s.get(sid)
        if s is None:
            s = self._s[sid] = Session()
        s.touched = time.time()
        return s

    def add_exchange(self, sid: str, user: str, assistant: str) -> None:
        s = self.get(sid)
        s.turns += [Turn("user", user), Turn("assistant", assistant)]
        del s.turns[: -self.max_turns * 2]

    def history(self, sid: str) -> list[Turn]:
        return list(self.get(sid).turns)

    def _purge(self) -> None:
        now = time.time()
        for k in [k for k, v in self._s.items() if now - v.touched > self.ttl]:
            del self._s[k]
        if len(self._s) > self.max_sessions:
            for k in sorted(self._s, key=lambda k: self._s[k].touched)[: len(self._s) - self.max_sessions]:
                del self._s[k]
