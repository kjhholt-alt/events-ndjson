import { Reader } from "./reader.js";

const VOLATILE_FIELDS = ["ts", "correlation_id"] as const;

export interface Divergence {
  index: number;
  reason: string;
  a?: Record<string, unknown> | null;
  b?: Record<string, unknown> | null;
}

export interface DiffResult {
  divergence: Divergence | null;
  aCount: number;
  bCount: number;
  matched: number;
  identical: boolean;
}

export interface DiffOptions {
  ignore?: readonly string[];
  key?: (ev: Record<string, unknown>) => unknown;
}

export interface Stats {
  total: number;
  byStream: Record<string, number>;
  byEventType: Record<string, number>;
  bySource: Record<string, number>;
}

function coerceArray(
  src: string | Iterable<Record<string, unknown>>,
): Record<string, unknown>[] {
  if (typeof src === "string") {
    return new Reader(src).readAll();
  }
  return Array.from(src);
}

function strip(
  ev: Record<string, unknown>,
  ignore: Set<string>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const k of Object.keys(ev)) {
    if (!ignore.has(k)) out[k] = ev[k];
  }
  return out;
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a === null || b === null) return a === b;
  if (Array.isArray(a)) {
    if (!Array.isArray(b) || a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (!deepEqual(a[i], b[i])) return false;
    }
    return true;
  }
  if (typeof a === "object" && typeof b === "object") {
    const ao = a as Record<string, unknown>;
    const bo = b as Record<string, unknown>;
    const ak = Object.keys(ao);
    const bk = Object.keys(bo);
    if (ak.length !== bk.length) return false;
    for (const k of ak) {
      if (!deepEqual(ao[k], bo[k])) return false;
    }
    return true;
  }
  return false;
}

export function diff(
  a: string | Iterable<Record<string, unknown>>,
  b: string | Iterable<Record<string, unknown>>,
  opts: DiffOptions = {},
): DiffResult {
  const ignore = new Set(opts.ignore ?? VOLATILE_FIELDS);
  const norm = opts.key
    ? (ev: Record<string, unknown>) => opts.key!(ev)
    : (ev: Record<string, unknown>) => strip(ev, ignore);

  const arrA = coerceArray(a);
  const arrB = coerceArray(b);

  const max = Math.max(arrA.length, arrB.length);
  for (let i = 0; i < max; i++) {
    const ea = arrA[i];
    const eb = arrB[i];
    if (ea === undefined) {
      return {
        divergence: { index: i, reason: "stream A ended first", a: null, b: eb },
        aCount: arrA.length,
        bCount: i + 1,
        matched: i,
        identical: false,
      };
    }
    if (eb === undefined) {
      return {
        divergence: { index: i, reason: "stream B ended first", a: ea, b: null },
        aCount: i + 1,
        bCount: arrB.length,
        matched: i,
        identical: false,
      };
    }
    if (!deepEqual(norm(ea), norm(eb))) {
      return {
        divergence: { index: i, reason: "events differ", a: ea, b: eb },
        aCount: i + 1,
        bCount: i + 1,
        matched: i,
        identical: false,
      };
    }
  }
  return {
    divergence: null,
    aCount: arrA.length,
    bCount: arrB.length,
    matched: arrA.length,
    identical: arrA.length === arrB.length,
  };
}

export function replay(
  src: string | Iterable<Record<string, unknown>>,
  handler: (ev: Record<string, unknown>) => void,
): number {
  let n = 0;
  for (const ev of coerceArray(src)) {
    handler(ev);
    n++;
  }
  return n;
}

export function stats(
  src: string | Iterable<Record<string, unknown>>,
): Stats {
  const out: Stats = { total: 0, byStream: {}, byEventType: {}, bySource: {} };
  for (const ev of coerceArray(src)) {
    out.total += 1;
    const s = (ev.stream as string) || "?";
    const e = (ev.event_type as string) || "?";
    const src2 = (ev.source as string) || "?";
    out.byStream[s] = (out.byStream[s] || 0) + 1;
    out.byEventType[e] = (out.byEventType[e] || 0) + 1;
    out.bySource[src2] = (out.bySource[src2] || 0) + 1;
  }
  return out;
}
