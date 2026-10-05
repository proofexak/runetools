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
import { HttpError } from "./http.js";

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

type Tx = Parameters<Parameters<Db["transaction"]>[0]>[0];

/**
 * Runs an accounts change and rewrites data/active_account inside the same transaction:
 * if the file can't be written, nothing changes and the caller gets the error.
 */
export async function changeAccounts(db: Db, dataDir: string, change: (tx: Tx) => Promise<void>) {
  await db.transaction(async (tx) => {
    await change(tx);
    const [row] = await tx.select({ name: accounts.name }).from(accounts).where(eq(accounts.active, true));
    try {
      await writeActiveFile(dataDir, row?.name ?? null);
    } catch (err) {
      throw new HttpError(500, `couldn't write ${path.join(dataDir, "active_account")}: ${(err as Error).message}`);
    }
  });
}

export async function createAccount(db: Db, dataDir: string, name: string, notes: string): Promise<number> {
  let id = 0;
  await changeAccounts(db, dataDir, async (tx) => {
    await assertFree(tx, name);
    const [{ n }] = (await tx.select({ n: sql<number>`count(*)::int` }).from(accounts).where(eq(accounts.active, true))) as [{ n: number }];
    // the first account becomes the active one, as the prototype did
    const [row] = await tx.insert(accounts).values({ name, notes, active: n === 0 }).returning({ id: accounts.id });
    id = row!.id;
  });
  return id;
}

/** Rename and/or edit notes. A rename carries the session history along (sessions.account). */
export async function updateAccount(db: Db, dataDir: string, id: number, patch: { name?: string; notes?: string }) {
  await changeAccounts(db, dataDir, async (tx) => {
    const [cur] = await tx.select().from(accounts).where(eq(accounts.id, id));
    if (!cur) throw new HttpError(404, "no such account");
    if (patch.name !== undefined && patch.name !== cur.name) {
      await assertFree(tx, patch.name);
      await tx.update(sessions).set({ account: patch.name }).where(eq(sessions.account, cur.name));
    }
    await tx.update(accounts).set({ name: patch.name ?? cur.name, notes: patch.notes ?? cur.notes }).where(eq(accounts.id, id));
  });
}

/** Deletes the account and its stored login. Its sessions keep the name (they show as an old account). */
export async function deleteAccount(db: Db, dataDir: string, id: number) {
  await changeAccounts(db, dataDir, async (tx) => {
    const gone = await tx.delete(accounts).where(eq(accounts.id, id)).returning({ id: accounts.id });
    if (gone.length === 0) throw new HttpError(404, "no such account");
  });
}

/** id = null: no active account, new sessions are logged without one. */
export async function setActive(db: Db, dataDir: string, id: number | null) {
  await changeAccounts(db, dataDir, async (tx) => {
    await tx.update(accounts).set({ active: false }).where(eq(accounts.active, true));
    if (id === null) return;
    const done = await tx.update(accounts).set({ active: true }).where(eq(accounts.id, id)).returning({ id: accounts.id });
    if (done.length === 0) throw new HttpError(404, "no such account");
  });
}

async function assertFree(tx: Tx, name: string) {
  const [taken] = await tx.select({ id: accounts.id }).from(accounts).where(eq(accounts.name, name));
  if (taken) throw new HttpError(409, `there is already an account called ${name}`);
}
