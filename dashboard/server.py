"""
Local HTTP server for the dashboard — stdlib only, bound to 127.0.0.1.

Every /api call must carry the random per-run token baked into the served page
(X-Token header) and a localhost Host header, so another website open in the
same browser can't read stats or the vault (CSRF / DNS rebinding).
The vault locks itself after AUTO_LOCK seconds without a vault request.
"""
import json, os, secrets, threading, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import lib.accounts as accounts
import lib.logreport as logreport
from dashboard import stats
from dashboard.vault import Vault, WrongPassword

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
AUTO_LOCK = 10 * 60
MAX_BODY = 64 * 1024


class App:
    def __init__(self, root=None, vault=None):
        self.root = root or logreport.ROOT
        self.vault = vault or Vault()
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.Lock()
        self.vault_used = 0.0

    # ── stats + accounts ────────────────────────────────────────────────────
    def overview(self):
        summaries, _, _ = logreport.load_sessions(self.root)
        data = accounts.load(self.root)
        out = stats.build(summaries, data["accounts"], datetime.now())
        out["active"] = accounts.active(self.root)
        out["account_notes"] = {a["name"]: a.get("notes", "") for a in data["accounts"]}
        out["env_override"] = bool(os.environ.get(accounts.ENV_VAR))
        return out

    def save_account(self, body):
        name, old = _name(body.get("name")), body.get("old") or None
        data = accounts.load(self.root)
        names = [a["name"] for a in data["accounts"]]
        if name in names and name != old:
            raise ValueError(f"account {name!r} already exists")
        if old in names and old != name:
            self._need_unlocked("rename")
        entry = {"name": name, "notes": str(body.get("notes", ""))[:500]}
        if old in names:
            data["accounts"][names.index(old)] = entry
            if data["active"] == old:
                data["active"] = name
            if old != name and self.vault.exists():
                self.vault.rename(old, name)
        else:
            data["accounts"].append(entry)
        if not data["active"]:
            data["active"] = name
        accounts.save(data, self.root)

    def delete_account(self, body):
        name = body.get("name")
        self._need_unlocked("delete")
        data = accounts.load(self.root)
        data["accounts"] = [a for a in data["accounts"] if a["name"] != name]
        if data["active"] == name:
            data["active"] = data["accounts"][0]["name"] if data["accounts"] else None
        accounts.save(data, self.root)
        if self.vault.exists():
            self.vault.delete(name)

    def set_active(self, body):
        data = accounts.load(self.root)
        name = body.get("name") or None
        if name is not None and name not in [a["name"] for a in data["accounts"]]:
            raise ValueError(f"unknown account {name!r}")
        data["active"] = name
        accounts.save(data, self.root)

    def _need_unlocked(self, what):
        """Renaming/deleting with a locked vault would orphan the stored login."""
        if self.vault.exists() and not self.vault_status()["unlocked"]:
            raise WrongPassword(f"unlock the vault to {what} an account (its login moves with it)")
        self.vault_used = time.time()

    # ── vault ────────────────────────────────────────────────────────────────
    def vault_status(self):
        if self.vault.unlocked and time.time() - self.vault_used > AUTO_LOCK:
            self.vault.lock()
        return {"exists": self.vault.exists(), "unlocked": self.vault.unlocked,
                "auto_lock": AUTO_LOCK}

    def vault_call(self, fn):
        self.vault_status()            # applies the auto-lock first
        out = fn()
        self.vault_used = time.time()
        return out


def _name(value):
    name = str(value or "").strip()
    if not name or len(name) > 32:
        raise ValueError("account name must be 1-32 characters")
    return name


def _routes(app):
    v = app.vault
    return {
        ("GET", "/api/overview"):      lambda b: app.overview(),
        ("POST", "/api/account"):      lambda b: app.save_account(b),
        ("POST", "/api/account/delete"): lambda b: app.delete_account(b),
        ("POST", "/api/active"):       lambda b: app.set_active(b),
        ("GET", "/api/vault"):         lambda b: app.vault_status(),
        ("POST", "/api/vault/unlock"): lambda b: app.vault_call(lambda: v.unlock(str(b.get("master", "")))),
        ("POST", "/api/vault/lock"):   lambda b: v.lock(),
        ("POST", "/api/vault/list"):   lambda b: app.vault_call(
            lambda: {k: {"email": e["email"], "notes": e.get("notes", ""), "has_password": bool(e["password"])}
                     for k, e in v.entries().items()}),
        ("POST", "/api/vault/reveal"): lambda b: app.vault_call(
            lambda: {"password": v.entries().get(b.get("name"), {}).get("password", "")}),
        ("POST", "/api/vault/set"):    lambda b: app.vault_call(
            lambda: v.set(_name(b.get("name")), str(b.get("email", "")),
                          None if b.get("password") is None else str(b["password"]),
                          str(b.get("notes", ""))[:500])),
        ("POST", "/api/vault/master"): lambda b: app.vault_call(lambda: v.change_master(str(b.get("master", "")))),
    }


def make_handler(app, port):
    routes = _routes(app)
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "runetools-dashboard"

        def log_message(self, fmt, *args):   # quiet; errors still go to the response
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def _handle(self, method):
            if self.headers.get("Host") not in hosts:
                return self._send(403, {"error": "bad host"})
            path = self.path.split("?", 1)[0]
            if method == "GET" and path in ("/", "/index.html"):
                with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
                    page = f.read().replace("__TOKEN__", app.token)
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            route = routes.get((method, path))
            if route is None:
                return self._send(404, {"error": "not found"})
            if not secrets.compare_digest(self.headers.get("X-Token", ""), app.token):
                return self._send(403, {"error": "bad token"})
            body = {}
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self._send(413, {"error": "too large"})
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._send(400, {"error": "bad json"})
                if not isinstance(body, dict):
                    return self._send(400, {"error": "bad json"})
            try:
                with app.lock:
                    out = route(body)
            except WrongPassword as e:
                return self._send(401, {"error": str(e)})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            self._send(200, out if out is not None else {"ok": True})

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return Handler


def serve(port, app=None):
    app = app or App()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    # port 0 picks a free one: the Host check needs the real port
    httpd.RequestHandlerClass = make_handler(app, httpd.server_address[1])
    return httpd, app
