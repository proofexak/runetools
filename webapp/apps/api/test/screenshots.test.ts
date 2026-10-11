/** Failure screenshots (PRO-91): ingested from step / error events, listed on the session, served safely. */
import fs from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Ingester } from "../src/ingest/ingester.js";
import { setLogRoots } from "../src/settings.js";
import { HOST, login, makeApp, tmpDir, type Client, type TestApp } from "./helpers.js";
import { writeLog, type Ev } from "./logs.js";

const PNG = Buffer.from("89504e470d0a1a0a0000000d4948445200000001000000010806000000", "hex");
const STEP_SHOT = "tanner_20261005_100000_1_trade_ellis.png";
const ERROR_SHOT = "tanner_20261005_100000_2_recover.png";

const withShots: Ev[] = [
  { ts: "2026-10-05T10:00:00.000", event: "session_start", params: {}, pid: 42 },
  { ts: "2026-10-05T10:00:20.000", event: "step", state: "walk_to_tanner", result: "ok", seconds: 15, run: 1 },
  { ts: "2026-10-05T10:00:40.000", event: "step", state: "trade_ellis", result: "fail", seconds: 20, run: 1, screenshot: STEP_SHOT },
  { ts: "2026-10-05T10:00:41.000", event: "error", where: "session", state: "recover", type: "RuntimeError",
    message: "boom", traceback: "tb", screenshot: ERROR_SHOT },
  { ts: "2026-10-05T10:00:41.500", event: "session_end", final: "crashed", reason: null, last_step: "recover",
    stats: { run: 1 }, active_seconds: 41.5, paused_seconds: 0 },
];

let t: TestApp;
let c: Client;
let root: string;

beforeEach(async () => {
  t = await makeApp();
  root = t.ctx.config.logRoots[0]!;
  c = await login(t.app);
});
afterEach(async () => { await t.close(); });

async function ingest(roots = [root]) {
  await new Ingester(t.ctx.db, async () => roots).scanOnce();
}

/** Writes the log + its PNGs under `base`, ingests, returns the session id. */
async function session(base = root, roots = [root]): Promise<number> {
  const log = writeLog(base, "tanner/log/tanner_20261005_100000.jsonl", withShots);
  fs.writeFileSync(path.join(path.dirname(log), STEP_SHOT), PNG);
  fs.writeFileSync(path.join(path.dirname(log), ERROR_SHOT), PNG);
  await ingest(roots);
  const list = (await c.get("/api/sessions")).json();
  return list.sessions[0].id as number;
}

const url = (id: number, file: string) => `/api/sessions/${id}/screenshots/${file}`;

describe("screenshots on the session", () => {
  it("are stored with their step / error and listed oldest first", async () => {
    const id = await session();
    const d = (await c.get(`/api/sessions/${id}`)).json();
    expect(d.steps.map((s: { screenshot: string | null }) => s.screenshot)).toEqual([null, STEP_SHOT]);
    expect(d.errorList[0].screenshot).toBe(ERROR_SHOT);
    expect(d.screenshots).toEqual([
      { ts: "2026-10-05T10:00:40", state: "trade_ellis", label: "fail", kind: "step", file: STEP_SHOT },
      { ts: "2026-10-05T10:00:41", state: "recover", label: "RuntimeError", kind: "error", file: ERROR_SHOT },
    ]);
  });

  it("a session without any has an empty list", async () => {
    writeLog(root, "tanner/log/tanner_20261005_110000.jsonl", withShots.map(({ screenshot: _s, ...e }) => e as Ev));
    await ingest();
    const id = (await c.get("/api/sessions")).json().sessions[0].id;
    expect((await c.get(`/api/sessions/${id}`)).json().screenshots).toEqual([]);
  });
});

describe("GET /api/sessions/:id/screenshots/:file", () => {
  it("serves a recorded PNG from the log's folder", async () => {
    const id = await session();
    for (const file of [STEP_SHOT, ERROR_SHOT]) {
      const res = await c.get(url(id, file));
      expect(res.statusCode).toBe(200);
      expect(res.headers["content-type"]).toBe("image/png");
      expect(res.rawPayload.equals(PNG)).toBe(true);
      // a screenshot never changes: the browser keeps it (other /api replies stay no-store)
      expect(res.headers["cache-control"]).toBe("private, max-age=604800, immutable");
    }
    expect((await c.get(`/api/sessions/${id}`)).headers["cache-control"]).toBe("no-store");
    expect((await c.get(url(id, "nope.png"))).headers["cache-control"]).toBe("no-store");
  });

  it("refuses a symlink in the log folder that points outside it", async (ctx) => {
    const id = await session();
    const outside = path.join(tmpDir(), "secret.png");
    fs.writeFileSync(outside, PNG);
    const link = path.join(root, "tanner", "log", STEP_SHOT);
    fs.rmSync(link);
    try {
      fs.symlinkSync(outside, link);
    } catch {
      ctx.skip();   // Windows without the symlink privilege
    }
    expect((await c.get(url(id, STEP_SHOT))).statusCode).toBe(404);
  });

  it("needs the app login", async () => {
    const id = await session();
    const res = await t.app.inject({ url: url(id, STEP_SHOT), headers: { host: HOST } });
    expect(res.statusCode).toBe(401);
  });

  it("refuses a PNG next to the log that the session didn't record", async () => {
    const id = await session();
    fs.writeFileSync(path.join(root, "tanner", "log", "other.png"), PNG);
    expect((await c.get(url(id, "other.png"))).statusCode).toBe(404);
  });

  it("refuses names that leave the folder or aren't PNGs", async () => {
    const id = await session();
    fs.writeFileSync(path.join(root, "tanner", "secret.png"), PNG);
    for (const name of ["..%2Fsecret.png", "%2E%2E%2Fsecret.png", "..%5Csecret.png", "..", "x.jsonl",
      "tanner_20261005_100000.jsonl", "%00.png"]) {
      expect((await c.get(url(id, name))).statusCode, name).toBe(404);
    }
  });

  it("404s a missing file, another session's screenshot and an unknown session", async () => {
    const id = await session();
    fs.rmSync(path.join(root, "tanner", "log", STEP_SHOT));
    expect((await c.get(url(id, STEP_SHOT))).statusCode).toBe(404);

    writeLog(root, "choc/log/choc_20261005_120000.jsonl", [
      { ts: "2026-10-05T12:00:00.000", event: "session_start", params: {} }]);
    await ingest();
    const choc = (await c.get("/api/sessions?bot=choc")).json().sessions[0].id;
    expect((await c.get(url(choc, ERROR_SHOT))).statusCode).toBe(404);
    expect((await c.get(url(999, ERROR_SHOT))).statusCode).toBe(404);
  });

  it("404s once the log is no longer under a log root", async () => {
    const id = await session();
    await setLogRoots(t.ctx.db, [tmpDir()]);
    expect((await c.get(url(id, STEP_SHOT))).statusCode).toBe(404);
  });

  it("serves a session from a second log root (keyed by absolute path)", async () => {
    const second = tmpDir();
    await setLogRoots(t.ctx.db, [root, second]);
    const id = await session(second, [root, second]);
    const d = (await c.get(`/api/sessions/${id}`)).json();
    expect(path.isAbsolute(d.file)).toBe(true);
    expect((await c.get(url(id, STEP_SHOT))).statusCode).toBe(200);
  });
});
