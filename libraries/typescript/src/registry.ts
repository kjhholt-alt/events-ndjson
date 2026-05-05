import { readFileSync, existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";

import { StreamError, SCHEMA_VERSION } from "./types.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Schemas are bundled at libraries/typescript/schema/v1/. When running from
// dist/ we resolve up one level; from src/ we resolve up two.
function findSchemaRoot(): string {
  const candidates = [
    resolve(__dirname, "..", "schema", "v1"),
    resolve(__dirname, "..", "..", "schema", "v1"),
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  throw new Error(`could not locate schema/v1 from ${__dirname}`);
}

const SCHEMA_ROOT = findSchemaRoot();
const STREAMS_DIR = join(SCHEMA_ROOT, "streams");

const _envelopeCache: { schema?: Record<string, unknown> } = {};
const _streamCache: Map<string, Record<string, unknown>> = new Map();

export function envelopeSchema(): Record<string, unknown> {
  if (!_envelopeCache.schema) {
    const txt = readFileSync(join(SCHEMA_ROOT, "envelope.json"), "utf8");
    _envelopeCache.schema = JSON.parse(txt);
  }
  return _envelopeCache.schema!;
}

function isSafeStreamName(stream: string): boolean {
  if (!stream) return false;
  if (stream.includes("/") || stream.includes("\\") || stream.includes(".."))
    return false;
  return /^[A-Za-z0-9_-]+$/.test(stream);
}

export function streamSchema(stream: string): Record<string, unknown> {
  if (!isSafeStreamName(stream)) {
    throw new StreamError(`invalid stream name: ${JSON.stringify(stream)}`);
  }
  const cached = _streamCache.get(stream);
  if (cached) return cached;
  const path = join(STREAMS_DIR, `${stream}.json`);
  if (!existsSync(path)) {
    throw new StreamError(
      `stream ${JSON.stringify(stream)} is not registered. ` +
        `Add a schema at spec/schema/v1/streams/${stream}.json`,
    );
  }
  const schema = JSON.parse(readFileSync(path, "utf8"));
  _streamCache.set(stream, schema);
  return schema;
}

export function listStreams(): string[] {
  if (!existsSync(STREAMS_DIR)) return [];
  return readdirSync(STREAMS_DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""))
    .sort();
}

export function isRegistered(stream: string): boolean {
  try {
    streamSchema(stream);
    return true;
  } catch {
    return false;
  }
}

// ---- Zod registry --------------------------------------------------------
//
// In addition to the JSON Schema files, we expose a Zod registry that mirrors
// each stream's expected payload shape for type-safe consumers in TypeScript.
// The JSON Schema remains the contract; Zod is a convenience layer.

export const CostPayload = z
  .object({
    agent: z.string().min(1).max(128),
    cost_usd: z.number().min(0),
    duration_ms: z.number().int().min(0).optional(),
    input_tokens: z.number().int().min(0).optional(),
    output_tokens: z.number().int().min(0).optional(),
    model: z.string().max(64).optional(),
    session_id: z.string().max(64).optional(),
    exit_code: z.number().int().optional(),
  })
  .strict();

export const PacingPayload = z
  .object({
    scene: z.string().min(1).max(128),
    elapsed_ms: z.number().int().min(0).optional(),
    interaction_count: z.number().int().min(0).optional(),
    tag: z.string().max(64).optional(),
    intensity: z.number().min(0).max(1).optional(),
    session_id: z.string().max(64).optional(),
  })
  .strict();

export const CampaignPayload = z
  .object({
    campaign_id: z.string().min(1).max(64),
    phase: z.enum([
      "queued",
      "sent",
      "delivered",
      "opened",
      "clicked",
      "replied",
      "bounced",
      "suppressed",
      "unsubscribed",
      "failed",
    ]),
    lead_id: z.string().max(64).optional(),
    channel: z.enum(["email", "sms", "linkedin", "phone"]).optional(),
    subject: z.string().max(256).optional(),
    provider_message_id: z.string().max(256).optional(),
    error: z.string().max(512).optional(),
  })
  .strict();

export const AgentSessionPayload = z
  .object({
    session_id: z.string().min(1).max(64),
    phase: z.enum([
      "start",
      "tool_use",
      "tool_result",
      "message",
      "thinking",
      "end",
      "error",
    ]),
    agent: z.string().max(128).optional(),
    tool: z.string().max(64).optional(),
    summary: z.string().max(1024).optional(),
    duration_ms: z.number().int().min(0).optional(),
    exit_code: z.number().int().optional(),
  })
  .strict();

export const ZodRegistry = {
  cost: CostPayload,
  pacing: PacingPayload,
  campaign: CampaignPayload,
  agent_session: AgentSessionPayload,
} as const;

export { SCHEMA_VERSION };
