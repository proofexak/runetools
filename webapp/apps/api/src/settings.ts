import { eq } from "drizzle-orm";
import type { Config } from "./config.js";
import type { Db } from "./db/index.js";
import { settings } from "./db/schema.js";

/** Watched log directories: Settings page value, else LOG_ROOTS / the repo. */
export async function getLogRoots(db: Db, config: Config): Promise<string[]> {
  const [row] = await db.select().from(settings).where(eq(settings.key, "logRoots"));
  const value = row?.value;
  return Array.isArray(value) && value.length && value.every((v) => typeof v === "string") ? value : config.logRoots;
}

export async function setLogRoots(db: Db, roots: string[]) {
  await db.insert(settings).values({ key: "logRoots", value: roots })
    .onConflictDoUpdate({ target: settings.key, set: { value: roots } });
}
