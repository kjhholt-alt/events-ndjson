"""Writer tests."""

import json
import os
import re
import threading

import pytest

from events_ndjson import Writer
from events_ndjson.types import EnvelopeError, StreamError


def test_writer_appends_single_event(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("agent_complete", {"agent": "x", "cost_usd": 0.5})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["stream"] == "cost"
    assert obj["source"] == "test"
    assert obj["event_type"] == "agent_complete"
    assert obj["payload"] == {"agent": "x", "cost_usd": 0.5}
    assert obj["schema_version"] == "events-ndjson/v1"


def test_writer_generates_iso_ts(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("agent_complete", {"agent": "x", "cost_usd": 0.5})
    obj = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", obj["ts"])


def test_writer_generates_correlation_id(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("agent_complete", {"agent": "x", "cost_usd": 0.5})
    obj = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert obj["correlation_id"]
    # default is uuid4 -> 36 chars
    assert len(obj["correlation_id"]) == 36


def test_writer_accepts_explicit_correlation_id(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("a", {"agent": "x", "cost_usd": 0.0}, correlation_id="my-corr-id")
    obj = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert obj["correlation_id"] == "my-corr-id"


def test_writer_accepts_explicit_ts(tmp_path):
    p = tmp_path / "cost.ndjson"
    ts = "2026-05-04T22:31:00.123Z"
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("a", {"agent": "x", "cost_usd": 0.0}, ts=ts)
    obj = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert obj["ts"] == ts


def test_writer_appends_in_order(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        for i in range(50):
            w.append("a", {"agent": f"a{i}", "cost_usd": float(i)})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 50
    for i, line in enumerate(lines):
        obj = json.loads(line)
        assert obj["payload"]["agent"] == f"a{i}"


def test_writer_rejects_unregistered_stream(tmp_path):
    with pytest.raises(StreamError):
        Writer(stream="not_a_real_stream", source="test", path=tmp_path / "x.ndjson")


def test_writer_validates_payload_by_default(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        with pytest.raises(StreamError):
            w.append("agent_complete", {"missing": "agent"})


def test_writer_payload_validation_can_be_disabled(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p, validate_payload=False) as w:
        w.append("agent_complete", {"this_is_not_in_schema": True})
    assert p.exists()


def test_writer_atomic_under_threads(tmp_path):
    """Concurrent appenders should never produce a partial line."""
    p = tmp_path / "cost.ndjson"
    w = Writer(stream="cost", source="test", path=p)
    barrier = threading.Barrier(8)

    def worker(i: int):
        barrier.wait()
        for j in range(50):
            w.append(
                "agent_complete",
                {"agent": f"thread-{i}-{j}", "cost_usd": float(j)},
            )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    w.close()

    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 8 * 50
    for line in lines:
        obj = json.loads(line)
        assert obj["stream"] == "cost"


def test_writer_creates_parent_dir(tmp_path):
    p = tmp_path / "nested" / "deeper" / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("agent_complete", {"agent": "x", "cost_usd": 0.0})
    assert p.exists()


def test_writer_appends_across_open_close(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("a", {"agent": "first", "cost_usd": 1.0})
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("a", {"agent": "second", "cost_usd": 2.0})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["payload"]["agent"] == "first"
    assert json.loads(lines[1])["payload"]["agent"] == "second"


def test_writer_rejects_extra_payload_field(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        with pytest.raises(StreamError):
            w.append("a", {"agent": "x", "cost_usd": 0.0, "stowaway": True})


def test_writer_writes_lf_not_crlf(tmp_path):
    """Even on Windows the writer must emit only \n, never \r\n."""
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("a", {"agent": "x", "cost_usd": 0.0})
        w.append("a", {"agent": "y", "cost_usd": 0.0})
    raw = p.read_bytes()
    assert b"\r\n" not in raw
    assert raw.count(b"\n") == 2
