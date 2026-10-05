import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { FastifyInstance, LightMyRequestResponse } from "fastify";
import { buildApp, type AppContext } from "../src/app.js";
import { Bus } from "../src/bus.js";
import { loadConfig, type Config } from "../src/config.js";
import { sql } from "drizzle-orm";
import { openDb, type DbHandle } from "../src/db/index.js";

process.env.NODE_ENV = "test";

export const HOST = "127.0.0.1:8778";

export function tmpDir(prefix = "rt-") {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

export interface TestApp {
  app: FastifyInstance;
  ctx: AppContext;
  handle: DbHandle;
  close: () => Promise<void>;
}

// One PGlite per test file (worker): starting one takes seconds. Tests get it truncated.
let shared: Promise<DbHandle> | null = null;

export async function testDb(): Promise<DbHandle> {
  shared ??= openDb("pglite:memory");
  const handle = await shared;
  await handle.db.execute(sql`TRUNCATE users, auth_sessions, accounts, credentials, vault_meta, settings,
    sessions, steps, errors, ingest_cursors RESTART IDENTITY CASCADE`);
  return handle;
}

export async function makeApp(overrides: Partial<Config> = {},
  register?: (app: FastifyInstance, ctx: AppContext) => Promise<void>): Promise<TestApp> {
  const handle = await testDb();
  const root = tmpDir();
  const config: Config = {
    ...loadConfig({}),
    logRoots: [root],
    dataDir: path.join(root, "data"),
    webDist: null,
    ...overrides,
  };
  const ctx: AppContext = { db: handle.db, config, bus: new Bus() };
  const app = await buildApp(ctx, register ? (a) => register(a, ctx) : undefined);
  return { app, ctx, handle, close: async () => { await app.close(); } };
}

export interface Client {
  get: (url: string) => Promise<LightMyRequestResponse>;
  post: (url: string, body?: unknown) => Promise<LightMyRequestResponse>;
  send: (method: "PUT" | "PATCH" | "DELETE" | "POST", url: string, body?: unknown) => Promise<LightMyRequestResponse>;
  cookie: string;
  csrf: string;
}

/** Sets up the app user (first run) and returns a logged-in client. */
export async function login(app: FastifyInstance, username = "admin", password = "correct horse"): Promise<Client> {
  let res = await app.inject({ method: "POST", url: "/api/auth/setup", headers: { host: HOST }, payload: { username, password } });
  if (res.statusCode === 409) {
    res = await app.inject({ method: "POST", url: "/api/auth/login", headers: { host: HOST }, payload: { username, password } });
  }
  if (res.statusCode !== 200) throw new Error(`login failed: ${res.statusCode} ${res.body}`);
  const cookie = res.cookies.find((c) => c.name === "rt_session")!.value;
  const me = await app.inject({ url: "/api/auth/me", headers: { host: HOST }, cookies: { rt_session: cookie } });
  const csrf = me.json().csrf as string;
  const send = (method: "PUT" | "PATCH" | "DELETE" | "POST", url: string, body?: unknown) => app.inject({
    method, url, headers: { host: HOST, "x-csrf-token": csrf }, cookies: { rt_session: cookie },
    ...(body === undefined ? {} : { payload: body as object }),
  });
  return {
    cookie, csrf, send,
    get: (url) => app.inject({ url, headers: { host: HOST }, cookies: { rt_session: cookie } }),
    post: (url, body) => send("POST", url, body ?? {}),
  };
}
