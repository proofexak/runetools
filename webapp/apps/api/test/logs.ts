/** Builds session logs the way lib/events.py writes them (one JSON object per line). */
import fs from "node:fs";
import path from "node:path";

export interface Ev { ts: string; event: string; [k: string]: unknown }

export function line(e: Ev, session: string, bot: string): string {
  const { ts, ...rest } = e;
  return JSON.stringify({ ts, session, bot, ...rest }) + "\n";
}

export function writeLog(root: string, rel: string, events: Ev[], opts: { session?: string; bot?: string; crlf?: boolean } = {}) {
  const file = path.join(root, ...rel.split("/"));
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const bot = opts.bot ?? rel.split("/").at(-3)!;
  const session = opts.session ?? path.basename(rel, ".jsonl").split("_").slice(-2).join("_");
  let text = events.map((e) => line(e, session, bot)).join("");
  if (opts.crlf) text = text.replaceAll("\n", "\r\n");
  fs.writeFileSync(file, text);
  return file;
}

export function appendLog(file: string, text: string) {
  fs.appendFileSync(file, text);
}

/** A finished tanner session: 2 runs, one failed step, a pause, ends "stopped". */
export const finished: Ev[] = [
  { ts: "2026-10-05T10:00:00.000", event: "session_start", params: { hide_type: "green" }, pid: 42, account: "Zezima" },
  { ts: "2026-10-05T10:00:20.000", event: "step", state: "walk_to_tanner", result: "ok", seconds: 15, run: 1 },
  { ts: "2026-10-05T10:00:40.000", event: "step", state: "trade_ellis", result: "fail", seconds: 20, run: 1 },
  { ts: "2026-10-05T10:01:00.000", event: "step", state: "recover", result: "ok", seconds: 20, run: 1 },
  { ts: "2026-10-05T10:02:00.000", event: "pause", state: "banking", seconds: 30 },
  { ts: "2026-10-05T10:02:30.000", event: "step", state: "banking", result: "ok", seconds: 10, run: 2 },
  { ts: "2026-10-05T10:03:00.000", event: "soft_stop", state: "walk_to_tanner" },
  { ts: "2026-10-05T10:03:00.100", event: "session_end", final: "stopped", reason: "stop button", last_step: "banking",
    stats: { run: 2, step: "stopped" }, active_seconds: 150.1, paused_seconds: 30 },
];

/** A crashed session with an error + traceback. */
export const crashed: Ev[] = [
  { ts: "2026-10-05T11:00:00.000", event: "session_start", params: {}, pid: 43 },
  { ts: "2026-10-05T11:00:10.000", event: "step", state: "walk_to_tanner", result: "ok", seconds: 10, run: 1 },
  { ts: "2026-10-05T11:00:11.000", event: "error", where: "session", state: "trade_ellis", type: "ValueError",
    message: "boom", traceback: "Traceback (most recent call last):\n  ...\nValueError: boom\n" },
  { ts: "2026-10-05T11:00:11.500", event: "session_end", final: "crashed", reason: null, last_step: "trade_ellis",
    stats: { run: 1 }, active_seconds: 11.5, paused_seconds: 0 },
];

/** No session_end: killed (or still running). 3 runs, one 60 s pause. */
export const open: Ev[] = [
  { ts: "2026-10-05T12:00:00.000", event: "session_start", params: {}, pid: 44, account: "Zezima" },
  { ts: "2026-10-05T12:01:00.000", event: "step", state: "mine", result: "ok", seconds: 60, run: 1 },
  { ts: "2026-10-05T12:03:00.000", event: "pause", state: "mine", seconds: 60 },
  { ts: "2026-10-05T12:05:00.000", event: "step", state: "drop", result: "ok", seconds: 5, run: 3 },
];
