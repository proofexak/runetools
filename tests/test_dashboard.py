"""Dashboard: pure stats, the encrypted vault, account tagging and the HTTP guard."""
import json, threading, urllib.error, urllib.request
from datetime import datetime

import pytest

import lib.accounts as accounts
import lib.events as events
import lib.pause as pause
import lib.session as session
from dashboard import stats, vault as vault_mod
from dashboard.server import App, serve
from dashboard.vault import Vault, WrongPassword

NOW = datetime(2026, 10, 5, 14, 0, 0)


def summ(start, end, active, runs=0, final="done", account="Main", bot="tanner"):
    return {"session": start, "bot": bot, "account": account, "start": start, "end": end,
            "active_seconds": active, "runs": runs, "final": final, "reason": None,
            "last_step": "bank", "errors": []}


# ── stats ─────────────────────────────────────────────────────────────────────

def test_session_over_midnight_is_split_by_wall_time():
    s = summ("2026-10-04T23:00:00", "2026-10-05T01:00:00", 7200, runs=10)
    days = stats.daily([s], datetime(2026, 10, 4).date(), datetime(2026, 10, 5).date())
    assert days["2026-10-04"]["hours"] == pytest.approx(1.0)
    assert days["2026-10-05"]["hours"] == pytest.approx(1.0)
    assert days["2026-10-05"]["runs"] == pytest.approx(5)
    assert days["2026-10-05"]["bots"] == {"tanner": pytest.approx(1.0)}


def test_overview_today_week_and_crashes():
    ss = [summ("2026-10-05T08:00:00", "2026-10-05T10:00:00", 5400, runs=40),
          summ("2026-10-01T08:00:00", "2026-10-01T09:00:00", 3600, final="crashed"),
          summ("2026-09-20T08:00:00", "2026-09-20T09:00:00", 3600, final="crashed")]   # > 7 days ago
    o = stats.overview(ss, NOW)
    assert o["today"]["hours"] == pytest.approx(1.5) and o["today"]["runs"] == 40
    assert o["today"]["sessions"] == 1
    assert o["week"]["hours"] == pytest.approx(2.5) and o["week"]["crashes"] == 1
    assert o["total_hours"] == pytest.approx(3.5)
    assert len(o["daily"]) == 14 and o["daily"][-1]["date"] == "2026-10-05"


def test_live_needs_no_session_end_and_recent_activity():
    running = summ("2026-10-05T13:00:00", "2026-10-05T13:50:00", 3000, final="killed")
    stale = summ("2026-10-05T09:00:00", "2026-10-05T10:00:00", 3600, final="killed")
    ended = summ("2026-10-05T13:00:00", "2026-10-05T13:59:00", 3540, final="stopped")
    rows = stats.live([running, stale, ended], NOW)
    assert [r["session"] for r in rows] == [running["session"]]
    assert rows[0]["final"] == "running" and rows[0]["idle_seconds"] == 600


def test_build_views_per_account_and_unassigned():
    ss = [summ("2026-10-05T08:00:00", "2026-10-05T09:00:00", 3600, account="Main"),
          summ("2026-10-05T10:00:00", "2026-10-05T11:00:00", 3600, account=None),
          summ("2026-10-05T11:00:00", "2026-10-05T12:00:00", 3600, account="OldAlt")]
    out = stats.build(ss, [{"name": "Main"}, {"name": "Fresh"}], NOW)
    assert out["accounts"] == ["Main", "Fresh", "OldAlt"] and out["unassigned"]
    assert out["views"]["*"]["today"]["hours"] == pytest.approx(3)
    assert out["views"]["Main"]["today"]["hours"] == pytest.approx(1)
    assert out["views"]["Fresh"]["today"]["hours"] == 0
    assert out["views"][""]["today"]["hours"] == pytest.approx(1)


# ── accounts / session tagging ────────────────────────────────────────────────

def test_active_account_file_env_and_garbage(tmp_path, monkeypatch):
    assert accounts.active() is None
    accounts.save({"active": "Main", "accounts": [{"name": "Main"}]})
    assert accounts.active() == "Main"
    monkeypatch.setenv(accounts.ENV_VAR, "Alt")
    assert accounts.active() == "Alt"
    monkeypatch.delenv(accounts.ENV_VAR)
    (tmp_path / "data" / "accounts.json").write_text("[1, 2")
    assert accounts.active() is None


def test_session_start_records_active_account(tmp_path, monkeypatch):
    accounts.save({"active": "Main", "accounts": [{"name": "Main"}]})
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    monkeypatch.setattr(session.log, "setup", lambda prefix, stamp=None: None)
    pause.reset()
    from transitions import Machine

    class M:
        pass

    def model():
        m = M()
        Machine(model=m, states=["a", "end"], initial="a", auto_transitions=False,
                transitions=[{"trigger": "ok", "source": "a", "dest": "end"}])
        return m
    try:
        session.run_session({}, bot="demo", log_prefix=str(tmp_path / "bot"), intro=[],
                            setup=lambda: None, session=model, handlers=lambda m: {"a": lambda: "ok"},
                            final_states={"end"}, cycle_start="a", summary=lambda m, f, l: "")
    finally:
        events.finish()
    (path,) = tmp_path.glob("bot_*.jsonl")
    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert first["event"] == "session_start" and first["account"] == "Main"


# ── vault ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def fast_scrypt(monkeypatch):
    monkeypatch.setattr(vault_mod, "SCRYPT", {"n": 2 ** 10, "r": 8, "p": 1})


def test_vault_roundtrip_and_wrong_password(tmp_path, fast_scrypt):
    path = str(tmp_path / "vault.json")
    v = Vault(path)
    with pytest.raises(WrongPassword):
        v.unlock("short")                       # too short to create
    v.unlock("correct horse")
    v.set("Main", "me@example.com", "hunter2")
    assert "hunter2" not in open(path, encoding="utf-8").read()

    v2 = Vault(path)
    with pytest.raises(WrongPassword):
        v2.unlock("wrong password")
    assert not v2.unlocked
    v2.unlock("correct horse")
    assert v2.entries()["Main"]["password"] == "hunter2"
    v2.set("Main", "new@example.com")           # password=None keeps it
    assert v2.entries()["Main"] == {"email": "new@example.com", "password": "hunter2", "notes": ""}

    v2.change_master("battery staple")
    v2.lock()
    with pytest.raises(WrongPassword):
        v2.entries()
    with pytest.raises(WrongPassword):
        Vault(path).unlock("correct horse")
    v3 = Vault(path)
    v3.unlock("battery staple")
    v3.rename("Main", "Renamed")
    assert list(v3.entries()) == ["Renamed"]


# ── server ────────────────────────────────────────────────────────────────────

@pytest.fixture
def server(tmp_path, fast_scrypt):
    app = App(root=str(tmp_path), vault=Vault(str(tmp_path / "data" / "vault.json")))
    httpd, _ = serve(0, app)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, port
    httpd.shutdown()
    httpd.server_close()


def call(port, path, body=None, token=None, host=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Token": token or "", "Host": host or f"127.0.0.1:{port}"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_server_rejects_missing_token_and_foreign_host(server):
    app, port = server
    assert call(port, "/api/overview")[0] == 403
    assert call(port, "/api/overview", token=app.token, host=f"evil.example:{port}")[0] == 403
    status, page = call(port, "/")
    assert status == 200 and app.token.encode() in page
    assert call(port, "/", host="evil.example")[0] == 403


def test_server_account_and_vault_flow(server, tmp_path):
    app, port = server
    t = app.token
    assert call(port, "/api/account", {"name": "Main", "notes": "tanner"}, t)[0] == 200
    assert accounts.load(str(tmp_path))["active"] == "Main"   # first account becomes active

    assert call(port, "/api/vault/unlock", {"master": "correct horse"}, t)[0] == 200
    assert call(port, "/api/vault/set", {"name": "Main", "email": "a@b.c", "password": "pw"}, t)[0] == 200
    status, body = call(port, "/api/vault/list", {}, t)
    assert json.loads(body) == {"Main": {"email": "a@b.c", "notes": "", "has_password": True}}

    # rename with a locked vault would orphan the login
    call(port, "/api/vault/lock", {}, t)
    assert call(port, "/api/account", {"old": "Main", "name": "Alt"}, t)[0] == 401
    assert call(port, "/api/account/delete", {"name": "Main"}, t)[0] == 401
    call(port, "/api/vault/unlock", {"master": "correct horse"}, t)
    assert call(port, "/api/account", {"old": "Main", "name": "Alt"}, t)[0] == 200
    status, body = call(port, "/api/vault/reveal", {"name": "Alt"}, t)
    assert json.loads(body) == {"password": "pw"}
    assert accounts.load(str(tmp_path))["active"] == "Alt"

    status, body = call(port, "/api/overview", token=t)
    assert status == 200 and json.loads(body)["accounts"] == ["Alt"]
