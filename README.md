# events-ndjson

Tiny, rigorous library for newline-delimited JSON event streams.

Append-only, atomic-line, schema-validated telemetry that any project can write
or replay without coordinating on a shared database.

## Install

Python:

```bash
pip install events-ndjson
```

TypeScript:

```bash
npm install events-ndjson
```

## Quick example

Python:

```python
from events_ndjson import Writer

w = Writer(stream="cost", source="operator-core", path="cost.ndjson")
w.append(event_type="agent_complete", payload={"agent": "morning", "cost_usd": 0.42})
```

TypeScript:

```ts
import { Writer } from "events-ndjson";

const w = new Writer({ stream: "cost", source: "operator-core", path: "cost.ndjson" });
await w.append({ event_type: "agent_complete", payload: { agent: "morning", cost_usd: 0.42 } });
```

## CLI

```
events validate cost.ndjson
events tail   cost.ndjson --follow
events replay a.ndjson b.ndjson    # diff two streams
events stats  cost.ndjson
```

## Spec

See `spec/EVENTS_SPEC.md`. Envelope is frozen at v1.

## Streams

- `cost`           agent cost ledger
- `pacing`         game/UX pacing
- `campaign`       outreach lifecycle
- `agent_session`  agent invocation lifecycle
- `runs`           recipe / job lifecycle (started, finished, skipped, cancelled)
- `gate_audit`     outreach Sender Gate shadow-mode decisions (cut-over diff log)

Adding a new stream is a PR adding `spec/schema/v1/streams/<name>.json`
plus mirrored copies under `libraries/python/events_ndjson/schema/v1/streams/`
and `libraries/typescript/schema/v1/streams/`. Add a conformance case in
`conformance/conformance.py` to lock the contract.
