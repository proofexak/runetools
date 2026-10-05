import { ChangeMasterBody, LoginEntry, MasterBody, NewMasterBody } from "@runetools/shared";
import { eq } from "drizzle-orm";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import type { AppContext } from "../app.js";
import { verifyPassword } from "../auth/auth.js";
import { accounts, users } from "../db/schema.js";
import { HttpError, ok, parse, passwordLimited } from "../http.js";

const Id = z.object({ id: z.coerce.number().int().positive() });
const ResetBody = z.object({ password: z.string().min(1).max(256) });

export async function vaultRoutes(app: FastifyInstance, { db, vault, config }: AppContext) {
  const LIMITED = passwordLimited(config.passwordRateLimit);
  const account = async (id: number) => {
    const [row] = await db.select({ id: accounts.id }).from(accounts).where(eq(accounts.id, id));
    if (!row) throw new HttpError(404, "no such account");
    return row.id;
  };

  app.get("/api/vault", async () => vault.status());

  app.post("/api/vault/setup", LIMITED, async (req, reply) => {
    await vault.create(parse(NewMasterBody, req.body).master);
    return ok(reply);
  });

  app.post("/api/vault/unlock", LIMITED, async (req, reply) => {
    await vault.unlock(parse(MasterBody, req.body).master);
    return ok(reply);
  });

  app.post("/api/vault/lock", async (_req, reply) => {
    vault.lock();
    return ok(reply);
  });

  app.get("/api/vault/entries/:id", async (req) => {
    const entry = await vault.get(await account(parse(Id, req.params).id));
    if (!entry) throw new HttpError(404, "no login stored for this account");
    return entry;
  });

  app.put("/api/vault/entries/:id", async (req, reply) => {
    const id = await account(parse(Id, req.params).id);
    await vault.set(id, parse(LoginEntry, req.body));
    return ok(reply);
  });

  app.delete("/api/vault/entries/:id", async (req, reply) => {
    await vault.remove(await account(parse(Id, req.params).id));
    return ok(reply);
  });

  app.post("/api/vault/master", LIMITED, async (req, reply) => {
    const body = parse(ChangeMasterBody, req.body);
    await vault.changeMaster(body.current, body.next);
    return ok(reply);
  });

  // forgotten master password: wipe the stored logins. Needs the app password.
  app.post("/api/vault/reset", LIMITED, async (req, reply) => {
    const { password } = parse(ResetBody, req.body);
    const [user] = await db.select().from(users).where(eq(users.id, req.auth!.userId));
    if (!user || !(await verifyPassword(user.passwordHash, password))) throw new HttpError(401, "app password is wrong");
    await vault.reset();
    return ok(reply);
  });
}
