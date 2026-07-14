"""Bounded, TTL-evicting session store.

The original implementation kept conversation sessions in a bare module-level
dict, which grows without bound on a long-running server — every new
session_id leaks its full conversation history until the process restarts.

SessionStore is a drop-in replacement for the dict operations the app uses
(`in`, `[]`, `del`) that additionally:

* expires sessions idle longer than ``ttl_seconds`` (lazy eviction — no
  background task needed), and
* caps the number of live sessions at ``max_sessions``, evicting the least
  recently used session when full.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Iterator


class SessionStore:
    def __init__(self, ttl_seconds: float = 3600.0, max_sessions: int = 1000):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_sessions <= 0:
            raise ValueError("max_sessions must be positive")
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._lock = threading.Lock()
        # session_id -> (value, last_access_monotonic); ordered by recency
        self._data: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()

    # -- internal ---------------------------------------------------------
    def _evict_expired_locked(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, ts) in self._data.items() if now - ts > self._ttl]
        for k in expired:
            del self._data[k]

    # -- dict-compatible API ----------------------------------------------
    def __contains__(self, session_id: str) -> bool:
        with self._lock:
            self._evict_expired_locked()
            return session_id in self._data

    def __getitem__(self, session_id: str) -> Any:
        with self._lock:
            self._evict_expired_locked()
            value, _ = self._data[session_id]  # raises KeyError if missing
            self._data[session_id] = (value, time.monotonic())
            self._data.move_to_end(session_id)
            return value

    def __setitem__(self, session_id: str, value: Any) -> None:
        with self._lock:
            self._evict_expired_locked()
            if session_id not in self._data and len(self._data) >= self._max:
                self._data.popitem(last=False)  # drop least recently used
            self._data[session_id] = (value, time.monotonic())
            self._data.move_to_end(session_id)

    def __delitem__(self, session_id: str) -> None:
        with self._lock:
            del self._data[session_id]

    def __len__(self) -> int:
        with self._lock:
            self._evict_expired_locked()
            return len(self._data)

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            self._evict_expired_locked()
            return iter(list(self._data))

    # -- convenience --------------------------------------------------------
    def get_or_create(self, session_id: str, factory: Callable[[], Any]) -> Any:
        """Return the stored session, creating it with ``factory`` if absent."""
        with self._lock:
            self._evict_expired_locked()
            if session_id in self._data:
                value, _ = self._data[session_id]
            else:
                if len(self._data) >= self._max:
                    self._data.popitem(last=False)
                value = factory()
            self._data[session_id] = (value, time.monotonic())
            self._data.move_to_end(session_id)
            return value

    def stats(self) -> dict:
        with self._lock:
            self._evict_expired_locked()
            return {
                "active_sessions": len(self._data),
                "max_sessions": self._max,
                "ttl_seconds": self._ttl,
            }
