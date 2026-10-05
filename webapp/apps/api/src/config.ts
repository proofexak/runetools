import path from "node:path";
import { fileURLToPath } from "node:url";

/** The runetools repo (webapp/apps/api/src → ../../../..). In Docker it is mounted at /repo. */
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");

export interface Config {
  databaseUrl: string;
  host: string;
  port: number;
  /** Directories scanned for <bot>/log/*.jsonl and <group>/<bot>/log/*.jsonl, unless set in Settings. */
  logRoots: string[];
  /** Where data/active_account lives: the bots read it at session start. */
  dataDir: string;
  /** Host headers accepted (DNS-rebinding guard); empty = derive from host + port. */
  allowedHosts: string[];
  webDist: string | null;
  pollMs: number;
  secureCookie: boolean;
  /** RUNETOOLS_ACCOUNT as seen by this process — shown in the UI as an override. */
  envAccount: string | null;
  /** Password attempts (login, unlock, ...) per minute per client. */
  passwordRateLimit: number;
}

function list(value: string | undefined): string[] {
  return (value ?? "").split(path.delimiter === ";" ? /[;,]/ : /[:,]/).map((s) => s.trim()).filter(Boolean);
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const host = env.HOST || "127.0.0.1";
  const port = Number(env.PORT || 8778);
  const publicPort = Number(env.PUBLIC_PORT || port);
  return {
    databaseUrl: env.DATABASE_URL || "postgres://runetools:runetools@127.0.0.1:5433/runetools",
    host,
    port,
    logRoots: env.LOG_ROOTS ? list(env.LOG_ROOTS) : [REPO],
    dataDir: env.DATA_DIR || path.join(REPO, "data"),
    allowedHosts: env.ALLOWED_HOSTS
      ? env.ALLOWED_HOSTS.split(",").map((s) => s.trim()).filter(Boolean)
      : [`127.0.0.1:${publicPort}`, `localhost:${publicPort}`],
    webDist: env.WEB_DIST === "" ? null : env.WEB_DIST || path.resolve(REPO, "webapp/apps/web/dist"),
    pollMs: Number(env.POLL_MS || 2000),
    secureCookie: env.COOKIE_SECURE === "1",
    envAccount: env.RUNETOOLS_ACCOUNT || null,
    passwordRateLimit: Number(env.PASSWORD_RATE_LIMIT || 10),
  };
}
