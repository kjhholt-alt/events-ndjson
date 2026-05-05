"""events-ndjson: portable NDJSON telemetry event streams."""

from events_ndjson.types import Event, EnvelopeError, StreamError, ValidationError
from events_ndjson.writer import Writer
from events_ndjson.reader import Reader
from events_ndjson import replay, registry

__version__ = "0.1.0"
SCHEMA_VERSION = "events-ndjson/v1"

__all__ = [
    "Writer",
    "Reader",
    "Event",
    "EnvelopeError",
    "StreamError",
    "ValidationError",
    "replay",
    "registry",
    "SCHEMA_VERSION",
    "__version__",
]
