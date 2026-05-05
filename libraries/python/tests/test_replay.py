"""Replay + diff tests."""

import json

import pytest

from events_ndjson import Writer
from events_ndjson.replay import diff, replay, stats


def _seed(path, source="test", agents=("a", "b", "c")):
    with Writer(stream="cost", source=source, path=path) as w:
        for a in agents:
            w.append("agent_complete", {"agent": a, "cost_usd": 1.0})


def test_diff_identical_streams(tmp_path):
    a = tmp_path / "a.ndjson"
    b = tmp_path / "b.ndjson"
    _seed(a)
    _seed(b)
    res = diff(a, b)
    assert res.identical
    assert res.matched == 3
    assert res.divergence is None
    assert bool(res) is True


def test_diff_finds_payload_change(tmp_path):
    a = tmp_path / "a.ndjson"
    b = tmp_path / "b.ndjson"
    _seed(a, agents=("x", "y", "z"))
    _seed(b, agents=("x", "Y_DIFFERENT", "z"))
    res = diff(a, b)
    assert not res.identical
    assert res.divergence is not None
    assert res.divergence.index == 1
    assert res.divergence.reason == "events differ"
    assert res.matched == 1


def test_diff_a_ends_first(tmp_path):
    a = tmp_path / "a.ndjson"
    b = tmp_path / "b.ndjson"
    _seed(a, agents=("x", "y"))
    _seed(b, agents=("x", "y", "z"))
    res = diff(a, b)
    assert not res.identical
    assert res.divergence.reason == "stream A ended first"
    assert res.divergence.index == 2


def test_diff_b_ends_first(tmp_path):
    a = tmp_path / "a.ndjson"
    b = tmp_path / "b.ndjson"
    _seed(a, agents=("x", "y", "z"))
    _seed(b, agents=("x", "y"))
    res = diff(a, b)
    assert not res.identical
    assert res.divergence.reason == "stream B ended first"


def test_diff_ignores_volatile_fields(tmp_path):
    """Different ts and correlation_id should NOT cause divergence."""
    a = tmp_path / "a.ndjson"
    b = tmp_path / "b.ndjson"
    _seed(a)
    _seed(b)
    res = diff(a, b)
    assert res.identical


def test_diff_with_custom_key(tmp_path):
    a = tmp_path / "a.ndjson"
    b = tmp_path / "b.ndjson"
    _seed(a, source="alpha", agents=("x", "y"))
    _seed(b, source="beta", agents=("x", "y"))
    # By default, source mismatch causes divergence.
    res_default = diff(a, b)
    assert not res_default.identical
    # With key=event_type only, identical.
    res_keyed = diff(a, b, key=lambda ev: ev["event_type"])
    assert res_keyed.identical


def test_diff_catches_injected_bug(tmp_path):
    """Replay determinism: if a 'reproduction' file silently flips a value,
    diff must catch the first divergence."""
    golden = tmp_path / "golden.ndjson"
    repro = tmp_path / "repro.ndjson"
    _seed(golden, agents=("a", "b", "c", "d"))
    # The 'replayer' has a bug that drops one event in the middle.
    with Writer(stream="cost", source="test", path=repro) as w:
        w.append("agent_complete", {"agent": "a", "cost_usd": 1.0})
        w.append("agent_complete", {"agent": "b", "cost_usd": 1.0})
        # bug: skipped 'c'
        w.append("agent_complete", {"agent": "d", "cost_usd": 1.0})
    res = diff(golden, repro)
    assert not res.identical
    assert res.divergence.index == 2
    assert res.divergence.a["payload"]["agent"] == "c"


def test_replay_invokes_handler(tmp_path):
    p = tmp_path / "cost.ndjson"
    _seed(p, agents=("a", "b", "c"))
    seen = []
    n = replay(p, handler=lambda ev: seen.append(ev["payload"]["agent"]))
    assert n == 3
    assert seen == ["a", "b", "c"]


def test_replay_handles_in_memory_iterable():
    events = [
        {
            "ts": "2026-05-04T22:31:00.123Z",
            "source": "x",
            "stream": "cost",
            "event_type": "a",
            "payload": {"agent": "x", "cost_usd": 0.0},
            "correlation_id": "1",
            "schema_version": "events-ndjson/v1",
        }
    ]
    seen = []
    replay(events, handler=lambda ev: seen.append(ev))
    assert len(seen) == 1


def test_stats_counts(tmp_path):
    p = tmp_path / "cost.ndjson"
    _seed(p, agents=("a", "b", "c"))
    s = stats(p)
    assert s["total"] == 3
    assert s["by_stream"]["cost"] == 3
    assert s["by_event_type"]["agent_complete"] == 3
    assert s["by_source"]["test"] == 3


def test_stats_empty_file(tmp_path):
    p = tmp_path / "empty.ndjson"
    p.touch()
    s = stats(p)
    assert s["total"] == 0
    assert s["by_stream"] == {}
