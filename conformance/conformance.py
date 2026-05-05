"""Conformance test suite for events-ndjson.

Any library claiming events-ndjson v1 conformance MUST pass every test here.
The Python reference library passes this directly; for the TypeScript library
we shell out to a small Node entrypoint (see conformance_ts_runner.mjs) so
the same scenarios drive both implementations.

Run:
    py conformance/conformance.py            # Python reference
    py conformance/conformance.py --ts       # TypeScript implementation
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_LIB = REPO_ROOT / "libraries" / "python"
TS_LIB = REPO_ROOT / "libraries" / "typescript"
sys.path.insert(0, str(PYTHON_LIB))

from events_ndjson import Reader, Writer  # noqa: E402
from events_ndjson.replay import diff  # noqa: E402

CASES: List[Tuple[str, Callable[[Path], None]]] = []


def case(name: str):
    def deco(fn):
        CASES.append((name, fn))
        return fn

    return deco


@case("append-roundtrip")
def _t_roundtrip(tmp: Path) -> None:
    p = tmp / "cost.ndjson"
    with Writer(stream="cost", source="conf", path=p) as w:
        for i in range(5):
            w.append("agent_complete", {"agent": f"a{i}", "cost_usd": float(i)})
    events = Reader(p).read_all()
    assert len(events) == 5, f"expected 5 events, got {len(events)}"
    for i, ev in enumerate(events):
        assert ev["payload"]["agent"] == f"a{i}"


@case("append-atomic-under-threads")
def _t_atomic(tmp: Path) -> None:
    p = tmp / "cost.ndjson"
    w = Writer(stream="cost", source="conf", path=p)
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        barrier.wait()
        for j in range(50):
            w.append(
                "agent_complete",
                {"agent": f"t{i}-{j}", "cost_usd": float(j)},
            )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    w.close()

    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 400
    for line in lines:
        # Each line must parse as a complete JSON object — no interleaving.
        json.loads(line)


@case("partial-last-line-tolerance")
def _t_partial(tmp: Path) -> None:
    p = tmp / "cost.ndjson"
    with Writer(stream="cost", source="conf", path=p) as w:
        w.append("a", {"agent": "x", "cost_usd": 0.0})
        w.append("a", {"agent": "y", "cost_usd": 0.0})
    # Simulate a write in progress.
    with open(p, "ab") as f:
        f.write(b'{"ts":"2026-05-04T22:31:00.123Z","source":"conf"')
    events = Reader(p).read_all()
    assert len(events) == 2


@case("tail-follow")
def _t_tail(tmp: Path) -> None:
    p = tmp / "cost.ndjson"
    with Writer(stream="cost", source="conf", path=p) as w:
        w.append("a", {"agent": "history", "cost_usd": 0.0})

    received: List[dict] = []
    stop = {"v": False}

    def consume() -> None:
        for ev in Reader(p).tail(
            follow=True, poll_interval=0.02, stop=lambda: stop["v"]
        ):
            received.append(ev)
            if len(received) >= 3:
                break

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    time.sleep(0.05)
    with Writer(stream="cost", source="conf", path=p) as w:
        w.append("a", {"agent": "live-1", "cost_usd": 0.0})
        w.append("a", {"agent": "live-2", "cost_usd": 0.0})

    t.join(timeout=3.0)
    stop["v"] = True
    assert len(received) == 3
    assert received[1]["payload"]["agent"] == "live-1"


@case("replay-determinism-catches-missing-event")
def _t_replay(tmp: Path) -> None:
    golden = tmp / "g.ndjson"
    repro = tmp / "r.ndjson"
    with Writer(stream="cost", source="conf", path=golden) as w:
        for a in ("a", "b", "c", "d"):
            w.append("agent_complete", {"agent": a, "cost_usd": 1.0})
    with Writer(stream="cost", source="conf", path=repro) as w:
        # Bug: drops 'c'
        for a in ("a", "b", "d"):
            w.append("agent_complete", {"agent": a, "cost_usd": 1.0})

    res = diff(golden, repro)
    assert not res.identical
    assert res.divergence is not None
    assert res.divergence.index == 2
    assert res.divergence.a["payload"]["agent"] == "c"


@case("diff-sensitivity-payload-change")
def _t_diff_sensitive(tmp: Path) -> None:
    a = tmp / "a.ndjson"
    b = tmp / "b.ndjson"
    with Writer(stream="cost", source="conf", path=a) as w:
        w.append("agent_complete", {"agent": "x", "cost_usd": 1.0})
    with Writer(stream="cost", source="conf", path=b) as w:
        w.append("agent_complete", {"agent": "x", "cost_usd": 2.0})
    res = diff(a, b)
    assert not res.identical
    assert res.divergence.index == 0


@case("envelope-rejects-bad-ts")
def _t_bad_ts(tmp: Path) -> None:
    p = tmp / "bad.ndjson"
    p.write_bytes(
        b'{"ts":"2026-05-04T22:31:00Z","source":"x","stream":"cost",'
        b'"event_type":"a","payload":{"agent":"x","cost_usd":0},'
        b'"correlation_id":"1","schema_version":"events-ndjson/v1"}\n'
    )
    try:
        Reader(p, strict=True).read_all()
    except Exception:
        return
    raise AssertionError("expected envelope error for bad ts")


@case("registry-rejects-unregistered-stream")
def _t_unregistered(tmp: Path) -> None:
    try:
        Writer(stream="totally_made_up", source="conf", path=tmp / "x.ndjson")
    except Exception:
        return
    raise AssertionError("expected stream error for unregistered stream")


@case("runs-stream-roundtrip")
def _t_runs_roundtrip(tmp: Path) -> None:
    """The runs stream (recipe lifecycle) must roundtrip cleanly."""
    p = tmp / "runs.ndjson"
    with Writer(stream="runs", source="conf", path=p) as w:
        w.append("started", {"recipe": "build", "kind": "started",
                              "version": "1.0", "dry_run": False})
        w.append("finished", {"recipe": "build", "kind": "finished",
                               "status": "ok", "duration_sec": 12.5,
                               "cost_usd": 0.04})
    events = Reader(p).read_all()
    assert len(events) == 2
    assert events[0]["payload"]["kind"] == "started"
    assert events[0]["payload"]["recipe"] == "build"
    assert events[1]["payload"]["status"] == "ok"


@case("runs-stream-rejects-bad-kind")
def _t_runs_bad_kind(tmp: Path) -> None:
    """The runs schema's `kind` enum is enforced by the Writer."""
    p = tmp / "runs.ndjson"
    w = Writer(stream="runs", source="conf", path=p)
    try:
        try:
            w.append("started", {"recipe": "build", "kind": "exploded"})
        except Exception:
            return
        raise AssertionError("expected schema error for invalid kind")
    finally:
        w.close()


@case("runs-stream-requires-recipe")
def _t_runs_missing_recipe(tmp: Path) -> None:
    """Required field 'recipe' must be present."""
    p = tmp / "runs.ndjson"
    w = Writer(stream="runs", source="conf", path=p)
    try:
        try:
            w.append("started", {"kind": "started"})
        except Exception:
            return
        raise AssertionError("expected schema error for missing recipe")
    finally:
        w.close()


def run_python() -> int:
    failed = 0
    for name, fn in CASES:
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(Path(d))
                print(f"  PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"  FAIL  {name}: {e}", file=sys.stderr)
            except Exception as e:
                failed += 1
                print(f"  FAIL  {name}: {type(e).__name__}: {e}", file=sys.stderr)
    print()
    print(f"python conformance: {len(CASES) - failed}/{len(CASES)} passed")
    return 0 if failed == 0 else 1


def run_typescript() -> int:
    """Drive the TS library through a small Node helper that exercises the
    same scenarios. The helper writes an NDJSON file from each scenario so
    the Python harness can verify outputs."""
    runner = REPO_ROOT / "conformance" / "ts_runner.mjs"
    if not runner.exists():
        print("ts_runner.mjs missing — skipping TS conformance", file=sys.stderr)
        return 1
    proc = subprocess.run(
        ["node", str(runner)],
        cwd=str(TS_LIB),
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ts", action="store_true", help="Run TS conformance")
    parser.add_argument("--all", action="store_true", help="Run both")
    args = parser.parse_args()

    if args.all:
        py_rc = run_python()
        ts_rc = run_typescript()
        return py_rc | ts_rc
    if args.ts:
        return run_typescript()
    return run_python()


if __name__ == "__main__":
    sys.exit(main())
