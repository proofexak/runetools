/**
 * Tails the bots' session logs into the database. Polling, not fs.watch: Docker Desktop
 * bind mounts don't deliver file events from a Windows/macOS host.
 *
 * Per file, the read position lives in ingest_cursors and moves in the same transaction
 * as the rows it produced, so a crash or restart never applies a line twice or skips one.
 * A file that got shorter than its cursor was replaced: its session is re-read from 0.
 *
 * Bots also push each line as they write it (POST /api/ingest, PRO-99) with its byte
 * offset. A pushed line is applied only when its offset is exactly the file's cursor;
 * behind it is a duplicate, ahead of it means lines were missed, so that file is re-read.
 * Reads and pushes of one file take turns (withFile), and every transaction re-checks the
 * cursor it starts from, so a line counts once whichever way it arrives.
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

type Tx = Parameters<Parameters<Db["transaction"]>[0]>[0];

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

/**
 * The log file a pushed key names — only a key findLogFiles would give an existing file
 * under the first root, so a pushed line and the tailer always share one cursor.
 */
export async function pushedLogFile(roots: string[], key: string): Promise<LogFile | null> {
  const parts = key.split("/");
  if (!roots[0] || (parts.length !== 3 && parts.length !== 4)) return null;
  const name = parts[parts.length - 1]!;
  const folders = parts.slice(0, -2);
  if (parts[parts.length - 2] !== "log" || !name.endsWith(".jsonl") || folders[1] === "log") return null;
  if (parts.some((p) => !p || /[\\:\0]/.test(p))) return null;
  if (folders.some((d) => d.startsWith(".") || SKIP_DIRS.has(d))) return null;
  const abs = path.join(path.resolve(roots[0]), ...parts);
  try {
    if (!(await fs.stat(abs)).isFile()) return null;
    // exact on-disk spelling (case-insensitive file systems), no symlinked folders: as findLogFiles keys it
    const [realRoot, real] = await Promise.all([fs.realpath(path.resolve(roots[0])), fs.realpath(abs)]);
    return posix(path.relative(realRoot, real)) === key ? { key, abs } : null;
  } catch {
    return null;
  }
}

class CursorMoved extends Error {}

/** Locks the file's cursor row for this transaction; false if it isn't at `expected`. */
async function claimCursor(tx: Tx, key: string, expected: number): Promise<boolean> {
  await tx.insert(ingestCursors).values({ path: key, offset: 0 }).onConflictDoNothing();
  const [row] = await tx.select({ offset: ingestCursors.offset }).from(ingestCursors)
    .where(eq(ingestCursors.path, key)).for("update");
  return (row?.offset ?? 0) === expected;
}

async function saveCursor(tx: Tx, key: string, offset: number) {
  await tx.update(ingestCursors).set({ offset, updatedAt: new Date() }).where(eq(ingestCursors.path, key));
}

export interface ScanResult { files: number; changed: number[]; badLines: number }

/** applied; duplicate (behind the cursor); ahead (lines missed: the file is re-read); unknown file. */
export type PushResult = "applied" | "duplicate" | "ahead" | "unknown";

export class Ingester {
  private cursors: Map<string, number> | null = null;
  private timer: NodeJS.Timeout | null = null;
  private running: Promise<unknown> | null = null;
  private turns = new Map<string, Promise<unknown>>();
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

  /** Runs fn after every earlier read / push of the same file has finished. */
  private withFile<T>(key: string, fn: () => Promise<T>): Promise<T> {
    const run = (this.turns.get(key) ?? Promise.resolve()).then(fn);
    const done = run.catch(() => {});
    this.turns.set(key, done);
    void done.then(() => { if (this.turns.get(key) === done) this.turns.delete(key); });
    return run;
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

  private ingestFile(f: LogFile): Promise<{ sessionId: number | null; bad: number }> {
    return this.withFile(f.key, () => this.readFile(f));
  }

  private async readFile(f: LogFile): Promise<{ sessionId: number | null; bad: number }> {
    const cursors = this.cursors ??= await this.loadCursors();
    const stat = await fs.stat(f.abs);
    const at = cursors.get(f.key) ?? 0;
    let offset = at;
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
      // another API process (pnpm dev + the container on one database) moved it: reload
      if (!(await claimCursor(tx, f.key, at))) throw new CursorMoved(`${f.key}: cursor moved`);
      if (reset) await tx.delete(sessions).where(eq(sessions.file, f.key));
      const id = await applyEvents(tx, f.key, events);
      if (id !== null) await tx.update(sessions).set({ fileMtime: stat.mtime }).where(eq(sessions.id, id));
      await saveCursor(tx, f.key, next);
      return id;
    });
    cursors.set(f.key, next);
    return { sessionId, bad };
  }

  /**
   * A line a bot just wrote, pushed with its byte offset (no trailing newline). Applied only
   * at the cursor; ahead of it, the file is re-read in the background to catch up.
   */
  async push(key: string, offset: number, line: string): Promise<PushResult> {
    const f = await pushedLogFile(await this.roots(), key);
    if (!f) return "unknown";
    const result = await this.withFile(key, async (): Promise<PushResult> => {
      const cursors = this.cursors ??= await this.loadCursors();
      const at = cursors.get(key) ?? 0;
      if (offset < at) return "duplicate";
      if (offset > at) return "ahead";
      const { events, bad } = parseLines(`${line}\n`);   // a bad line moves the cursor too, as tailing does
      const next = offset + Buffer.byteLength(line, "utf8") + 1;
      let id: number | null;
      try {
        id = await this.db.transaction(async (tx) => {
          if (!(await claimCursor(tx, key, at))) throw new CursorMoved(`${key}: cursor moved`);
          const sessionId = await applyEvents(tx, key, events);
          // the file was written just now; its mtime may not show it yet through a bind mount
          if (sessionId !== null) await tx.update(sessions).set({ fileMtime: new Date() }).where(eq(sessions.id, sessionId));
          await saveCursor(tx, key, next);
          return sessionId;
        });
      } catch (err) {
        if (!(err instanceof CursorMoved)) throw err;
        this.cursors = null;
        return "ahead";
      }
      cursors.set(key, next);
      this.badLines += bad;
      if (id !== null) this.bus?.emit({ type: "sessions", ids: [id] });
      return "applied";
    });
    if (result === "ahead") void this.catchUp(f);
    return result;
  }

  private async catchUp(f: LogFile) {
    try {
      const r = await this.ingestFile(f);
      this.badLines += r.bad;
      if (r.sessionId !== null) this.bus?.emit({ type: "sessions", ids: [r.sessionId] });
    } catch (err) {
      this.log(`ingest ${f.key} failed`, err);
      this.cursors = null;
    }
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
    await Promise.all([...this.turns.values()]);
  }
}
