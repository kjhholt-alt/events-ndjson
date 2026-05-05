import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, readFileSync, appendFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { Writer, StreamError } from "../src/index.js";

let dir: string;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "events-ts-"));
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

describe("Writer", () => {
  it("writes a single event", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await w.append({ event_type: "agent_complete", payload: { agent: "x", cost_usd: 0.5 } });
    await w.close();

    const lines = readFileSync(p, "utf8").split("\n").filter((l) => l);
    expect(lines).toHaveLength(1);
    const obj = JSON.parse(lines[0]);
    expect(obj.stream).toBe("cost");
    expect(obj.payload).toEqual({ agent: "x", cost_usd: 0.5 });
    expect(obj.schema_version).toBe("events-ndjson/v1");
  });

  it("generates ISO ts with ms", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await w.append({ event_type: "a", payload: { agent: "x", cost_usd: 0 } });
    await w.close();
    const obj = JSON.parse(readFileSync(p, "utf8").trim());
    expect(obj.ts).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  });

  it("generates correlation_id when omitted", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await w.append({ event_type: "a", payload: { agent: "x", cost_usd: 0 } });
    await w.close();
    const obj = JSON.parse(readFileSync(p, "utf8").trim());
    expect(obj.correlation_id).toBeTruthy();
    expect(obj.correlation_id.length).toBe(36); // uuid v4
  });

  it("respects explicit ts and correlation_id", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await w.append({
      event_type: "a",
      payload: { agent: "x", cost_usd: 0 },
      ts: "2026-05-04T22:31:00.123Z",
      correlation_id: "fixed-id",
    });
    await w.close();
    const obj = JSON.parse(readFileSync(p, "utf8").trim());
    expect(obj.ts).toBe("2026-05-04T22:31:00.123Z");
    expect(obj.correlation_id).toBe("fixed-id");
  });

  it("appends in order", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    for (let i = 0; i < 25; i++) {
      await w.append({
        event_type: "a",
        payload: { agent: `a${i}`, cost_usd: i },
      });
    }
    await w.close();
    const events = readFileSync(p, "utf8")
      .split("\n")
      .filter(Boolean)
      .map((l) => JSON.parse(l));
    expect(events).toHaveLength(25);
    events.forEach((ev, i) => {
      expect(ev.payload.agent).toBe(`a${i}`);
    });
  });

  it("rejects unregistered stream", () => {
    expect(
      () => new Writer({ stream: "ghost", source: "x", path: join(dir, "x.ndjson") }),
    ).toThrow(StreamError);
  });

  it("validates payload by default", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await expect(
      w.append({ event_type: "a", payload: { not_agent: true } }),
    ).rejects.toBeInstanceOf(StreamError);
    await w.close();
  });

  it("payload validation can be disabled", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({
      stream: "cost",
      source: "test",
      path: p,
      validatePayload: false,
    });
    await w.append({ event_type: "a", payload: { freeform: 42 } });
    await w.close();
    const obj = JSON.parse(readFileSync(p, "utf8").trim());
    expect(obj.payload.freeform).toBe(42);
  });

  it("rejects extra payload field", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await expect(
      w.append({
        event_type: "a",
        payload: { agent: "x", cost_usd: 0, stowaway: true },
      }),
    ).rejects.toBeInstanceOf(StreamError);
    await w.close();
  });

  it("creates parent dir", async () => {
    const p = join(dir, "nested", "deep", "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await w.append({ event_type: "a", payload: { agent: "x", cost_usd: 0 } });
    await w.close();
    expect(readFileSync(p, "utf8")).toContain('"agent":"x"');
  });

  it("emits LF only, not CRLF", async () => {
    const p = join(dir, "cost.ndjson");
    const w = new Writer({ stream: "cost", source: "test", path: p });
    await w.append({ event_type: "a", payload: { agent: "x", cost_usd: 0 } });
    await w.append({ event_type: "a", payload: { agent: "y", cost_usd: 0 } });
    await w.close();
    const raw = readFileSync(p);
    expect(raw.includes(Buffer.from("\r\n"))).toBe(false);
    expect(raw.filter((b) => b === 0x0a).length).toBe(2);
  });

  it("appends across separate Writer instances", async () => {
    const p = join(dir, "cost.ndjson");
    const w1 = new Writer({ stream: "cost", source: "test", path: p });
    await w1.append({ event_type: "a", payload: { agent: "first", cost_usd: 1 } });
    await w1.close();
    const w2 = new Writer({ stream: "cost", source: "test", path: p });
    await w2.append({ event_type: "a", payload: { agent: "second", cost_usd: 2 } });
    await w2.close();
    const lines = readFileSync(p, "utf8").split("\n").filter(Boolean);
    expect(lines).toHaveLength(2);
  });
});
