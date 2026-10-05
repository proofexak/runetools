/**
 * App login: one or more users with argon2id password hashes, and server-side sessions
 * keyed by sha256(cookie token). Each session carries a CSRF token the client echoes in
 * the x-csrf-token header on every mutating request.
 */
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { hash, verify } from "@node-rs/argon2";
import { and, count, eq, gt, lt } from "drizzle-orm";
import type { Db } from "../db/index.js";
import { authSessions, users } from "../db/schema.js";

export const COOKIE = "rt_session";
export const SESSION_TTL_MS = 30 * 24 * 3600 * 1000;

// argon2id, OWASP's minimum-memory profile is 19 MiB / t=2; a bit above that.
const HASH_OPTS = { memoryCost: 32 * 1024, timeCost: 3, parallelism: 1 } as const;

export const hashPassword = (password: string) => hash(password, HASH_OPTS);

export async function verifyPassword(phc: string, password: string): Promise<boolean> {
  try {
    return await verify(phc, password);
  } catch {
    return false;
  }
}

const sha256 = (token: string) => createHash("sha256").update(token).digest("hex");
const token = () => randomBytes(32).toString("base64url");

export function safeEqual(a: string, b: string): boolean {
  const x = Buffer.from(a), y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export async function userCount(db: Db): Promise<number> {
  const [row] = await db.select({ n: count() }).from(users);
  return row?.n ?? 0;
}

export async function createUser(db: Db, username: string, password: string) {
  const [row] = await db.insert(users).values({ username, passwordHash: await hashPassword(password) })
    .returning({ id: users.id });
  return row!.id;
}

// A real hash to verify against when the user doesn't exist, so timing doesn't tell.
let dummyHash: Promise<string> | null = null;

export async function checkLogin(db: Db, username: string, password: string): Promise<number | null> {
  const [user] = await db.select().from(users).where(eq(users.username, username));
  if (!user) {
    dummyHash ??= hashPassword("not-a-real-password");
    await verifyPassword(await dummyHash, password);
    return null;
  }
  return (await verifyPassword(user.passwordHash, password)) ? user.id : null;
}

export async function setPassword(db: Db, userId: number, password: string) {
  await db.update(users).set({ passwordHash: await hashPassword(password) }).where(eq(users.id, userId));
}

/** New session → the cookie value (only its hash is stored). */
export async function startSession(db: Db, userId: number): Promise<string> {
  const value = token();
  await db.delete(authSessions).where(lt(authSessions.expiresAt, new Date()));
  await db.insert(authSessions).values({
    id: sha256(value), userId, csrf: token(), expiresAt: new Date(Date.now() + SESSION_TTL_MS),
  });
  return value;
}

export interface AuthedSession { userId: number; username: string; csrf: string; sid: string }

export async function lookupSession(db: Db, cookie: string | undefined): Promise<AuthedSession | null> {
  if (!cookie) return null;
  const sid = sha256(cookie);
  const [row] = await db
    .select({ userId: authSessions.userId, csrf: authSessions.csrf, username: users.username })
    .from(authSessions)
    .innerJoin(users, eq(users.id, authSessions.userId))
    .where(and(eq(authSessions.id, sid), gt(authSessions.expiresAt, new Date())));
  return row ? { ...row, sid } : null;
}

export async function endSession(db: Db, sid: string) {
  await db.delete(authSessions).where(eq(authSessions.id, sid));
}

/** After a password change: every other browser has to log in again. */
export async function endOtherSessions(db: Db, userId: number, keepSid: string) {
  const rows = await db.select({ id: authSessions.id }).from(authSessions).where(eq(authSessions.userId, userId));
  for (const r of rows) if (r.id !== keepSid) await db.delete(authSessions).where(eq(authSessions.id, r.id));
}
