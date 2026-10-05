import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { HOST, login, makeApp, type TestApp } from "./helpers.js";

let t: TestApp;
beforeEach(async () => { t = await makeApp(); });
afterEach(async () => { await t.close(); });

const get = (url: string, headers: Record<string, string> = {}) =>
  t.app.inject({ url, headers: { host: HOST, ...headers } });

describe("auth", () => {
  it("health needs nothing", async () => {
    const res = await t.app.inject({ url: "/api/health", headers: { host: "evil.example" } });
    expect(res.json()).toEqual({ ok: true });
  });

  it("starts in setup state, then requires login", async () => {
    expect((await get("/api/auth/me")).json()).toEqual({ state: "setup" });
    await login(t.app);
    expect((await get("/api/auth/me")).json()).toEqual({ state: "anonymous" });
  });

  it("setup is refused once a user exists", async () => {
    await login(t.app);
    const res = await t.app.inject({ method: "POST", url: "/api/auth/setup", headers: { host: HOST },
      payload: { username: "mallory", password: "12345678" } });
    expect(res.statusCode).toBe(409);
  });

  it("sets an httpOnly SameSite=Strict cookie and reports the user", async () => {
    const res = await t.app.inject({ method: "POST", url: "/api/auth/setup", headers: { host: HOST },
      payload: { username: "admin", password: "correct horse" } });
    const c = res.cookies.find((x) => x.name === "rt_session")!;
    expect(c.httpOnly).toBe(true);
    expect(c.sameSite).toBe("Strict");
    const me = await t.app.inject({ url: "/api/auth/me", headers: { host: HOST }, cookies: { rt_session: c.value } });
    expect(me.json()).toMatchObject({ state: "authenticated", username: "admin" });
  });

  it("rejects a wrong password", async () => {
    await login(t.app);
    const res = await t.app.inject({ method: "POST", url: "/api/auth/login", headers: { host: HOST },
      payload: { username: "admin", password: "wrong" } });
    expect(res.statusCode).toBe(401);
    const res2 = await t.app.inject({ method: "POST", url: "/api/auth/login", headers: { host: HOST },
      payload: { username: "nobody", password: "wrong" } });
    expect(res2.statusCode).toBe(401);
  });

  it("short passwords are refused at setup", async () => {
    const res = await t.app.inject({ method: "POST", url: "/api/auth/setup", headers: { host: HOST },
      payload: { username: "admin", password: "short" } });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toMatch(/password/);
  });

  it("mutating routes need the CSRF token", async () => {
    const c = await login(t.app);
    const bad = await t.app.inject({ method: "POST", url: "/api/auth/logout", headers: { host: HOST },
      cookies: { rt_session: c.cookie } });
    expect(bad.statusCode).toBe(403);
    const good = await c.post("/api/auth/logout");
    expect(good.statusCode).toBe(200);
    expect((await c.get("/api/auth/me")).json()).toEqual({ state: "anonymous" });
  });

  it("rejects foreign Host and Origin headers", async () => {
    expect((await get("/api/auth/me", { host: "evil.example:8778" })).statusCode).toBe(403);
    const res = await t.app.inject({ method: "POST", url: "/api/auth/setup",
      headers: { host: HOST, origin: "http://evil.example" }, payload: { username: "a", password: "12345678" } });
    expect(res.statusCode).toBe(403);
  });

  it("sends anti-framing headers", async () => {
    const res = await get("/api/auth/me");
    expect(res.headers["x-frame-options"]).toBe("DENY");
    expect(res.headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  });

  it("changing the password logs out other browsers", async () => {
    const a = await login(t.app);
    const b = await login(t.app);
    const res = await a.post("/api/auth/password", { current: "correct horse", next: "battery staple" });
    expect(res.statusCode).toBe(200);
    expect((await a.get("/api/auth/me")).json().state).toBe("authenticated");
    expect((await b.get("/api/auth/me")).json().state).toBe("anonymous");
    await expect(login(t.app, "admin", "battery staple")).resolves.toBeTruthy();
  });
});
