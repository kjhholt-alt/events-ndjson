"""Type aliases and exception hierarchy."""

from __future__ import annotations

from typing import Any, Dict, TypedDict


class Event(TypedDict):
    ts: str
    source: str
    stream: str
    event_type: str
    payload: Dict[str, Any]
    correlation_id: str
    schema_version: str


class EventsNdjsonError(Exception):
    """Base class for all events-ndjson errors."""


class EnvelopeError(EventsNdjsonError):
    """Envelope failed validation against the v1 envelope schema."""


class StreamError(EventsNdjsonError):
    """Stream is unregistered or payload failed the stream schema."""


class ValidationError(EventsNdjsonError):
    """Generic validation error surfaced to the caller."""
