import { AccountFilter, BotStatsQuery, SessionsQuery, type BotStatsResponse } from "@runetools/shared";
import fs from "node:fs/promises";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import type { AppContext } from "../app.js";
import { HttpError, parse } from "../http.js";
import { screenshotFile } from "../screenshots.js";
import { getLogRoots } from "../settings.js";
import { botStats, listSessions, overview, sessionDetail } from "../stats.js";

const Id = z.object({ id: z.coerce.number().int().positive() });

export async function statsRoutes(app: FastifyInstance, { db, config }: AppContext) {
  app.get("/api/overview", async (req) => overview(db, parse(AccountFilter, req.query).account));

  app.get("/api/sessions", async (req) => listSessions(db, parse(SessionsQuery, req.query)));

  app.get("/api/sessions/:id", async (req) => {
    const detail = await sessionDetail(db, parse(Id, req.params).id);
    if (!detail) throw new HttpError(404, "no such session");
    return detail;
  });

  // a failure screenshot (PRO-91): only one the session recorded, from its log's own folder
  app.get("/api/sessions/:id/screenshots/:file", async (req, reply) => {
    const { id, file } = req.params as { id: string; file: string };
    const n = Number(id);
    const abs = Number.isSafeInteger(n) && n > 0
      ? await screenshotFile(db, await getLogRoots(db, config), n, file) : null;
    if (!abs) throw new HttpError(404, "no such screenshot");
    return reply.type("image/png").send(await fs.readFile(abs));
  });

  app.get("/api/bots/stats", async (req): Promise<BotStatsResponse> => {
    const q = parse(BotStatsQuery, req.query);
    return { bots: await botStats(db, q.account, q.since) };
  });
}
