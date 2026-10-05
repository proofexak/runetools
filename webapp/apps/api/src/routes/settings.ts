import fs from "node:fs/promises";
import path from "node:path";
import { SettingsBody, type SettingsResponse } from "@runetools/shared";
import type { FastifyInstance } from "fastify";
import type { AppContext } from "../app.js";
import { HttpError, parse } from "../http.js";
import { getLogRoots, setLogRoots } from "../settings.js";

export async function settingsRoutes(app: FastifyInstance, { db, config, ingester }: AppContext) {
  const read = async (): Promise<SettingsResponse> => ({
    logRoots: await getLogRoots(db, config),
    defaultLogRoots: config.logRoots,
  });

  app.get("/api/settings", read);

  app.put("/api/settings", async (req) => {
    const { logRoots } = parse(SettingsBody, req.body);
    const roots = [...new Set(logRoots.map((r) => path.resolve(r)))];
    for (const r of roots) {
      const st = await fs.stat(r).catch(() => null);
      if (!st?.isDirectory()) throw new HttpError(400, `not a directory the server can see: ${r}`);
    }
    await setLogRoots(db, roots);
    void ingester?.scanOnce();
    return read();
  });
}
