"""Unit tests for the latency-metrics collector and the bounded session store."""

import time

import pytest
from fastapi.testclient import TestClient

from metrics import PipelineMetrics
from session_store import SessionStore
from main import app

client = TestClient(app)


# ---------------------------------------------------------------- metrics ---

def test_record_and_summary_percentiles():
    m = PipelineMetrics()
    for ms in range(1, 101):          # 0.001s .. 0.100s
        m.record("stt", ms / 1000)
    stats = m.summary()["stages"]["stt"]
    assert stats["requests"] == 100
    assert stats["errors"] == 0
    assert stats["latency_seconds"]["p50"] == pytest.approx(0.050, abs=0.002)
    assert stats["latency_seconds"]["p95"] == pytest.approx(0.095, abs=0.002)
    assert stats["latency_seconds"]["max"] == pytest.approx(0.100, abs=0.001)


def test_unknown_stage_rejected():
    m = PipelineMetrics()
    with pytest.raises(ValueError):
        m.record("warp_drive", 0.1)
    with pytest.raises(ValueError):
        m.record_error("warp_drive")


def test_track_context_manager_records_success_and_error():
    m = PipelineMetrics()
    with m.track("llm"):
        time.sleep(0.01)
    stats = m.summary()["stages"]["llm"]
    assert stats["requests"] == 1
    assert stats["latency_seconds"]["max"] >= 0.01

    with pytest.raises(RuntimeError):
        with m.track("llm"):
            raise RuntimeError("boom")
    stats = m.summary()["stages"]["llm"]
    assert stats["errors"] == 1
    assert stats["requests"] == 1  # failed call is not a latency sample


def test_rolling_window_caps_samples():
    m = PipelineMetrics(window=10)
    for _ in range(25):
        m.record("tts", 0.01)
    stats = m.summary()["stages"]["tts"]
    assert stats["requests"] == 25        # total count keeps growing
    assert stats["window_size"] == 10     # window stays bounded


def test_reset_clears_everything():
    m = PipelineMetrics()
    m.record("stt", 0.5)
    m.record_error("tts")
    m.reset()
    s = m.summary()["stages"]
    assert s["stt"]["requests"] == 0
    assert s["tts"]["errors"] == 0


# ---------------------------------------------------------- session store ---

def test_session_store_dict_compatibility():
    s = SessionStore()
    s["abc"] = {"history": []}
    assert "abc" in s
    assert s["abc"] == {"history": []}
    del s["abc"]
    assert "abc" not in s


def test_session_store_ttl_eviction():
    s = SessionStore(ttl_seconds=0.05)
    s["old"] = 1
    time.sleep(0.06)
    assert "old" not in s
    assert len(s) == 0


def test_session_store_lru_cap():
    s = SessionStore(max_sessions=2)
    s["a"] = 1
    s["b"] = 2
    _ = s["a"]        # touch "a" so "b" is the LRU entry
    s["c"] = 3
    assert "a" in s and "c" in s and "b" not in s


def test_get_or_create():
    s = SessionStore()
    created = s.get_or_create("x", lambda: {"n": 1})
    again = s.get_or_create("x", lambda: {"n": 2})
    assert created is again


def test_session_store_validation():
    with pytest.raises(ValueError):
        SessionStore(ttl_seconds=0)
    with pytest.raises(ValueError):
        SessionStore(max_sessions=0)


# ------------------------------------------------------------- /metrics -----

def test_metrics_endpoint_shape():
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    assert "uptime_seconds" in body
    assert set(body["stages"]) == {"stt", "rag_retrieval", "llm", "tts", "converse"}
    for stage in body["stages"].values():
        assert {"requests", "errors", "window_size", "latency_seconds"} <= set(stage)
    assert body["sessions"]["max_sessions"] >= 1
