"""lib/notify.py: Discord alerts when a bot needs a human (PRO-93) — no network, no screen."""
import io
import json
import socket
import urllib.error

import numpy as np
import pytest

import lib.notify as notify

URL = "https://discord.com/api/webhooks/123/SECRET-TOKEN"


# ── should_alert ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("source,final,why,operator,supervised,expected", [
    # unattended: the supervisor gave up, or waits for saved credentials
    ("unattended", None, "giving_up", False, True, True),
    ("unattended", None, "waiting", False, True, True),
    ("unattended", None, "finished", False, True, False),
    ("unattended", None, "operator", True, True, False),
    ("unattended", None, None, False, True, False),
    # menu: stopped by the bot itself, or crashed
    ("menu", "crashed", None, False, False, True),
    ("menu", "stopped", None, False, False, True),
    ("menu", "stopped", None, True, False, False),     # P / overlay Stop
    ("menu", "crashed", None, True, False, True),      # a crash is never the operator's doing
    ("menu", "done", None, False, False, False),
    ("menu", "interrupted", None, False, False, False),
    ("menu", "end", None, False, False, False),
    # supervised: the supervisor decides, never a double alert
    ("menu", "crashed", None, False, True, False),
    ("menu", "stopped", None, False, True, False),
])
def test_should_alert(source, final, why, operator, supervised, expected):
    assert notify.should_alert(source, final, why=why, operator=operator, supervised=supervised) is expected


# ── payload ───────────────────────────────────────────────────────────────────

def _alert(**kw):
    base = dict(account="Main", bot="Tanning", launch="Black Dragonhide", reason="out of hides",
                last_step="banking", seconds=2 * 3600 + 14 * 60 + 5, runs=143, source="unattended",
                ts="2026-10-05T17:42:01+02:00")
    base.update(kw)
    return notify.Alert(**base)


def _embed_total(embed):
    return (len(embed.get("title", "")) + len(embed.get("description", ""))
            + sum(len(f["name"]) + len(f["value"]) for f in embed.get("fields", []))
            + len(embed.get("footer", {}).get("text", "")))


def test_payload_mentions_the_user():
    p = notify.discord_payload(_alert(), "123456789", host="3f2a9c1d", image=True)
    assert p["content"] == "<@123456789> Tanning stopped: out of hides"
    assert p["allowed_mentions"] == {"users": ["123456789"]}
    assert p["username"] == "runetools"
    e = p["embeds"][0]
    assert e["title"] == "Tanning stopped" and e["description"] == "out of hides"
    assert e["color"] == 15158332
    assert [(f["name"], f["value"]) for f in e["fields"]] == [
        ("Account", "Main"), ("Bot", "Tanning · Black Dragonhide"), ("Last step", "banking"),
        ("Runtime", "2:14:05"), ("Runs", "143")]
    assert all(f["inline"] for f in e["fields"])
    assert e["image"] == {"url": "attachment://screen.jpg"}
    assert p["attachments"] == [{"id": 0, "filename": "screen.jpg"}]
    assert e["footer"] == {"text": "unattended · 3f2a9c1d"}
    assert e["timestamp"] == "2026-10-05T17:42:01+02:00"


@pytest.mark.parametrize("user_id", ["", None, "not-a-number", "<@123>"])
def test_payload_without_a_valid_user_id_mentions_nobody(user_id):
    p = notify.discord_payload(_alert(reason="@everyone look"), user_id, host="h")
    assert p["content"] == "Tanning stopped: @everyone look"
    assert p["allowed_mentions"] == {"parse": []}           # not even @everyone in the reason


def test_payload_leaves_out_empty_fields_and_the_image():
    p = notify.discord_payload(_alert(account=None, launch=None, last_step=None, seconds=None, runs=0),
                               "1", host="h", image=False)
    e = p["embeds"][0]
    assert [(f["name"], f["value"]) for f in e["fields"]] == [("Bot", "Tanning"), ("Runs", "0")]
    assert "image" not in e and "attachments" not in p


def test_payload_without_a_reason_or_bot():
    p = notify.discord_payload(_alert(bot=None, reason=None), "", host="h")
    assert p["content"] == "Bot stopped: no reason given"


def test_payload_cuts_every_string_to_its_discord_limit():
    huge = "x" * 10000
    p = notify.discord_payload(_alert(account=huge, bot=huge, launch=huge, reason=huge, last_step=huge),
                               "1", host=huge, image=True)
    e = p["embeds"][0]
    assert len(p["content"]) <= 2000 and len(p["username"]) <= 80
    assert len(e["title"]) <= 256 and len(e["description"]) <= 4096
    assert all(len(f["name"]) <= 256 and len(f["value"]) <= 1024 for f in e["fields"])
    assert len(e["footer"]["text"]) <= 2048
    assert _embed_total(e) <= 6000
    assert e["description"].endswith("…")


def test_duration():
    assert notify.duration(0) == "0:00:00"
    assert notify.duration(59.9) == "0:00:59"
    assert notify.duration(26 * 3600 + 61) == "26:01:01"


# ── multipart ─────────────────────────────────────────────────────────────────

def test_multipart_body_exact_bytes():
    body, ctype = notify.multipart_body({"a": 1}, b"\xff\xd8JPEG", boundary="BOUND")
    assert ctype == "multipart/form-data; boundary=BOUND"
    assert body == (b'--BOUND\r\n'
                    b'Content-Disposition: form-data; name="payload_json"\r\n'
                    b'Content-Type: application/json\r\n\r\n'
                    b'{"a": 1}\r\n'
                    b'--BOUND\r\n'
                    b'Content-Disposition: form-data; name="files[0]"; filename="screen.jpg"\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n'
                    b'\xff\xd8JPEG\r\n'
                    b'--BOUND--\r\n')


def test_multipart_body_without_an_image():
    body, _ = notify.multipart_body({"a": 1}, None, boundary="B")
    assert b"files[0]" not in body and body.endswith(b'{"a": 1}\r\n--B--\r\n')


def test_multipart_boundary_is_random_by_default():
    _, a = notify.multipart_body({}, None)
    _, b = notify.multipart_body({}, None)
    assert a != b


def test_jpeg_encodes_a_bgr_frame():
    frame = np.zeros((90, 160, 3), dtype=np.uint8)
    frame[:, :, 2] = 255                                    # red in BGR
    data = notify.jpeg(frame)
    assert data[:2] == b"\xff\xd8"
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    assert img.size == (160, 90)
    r, g, b = img.getpixel((80, 45))
    assert r > 200 and g < 50 and b < 50


# ── limiter ───────────────────────────────────────────────────────────────────

def test_limiter_dedupes_the_same_key_within_the_interval():
    t = {"now": 0.0}
    lim = notify.Limiter(min_interval=600, max_per_hour=10, clock=lambda: t["now"])
    assert lim.allow(("Main", "out of hides")) is None
    t["now"] = 599
    assert lim.allow(("Main", "out of hides")) == "duplicate"
    assert lim.allow(("Alt", "out of hides")) is None      # another account
    t["now"] = 600
    assert lim.allow(("Main", "out of hides")) is None


def test_limiter_hourly_cap_is_rolling():
    t = {"now": 0.0}
    lim = notify.Limiter(min_interval=0, max_per_hour=3, clock=lambda: t["now"])
    for i in range(3):
        t["now"] = i * 10
        assert lim.allow(i) is None
    t["now"] = 100
    assert lim.allow("x") == "hourly cap"
    t["now"] = 3600                                         # the first one is an hour old
    assert lim.allow("x") is None
    assert lim.allow("y") == "hourly cap"


# ── post (fake opener) ────────────────────────────────────────────────────────

class _Res:
    def __init__(self, status):
        self.status = status

    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, body=b"", headers=None):
    return urllib.error.HTTPError(URL + "?wait=true", code, "err", headers or {}, io.BytesIO(body))


class Opener:
    def __init__(self, *results):
        self.results, self.requests = list(results), []

    def __call__(self, req, timeout=None):
        self.requests.append((req, timeout))
        r = self.results.pop(0)
        if isinstance(r, BaseException):
            raise r
        return _Res(r)


def test_post_204():
    op, sleeps = Opener(204), []
    assert notify.post(URL, b"body", "multipart/form-data; boundary=B", op, sleeps.append) == (True, 204)
    req, timeout = op.requests[0]
    assert req.full_url == URL + "?wait=true" and req.get_method() == "POST" and req.data == b"body"
    assert req.get_header("User-agent") == "DiscordBot (https://github.com/proofexak/runetools, 1)"
    assert req.get_header("Content-type") == "multipart/form-data; boundary=B"
    assert timeout == 10 and sleeps == []


def test_post_keeps_an_existing_query():
    op = Opener(200)
    notify.post(URL + "?thread_id=5", b"", "x", op, lambda s: None)
    assert op.requests[0][0].full_url == URL + "?thread_id=5&wait=true"


def test_post_429_waits_retry_after_and_retries_once():
    op, sleeps = Opener(_http_error(429, b'{"retry_after": 1.5, "global": false}'), 204), []
    assert notify.post(URL, b"", "x", op, sleeps.append) == (True, 204)
    assert sleeps == [1.5] and len(op.requests) == 2


def test_post_429_wait_is_capped_and_only_retried_once():
    op, sleeps = Opener(_http_error(429, b'{"retry_after": 900}'), _http_error(429, b'{"retry_after": 1}')), []
    assert notify.post(URL, b"", "x", op, sleeps.append) == (False, 429)
    assert sleeps == [30] and len(op.requests) == 2


def test_post_429_falls_back_to_the_header():
    op, sleeps = Opener(_http_error(429, b"not json", {"Retry-After": "2"}), 204), []
    assert notify.post(URL, b"", "x", op, sleeps.append) == (True, 204)
    assert sleeps == [2.0]


@pytest.mark.parametrize("code", [400, 401, 403, 404, 500])
def test_post_errors_are_not_retried(code):
    op, sleeps = Opener(_http_error(code), 204), []
    assert notify.post(URL, b"", "x", op, sleeps.append) == (False, code)
    assert len(op.requests) == 1 and sleeps == []


@pytest.mark.parametrize("exc,status", [
    (socket.timeout("timed out"), "timeout"),
    (TimeoutError(), "timeout"),
    (urllib.error.URLError(socket.timeout("timed out")), "timeout"),
    (urllib.error.URLError(ConnectionRefusedError(111, "refused")), "URLError"),
    (OSError("boom " + URL), "OSError"),
])
def test_post_network_errors_are_not_retried(exc, status):
    op = Opener(exc, 204)
    assert notify.post(URL, b"", "x", op, lambda s: None) == (False, status)
    assert len(op.requests) == 1


# ── settings ──────────────────────────────────────────────────────────────────

class _Cfg:
    DISCORD_WEBHOOK_URL = "https://file/hook"
    DISCORD_USER_ID = "42"
    SCREENSHOT = False
    MIN_INTERVAL = 60
    MAX_PER_HOUR = 3


def test_settings_from_the_file():
    s = notify.load_settings({}, _Cfg)
    assert s == notify.Settings("https://file/hook", "42", False, 60, 3)


def test_settings_env_overrides_the_file():
    s = notify.load_settings({"NOTIFY_DISCORD_WEBHOOK": "https://env/hook", "NOTIFY_DISCORD_USER_ID": " 7 "}, _Cfg)
    assert (s.url, s.user_id, s.screenshot) == ("https://env/hook", "7", False)


def test_settings_empty_env_falls_back_to_the_file():
    s = notify.load_settings({"NOTIFY_DISCORD_WEBHOOK": "", "NOTIFY_DISCORD_USER_ID": ""}, _Cfg)
    assert (s.url, s.user_id) == ("https://file/hook", "42")


def test_settings_without_a_file():
    assert notify.load_settings({}, None) == notify.Settings()
    assert notify.Settings().url == "" and notify.Settings().screenshot is True
    assert notify.load_settings({"NOTIFY_DISCORD_WEBHOOK": "https://env/hook"}, None).url == "https://env/hook"


def test_example_config_is_unconfigured():
    import importlib.util, os
    path = os.path.join(os.path.dirname(notify.__file__), "notify_config.example.py")
    spec = importlib.util.spec_from_file_location("notify_config_example", path)
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    assert notify.load_settings({}, cfg) == notify.Settings()


# ── send ──────────────────────────────────────────────────────────────────────

def _launcher_events(tmp_path):
    path = tmp_path / "log" / "launcher.jsonl"
    return [json.loads(l) for l in open(path)] if path.exists() else []


def test_send_unconfigured_does_nothing(tmp_path, monkeypatch):
    grabs = []
    monkeypatch.setattr(notify, "_grab_jpeg", lambda: grabs.append(1) or b"img")
    assert notify.send(_alert()) is None
    assert notify.screenshot() is None
    assert grabs == [] and _launcher_events(tmp_path) == []


@pytest.fixture
def configured(monkeypatch):
    """notify configured with a fake opener and screen; returns (opener, settings holder)."""
    holder = {"settings": notify.Settings(URL, "99", True, 600, 10)}
    op = Opener(*[204] * 5)
    monkeypatch.setattr(notify, "settings", lambda: holder["settings"])
    monkeypatch.setattr(notify, "_opener", lambda: op)
    monkeypatch.setattr(notify, "_grab_jpeg", lambda: b"\xff\xd8shot")
    monkeypatch.setattr(notify, "_sleep", lambda s: None)
    return op, holder


def test_send_posts_one_alert_with_the_screenshot(tmp_path, configured):
    op, _ = configured
    notify.send(_alert()).join(5)
    assert len(op.requests) == 1
    body = op.requests[0][0].data
    assert b'name="files[0]"; filename="screen.jpg"' in body and b"\xff\xd8shot" in body
    assert b"<@99> Tanning stopped: out of hides" in body
    sent = [e for e in _launcher_events(tmp_path) if e["event"] == "notify"]
    assert len(sent) == 1 and sent[0]["status"] == 204 and sent[0]["reason"] == "out of hides"
    assert sent[0]["bot"] == "Tanning"


def test_send_uses_a_given_image_and_can_skip_the_screenshot(configured, monkeypatch):
    op, _ = configured
    monkeypatch.setattr(notify, "_grab_jpeg", lambda: pytest.fail("grabbed"))
    notify.send(_alert(), image=b"\xff\xd8given").join(5)
    notify.send(_alert(reason="other"), screenshot=False).join(5)
    assert b"\xff\xd8given" in op.requests[0][0].data
    assert b"files[0]" not in op.requests[1][0].data and b"attachment://" not in op.requests[1][0].data


def test_send_screenshot_off_in_the_config(configured, monkeypatch):
    op, holder = configured
    holder["settings"] = notify.Settings(URL, "99", False, 600, 10)
    monkeypatch.setattr(notify, "_grab_jpeg", lambda: pytest.fail("grabbed"))
    notify.send(_alert()).join(5)
    assert notify.screenshot() is None
    assert b"files[0]" not in op.requests[0][0].data


def test_send_screenshot_failure_sends_text_only(configured, monkeypatch):
    op, _ = configured

    def broken():
        raise RuntimeError("no display")
    monkeypatch.setattr(notify, "_grab_jpeg", broken)
    notify.send(_alert()).join(5)
    assert len(op.requests) == 1 and b"files[0]" not in op.requests[0][0].data


def test_send_suppresses_a_duplicate(tmp_path, configured):
    op, _ = configured
    notify.send(_alert()).join(5)
    assert notify.send(_alert()) is None
    assert len(op.requests) == 1
    suppressed = [e for e in _launcher_events(tmp_path) if e["event"] == "notify_suppressed"]
    assert len(suppressed) == 1 and suppressed[0]["why"] == "duplicate"


def test_send_failure_is_logged_without_the_url(tmp_path, configured, monkeypatch):
    op = Opener(_http_error(403, b'{"message": "' + URL.encode() + b'"}'))
    monkeypatch.setattr(notify, "_opener", lambda: op)
    notify.send(_alert()).join(5)
    errors = [e for e in _launcher_events(tmp_path) if e["event"] == "notify_error"]
    assert len(errors) == 1 and errors[0]["status"] == 403
    assert "SECRET-TOKEN" not in (tmp_path / "log" / "launcher.jsonl").read_text()


def test_send_never_raises(tmp_path, configured, monkeypatch):
    def boom():
        raise RuntimeError("opener exploded " + URL)
    monkeypatch.setattr(notify, "_opener", boom)
    notify.send(_alert()).join(5)                            # the thread swallows it
    errors = [e for e in _launcher_events(tmp_path) if e["event"] == "notify_error"]
    assert len(errors) == 1 and errors[0]["status"] == "RuntimeError"
    assert "SECRET-TOKEN" not in (tmp_path / "log" / "launcher.jsonl").read_text()
    monkeypatch.setattr(notify, "settings", lambda: 1 / 0)
    assert notify.send(_alert()) is None and notify.screenshot() is None


def test_send_network_error_is_logged(tmp_path, configured, monkeypatch):
    monkeypatch.setattr(notify, "_opener", lambda: Opener(socket.timeout("timed out")))
    notify.send(_alert()).join(5)
    errors = [e for e in _launcher_events(tmp_path) if e["event"] == "notify_error"]
    assert errors[0]["status"] == "timeout"


# ── the menu hook's helper ────────────────────────────────────────────────────

def test_session_ended_alerts_a_bot_stop(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda alert, **kw: sent.append(alert))
    notify.session_ended("tanner", "Main", {"hide_type": "Black Dragonhide", "start_at": "GE"}, "stopped",
                         "recovery failed", "recover", {"run": 12}, 3725.0)
    a, = sent
    assert (a.account, a.bot, a.reason, a.last_step, a.runs, a.seconds, a.source) == (
        "Main", "tanner", "recovery failed", "recover", 12, 3725.0, "menu")
    assert a.launch == "hide_type=Black Dragonhide, start_at=GE"


def test_session_ended_crash_reason_is_the_exception(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda alert, **kw: sent.append(alert))
    notify.session_ended("choc", None, None, "crashed", None, "grind", {}, 5.0, error=KeyError("x"))
    assert sent[0].reason == "crashed: KeyError: 'x'" and sent[0].launch is None


@pytest.mark.parametrize("final,operator", [("done", False), ("stopped", True), ("interrupted", False)])
def test_session_ended_no_alert(monkeypatch, final, operator):
    monkeypatch.setattr(notify, "send", lambda *a, **kw: pytest.fail("sent"))
    notify.session_ended("tanner", None, {}, final, None, "x", {}, 1.0, operator=operator)


def test_session_ended_supervised_no_alert(monkeypatch):
    monkeypatch.setattr(notify, "send", lambda *a, **kw: pytest.fail("sent"))
    monkeypatch.setattr(notify, "supervised", True)
    notify.session_ended("tanner", None, {}, "crashed", None, "x", {}, 1.0, error=RuntimeError())


def test_session_ended_never_raises(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError
    monkeypatch.setattr(notify, "send", boom)
    notify.session_ended("tanner", None, {}, "stopped", None, "x", None, None)


# ── review fixes ──────────────────────────────────────────────────────────────

def test_settings_bad_numbers_fall_back_to_the_defaults():
    class Cfg(_Cfg):
        MIN_INTERVAL = "ten minutes"
        MAX_PER_HOUR = None
    s = notify.load_settings({}, Cfg)
    assert (s.url, s.min_interval, s.max_per_hour) == ("https://file/hook", 600, 10)


def test_broken_config_file_is_logged_once_and_the_env_still_works(tmp_path, monkeypatch):
    import builtins, json, sys
    real_import = builtins.__import__

    def broken(name, *a, **kw):
        if name == "lib.notify_config":
            raise SyntaxError("invalid syntax (notify_config.py, line 3)")
        return real_import(name, *a, **kw)
    monkeypatch.setattr(notify, "_config_warned", False)
    monkeypatch.delitem(sys.modules, "lib.notify_config", raising=False)
    monkeypatch.setattr(builtins, "__import__", broken)
    try:
        assert notify.config_module() is None
        assert notify.config_module() is None
    finally:
        monkeypatch.setattr(builtins, "__import__", real_import)
    assert notify.load_settings({notify.ENV_WEBHOOK: "https://env/hook"}, None).url == "https://env/hook"
    errors = [json.loads(l) for l in open(tmp_path / "log" / "launcher.jsonl")]
    assert [(e["event"], e["where"]) for e in errors] == [("error", "notify_config")]   # once


def test_retry_after_nan_is_not_slept():
    op, sleeps = Opener(_http_error(429, b'{"retry_after": NaN}'), 204), []
    assert notify.post(URL, b"", "x", op, sleeps.append) == (True, 204)
    assert sleeps == [1.0]


def test_session_ended_without_a_stop_reason_says_so(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda alert, **kw: sent.append(alert))
    notify.session_ended("golden_nuggets", None, {}, "stopped", None, "deposit", {"run": 3}, 60.0)
    assert sent[0].reason is None
    p = notify.discord_payload(sent[0], "", host="h")
    assert p["content"] == "golden_nuggets stopped: no reason given"
