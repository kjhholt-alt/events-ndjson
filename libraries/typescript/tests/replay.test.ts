import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { Writer, diff, replay, stats } from "../src/index.js";

let dir: string;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "events-ts-d-"));
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

async function seed(p: string, agents = ["a", "b", "c"], source = "test") {
  const w = new Writer({ stream: "cost", source, path: p });
  for (const a of agents) {
    await w.append({
      event_type: "agent_complete",
      payload: { agent: a, cost_usd: 1 },
    });
  }
  await w.close();
}

describe("replay.diff", () => {
  it("identical streams", async () => {
    const a = join(dir, "a.ndjson");
    const b = join(dir, "b.ndjson");
    await seed(a);
    await seed(b);
    const res = diff(a, b);
    expect(res.identical).toBe(true);
    expect(res.divergence).toBeNull();
    expect(res.matched).toBe(3);
  });

  it("payload divergence", async () => {
    const a = join(dir, "a.ndjson");
    const b = join(dir, "b.ndjson");
    await seed(a, ["x", "y", "z"]);
    await seed(b, ["x", "Y!", "z"]);
    const res = diff(a, b);
    expect(res.identical).toBe(false);
    expect(res.divergence?.index).toBe(1);
    expect(res.divergence?.reason).toBe("events differ");
  });

  it("A ends first", async () => {
    const a = join(dir, "a.ndjson");
    const b = join(dir, "b.ndjson");
    await seed(a, ["x", "y"]);
    await seed(b, ["x", "y", "z"]);
    const res = diff(a, b);
    expect(res.divergence?.reason).toBe("stream A ended first");
    expect(res.divergence?.index).toBe(2);
  });

  it("B ends first", async () => {
    const a = join(dir, "a.ndjson");
    const b = join(dir, "b.ndjson");
    await seed(a, ["x", "y", "z"]);
    await seed(b, ["x", "y"]);
    const res = diff(a, b);
    expect(res.divergence?.reason).toBe("stream B ended first");
  });

  it("ignores volatile fields by default", async () => {
    // Writes happen at different times and produce different ts/correlation_id,
    // but the diff should still report identical.
    const a = join(dir, "a.ndjson");
    const b = join(dir, "b.ndjson");
    await seed(a);
    await new Promise((r) => setTimeout(r, 5));
    await seed(b);
    expect(diff(a, b).identical).toBe(true);
  });

  it("custom key narrows comparison", async () => {
    const a = join(dir, "a.ndjson");
    const b = join(dir, "b.ndjson");
    await seed(a, ["x", "y"], "alpha");
    await seed(b, ["x", "y"], "beta");
    expect(diff(a, b).identical).toBe(false);
    expect(diff(a, b, { key: (ev) => ev.event_type }).identical).toBe(true);
  });

  it("catches injected bug (replay determinism)", async () => {
    const golden = join(dir, "g.ndjson");
    const repro = join(dir, "r.ndjson");
    await seed(golden, ["a", "b", "c", "d"]);
    const w = new Writer({ stream: "cost", source: "test", path: repro });
    await w.append({ event_type: "agent_complete", payload: { agent: "a", cost_usd: 1 } });
    await w.append({ event_type: "agent_complete", payload: { agent: "b", cost_usd: 1 } });
    // bug: skipped 'c'
    await w.append({ event_type: "agent_complete", payload: { agent: "d", cost_usd: 1 } });
    await w.close();
    const res = diff(golden, repro);
    expect(res.identical).toBe(false);
    expect(res.divergence?.index).toBe(2);
    expect(((res.divergence?.a as any).payload).agent).toBe("c");
  });
});

describe("replay.replay", () => {
  it("invokes handler per event", async () => {
    const p = join(dir, "cost.ndjson");
    await seed(p, ["a", "b", "c"]);
    const seen: string[] = [];
    const n = replay(p, (ev) =>
      seen.push((ev.payload as Record<string, unknown>).agent as string),
    );
    expect(n).toBe(3);
    expect(seen).toEqual(["a", "b", "c"]);
  });

  it("works with in-memory iterable", () => {
    const events = [
      {
        ts: "2026-05-04T22:31:00.123Z",
        source: "x",
        stream: "cost",
        event_type: "a",
        payload: { agent: "x", cost_usd: 0 },
        correlation_id: "1",
        schema_version: "events-ndjson/v1",
      },
    ];
    const seen: Record<string, unknown>[] = [];
    replay(events, (ev) => seen.push(ev));
    expect(seen).toHaveLength(1);
  });
});

describe("replay.stats", () => {
  it("counts by stream/event_type/source", async () => {
    const p = join(dir, "cost.ndjson");
    await seed(p, ["a", "b", "c"], "agent2");
    const s = stats(p);
    expect(s.total).toBe(3);
    expect(s.byStream.cost).toBe(3);
    expect(s.byEventType.agent_complete).toBe(3);
    expect(s.bySource.agent2).toBe(3);
  });

  it("empty file has zero total", () => {
    const p = join(dir, "empty.ndjson");
    writeFileSync(p, "");
    expect(stats(p).total).toBe(0);
  });
});
