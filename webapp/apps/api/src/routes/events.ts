/**
 * GET /api/events — Server-Sent Events. The page keeps one open and refetches whatever an
 * event names (sessions changed by ingestion, accounts, vault lock state).
 */
import type { FastifyInstance } from "fastify";
import type { AppContext } from "../app.js";

const HEARTBEAT_MS = 25_000;

export async function eventRoutes(app: FastifyInstance, { bus }: AppContext) {
  const streams = new Set<() => void>();
  // let app.close() finish while browsers stay connected
  app.addHook("onClose", async () => { for (const end of [...streams]) end(); });

  app.get("/api/events", (req, reply) => {
    reply.hijack();
    const res = reply.raw;
    res.writeHead(200, {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-store",
      connection: "keep-alive",
      "x-content-type-options": "nosniff",
      "x-accel-buffering": "no",
    });
    res.write("retry: 3000\n\n");
    const off = bus.on((event) => res.write(`data: ${JSON.stringify(event)}\n\n`));
    const beat = setInterval(() => res.write(": ping\n\n"), HEARTBEAT_MS);
    const end = () => {
      if (!streams.delete(end)) return;
      clearInterval(beat);
      off();
      res.end();
    };
    streams.add(end);
    req.raw.on("close", end);
  });
}
