import fs from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Ingester } from "../src/ingest/ingester.js";
import { login, makeApp, type Client, type TestApp } from "./helpers.js";
import { crashed, finished, writeLog } from "./logs.js";

let t: TestApp;
let c: Client;
const activeFile = () => path.join(t.ctx.config.dataDir, "active_account");
const readActive = () => (fs.existsSync(activeFile()) ? fs.readFileSync(activeFile(), "utf8") : null);
const list = async () => (await c.get("/api/accounts")).json();

beforeEach(async () => {
  t = await makeApp();
  c = await login(t.app);
});
afterEach(async () => { await t.close(); });

describe("accounts", () => {
  it("the first account becomes active and is written for the bots", async () => {
    expect(readActive()).toBeNull();
    const res = await c.post("/api/accounts", { name: "Zezima", notes: "main" });
    expect(res.statusCode).toBe(200);
    await c.post("/api/accounts", { name: "Lynx Titan" });
    const l = await list();
    expect(l.accounts).toEqual([
      { id: 2, name: "Lynx Titan", notes: "", active: false, hasLogin: false },
      { id: 1, name: "Zezima", notes: "main", active: true, hasLogin: false },
    ]);
    expect(readActive()).toBe("Zezima\n");
  });

  it("switching the active account rewrites the file; deactivate removes it", async () => {
    await c.post("/api/accounts", { name: "Zezima" });
    await c.post("/api/accounts", { name: "Lynx Titan" });
    await c.post("/api/accounts/2/activate");
    expect(readActive()).toBe("Lynx Titan\n");
    expect((await list()).accounts.filter((a: { active: boolean }) => a.active).map((a: { name: string }) => a.name)).toEqual(["Lynx Titan"]);
    await c.post("/api/accounts/deactivate");
    expect(readActive()).toBeNull();
    expect((await c.post("/api/accounts/99/activate")).statusCode).toBe(404);
  });

  it("refuses duplicate and empty names", async () => {
    await c.post("/api/accounts", { name: "Zezima" });
    expect((await c.post("/api/accounts", { name: "Zezima" })).statusCode).toBe(409);
    expect((await c.post("/api/accounts", { name: "  " })).statusCode).toBe(400);
    expect((await c.post("/api/accounts", { name: "x".repeat(33) })).statusCode).toBe(400);
  });

  it("a rename carries the session history and the active file along", async () => {
    writeLog(t.ctx.config.logRoots[0]!, "tanner/log/tanner_20261005_100000.jsonl", finished);   // account Zezima
    writeLog(t.ctx.config.logRoots[0]!, "tanner/log/tanner_20261005_110000.jsonl", crashed);    // none
    await new Ingester(t.ctx.db, async () => t.ctx.config.logRoots).scanOnce();
    await c.post("/api/accounts", { name: "Zezima", notes: "main" });
    const res = await c.send("PATCH", "/api/accounts/1", { name: "Zezima2" });
    expect(res.statusCode).toBe(200);
    expect(readActive()).toBe("Zezima2\n");
    const sessions = (await c.get("/api/sessions?account=Zezima2")).json();
    expect(sessions.total).toBe(1);
    const l = await list();
    expect(l.accounts[0]).toMatchObject({ name: "Zezima2", notes: "main" });    // notes untouched
    expect(l.orphanNames).toEqual([]);
    expect(l.hasUnassigned).toBe(true);
  });

  it("deleting keeps the sessions under the old name", async () => {
    writeLog(t.ctx.config.logRoots[0]!, "tanner/log/tanner_20261005_100000.jsonl", finished);
    await new Ingester(t.ctx.db, async () => t.ctx.config.logRoots).scanOnce();
    await c.post("/api/accounts", { name: "Zezima" });
    expect((await c.send("DELETE", "/api/accounts/1")).statusCode).toBe(200);
    expect(readActive()).toBeNull();
    const l = await list();
    expect(l.accounts).toEqual([]);
    expect(l.orphanNames).toEqual(["Zezima"]);
  });

  it("nothing changes when data/active_account can't be written", async () => {
    // a file where the data directory should be: mkdir fails
    const bad = path.join(t.ctx.config.logRoots[0]!, "not-a-dir");
    fs.writeFileSync(bad, "x");
    t.ctx.config.dataDir = bad;
    const res = await c.post("/api/accounts", { name: "Zezima" });
    expect(res.statusCode).toBe(500);
    expect(res.json().error).toContain("active_account");
    expect((await list()).accounts).toEqual([]);
  });

  it("announces changes on the live feed", async () => {
    const seen: unknown[] = [];
    t.ctx.bus.on((e) => seen.push(e));
    await c.post("/api/accounts", { name: "Zezima" });
    expect(seen).toContainEqual({ type: "accounts" });
  });

  it("reports RUNETOOLS_ACCOUNT as an override", async () => {
    t.ctx.config.envAccount = "Bot1";
    expect((await list()).envOverride).toBe("Bot1");
  });
});

describe("settings", () => {
  it("watched log directories default to the config and must exist", async () => {
    const s = (await c.get("/api/settings")).json();
    expect(s.logRoots).toEqual(t.ctx.config.logRoots);
    expect(s.defaultLogRoots).toEqual(t.ctx.config.logRoots);
    const extra = path.join(t.ctx.config.logRoots[0]!, "more");
    expect((await c.send("PUT", "/api/settings", { logRoots: [extra] })).statusCode).toBe(400);
    fs.mkdirSync(extra);
    const res = await c.send("PUT", "/api/settings", { logRoots: [t.ctx.config.logRoots[0], extra] });
    expect(res.statusCode).toBe(200);
    expect(res.json().logRoots).toEqual([path.resolve(t.ctx.config.logRoots[0]!), path.resolve(extra)]);
    expect((await c.send("PUT", "/api/settings", { logRoots: [] })).statusCode).toBe(400);
  });
});
