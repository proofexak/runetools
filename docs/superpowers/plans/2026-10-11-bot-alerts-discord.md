# Bot alerts to Discord: plan (PRO-93)

Spec: `docs/superpowers/specs/2026-10-05-bot-alerts-discord-design.md`. Base: `proofexak/pro-102-play-schedules`
(schedule mode in `lib/headless.py`). PRO-91 runs in parallel and also touches `lib/events.py`,
`lib/session.py`, `CLAUDE.md`: changes there stay a few additive lines.

## 1. `lib/notify.py` (pure parts first)

- `Alert` dataclass: `account, bot, launch, reason, last_step, seconds, runs, source, ts`
  (`ts` defaults to now, local, with offset).
- `should_alert(source, final=None, why=None, operator=False, supervised=False) -> bool`
  - `"unattended"`: `why in {"giving_up", "waiting"}` (waiting = no saved credentials)
  - `"menu"`: not supervised, not operator, and `final == "crashed"` or `final == "stopped"`
- `Settings` (url, user_id, screenshot, min_interval, max_per_hour); `load_settings(env, cfg)`:
  non-empty `NOTIFY_DISCORD_WEBHOOK` / `NOTIFY_DISCORD_USER_ID` win over `cfg`; `settings()` imports
  `lib.notify_config` (missing → defaults, unconfigured).
- `discord_payload(alert, user_id, host, image=True) -> dict`: content `<@id> {bot} stopped: {reason}`
  (mention only for an all-digit id, `allowed_mentions` `{"users": [id]}`, else `{"parse": []}`), red embed,
  inline fields Account / Bot (`bot · launch`) / Last step / Runtime (`h:mm:ss`) / Runs, empty ones left out,
  `image: attachment://screen.jpg` + `attachments` only with an image, footer `source · host`, timestamp.
  Limits: content 2000, username 80, title 256, description 4096, field name 256 / value 1024, footer 2048,
  embed total 6000 (description gives way).
- `multipart_body(payload, image, boundary) -> (bytes, content_type)`: `payload_json` part + `files[0]`
  `screen.jpg` (`image/jpeg`) when an image is given.
- `jpeg(frame_bgr, quality=70) -> bytes` (Pillow).
- `Limiter(min_interval, max_per_hour, clock)`: `allow(key) -> None | "duplicate" | "hourly cap"`.
- `post(url, body, content_type, opener, sleeper) -> (ok, status)`: `?wait=true`, `DiscordBot` UA,
  timeout 10, 429 → `retry_after` (≤ 30 s) and one retry, 4xx/5xx/network → no retry; status is the HTTP
  code or the exception's type name — never the URL.
- `send(alert, image=None) -> Thread | None`: unconfigured → None; limiter → `notify_suppressed`; image
  (given, or grabbed now when `SCREENSHOT`) → post in a daemon thread → `notify` / `notify_error`
  (launcher.jsonl; the session's log is closed by then). Never raises.
- `screenshot() -> bytes | None`: the full screen as JPEG, None when unconfigured / off / failing.
- `session_ended(bot, params, final, reason, last_step, stats, seconds, operator, error)`: the menu hook.
- `supervised = False` module flag.

Tests `tests/test_notify.py`: `should_alert` table; payload mention / no mention / limits / total ≤ 6000 /
image ref; multipart exact bytes; jpeg magic; limiter with a fake clock; `post` with a fake opener
(204, 429→204 with one sleep, 403 no retry, timeout, URLError) and the URL never in the logged events;
`load_settings` env over file, empty env falls back; `send` unconfigured → nothing, configured → one post
with the screenshot, suppressed second alert logged.

## 2. Config trio

`lib/notify_config.example.py` (`DISCORD_WEBHOOK_URL = ""`, `DISCORD_USER_ID = ""`, `SCREENSHOT = True`,
`MIN_INTERVAL = 600`, `MAX_PER_HOUR = 10`), `.gitignore` `lib/notify_config.py`. conftest autouse:
`notify.settings` → unconfigured, `notify.supervised = False`, fresh limiter — no test can post.

## 3. Hooks

- `lib/events.py`: `EventLog.operator_stop` (False; True once `force_stop` / `soft_stop` is emitted).
- `lib/session.py`: `stats["last_step"]`; after `events.finish()`, `notify.session_ended(...)`.
- `lib/headless.py`: `Supervisor(launch=)`, schedule blocks set it; `_idle(why, reason, shot=None)` alerts
  when `should_alert("unattended", why=why)`; the screenshot is taken before RuneLite is killed (login
  give-up, a lost block's idle); the credentials wait alerts once per stretch; `main()` sets
  `notify.supervised = True` and alerts a setup error (bad BOT / LAUNCH, no account).
  Not alerted: `schedule_skip` (one lost block), `schedule_wait`, finished / operator idles, restarts.

Tests: `tests/test_headless.py` (giving up while logged in → one alert with last step / runs / runtime;
3 failed logins → one alert, screenshot taken before the kill; restart budget → one; finished / operator
→ none; schedule: 2 lost blocks → none, the 3rd → one; credentials wait → one over several checks),
`tests/test_session.py` (crash → one, bot stop → one, done / ForceStop / overlay Stop / supervised → none),
`tests/test_events.py` (`operator_stop`).

## 4. Live check, compose, docs

`lib/checks/notify_test.py` (sends a test alert, waits for the thread, prints the status from
launcher.jsonl). `docker/bot.yml`: `NOTIFY_DISCORD_WEBHOOK` / `NOTIFY_DISCORD_USER_ID`. README "Phone alerts",
docker/README (settings table, "What it does when a session ends"), CLAUDE.md layout + design note.
