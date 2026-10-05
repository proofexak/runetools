/**
 * POST /api/ingest — a bot pushes each session-log line as it writes it (lib/events.py,
 * PRO-99). Authenticated by the bot token (data/bot_token), not the login cookie: no CSRF
 * or Origin check, bots send neither. The tailer still reads every file, so a push that's
 * dropped, refused or early changes nothing but how soon the page sees the line.
 */
import { IngestBody } from "@runetools/shared";
import type { FastifyInstance } from "fastify";
import type { AppContext } from "../app.js";
import { safeEqual } from "../auth/auth.js";
import { HttpError, parse } from "../http.js";

export const INGEST_ROUTE = "/api/ingest";

export async function ingestRoutes(app: FastifyInstance, ctx: AppContext) {
  app.post(INGEST_ROUTE, { bodyLimit: 8 * 1024 * 1024 }, async (req) => {
    const { botToken, ingester } = ctx;
    const auth = req.headers.authorization;
    const sent = typeof auth === "string" && auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
    if (!botToken || !sent || !safeEqual(sent, botToken)) throw new HttpError(401, "bad bot token");
    const body = parse(IngestBody, req.body);
    if (!ingester) throw new HttpError(503, "ingestion is off");
    const result = await ingester.push(body.file, body.offset, body.line);
    if (result === "unknown") throw new HttpError(404, "not a session log");
    return { result };
  });
}
