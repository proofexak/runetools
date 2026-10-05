/**
 * Database schema. `drizzle-kit generate` (pnpm db:generate) turns changes here into a new
 * SQL migration in ../../drizzle; the server applies pending ones at startup.
 *
 * Session timestamps are `timestamp without time zone` holding the bots' local wall time
 * as logged, read back as strings — never converted through a JS Date.
 */
import { sql } from "drizzle-orm";
import {
  bigint, bigserial, boolean, check, customType, date, doublePrecision, index, integer, jsonb,
  pgTable, pgView, serial, text, timestamp, uniqueIndex,
} from "drizzle-orm/pg-core";

const bytea = customType<{ data: Buffer; driverData: Uint8Array }>({
  dataType: () => "bytea",
  toDriver: (value) => value,
  // postgres.js gives a Buffer, PGlite a Uint8Array
  fromDriver: (value) => Buffer.from(value),
});

const wallTime = (name: string) => timestamp(name, { precision: 3, mode: "string" });
const createdAt = () => timestamp("created_at", { withTimezone: true }).notNull().defaultNow();

// ── app login ────────────────────────────────────────────────────────────────

export const users = pgTable("users", {
  id: serial("id").primaryKey(),
  username: text("username").notNull().unique(),
  passwordHash: text("password_hash").notNull(),          // argon2id PHC string
  createdAt: createdAt(),
});

export const authSessions = pgTable("auth_sessions", {
  id: text("id").primaryKey(),                              // sha256 of the cookie token
  userId: integer("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  csrf: text("csrf").notNull(),
  createdAt: createdAt(),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
});

// ── accounts + vault ─────────────────────────────────────────────────────────

export const accounts = pgTable("accounts", {
  id: serial("id").primaryKey(),
  name: text("name").notNull().unique(),
  notes: text("notes").notNull().default(""),
  active: boolean("active").notNull().default(false),
  createdAt: createdAt(),
}, (t) => [uniqueIndex("accounts_one_active").on(t.active).where(sql`${t.active}`)]);

/** One encrypted login per account: AES-256-GCM over {email, password, notes}, AAD = account id. */
export const credentials = pgTable("credentials", {
  id: serial("id").primaryKey(),
  accountId: integer("account_id").notNull().unique().references(() => accounts.id, { onDelete: "cascade" }),
  ciphertext: bytea("ciphertext").notNull(),
  nonce: bytea("nonce").notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

/** Singleton: argon2id salt + params for the master key and a sealed check value. */
export const vaultMeta = pgTable("vault_meta", {
  id: integer("id").primaryKey().default(1),
  salt: bytea("salt").notNull(),
  kdf: jsonb("kdf").$type<{ memoryCost: number; timeCost: number; parallelism: number }>().notNull(),
  checkCiphertext: bytea("check_ciphertext").notNull(),
  checkNonce: bytea("check_nonce").notNull(),
  createdAt: createdAt(),
}, (t) => [check("vault_meta_singleton", sql`${t.id} = 1`)]);

export const settings = pgTable("settings", {
  key: text("key").primaryKey(),
  value: jsonb("value").notNull(),
});

// ── ingested session logs ────────────────────────────────────────────────────

export const sessions = pgTable("sessions", {
  id: serial("id").primaryKey(),
  file: text("file").notNull().unique(),                    // absolute path of the .jsonl
  stamp: text("stamp"),
  bot: text("bot"),
  account: text("account"),                                 // name as tagged; not a FK (renames, deletes)
  pid: integer("pid"),
  params: jsonb("params").$type<Record<string, unknown>>().notNull().default({}),
  startedAt: wallTime("started_at").notNull(),
  lastEventAt: wallTime("last_event_at").notNull(),
  endedAt: wallTime("ended_at"),                            // session_end ts; null = killed or running
  final: text("final"),
  reason: text("reason"),
  lastStep: text("last_step"),
  activeSeconds: doublePrecision("active_seconds").notNull().default(0),
  pausedSeconds: doublePrecision("paused_seconds").notNull().default(0),
  pauses: integer("pauses").notNull().default(0),
  runs: integer("runs").notNull().default(0),
  errorCount: integer("error_count").notNull().default(0),
}, (t) => [
  index("sessions_started_at").on(t.startedAt),
  index("sessions_account").on(t.account),
  index("sessions_bot").on(t.bot),
]);

export const steps = pgTable("steps", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  sessionId: integer("session_id").notNull().references(() => sessions.id, { onDelete: "cascade" }),
  ts: wallTime("ts").notNull(),
  state: text("state").notNull(),
  result: text("result"),
  seconds: doublePrecision("seconds").notNull().default(0),
  run: integer("run"),
}, (t) => [index("steps_session").on(t.sessionId)]);

export const errors = pgTable("errors", {
  id: serial("id").primaryKey(),
  sessionId: integer("session_id").notNull().references(() => sessions.id, { onDelete: "cascade" }),
  ts: wallTime("ts").notNull(),
  type: text("type"),
  message: text("message"),
  traceback: text("traceback"),
  state: text("state"),
  where: text("where"),
}, (t) => [index("errors_session").on(t.sessionId)]);

/** How far each log file has been read. Only whole lines are consumed. */
export const ingestCursors = pgTable("ingest_cursors", {
  path: text("path").primaryKey(),
  offset: bigint("offset", { mode: "number" }).notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

/**
 * Active hours + runs per account, bot and day. Only a session's total active time is
 * logged, so a session spanning midnight is split in proportion to its wall time on each
 * day (pauses assumed spread evenly) — same rule as the Python prototype.
 */
export const dailyActivity = pgView("daily_activity", {
  account: text("account"),
  bot: text("bot"),
  day: date("day", { mode: "string" }).notNull(),
  hours: doublePrecision("hours").notNull(),
  runs: doublePrecision("runs").notNull(),
}).as(sql`
  SELECT s.account, s.bot, d.day::date AS day,
         sum(s.active_seconds * d.frac) / 3600 AS hours,
         sum(s.runs * d.frac) AS runs
  FROM sessions s
  CROSS JOIN LATERAL (
    SELECT g AS day,
           CASE WHEN coalesce(s.ended_at, s.last_event_at) <= s.started_at THEN 1.0
                ELSE extract(epoch FROM least(coalesce(s.ended_at, s.last_event_at), g + interval '1 day')
                                        - greatest(s.started_at, g))
                     / extract(epoch FROM coalesce(s.ended_at, s.last_event_at) - s.started_at)
           END AS frac
    FROM generate_series(date_trunc('day', s.started_at),
                         date_trunc('day', coalesce(s.ended_at, s.last_event_at)),
                         interval '1 day') AS g
  ) d
  WHERE d.frac > 0
  GROUP BY s.account, s.bot, d.day
`);
