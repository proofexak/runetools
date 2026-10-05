/**
 * Live view (PRO-89): the bot container's screen in the page, and "Take control".
 *
 * GET  /api/live/config   x11vnc's password, for the logged-in page only (never in a URL)
 * GET  /api/live/vnc      WebSocket ↔ TCP bridge to x11vnc (config.vnc). The page's noVNC
 *                         speaks RFB through it, so the stream is same-origin and behind the
 *                         app login: no websockify, no extra published port.
 * GET  /api/live/control  the take-control request and the bot's answer (LiveControl)
 * POST /api/live/control  { action: "take" | "release" } → data/live_control.json, which the
 *                         bot's lib/live_control.py applies (pause + O/P off, or back) and
 *                         answers in data/live_control_ack.json
 */
import { randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import net from "node:net";
import path from "node:path";
import { LiveControlBody, type LiveConfig, type LiveControl } from "@runetools/shared";
import websocket from "@fastify/websocket";
import type { FastifyInstance, FastifyRequest } from "fastify";
import { writeDataFile } from "../accounts.js";
import type { AppContext } from "../app.js";
import { HttpError, parse } from "../http.js";

/** Stop reading from x11vnc while this much is still queued for a slow browser. */
const HIGH_WATER = 4 * 1024 * 1024;

/** Parsed JSON, or null if the file is missing or not (yet) valid JSON. */
async function readJson(file: string): Promise<Record<string, unknown> | null> {
  try {
    return JSON.parse(await fs.readFile(file, "utf8"));
  } catch {
    return null;
  }
}

export async function liveRoutes(app: FastifyInstance, { config, bus }: AppContext,
  checkOrigin: (req: FastifyRequest) => void) {
  const requestFile = path.join(config.dataDir, "live_control.json");
  const ackFile = path.join(config.dataDir, "live_control_ack.json");
  let vncDown = false;

  await app.register(websocket, { options: { maxPayload: 1024 * 1024 } });

  app.get("/api/live/config", async (): Promise<LiveConfig> => ({ password: config.vncPassword }));

  app.get("/api/live/vnc", {
    websocket: true,
    // browsers always send Origin on a WebSocket: a cross-site page must not reach the stream
    preHandler: async (req) => checkOrigin(req),
  }, (socket, req) => {
    const tcp = net.connect(config.vnc.port, config.vnc.host);
    let closed = false;
    const close = (code: number, reason: string) => {
      if (closed) return;
      closed = true;
      tcp.destroy();
      socket.close(code, reason);
    };
    tcp.setNoDelay(true);
    tcp.on("data", (chunk) => {
      socket.send(chunk, () => { if (tcp.isPaused() && socket.bufferedAmount < HIGH_WATER) tcp.resume(); });
      if (socket.bufferedAmount >= HIGH_WATER) tcp.pause();
    });
    tcp.on("connect", () => {
      if (vncDown) req.log.info("live view: VNC reachable again");
      vncDown = false;
    });
    tcp.on("error", (err) => {
      // the page retries every few seconds: say it once per outage
      if (!vncDown) req.log.warn(`live view: can't reach VNC at ${config.vnc.host}:${config.vnc.port} (${err.message})`);
      vncDown = true;
      close(1011, "VNC unreachable");
    });
    tcp.on("close", () => close(1000, "VNC closed"));
    socket.on("message", (data: Buffer | Buffer[] | ArrayBuffer) => {
      tcp.write(Buffer.isBuffer(data) ? data : Array.isArray(data) ? Buffer.concat(data) : Buffer.from(data));
    });
    socket.on("close", () => { closed = true; tcp.destroy(); });
  });

  const read = async (): Promise<LiveControl> => {
    const [request, ack] = await Promise.all([readJson(requestFile), readJson(ackFile)]);
    const id = typeof request?.id === "string" ? request.id : null;
    return {
      held: request?.held === true,
      id,
      requestedAt: typeof request?.at === "string" ? request.at : null,
      bot: id !== null && ack?.id === id ? { held: ack.held === true, safe: ack.safe === true } : null,
    };
  };

  app.get("/api/live/control", read);

  app.post("/api/live/control", async (req) => {
    const { action } = parse(LiveControlBody, req.body);
    const request = { id: randomUUID(), held: action === "take", at: new Date().toISOString() };
    try {
      await writeDataFile(config.dataDir, "live_control.json", `${JSON.stringify(request)}\n`);
    } catch (err) {
      throw new HttpError(500, `couldn't write ${requestFile}: ${(err as Error).message}`);
    }
    bus.emit({ type: "live" });
    return read();
  });
}
