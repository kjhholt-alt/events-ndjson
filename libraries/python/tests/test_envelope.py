"""Envelope validation tests."""

import pytest

from events_ndjson._validate import validate_envelope, validate_event
from events_ndjson.types import EnvelopeError, StreamError


def _good_envelope(**overrides):
    base = {
        "ts": "2026-05-04T22:31:00.123Z",
        "source": "test-suite",
        "stream": "cost",
        "event_type": "agent_complete",
        "payload": {"agent": "x", "cost_usd": 0.1},
        "correlation_id": "abc-123",
        "schema_version": "events-ndjson/v1",
    }
    base.update(overrides)
    return base


def test_envelope_accepts_minimum_valid():
    validate_envelope(_good_envelope())


def test_envelope_rejects_non_dict():
    with pytest.raises(EnvelopeError):
        validate_envelope("not an object")


def test_envelope_requires_ts():
    obj = _good_envelope()
    obj.pop("ts")
    with pytest.raises(EnvelopeError):
        validate_envelope(obj)


def test_envelope_requires_source():
    obj = _good_envelope()
    obj.pop("source")
    with pytest.raises(EnvelopeError):
        validate_envelope(obj)


def test_envelope_requires_stream():
    obj = _good_envelope()
    obj.pop("stream")
    with pytest.raises(EnvelopeError):
        validate_envelope(obj)


def test_envelope_requires_event_type():
    obj = _good_envelope()
    obj.pop("event_type")
    with pytest.raises(EnvelopeError):
        validate_envelope(obj)


def test_envelope_requires_payload():
    obj = _good_envelope()
    obj.pop("payload")
    with pytest.raises(EnvelopeError):
        validate_envelope(obj)


def test_envelope_requires_correlation_id():
    obj = _good_envelope()
    obj.pop("correlation_id")
    with pytest.raises(EnvelopeError):
        validate_envelope(obj)


def test_envelope_requires_schema_version():
    obj = _good_envelope()
    obj.pop("schema_version")
    with pytest.raises(EnvelopeError):
        validate_envelope(obj)


def test_envelope_rejects_wrong_schema_version():
    with pytest.raises(EnvelopeError):
        validate_envelope(_good_envelope(schema_version="events-ndjson/v2"))


def test_envelope_rejects_extra_field():
    obj = _good_envelope()
    obj["extra"] = 1
    with pytest.raises(EnvelopeError):
        validate_envelope(obj)


def test_envelope_rejects_ts_without_ms():
    with pytest.raises(EnvelopeError):
        validate_envelope(_good_envelope(ts="2026-05-04T22:31:00Z"))


def test_envelope_rejects_ts_with_offset():
    with pytest.raises(EnvelopeError):
        validate_envelope(_good_envelope(ts="2026-05-04T22:31:00.123+00:00"))


def test_envelope_rejects_ts_lowercase_z():
    with pytest.raises(EnvelopeError):
        validate_envelope(_good_envelope(ts="2026-05-04T22:31:00.123z"))


def test_envelope_rejects_ts_with_microseconds():
    with pytest.raises(EnvelopeError):
        validate_envelope(_good_envelope(ts="2026-05-04T22:31:00.123456Z"))


def test_envelope_rejects_blank_source():
    with pytest.raises(EnvelopeError):
        validate_envelope(_good_envelope(source=""))


def test_envelope_rejects_long_source():
    with pytest.raises(EnvelopeError):
        validate_envelope(_good_envelope(source="x" * 65))


def test_envelope_rejects_payload_not_object():
    with pytest.raises(EnvelopeError):
        validate_envelope(_good_envelope(payload=[1, 2]))


def test_validate_event_runs_stream_check():
    bad = _good_envelope(payload={"missing": "agent"})
    with pytest.raises(StreamError):
        validate_event(bad)


def test_envelope_rejects_invalid_stream_chars():
    with pytest.raises(EnvelopeError):
        validate_envelope(_good_envelope(stream="bad name"))


def test_envelope_accepts_unicode_in_payload():
    obj = _good_envelope(payload={"agent": "agent-é", "cost_usd": 0.0})
    validate_envelope(obj)
