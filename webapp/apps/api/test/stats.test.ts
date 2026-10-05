import fs from "node:fs";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Ingester } from "../src/ingest/ingester.js";
import { botStats, overview } from "../src/stats.js";
import { HOST, login, makeApp, type Client, type TestApp } from "./helpers.js";
import { crashed, finished, open, writeLog } from "./logs.js";

let t: TestApp;
let c: Client;
let root: string;

beforeEach(async () => {
  t = await makeApp();
  root = t.ctx.config.logRoots[0]!;
  c = await login(t.app);
});
afterEach(async () => { await t.close(); });

async function ingest(opts: { staleOpen?: boolean } = {}) {
  writeLog(root, "tanner/log/tanner_20261005_100000.jsonl", finished);
  writeLog(root, "tanner/log/tanner_20261005_110000.jsonl", crashed);
  const f = writeLog(root, "miner/golden_nuggets/log/golden_nuggets_20261005_120000.jsonl", open);
  if (opts.staleOpen) {
    const old = new Date(Date.now() - 3600_000);
    fs.utimesSync(f, old, old);
  }
  await new Ingester(t.ctx.db, async () => [root]).scanOnce();
}

describe("overview", () => {
  it("adds up today, the week and the 14-day series", async () => {
    await ingest();
    const o = await overview(t.ctx.db, undefined, "2026-10-05T18:00:00.000");
    expect(o.daily).toHaveLength(14);
    expect(o.daily.at(-1)!.date).toBe("2026-10-05");
    expect(o.daily[0]!.date).toBe("2026-09-22");
    const hours = (150.1 + 11.5 + 240) / 3600;
    expect(o.today.hours).toBeCloseTo(hours);
    expect(o.today.runs).toBe(2 + 1 + 3);
    expect(o.today.sessions).toBe(3);
    expect(o.today.bots.tanner).toBeCloseTo((150.1 + 11.5) / 3600);
    expect(o.week).toMatchObject({ runs: 6, crashes: 1 });
    expect(o.totalHours).toBeCloseTo(hours);
    expect(o.recent.map((s) => s.bot)).toEqual(["golden_nuggets", "tanner", "tanner"]);
  });

  it("an open session with a fresh log is live; a stale one was killed", async () => {
    await ingest();
    let o = await overview(t.ctx.db, undefined, "2026-10-05T18:00:00.000");
    expect(o.live).toHaveLength(1);
    expect(o.live[0]).toMatchObject({ bot: "golden_nuggets", status: "running", lastStep: "drop", runs: 3 });
    expect(o.live[0]!.idleSeconds).toBeLessThan(60);

    await t.ctx.db.execute("UPDATE sessions SET file_mtime = now() - interval '1 hour'");
    o = await overview(t.ctx.db, undefined, "2026-10-05T18:00:00.000");
    expect(o.live).toEqual([]);
    expect(o.recent[0]!.status).toBe("killed");
  });

  it("filters by account; '' means sessions without one", async () => {
    await ingest();
    const z = await overview(t.ctx.db, "Zezima", "2026-10-05T18:00:00.000");
    expect(z.recent.map((s) => s.stamp).sort()).toEqual(["20261005_100000", "20261005_120000"]);
    const none = await overview(t.ctx.db, "", "2026-10-05T18:00:00.000");
    expect(none.recent.map((s) => s.stamp)).toEqual(["20261005_110000"]);
    expect(none.week.crashes).toBe(1);
  });

  it("is served at /api/overview", async () => {
    await ingest();
    const res = await c.get("/api/overview?account=Zezima");
    expect(res.statusCode).toBe(200);
    expect(res.json().recent).toHaveLength(2);
    expect((await t.app.inject({ url: "/api/overview", headers: { host: HOST } })).statusCode).toBe(401);
  });
});

describe("sessions", () => {
  it("lists newest first with filters and paging", async () => {
    await ingest({ staleOpen: true });
    let r = (await c.get("/api/sessions")).json();
    expect(r.total).toBe(3);
    expect(r.bots).toEqual(["golden_nuggets", "tanner"]);
    expect(r.sessions.map((s: { status: string }) => s.status)).toEqual(["killed", "crashed", "stopped"]);
    expect(r.sessions[0].startedAt).toBe("2026-10-05T12:00:00");

    r = (await c.get("/api/sessions?bot=tanner&limit=1&offset=1")).json();
    expect(r.total).toBe(2);
    expect(r.sessions.map((s: { stamp: string }) => s.stamp)).toEqual(["20261005_100000"]);
    expect(r.sessions[0].reason).toBe("stop button");

    r = (await c.get("/api/sessions?status=crashed")).json();
    expect(r.sessions.map((s: { stamp: string }) => s.stamp)).toEqual(["20261005_110000"]);
    expect(r.sessions[0].reason).toBe("after trade_ellis");          // logreport's fallback

    r = (await c.get("/api/sessions?from=2026-10-06")).json();
    expect(r.total).toBe(0);
    expect((await c.get("/api/sessions?from=yesterday")).statusCode).toBe(400);
  });

  it("returns one session with steps, time per state and errors", async () => {
    await ingest();
    const list = (await c.get("/api/sessions?bot=tanner")).json();
    const id = list.sessions.find((s: { stamp: string }) => s.stamp === "20261005_100000").id;
    const d = (await c.get(`/api/sessions/${id}`)).json();
    expect(d).toMatchObject({ file: "tanner/log/tanner_20261005_100000.jsonl", params: { hide_type: "green" }, pauses: 1 });
    expect(d.steps).toHaveLength(4);
    expect(d.steps[0]).toEqual({ ts: "2026-10-05T10:00:20", state: "walk_to_tanner", result: "ok", seconds: 15, run: 1 });
    expect(d.stateTime.map((x: { state: string }) => x.state)).toEqual(["recover", "trade_ellis", "walk_to_tanner", "banking"]);
    expect(d.stateTime[1]).toEqual({ state: "trade_ellis", seconds: 20, count: 1, failures: 1 });

    const crashId = list.sessions.find((s: { stamp: string }) => s.stamp === "20261005_110000").id;
    const e = (await c.get(`/api/sessions/${crashId}`)).json();
    expect(e.errorList[0]).toMatchObject({ type: "ValueError", ts: "2026-10-05T11:00:11" });

    expect((await c.get("/api/sessions/999")).statusCode).toBe(404);
  });
});

describe("bot stats (logreport.aggregate)", () => {
  it("totals, failure rates per state, recoveries and crash types", async () => {
    await ingest({ staleOpen: true });
    const [nuggets, tanner] = await botStats(t.ctx.db, undefined, undefined);
    expect(nuggets).toMatchObject({ bot: "golden_nuggets", sessions: 1, runs: 3, finals: { killed: 1 } });
    expect(tanner).toMatchObject({
      bot: "tanner", sessions: 2, runs: 3, finals: { stopped: 1, crashed: 1 },
      reasons: [{ reason: "stop button", count: 1 }],
      failuresByState: [{ state: "trade_ellis", failures: 1, steps: 1, rate: 1 }],
      crashTypes: [{ type: "ValueError", count: 1 }],
    });
    const hours = (150.1 + 11.5) / 3600;
    expect(tanner!.activeHours).toBeCloseTo(hours);
    expect(tanner!.runsPerHour).toBeCloseTo(3 / hours);
    expect(tanner!.recoveriesPerHour).toBeCloseTo(1 / hours);

    const r = (await c.get("/api/bots/stats?since=2026-10-06")).json();
    expect(r.bots).toEqual([]);
  });
});

describe("SSE feed", () => {
  it("streams bus events to a logged-in browser", async () => {
    await t.app.listen({ port: 0, host: "127.0.0.1" });
    const { port } = t.app.server.address() as AddressInfo;
    // the Host check wants the configured host; send that, connect to the real port
    const got = await new Promise<string>((resolve, reject) => {
      const req = http.get({ host: "127.0.0.1", port, path: "/api/events",
        headers: { host: HOST, cookie: `rt_session=${c.cookie}` } }, (res) => {
        expect(res.headers["content-type"]).toContain("text/event-stream");
        let buf = "";
        res.on("data", (d) => {
          buf += d;
          if (buf.includes("retry:")) t.ctx.bus.emit({ type: "accounts" });
          if (buf.includes("data:")) { req.destroy(); resolve(buf); }
        });
      });
      req.on("error", reject);
    });
    expect(got).toContain('data: {"type":"accounts"}');
  });

  it("needs a login", async () => {
    const res = await t.app.inject({ url: "/api/events", headers: { host: HOST } });
    expect(res.statusCode).toBe(401);
  });
});
