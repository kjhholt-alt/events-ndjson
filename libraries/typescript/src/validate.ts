import Ajv2020, { type ValidateFunction } from "ajv/dist/2020.js";

import { envelopeSchema, streamSchema } from "./registry.js";
import { EnvelopeError, StreamError, SCHEMA_VERSION } from "./types.js";

const TS_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;

// Schemas declare draft 2020-12 — use the matching Ajv build.
const ajv = new Ajv2020({ allErrors: true, strict: false });

let _envelopeValidator: ValidateFunction | undefined;
const _streamValidators: Map<string, ValidateFunction> = new Map();

function envelopeValidator(): ValidateFunction {
  if (!_envelopeValidator) {
    _envelopeValidator = ajv.compile(envelopeSchema());
  }
  return _envelopeValidator;
}

function streamValidator(stream: string): ValidateFunction {
  const cached = _streamValidators.get(stream);
  if (cached) return cached;
  const v = ajv.compile(streamSchema(stream));
  _streamValidators.set(stream, v);
  return v;
}

export function validateEnvelope(obj: unknown): asserts obj is Record<string, unknown> {
  if (typeof obj !== "object" || obj === null || Array.isArray(obj)) {
    throw new EnvelopeError("event must be a JSON object");
  }
  const validate = envelopeValidator();
  if (!validate(obj)) {
    const msg = (validate.errors || [])
      .slice(0, 5)
      .map((e) => `${e.instancePath || "/"}: ${e.message}`)
      .join("; ");
    throw new EnvelopeError(`envelope validation failed: ${msg}`);
  }
  const ev = obj as Record<string, unknown>;
  if (typeof ev.ts !== "string" || !TS_RE.test(ev.ts)) {
    throw new EnvelopeError(
      `ts must match YYYY-MM-DDTHH:MM:SS.sssZ, got ${JSON.stringify(ev.ts)}`,
    );
  }
  if (ev.schema_version !== SCHEMA_VERSION) {
    throw new EnvelopeError(
      `schema_version must be "${SCHEMA_VERSION}", got ${JSON.stringify(ev.schema_version)}`,
    );
  }
}

export function validateStreamPayload(stream: string, payload: unknown): void {
  const validate = streamValidator(stream);
  if (!validate(payload)) {
    const msg = (validate.errors || [])
      .slice(0, 5)
      .map((e) => `${e.instancePath || "/"}: ${e.message}`)
      .join("; ");
    throw new StreamError(`stream "${stream}" payload invalid: ${msg}`);
  }
}

export function validateEvent(obj: unknown): asserts obj is Record<string, unknown> {
  validateEnvelope(obj);
  const ev = obj as Record<string, unknown>;
  validateStreamPayload(ev.stream as string, ev.payload);
}
