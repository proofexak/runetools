/**
 * The bots' credential for POST /api/ingest (PRO-99). The app keeps a random token in
 * <DATA_DIR>/bot_token (gitignored, like active_account); lib/events.py reads it at every
 * session start and sends it as `Authorization: Bearer …`. An existing token is kept, so
 * bots that are already running keep pushing across an app restart.
 */
import { randomBytes } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { writeDataFile } from "./accounts.js";

const VALID = /^[0-9a-f]{64}$/;

export async function ensureBotToken(dataDir: string): Promise<string> {
  try {
    const existing = (await fs.readFile(path.join(dataDir, "bot_token"), "utf8")).trim();
    if (VALID.test(existing)) return existing;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
  }
  const token = randomBytes(32).toString("hex");
  await writeDataFile(dataDir, "bot_token", `${token}\n`, 0o600);
  return token;
}
