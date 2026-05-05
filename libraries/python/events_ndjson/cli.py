"""events CLI: tail, replay, diff, stats, validate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from events_ndjson import replay as replay_mod
from events_ndjson.reader import Reader
from events_ndjson.types import EnvelopeError, StreamError, ValidationError


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"validate: file not found: {path}", file=sys.stderr)
        return 2
    reader = Reader(path, strict=True, validate_payload=not args.envelope_only)
    line_no = 0
    errors = 0
    try:
        with open(path, "rb") as f:
            data = f.read()
        if not data:
            print(f"validate: {path} is empty (0 events)")
            return 0
        last_nl = data.rfind(b"\n")
        if last_nl == -1:
            print(f"validate: {path} has no complete lines", file=sys.stderr)
            return 1
        usable = data[: last_nl + 1].decode("utf-8")
        for raw in usable.split("\n"):
            if not raw.strip():
                continue
            line_no += 1
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                errors += 1
                print(f"  line {line_no}: invalid JSON: {e}", file=sys.stderr)
                continue
            try:
                reader._validate(obj)  # noqa: SLF001 - intentional reuse
            except (EnvelopeError, StreamError, ValidationError) as e:
                errors += 1
                print(f"  line {line_no}: {e}", file=sys.stderr)
    except Exception as e:  # pragma: no cover - defensive
        print(f"validate: {e}", file=sys.stderr)
        return 2

    if errors:
        print(f"validate: {errors} error(s) in {line_no} line(s)", file=sys.stderr)
        return 1
    print(f"validate: OK ({line_no} events)")
    return 0


def _cmd_tail(args: argparse.Namespace) -> int:
    reader = Reader(args.path, strict=False)
    for ev in reader.tail(follow=args.follow, from_start=not args.no_history):
        print(json.dumps(ev, ensure_ascii=False))
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    s = replay_mod.stats(args.path)
    print(json.dumps(s, indent=2, ensure_ascii=False))
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    result = replay_mod.diff(args.a, args.b)
    if result.identical:
        print(f"diff: identical ({result.matched} events)")
        return 0
    d = result.divergence
    assert d is not None
    out = {
        "diverged_at": d.index,
        "reason": d.reason,
        "a_event": d.a,
        "b_event": d.b,
        "a_count": result.a_count,
        "b_count": result.b_count,
        "matched_before_divergence": result.matched,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1


def _cmd_replay(args: argparse.Namespace) -> int:
    """Print every event in canonical form. Used as the basis for replay
    determinism checks."""
    reader = Reader(args.path)
    n = 0
    for ev in reader.stream():
        print(json.dumps(ev, ensure_ascii=False, sort_keys=True))
        n += 1
    print(f"# replay: {n} events", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="events", description="events-ndjson CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("validate", help="Validate an NDJSON event file")
    pv.add_argument("path")
    pv.add_argument(
        "--envelope-only",
        action="store_true",
        help="Skip stream payload validation; check envelope only",
    )
    pv.set_defaults(func=_cmd_validate)

    pt = sub.add_parser("tail", help="Print events as they appear")
    pt.add_argument("path")
    pt.add_argument("--follow", action="store_true", help="Keep watching for new events")
    pt.add_argument("--no-history", action="store_true", help="Skip existing events")
    pt.set_defaults(func=_cmd_tail)

    ps = sub.add_parser("stats", help="Aggregate counts by stream / event_type / source")
    ps.add_argument("path")
    ps.set_defaults(func=_cmd_stats)

    pd = sub.add_parser("diff", help="Find first divergence between two streams")
    pd.add_argument("a")
    pd.add_argument("b")
    pd.set_defaults(func=_cmd_diff)

    pr = sub.add_parser("replay", help="Print canonical events in order")
    pr.add_argument("path")
    pr.set_defaults(func=_cmd_replay)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
