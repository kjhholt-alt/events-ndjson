// Conformance scenarios driven against the TS library.
// Run from libraries/typescript so node module resolution works.

import { mkdtempSync, rmSync, readFileSync, appendFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Resolve dist/index.js relative to libraries/typescript regardless of cwd.
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const libRoot = resolve(__dirname, "..", "libraries", "typescript");
const distEntry = pathToFileURL(resolve(libRoot, "dist", "index.js")).href;

const { Writer, Reader, diff } = await import(distEntry);

const cases = [];
function ccase(name, fn) {
  cases.push([name, fn]);
}

ccase("append-roundtrip", async (dir) => {
  const p = join(dir, "cost.ndjson");
  const w = new Writer({ stream: "cost", source: "conf", path: p });
  for (let i = 0; i < 5; i++) {
    await w.append({
      event_type: "agent_complete",
      payload: { agent: `a${i}`, cost_usd: i },
    });
  }
  await w.close();
  const events = new Reader(p).readAll();
  if (events.length !== 5) throw new Error(`expected 5, got ${events.length}`);
});

ccase("append-serial-under-many-async", async (dir) => {
  // The TS Writer serializes through an internal chain so concurrent
  // append() calls cannot interleave bytes.
  const p = join(dir, "cost.ndjson");
  const w = new Writer({ stream: "cost", source: "conf", path: p });
  const tasks = [];
  for (let i = 0; i < 100; i++) {
    tasks.push(
      w.append({
        event_type: "agent_complete",
        payload: { agent: `n${i}`, cost_usd: i },
      }),
    );
  }
  await Promise.all(tasks);
  await w.close();
  const lines = readFileSync(p, "utf8").split("\n").filter(Boolean);
  if (lines.length !== 100) throw new Error(`expected 100, got ${lines.length}`);
  for (const line of lines) JSON.parse(line);
});

ccase("partial-last-line-tolerance", async (dir) => {
  const p = join(dir, "cost.ndjson");
  const w = new Writer({ stream: "cost", source: "conf", path: p });
  await w.append({ event_type: "a", payload: { agent: "x", cost_usd: 0 } });
  await w.append({ event_type: "a", payload: { agent: "y", cost_usd: 0 } });
  await w.close();
  appendFileSync(p, '{"ts":"2026-05-04T22:31:00.123Z","source":"x"');
  const events = new Reader(p).readAll();
  if (events.length !== 2) throw new Error(`expected 2 complete events, got ${events.length}`);
});

ccase("tail-follow", async (dir) => {
  const p = join(dir, "cost.ndjson");
  const w0 = new Writer({ stream: "cost", source: "conf", path: p });
  await w0.append({ event_type: "a", payload: { agent: "history", cost_usd: 0 } });
  await w0.close();

  const r = new Reader(p);
  const received = [];
  const consumer = (async () => {
    for await (const ev of r.tail({ follow: true, pollIntervalMs: 10 })) {
      received.push(ev);
      if (received.length >= 3) break;
    }
  })();

  await new Promise((r) => setTimeout(r, 50));
  const w = new Writer({ stream: "cost", source: "conf", path: p });
  await w.append({ event_type: "a", payload: { agent: "live-1", cost_usd: 0 } });
  await w.append({ event_type: "a", payload: { agent: "live-2", cost_usd: 0 } });
  await w.close();

  await consumer;
  if (received.length !== 3) throw new Error(`expected 3 events, got ${received.length}`);
});

ccase("replay-determinism-catches-missing-event", async (dir) => {
  const golden = join(dir, "g.ndjson");
  const repro = join(dir, "r.ndjson");
  const wg = new Writer({ stream: "cost", source: "conf", path: golden });
  for (const a of ["a", "b", "c", "d"]) {
    await wg.append({ event_type: "agent_complete", payload: { agent: a, cost_usd: 1 } });
  }
  await wg.close();
  const wr = new Writer({ stream: "cost", source: "conf", path: repro });
  for (const a of ["a", "b", "d"]) {
    await wr.append({ event_type: "agent_complete", payload: { agent: a, cost_usd: 1 } });
  }
  await wr.close();
  const res = diff(golden, repro);
  if (res.identical) throw new Error("expected divergence");
  if (res.divergence.index !== 2) throw new Error(`expected index 2, got ${res.divergence.index}`);
  if (res.divergence.a.payload.agent !== "c") throw new Error("expected missing event 'c'");
});

ccase("envelope-rejects-bad-ts", async (dir) => {
  const p = join(dir, "bad.ndjson");
  appendFileSync(
    p,
    '{"ts":"2026-05-04T22:31:00Z","source":"x","stream":"cost",' +
      '"event_type":"a","payload":{"agent":"x","cost_usd":0},' +
      '"correlation_id":"1","schema_version":"events-ndjson/v1"}\n',
  );
  let threw = false;
  try {
    new Reader(p, { strict: true }).readAll();
  } catch {
    threw = true;
  }
  if (!threw) throw new Error("expected envelope error for bad ts");
});

ccase("registry-rejects-unregistered-stream", async (dir) => {
  let threw = false;
  try {
    new Writer({
      stream: "totally_made_up_xyz",
      source: "conf",
      path: join(dir, "x.ndjson"),
    });
  } catch {
    threw = true;
  }
  if (!threw) throw new Error("expected stream error");
});

let failed = 0;
for (const [name, fn] of cases) {
  const d = mkdtempSync(join(tmpdir(), "events-conf-"));
  try {
    await fn(d);
    console.log(`  PASS  ${name}`);
  } catch (e) {
    failed += 1;
    console.error(`  FAIL  ${name}: ${e.message}`);
  } finally {
    rmSync(d, { recursive: true, force: true });
  }
}
console.log("");
console.log(`typescript conformance: ${cases.length - failed}/${cases.length} passed`);
process.exit(failed === 0 ? 0 : 1);
