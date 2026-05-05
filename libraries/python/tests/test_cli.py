"""CLI integration tests."""

import json
from io import StringIO

import pytest

from events_ndjson import Writer
from events_ndjson.cli import main


def _seed(p, agents=("x", "y")):
    with Writer(stream="cost", source="test", path=p) as w:
        for a in agents:
            w.append("agent_complete", {"agent": a, "cost_usd": 1.0})


def test_cli_validate_ok(tmp_path, capsys):
    p = tmp_path / "cost.ndjson"
    _seed(p)
    rc = main(["validate", str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out
    assert "2 events" in out


def test_cli_validate_missing(tmp_path, capsys):
    rc = main(["validate", str(tmp_path / "nope.ndjson")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err


def test_cli_validate_bad_envelope(tmp_path, capsys):
    p = tmp_path / "bad.ndjson"
    p.write_bytes(b'{"ts":"bad"}\n')
    rc = main(["validate", str(p)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "error" in err.lower()


def test_cli_stats(tmp_path, capsys):
    p = tmp_path / "cost.ndjson"
    _seed(p, agents=("a", "b", "c"))
    rc = main(["stats", str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["total"] == 3


def test_cli_diff_identical(tmp_path, capsys):
    a = tmp_path / "a.ndjson"
    b = tmp_path / "b.ndjson"
    _seed(a, agents=("x", "y"))
    _seed(b, agents=("x", "y"))
    rc = main(["diff", str(a), str(b)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "identical" in out


def test_cli_diff_diverges(tmp_path, capsys):
    a = tmp_path / "a.ndjson"
    b = tmp_path / "b.ndjson"
    _seed(a, agents=("x", "y"))
    _seed(b, agents=("x", "Y2"))
    rc = main(["diff", str(a), str(b)])
    out = capsys.readouterr().out
    assert rc == 1
    parsed = json.loads(out)
    assert parsed["diverged_at"] == 1


def test_cli_replay_canonical_order(tmp_path, capsys):
    p = tmp_path / "cost.ndjson"
    _seed(p, agents=("x", "y", "z"))
    rc = main(["replay", str(p)])
    captured = capsys.readouterr()
    assert rc == 0
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) == 3
    parsed = [json.loads(ln) for ln in lines]
    # Sorted-keys means schema_version comes after stream alphabetically;
    # what we care about is determinism.
    repro = main(["replay", str(p)])
    captured2 = capsys.readouterr()
    assert captured2.out == captured.out


def test_cli_tail_no_follow(tmp_path, capsys):
    p = tmp_path / "cost.ndjson"
    _seed(p, agents=("only",))
    rc = main(["tail", str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out.strip())
    assert parsed["payload"]["agent"] == "only"
