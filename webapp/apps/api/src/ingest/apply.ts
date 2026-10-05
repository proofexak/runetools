/**
 * Folds newly read events of one log file into its `sessions` row (+ steps, errors).
 * The result for a whole file equals lib/logreport.summarize, however the file was
 * split into reads:
 *   - session_end, when present, decides final / reason / last_step / active / paused / runs;
 *   - without it the session is open: active = (last event − start) − logged pauses,
 *     runs = the last step's run number.
 */
import { eq } from "drizzle-orm";
import type { Db } from "../db/index.js";
import { errors, sessions, steps } from "../db/schema.js";
import { tsMillis, type LogEvent } from "./parse.js";

type Tx = Parameters<Parameters<Db["transaction"]>[0]>[0];
type SessionRow = typeof sessions.$inferSelect;

const str = (v: unknown): string | null => (typeof v === "string" ? v : v == null ? null : String(v));
const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const int = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? Math.trunc(v) : null);
const wall = (ts: string) => ts.replace(" ", "T");

/** Applies events (file order) to the session of `file`; returns its id, or null if nothing to do. */
export async function applyEvents(tx: Tx, file: string, events: LogEvent[]): Promise<number | null> {
  if (events.length === 0) return null;
  const [existing] = await tx.select().from(sessions).where(eq(sessions.file, file));
  const first = events[0]!;
  const s: Omit<SessionRow, "id"> & { id?: number } = existing ?? {
    file,
    stamp: str(first.session),
    bot: str(first.bot),
    account: null,
    pid: null,
    params: {},
    startedAt: wall(first.ts),
    lastEventAt: wall(first.ts),
    endedAt: null,
    final: null,
    reason: null,
    lastStep: null,
    activeSeconds: 0,
    pausedSeconds: 0,
    pauses: 0,
    runs: 0,
    errorCount: 0,
    hasStart: false,
    fileMtime: null,
  };
  const newSteps: (typeof steps.$inferInsert)[] = [];
  const newErrors: (typeof errors.$inferInsert)[] = [];
  let lastRun: number | null = null;

  for (const e of events) {
    if (tsMillis(e.ts) > tsMillis(s.lastEventAt)) s.lastEventAt = wall(e.ts);
    switch (e.event) {
      case "session_start":
        // the first session_start defines the start (logreport: next(... session_start), else first event)
        if (!s.hasStart) {
          s.hasStart = true;
          s.startedAt = wall(e.ts);
          s.account = str(e.account);
          s.pid = int(e.pid);
          s.params = e.params && typeof e.params === "object" ? (e.params as Record<string, unknown>) : {};
          s.stamp ??= str(e.session);
          s.bot ??= str(e.bot);
        }
        break;
      case "step": {
        const state = str(e.state) ?? "?";
        newSteps.push({ sessionId: 0, ts: wall(e.ts), state, result: str(e.result), seconds: num(e.seconds), run: int(e.run) });
        if (s.final === null) s.lastStep = state;
        lastRun = int(e.run);
        break;
      }
      case "pause":
        s.pauses += 1;
        if (s.final === null) s.pausedSeconds += num(e.seconds);
        break;
      case "error":
        newErrors.push({
          sessionId: 0, ts: wall(e.ts), type: str(e.type), message: str(e.message),
          traceback: str(e.traceback), state: str(e.state), where: str(e.where),
        });
        s.errorCount += 1;
        break;
      case "session_end": {
        s.final = str(e.final) ?? "unknown";
        s.reason = str(e.reason);
        s.lastStep = str(e.last_step);
        s.endedAt = wall(e.ts);
        s.activeSeconds = num(e.active_seconds);
        s.pausedSeconds = num(e.paused_seconds);
        s.runs = int((e.stats as Record<string, unknown> | undefined)?.run) ?? 0;
        break;
      }
    }
  }

  if (s.final === null) {
    if (lastRun !== null) s.runs = lastRun;
    else if (newSteps.length > 0) s.runs = 0;   // logreport: `steps[-1].get("run") or 0`
    s.activeSeconds = (tsMillis(s.lastEventAt) - tsMillis(s.startedAt)) / 1000 - s.pausedSeconds;
  }

  const { id: _id, ...values } = s;
  let id: number;
  if (existing) {
    id = existing.id;
    await tx.update(sessions).set(values).where(eq(sessions.id, id));
  } else {
    const [row] = await tx.insert(sessions).values(values).returning({ id: sessions.id });
    id = row!.id;
  }
  for (let i = 0; i < newSteps.length; i += 1000) {
    await tx.insert(steps).values(newSteps.slice(i, i + 1000).map((r) => ({ ...r, sessionId: id })));
  }
  if (newErrors.length) await tx.insert(errors).values(newErrors.map((r) => ({ ...r, sessionId: id })));
  return id;
}
