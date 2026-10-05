/**
 * API contract shared by apps/api (validates requests) and apps/web (types responses).
 *
 * Timestamps are naive local wall-clock strings, "YYYY-MM-DDTHH:MM:SS.mmm", exactly as the
 * bots write them into their session logs — days are split by that wall time.
 */
import { z } from "zod";

// ── auth ─────────────────────────────────────────────────────────────────────

export const Username = z.string().trim().min(1).max(64);
export const Password = z.string().min(8, "at least 8 characters").max(256);

export const SetupBody = z.object({ username: Username, password: Password });
export const LoginBody = z.object({ username: Username, password: z.string().min(1).max(256) });
export const ChangePasswordBody = z.object({ current: z.string().min(1).max(256), next: Password });
export type SetupBody = z.infer<typeof SetupBody>;
export type LoginBody = z.infer<typeof LoginBody>;
export type ChangePasswordBody = z.infer<typeof ChangePasswordBody>;

export type Me =
  | { state: "setup" }                       // no app user yet: first run
  | { state: "anonymous" }
  | { state: "authenticated"; username: string; csrf: string };

// ── accounts ─────────────────────────────────────────────────────────────────

export const AccountName = z.string().trim().min(1, "required").max(32, "at most 32 characters");
export const AccountBody = z.object({ name: AccountName, notes: z.string().max(500).default("") });
export type AccountBody = z.input<typeof AccountBody>;

export interface Account {
  id: number;
  name: string;
  notes: string;
  active: boolean;
  hasLogin: boolean;
}

export interface AccountsResponse {
  accounts: Account[];
  /** RUNETOOLS_ACCOUNT is set for the API process: bots on this machine may ignore the active flag. */
  envOverride: string | null;
  /** Names tagged in session logs that no account row has (renamed/deleted). */
  orphanNames: string[];
  /** Some sessions carry no account (logged before tagging, or with none active). */
  hasUnassigned: boolean;
}

// ── sessions + stats ─────────────────────────────────────────────────────────

/** session_end "final", plus "running" (no end yet, recent event) and "killed" (no end, stale). */
export type SessionStatus = "running" | "killed" | "done" | "stopped" | "crashed" | "interrupted" | string;

export interface SessionRow {
  id: number;
  stamp: string | null;
  bot: string | null;
  account: string | null;
  startedAt: string;
  endedAt: string;              // session_end ts, else the last event so far
  status: SessionStatus;
  reason: string | null;
  lastStep: string | null;
  activeSeconds: number;
  pausedSeconds: number;
  runs: number;
  errors: number;
}

/** A running session. Durations are as of the response: the page ticks them on from there. */
export interface LiveSession extends SessionRow {
  idleSeconds: number;          // since the log was last written
  /** The state whose handler is running (state_enter); null for logs from before PRO-99. */
  state: string | null;
  stateSeconds: number | null;  // time in `state` so far
  paused: boolean;
  // activeSeconds here runs up to now (not the last event), unless paused
}

export interface StepRow { ts: string; state: string; result: string | null; seconds: number; run: number | null }
export interface ErrorRow {
  ts: string; type: string | null; message: string | null; traceback: string | null;
  state: string | null; where: string | null;
}
export interface StateTime { state: string; seconds: number; count: number; failures: number }

export interface SessionDetail extends SessionRow {
  file: string;
  params: Record<string, unknown>;
  pauses: number;
  steps: StepRow[];
  errorList: ErrorRow[];
  stateTime: StateTime[];
}

export const SessionsQuery = z.object({
  account: z.string().max(64).optional(),     // "" = unassigned
  bot: z.string().max(64).optional(),
  status: z.string().max(32).optional(),
  from: z.iso.date().optional(),
  to: z.iso.date().optional(),
  limit: z.coerce.number().int().min(1).max(500).default(100),
  offset: z.coerce.number().int().min(0).default(0),
});
export type SessionsQuery = z.input<typeof SessionsQuery>;
export interface SessionsResponse { sessions: SessionRow[]; total: number; bots: string[] }

export const AccountFilter = z.object({ account: z.string().max(64).optional() });

export interface DayRow { date: string; hours: number; runs: number; bots: Record<string, number> }

export interface Overview {
  now: string;
  today: { hours: number; runs: number; sessions: number; bots: Record<string, number> };
  week: { hours: number; runs: number; crashes: number };
  totalHours: number;
  daily: DayRow[];              // last 14 days, oldest first
  live: LiveSession[];
  recent: SessionRow[];
}

export interface BotStats {
  bot: string;
  sessions: number;
  activeHours: number;
  runs: number;
  runsPerHour: number;
  finals: Record<string, number>;
  reasons: { reason: string; count: number }[];
  failuresByState: { state: string; failures: number; steps: number; rate: number }[];
  recoveriesPerHour: number;
  crashTypes: { type: string; count: number }[];
}

export const BotStatsQuery = z.object({
  account: z.string().max(64).optional(),
  since: z.iso.date().optional(),
});
export interface BotStatsResponse { bots: BotStats[] }

// ── vault ────────────────────────────────────────────────────────────────────

export interface VaultStatus { exists: boolean; unlocked: boolean; autoLockSeconds: number }

export const MasterBody = z.object({ master: z.string().min(1).max(256) });
export const NewMasterBody = z.object({ master: Password });
export const ChangeMasterBody = z.object({ current: z.string().min(1).max(256), next: Password });

export const LoginEntry = z.object({
  email: z.string().max(256).default(""),
  password: z.string().max(256).default(""),
  notes: z.string().max(500).default(""),
});
export type LoginEntry = z.infer<typeof LoginEntry>;

// ── settings ─────────────────────────────────────────────────────────────────

export const SettingsBody = z.object({
  logRoots: z.array(z.string().trim().min(1).max(500)).min(1).max(20),
});
export type SettingsBody = z.infer<typeof SettingsBody>;
export interface SettingsResponse extends SettingsBody { defaultLogRoots: string[] }

// ── live feed (SSE /api/events) ──────────────────────────────────────────────

export type FeedEvent =
  | { type: "sessions"; ids: number[] }      // ingestion changed these sessions
  | { type: "accounts" }
  | { type: "vault"; unlocked: boolean };

// ── bot push (POST /api/ingest, PRO-99) ──────────────────────────────────────

/** One line a bot just wrote to its session log: file key (repo-relative), byte offset, the line. */
export const IngestBody = z.object({
  file: z.string().min(1).max(512),
  offset: z.number().int().min(0),
  line: z.string().max(4 * 1024 * 1024).regex(/^[^\r\n]*$/, "one line"),
});
export type IngestBody = z.infer<typeof IngestBody>;

/** No session_end and the log written within this window: running (logs without heartbeats). */
export const LIVE_WINDOW_SECONDS = 15 * 60;
/** Same, for a session that sends heartbeats (every 30 s): it's gone after this long without one. */
export const HEARTBEAT_WINDOW_SECONDS = 90;
export const FAILURE_RESULTS = ["fail", "not_found"] as const;
export const UNASSIGNED = "";
