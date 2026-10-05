import { AccountFilter, BotStatsQuery, SessionsQuery, type BotStatsResponse } from "@runetools/shared";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import type { AppContext } from "../app.js";
import { HttpError, parse } from "../http.js";
import { botStats, listSessions, overview, sessionDetail } from "../stats.js";

const Id = z.object({ id: z.coerce.number().int().positive() });

export async function statsRoutes(app: FastifyInstance, { db }: AppContext) {
  app.get("/api/overview", async (req) => overview(db, parse(AccountFilter, req.query).account));

  app.get("/api/sessions", async (req) => listSessions(db, parse(SessionsQuery, req.query)));

  app.get("/api/sessions/:id", async (req) => {
    const detail = await sessionDetail(db, parse(Id, req.params).id);
    if (!detail) throw new HttpError(404, "no such session");
    return detail;
  });

  app.get("/api/bots/stats", async (req): Promise<BotStatsResponse> => {
    const q = parse(BotStatsQuery, req.query);
    return { bots: await botStats(db, q.account, q.since) };
  });
}
