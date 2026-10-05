import { eq } from "drizzle-orm";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { credentials, vaultMeta } from "../src/db/schema.js";
import { deriveKey, newSalt, open, recordAad, seal } from "../src/vault/crypto.js";
import { Vault } from "../src/vault/vault.js";
import { login, makeApp, TEST_KDF, type Client, type TestApp } from "./helpers.js";

let t: TestApp;
let c: Client;
const login1 = { email: "zezima@example.com", password: "hunter2", notes: "bank pin 1234" };

beforeEach(async () => {
  t = await makeApp();
  c = await login(t.app);
  await c.post("/api/accounts", { name: "Zezima" });
  await c.post("/api/accounts", { name: "Lynx Titan" });
});
afterEach(async () => { await t.close(); });

const status = async () => (await c.get("/api/vault")).json();

describe("crypto", () => {
  it("round-trips, and fails on a wrong key or a moved record", async () => {
    const key = await deriveKey("master", newSalt(), TEST_KDF);
    const s = seal(key, "secret", recordAad(1));
    expect(s.nonce).toHaveLength(12);
    expect(open(key, s.ciphertext, s.nonce, recordAad(1))).toBe("secret");
    expect(() => open(key, s.ciphertext, s.nonce, recordAad(2))).toThrow();
    const other = await deriveKey("other", newSalt(), TEST_KDF);
    expect(() => open(other, s.ciphertext, s.nonce, recordAad(1))).toThrow();
  });

  it("derives the same key from the same password + salt only", async () => {
    const salt = newSalt();
    expect((await deriveKey("a", salt, TEST_KDF)).equals(await deriveKey("a", salt, TEST_KDF))).toBe(true);
    expect((await deriveKey("a", salt, TEST_KDF)).equals(await deriveKey("a", newSalt(), TEST_KDF))).toBe(false);
  });
});

describe("vault", () => {
  it("is created with a master password and starts unlocked", async () => {
    expect(await status()).toEqual({ exists: false, unlocked: false, autoLockSeconds: 600 });
    expect((await c.post("/api/vault/setup", { master: "short" })).statusCode).toBe(400);
    expect((await c.post("/api/vault/setup", { master: "correct horse" })).statusCode).toBe(200);
    expect(await status()).toMatchObject({ exists: true, unlocked: true });
    expect((await c.post("/api/vault/setup", { master: "again again" })).statusCode).toBe(409);
  });

  it("stores, shows and edits a login; only ciphertext reaches the database", async () => {
    await c.post("/api/vault/setup", { master: "correct horse" });
    expect((await c.send("PUT", "/api/vault/entries/1", login1)).statusCode).toBe(200);
    expect((await c.get("/api/vault/entries/1")).json()).toEqual(login1);
    expect((await c.get("/api/vault/entries/2")).statusCode).toBe(404);
    expect((await c.get("/api/accounts")).json().accounts.find((a: { id: number }) => a.id === 1).hasLogin).toBe(true);

    const [row] = await t.ctx.db.select().from(credentials).where(eq(credentials.accountId, 1));
    const raw = row!.ciphertext.toString("latin1");
    for (const secret of [login1.email, login1.password, login1.notes]) expect(raw).not.toContain(secret);

    await c.send("PUT", "/api/vault/entries/1", { ...login1, password: "hunter3" });
    expect((await c.get("/api/vault/entries/1")).json().password).toBe("hunter3");
    expect((await c.send("DELETE", "/api/vault/entries/1")).statusCode).toBe(200);
    expect((await c.get("/api/vault/entries/1")).statusCode).toBe(404);
  });

  it("locked: nothing readable or writable until unlocked with the right password", async () => {
    await c.post("/api/vault/setup", { master: "correct horse" });
    await c.send("PUT", "/api/vault/entries/1", login1);
    await c.post("/api/vault/lock");
    expect(await status()).toMatchObject({ exists: true, unlocked: false });
    expect((await c.get("/api/vault/entries/1")).statusCode).toBe(423);
    expect((await c.send("PUT", "/api/vault/entries/2", login1)).statusCode).toBe(423);
    expect((await c.post("/api/vault/unlock", { master: "wrong one" })).statusCode).toBe(401);
    expect((await c.post("/api/vault/unlock", { master: "correct horse" })).statusCode).toBe(200);
    expect((await c.get("/api/vault/entries/1")).json()).toEqual(login1);
  });

  it("a restart (new process) starts locked; the key is never stored", async () => {
    await c.post("/api/vault/setup", { master: "correct horse" });
    await c.send("PUT", "/api/vault/entries/1", login1);
    const fresh = new Vault(t.ctx.db, undefined, undefined, TEST_KDF);
    expect((await fresh.status()).unlocked).toBe(false);
    await fresh.unlock("correct horse");
    expect(await fresh.get(1)).toEqual(login1);
    fresh.lock();
    const [meta] = await t.ctx.db.select().from(vaultMeta);
    expect(Object.keys(meta!).sort()).toEqual(["checkCiphertext", "checkNonce", "createdAt", "id", "kdf", "salt"]);
  });

  it("locks itself after the idle timeout and on logout", async () => {
    const v = new Vault(t.ctx.db, t.ctx.bus, 50, TEST_KDF);
    const events: unknown[] = [];
    t.ctx.bus.on((e) => events.push(e));
    await v.create("correct horse");
    expect((await v.status()).unlocked).toBe(true);
    await new Promise((r) => setTimeout(r, 120));
    expect((await v.status()).unlocked).toBe(false);
    expect(events).toEqual([{ type: "vault", unlocked: true }, { type: "vault", unlocked: false }]);

    await c.post("/api/vault/setup", { master: "correct horse" });
    await c.post("/api/auth/logout");
    expect((await t.ctx.vault.status()).unlocked).toBe(false);
  });

  it("changing the master password re-encrypts every login", async () => {
    await c.post("/api/vault/setup", { master: "correct horse" });
    await c.send("PUT", "/api/vault/entries/1", login1);
    await c.send("PUT", "/api/vault/entries/2", { email: "lynx@example.com", password: "pw", notes: "" });
    expect((await c.post("/api/vault/master", { current: "nope nope", next: "battery staple" })).statusCode).toBe(401);
    expect((await c.post("/api/vault/master", { current: "correct horse", next: "battery staple" })).statusCode).toBe(200);
    await c.post("/api/vault/lock");
    expect((await c.post("/api/vault/unlock", { master: "correct horse" })).statusCode).toBe(401);
    expect((await c.post("/api/vault/unlock", { master: "battery staple" })).statusCode).toBe(200);
    expect((await c.get("/api/vault/entries/1")).json()).toEqual(login1);
    expect((await c.get("/api/vault/entries/2")).json().email).toBe("lynx@example.com");
  });

  it("a forgotten master password: reset wipes the logins, needs the app password", async () => {
    await c.post("/api/vault/setup", { master: "correct horse" });
    await c.send("PUT", "/api/vault/entries/1", login1);
    expect((await c.post("/api/vault/reset", { password: "wrong" })).statusCode).toBe(401);
    expect((await c.post("/api/vault/reset", { password: "correct horse" })).statusCode).toBe(200);
    expect(await status()).toMatchObject({ exists: false, unlocked: false });
    expect(await t.ctx.db.select().from(credentials)).toEqual([]);
  });

  it("deleting an account deletes its stored login", async () => {
    await c.post("/api/vault/setup", { master: "correct horse" });
    await c.send("PUT", "/api/vault/entries/1", login1);
    await c.send("DELETE", "/api/accounts/1");
    expect(await t.ctx.db.select().from(credentials)).toEqual([]);
    expect((await c.send("PUT", "/api/vault/entries/1", login1)).statusCode).toBe(404);
  });

  it("needs a logged-in user and CSRF token", async () => {
    await c.post("/api/vault/setup", { master: "correct horse" });
    const res = await t.app.inject({ method: "GET", url: "/api/vault/entries/1", headers: { host: "127.0.0.1:8778" } });
    expect(res.statusCode).toBe(401);
    const noCsrf = await t.app.inject({ method: "POST", url: "/api/vault/lock", headers: { host: "127.0.0.1:8778" },
      cookies: { rt_session: c.cookie } });
    expect(noCsrf.statusCode).toBe(403);
  });
});
