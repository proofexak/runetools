import fs from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { asc, eq } from "drizzle-orm";
import { scheduleBlocks, sessions } from "../src/db/schema.js";
import { HORIZON_DAYS, refill, saveProfile } from "../src/schedule/store.js";
import { addDays, weekday, zonedDate, zonedEpoch } from "../src/schedule/zone.js";
import { login, makeApp, type Client, type TestApp } from "./helpers.js";

let t: TestApp;
let c: Client;
const now = () => Math.floor(Date.now() / 1000);
const fileOf = (name: string) => path.join(t.ctx.config.dataDir, "schedules", `${name}.json`);
const readFile = (name: string) => JSON.parse(fs.readFileSync(fileOf(name), "utf8"));
const profile = (over: Record<string, unknown> = {}) => ({
  enabled: true, timezone: "Europe/Warsaw", monthlyHours: 200, rampStart: null,
  activities: [{ bot: "Tanning", launch: "Green Dragonhide", value: "Al Kharid", weight: 1 }], ...over,
});
const view = async (id = 1) => (await c.get(`/api/accounts/${id}/schedule?from=${now() - 86400}&to=${now() + 15 * 86400}`)).json();

beforeEach(async () => {
  t = await makeApp();
  c = await login(t.app);
  await c.post("/api/accounts", { name: "alt1" });
});
afterEach(async () => { await t.close(); });

describe("schedule", () => {
  it("profile defaults then save fills the next 14 days", async () => {
    const empty = await view();
    expect(empty.profile).toEqual({ enabled: false, timezone: "Europe/Warsaw", monthlyHours: 200, activities: [],
      rampStart: null, seed: 0 });
    expect(empty.blocks).toEqual([]);

    expect((await c.send("PUT", "/api/accounts/1/schedule", profile())).statusCode).toBe(200);
    const { blocks } = await view();
    expect(blocks.length).toBeGreaterThan(10);
    expect(blocks.every((b: { start: number }) => b.start >= now() - 5 && b.start < now() + HORIZON_DAYS * 86400)).toBe(true);
    const hours = blocks.reduce((s: number, b: { start: number; end: number }) => s + b.end - b.start, 0) / 3600;
    expect(hours).toBeGreaterThan(50);
    expect(blocks[0]).toMatchObject({ bot: "Tanning", launch: "Green Dragonhide", value: "Al Kharid", edited: false });
  });

  it("writes the schedule file for the bot", async () => {
    await c.send("PUT", "/api/accounts/1/schedule", profile());
    const file = readFile("alt1");
    const { blocks } = await view();
    expect(file).toMatchObject({ account: "alt1", enabled: true, timezone: "Europe/Warsaw" });
    expect(file.blocks.map((b: { id: number }) => b.id)).toEqual(blocks.map((b: { id: number }) => b.id));
    expect(Object.keys(file.blocks[0]).sort()).toEqual(["bot", "end", "id", "launch", "start", "value"]);
    for (let i = 1; i < file.blocks.length; i++) expect(file.blocks[i - 1].end).toBeLessThanOrEqual(file.blocks[i].start);
  });

  it("disable keeps history, drops the future", async () => {
    await c.send("PUT", "/api/accounts/1/schedule", profile());
    await t.ctx.db.insert(scheduleBlocks).values({ accountId: 1, startAt: new Date((now() - 7200) * 1000),
      endAt: new Date((now() - 3600) * 1000), bot: "Tanning", launch: "Green Dragonhide", value: null });
    await c.send("PUT", "/api/accounts/1/schedule", profile({ enabled: false }));
    const { blocks } = await view();
    expect(blocks.length).toBe(1);
    expect(blocks[0].end).toBeLessThanOrEqual(now());
    expect(readFile("alt1").enabled).toBe(false);
  });

  it("regenerate changes the plan but keeps edited blocks", async () => {
    await c.send("PUT", "/api/accounts/1/schedule", profile());
    const before = (await view()).blocks;
    const pick = before[3];
    const moved = { start: pick.start + 600, end: pick.end + 600 };
    const next = before[4];
    if (moved.end > next.start) moved.end = next.start - 60;      // stay clear of the next one
    expect((await c.send("PATCH", `/api/schedule/blocks/${pick.id}`, moved)).statusCode).toBe(200);
    expect((await c.post("/api/accounts/1/schedule/regenerate")).statusCode).toBe(200);
    const after = (await view()).blocks;
    expect(after.find((b: { id: number }) => b.id === pick.id)).toMatchObject({ ...moved, edited: true });
    expect(after.map((b: { start: number }) => b.start).join()).not.toBe(before.map((b: { start: number }) => b.start).join());
    for (let i = 1; i < after.length; i++) expect(after[i - 1].end).toBeLessThanOrEqual(after[i].start);
    expect((await view()).profile.seed).toBe(1);
  });

  it("patch rejects overlaps and empty blocks", async () => {
    await c.send("PUT", "/api/accounts/1/schedule", profile());
    const [a, b] = (await view()).blocks;
    expect((await c.send("PATCH", `/api/schedule/blocks/${a.id}`, { end: a.start })).statusCode).toBe(400);
    expect((await c.send("PATCH", `/api/schedule/blocks/${a.id}`, { end: b.start + 60 })).statusCode).toBe(409);
    expect((await c.send("PATCH", "/api/schedule/blocks/99999", { end: a.end })).statusCode).toBe(404);
    expect((await c.send("DELETE", `/api/schedule/blocks/${a.id}`)).statusCode).toBe(200);
    expect((await view()).blocks.some((x: { id: number }) => x.id === a.id)).toBe(false);
    expect(readFile("alt1").blocks.some((x: { id: number }) => x.id === a.id)).toBe(false);
  });

  it("actual sessions come back as epoch seconds", async () => {
    const day = new Date(Date.now() - 86400_000 / 2);
    const p = (n: number) => String(n).padStart(2, "0");
    const stamp = `${day.getFullYear()}-${p(day.getMonth() + 1)}-${p(day.getDate())}`;
    await t.ctx.db.insert(sessions).values({ file: "/x/tanner_1.jsonl", bot: "Tanning", account: "alt1",
      startedAt: `${stamp}T00:00:00.000`, lastEventAt: `${stamp}T01:30:00.000`, endedAt: `${stamp}T01:30:00.000`,
      final: "stopped", hasStart: true });
    const res = (await c.get(`/api/accounts/1/schedule?from=${now() - 3 * 86400}&to=${now() + 86400}`)).json();
    expect(res.actual).toHaveLength(1);
    expect(res.actual[0]).toMatchObject({ bot: "Tanning", status: "stopped",
      start: new Date(`${stamp}T00:00:00.000`).getTime() / 1000 });
    expect(res.actual[0].end - res.actual[0].start).toBe(5400);
  });

  it("rename moves the schedule file; delete removes it", async () => {
    await c.send("PUT", "/api/accounts/1/schedule", profile());
    await c.send("PATCH", "/api/accounts/1", { name: "alt9" });
    expect(fs.existsSync(fileOf("alt1"))).toBe(false);
    expect(readFile("alt9").account).toBe("alt9");
    await c.send("DELETE", "/api/accounts/1");
    expect(fs.existsSync(fileOf("alt9"))).toBe(false);
  });

  it("bad timezone or account is refused", async () => {
    expect((await c.send("PUT", "/api/accounts/1/schedule", profile({ timezone: "Mars/Olympus" }))).statusCode).toBe(400);
    expect((await c.send("PUT", "/api/accounts/7/schedule", profile())).statusCode).toBe(404);
    expect((await c.get("/api/accounts/7/schedule")).statusCode).toBe(404);
  });

  it("an account name that can't be a file name is refused", async () => {
    await c.post("/api/accounts", { name: "a/b" });
    const res = await c.send("PUT", "/api/accounts/2/schedule", profile());
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toMatch(/file name/);
  });

  it("refillAll keeps every enabled account 14 days ahead", async () => {
    const { refillAll } = await import("../src/schedule/store.js");
    await c.send("PUT", "/api/accounts/1/schedule", profile());
    fs.rmSync(fileOf("alt1"));
    await refillAll(t.ctx.db, t.ctx.config.dataDir);
    expect(readFile("alt1").blocks.length).toBeGreaterThan(10);
  });
});

describe("schedule — review fixes", () => {
  const TZ = "Europe/Warsaw";
  const W = zonedEpoch(TZ, "2027-01-13", 15 * 3600);          // a Wednesday afternoon
  const rows = async () => (await t.ctx.db.select().from(scheduleBlocks).where(eq(scheduleBlocks.accountId, 1))
    .orderBy(asc(scheduleBlocks.startAt))).map((r) => ({ id: r.id, start: r.startAt.getTime() / 1000, end: r.endAt.getTime() / 1000 }));

  it("a deleted block stays deleted after the hourly refill", async () => {
    await saveProfile(t.ctx.db, 1, profile());
    await refill(t.ctx.db, 1, { replace: true, now: W });
    const before = await rows();
    const last = before.at(-1)!;
    await t.ctx.db.delete(scheduleBlocks).where(eq(scheduleBlocks.id, last.id));
    await refill(t.ctx.db, 1, { now: W + 3600 });             // the next hourly run
    const after = await rows();
    expect(after.some((b) => b.start === last.start)).toBe(false);
    await refill(t.ctx.db, 1, { now: W + 86400 });            // a day later: only the new day is added
    const later = await rows();
    const added = later.filter((b) => !after.some((a) => a.id === b.id));
    expect(added.length).toBeGreaterThan(0);
    expect(added.every((b) => b.start >= W + HORIZON_DAYS * 86400)).toBe(true);
  });

  it("regenerate mid-day keeps today and the generator's rules", async () => {
    await saveProfile(t.ctx.db, 1, profile());
    await refill(t.ctx.db, 1, { replace: true, now: W });
    const tomorrow = zonedEpoch(TZ, "2027-01-14", 0);
    const today = (await rows()).filter((b) => b.start < tomorrow);
    await saveProfile(t.ctx.db, 1, { ...profile(), seed: 1 });
    await refill(t.ctx.db, 1, { replace: true, now: W });
    const all = await rows();
    expect(all.filter((b) => b.start < tomorrow)).toEqual(today);
    for (let i = 1; i < all.length; i++) expect(all[i - 1]!.end).toBeLessThanOrEqual(all[i]!.start);
    const perDay = new Map<string, number>();
    for (const b of all) perDay.set(zonedDate(TZ, b.start), (perDay.get(zonedDate(TZ, b.start)) ?? 0) + b.end - b.start);
    expect(Math.max(...perDay.values())).toBeLessThanOrEqual(11 * 3600);
    for (let monday = "2027-01-18"; monday <= "2027-01-25"; monday = addDays(monday, 7)) {
      const week = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
      expect(weekday(monday)).toBe(0);
      expect(week.some((d) => !perDay.has(d))).toBe(true);
    }
  });

  it("a rename doesn't change the plan", async () => {
    await saveProfile(t.ctx.db, 1, profile());
    await refill(t.ctx.db, 1, { replace: true, now: W });
    const before = (await rows()).map((b) => b.start);
    await c.send("PATCH", "/api/accounts/1", { name: "alt9" });
    await t.ctx.db.delete(scheduleBlocks).where(eq(scheduleBlocks.accountId, 1));
    await refill(t.ctx.db, 1, { replace: true, now: W });
    expect((await rows()).map((b) => b.start)).toEqual(before);
  });
});
