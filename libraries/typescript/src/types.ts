export const SCHEMA_VERSION = "events-ndjson/v1" as const;

export interface Event {
  ts: string;
  source: string;
  stream: string;
  event_type: string;
  payload: Record<string, unknown>;
  correlation_id: string;
  schema_version: typeof SCHEMA_VERSION;
}

export class EventsNdjsonError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EventsNdjsonError";
  }
}

export class EnvelopeError extends EventsNdjsonError {
  constructor(message: string) {
    super(message);
    this.name = "EnvelopeError";
  }
}

export class StreamError extends EventsNdjsonError {
  constructor(message: string) {
    super(message);
    this.name = "StreamError";
  }
}

export class ValidationError extends EventsNdjsonError {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}
