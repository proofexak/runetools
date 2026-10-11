/**
 * Failure screenshots (PRO-91): the bots save a PNG next to the session log when a step
 * fails or the session records an error, and name it in that event (steps.screenshot /
 * errors.screenshot). The API reads one only when every check holds:
 *   - the name is a plain file name ending in .png (no folder, no "..", no NUL);
 *   - that session recorded exactly this name on one of its steps or errors;
 *   - the session's log is one the ingester would read under today's log roots;
 *   - the PNG's real path (symlinks resolved) is a file directly in that log's real folder.
 * So the route can't be pointed at any other file on the machine, whatever a log line says.
 */
import fs from "node:fs/promises";
import path from "node:path";
import { and, eq, sql } from "drizzle-orm";
import type { Db } from "./db/index.js";
import { errors, sessions, steps } from "./db/schema.js";
import { findLogFiles } from "./ingest/ingester.js";

export const SCREENSHOT_NAME = /^[A-Za-z0-9_-][A-Za-z0-9_.-]*\.png$/;
const MAX_BYTES = 32 * 1024 * 1024;

/** Absolute path of session `id`'s screenshot `name`, or null when it may not be served. */
export async function screenshotFile(db: Db, roots: string[], id: number, name: string): Promise<string | null> {
  if (name.length > 255 || !SCREENSHOT_NAME.test(name)) return null;
  const [row] = await db.select({ file: sessions.file }).from(sessions).where(eq(sessions.id, id));
  if (!row) return null;
  const [recorded] = await db.select({ n: sql<number>`1` }).from(steps)
    .where(and(eq(steps.sessionId, id), eq(steps.screenshot, name)))
    .union(db.select({ n: sql<number>`1` }).from(errors)
      .where(and(eq(errors.sessionId, id), eq(errors.screenshot, name))))
    .limit(1);
  if (!recorded) return null;
  const log = (await findLogFiles(roots)).find((f) => f.key === row.file);
  if (!log) return null;
  try {
    const dir = await fs.realpath(path.dirname(log.abs));
    const real = await fs.realpath(path.join(dir, name));
    if (path.dirname(real) !== dir) return null;
    const stat = await fs.stat(real);
    return stat.isFile() && stat.size <= MAX_BYTES ? real : null;
  } catch {
    return null;
  }
}
