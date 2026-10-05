import fs from "node:fs";
import path from "node:path";
import { asc, eq, sql } from "drizzle-orm";
import { beforeEach, describe, expect, it } from "vitest";
import { Bus } from "../src/bus.js";
import type { Db } from "../src/db/index.js";
import { dailyActivity, errors, ingestCursors, sessions, steps } from "../src/db/schema.js";
import { findLogFiles, Ingester } from "../src/ingest/ingester.js";
import { completeLines, parseLines } from "../src/ingest/parse.js";
import { testDb, tmpDir } from "./helpers.js";
import { appendLog, crashed, finished, line, open, writeLog } from "./logs.js";

describe("parseLines (logreport.parse_lines rules)", () => {
  it("skips blank lines and counts unusable ones", () => {
    const text = [
      '{"ts": "2026-10-05T10:00:00", "event": "step"}',
      "",
      "   ",
      '{"ts": "2026-10-05T10:00:01", "eve',      // cut short
      "[1, 2]",                                 // not an object
      '{"ts": "2026-10-05T10:00:02"}',           // no event
      '{"ts": "2026-10-05T10:00:03", "event": "pause"}\r',
    ].join("\n");
    const { events, bad } = parseLines(text);
    expect(events.map((e) => e.event)).toEqual(["step", "pause"]);
    expect(bad).toBe(3);
  });

  it("reads Python's NaN / Infinity as null", () => {
    const { events, bad } = parseLines('{"ts": "2026-10-05T10:00:00", "event": "step", "seconds": NaN, "x": -Infinity}\n');
    expect(bad).toBe(0);
    expect(events[0]).toMatchObject({ seconds: null, x: null });
  });

  it("completeLines keeps a line still being written for later", () => {
    const { text, bytes } = completeLines(Buffer.from('{"a":1}\n{"b":'));
    expect(text).toBe('{"a":1}\n');
    expect(bytes).toBe(8);
    expect(completeLines(Buffer.from("no newline yet")).bytes).toBe(0);
  });
});

describe("findLogFiles", () => {
  it("finds <bot>/log and <group>/<bot>/log, keyed relative to the first root", async () => {
    const root = tmpDir();
    writeLog(root, "tanner/log/tanner_20261005_100000.jsonl", finished);
    writeLog(root, "miner/varrock_exp/log/varrock_exp_20261005_100000.jsonl", finished);
    writeLog(root, "log/launcher.jsonl", finished, { bot: "x" });                 // not a session log
    writeLog(root, "tanner/log/tanner_20261005_100000.log", []);                  // text log
    writeLog(root, "webapp/node_modules/x/log/y.jsonl", finished, { bot: "x" });  // skipped dirs
    const other = tmpDir();
    writeLog(other, "choc/log/choc_20261005_100000.jsonl", finished);
    const files = await findLogFiles([root, other]);
    expect(files.map((f) => f.key).sort()).toEqual([
      "miner/varrock_exp/log/varrock_exp_20261005_100000.jsonl",
      path.join(other, "choc/log/choc_20261005_100000.jsonl").split(path.sep).join("/"),
      "tanner/log/tanner_20261005_100000.jsonl",
    ].sort());
  });
});

describe("Ingester", () => {
  let db: Db;
  let root: string;
  let ingester: Ingester;
  beforeEach(async () => {
    db = (await testDb()).db;
    root = tmpDir();
    ingester = new Ingester(db, async () => [root]);
  });

  const session = async (file: string) => {
    const [s] = await db.select().from(sessions).where(eq(sessions.file, file));
    return s!;
  };
  const stepsOf = (id: number) => db.select().from(steps).where(eq(steps.sessionId, id)).orderBy(asc(steps.id));

  it("summarises a finished session like logreport.summarize", async () => {
    writeLog(root, "tanner/log/tanner_20261005_100000.jsonl", finished, { crlf: true });
    await ingester.scanOnce();
    const s = await session("tanner/log/tanner_20261005_100000.jsonl");
    expect(s).toMatchObject({
      stamp: "20261005_100000", bot: "tanner", account: "Zezima", pid: 42, params: { hide_type: "green" },
      startedAt: "2026-10-05 10:00:00", endedAt: "2026-10-05 10:03:00.1", lastEventAt: "2026-10-05 10:03:00.1",
      final: "stopped", reason: "stop button", lastStep: "banking",
      activeSeconds: 150.1, pausedSeconds: 30, pauses: 1, runs: 2, errorCount: 0, hasStart: true,
    });
    expect(s.fileMtime).toBeInstanceOf(Date);
    const st = await stepsOf(s.id);
    expect(st.map((x) => [x.state, x.result, x.run])).toEqual([
      ["walk_to_tanner", "ok", 1], ["trade_ellis", "fail", 1], ["recover", "ok", 1], ["banking", "ok", 2],
    ]);
  });

  it("records errors with tracebacks", async () => {
    writeLog(root, "tanner/log/tanner_20261005_110000.jsonl", crashed);
    await ingester.scanOnce();
    const s = await session("tanner/log/tanner_20261005_110000.jsonl");
    expect(s).toMatchObject({ final: "crashed", errorCount: 1, account: null, lastStep: "trade_ellis" });
    const [e] = await db.select().from(errors).where(eq(errors.sessionId, s.id));
    expect(e).toMatchObject({ type: "ValueError", message: "boom", state: "trade_ellis", where: "session" });
    expect(e!.traceback).toContain("ValueError: boom");
  });

  it("an open session: active = wall time − pauses, runs = last step's run", async () => {
    const file = writeLog(root, "miner/golden_nuggets/log/golden_nuggets_20261005_120000.jsonl", open);
    appendLog(file, '{"ts": "2026-10-05T12:06:00", "sess');     // hard kill mid-line
    const res = await ingester.scanOnce();
    expect(res.badLines).toBe(0);                                // never read: not a whole line
    const s = await session("miner/golden_nuggets/log/golden_nuggets_20261005_120000.jsonl");
    expect(s).toMatchObject({
      bot: "golden_nuggets", final: null, endedAt: null, lastStep: "drop", runs: 3,
      pausedSeconds: 60, activeSeconds: 300 - 60, lastEventAt: "2026-10-05 12:05:00",
    });
  });

  it("tails a growing file: same result as reading it whole, nothing applied twice", async () => {
    const rel = "tanner/log/tanner_20261005_100000.jsonl";
    const all = finished.map((e) => line(e, "20261005_100000", "tanner")).join("");
    const file = path.join(root, ...rel.split("/"));
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const cut = all.indexOf("trade_ellis") + 5;                  // mid-line
    fs.writeFileSync(file, all.slice(0, cut));
    await ingester.scanOnce();
    let s = await session(rel);
    expect(s).toMatchObject({ final: null, runs: 1, lastStep: "walk_to_tanner" });
    expect(await stepsOf(s.id)).toHaveLength(1);

    appendLog(file, all.slice(cut));
    await ingester.scanOnce();
    await ingester.scanOnce();                                    // nothing new: no-op
    s = await session(rel);
    expect(s).toMatchObject({ final: "stopped", runs: 2, activeSeconds: 150.1, pauses: 1 });
    expect(await stepsOf(s.id)).toHaveLength(4);
    const [cursor] = await db.select().from(ingestCursors).where(eq(ingestCursors.path, rel));
    expect(cursor!.offset).toBe(Buffer.byteLength(all));
  });

  it("a restarted ingester resumes from the stored cursors", async () => {
    writeLog(root, "tanner/log/tanner_20261005_100000.jsonl", finished);
    await ingester.scanOnce();
    const again = new Ingester(db, async () => [root]);
    const res = await again.scanOnce();
    expect(res.changed).toEqual([]);
    const [{ n }] = (await db.select({ n: sql<number>`count(*)::int` }).from(steps)) as [{ n: number }];
    expect(n).toBe(4);
  });

  it("re-reads a file that was replaced by a shorter one", async () => {
    const file = writeLog(root, "tanner/log/tanner_20261005_100000.jsonl", finished);
    await ingester.scanOnce();
    fs.writeFileSync(file, line(crashed[0]!, "20261005_100000", "tanner"));
    await ingester.scanOnce();
    const s = await session("tanner/log/tanner_20261005_100000.jsonl");
    expect(s).toMatchObject({ final: null, pid: 43, runs: 0 });
    expect(await stepsOf(s.id)).toHaveLength(0);
  });

  it("announces changed sessions on the bus", async () => {
    const bus = new Bus();
    const seen: unknown[] = [];
    bus.on((e) => seen.push(e));
    const ing = new Ingester(db, async () => [root], bus);
    writeLog(root, "tanner/log/tanner_20261005_100000.jsonl", finished);
    await ing.scanOnce();
    await ing.scanOnce();
    expect(seen).toEqual([{ type: "sessions", ids: [1] }]);
  });

  it("daily_activity splits a session across midnight by wall time", async () => {
    writeLog(root, "tanner/log/tanner_20261004_230000.jsonl", [
      { ts: "2026-10-04T23:00:00.000", event: "session_start", params: {}, account: "Zezima" },
      { ts: "2026-10-05T00:59:00.000", event: "step", state: "x", result: "ok", seconds: 1, run: 40 },
      { ts: "2026-10-05T01:00:00.000", event: "session_end", final: "done", stats: { run: 40 },
        active_seconds: 3600, paused_seconds: 3600 },
    ]);
    writeLog(root, "tanner/log/tanner_20261005_100000.jsonl", finished);
    await ingester.scanOnce();
    const rows = await db.select().from(dailyActivity).orderBy(asc(dailyActivity.day));
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ account: "Zezima", bot: "tanner", day: "2026-10-04" });
    expect(rows[0]!.hours).toBeCloseTo(0.5);
    expect(rows[0]!.runs).toBeCloseTo(20);
    expect(rows[1]!.day).toBe("2026-10-05");
    expect(rows[1]!.hours).toBeCloseTo(0.5 + 150.1 / 3600);
    expect(rows[1]!.runs).toBeCloseTo(22);
  });
});
