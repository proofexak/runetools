/**
 * Play schedules (PRO-102): an account's profile, its blocks (kept HORIZON_DAYS ahead), and
 * data/schedules/<account>.json — what schedule mode in the bot container follows
 * (lib/schedule.py reads it; same hand-over as data/active_account). Block times are
 * timestamptz here and epoch seconds everywhere else.
 */
import fs from "node:fs/promises";
import path from "node:path";
import type {
  ActualSession, ScheduleBlock, ScheduleProfile, ScheduleProfileBody, ScheduleResponse,
} from "@runetools/shared";
import { and, asc, eq, gt, isNotNull, lt, ne, sql } from "drizzle-orm";
import { writeDataFile } from "../accounts.js";
import type { Db } from "../db/index.js";
import { accounts, scheduleBlocks, scheduleProfiles, sessions } from "../db/schema.js";
import { HttpError } from "../http.js";
import { iso, localIso } from "../time.js";
import { generateRange } from "./generate.js";

export const HORIZON_DAYS = 14;
export const DEFAULT_PROFILE: ScheduleProfile = {
  enabled: false, timezone: "Europe/Warsaw", monthlyHours: 200, activities: [], rampStart: null, seed: 0,
};

const DAY = 86_400;
const toDate = (epoch: number) => new Date(epoch * 1000);
const toEpoch = (d: Date) => Math.floor(d.getTime() / 1000);
const nowEpoch = () => Math.floor(Date.now() / 1000);

export function validTimezone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat("en", { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

/** The account name doubles as the file name the bot looks for: it must be a plain one. */
export function fileSafe(name: string): boolean {
  return name !== "." && name !== ".." && !/[\\/:*?"<>|\x00-\x1f]/.test(name);
}

async function accountName(db: Db, id: number): Promise<string> {
  const [row] = await db.select({ name: accounts.name }).from(accounts).where(eq(accounts.id, id));
  if (!row) throw new HttpError(404, "no such account");
  return row.name;
}

export async function getProfile(db: Db, accountId: number): Promise<ScheduleProfile> {
  const [row] = await db.select().from(scheduleProfiles).where(eq(scheduleProfiles.accountId, accountId));
  if (!row) return { ...DEFAULT_PROFILE };
  const { enabled, timezone, monthlyHours, activities, rampStart, seed } = row;
  return { enabled, timezone, monthlyHours, activities, rampStart, seed };
}

export async function saveProfile(db: Db, accountId: number, body: ScheduleProfileBody & { seed?: number }) {
  const name = await accountName(db, accountId);
  if (!validTimezone(body.timezone)) throw new HttpError(400, `timezone: unknown zone ${body.timezone}`);
  if (!fileSafe(name)) throw new HttpError(400, `the account name ${name} can't be a file name — rename it first`);
  const values = {
    enabled: body.enabled, timezone: body.timezone, monthlyHours: body.monthlyHours,
    activities: body.activities.map((a) => ({ ...a, value: a.value ? a.value : null })),
    rampStart: body.rampStart, updatedAt: new Date(),
    ...(body.seed === undefined ? {} : { seed: body.seed }),
  };
  await db.insert(scheduleProfiles).values({ accountId, ...values })
    .onConflictDoUpdate({ target: scheduleProfiles.accountId, set: values });
}

/**
 * Fills the account's blocks up to HORIZON_DAYS ahead. replace: the profile changed — every
 * future block not edited by hand is generated again; otherwise only the days past the last
 * block are added (block ids stay put). Disabled → only the replace deletes.
 */
export async function refill(db: Db, accountId: number, { replace = false, now = nowEpoch() } = {}) {
  const name = await accountName(db, accountId);
  const p = await getProfile(db, accountId);
  await db.transaction(async (tx) => {
    const mine = eq(scheduleBlocks.accountId, accountId);
    if (replace) {
      await tx.delete(scheduleBlocks)
        .where(and(mine, gt(scheduleBlocks.startAt, toDate(now)), eq(scheduleBlocks.edited, false)));
    }
    if (!p.enabled) return;
    const kept = (await tx.select({ startAt: scheduleBlocks.startAt, endAt: scheduleBlocks.endAt })
      .from(scheduleBlocks).where(and(mine, gt(scheduleBlocks.endAt, toDate(now - DAY)))))
      .map((k) => ({ start: toEpoch(k.startAt), end: toEpoch(k.endAt) }));
    const after = replace ? now : Math.max(now, ...kept.map((k) => k.end));
    const planned = generateRange({ ...p, account: name }, after, now + HORIZON_DAYS * DAY)
      .filter((b) => !kept.some((k) => b.start < k.end && k.start < b.end));
    if (planned.length === 0) return;
    await tx.insert(scheduleBlocks).values(planned.map((b) => ({
      accountId, startAt: toDate(b.start), endAt: toDate(b.end), bot: b.bot, launch: b.launch, value: b.value,
    })));
  });
}

function blockOut(r: typeof scheduleBlocks.$inferSelect): ScheduleBlock {
  return { id: r.id, start: toEpoch(r.startAt), end: toEpoch(r.endAt), bot: r.bot, launch: r.launch,
    value: r.value, edited: r.edited };
}

async function blocksBetween(db: Db, accountId: number, from: number, to: number): Promise<ScheduleBlock[]> {
  const rows = await db.select().from(scheduleBlocks).where(and(eq(scheduleBlocks.accountId, accountId),
    lt(scheduleBlocks.startAt, toDate(to)), gt(scheduleBlocks.endAt, toDate(from)))).orderBy(asc(scheduleBlocks.startAt));
  return rows.map(blockOut);
}

/** data/schedules/<account>.json: the profile's switch and the blocks from a day back on. */
export async function writeScheduleFile(db: Db, dataDir: string, accountId: number) {
  const name = await accountName(db, accountId);
  if (!fileSafe(name)) return;
  const p = await getProfile(db, accountId);
  const blocks = (await blocksBetween(db, accountId, nowEpoch() - DAY, nowEpoch() + 366 * DAY))
    .map(({ id, start, end, bot, launch, value }) => ({ id, start, end, bot, launch, value }));
  const file = { account: name, enabled: p.enabled, timezone: p.timezone, written: new Date().toISOString(), blocks };
  await writeDataFile(path.join(dataDir, "schedules"), `${name}.json`, `${JSON.stringify(file, null, 1)}\n`);
}

export async function removeScheduleFile(dataDir: string, name: string) {
  if (fileSafe(name)) await fs.rm(path.join(dataDir, "schedules", `${name}.json`), { force: true });
}

/** Every account with a profile: blocks topped up to the horizon, file rewritten. Errors: onError, next account. */
export async function refillAll(db: Db, dataDir: string, onError: (err: unknown) => void = () => {}) {
  const rows = await db.select({ id: scheduleProfiles.accountId }).from(scheduleProfiles);
  for (const { id } of rows) {
    try {
      await refill(db, id);
      await writeScheduleFile(db, dataDir, id);
    } catch (err) {
      onError(err);
    }
  }
}

/** Planned blocks and the sessions that ran, overlapping [from, to). */
export async function scheduleView(db: Db, accountId: number, from: number, to: number): Promise<ScheduleResponse> {
  const name = await accountName(db, accountId);
  const ends = sql`coalesce(${sessions.endedAt}, ${sessions.lastEventAt})`;
  // session times are naive wall time in this process's zone (= the bots', docker/.env TZ)
  const rows = await db.select({
    id: sessions.id, bot: sessions.bot, final: sessions.final,
    startedAt: sessions.startedAt, endedAt: sessions.endedAt, lastEventAt: sessions.lastEventAt,
  }).from(sessions).where(and(eq(sessions.account, name), isNotNull(sessions.startedAt),
    lt(sessions.startedAt, localIso(toDate(to))), sql`${ends} > ${localIso(toDate(from))}`))
    .orderBy(asc(sessions.startedAt));
  const actual: ActualSession[] = rows.map((r) => ({
    id: r.id, bot: r.bot, status: r.final ?? (r.endedAt ? "done" : "running"),
    start: toEpoch(new Date(iso(r.startedAt))), end: toEpoch(new Date(iso(r.endedAt ?? r.lastEventAt))),
  }));
  return { profile: await getProfile(db, accountId), blocks: await blocksBetween(db, accountId, from, to), actual,
    now: nowEpoch() };
}

/** A hand edit: the block keeps its id, gets edited = true; never empty, never over another. */
export async function editBlock(db: Db, id: number, patch: Partial<Omit<ScheduleBlock, "id" | "edited">>) {
  const [cur] = await db.select().from(scheduleBlocks).where(eq(scheduleBlocks.id, id));
  if (!cur) throw new HttpError(404, "no such block");
  const start = patch.start ?? toEpoch(cur.startAt), end = patch.end ?? toEpoch(cur.endAt);
  if (end <= start) throw new HttpError(400, "a block must end after it starts");
  const [clash] = await db.select({ id: scheduleBlocks.id }).from(scheduleBlocks).where(and(
    eq(scheduleBlocks.accountId, cur.accountId), ne(scheduleBlocks.id, id),
    lt(scheduleBlocks.startAt, toDate(end)), gt(scheduleBlocks.endAt, toDate(start))));
  if (clash) throw new HttpError(409, "it would overlap another block");
  await db.update(scheduleBlocks).set({
    startAt: toDate(start), endAt: toDate(end), bot: patch.bot ?? cur.bot, launch: patch.launch ?? cur.launch,
    value: patch.value === undefined ? cur.value : patch.value || null, edited: true,
  }).where(eq(scheduleBlocks.id, id));
  return cur.accountId;
}

export async function deleteBlock(db: Db, id: number): Promise<number> {
  const gone = await db.delete(scheduleBlocks).where(eq(scheduleBlocks.id, id)).returning({ accountId: scheduleBlocks.accountId });
  if (gone.length === 0) throw new HttpError(404, "no such block");
  return gone[0]!.accountId;
}
