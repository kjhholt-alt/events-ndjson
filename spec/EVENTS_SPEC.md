# events-ndjson Spec v1.0.0

Status: FROZEN once first stable release ships.

## Purpose

Define a portable, machine-checkable format for telemetry event streams written
to disk as newline-delimited JSON. Every event is a single JSON object on its
own line, terminated by a single `\n`. No comments, no surrounding array, no
multi-line records.

## Envelope

Every event MUST be a JSON object with exactly the following top-level fields:

| Field            | Type   | Required | Description |
|------------------|--------|----------|-------------|
| `ts`             | string | yes      | UTC ISO 8601 with millisecond precision: `YYYY-MM-DDTHH:MM:SS.sssZ` |
| `source`         | string | yes      | Producer identifier (project or service name). ASCII, max 64 chars. |
| `stream`         | string | yes      | Registered stream name (see Stream Registry). ASCII, max 64 chars. |
| `event_type`     | string | yes      | Event kind within the stream. ASCII, max 64 chars. |
| `payload`        | object | yes      | Stream-specific payload, validated by stream schema. |
| `correlation_id` | string | yes      | UUID-like string used to correlate events across streams. Max 64 chars. |
| `schema_version` | string | yes      | Always `events-ndjson/v1` for spec v1. |

No additional top-level fields are permitted.

### Example

```json
{"ts":"2026-05-04T22:31:00.123Z","source":"operator-core","stream":"cost","event_type":"agent_complete","payload":{"agent":"morning-briefing","cost_usd":0.42,"duration_ms":18234},"correlation_id":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","schema_version":"events-ndjson/v1"}
```

## Timestamp format

`ts` MUST match this regex:

```
^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$
```

Milliseconds are required. Microseconds, nanoseconds, and timezone offsets
other than `Z` are rejected.

## Append semantics

1. Append-only. Never modify or delete past lines.
2. Each line is a single JSON object plus exactly one `\n`.
3. The full line+newline MUST be written in a single `write` syscall path so
   concurrent writers do not interleave bytes within a line.
4. Files MAY be rotated (renamed and reopened) but never edited in place.

## Reader semantics

1. Readers MUST handle a partial last line (a write in progress) by ignoring
   it until terminated by `\n`.
2. Readers MUST tolerate trailing whitespace.
3. Readers MUST reject any line that fails envelope validation when in strict
   mode. In lenient mode they MAY skip and surface a warning.
4. `tail(follow=True)` MUST yield events in append order and MUST NOT lose
   events present at open time.

## Stream Registry

Each stream has its own JSON Schema in `spec/schema/v1/streams/<name>.json`.
Registered streams in v1:

- `cost` — agent cost ledger events
- `pacing` — game/UX pacing events (e.g., quiet-woods)
- `campaign` — outreach campaign lifecycle events
- `agent_session` — agent invocation lifecycle events

Adding a new stream is a PR that adds a schema file in `streams/` and a row
to this list. Unregistered streams are a validation FAIL.

## Versioning

- Envelope schema version is encoded in the `schema_version` field.
- Stream schemas MAY add optional fields without bumping envelope version.
- Removing or renaming envelope fields requires `events-ndjson/v2`.
- Stream payload breaking changes get a new stream name (e.g., `cost_v2`).

## Hard rules

1. Append must be atomic at line level.
2. Append-only. Never modify past lines.
3. `ts` MUST be UTC ISO 8601 with millisecond precision.
4. Stream registry is the contract. Unregistered stream is a validation FAIL.
5. Reader handles partial last line.
6. ASCII-only in field values where reasonable; payload MAY contain UTF-8.
7. Writers MUST flush on every append.

## Conformance

A library is conformant if:

- All envelope rules above are enforced on write.
- Readers handle partial last line, follow mode, and rotation.
- The `conformance/` test suite passes.
