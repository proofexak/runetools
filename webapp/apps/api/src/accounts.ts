/**
 * Accounts and the active one. The active account is mirrored into <DATA_DIR>/active_account
 * (one line, the name) which lib/accounts.py reads at every session start — the bots never
 * talk to the API or the database.
 */
import fs from "node:fs/promises";
import path from "node:path";
import type { AccountsResponse } from "@runetools/shared";
import { asc, eq, sql } from "drizzle-orm";
import type { Db } from "./db/index.js";
import { accounts, credentials, sessions } from "./db/schema.js";

export async function listAccounts(db: Db, envOverride: string | null): Promise<AccountsResponse> {
  const [rows, tagged] = await Promise.all([
    db.select({
      id: accounts.id, name: accounts.name, notes: accounts.notes, active: accounts.active,
      hasLogin: sql<boolean>`${credentials.id} IS NOT NULL`,
    }).from(accounts).leftJoin(credentials, eq(credentials.accountId, accounts.id)).orderBy(asc(accounts.name)),
    db.selectDistinct({ account: sessions.account }).from(sessions),
  ]);
  const known = new Set(rows.map((r) => r.name));
  const names = tagged.map((t) => t.account);
  return {
    accounts: rows,
    envOverride,
    orphanNames: names.filter((n): n is string => !!n && !known.has(n)).sort(),
    hasUnassigned: names.some((n) => !n),
  };
}

export async function activeAccount(db: Db): Promise<string | null> {
  const [row] = await db.select({ name: accounts.name }).from(accounts).where(eq(accounts.active, true));
  return row?.name ?? null;
}

/** Write (or remove) data/active_account atomically, so a starting bot never reads half a name. */
export async function writeActiveFile(dataDir: string, name: string | null) {
  const file = path.join(dataDir, "active_account");
  if (name === null) {
    await fs.rm(file, { force: true });
    return;
  }
  await fs.mkdir(dataDir, { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  await fs.writeFile(tmp, `${name}\n`, "utf8");
  // Windows refuses to replace a file another process has open for a moment: retry briefly
  for (let attempt = 0; ; attempt++) {
    try {
      await fs.rename(tmp, file);
      return;
    } catch (err) {
      if (attempt >= 5 || (err as NodeJS.ErrnoException).code !== "EPERM") throw err;
      await new Promise((r) => setTimeout(r, 50));
    }
  }
}
