/**
 * Tails the bots' session logs into the database. Polling, not fs.watch: Docker Desktop
 * bind mounts don't deliver file events from a Windows/macOS host.
 *
 * Per file, the read position lives in ingest_cursors and moves in the same transaction
 * as the rows it produced, so a crash or restart never applies a line twice or skips one.
 * A file that got shorter than its cursor was replaced: its session is re-read from 0.
 *
 * Files are keyed by their path relative to the first log root ("tanner/log/x.jsonl"), so
 * the API on the host and in the container (repo at /repo) share one history; files under
 * any other root are keyed by absolute path.
 */
import fs from "node:fs/promises";
import path from "node:path";
import { eq } from "drizzle-orm";
import type { Bus } from "../bus.js";
import type { Db } from "../db/index.js";
import { ingestCursors, sessions } from "../db/schema.js";
import { applyEvents } from "./apply.js";
import { completeLines, parseLines } from "./parse.js";

const SKIP_DIRS = new Set(["node_modules", "webapp", "data", "__pycache__"]);
const MAX_CHUNK = 4 * 1024 * 1024;

export interface LogFile { key: string; abs: string }

async function dirs(p: string): Promise<string[]> {
  try {
    const entries = await fs.readdir(p, { withFileTypes: true });
    return entries.filter((e) => e.isDirectory() && !e.name.startsWith(".") && !SKIP_DIRS.has(e.name)).map((e) => e.name);
  } catch {
    return [];
  }
}

async function jsonl(dir: string): Promise<string[]> {
  try {
    return (await fs.readdir(dir)).filter((n) => n.endsWith(".jsonl")).map((n) => path.join(dir, n));
  } catch {
    return [];
  }
}

const posix = (p: string) => p.split(path.sep).join("/");

/** <root>/<bot>/log/*.jsonl and <root>/<group>/<bot>/log/*.jsonl — what logreport.load_sessions reads. */
export async function findLogFiles(roots: string[]): Promise<LogFile[]> {
  const out: LogFile[] = [];
  for (const [i, rawRoot] of roots.entries()) {
    const root = path.resolve(rawRoot);
    const key = (abs: string) => (i === 0 ? posix(path.relative(root, abs)) : posix(abs));
    for (const d of await dirs(root)) {
      for (const f of await jsonl(path.join(root, d, "log"))) out.push({ key: key(f), abs: f });
      for (const sub of await dirs(path.join(root, d))) {
        if (sub === "log") continue;
        for (const f of await jsonl(path.join(root, d, sub, "log"))) out.push({ key: key(f), abs: f });
      }
    }
  }
  return out;
}

export interface ScanResult { files: number; changed: number[]; badLines: number }

export class Ingester {
  private cursors: Map<string, number> | null = null;
  private timer: NodeJS.Timeout | null = null;
  private running: Promise<unknown> | null = null;
  private stopped = false;
  badLines = 0;

  constructor(
    private db: Db,
    private roots: () => Promise<string[]>,
    private bus?: Bus,
    private log: (msg: string, err?: unknown) => void = () => {},
  ) {}

  private async loadCursors() {
    const rows = await this.db.select().from(ingestCursors);
    return new Map(rows.map((r) => [r.path, r.offset]));
  }

  /** One pass over every log file. Concurrent calls share the pass in flight. */
  scanOnce(): Promise<ScanResult> {
    if (this.running) return this.running as Promise<ScanResult>;
    const p = this.scan().finally(() => { this.running = null; });
    this.running = p;
    return p;
  }

  private async scan(): Promise<ScanResult> {
    this.cursors ??= await this.loadCursors();
    const files = await findLogFiles(await this.roots());
    const changed: number[] = [];
    let badLines = 0;
    for (const f of files) {
      try {
        const r = await this.ingestFile(f);
        if (r.sessionId !== null) changed.push(r.sessionId);
        badLines += r.bad;
      } catch (err) {
        this.log(`ingest ${f.key} failed`, err);
        this.cursors = null;           // reload: the transaction rolled back
      }
    }
    this.badLines += badLines;
    if (changed.length && this.bus) this.bus.emit({ type: "sessions", ids: changed });
    return { files: files.length, changed, badLines };
  }

  private async ingestFile(f: LogFile): Promise<{ sessionId: number | null; bad: number }> {
    const cursors = this.cursors ??= await this.loadCursors();
    const stat = await fs.stat(f.abs);
    let offset = cursors.get(f.key) ?? 0;
    let reset = false;
    if (stat.size < offset) {           // truncated / replaced: start over
      offset = 0;
      reset = true;
    }
    if (stat.size === offset && !reset) return { sessionId: null, bad: 0 };

    const handle = await fs.open(f.abs, "r");
    let chunk: Buffer;
    try {
      let want = Math.min(stat.size - offset, MAX_CHUNK);
      chunk = Buffer.alloc(want);
      let { bytesRead } = await handle.read(chunk, 0, want, offset);
      chunk = chunk.subarray(0, bytesRead);
      if (completeLines(chunk).bytes === 0 && want < stat.size - offset) {
        // one line longer than MAX_CHUNK: read to the end
        want = stat.size - offset;
        chunk = Buffer.alloc(want);
        ({ bytesRead } = await handle.read(chunk, 0, want, offset));
        chunk = chunk.subarray(0, bytesRead);
      }
    } finally {
      await handle.close();
    }
    const { text, bytes } = completeLines(chunk);
    if (bytes === 0 && !reset) return { sessionId: null, bad: 0 };
    const { events, bad } = parseLines(text);
    const next = offset + bytes;

    const sessionId = await this.db.transaction(async (tx) => {
      if (reset) await tx.delete(sessions).where(eq(sessions.file, f.key));
      const id = await applyEvents(tx, f.key, events);
      if (id !== null) await tx.update(sessions).set({ fileMtime: stat.mtime }).where(eq(sessions.id, id));
      await tx.insert(ingestCursors).values({ path: f.key, offset: next })
        .onConflictDoUpdate({ target: ingestCursors.path, set: { offset: next, updatedAt: new Date() } });
      return id;
    });
    cursors.set(f.key, next);
    return { sessionId, bad };
  }

  /** Polls until stop(). The first pass is the backfill of every existing log. */
  start(pollMs: number) {
    this.stopped = false;
    const tick = async () => {
      try {
        await this.scanOnce();
      } catch (err) {
        this.log("ingest pass failed", err);
      }
      if (!this.stopped) this.timer = setTimeout(tick, pollMs);
    };
    void tick();
  }

  async stop() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    await this.running?.catch(() => {});
  }
}
