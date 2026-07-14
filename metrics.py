"""In-process latency and request metrics for the voice pipeline.

Tracks per-stage latencies (STT, RAG retrieval, LLM generation, TTS, and the
end-to-end /converse pipeline) in fixed-size rolling windows and exposes
percentile summaries. Designed to answer the question every real-time voice
system lives or dies by: "where does my latency budget go?"

No external dependencies; safe under FastAPI's async concurrency because all
mutation happens synchronously between awaits on the event loop, and a lock
guards against multi-threaded use (e.g. sync test clients).
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Deque, Dict, Iterator

# Pipeline stages we track. "converse" is the end-to-end voice round trip.
STAGES = ("stt", "rag_retrieval", "llm", "tts", "converse")

_WINDOW = 500  # samples kept per stage


def _percentile(sorted_values, pct: float) -> float:
    """Nearest-rank percentile on a pre-sorted list."""
    if not sorted_values:
        return 0.0
    k = max(0, min(len(sorted_values) - 1, math.ceil(pct / 100 * len(sorted_values)) - 1))
    return sorted_values[k]


class PipelineMetrics:
    """Rolling-window latency metrics, one window per pipeline stage."""

    def __init__(self, window: int = _WINDOW):
        self._lock = threading.Lock()
        self._window = window
        self._latencies: Dict[str, Deque[float]] = {s: deque(maxlen=window) for s in STAGES}
        self._counts: Dict[str, int] = {s: 0 for s in STAGES}
        self._errors: Dict[str, int] = {s: 0 for s in STAGES}
        self._started_at = datetime.now(timezone.utc)

    def record(self, stage: str, seconds: float) -> None:
        if stage not in self._latencies:
            raise ValueError(f"Unknown stage: {stage!r}. Expected one of {STAGES}.")
        with self._lock:
            self._latencies[stage].append(seconds)
            self._counts[stage] += 1

    def record_error(self, stage: str) -> None:
        if stage not in self._errors:
            raise ValueError(f"Unknown stage: {stage!r}. Expected one of {STAGES}.")
        with self._lock:
            self._errors[stage] += 1

    @contextmanager
    def track(self, stage: str) -> Iterator[None]:
        """Context manager: times the wrapped block, records errors on raise."""
        start = time.perf_counter()
        try:
            yield
        except Exception:
            self.record_error(stage)
            raise
        else:
            self.record(stage, time.perf_counter() - start)

    def summary(self) -> Dict:
        """Snapshot of counts, errors, and latency percentiles per stage."""
        with self._lock:
            stages = {}
            for stage in STAGES:
                values = sorted(self._latencies[stage])
                stages[stage] = {
                    "requests": self._counts[stage],
                    "errors": self._errors[stage],
                    "window_size": len(values),
                    "latency_seconds": {
                        "p50": round(_percentile(values, 50), 4),
                        "p95": round(_percentile(values, 95), 4),
                        "p99": round(_percentile(values, 99), 4),
                        "mean": round(sum(values) / len(values), 4) if values else 0.0,
                        "max": round(max(values), 4) if values else 0.0,
                    },
                }
            return {
                "uptime_seconds": round(
                    (datetime.now(timezone.utc) - self._started_at).total_seconds(), 1
                ),
                "stages": stages,
            }

    def reset(self) -> None:
        with self._lock:
            for s in STAGES:
                self._latencies[s].clear()
                self._counts[s] = 0
                self._errors[s] = 0
            self._started_at = datetime.now(timezone.utc)


# Module-level singleton used by the app
pipeline_metrics = PipelineMetrics()
