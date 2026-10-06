/**
 * Allowlist proxy in front of the Docker socket (PRO-90). The web app may start / stop the
 * bot container and read its state — nothing else: the socket itself is root on the host,
 * and the app can be on the internet (Tailscale Funnel). This runs as its own small
 * container (the only one holding /var/run/docker.sock) on the compose network, unpublished.
 *
 * Allowed, for the one configured container only (Docker API, optional /v1.xx prefix):
 *   GET  /containers/<name>/json
 *   POST /containers/<name>/start
 *   POST /containers/<name>/stop[?t=<seconds>]
 * Everything else gets 403 and never reaches Docker (no create, remove, exec, ...).
 */
import http from "node:http";

const VERSION = /^\/v\d+(?:\.\d+)?(?=\/)/;

/** Whether a request may reach Docker. Pure: method + raw URL + the allowed container name. */
export function allowRequest(method: string, url: string, container: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(url, "http://docker");
  } catch {
    return false;
  }
  const path = parsed.pathname.replace(VERSION, "");
  const m = /^\/containers\/([^/]+)\/(json|start|stop)$/.exec(path);
  if (!m) return false;
  let name: string;
  try {
    name = decodeURIComponent(m[1]!);
  } catch {
    return false;
  }
  if (name !== container) return false;
  const params = [...parsed.searchParams.keys()];
  switch (m[2]) {
    case "json":  return method === "GET" && params.length === 0;
    case "start": return method === "POST" && params.length === 0;
    case "stop":
      return method === "POST" && params.every((k) => k === "t") &&
        [...parsed.searchParams.values()].every((v) => /^\d{1,3}$/.test(v));
  }
  return false;
}

export interface ProxyOptions {
  container: string;
  /** Where Docker listens: its unix socket, or host/port (tests). */
  upstream: { socketPath: string } | { host: string; port: number };
}

export function createDockerProxy({ container, upstream }: ProxyOptions): http.Server {
  return http.createServer((req, res) => {
    const method = req.method ?? "GET";
    const url = req.url ?? "/";
    if (!allowRequest(method, url, container)) {
      req.resume();
      res.writeHead(403, { "content-type": "application/json" });
      res.end(JSON.stringify({ message: "not allowed by the runetools docker proxy" }));
      return;
    }
    req.resume();                                   // the allowed calls carry no body
    const out = http.request({ ...upstream, method, path: url, headers: { host: "docker", "content-length": "0" } },
      (up) => {
        res.writeHead(up.statusCode ?? 502, { "content-type": up.headers["content-type"] ?? "application/json" });
        up.pipe(res);
      });
    out.on("error", (err) => {
      if (!res.headersSent) res.writeHead(502, { "content-type": "application/json" });
      res.end(JSON.stringify({ message: `docker unreachable: ${err.message}` }));
    });
    out.end();
  });
}
