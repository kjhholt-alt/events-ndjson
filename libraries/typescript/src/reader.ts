import { existsSync, readFileSync, statSync, openSync, readSync, closeSync, writeFileSync } from "node:fs";

import { validateEnvelope, validateStreamPayload } from "./validate.js";
import { EnvelopeError, StreamError, ValidationError } from "./types.js";

export interface ReaderOptions {
  strict?: boolean;
  validatePayload?: boolean;
}

export interface FilterOptions {
  stream?: string;
  event_type?: string;
  source?: string;
  correlation_id?: string;
  predicate?: (ev: Record<string, unknown>) => boolean;
}

export interface TailOptions {
  follow?: boolean;
  fromStart?: boolean;
  pollIntervalMs?: number;
  stop?: () => boolean;
}

/**
 * NDJSON reader. Tolerates a partial last line (mid-write).
 */
export class Reader {
  readonly path: string;
  readonly strict: boolean;
  readonly validatePayload: boolean;

  constructor(path: string, opts: ReaderOptions = {}) {
    this.path = path;
    this.strict = opts.strict ?? true;
    this.validatePayload = opts.validatePayload ?? true;
  }

  private _validate(obj: unknown): asserts obj is Record<string, unknown> {
    validateEnvelope(obj);
    if (this.validatePayload) {
      const ev = obj as Record<string, unknown>;
      validateStreamPayload(ev.stream as string, ev.payload);
    }
  }

  private _parseLine(line: string): Record<string, unknown> | null {
    const trimmed = line.trim();
    if (!trimmed) return null;
    let obj: unknown;
    try {
      obj = JSON.parse(trimmed);
    } catch (e) {
      if (this.strict) {
        throw new ValidationError(`invalid JSON: ${(e as Error).message}`);
      }
      return null;
    }
    try {
      this._validate(obj);
    } catch (e) {
      if (this.strict) throw e;
      return null;
    }
    return obj as Record<string, unknown>;
  }

  readAll(): Record<string, unknown>[] {
    if (!existsSync(this.path)) return [];
    const raw = readFileSync(this.path);
    if (raw.length === 0) return [];
    const lastNl = raw.lastIndexOf(0x0a);
    if (lastNl === -1) return []; // Whole file is partial.
    const usable = raw.subarray(0, lastNl + 1).toString("utf8");
    const events: Record<string, unknown>[] = [];
    for (const line of usable.split("\n")) {
      const ev = this._parseLine(line);
      if (ev) events.push(ev);
    }
    return events;
  }

  *stream(): Generator<Record<string, unknown>, void, void> {
    for (const ev of this.readAll()) yield ev;
  }

  filter(opts: FilterOptions): FilteredReader {
    return new FilteredReader(this, opts);
  }

  /**
   * Async iterator yielding events as they appear. Set follow=true to keep
   * polling after EOF.
   */
  async *tail(opts: TailOptions = {}): AsyncGenerator<Record<string, unknown>> {
    const follow = opts.follow ?? false;
    const fromStart = opts.fromStart ?? true;
    const poll = opts.pollIntervalMs ?? 100;
    const stop = opts.stop ?? (() => false);

    if (!existsSync(this.path)) {
      writeFileSync(this.path, "");
    }

    const fd = openSync(this.path, "r");
    try {
      let pos = 0;
      if (!fromStart) {
        pos = statSync(this.path).size;
      }
      let buffer = Buffer.alloc(0);
      const chunk = Buffer.alloc(65536);
      while (true) {
        const n = readSync(fd, chunk, 0, chunk.length, pos);
        if (n > 0) {
          pos += n;
          buffer = Buffer.concat([buffer, chunk.subarray(0, n)]);
          while (true) {
            const nl = buffer.indexOf(0x0a);
            if (nl === -1) break;
            const raw = buffer.subarray(0, nl).toString("utf8");
            buffer = buffer.subarray(nl + 1);
            const ev = this._parseLine(raw);
            if (ev) yield ev;
          }
        } else {
          if (!follow) return;
          if (stop()) return;
          await new Promise((r) => setTimeout(r, poll));
        }
      }
    } finally {
      closeSync(fd);
    }
  }
}

export class FilteredReader {
  constructor(
    private readonly _reader: Reader,
    private readonly _opts: FilterOptions,
  ) {}

  private _matches(ev: Record<string, unknown>): boolean {
    const o = this._opts;
    if (o.stream !== undefined && ev.stream !== o.stream) return false;
    if (o.event_type !== undefined && ev.event_type !== o.event_type) return false;
    if (o.source !== undefined && ev.source !== o.source) return false;
    if (o.correlation_id !== undefined && ev.correlation_id !== o.correlation_id)
      return false;
    if (o.predicate !== undefined && !o.predicate(ev)) return false;
    return true;
  }

  events(): Record<string, unknown>[] {
    return this._reader.readAll().filter((ev) => this._matches(ev));
  }

  *stream(): Generator<Record<string, unknown>, void, void> {
    for (const ev of this._reader.stream()) {
      if (this._matches(ev)) yield ev;
    }
  }
}

// Re-export for convenience
export { EnvelopeError, StreamError, ValidationError };
