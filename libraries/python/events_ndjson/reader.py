"""NDJSON reader with tail/follow, partial-line tolerance, and filtering."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

from events_ndjson._validate import validate_envelope, validate_stream_payload
from events_ndjson.types import EnvelopeError, StreamError, ValidationError


@dataclass
class ReaderResult:
    events: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class Reader:
    """Append-aware NDJSON reader.

    - Handles partial last line (mid-write) by ignoring bytes after the last
      complete '\n' until more data is available.
    - `tail(follow=True)` yields events forever, sleeping briefly between
      poll cycles when at EOF.
    - `filter(...)` returns a chained Reader-like object whose `stream()`
      iterates events matching a predicate.
    """

    def __init__(
        self,
        path: Union[str, Path],
        *,
        strict: bool = True,
        validate_payload: bool = True,
    ) -> None:
        self.path = Path(path)
        self.strict = strict
        self.validate_payload = validate_payload

    # ----- internal helpers -------------------------------------------------

    def _validate(self, obj: Dict[str, Any]) -> None:
        validate_envelope(obj)
        if self.validate_payload:
            validate_stream_payload(obj["stream"], obj["payload"])

    def _parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            if self.strict:
                raise ValidationError(f"invalid JSON: {e}") from e
            return None
        try:
            self._validate(obj)
        except (EnvelopeError, StreamError) as e:
            if self.strict:
                raise
            return None
        return obj

    # ----- public API -------------------------------------------------------

    def read_all(self) -> List[Dict[str, Any]]:
        """Read every complete event in the file. Ignores a trailing partial
        line (no terminating newline)."""
        events: List[Dict[str, Any]] = []
        if not self.path.exists():
            return events
        with open(self.path, "rb") as f:
            data = f.read()
        # Find the last newline; anything after it is partial and skipped.
        if not data:
            return events
        last_nl = data.rfind(b"\n")
        if last_nl == -1:
            # Whole file is a partial line, nothing complete yet.
            return events
        usable = data[: last_nl + 1].decode("utf-8")
        for raw in usable.split("\n"):
            ev = self._parse_line(raw)
            if ev is not None:
                events.append(ev)
        return events

    def stream(self) -> Iterator[Dict[str, Any]]:
        for ev in self.read_all():
            yield ev

    def tail(
        self,
        *,
        follow: bool = False,
        from_start: bool = True,
        poll_interval: float = 0.1,
        stop: Optional[Callable[[], bool]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield events as they appear in the file.

        If follow=False, behaves like read_all but as an iterator.
        If follow=True, after EOF poll for more bytes every poll_interval
        seconds until stop() returns True (if provided).
        """
        if not self.path.exists():
            self.path.touch()

        with open(self.path, "rb") as f:
            if not from_start:
                f.seek(0, os.SEEK_END)

            buffer = b""
            while True:
                chunk = f.read(65536)
                if chunk:
                    buffer += chunk
                    while True:
                        nl = buffer.find(b"\n")
                        if nl == -1:
                            break
                        raw = buffer[:nl].decode("utf-8")
                        buffer = buffer[nl + 1 :]
                        ev = self._parse_line(raw)
                        if ev is not None:
                            yield ev
                else:
                    if not follow:
                        return
                    if stop is not None and stop():
                        return
                    time.sleep(poll_interval)

    def filter(
        self,
        *,
        stream: Optional[str] = None,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
        predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> "FilteredReader":
        return FilteredReader(
            self,
            stream=stream,
            event_type=event_type,
            source=source,
            correlation_id=correlation_id,
            predicate=predicate,
        )


class FilteredReader:
    def __init__(
        self,
        reader: Reader,
        *,
        stream: Optional[str] = None,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
        predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> None:
        self._reader = reader
        self._stream = stream
        self._event_type = event_type
        self._source = source
        self._correlation_id = correlation_id
        self._predicate = predicate

    def _matches(self, ev: Dict[str, Any]) -> bool:
        if self._stream is not None and ev.get("stream") != self._stream:
            return False
        if self._event_type is not None and ev.get("event_type") != self._event_type:
            return False
        if self._source is not None and ev.get("source") != self._source:
            return False
        if (
            self._correlation_id is not None
            and ev.get("correlation_id") != self._correlation_id
        ):
            return False
        if self._predicate is not None and not self._predicate(ev):
            return False
        return True

    def stream(self) -> Iterator[Dict[str, Any]]:
        for ev in self._reader.stream():
            if self._matches(ev):
                yield ev

    def events(self) -> List[Dict[str, Any]]:
        return list(self.stream())
