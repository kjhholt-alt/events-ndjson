import { describe, it, expect } from "vitest";
import {
  isRegistered,
  listStreams,
  streamSchema,
  envelopeSchema,
  StreamError,
  ZodRegistry,
} from "../src/index.js";

describe("stream registry", () => {
  it("lists known streams", () => {
    const s = listStreams();
    expect(s).toContain("cost");
    expect(s).toContain("pacing");
    expect(s).toContain("campaign");
    expect(s).toContain("agent_session");
  });

  it("isRegistered for known streams", () => {
    expect(isRegistered("cost")).toBe(true);
    expect(isRegistered("pacing")).toBe(true);
    expect(isRegistered("campaign")).toBe(true);
    expect(isRegistered("agent_session")).toBe(true);
  });

  it("isRegistered false for unknown", () => {
    expect(isRegistered("does_not_exist_xyz")).toBe(false);
  });

  it("streamSchema throws for unknown", () => {
    expect(() => streamSchema("nope")).toThrow(StreamError);
  });

  it("rejects path traversal", () => {
    expect(() => streamSchema("../envelope")).toThrow(StreamError);
    expect(() => streamSchema("..")).toThrow(StreamError);
  });

  it("envelopeSchema loads", () => {
    const sch = envelopeSchema();
    expect(typeof sch).toBe("object");
    expect((sch as Record<string, unknown>).title).toContain("envelope");
  });

  it("Zod registry validates a good cost payload", () => {
    const result = ZodRegistry.cost.safeParse({ agent: "x", cost_usd: 0.5 });
    expect(result.success).toBe(true);
  });

  it("Zod registry rejects bad cost payload", () => {
    const result = ZodRegistry.cost.safeParse({ agent: "x" });
    expect(result.success).toBe(false);
  });

  it("Zod registry validates campaign phase enum", () => {
    expect(
      ZodRegistry.campaign.safeParse({ campaign_id: "c1", phase: "sent" })
        .success,
    ).toBe(true);
    expect(
      ZodRegistry.campaign.safeParse({ campaign_id: "c1", phase: "weird" })
        .success,
    ).toBe(false);
  });
});
