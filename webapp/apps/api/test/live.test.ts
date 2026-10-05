import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type WebSocket from "ws";
import { HOST, login, makeApp, type Client, type TestApp } from "./helpers.js";

let t: TestApp;
let c: Client;
let vnc: net.Server;
let vncPort: number;

/** Stands in for x11vnc: greets like RFB, then echoes. */
function fakeVnc(): Promise<net.Server> {
  const server = net.createServer((sock) => {
    sock.write("RFB 003.008\n");
    sock.on("data", (d) => sock.write(d));
    sock.on("error", () => {});
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

beforeEach(async () => {
  vnc = await fakeVnc();
  vncPort = (vnc.address() as net.AddressInfo).port;
  t = await makeApp({ vnc: { host: "127.0.0.1", port: vncPort }, vncPassword: "s3cret" });
  c = await login(t.app);
});
afterEach(async () => {
  await t.close();
  await new Promise((r) => vnc.close(r));
});

const file = (name: string) => path.join(t.ctx.config.dataDir, name);
const readRequest = () => JSON.parse(fs.readFileSync(file("live_control.json"), "utf8"));
/** What lib/live_control.py writes back. */
const ack = (data: object) => fs.writeFileSync(file("live_control_ack.json"), JSON.stringify(data));

const nextMessage = (ws: WebSocket) => new Promise<string>((resolve) => ws.once("message", (d) => resolve(String(d))));
const closed = (ws: WebSocket) => new Promise<number>((resolve) => ws.once("close", (code) => resolve(code)));
const connect = (headers: Record<string, string> = {}) => t.app.injectWS("/api/live/vnc", {
  headers: { host: HOST, cookie: `rt_session=${c.cookie}`, origin: `http://${HOST}`, ...headers },
});

describe("live view", () => {
  it("hands the VNC password to a logged-in page only", async () => {
    expect((await t.app.inject({ url: "/api/live/config", headers: { host: HOST } })).statusCode).toBe(401);
    expect((await c.get("/api/live/config")).json()).toEqual({ password: "s3cret" });
  });

  it("bridges the WebSocket to VNC both ways", async () => {
    const ws = await connect();
    const greeting = nextMessage(ws);
    expect(await greeting).toBe("RFB 003.008\n");
    const echo = nextMessage(ws);
    ws.send(Buffer.from("RFB 003.008\n"));
    expect(await echo).toBe("RFB 003.008\n");
    const done = closed(ws);
    ws.close();
    await done;
  });

  it("refuses the stream without a login or from another site", async () => {
    await expect(connect({ cookie: "" })).rejects.toThrow(/401/);
    await expect(connect({ origin: "http://evil.example" })).rejects.toThrow(/403/);
  });

  it("closes the socket when VNC can't be reached", async () => {
    await new Promise((r) => vnc.close(r));
    vnc = await fakeVnc();          // a different port; the configured one is now dead
    const ws = await connect();
    expect(await closed(ws)).toBe(1011);
  });
});

describe("take control", () => {
  it("starts released, with no request and no answer", async () => {
    expect((await c.get("/api/live/control")).json()).toEqual({ held: false, id: null, requestedAt: null, bot: null });
  });

  it("take writes the request for the bot; the answer counts only for that request", async () => {
    const res = await c.post("/api/live/control", { action: "take" });
    expect(res.statusCode).toBe(200);
    const req = readRequest();
    expect(req).toMatchObject({ held: true });
    expect(res.json()).toMatchObject({ held: true, id: req.id, bot: null });

    ack({ id: "an-older-request", held: true, safe: true });
    expect((await c.get("/api/live/control")).json().bot).toBeNull();

    ack({ id: req.id, held: true, safe: false });        // pausing: a step still runs
    expect((await c.get("/api/live/control")).json().bot).toEqual({ held: true, safe: false });
    ack({ id: req.id, held: true, safe: true });
    expect((await c.get("/api/live/control")).json().bot).toEqual({ held: true, safe: true });
  });

  it("release writes a new request that hands control back", async () => {
    await c.post("/api/live/control", { action: "take" });
    const taken = readRequest();
    const res = (await c.post("/api/live/control", { action: "release" })).json();
    const released = readRequest();
    expect(released.held).toBe(false);
    expect(released.id).not.toBe(taken.id);
    expect(res).toMatchObject({ held: false, id: released.id, bot: null });
  });

  it("validates the action and needs the CSRF token", async () => {
    expect((await c.post("/api/live/control", { action: "steal" })).statusCode).toBe(400);
    const res = await t.app.inject({
      method: "POST", url: "/api/live/control", headers: { host: HOST }, cookies: { rt_session: c.cookie },
      payload: { action: "take" },
    });
    expect(res.statusCode).toBe(403);
  });
});
