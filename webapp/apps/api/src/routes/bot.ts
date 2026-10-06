/**
 * Bot container control (PRO-90): GET /api/bot (container + manual mode + job), and
 * POST /api/bot/start | /api/bot/stop. Logged in + CSRF like every mutating route; the
 * start / stop run in the background and report on the bus ({type: "bot"}).
 */
import type { FastifyInstance } from "fastify";
import type { AppContext } from "../app.js";

export async function botRoutes(app: FastifyInstance, { botControl }: AppContext & { botControl: NonNullable<AppContext["botControl"]> }) {
  app.get("/api/bot", async () => botControl.status());

  app.post("/api/bot/start", async (_req, reply) => {
    botControl.start();
    return reply.status(202).send(await botControl.status());
  });

  app.post("/api/bot/stop", async (_req, reply) => {
    botControl.stop();
    return reply.status(202).send(await botControl.status());
  });
}
