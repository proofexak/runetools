"""
Phone alerts (PRO-93): a Discord message, with a screenshot, when a bot stops and needs a human.

Who calls it:
- lib/headless.py, when the supervisor gives up (`idle` with why "giving_up": stopped while logged
  in, 3 failed logins, the restart budget, missing client templates, 3 lost schedule blocks) or waits
  for saved credentials (once per wait);
- lib/session.py, after a menu session's session_end: crashed, or stopped by the bot itself — not
  by the operator (P, overlay Stop), not `done`, and not when lib.headless runs it (`supervised`:
  the supervisor decides, so there is never a double alert).

Set up in lib/notify_config.py (gitignored, copy notify_config.example.py) or NOTIFY_DISCORD_WEBHOOK /
NOTIFY_DISCORD_USER_ID (docker/.env), which win over the file. No webhook URL = nothing is sent.

send() never raises and never blocks on the network: the screenshot is taken at once (it shows the
moment the bot stopped), the post runs on a daemon thread. Outcomes go to log/launcher.jsonl as
`notify` / `notify_error` / `notify_suppressed` events — with the HTTP status only: the webhook URL
is the credential and is never logged.

    python -m lib.checks.notify_test      # sends a test alert
"""
import io, json, math, os, socket, threading, time, urllib.error, urllib.request, uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import lib.events as events

ENV_WEBHOOK   = "NOTIFY_DISCORD_WEBHOOK"
ENV_USER_ID   = "NOTIFY_DISCORD_USER_ID"
USER_AGENT    = "DiscordBot (https://github.com/proofexak/runetools, 1)"  # urllib's default is blocked
TIMEOUT       = 10       # s per request
MAX_RETRY_AFTER = 30     # s: a 429's longest wait before its one retry
HOUR          = 3600
COLOR_RED     = 15158332
IMAGE_NAME    = "screen.jpg"
JPEG_QUALITY  = 70

# Discord's limits (docs.discord.com/developers/resources/message); field values (Discord: 1024) and
# the footer (2048) are kept well under theirs so the embed's 6000-character total always holds,
# even with a full description: 256 + 4096 + 5 × (9 + 256) + 256 < 6000
LIMIT_CONTENT, LIMIT_TITLE, LIMIT_DESCRIPTION = 2000, 256, 4096
LIMIT_FIELD_VALUE, LIMIT_FOOTER = 256, 256

supervised = False   # lib.headless sets it: its sessions are alerted by the supervisor, not run_session


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Alert:
    account:   Optional[str] = None
    bot:       Optional[str] = None
    launch:    Optional[str] = None
    reason:    Optional[str] = None
    last_step: Optional[str] = None
    seconds:   Optional[float] = None
    runs:      Optional[int] = None
    source:    str = "menu"            # "unattended" | "menu"
    ts:        str = field(default_factory=_now)


def should_alert(source, final=None, why=None, operator=False, supervised=False):
    """Does this end need a human? unattended: the supervisor gave up or waits for credentials;
    menu: crashed, or stopped by the bot itself — never an operator stop, done or Ctrl+C, and never
    a supervised session (the supervisor decides)."""
    if source == "unattended":
        return why in ("giving_up", "waiting")
    if supervised:
        return False
    return final == "crashed" or (final == "stopped" and not operator)


# ── settings ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Settings:
    url:          str = ""
    user_id:      str = ""
    screenshot:   bool = True
    min_interval: float = 600
    max_per_hour: int = 10


def load_settings(env, cfg):
    """Settings from a notify_config module (or None) with the environment's non-empty
    NOTIFY_DISCORD_* winning. A value that isn't a number keeps its default."""
    def get(name, default, kind=None):
        value = getattr(cfg, name, default) if cfg is not None else default
        try:
            return kind(value) if kind else value
        except (TypeError, ValueError):
            return default
    url = (env.get(ENV_WEBHOOK) or "").strip() or str(get("DISCORD_WEBHOOK_URL", "") or "").strip()
    user = (env.get(ENV_USER_ID) or "").strip() or str(get("DISCORD_USER_ID", "") or "").strip()
    return Settings(url, user, bool(get("SCREENSHOT", True)), get("MIN_INTERVAL", 600, float),
                    get("MAX_PER_HOUR", 10, int))


_config_warned = False


def config_module():
    """lib/notify_config.py, or None: missing, or broken — then logged once (launcher.jsonl,
    where "notify_config") and the environment's settings still work."""
    global _config_warned
    try:
        import lib.notify_config as cfg
        return cfg
    except ModuleNotFoundError as e:
        if e.name == "lib.notify_config":
            return None              # not set up: the environment alone
        err = e
    except Exception as e:           # a SyntaxError, a failing import inside it, ...
        err = e
    if not _config_warned:
        _config_warned = True
        try:
            events.launcher_error(None, err, "notify_config")
        except Exception:
            pass
    return None


def settings():
    try:
        return load_settings(os.environ, config_module())
    except Exception:          # never: but no alerts rather than a broken bot
        return Settings()


# ── message ───────────────────────────────────────────────────────────────────

def _cut(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def duration(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def discord_payload(alert, user_id, host, image=False):
    """The webhook's payload_json. The mention is in `content` (mentions in embeds never notify),
    and allowed_mentions lets only that user be pinged — not an @everyone inside a reason."""
    title = _cut(f"{alert.bot or 'Bot'} stopped", LIMIT_TITLE)
    reason = alert.reason or "no reason given"
    uid = str(user_id or "").strip()
    if uid.isdigit():
        content, mentions = f"<@{uid}> {title}: {reason}", {"users": [uid]}
    else:
        content, mentions = f"{title}: {reason}", {"parse": []}
    bot = " · ".join(str(x) for x in (alert.bot, alert.launch) if x)
    fields = [("Account", alert.account), ("Bot", bot), ("Last step", alert.last_step),
              ("Runtime", None if alert.seconds is None else duration(alert.seconds)),
              ("Runs", alert.runs)]
    embed = {
        "title": title,
        "description": _cut(reason, LIMIT_DESCRIPTION),
        "color": COLOR_RED,
        "fields": [{"name": name, "value": _cut(value, LIMIT_FIELD_VALUE), "inline": True}
                   for name, value in fields if value is not None and value != ""],
        "footer": {"text": _cut(f"{alert.source} · {host}", LIMIT_FOOTER)},
        "timestamp": alert.ts,
    }
    payload = {"username": "runetools", "content": _cut(content, LIMIT_CONTENT),
               "allowed_mentions": mentions, "embeds": [embed]}
    if image:
        embed["image"] = {"url": f"attachment://{IMAGE_NAME}"}
        payload["attachments"] = [{"id": 0, "filename": IMAGE_NAME}]
    return payload


def multipart_body(payload, image, boundary=None):
    """(body, content type) for a webhook post: payload_json, plus files[0] = the screenshot."""
    boundary = boundary or uuid.uuid4().hex
    b = boundary.encode("ascii")
    parts = [b"--" + b + b"\r\n",
             b'Content-Disposition: form-data; name="payload_json"\r\n',
             b"Content-Type: application/json\r\n\r\n",
             json.dumps(payload).encode("utf-8"), b"\r\n"]
    if image is not None:
        parts += [b"--" + b + b"\r\n",
                  f'Content-Disposition: form-data; name="files[0]"; filename="{IMAGE_NAME}"\r\n'.encode("ascii"),
                  b"Content-Type: image/jpeg\r\n\r\n",
                  image, b"\r\n"]
    parts.append(b"--" + b + b"--\r\n")
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def jpeg(frame, quality=JPEG_QUALITY):
    """A BGR frame (lib.screen.grab) as JPEG bytes."""
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(frame[:, :, ::-1].copy()).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ── limits ────────────────────────────────────────────────────────────────────

class Limiter:
    """The same key at most once per min_interval, at most max_per_hour alerts per rolling hour."""

    def __init__(self, min_interval=600, max_per_hour=10, clock=time.monotonic):
        self.min_interval, self.max_per_hour, self.clock = min_interval, max_per_hour, clock
        self._last, self._sent = {}, deque()
        self._lock = threading.Lock()

    def allow(self, key):
        """None if it may go out (and counts it), else why not: "duplicate" / "hourly cap"."""
        with self._lock:
            now = self.clock()
            while self._sent and now - self._sent[0] >= HOUR:
                self._sent.popleft()
            last = self._last.get(key)
            if last is not None and now - last < self.min_interval:
                return "duplicate"
            if len(self._sent) >= self.max_per_hour:
                return "hourly cap"
            self._last[key] = now
            self._sent.append(now)
            return None


_limiter = None


def _limiter_for(s):
    global _limiter
    if _limiter is None or (_limiter.min_interval, _limiter.max_per_hour) != (s.min_interval, s.max_per_hour):
        _limiter = Limiter(s.min_interval, s.max_per_hour)
    return _limiter


# ── sending ───────────────────────────────────────────────────────────────────

def _retry_after(err):
    for read in (lambda: json.loads(err.read())["retry_after"], lambda: err.headers.get("Retry-After")):
        try:
            value = float(read())
            if math.isfinite(value):
                return value
        except Exception:
            pass
    return 1.0


def _failure(exc):
    """What a failed request is logged as: never str(exc), which may hold the URL."""
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, (socket.timeout, TimeoutError)):
        return "timeout"
    return type(exc).__name__


def post(url, body, content_type, opener, sleeper):
    """POST to the webhook (?wait=true): (True, status) on 2xx, else (False, status or error name).
    A 429 waits its retry_after (at most MAX_RETRY_AFTER) and tries once more; anything else —
    401/403/404 (a dead or blocked webhook), 5xx, network — is not retried."""
    target = url + ("&" if "?" in url else "?") + "wait=true"
    for attempt in (1, 2):
        req = urllib.request.Request(target, data=body, method="POST",
                                     headers={"User-Agent": USER_AGENT, "Content-Type": content_type})
        try:
            with opener(req, timeout=TIMEOUT) as res:
                res.read()
                return True, getattr(res, "status", None)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                sleeper(min(max(_retry_after(e), 0.0), MAX_RETRY_AFTER))
                continue
            return False, e.code
        except Exception as e:
            return False, _failure(e)
    return False, 429


def _opener():
    return urllib.request.build_opener().open


_sleep = time.sleep


def _grab_jpeg():
    import lib.screen as screen
    frame, _ = screen.grab(screen.screen_rect())
    return jpeg(frame)


def _log(alert, event, **fields):
    try:
        events.launcher_event(alert.bot, event, account=alert.account, source=alert.source, **fields)
    except Exception:
        pass


def screenshot():
    """The whole screen as JPEG bytes, now — None when alerts are off, SCREENSHOT is False or the
    grab fails. lib.headless takes it before closing RuneLite, so the alert shows the game."""
    return _screenshot(None)


def _screenshot(s):
    try:
        s = s or settings()
        if not s.url or not s.screenshot:
            return None
        return _grab_jpeg()
    except Exception:
        return None


def _deliver(s, alert, image):
    try:
        payload = discord_payload(alert, s.user_id, socket.gethostname(), image=image is not None)
        body, ctype = multipart_body(payload, image)
        ok, status = post(s.url, body, ctype, _opener(), _sleep)
    except Exception as e:
        ok, status = False, _failure(e)
    _log(alert, "notify" if ok else "notify_error", reason=alert.reason, status=status,
         screenshot=image is not None)


def send(alert, image=None, screenshot=True):
    """Alert the owner. Returns the sending thread (tests join it), or None when nothing goes out:
    not configured, or the limiter held it back (logged as notify_suppressed). image: JPEG bytes
    taken earlier; otherwise the screen is grabbed now (unless screenshot=False or SCREENSHOT is
    off). Never raises."""
    try:
        s = settings()
        if not s.url:
            return None
        why = _limiter_for(s).allow((alert.account, alert.reason))
        if why:
            _log(alert, "notify_suppressed", reason=alert.reason, why=why)
            return None
        if image is None and screenshot:
            image = _screenshot(s)
        thread = threading.Thread(target=_deliver, args=(s, alert, image), name="notify", daemon=True)
        thread.start()
        return thread
    except Exception:
        return None


def session_ended(bot, account, params, final, reason, last_step, stats, seconds, operator=False, error=None):
    """lib/session.py's hook, after session_end: alert if the menu session needs a human."""
    try:
        if not should_alert("menu", final, operator=operator, supervised=supervised):
            return None
        if final == "crashed" and error is not None:
            f = events.error_fields(error)
            reason = f"crashed: {f['type']}: {f['message']}"
        launch = ", ".join(f"{k}={v}" for k, v in (params or {}).items()) or None
        return send(Alert(account=account, bot=bot, launch=launch, reason=reason,
                          last_step=last_step, seconds=seconds, runs=(stats or {}).get("run"),
                          source="menu"))
    except Exception:
        return None
