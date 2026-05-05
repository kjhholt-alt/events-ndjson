import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  mkdtempSync,
  rmSync,
  appendFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { Writer, Reader, EnvelopeError, ValidationError } from "../src/index.js";

let dir: string;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "events-ts-r-"));
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

async function seed(p: string, n = 3, source = "test") {
  const w = new Writer({ stream: "cost", source, path: p });
  for (let i = 0; i < n; i++) {
    await w.append({
      event_type: "agent_complete",
      payload: { agent: `a${i}`, cost_usd: i },
    });
  }
  await w.close();
}

describe("Reader", () => {
  it("returns empty for missing file", () => {
    const r = new Reader(join(dir, "nope.ndjson"));
    expect(r.readAll()).toEqual([]);
  });

  it("returns empty for empty file", () => {
    const p = join(dir, "empty.ndjson");
    writeFileSync(p, "");
    expect(new Reader(p).readAll()).toEqual([]);
  });

  it("reads all events", async () => {
    const p = join(dir, "cost.ndjson");
    await seed(p, 5);
    const events = new Reader(p).readAll();
    expect(events).toHaveLength(5);
  });

  it("skips partial last line", async () => {
    const p = join(dir, "cost.ndjson");
    await seed(p, 3);
    appendFileSync(p, '{"ts":"2026-05-04T22:31:00.123Z"'); // mid-write, no newline
    const events = new Reader(p).readAll();
    expect(events).toHaveLength(3);
  });

  it("strict rejects bad envelope", () => {
    const p = join(dir, "bad.ndjson");
    writeFileSync(p, '{"not":"valid"}\n');
    expect(() => new Reader(p, { strict: true }).readAll()).toThrow();
  });

  it("lenient skips bad lines", async () => {
    const p = join(dir, "mix.ndjson");
    await seed(p, 2);
    appendFileSync(p, '{"not":"valid"}\n');
    appendFileSync(p, "this is not json\n");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await w.append({
      event_type: "agent_complete",
      payload: { agent: "tail", cost_usd: 0 },
    });
    await w.close();
    const events = new Reader(p, { strict: false }).readAll();
    expect(events).toHaveLength(3);
    expect((events[2].payload as Record<string, unknown>).agent).toBe("tail");
  });

  it("filter by stream", async () => {
    const p = join(dir, "cost.ndjson");
    await seed(p, 3);
    expect(new Reader(p).filter({ stream: "cost" }).events()).toHaveLength(3);
    expect(new Reader(p).filter({ stream: "pacing" }).events()).toHaveLength(0);
  });

  it("filter by event_type", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "t", path: p });
    await w.append({ event_type: "agent_complete", payload: { agent: "x", cost_usd: 1 } });
    await w.append({ event_type: "agent_failed", payload: { agent: "y", cost_usd: 0 } });
    await w.close();
    const matched = new Reader(p).filter({ event_type: "agent_failed" }).events();
    expect(matched).toHaveLength(1);
  });

  it("filter by source", async () => {
    const p = join(dir, "cost.ndjson");
    await seed(p, 2, "alpha");
    await seed(p, 2, "beta");
    expect(new Reader(p).filter({ source: "alpha" }).events()).toHaveLength(2);
    expect(new Reader(p).filter({ source: "beta" }).events()).toHaveLength(2);
  });

  it("filter by predicate", async () => {
    const p = join(dir, "cost.ndjson");
    await seed(p, 5);
    const high = new Reader(p)
      .filter({
        predicate: (ev) =>
          ((ev.payload as Record<string, unknown>).cost_usd as number) >= 3,
      })
      .events();
    expect(high).toHaveLength(2);
  });

  it("tail without follow yields all and stops", async () => {
    const p = join(dir, "cost.ndjson");
    await seed(p, 3);
    const out: Record<string, unknown>[] = [];
    for await (const ev of new Reader(p).tail({ follow: false })) {
      out.push(ev);
    }
    expect(out).toHaveLength(3);
  });

  it("tail follow picks up new events", async () => {
    const p = join(dir, "cost.ndjson");
    await seed(p, 2);

    const r = new Reader(p);
    const received: Record<string, unknown>[] = [];

    const consumer = (async () => {
      for await (const ev of r.tail({ follow: true, pollIntervalMs: 10 })) {
        received.push(ev);
        if (received.length >= 4) break;
      }
    })();

    // Give the tailer a beat to reach EOF before appending.
    await new Promise((r) => setTimeout(r, 50));
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await w.append({ event_type: "a", payload: { agent: "live-1", cost_usd: 0 } });
    await w.append({ event_type: "a", payload: { agent: "live-2", cost_usd: 0 } });
    await w.close();

    await consumer;
    expect(received).toHaveLength(4);
    expect((received[2].payload as Record<string, unknown>).agent).toBe("live-1");
    expect((received[3].payload as Record<string, unknown>).agent).toBe("live-2");
  }, 10000);
});
