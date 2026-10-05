/**
 * Read side: session lists, one session in detail, the dashboard overview and per-bot
 * stats (logreport `stats` as data). "today" is the API process's local date, which has to
 * be the bots' zone (TZ) since the logs hold naive wall time; liveness instead compares
 * the log file's mtime with now(), which needs no zone at all. A session that sends
 * heartbeats (every 30 s, PRO-99) is gone after 90 s without a write; older logs keep the
 * 15-minute rule.
 */
import {
  FAILURE_RESULTS, HEARTBEAT_WINDOW_SECONDS, LIVE_WINDOW_SECONDS, type BotStats, type DayRow, type LiveSession,
  type Overview, type SessionDetail, type SessionRow, type SessionsQuery,
} from "@runetools/shared";
import { and, asc, count, desc, eq, gte, inArray, isNull, lte, or, sql, type SQL } from "drizzle-orm";
import type { z } from "zod";
import type { Db } from "./db/index.js";
import { dailyActivity, errors, sessions, steps } from "./db/schema.js";
import { addDays, iso, localIso } from "./time.js";

export const status = sql<string>`CASE
  WHEN ${sessions.final} IS NOT NULL THEN ${sessions.final}
  WHEN ${sessions.fileMtime} > now() - CASE WHEN ${sessions.lastHeartbeat} IS NULL
    THEN interval '${sql.raw(String(LIVE_WINDOW_SECONDS))} seconds'
    ELSE interval '${sql.raw(String(HEARTBEAT_WINDOW_SECONDS))} seconds' END THEN 'running'
  ELSE 'killed' END`;

const endedAt = sql<string>`coalesce(${sessions.endedAt}, ${sessions.lastEventAt})`;

const rowFields = {
  id: sessions.id,
  stamp: sessions.stamp,
  bot: sessions.bot,
  account: sessions.account,
  startedAt: sessions.startedAt,
  endedAt: sql<string>`${endedAt}::text`,
  status,
  reason: sessions.reason,
  lastStep: sessions.lastStep,
  activeSeconds: sessions.activeSeconds,
  pausedSeconds: sessions.pausedSeconds,
  runs: sessions.runs,
  errors: sessions.errorCount,
};

type RawRow = { [K in keyof typeof rowFields]: unknown } & { startedAt: string; endedAt: string };

function toRow(r: RawRow): SessionRow {
  return {
    ...(r as unknown as SessionRow),
    startedAt: iso(r.startedAt),
    endedAt: iso(r.endedAt),
    // logreport: no reason → "after <last step>"
    reason: (r.reason as string | null) ?? (r.lastStep ? `after ${r.lastStep}` : null),
  };
}

/** undefined = every account; "" = sessions without one. */
export function accountWhere(account: string | undefined): SQL | undefined {
  if (account === undefined) return undefined;
  if (account === "") return or(isNull(sessions.account), eq(sessions.account, ""));
  return eq(sessions.account, account);
}

function dailyAccountWhere(account: string | undefined): SQL | undefined {
  if (account === undefined) return undefined;
  if (account === "") return or(isNull(dailyActivity.account), eq(dailyActivity.account, ""));
  return eq(dailyActivity.account, account);
}

// ── sessions ─────────────────────────────────────────────────────────────────

export async function listSessions(db: Db, q: z.output<typeof SessionsQuery>) {
  const where = and(
    accountWhere(q.account),
    q.bot ? eq(sessions.bot, q.bot) : undefined,
    q.status ? sql`${status} = ${q.status}` : undefined,
    q.from ? gte(sessions.startedAt, `${q.from}T00:00:00`) : undefined,
    q.to ? lte(sessions.startedAt, `${q.to}T23:59:59.999`) : undefined,
  );
  const [rows, [total], bots] = await Promise.all([
    db.select(rowFields).from(sessions).where(where)
      .orderBy(desc(sessions.startedAt), desc(sessions.id)).limit(q.limit).offset(q.offset),
    db.select({ n: count() }).from(sessions).where(where),
    db.selectDistinct({ bot: sessions.bot }).from(sessions).orderBy(asc(sessions.bot)),
  ]);
  return {
    sessions: rows.map((r) => toRow(r as RawRow)),
    total: total?.n ?? 0,
    bots: bots.map((b) => b.bot).filter((b): b is string => !!b),
  };
}

const MAX_STEPS = 2000;

export async function sessionDetail(db: Db, id: number): Promise<SessionDetail | null> {
  const [row] = await db.select({ ...rowFields, file: sessions.file, params: sessions.params, pauses: sessions.pauses })
    .from(sessions).where(eq(sessions.id, id));
  if (!row) return null;
  const failed = inArray(steps.result, [...FAILURE_RESULTS]);
  const [stepRows, errorRows, stateTime] = await Promise.all([
    // the newest MAX_STEPS, shown oldest first
    db.select({ ts: steps.ts, state: steps.state, result: steps.result, seconds: steps.seconds, run: steps.run })
      .from(steps).where(eq(steps.sessionId, id)).orderBy(desc(steps.id)).limit(MAX_STEPS),
    db.select({ ts: errors.ts, type: errors.type, message: errors.message, traceback: errors.traceback,
      state: errors.state, where: errors.where })
      .from(errors).where(eq(errors.sessionId, id)).orderBy(asc(errors.id)),
    db.select({
      state: steps.state,
      seconds: sql<number>`sum(${steps.seconds})::float8`,
      count: sql<number>`count(*)::int`,
      failures: sql<number>`(count(*) FILTER (WHERE ${failed}))::int`,
    }).from(steps).where(eq(steps.sessionId, id)).groupBy(steps.state).orderBy(desc(sql`sum(${steps.seconds})`), asc(steps.state)),
  ]);
  const { file, params, pauses, ...base } = row;
  return {
    ...toRow(base as RawRow),
    file, params, pauses,
    steps: stepRows.reverse().map((s) => ({ ...s, ts: iso(s.ts) })),
    errorList: errorRows.map((e) => ({ ...e, ts: iso(e.ts) })),
    stateTime,
  };
}

// ── overview ─────────────────────────────────────────────────────────────────

export const DAYS = 14;

export async function overview(db: Db, account: string | undefined, now = localIso()): Promise<Overview> {
  const today = now.slice(0, 10);
  const first = addDays(today, -(DAYS - 1));
  const weekStart = addDays(today, -6);
  const acc = accountWhere(account);

  const [dayRows, liveRows, recentRows, [totals], [todayCount], [crashes]] = await Promise.all([
    db.select({
      day: dailyActivity.day, bot: dailyActivity.bot,
      hours: sql<number>`sum(${dailyActivity.hours})::float8`, runs: sql<number>`sum(${dailyActivity.runs})::float8`,
    }).from(dailyActivity)
      .where(and(dailyAccountWhere(account), gte(dailyActivity.day, first), lte(dailyActivity.day, today)))
      .groupBy(dailyActivity.day, dailyActivity.bot),
    db.select({
      ...rowFields,
      idleSeconds: sql<number>`extract(epoch FROM now() - ${sessions.fileMtime})::float8`,
      state: sessions.currentState,
      // both naive wall times from one log: their difference needs no zone
      stateSeconds: sql<number | null>`extract(epoch FROM ${sessions.lastEventAt} - ${sessions.stateSince})::float8`,
      paused: sql<boolean>`${sessions.pausedSince} IS NOT NULL`,
    })
      .from(sessions).where(and(acc, sql`${status} = 'running'`)).orderBy(desc(sessions.startedAt)),
    db.select(rowFields).from(sessions).where(acc).orderBy(desc(sessions.startedAt), desc(sessions.id)).limit(25),
    db.select({ seconds: sql<number>`coalesce(sum(${sessions.activeSeconds}), 0)::float8` }).from(sessions).where(acc),
    db.select({ n: count() }).from(sessions).where(and(acc, sql`${endedAt} >= ${today}::timestamp`)),
    db.select({ n: count() }).from(sessions)
      .where(and(acc, eq(sessions.final, "crashed"), gte(sessions.startedAt, `${weekStart}T00:00:00`))),
  ]);

  const days = new Map<string, DayRow>();
  for (let d = first; d <= today; d = addDays(d, 1)) days.set(d, { date: d, hours: 0, runs: 0, bots: {} });
  for (const r of dayRows) {
    const row = days.get(r.day);
    if (!row) continue;
    row.hours += r.hours;
    row.runs += r.runs;
    const bot = r.bot ?? "?";
    row.bots[bot] = (row.bots[bot] ?? 0) + r.hours;
  }
  const t = days.get(today)!;
  const live = liveRows.map((r) => liveRow(r as Parameters<typeof liveRow>[0]));
  for (const s of live) {
    // running now: its time since the last logged event belongs to today (logged time is in already)
    const extra = s.paused ? 0 : s.idleSeconds / 3600;
    const bot = s.bot ?? "?";
    t.hours += extra;
    t.bots[bot] = (t.bots[bot] ?? 0) + extra;
  }
  const daily = [...days.values()];
  const week = daily.filter((d) => d.date >= weekStart);

  return {
    now,
    today: { hours: t.hours, runs: Math.round(t.runs), sessions: todayCount?.n ?? 0, bots: t.bots },
    week: {
      hours: week.reduce((a, d) => a + d.hours, 0),
      runs: Math.round(week.reduce((a, d) => a + d.runs, 0)),
      crashes: crashes?.n ?? 0,
    },
    totalHours: (totals?.seconds ?? 0) / 3600,
    daily,
    live,
    recent: recentRows.map((r) => toRow(r as RawRow)),
  };
}

/** Durations brought from the last logged event up to now: the bot has been at it since. */
function liveRow(r: RawRow & { idleSeconds: number; state: string | null; stateSeconds: number | null; paused: boolean }): LiveSession {
  const idle = Math.max(0, r.idleSeconds ?? 0);
  const row = toRow(r);
  return {
    ...row,
    activeSeconds: row.activeSeconds + (r.paused ? 0 : idle),
    idleSeconds: idle,
    state: r.state,
    stateSeconds: r.state !== null && r.stateSeconds !== null ? Math.max(0, r.stateSeconds) + idle : null,
    paused: r.paused,
  };
}

// ── per-bot stats (logreport.aggregate) ──────────────────────────────────────

export async function botStats(db: Db, account: string | undefined, since: string | undefined): Promise<BotStats[]> {
  const where = and(accountWhere(account), since ? gte(sessions.startedAt, `${since}T00:00:00`) : undefined);
  const failed = inArray(steps.result, [...FAILURE_RESULTS]);
  const [base, finals, reasons, stepStats, crashTypes] = await Promise.all([
    db.select({
      bot: sessions.bot,
      sessions: sql<number>`count(*)::int`,
      seconds: sql<number>`sum(${sessions.activeSeconds})::float8`,
      runs: sql<number>`sum(${sessions.runs})::int`,
    }).from(sessions).where(where).groupBy(sessions.bot),
    db.select({ bot: sessions.bot, status, n: sql<number>`count(*)::int` })
      .from(sessions).where(where).groupBy(sessions.bot, status),
    db.select({ bot: sessions.bot, reason: sessions.reason, n: sql<number>`count(*)::int` })
      .from(sessions).where(and(where, sql`${sessions.reason} IS NOT NULL`))
      .groupBy(sessions.bot, sessions.reason).orderBy(desc(sql`count(*)`)),
    db.select({
      bot: sessions.bot, state: steps.state,
      steps: sql<number>`count(*)::int`,
      failures: sql<number>`(count(*) FILTER (WHERE ${failed}))::int`,
    }).from(steps).innerJoin(sessions, eq(sessions.id, steps.sessionId)).where(where)
      .groupBy(sessions.bot, steps.state),
    db.select({ bot: sessions.bot, type: errors.type, n: sql<number>`count(*)::int` })
      .from(errors).innerJoin(sessions, eq(sessions.id, errors.sessionId)).where(where)
      .groupBy(sessions.bot, errors.type).orderBy(desc(sql`count(*)`)),
  ]);

  return base
    .map((b): BotStats => {
      const bot = b.bot ?? "?";
      const mine = <T extends { bot: string | null }>(rows: T[]) => rows.filter((r) => (r.bot ?? "?") === bot);
      const hours = b.seconds / 3600;
      const states = mine(stepStats);
      const recoveries = states.find((s) => s.state === "recover")?.steps ?? 0;
      return {
        bot,
        sessions: b.sessions,
        activeHours: hours,
        runs: b.runs,
        runsPerHour: hours > 0 ? b.runs / hours : 0,
        finals: Object.fromEntries(mine(finals).map((f) => [f.status, f.n])),
        reasons: mine(reasons).slice(0, 5).map((r) => ({ reason: r.reason!, count: r.n })),
        failuresByState: states.filter((s) => s.failures > 0)
          .map((s) => ({ state: s.state, failures: s.failures, steps: s.steps, rate: s.failures / s.steps }))
          .sort((x, y) => y.failures - x.failures),
        recoveriesPerHour: hours > 0 ? recoveries / hours : 0,
        crashTypes: mine(crashTypes).map((c) => ({ type: c.type ?? "?", count: c.n })),
      };
    })
    .sort((a, b) => a.bot.localeCompare(b.bot));
}
