"""Reader tests."""

import json
import threading
import time

import pytest

from events_ndjson import Reader, Writer
from events_ndjson.types import EnvelopeError, ValidationError


def _seed(path, n=5, source="test"):
    with Writer(stream="cost", source=source, path=path) as w:
        for i in range(n):
            w.append("agent_complete", {"agent": f"a{i}", "cost_usd": float(i)})


def test_reader_returns_empty_for_missing_file(tmp_path):
    r = Reader(tmp_path / "nope.ndjson")
    assert r.read_all() == []


def test_reader_returns_empty_for_empty_file(tmp_path):
    p = tmp_path / "empty.ndjson"
    p.touch()
    r = Reader(p)
    assert r.read_all() == []


def test_reader_reads_all_events(tmp_path):
    p = tmp_path / "cost.ndjson"
    _seed(p, n=10)
    events = list(Reader(p).stream())
    assert len(events) == 10
    for i, ev in enumerate(events):
        assert ev["payload"]["agent"] == f"a{i}"


def test_reader_skips_partial_last_line(tmp_path):
    p = tmp_path / "cost.ndjson"
    _seed(p, n=3)
    # Append a partial line (mid-write simulation)
    with open(p, "ab") as f:
        f.write(b'{"ts":"2026-05-04T22:31:00.123Z","source":"x"')  # no newline
    events = Reader(p).read_all()
    assert len(events) == 3


def test_reader_strict_rejects_invalid_json(tmp_path):
    p = tmp_path / "bad.ndjson"
    p.write_bytes(b'{"not":"a valid envelope"}\n')
    with pytest.raises((EnvelopeError, ValidationError)):
        Reader(p, strict=True).read_all()


def test_reader_lenient_skips_invalid(tmp_path):
    p = tmp_path / "mix.ndjson"
    _seed(p, n=2)
    with open(p, "ab") as f:
        f.write(b'{"not":"valid"}\n')
        f.write(b"not even json\n")
    _seed_more = Writer(stream="cost", source="test", path=p)
    _seed_more.append("a", {"agent": "tail", "cost_usd": 0.0})
    _seed_more.close()
    events = Reader(p, strict=False).read_all()
    # Only valid envelopes survive
    assert len(events) == 3
    assert events[-1]["payload"]["agent"] == "tail"


def test_reader_filter_by_stream(tmp_path):
    cost_p = tmp_path / "cost.ndjson"
    _seed(cost_p, n=5)
    matched = Reader(cost_p).filter(stream="cost").events()
    assert len(matched) == 5
    none = Reader(cost_p).filter(stream="pacing").events()
    assert none == []


def test_reader_filter_by_event_type(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("agent_complete", {"agent": "x", "cost_usd": 1.0})
        w.append("agent_failed", {"agent": "y", "cost_usd": 0.0})
    matched = Reader(p).filter(event_type="agent_failed").events()
    assert len(matched) == 1
    assert matched[0]["payload"]["agent"] == "y"


def test_reader_filter_by_source(tmp_path):
    p = tmp_path / "cost.ndjson"
    _seed(p, n=2, source="alpha")
    _seed(p, n=2, source="beta")
    alpha = Reader(p).filter(source="alpha").events()
    beta = Reader(p).filter(source="beta").events()
    assert len(alpha) == 2
    assert len(beta) == 2


def test_reader_filter_by_correlation_id(tmp_path):
    p = tmp_path / "cost.ndjson"
    with Writer(stream="cost", source="t", path=p) as w:
        w.append("a", {"agent": "x", "cost_usd": 0.0}, correlation_id="A")
        w.append("a", {"agent": "y", "cost_usd": 0.0}, correlation_id="B")
        w.append("a", {"agent": "z", "cost_usd": 0.0}, correlation_id="A")
    matched = Reader(p).filter(correlation_id="A").events()
    assert len(matched) == 2


def test_reader_filter_predicate(tmp_path):
    p = tmp_path / "cost.ndjson"
    _seed(p, n=5)
    high = (
        Reader(p)
        .filter(predicate=lambda ev: ev["payload"]["cost_usd"] >= 3.0)
        .events()
    )
    assert {e["payload"]["agent"] for e in high} == {"a3", "a4"}


def test_reader_tail_no_follow(tmp_path):
    p = tmp_path / "cost.ndjson"
    _seed(p, n=4)
    events = list(Reader(p).tail(follow=False))
    assert len(events) == 4


def test_reader_tail_follow_picks_up_new_events(tmp_path):
    p = tmp_path / "cost.ndjson"
    _seed(p, n=2)
    received = []
    stop_flag = {"v": False}

    def consume():
        for ev in Reader(p).tail(
            follow=True, poll_interval=0.02, stop=lambda: stop_flag["v"]
        ):
            received.append(ev)
            if len(received) >= 4:
                break

    t = threading.Thread(target=consume, daemon=True)
    t.start()

    time.sleep(0.1)  # let tailer reach EOF
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("a", {"agent": "live-1", "cost_usd": 0.0})
        w.append("a", {"agent": "live-2", "cost_usd": 0.0})

    t.join(timeout=3.0)
    stop_flag["v"] = True
    assert len(received) == 4
    assert received[2]["payload"]["agent"] == "live-1"
    assert received[3]["payload"]["agent"] == "live-2"


def test_reader_tail_no_history(tmp_path):
    p = tmp_path / "cost.ndjson"
    _seed(p, n=3)
    received = []
    stop_flag = {"v": False}

    def consume():
        for ev in Reader(p).tail(
            follow=True,
            from_start=False,
            poll_interval=0.02,
            stop=lambda: stop_flag["v"],
        ):
            received.append(ev)

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    time.sleep(0.1)
    with Writer(stream="cost", source="test", path=p) as w:
        w.append("a", {"agent": "fresh", "cost_usd": 0.0})
    time.sleep(0.2)
    stop_flag["v"] = True
    t.join(timeout=2.0)
    assert len(received) == 1
    assert received[0]["payload"]["agent"] == "fresh"


def test_reader_handles_blank_lines(tmp_path):
    p = tmp_path / "blanks.ndjson"
    _seed(p, n=2)
    with open(p, "ab") as f:
        f.write(b"\n\n")
    _seed_more = Writer(stream="cost", source="test", path=p)
    _seed_more.append("a", {"agent": "after", "cost_usd": 0.0})
    _seed_more.close()
    events = Reader(p).read_all()
    assert len(events) == 3
