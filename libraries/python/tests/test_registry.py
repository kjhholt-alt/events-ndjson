"""Stream registry tests."""

import pytest

from events_ndjson import registry
from events_ndjson.types import StreamError


def test_lists_known_streams():
    streams = registry.list_streams()
    for required in ("cost", "pacing", "campaign", "agent_session"):
        assert required in streams


def test_known_stream_is_registered():
    assert registry.is_registered("cost")
    assert registry.is_registered("pacing")
    assert registry.is_registered("campaign")
    assert registry.is_registered("agent_session")


def test_unknown_stream_is_not_registered():
    assert not registry.is_registered("bogus_stream_xyz")


def test_unknown_stream_raises():
    with pytest.raises(StreamError):
        registry.stream_schema("does_not_exist")


def test_path_traversal_rejected():
    with pytest.raises(StreamError):
        registry.stream_schema("../envelope")


def test_envelope_schema_loads():
    sch = registry.envelope_schema()
    assert sch["title"].startswith("events-ndjson envelope")
    assert "ts" in sch["properties"]


def test_stream_schemas_load():
    for name in ("cost", "pacing", "campaign", "agent_session"):
        sch = registry.stream_schema(name)
        assert sch["title"].startswith(name)
