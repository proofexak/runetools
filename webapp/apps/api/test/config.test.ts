import { afterEach, describe, expect, it } from "vitest";
import { loadConfig } from "../src/config.js";
import { makeApp, type TestApp } from "./helpers.js";

describe("PUBLIC_HOST (reaching the app from another device, e.g. over Tailscale)", () => {
  let t: TestApp | undefined;
  afterEach(async () => { await t?.close(); });

  it("is accepted next to the local hosts, or next to ALLOWED_HOSTS", () => {
    expect(loadConfig({ PUBLIC_HOST: "My-PC.tail1234.ts.net" }).allowedHosts)
      .toEqual(["127.0.0.1:8778", "localhost:8778", "my-pc.tail1234.ts.net"]);
    expect(loadConfig({ ALLOWED_HOSTS: "127.0.0.1:8778,webapp:8778", PUBLIC_HOST: "a.ts.net, b.ts.net:8443" }).allowedHosts)
      .toEqual(["127.0.0.1:8778", "webapp:8778", "a.ts.net", "b.ts.net:8443"]);
    expect(loadConfig({}).allowedHosts).toEqual(["127.0.0.1:8778", "localhost:8778"]);
  });

  it("lets a browser on that name log in; other names stay refused", async () => {
    t = await makeApp({ allowedHosts: loadConfig({ PUBLIC_HOST: "my-pc.tail1234.ts.net" }).allowedHosts });
    const setup = (host: string, origin: string) => t!.app.inject({
      method: "POST", url: "/api/auth/setup", headers: { host, origin },
      payload: { username: "admin", password: "correct horse" },
    });
    expect((await setup("evil.example", "https://evil.example")).statusCode).toBe(403);
    expect((await setup("my-pc.tail1234.ts.net", "https://evil.example")).statusCode).toBe(403);
    expect((await setup("my-pc.tail1234.ts.net", "https://my-pc.tail1234.ts.net")).statusCode).toBe(200);
  });
});
