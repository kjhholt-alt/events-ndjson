import { mkdirSync } from "node:fs";
import { open, type FileHandle } from "node:fs/promises";
import { dirname } from "node:path";
import { randomUUID } from "node:crypto";

import { isRegistered } from "./registry.js";
import { validateEnvelope, validateStreamPayload } from "./validate.js";
import { StreamError, SCHEMA_VERSION, type Event } from "./types.js";

export interface WriterOptions {
  stream: string;
  source: string;
  path: string;
  validatePayload?: boolean;
  ensureDir?: boolean;
}

export interface AppendInput {
  event_type: string;
  payload: Record<string, unknown>;
  ts?: string;
  correlation_id?: string;
}

function utcTs(): string {
  const d = new Date();
  const pad = (n: number, w = 2) => n.toString().padStart(w, "0");
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}` +
    `.${pad(d.getUTCMilliseconds(), 3)}Z`
  );
}

/**
 * Atomic NDJSON writer.
 *
 * Each append writes a single JSON line plus newline in one fs write call,
 * with the file opened in append mode so concurrent writers do not interleave
 * bytes within a line.
 */
export class Writer {
  readonly stream: string;
  readonly source: string;
  readonly path: string;

  private readonly _validatePayload: boolean;
  private _handle: FileHandle | null = null;
  // Promise chain that serializes writes within this Writer instance.
  private _chain: Promise<unknown> = Promise.resolve();

  constructor(opts: WriterOptions) {
    if (!isRegistered(opts.stream)) {
      throw new StreamError(
        `stream "${opts.stream}" is not registered. ` +
          `Add a schema in spec/schema/v1/streams/ first.`,
      );
    }
    this.stream = opts.stream;
    this.source = opts.source;
    this.path = opts.path;
    this._validatePayload = opts.validatePayload ?? true;
    if (opts.ensureDir ?? true) {
      mkdirSync(dirname(this.path), { recursive: true });
    }
  }

  private async _ensureOpen(): Promise<FileHandle> {
    if (!this._handle) {
      this._handle = await open(this.path, "a");
    }
    return this._handle;
  }

  async append(input: AppendInput): Promise<Event> {
    const envelope: Event = {
      ts: input.ts ?? utcTs(),
      source: this.source,
      stream: this.stream,
      event_type: input.event_type,
      payload: input.payload,
      correlation_id: input.correlation_id ?? randomUUID(),
      schema_version: SCHEMA_VERSION,
    };

    validateEnvelope(envelope);
    if (this._validatePayload) {
      validateStreamPayload(this.stream, input.payload);
    }

    const line = JSON.stringify(envelope) + "\n";
    const buf = Buffer.from(line, "utf8");

    // Serialize through the writer's chain so we never call write() in
    // parallel on the same FileHandle (which would interleave on some OSes).
    // Combined with O_APPEND, this guarantees full-line atomicity.
    const next = this._chain.then(async () => {
      const handle = await this._ensureOpen();
      await handle.write(buf, 0, buf.length, null);
    });
    this._chain = next.catch(() => undefined);
    await next;
    return envelope;
  }

  async close(): Promise<void> {
    await this._chain.catch(() => undefined);
    if (this._handle) {
      try {
        await this._handle.close();
      } finally {
        this._handle = null;
      }
    }
  }
}
