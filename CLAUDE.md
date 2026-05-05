# events-ndjson — agent guide

## What this is

Portable telemetry library. NDJSON envelope frozen at v1. One spec, two
libraries (Python + TypeScript), one CLI, multiple registered streams.

## Hard rules (DO NOT BREAK)

1. Envelope schema is FROZEN. No new fields without v2.
2. Append must be atomic at line level — full line + newline in one write.
3. `ts` MUST be UTC ISO 8601 with millisecond precision.
4. Append-only. Never modify or delete past lines.
5. Adding a stream is a PR adding the schema in `spec/schema/v1/streams/`.
6. ASCII-only in source / Markdown / TS / Python files. Payloads MAY have UTF-8.
7. Conventional commits. Co-author trailer required.

## Layout

```
spec/                 The contract. Treat as source of truth.
conformance/          Test suite both libs must pass.
libraries/python/     Python reference implementation.
libraries/typescript/ TypeScript reference implementation.
cli/                  events.py CLI.
docs/                 Auxiliary docs.
```

## Tests

Python: `cd libraries/python && pytest`
TypeScript: `cd libraries/typescript && npm test`
Conformance: `python conformance/conformance.py`

## Adding a stream

1. Drop the JSON Schema at `spec/schema/v1/streams/<name>.json`.
2. Add the stream to the registry in `libraries/python/events_ndjson/registry.py`
   and `libraries/typescript/src/registry.ts`.
3. Add a row to the table in `spec/EVENTS_SPEC.md`.
4. Add at least one test event in conformance fixtures.

## Migrations

Consumer migrations (operator-core, quiet-woods, prospector-pro) live on
branches in those repos. Never push migrations to master without sign-off.
