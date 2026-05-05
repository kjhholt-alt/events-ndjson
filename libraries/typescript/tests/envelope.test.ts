import { describe, it, expect } from "vitest";
import { validateEnvelope, validateEvent, EnvelopeError, StreamError } from "../src/index.js";

function good(overrides: Record<string, unknown> = {}) {
  return {
    ts: "2026-05-04T22:31:00.123Z",
    source: "test",
    stream: "cost",
    event_type: "agent_complete",
    payload: { agent: "x", cost_usd: 0.1 },
    correlation_id: "abc",
    schema_version: "events-ndjson/v1",
    ...overrides,
  };
}

describe("envelope validation", () => {
  it("accepts a minimum valid envelope", () => {
    expect(() => validateEnvelope(good())).not.toThrow();
  });

  it("rejects non-object", () => {
    expect(() => validateEnvelope("nope")).toThrow(EnvelopeError);
  });

  it("rejects array", () => {
    expect(() => validateEnvelope([1])).toThrow(EnvelopeError);
  });

  it("rejects missing ts", () => {
    const ev = good();
    delete (ev as Record<string, unknown>).ts;
    expect(() => validateEnvelope(ev)).toThrow(EnvelopeError);
  });

  it("rejects ts without ms", () => {
    expect(() => validateEnvelope(good({ ts: "2026-05-04T22:31:00Z" }))).toThrow(
      EnvelopeError,
    );
  });

  it("rejects ts with offset", () => {
    expect(() =>
      validateEnvelope(good({ ts: "2026-05-04T22:31:00.123+00:00" })),
    ).toThrow(EnvelopeError);
  });

  it("rejects ts with microseconds", () => {
    expect(() =>
      validateEnvelope(good({ ts: "2026-05-04T22:31:00.123456Z" })),
    ).toThrow(EnvelopeError);
  });

  it("rejects wrong schema_version", () => {
    expect(() =>
      validateEnvelope(good({ schema_version: "events-ndjson/v2" })),
    ).toThrow(EnvelopeError);
  });

  it("rejects extra top-level field", () => {
    expect(() => validateEnvelope(good({ extra: 1 }))).toThrow(EnvelopeError);
  });

  it("rejects blank source", () => {
    expect(() => validateEnvelope(good({ source: "" }))).toThrow(EnvelopeError);
  });

  it("rejects long source", () => {
    expect(() => validateEnvelope(good({ source: "x".repeat(65) }))).toThrow(EnvelopeError);
  });

  it("rejects payload not object", () => {
    expect(() => validateEnvelope(good({ payload: [1, 2] }))).toThrow(EnvelopeError);
  });

  it("validateEvent enforces stream payload", () => {
    expect(() => validateEvent(good({ payload: { not_an_agent: true } }))).toThrow(
      StreamError,
    );
  });
});
