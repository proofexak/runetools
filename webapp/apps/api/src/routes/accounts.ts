import type { FastifyInstance } from "fastify";
import { listAccounts } from "../accounts.js";
import type { AppContext } from "../app.js";

export async function accountRoutes(app: FastifyInstance, { db, config }: AppContext) {
  app.get("/api/accounts", async () => listAccounts(db, config.envAccount));
}
