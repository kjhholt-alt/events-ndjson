"""Stream registry. Loads JSON Schemas bundled with the package."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from events_ndjson.types import StreamError

SCHEMA_VERSION = "events-ndjson/v1"
_SCHEMA_ROOT = Path(__file__).parent / "schema" / "v1"
_STREAMS_DIR = _SCHEMA_ROOT / "streams"


@lru_cache(maxsize=1)
def envelope_schema() -> Dict[str, Any]:
    with open(_SCHEMA_ROOT / "envelope.json", "r", encoding="ascii") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def stream_schema(stream: str) -> Dict[str, Any]:
    """Return the JSON Schema for a registered stream.

    Raises StreamError if the stream is not registered.
    """
    if not stream or "/" in stream or "\\" in stream or ".." in stream:
        raise StreamError(f"invalid stream name: {stream!r}")
    path = _STREAMS_DIR / f"{stream}.json"
    if not path.exists():
        raise StreamError(
            f"stream {stream!r} is not registered. Add a schema at "
            f"spec/schema/v1/streams/{stream}.json"
        )
    with open(path, "r", encoding="ascii") as f:
        return json.load(f)


def list_streams() -> List[str]:
    if not _STREAMS_DIR.exists():
        return []
    return sorted(p.stem for p in _STREAMS_DIR.glob("*.json"))


def is_registered(stream: str) -> bool:
    try:
        stream_schema(stream)
        return True
    except StreamError:
        return False
