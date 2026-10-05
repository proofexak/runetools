import { AccountBody, AccountName } from "@runetools/shared";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { createAccount, deleteAccount, listAccounts, setActive, updateAccount } from "../accounts.js";
import type { AppContext } from "../app.js";
import { ok, parse } from "../http.js";

const Id = z.object({ id: z.coerce.number().int().positive() });
// explicit, not AccountBody.partial(): an omitted field must stay untouched, never take a default
const Patch = z.object({ name: AccountName.optional(), notes: z.string().max(500).optional() });

export async function accountRoutes(app: FastifyInstance, { db, config, bus }: AppContext) {
  const changed = () => bus.emit({ type: "accounts" });

  app.get("/api/accounts", async () => listAccounts(db, config.envAccount));

  app.post("/api/accounts", async (req) => {
    const body = parse(AccountBody, req.body);
    const id = await createAccount(db, config.dataDir, body.name, body.notes);
    changed();
    return { id };
  });

  app.patch("/api/accounts/:id", async (req, reply) => {
    const { id } = parse(Id, req.params);
    const body = parse(Patch, req.body);
    await updateAccount(db, config.dataDir, id, body);
    changed();
    // a rename re-tags history: every view of sessions changed
    if (body.name !== undefined) bus.emit({ type: "sessions", ids: [] });
    return ok(reply);
  });

  app.delete("/api/accounts/:id", async (req, reply) => {
    await deleteAccount(db, config.dataDir, parse(Id, req.params).id);
    changed();
    return ok(reply);
  });

  app.post("/api/accounts/:id/activate", async (req, reply) => {
    await setActive(db, config.dataDir, parse(Id, req.params).id);
    changed();
    return ok(reply);
  });

  app.post("/api/accounts/deactivate", async (_req, reply) => {
    await setActive(db, config.dataDir, null);
    changed();
    return ok(reply);
  });
}
