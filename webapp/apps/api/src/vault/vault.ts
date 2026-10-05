/**
 * The login vault. The key exists only in this process's memory while unlocked; it is
 * zeroed on lock, after AUTO_LOCK of no vault use, on logout and on restart. Nothing that
 * could recover it — the master password, the key — is ever written anywhere, so a
 * forgotten master password means the stored logins are gone (reset() wipes them).
 */
import { LoginEntry, type VaultStatus } from "@runetools/shared";
import { eq } from "drizzle-orm";
import type { Bus } from "../bus.js";
import type { Db } from "../db/index.js";
import { credentials, vaultMeta } from "../db/schema.js";
import { HttpError } from "../http.js";
import {
  CHECK_AAD, CHECK_PLAINTEXT, DEFAULT_KDF, deriveKey, newSalt, open, recordAad, seal, type KdfParams,
} from "./crypto.js";

export const AUTO_LOCK_MS = 10 * 60 * 1000;

export class Vault {
  private key: Buffer | null = null;
  private timer: NodeJS.Timeout | null = null;

  constructor(private db: Db, private bus?: Bus, private autoLockMs = AUTO_LOCK_MS, private kdf: KdfParams = DEFAULT_KDF) {}

  private async meta() {
    const [m] = await this.db.select().from(vaultMeta).where(eq(vaultMeta.id, 1));
    return m ?? null;
  }

  async status(): Promise<VaultStatus> {
    return { exists: (await this.meta()) !== null, unlocked: this.key !== null, autoLockSeconds: this.autoLockMs / 1000 };
  }

  /** First use: pick the master password. Leaves the vault unlocked. */
  async create(master: string) {
    if (await this.meta()) throw new HttpError(409, "the vault already exists");
    const salt = newSalt();
    const key = await deriveKey(master, salt, this.kdf);
    const check = seal(key, CHECK_PLAINTEXT, CHECK_AAD);
    await this.db.insert(vaultMeta).values({ salt, kdf: this.kdf, checkCiphertext: check.ciphertext, checkNonce: check.nonce });
    this.setKey(key);
  }

  async unlock(master: string) {
    const m = await this.meta();
    if (!m) throw new HttpError(409, "no vault yet: set a master password first");
    const key = await deriveKey(master, m.salt, m.kdf);
    if (!this.verify(key, m.checkCiphertext, m.checkNonce)) {
      key.fill(0);
      throw new HttpError(401, "wrong master password");
    }
    this.setKey(key);
  }

  lock() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    if (!this.key) return;
    this.key.fill(0);
    this.key = null;
    this.bus?.emit({ type: "vault", unlocked: false });
  }

  /** Account ids that have a stored login (readable while locked: says nothing secret). */
  async accountsWithLogin(): Promise<Set<number>> {
    const rows = await this.db.select({ id: credentials.accountId }).from(credentials);
    return new Set(rows.map((r) => r.id));
  }

  async get(accountId: number): Promise<LoginEntry | null> {
    const key = this.use();
    const [row] = await this.db.select().from(credentials).where(eq(credentials.accountId, accountId));
    if (!row) return null;
    return LoginEntry.parse(JSON.parse(open(key, row.ciphertext, row.nonce, recordAad(accountId))));
  }

  async set(accountId: number, entry: LoginEntry) {
    const key = this.use();
    const { ciphertext, nonce } = seal(key, JSON.stringify(entry), recordAad(accountId));
    await this.db.insert(credentials).values({ accountId, ciphertext, nonce })
      .onConflictDoUpdate({ target: credentials.accountId, set: { ciphertext, nonce, updatedAt: new Date() } });
  }

  async remove(accountId: number) {
    this.use();
    await this.db.delete(credentials).where(eq(credentials.accountId, accountId));
  }

  /** Re-encrypts every login under a key from the new password, in one transaction. */
  async changeMaster(current: string, next: string) {
    const m = await this.meta();
    if (!m) throw new HttpError(409, "no vault yet");
    const oldKey = await deriveKey(current, m.salt, m.kdf);
    if (!this.verify(oldKey, m.checkCiphertext, m.checkNonce)) throw new HttpError(401, "current master password is wrong");
    const salt = newSalt();
    const newKey = await deriveKey(next, salt, this.kdf);
    const check = seal(newKey, CHECK_PLAINTEXT, CHECK_AAD);
    await this.db.transaction(async (tx) => {
      for (const row of await tx.select().from(credentials)) {
        const aad = recordAad(row.accountId);
        const sealed = seal(newKey, open(oldKey, row.ciphertext, row.nonce, aad), aad);
        await tx.update(credentials).set({ ...sealed, updatedAt: new Date() }).where(eq(credentials.id, row.id));
      }
      await tx.update(vaultMeta).set({ salt, kdf: this.kdf, checkCiphertext: check.ciphertext, checkNonce: check.nonce })
        .where(eq(vaultMeta.id, 1));
    });
    oldKey.fill(0);
    this.setKey(newKey);
  }

  /** Forgotten master password: delete every stored login and the vault itself. */
  async reset() {
    this.lock();
    await this.db.transaction(async (tx) => {
      await tx.delete(credentials);
      await tx.delete(vaultMeta);
    });
  }

  private verify(key: Buffer, ciphertext: Buffer, nonce: Buffer): boolean {
    try {
      return open(key, ciphertext, nonce, CHECK_AAD) === CHECK_PLAINTEXT;
    } catch {
      return false;
    }
  }

  private setKey(key: Buffer) {
    const was = this.key !== null;
    if (this.key && this.key !== key) this.key.fill(0);
    this.key = key;
    this.touch();
    if (!was) this.bus?.emit({ type: "vault", unlocked: true });
  }

  /** The key for one operation; restarts the idle clock. */
  private use(): Buffer {
    if (!this.key) throw new HttpError(423, "the vault is locked");
    this.touch();
    return this.key;
  }

  private touch() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => this.lock(), this.autoLockMs);
    this.timer.unref();
  }
}
