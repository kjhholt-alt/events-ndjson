"""Internal validation helpers shared by Writer and Reader."""

from __future__ import annotations

import re
from typing import Any, Dict

from jsonschema import Draft202012Validator

from events_ndjson.registry import envelope_schema, stream_schema
from events_ndjson.types import EnvelopeError, StreamError

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
_SCHEMA_VERSION = "events-ndjson/v1"

_envelope_validator = Draft202012Validator(envelope_schema())


def validate_envelope(obj: Any) -> None:
    """Raise EnvelopeError if obj is not a valid envelope."""
    if not isinstance(obj, dict):
        raise EnvelopeError("event must be a JSON object")
    errors = sorted(_envelope_validator.iter_errors(obj), key=lambda e: e.path)
    if errors:
        msgs = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
        raise EnvelopeError(f"envelope validation failed: {msgs}")
    if not _TS_RE.match(obj["ts"]):
        raise EnvelopeError(f"ts must match YYYY-MM-DDTHH:MM:SS.sssZ, got {obj['ts']!r}")
    if obj["schema_version"] != _SCHEMA_VERSION:
        raise EnvelopeError(
            f"schema_version must be {_SCHEMA_VERSION!r}, got {obj['schema_version']!r}"
        )


def validate_stream_payload(stream: str, payload: Dict[str, Any]) -> None:
    """Raise StreamError if payload fails the stream schema."""
    schema = stream_schema(stream)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        msgs = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
        raise StreamError(f"stream {stream!r} payload invalid: {msgs}")


def validate_event(obj: Any) -> None:
    validate_envelope(obj)
    validate_stream_payload(obj["stream"], obj["payload"])
