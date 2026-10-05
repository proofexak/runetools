/**
 * The Fastify app, built from its dependencies so tests can drive it with app.inject().
 *
 * Every /api route except health and the auth entry points needs a logged-in session;
 * every mutating /api request also needs the session's CSRF token (x-csrf-token) and,
 * when the browser sends one, a same-site Origin. Host headers are checked against
 * allowedHosts so a DNS-rebinding page can't talk to the server. The bots' POST /api/ingest
 * authenticates with the bot token instead of the cookie (routes/ingest.ts).
 */
import fs from "node:fs";
import path from "node:path";
import cookie from "@fastify/cookie";
import rateLimit from "@fastify/rate-limit";
import fastifyStatic from "@fastify/static";
import Fastify, { LogController, type FastifyInstance, type FastifyRequest } from "fastify";
import { COOKIE, lookupSession, safeEqual, type AuthedSession } from "./auth/auth.js";
import type { Bus } from "./bus.js";
import type { Config } from "./config.js";
import type { Db } from "./db/index.js";
import { HttpError } from "./http.js";
import type { Ingester } from "./ingest/ingester.js";
import { accountRoutes } from "./routes/accounts.js";
import { authRoutes } from "./routes/auth.js";
import { eventRoutes } from "./routes/events.js";
import { INGEST_ROUTE, ingestRoutes } from "./routes/ingest.js";
import { liveRoutes } from "./routes/live.js";
import { settingsRoutes } from "./routes/settings.js";
import { statsRoutes } from "./routes/stats.js";
import { vaultRoutes } from "./routes/vault.js";
import type { Vault } from "./vault/vault.js";

export interface AppContext {
  db: Db;
  config: Config;
  bus: Bus;
  vault: Vault;
  /** Absent in tests that don't need it; routes then skip "rescan now" triggers. */
  ingester?: Ingester;
  /** data/bot_token: what bots send to POST /api/ingest. Absent = pushes are refused. */
  botToken?: string | null;
}

declare module "fastify" {
  interface FastifyRequest { auth: AuthedSession | null }
}

const PUBLIC = new Set(["/api/health", "/api/auth/me", "/api/auth/setup", "/api/auth/login"]);
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

const SECURITY_HEADERS = {
  "x-frame-options": "DENY",
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer",
  "cross-origin-opener-policy": "same-origin",
  "content-security-policy":
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; " +
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; " +
    "frame-ancestors 'none'",
};

export async function buildApp(ctx: AppContext, register?: (app: FastifyInstance) => Promise<void>) {
  const app = Fastify({
    logger: process.env.NODE_ENV === "test" ? false : { level: process.env.LOG_LEVEL || "info" },
    bodyLimit: 64 * 1024,
    trustProxy: false,
    logController: new LogController({ disableRequestLogging: true }),
  });
  const allowed = new Set(ctx.config.allowedHosts);
  const anyHost = allowed.has("*");

  await app.register(cookie);
  await app.register(rateLimit, { global: false });
  app.decorateRequest("auth", null);

  app.addHook("onRequest", async (req) => {
    if (req.url === "/api/health") return;
    if (!anyHost && !allowed.has(req.headers.host ?? "")) throw new HttpError(403, "bad host");
  });

  app.addHook("preHandler", async (req) => {
    if (!req.url.startsWith("/api/")) return;
    const route = req.url.split("?", 1)[0]!;
    if (route === INGEST_ROUTE) return;      // bot token, checked by the route
    req.auth = await lookupSession(ctx.db, req.cookies[COOKIE]);
    if (!SAFE_METHODS.has(req.method)) checkOrigin(req, allowed, anyHost);
    if (PUBLIC.has(route)) return;
    if (!req.auth) throw new HttpError(401, "not logged in");
    if (!SAFE_METHODS.has(req.method)) {
      const sent = req.headers["x-csrf-token"];
      if (typeof sent !== "string" || !safeEqual(sent, req.auth.csrf)) throw new HttpError(403, "bad csrf token");
    }
  });

  app.addHook("onSend", async (req, reply) => {
    reply.headers(SECURITY_HEADERS);
    if (req.url.startsWith("/api/")) reply.header("cache-control", "no-store");
  });

  app.setErrorHandler((err: Error & { statusCode?: number }, req, reply) => {
    if (err instanceof HttpError) return reply.status(err.status).send({ error: err.message });
    if (err.statusCode && err.statusCode < 500) return reply.status(err.statusCode).send({ error: err.message });
    req.log.error(err);
    return reply.status(500).send({ error: "internal error" });
  });

  app.get("/api/health", async () => ({ ok: true }));
  await authRoutes(app, ctx);
  await statsRoutes(app, ctx);
  await accountRoutes(app, ctx);
  await vaultRoutes(app, ctx);
  await settingsRoutes(app, ctx);
  await eventRoutes(app, ctx);
  await ingestRoutes(app, ctx);
  await liveRoutes(app, ctx, (req) => checkOrigin(req, allowed, anyHost));
  if (register) await register(app);

  const dist = ctx.config.webDist;
  if (dist && fs.existsSync(path.join(dist, "index.html"))) {
    await app.register(fastifyStatic, { root: dist, index: ["index.html"] });
    // client-side routes (/sessions/12 ...) get the SPA shell; a missing file is a 404
    app.setNotFoundHandler((req, reply) => {
      const route = req.url.split("?", 1)[0]!;
      if (req.method === "GET" && !route.startsWith("/api/") && !path.extname(route)) {
        return reply.header("cache-control", "no-cache").sendFile("index.html");
      }
      return reply.status(404).send({ error: "not found" });
    });
  } else {
    app.setNotFoundHandler((_req, reply) => reply.status(404).send({ error: "not found" }));
  }
  return app;
}

function checkOrigin(req: FastifyRequest, allowed: Set<string>, anyHost: boolean) {
  const origin = req.headers.origin;
  if (!origin || anyHost) return;
  let host: string;
  try {
    host = new URL(origin).host;
  } catch {
    throw new HttpError(403, "bad origin");
  }
  if (!allowed.has(host) || host !== req.headers.host) throw new HttpError(403, "bad origin");
}
