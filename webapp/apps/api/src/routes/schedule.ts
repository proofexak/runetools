import { ScheduleBlockPatch, ScheduleProfileBody } from "@runetools/shared";
import { eq } from "drizzle-orm";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import type { AppContext } from "../app.js";
import { accounts } from "../db/schema.js";
import { ok, parse } from "../http.js";
import {
  deleteBlock, editBlock, getProfile, refill, saveProfile, scheduleView, writeScheduleFile,
} from "../schedule/store.js";

const Id = z.object({ id: z.coerce.number().int().positive() });
const Window = z.object({ from: z.coerce.number().int().optional(), to: z.coerce.number().int().optional() });

export async function scheduleRoutes(app: FastifyInstance, { db, config, bus }: AppContext) {
  /** After a change: rewrite the bot's file, tell open pages. */
  const changed = async (accountId: number) => {
    await writeScheduleFile(db, config.dataDir, accountId);
    const [row] = await db.select({ name: accounts.name }).from(accounts).where(eq(accounts.id, accountId));
    bus.emit({ type: "schedule", account: row?.name ?? "" });
  };

  app.get("/api/accounts/:id/schedule", async (req) => {
    const { id } = parse(Id, req.params);
    const now = Math.floor(Date.now() / 1000);
    const { from = now - 7 * 86_400, to = now + 14 * 86_400 } = parse(Window, req.query);
    return scheduleView(db, id, from, to);
  });

  app.put("/api/accounts/:id/schedule", async (req, reply) => {
    const { id } = parse(Id, req.params);
    await saveProfile(db, id, parse(ScheduleProfileBody, req.body));
    await refill(db, id, { replace: true });
    await changed(id);
    return ok(reply);
  });

  app.post("/api/accounts/:id/schedule/regenerate", async (req, reply) => {
    const { id } = parse(Id, req.params);
    const p = await getProfile(db, id);
    await saveProfile(db, id, { ...p, seed: p.seed + 1 });
    await refill(db, id, { replace: true });
    await changed(id);
    return ok(reply);
  });

  app.patch("/api/schedule/blocks/:id", async (req, reply) => {
    const { id } = parse(Id, req.params);
    await changed(await editBlock(db, id, parse(ScheduleBlockPatch, req.body)));
    return ok(reply);
  });

  app.delete("/api/schedule/blocks/:id", async (req, reply) => {
    await changed(await deleteBlock(db, parse(Id, req.params).id));
    return ok(reply);
  });
}
