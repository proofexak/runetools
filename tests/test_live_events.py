"""Live status for the web app (PRO-99): push sender, byte offsets, heartbeat
thread, state_enter / pause_start / pause_end, and logreport on the new events."""
import glob
import http.server
import json
import os
import socket
import threading
import time
import urllib.error

import pytest
from transitions import Machine

import lib.events as events
import lib.heartbeat as heartbeat
import lib.pause as pause
import lib.session as session
from lib import logreport as lr


# ── a stand-in for the web app's POST /api/ingest ─────────────────────────────

class _App:
    def __init__(self):
        self.posts = []
        self.got = threading.Event()
        app = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["content-length"]))
                app.posts.append({"path": self.path, "auth": self.headers["authorization"],
                                  **json.loads(body)})
                app.got.set()
                self.send_response(200)
                self.send_header("content-length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def app():
    a = _App()
    yield a
    a.close()


def _closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ── push target + file keys ───────────────────────────────────────────────────

def test_no_token_means_no_push(tmp_path, monkeypatch):
    monkeypatch.setenv(events.APP_URL_VAR, "http://127.0.0.1:1")
    assert events.push_target() is None


def test_empty_url_means_no_push(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "bot_token").write_text("secret\n")
    monkeypatch.setenv(events.APP_URL_VAR, "")
    assert events.push_target() is None


def test_push_target_reads_url_and_token(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "bot_token").write_text("secret\n")
    monkeypatch.delenv(events.APP_URL_VAR)
    assert events.push_target() == (events.DEFAULT_APP_URL, "secret")
    monkeypatch.setenv(events.APP_URL_VAR, "http://webapp:8778/")
    assert events.push_target() == ("http://webapp:8778", "secret")


def test_file_key_is_repo_relative_posix(tmp_path):
    assert events.file_key(str(tmp_path / "tanner" / "log" / "t_1.jsonl")) == "tanner/log/t_1.jsonl"
    assert events.file_key(os.path.dirname(str(tmp_path))) is None   # outside the repo


# ── byte offsets ──────────────────────────────────────────────────────────────

def test_lines_are_lf_and_offsets_exact(tmp_path, app):
    path = tmp_path / "tanner" / "log" / "t_1.jsonl"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"old": "line"}\r\n')                 # a pre-existing CRLF line
    log = events.EventLog(str(path), "tanner", "1", push=(app.url, "tok"))
    log.emit("step", state="bank", note="żółw")              # non-ASCII field
    log.emit("heartbeat", state="walk")
    log.close()
    events.pusher_for(app.url).join()
    data = path.read_bytes()
    assert b"\r\n" not in data[17:]                           # new lines are LF on every platform
    assert [p["offset"] for p in app.posts] == [17, data.index(b"\n", 17) + 1]
    for p in app.posts:
        assert p["path"] == "/api/ingest" and p["auth"] == "Bearer tok"
        assert p["file"] == "tanner/log/t_1.jsonl"
        line = p["line"].encode("utf-8")
        assert data[p["offset"]:p["offset"] + len(line) + 1] == line + b"\n"
    assert json.loads(app.posts[0]["line"])["note"] == "żółw"


def test_concurrent_emits_keep_offsets_in_file_order(tmp_path, app):
    log = events.EventLog(str(tmp_path / "s.jsonl"), "b", "s", push=(app.url, "tok"))
    threads = [threading.Thread(target=lambda: [log.emit("heartbeat") for _ in range(20)]) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log.close()
    events.pusher_for(app.url).join()
    offsets = [p["offset"] for p in app.posts]
    assert len(offsets) == 80 and offsets == sorted(offsets)
    data = (tmp_path / "s.jsonl").read_bytes()
    assert all(data[o:o + len(p["line"])].decode() == p["line"] for o, p in zip(offsets, app.posts))


# ── the sender never blocks or raises ─────────────────────────────────────────

def test_full_queue_drops_without_blocking():
    release = threading.Event()

    def stuck(req, timeout):
        release.wait(5)
        raise urllib.error.URLError("slow app")
    p = events.Pusher("http://x", maxsize=2, opener=stuck)
    started = time.perf_counter()
    for i in range(50):
        p.send("tok", "k", i, "{}")
    assert time.perf_counter() - started < 0.1
    assert p.dropped >= 47
    release.set()
    p.join()


@pytest.mark.parametrize("failure", [urllib.error.URLError("refused"), socket.timeout("timed out"),
                                     OSError("reset"), ValueError("weird")])
def test_send_failures_are_swallowed_and_later_lines_still_go(failure):
    calls = []

    def opener(req, timeout):
        calls.append(json.loads(req.data)["offset"])
        if len(calls) == 1:
            raise failure
        raise urllib.error.URLError("still down")
    p = events.Pusher("http://x", opener=opener, backoff=0)
    p.send("tok", "k", 0, "{}")
    p.send("tok", "k", 3, "{}")
    p.join()
    assert calls == [0, 3]


def test_after_a_failure_lines_are_dropped_untried_for_the_backoff():
    now, calls = {"t": 0.0}, []

    def opener(req, timeout):
        calls.append(json.loads(req.data)["offset"])
        if len(calls) == 1:
            raise urllib.error.URLError("refused")
        return _Response()
    p = events.Pusher("http://x", opener=opener, backoff=5, clock=lambda: now["t"])
    p.send("tok", "k", 0, "{}")
    p.join()
    now["t"] = 4.9
    p.send("tok", "k", 3, "{}")
    p.join()
    now["t"] = 5.1
    p.send("tok", "k", 6, "{}")
    p.join()
    assert calls == [0, 6] and p.dropped == 1


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b"{}"


def test_app_down_never_slows_emit(tmp_path):
    url = f"http://127.0.0.1:{_closed_port()}"
    log = events.EventLog(str(tmp_path / "s.jsonl"), "b", "s", push=(url, "tok"))
    started = time.perf_counter()
    for _ in range(100):
        log.emit("heartbeat")
    elapsed = time.perf_counter() - started
    log.close()
    started = time.perf_counter()
    events.pusher_for(url).join()                      # one try, the rest dropped by the backoff
    assert time.perf_counter() - started < 3
    assert elapsed < 0.5
    assert len((tmp_path / "s.jsonl").read_bytes().splitlines()) == 100


def test_unresponsive_app_times_out(tmp_path):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)                                       # accepts, never answers
    try:
        p = events.Pusher(f"http://127.0.0.1:{srv.getsockname()[1]}", timeout=0.2)
        started = time.perf_counter()
        p.send("tok", "k", 0, "{}")
        p.join()
        assert time.perf_counter() - started < 2
    finally:
        srv.close()


# ── heartbeat thread ──────────────────────────────────────────────────────────

class _Log:
    def __init__(self):
        self.events = []

    def emit(self, event, **fields):
        self.events.append((event, fields))

    def names(self):
        return [e for e, _ in self.events]


def _until(cond, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_heartbeat_beats_with_state_run_and_paused():
    log, stats = _Log(), {"step": "mining", "run": 4}
    hb = heartbeat.Heartbeat(log, stats, lambda: False, interval=0.05, poll=0.01).start()
    assert _until(lambda: log.names().count("heartbeat") >= 2)
    hb.stop()
    assert log.events[0] == ("heartbeat", {"state": "mining", "run": 4, "paused": False})


def test_heartbeat_reports_pause_start_and_end():
    log, flag = _Log(), {"p": False}
    hb = heartbeat.Heartbeat(log, {"step": "banking"}, lambda: flag["p"], interval=60, poll=0.01).start()
    flag["p"] = True
    assert _until(lambda: "pause_start" in log.names())
    flag["p"] = False
    assert _until(lambda: "pause_end" in log.names())
    hb.stop()
    assert [e for e in log.events if e[0] != "heartbeat"] == [("pause_start", {"state": "banking"}),
                                                             ("pause_end", {"state": "banking"})]
    assert log.names().count("heartbeat") == 1          # the one at start; the next is a minute away


def test_heartbeat_stops_and_emits_nothing_after():
    log = _Log()
    hb = heartbeat.Heartbeat(log, {}, lambda: False, interval=0.01, poll=0.005).start()
    assert _until(lambda: log.events)
    hb.stop()
    assert not hb._thread.is_alive()
    n = len(log.events)
    time.sleep(0.05)
    assert len(log.events) == n


def test_heartbeat_survives_errors():
    log, calls = _Log(), {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return False
    hb = heartbeat.Heartbeat(log, {}, flaky, interval=0.02, poll=0.005).start()
    assert _until(lambda: "heartbeat" in log.names())
    hb.stop()


# ── through a real session ────────────────────────────────────────────────────

class _Model:
    pass


def _model():
    m = _Model()
    Machine(model=m, states=["a", "end"], initial="a", auto_transitions=False,
            transitions=[{"trigger": "ok", "source": "a", "dest": "end"},
                         {"trigger": "stop", "source": "a", "dest": "end"}])
    return m


@pytest.fixture
def env(monkeypatch, tmp_path):
    pause.reset()
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    monkeypatch.setattr(session.log, "setup", lambda prefix, stamp=None: None)
    monkeypatch.setattr(heartbeat, "INTERVAL", 0.02)
    monkeypatch.setattr(heartbeat, "POLL", 0.005)
    yield tmp_path
    pause.reset()
    events.finish()


def _session_events(tmp_path):
    (path,) = glob.glob(str(tmp_path / "bot_*.jsonl"))
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def _run(tmp_path, handler):
    return session.run_session({}, bot="demo", log_prefix=str(tmp_path / "bot"), intro=[], setup=lambda: None,
                               session=_model, handlers=lambda m: {"a": handler}, final_states={"end"},
                               cycle_start=None, summary=lambda m, f, l: "")


def test_session_heartbeats_and_stops_before_session_end(env):
    def slow():
        _until(lambda: False, 0.1)             # the fixture stubs time.sleep out
        return "ok"
    _run(env, slow)
    ev = _session_events(env)
    names = [e["event"] for e in ev]
    assert "heartbeat" in names and names[-1] == "session_end"
    beat = next(e for e in ev if e["event"] == "heartbeat")
    assert beat["state"] == "a" and beat["paused"] is False
    assert not any(t.name == "heartbeat" for t in threading.enumerate())


def test_session_logs_a_pause_taken_inside_an_action(env):
    def pausing():
        pause.set_paused(True)                 # O pressed mid-step ...
        _until(lambda: False, 0.05)
        pause.set_paused(False)                # ... and released, all inside the handler
        _until(lambda: False, 0.05)
        return "ok"
    _run(env, pausing)
    names = [e["event"] for e in _session_events(env)]
    i = names.index("pause_start")
    assert names.index("pause_end") > i and names.index("step") > names.index("pause_end")


# ── logreport ─────────────────────────────────────────────────────────────────

def _ev(event, t, **f):
    return {"ts": f"2026-09-30T12:{t // 60:02d}:{t % 60:02d}.000", "session": "s", "bot": "tanner",
            "event": event, **f}


def test_logreport_ignores_the_new_events_in_counts():
    evs = [_ev("session_start", 0), _ev("state_enter", 0, state="a", run=0),
           _ev("heartbeat", 30, state="a", run=0, paused=False),
           _ev("step", 40, state="a", result="ok", seconds=40.0, run=1),
           _ev("state_enter", 40, state="b", run=1), _ev("heartbeat", 60, state="b", run=1, paused=False)]
    s = lr.summarize(evs)
    assert s["final"] == "killed" and s["active_seconds"] == 60 and s["runs"] == 1
    assert s["state_counts"] == {"a": 1} and s["pauses"] == 0


def test_logreport_killed_while_paused_stops_the_clock_at_pause_start():
    evs = [_ev("session_start", 0), _ev("state_enter", 0, state="a", run=0),
           _ev("pause_start", 100, state="a"), _ev("heartbeat", 130, state="a", run=0, paused=True),
           _ev("heartbeat", 160, state="a", run=0, paused=True)]
    assert lr.summarize(evs)["active_seconds"] == 100


def test_logreport_finished_pauses_are_not_subtracted_twice():
    evs = [_ev("session_start", 0), _ev("pause_start", 10, state="a"),
           _ev("pause", 30, state="a", seconds=20.0), _ev("pause_end", 30, state="a"),
           _ev("pause_start", 50, state="a"), _ev("pause_end", 55, state="a"),   # inside an action: not logged
           _ev("heartbeat", 90, state="a", run=0, paused=False)]
    assert lr.summarize(evs)["active_seconds"] == 90 - 20
