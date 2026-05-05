"""Replay + diff utilities."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from events_ndjson.reader import Reader

# Fields that vary even on a faithful replay and must be ignored when comparing.
_VOLATILE_FIELDS = ("ts", "correlation_id")


@dataclass
class Divergence:
    """First point where two streams disagree."""

    index: int
    reason: str
    a: Optional[Dict[str, Any]] = None
    b: Optional[Dict[str, Any]] = None

    def __bool__(self) -> bool:
        return True


@dataclass
class DiffResult:
    """Outcome of replay.diff."""

    divergence: Optional[Divergence] = None
    a_count: int = 0
    b_count: int = 0
    matched: int = 0

    @property
    def identical(self) -> bool:
        return self.divergence is None and self.a_count == self.b_count

    def __bool__(self) -> bool:
        return self.identical


def _strip_volatile(ev: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in ev.items() if k not in _VOLATILE_FIELDS}


def _coerce_iter(
    src: Union[str, Path, Iterable[Dict[str, Any]]],
) -> Iterator[Dict[str, Any]]:
    if isinstance(src, (str, Path)):
        return iter(Reader(src).stream())
    return iter(src)


def diff(
    a: Union[str, Path, Iterable[Dict[str, Any]]],
    b: Union[str, Path, Iterable[Dict[str, Any]]],
    *,
    ignore: Sequence[str] = _VOLATILE_FIELDS,
    key: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> DiffResult:
    """Find the first divergence between two event streams.

    Compares events pairwise in order. Fields listed in `ignore` are stripped
    before comparison (default: ts and correlation_id). If `key` is given,
    each event is reduced to that value before comparison; useful for
    payload-only or event_type-only checks.
    """
    ignore_set = set(ignore)

    def _norm(ev: Dict[str, Any]) -> Any:
        if key is not None:
            return key(ev)
        return {k: v for k, v in ev.items() if k not in ignore_set}

    it_a = _coerce_iter(a)
    it_b = _coerce_iter(b)

    result = DiffResult()
    sentinel = object()
    for idx, (ea, eb) in enumerate(itertools.zip_longest(it_a, it_b, fillvalue=sentinel)):
        if ea is sentinel:
            result.b_count = idx + 1
            result.a_count = idx
            result.divergence = Divergence(idx, "stream A ended first", None, eb)  # type: ignore[arg-type]
            return result
        if eb is sentinel:
            result.a_count = idx + 1
            result.b_count = idx
            result.divergence = Divergence(idx, "stream B ended first", ea, None)  # type: ignore[arg-type]
            return result
        if _norm(ea) != _norm(eb):  # type: ignore[arg-type]
            result.a_count = idx + 1
            result.b_count = idx + 1
            result.matched = idx
            result.divergence = Divergence(idx, "events differ", ea, eb)  # type: ignore[arg-type]
            return result
        result.matched = idx + 1
        result.a_count = idx + 1
        result.b_count = idx + 1
    return result


def replay(
    src: Union[str, Path, Iterable[Dict[str, Any]]],
    handler: Callable[[Dict[str, Any]], None],
) -> int:
    """Drive `handler` for each event in src. Returns the number of events
    handled. Used to deterministically rebuild state from a stream."""
    n = 0
    for ev in _coerce_iter(src):
        handler(ev)
        n += 1
    return n


def stats(src: Union[str, Path, Iterable[Dict[str, Any]]]) -> Dict[str, Any]:
    """Aggregate counts by stream + event_type."""
    by_stream: Dict[str, int] = {}
    by_event_type: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    total = 0
    for ev in _coerce_iter(src):
        total += 1
        by_stream[ev.get("stream", "?")] = by_stream.get(ev.get("stream", "?"), 0) + 1
        by_event_type[ev.get("event_type", "?")] = (
            by_event_type.get(ev.get("event_type", "?"), 0) + 1
        )
        by_source[ev.get("source", "?")] = by_source.get(ev.get("source", "?"), 0) + 1
    return {
        "total": total,
        "by_stream": by_stream,
        "by_event_type": by_event_type,
        "by_source": by_source,
    }
