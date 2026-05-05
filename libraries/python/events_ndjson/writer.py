"""Atomic line-append NDJSON writer."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

from events_ndjson._validate import validate_envelope, validate_stream_payload
from events_ndjson.registry import is_registered
from events_ndjson.types import StreamError

SCHEMA_VERSION = "events-ndjson/v1"


def _utc_ts() -> str:
    """UTC ISO-8601 with millisecond precision and trailing Z."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class Writer:
    """Append-only NDJSON writer with atomic line writes.

    Each append serializes one event into a single JSON line and writes it
    plus the newline in one os.write call so concurrent writers cannot
    interleave bytes. Validation is performed against the envelope and the
    stream-specific JSON Schema before writing.
    """

    def __init__(
        self,
        stream: str,
        source: str,
        path: Union[str, Path],
        *,
        validate_payload: bool = True,
        ensure_dir: bool = True,
    ) -> None:
        if not is_registered(stream):
            raise StreamError(
                f"stream {stream!r} is not registered. "
                "Add a schema in spec/schema/v1/streams/ first."
            )
        self.stream = stream
        self.source = source
        self.path = Path(path)
        self._validate_payload = validate_payload
        self._lock = threading.Lock()
        self._fd: Optional[int] = None

        if ensure_dir:
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self._open()

    def _open(self) -> None:
        # O_APPEND on POSIX guarantees atomic single-write append. On Windows
        # CPython's os.open with O_APPEND maps to FILE_APPEND_DATA which is
        # atomic for writes <= PIPE_BUF (4096 on most systems). For longer
        # lines we still get single-write semantics via os.write below.
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY  # Windows: don't translate \n to \r\n
        self._fd = os.open(str(self.path), flags, 0o644)

    def append(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        ts: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate and append an event. Returns the serialized envelope."""
        envelope: Dict[str, Any] = {
            "ts": ts or _utc_ts(),
            "source": self.source,
            "stream": self.stream,
            "event_type": event_type,
            "payload": payload,
            "correlation_id": correlation_id or str(uuid.uuid4()),
            "schema_version": SCHEMA_VERSION,
        }

        validate_envelope(envelope)
        if self._validate_payload:
            validate_stream_payload(self.stream, payload)

        # Compact, deterministic JSON; ensure_ascii=False to allow utf-8 in
        # payload values per spec.
        line = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")

        with self._lock:
            if self._fd is None:
                self._open()
            assert self._fd is not None
            # Single write call. O_APPEND ensures the kernel positions the
            # write at the current EOF atomically with the write itself.
            written = os.write(self._fd, data)
            if written != len(data):  # pragma: no cover - kernel guarantee
                # If partial write happens we still must finish, but spec
                # promises atomicity at line level so flag it loudly.
                while written < len(data):
                    written += os.write(self._fd, data[written:])

        return envelope

    def close(self) -> None:
        with self._lock:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                finally:
                    self._fd = None

    def __enter__(self) -> "Writer":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - best effort
        try:
            self.close()
        except Exception:
            pass
