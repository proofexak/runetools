/**
 * Database handle: Postgres via postgres.js, or an embedded PGlite (same SQL, in-process)
 * when DATABASE_URL is "pglite:memory" / "pglite:<dir>" — used by tests and the e2e run.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { PgDatabase, PgQueryResultHKT } from "drizzle-orm/pg-core";
import * as schema from "./schema.js";

export type Db = PgDatabase<PgQueryResultHKT, typeof schema>;
export interface DbHandle { db: Db; close: () => Promise<void> }

// apps/api/drizzle, from src/db/ when run with tsx or from dist/ when bundled
const here = path.dirname(fileURLToPath(import.meta.url));
export const MIGRATIONS = process.env.MIGRATIONS_DIR ||
  [path.resolve(here, "../../drizzle"), path.resolve(here, "../drizzle")]
    .find((p) => fs.existsSync(path.join(p, "meta")))!;

export async function openDb(url: string, migrationsFolder = MIGRATIONS): Promise<DbHandle> {
  if (url.startsWith("pglite:")) {
    const { PGlite } = await import("@electric-sql/pglite");
    const { drizzle } = await import("drizzle-orm/pglite");
    const { migrate } = await import("drizzle-orm/pglite/migrator");
    const where = url.slice("pglite:".length);
    const client = new PGlite(where === "memory" ? undefined : where);
    const db = drizzle(client, { schema });
    await migrate(db, { migrationsFolder });
    return { db: db as unknown as Db, close: () => client.close() };
  }
  const { default: postgres } = await import("postgres");
  const { drizzle } = await import("drizzle-orm/postgres-js");
  const { migrate } = await import("drizzle-orm/postgres-js/migrator");
  const client = postgres(url, { max: 10, onnotice: () => {} });
  const db = drizzle(client, { schema });
  await migrate(db, { migrationsFolder });
  return { db: db as unknown as Db, close: () => client.end() };
}

export { schema };
