/** Bot pushes (POST /api/ingest) and live status (PRO-99). */
import fs from "node:fs";
import path from "node:path";
import { asc, eq } from "drizzle-orm";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ensureBotToken } from "../src/bot-token.js";
import { Bus } from "../src/bus.js";
import { ingestCursors, sessions, steps } from "../src/db/schema.js";
import { Ingester, pushedLogFile } from "../src/ingest/ingester.js";
import { overview } from "../src/stats.js";
import { HOST, makeApp, tmpDir, type TestApp } from "./helpers.js";
import { finished, line, type Ev } from "./logs.js";

const TOKEN = "a".repeat(64);
const REL = "tanner/log/tanner_20261005_100000.jsonl";

let t: TestApp;
let root: string;
let bus: Bus;
let fed: number[][];

beforeEach(async () => {
  t = await makeApp();
  root = t.ctx.config.logRoots[0]!;
  bus = new Bus();
  fed = [];
  bus.on((e) => { if (e.type === "sessions") fed.push(e.ids); });
  t.ctx.ingester = new Ingester(t.ctx.db, async () => [root], bus);
  t.ctx.botToken = TOKEN;
});
afterEach(async () => {
  await t.ctx.ingester!.stop();
  await t.close();
});

/** Writes events like lib/events.py (binary, "\n") and returns each line with its byte offset. */
function writeEvents(rel: string, events: Ev[], session = "20261005_100000", bot = "tanner") {
  const file = path.join(root, ...rel.split("/"));
  fs.mkdirSync(path.dirname(file), { recursive: true });
  let offset = fs.existsSync(file) ? fs.statSync(file).size : 0;
  const out: { offset: number; line: string }[] = [];
  for (const e of events) {
    const text = line(e, session, bot);
    fs.appendFileSync(file, text);
    out.push({ offset, line: text.slice(0, -1) });
    offset += Buffer.byteLength(text);
  }
  return out;
}

const push = (body: unknown, headers: Record<string, string> = {}) => t.app.inject({
  method: "POST", url: "/api/ingest", payload: body as object,
  headers: { host: HOST, authorization: `Bearer ${TOKEN}`, ...headers },
});

const session = async (file = REL) => (await t.ctx.db.select().from(sessions).where(eq(sessions.file, file)))[0];
const stepRows = async (id: number) => t.ctx.db.select().from(steps).where(eq(steps.sessionId, id)).orderBy(asc(steps.id));
const cursor = async (file = REL) =>
  (await t.ctx.db.select().from(ingestCursors).where(eq(ingestCursors.path, file)))[0]?.offset;

describe("POST /api/ingest auth", () => {
  it("needs the bot token, not a login", async () => {
    const [l] = writeEvents(REL, finished.slice(0, 1));
    expect((await push({ file: REL, ...l }, { authorization: "" })).statusCode).toBe(401);
    expect((await push({ file: REL, ...l }, { authorization: `Bearer ${"b".repeat(64)}` })).statusCode).toBe(401);
    expect((await push({ file: REL, ...l }, { authorization: TOKEN })).statusCode).toBe(401);   // no "Bearer"
    t.ctx.botToken = null;
    expect((await push({ file: REL, ...l })).statusCode).toBe(401);
    t.ctx.botToken = TOKEN;
    const ok = await push({ file: REL, ...l });                      // no cookie, no CSRF token
    expect(ok.statusCode).toBe(200);
    expect(ok.json()).toEqual({ result: "applied" });
  });

  it("checks Host but not Origin", async () => {
    const [l] = writeEvents(REL, finished.slice(0, 1));
    expect((await push({ file: REL, ...l }, { host: "webapp:8778" })).statusCode).toBe(403);
    expect((await push({ file: REL, ...l }, { origin: "http://elsewhere" })).statusCode).toBe(200);
  });

  it("accepts webapp:8778 when it's an allowed host (docker compose)", async () => {
    const other = await makeApp({ allowedHosts: ["127.0.0.1:8778", "localhost:8778", "webapp:8778"] });
    try {
      other.ctx.botToken = TOKEN;
      other.ctx.ingester = new Ingester(other.ctx.db, async () => [other.ctx.config.logRoots[0]!]);
      const file = path.join(other.ctx.config.logRoots[0]!, ...REL.split("/"));
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, line(finished[0]!, "20261005_100000", "tanner"));
      const res = await other.app.inject({
        method: "POST", url: "/api/ingest", headers: { host: "webapp:8778", authorization: `Bearer ${TOKEN}` },
        payload: { file: REL, offset: 0, line: line(finished[0]!, "20261005_100000", "tanner").trimEnd() },
      });
      expect(res.json()).toEqual({ result: "applied" });
    } finally {
      await other.close();
    }
  });

  it("refuses bad bodies and files that aren't session logs", async () => {
    const [l] = writeEvents(REL, finished.slice(0, 1));
    expect((await push({ file: REL, offset: -1, line: l!.line })).statusCode).toBe(400);
    expect((await push({ file: REL, offset: 0, line: `${l!.line}\n{}` })).statusCode).toBe(400);
    for (const file of ["tanner/log/nope.jsonl", "../tanner/log/x.jsonl", "log/launcher.jsonl",
      "tanner/tanner_20261005_100000.jsonl", "TANNER/log/tanner_20261005_100000.jsonl"]) {
      expect((await push({ file, ...l })).statusCode, file).toBe(404);
    }
    expect(await session()).toBeUndefined();
  });
});

describe("pushed lines", () => {
  it("offset == cursor: applied at once, cursor moved, the page told", async () => {
    const lines = writeEvents(REL, finished.slice(0, 3));
    for (const l of lines) expect((await push({ file: REL, ...l })).json()).toEqual({ result: "applied" });
    const s = (await session())!;
    expect(s).toMatchObject({ runs: 1, lastStep: "trade_ellis", final: null });
    expect(await stepRows(s.id)).toHaveLength(2);
    expect(await cursor()).toBe(fs.statSync(path.join(root, REL)).size);
    expect(fed).toEqual([[s.id], [s.id], [s.id]]);
  });

  it("offset < cursor: a duplicate, ignored", async () => {
    const lines = writeEvents(REL, finished.slice(0, 2));
    await t.ctx.ingester!.scanOnce();                                 // tailer got there first
    for (const l of lines) expect((await push({ file: REL, ...l })).json()).toEqual({ result: "duplicate" });
    expect(await stepRows((await session())!.id)).toHaveLength(1);
  });

  it("offset > cursor: lines were missed, the file is re-read", async () => {
    const lines = writeEvents(REL, finished.slice(0, 4));
    expect((await push({ file: REL, ...lines[3]! })).json()).toEqual({ result: "ahead" });
    await t.ctx.ingester!.stop();                                     // waits for the catch-up read
    const s = (await session())!;
    expect(await stepRows(s.id)).toHaveLength(3);
    expect(await cursor()).toBe(fs.statSync(path.join(root, REL)).size);
  });

  it("nothing counts twice, whichever way and order lines arrive", async () => {
    const lines = writeEvents(REL, finished);
    const ing = t.ctx.ingester!;
    // pushes and polls racing: some pushed early, some twice, the tailer in between
    const results = await Promise.all([
      push({ file: REL, ...lines[0]! }), push({ file: REL, ...lines[1]! }), ing.scanOnce(),
      push({ file: REL, ...lines[1]! }), push({ file: REL, ...lines[5]! }), push({ file: REL, ...lines[7]! }),
    ]);
    expect(results.length).toBe(6);
    for (const l of lines) await push({ file: REL, ...l });
    await ing.scanOnce();
    await ing.stop();

    const s = (await session())!;
    expect(s).toMatchObject({ final: "stopped", runs: 2, pauses: 1, activeSeconds: 150.1, pausedSeconds: 30 });
    expect((await stepRows(s.id)).map((r) => r.state)).toEqual(["walk_to_tanner", "trade_ellis", "recover", "banking"]);
    expect(await cursor()).toBe(fs.statSync(path.join(root, REL)).size);
  });

  it("a key spelled differently from the file on disk is refused", async () => {
    writeEvents(REL, finished.slice(0, 1));
    expect(await pushedLogFile([root], REL)).toMatchObject({ key: REL });
    expect(await pushedLogFile([root], "Tanner/log/tanner_20261005_100000.jsonl")).toBeNull();
    expect(await pushedLogFile([root], "tanner/log/../log/tanner_20261005_100000.jsonl")).toBeNull();
    expect(await pushedLogFile([], REL)).toBeNull();
  });
});

// ── live status ──────────────────────────────────────────────────────────────

const LIVE: Ev[] = [
  { ts: "2026-10-05T12:00:00.000", event: "session_start", params: {}, pid: 7 },
  { ts: "2026-10-05T12:00:00.100", event: "heartbeat", state: "starting", run: 0, paused: false },
  { ts: "2026-10-05T12:00:03.000", event: "state_enter", state: "walk_to_bank", run: 0 },
  { ts: "2026-10-05T12:00:10.000", event: "step", state: "walk_to_bank", result: "ok", seconds: 7, run: 0 },
  { ts: "2026-10-05T12:00:10.001", event: "state_enter", state: "banking", run: 0 },
];

describe("live status", () => {
  const pushAll = async (events: Ev[]) => {
    for (const l of writeEvents(REL, events)) expect((await push({ file: REL, ...l })).json()).toEqual({ result: "applied" });
  };

  it("tracks the state being run and how long it has been running", async () => {
    await pushAll(LIVE);
    expect(await session()).toMatchObject({
      currentState: "banking", stateSince: "2026-10-05 12:00:10.001", lastHeartbeat: "2026-10-05 12:00:00.1",
      pausedSince: null, lastStep: "walk_to_bank",
    });
    await pushAll([{ ts: "2026-10-05T12:00:40.001", event: "heartbeat", state: "banking", run: 0, paused: false }]);
    const o = await overview(t.ctx.db, undefined, "2026-10-05T12:00:41.000");
    expect(o.live).toHaveLength(1);
    const live = o.live[0]!;
    expect(live).toMatchObject({ status: "running", state: "banking", paused: false });
    expect(live.stateSeconds).toBeGreaterThanOrEqual(30);
    expect(live.stateSeconds).toBeLessThan(35);
    expect(live.activeSeconds).toBeGreaterThanOrEqual(40);
  });

  it("pause_start pauses; pause_end (or the runner's pause) resumes; the clock stops meanwhile", async () => {
    await pushAll([...LIVE, { ts: "2026-10-05T12:00:20.000", event: "pause_start", state: "banking" }]);
    expect(await session()).toMatchObject({ pausedSince: "2026-10-05 12:00:20" });
    await pushAll([{ ts: "2026-10-05T12:00:50.000", event: "heartbeat", state: "banking", run: 0, paused: true }]);
    let s = (await session())!;
    expect(s.activeSeconds).toBeCloseTo(20);                          // not 50: paused since 12:00:20
    let live = (await overview(t.ctx.db, undefined, "2026-10-05T12:00:51.000")).live[0]!;
    expect(live.paused).toBe(true);
    expect(live.activeSeconds).toBeCloseTo(20);                       // and it doesn't tick on

    await pushAll([{ ts: "2026-10-05T12:01:00.000", event: "pause_end", state: "banking" }]);
    s = (await session())!;
    expect(s.pausedSince).toBeNull();
    expect(s.activeSeconds).toBeCloseTo(60);   // a pause taken inside an action isn't logged with seconds

    await pushAll([
      { ts: "2026-10-05T12:01:10.000", event: "pause_start", state: "banking" },
      { ts: "2026-10-05T12:01:30.000", event: "pause", state: "banking", seconds: 20 },
    ]);
    s = (await session())!;
    expect(s).toMatchObject({ pausedSince: null, pausedSeconds: 20, pauses: 1 });
    expect(s.activeSeconds).toBeCloseTo(90 - 20);
  });

  it("session_end clears the state and the pause", async () => {
    await pushAll([...LIVE, { ts: "2026-10-05T12:00:20.000", event: "pause_start", state: "banking" },
      { ts: "2026-10-05T12:00:21.000", event: "force_stop", state: "banking" },
      { ts: "2026-10-05T12:00:21.100", event: "session_end", final: "stopped", reason: null, last_step: "banking",
        stats: { run: 0 }, active_seconds: 20, paused_seconds: 0 }]);
    expect(await session()).toMatchObject({ currentState: null, pausedSince: null, final: "stopped", activeSeconds: 20 });
    expect((await overview(t.ctx.db, undefined, "2026-10-05T12:01:00.000")).live).toEqual([]);
  });

  it("with heartbeats: gone 90 s after the last write; without: the 15-minute rule", async () => {
    await pushAll(LIVE);
    const legacy = "choc/log/choc_20261005_120000.jsonl";
    writeEvents(legacy, [LIVE[0]!, { ...LIVE[3]!, state: "grind" }], "20261005_120000", "choc");
    await t.ctx.ingester!.scanOnce();
    const live = async () => (await overview(t.ctx.db, undefined, "2026-10-05T12:05:00.000")).live.map((s) => s.bot).sort();
    expect(await live()).toEqual(["choc", "tanner"]);

    await t.ctx.db.update(sessions).set({ fileMtime: new Date(Date.now() - 80_000) });
    expect(await live()).toEqual(["choc", "tanner"]);
    await t.ctx.db.update(sessions).set({ fileMtime: new Date(Date.now() - 100_000) });
    expect(await live()).toEqual(["choc"]);                           // killed: no heartbeat for 100 s
    const [legacyRow] = (await overview(t.ctx.db, undefined, "2026-10-05T12:05:00.000")).live;
    expect(legacyRow).toMatchObject({ state: null, stateSeconds: null, paused: false, lastStep: "grind" });
  });

  it("is linked to the account the session started on: live on that account's page only", async () => {
    await pushAll([{ ...LIVE[0]!, account: "Zezima" }, ...LIVE.slice(1),
      { ts: "2026-10-05T12:00:20.000", event: "pause_start", state: "banking" }]);
    expect(await session()).toMatchObject({ account: "Zezima" });
    const zezima = await overview(t.ctx.db, "Zezima", "2026-10-05T12:01:00.000");
    expect(zezima.live).toHaveLength(1);
    expect(zezima.live[0]).toMatchObject({ account: "Zezima", state: "banking", paused: true });
    expect(zezima.today.hours).toBeGreaterThan(0);
    expect((await overview(t.ctx.db, "Lynx Titan", "2026-10-05T12:01:00.000")).live).toEqual([]);
    expect((await overview(t.ctx.db, "", "2026-10-05T12:01:00.000")).live).toEqual([]);   // not Unassigned
  });

  it("today's hours include the running sessions' time since their last event", async () => {
    await pushAll(LIVE);
    await t.ctx.db.update(sessions).set({ fileMtime: new Date(Date.now() - 60_000) });
    const o = await overview(t.ctx.db, undefined, "2026-10-05T12:05:00.000");
    expect(o.today.hours * 3600).toBeCloseTo(10.001 + 60, 0);
    expect(o.today.bots.tanner! * 3600).toBeCloseTo(10.001 + 60, 0);
    expect(o.live[0]!.activeSeconds).toBeCloseTo(10.001 + 60, 0);
  });
});

describe("bot token", () => {
  it("is created once and kept across restarts; a bad one is replaced", async () => {
    const dir = tmpDir();
    const a = await ensureBotToken(dir);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
    expect(fs.readFileSync(path.join(dir, "bot_token"), "utf8")).toBe(`${a}\n`);
    expect(await ensureBotToken(dir)).toBe(a);
    fs.writeFileSync(path.join(dir, "bot_token"), "short\n");
    const b = await ensureBotToken(dir);
    expect(b).not.toBe(a);
    expect(b).toMatch(/^[0-9a-f]{64}$/);
  });
});
