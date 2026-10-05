# Bot alerts to Discord: design

**Linear:** PRO-93 · **Date:** 2026-10-05
**Status:** approved in brainstorming (Discord webhook; "needs a human" only; screenshot attached;
unattended and menu sessions; approach A: a small `lib/notify`, called where a run ends)

## Goal

When a bot stops and can't continue without the owner, the owner's phone buzzes within about a
minute with what stopped, why, and a screenshot of the game at that moment.

Done when: an unattended or menu session that stops by itself (out of hides, no glory charges,
recovery failed, GE restock failed, crash), or a supervisor that gives up (3 failed logins,
restart budget, missing client templates, no saved credentials), sends exactly one Discord message
that @mentions the owner and carries a screenshot. Operator stops (P, overlay Stop, `botctl
stop` / `kill`), finished jobs (`done`) and successful automatic restarts send nothing. A failing
or unconfigured sender never blocks or breaks a bot.

User decisions: **Discord webhook** (ntfy / Pushover can be added later behind the same
`send`); **only "needs a human"** events; **attach a screenshot**; **unattended and menu sessions**.

## Research summary

| | Phone push | Cost | Notes |
|---|---|---|---|
| Discord webhook (chosen) | buzzes when `content` @mentions the user; mentions inside embeds never notify | free | Cloudflare blocks Python-urllib's default User-Agent (403 / error 1010): set `DiscordBot (url, version)`. The URL is the credential (anyone with it can post, edit, delete). 204 by default, 200 + JSON with `?wait=true`. Embed text ≤ 6000 total, title 256, description 4096, 25 fields (name 256 / value 1024), content 2000. 429 body has `retry_after` (float s); never retry 401/403/404; 10,000 invalid responses per 10 min gets the IP banned by Cloudflare |
| ntfy.sh | priority 4–5 = long vibration + pop-over; DND override per Android channel | free, 250 msgs/day | topic name = password; iOS app basic |
| Pushover | priority 2 repeats until acknowledged | $4.99 once per platform | best "can't miss it" |
| Telegram bot | normal chat push | free | only option with commands back (getUpdates polling); belongs with PRO-90 |
| Apprise | any of the above | free | about 7 transitive deps; rejected (stdlib only) |

Sources: https://docs.discord.com/developers/resources/webhook ,
https://docs.discord.com/developers/reference , https://docs.discord.com/developers/topics/rate-limits ,
https://docs.discord.com/developers/resources/message , https://docs.ntfy.sh/publish/ ,
https://pushover.net/api , https://core.telegram.org/bots/api , https://github.com/caronc/apprise

## Components

| piece | role |
|---|---|
| `lib/notify.py` | `Alert` record; pure `should_alert(...)`, `discord_payload(alert, user_id)`, `multipart_body(payload, image)`; `Limiter` (dedupe + hourly cap, clock passed in); `send(alert)`: grab, encode, post in a daemon thread. Never raises |
| `lib/notify_config.example.py` → `lib/notify_config.py` | gitignored like `ge_config.py`: `DISCORD_WEBHOOK_URL = ""`, `DISCORD_USER_ID = ""`, `SCREENSHOT = True`, `MIN_INTERVAL = 600`, `MAX_PER_HOUR = 10` |
| env overrides | `NOTIFY_DISCORD_WEBHOOK`, `NOTIFY_DISCORD_USER_ID` (from `docker/.env` through compose) win over the file |
| `lib/headless.py` | `Supervisor._idle(why, reason)`: alert when `why == "giving_up"`; the `waiting` (no saved credentials) loop alerts once per wait |
| `lib/session.py` | after `session_end`: alert when not supervised and the session crashed or was stopped by the bot itself |
| `lib/events.py` | `EventLog.operator_stop`: set when `force_stop` or `soft_stop` is emitted |
| `lib/checks/notify_test.py` | live check: sends a test alert with a screenshot to the configured channel |

Not configured (no webhook URL) means `send` does nothing.

## Alert

```
Alert(account, bot, launch, reason, last_step, seconds, runs, source, ts)
source: "unattended" | "menu"
```

`account` comes from `lib.accounts.active()`; `launch` from the supervisor's launch label or the
session params; the footer names the host (`socket.gethostname()`, which is the container id
inside Docker).

## When to alert

`should_alert(source, final, why=None, operator=False, supervised=False)`:

* **unattended** (`Supervisor._idle`): yes when `why == "giving_up"`; no for `finished`
  and `operator`
* **menu** (`run_session`): yes when `final == "crashed"`, or `final == "stopped"` and not
  `operator`; no for `done`, `interrupted` (Ctrl+C) and operator stops; **no when supervised**
  (the supervisor decides, so there is never a double alert)

`supervised` is a flag `lib.headless` sets before running the bot (`notify.supervised = True`).

## Message (Discord)

Request: `POST {webhook}?wait=true`, `multipart/form-data` with

* `payload_json`:
  ```json
  {"username": "runetools",
   "content": "<@USER_ID> Tanning stopped: out of hides",
   "allowed_mentions": {"users": ["USER_ID"]},
   "embeds": [{"title": "Tanning stopped", "description": "out of hides", "color": 15158332,
     "fields": [{"name": "Account", "value": "Main", "inline": true},
                {"name": "Bot", "value": "Tanning · Black Dragonhide", "inline": true},
                {"name": "Last step", "value": "banking", "inline": true},
                {"name": "Runtime", "value": "2:14:05", "inline": true},
                {"name": "Runs", "value": "143", "inline": true}],
     "image": {"url": "attachment://screen.jpg"},
     "footer": {"text": "unattended · 3f2a9c1d"}, "timestamp": "2026-10-05T17:42:01+02:00"}]}
  ```
* `files[0]`: `screen.jpg` (`image/jpeg`), the full screen via `lib.screen.grab`, Pillow JPEG
  quality 70 (about 150–300 KB at 1600×900)

Headers: `User-Agent: DiscordBot (https://github.com/proofexak/runetools, 1)`, the multipart
`Content-Type` with its boundary. Every string is cut to its Discord limit. Without a user id the
message has no mention (and won't buzz). The content line keeps the reason so the push preview
is readable.

## Sending and errors

* `send` returns at once; the work runs in a daemon thread (the supervisor goes idle right after)
* screenshot fails → text-only alert
* `urlopen(timeout=10)`; 2xx = sent; 429 → wait `retry_after` (max 30 s) and retry once;
  401 / 403 / 404 → no retry (dead or blocked webhook); network / timeout → no retry
* every failure becomes a `notify_error` event (launcher log, or the session's log) with the
  status code only; the webhook URL never appears in a log or exception text
* `Limiter`: the same (account, reason) at most once per `MIN_INTERVAL`, at most `MAX_PER_HOUR`
  alerts per rolling hour; suppressed alerts are logged as `notify_suppressed`
* sent alerts are logged as `notify` events (reason, status), so `logreport supervisor` shows them

## Out of scope

* other events (job finished, crash with auto-restart, daily summary)
* other channels (ntfy, Pushover); `send` keeps one backend for now
* commands from the phone (Resume / Stop): PRO-90
* full-screen screenshots of every failed step: PRO-91

## Testing

* `should_alert`: every source × final × why × operator × supervised combination in a table
* `discord_payload`: mention only with a user id, `allowed_mentions` limited to it, every field
  cut to its limit, total embed text ≤ 6000, image reference only with a screenshot
* `multipart_body`: fixed boundary → exact bytes (payload part + file part)
* `Limiter`: dedupe window and hourly cap with a fake clock
* sender with a fake opener: 204, 429 then 204 (one retry), 403 (no retry), timeout; none raise,
  the URL never shows in the logged error
* config: env overrides the file; no URL → nothing sent
* hooks: supervisor `giving_up` → one alert, `operator` / `finished` → none (existing stub
  client + fake clock); `run_session` crash → one alert, `ForceStop` / overlay Stop → none,
  supervised → none
* live: `python -m lib.checks.notify_test` posts a test alert with a screenshot

## Setup (once)

1. Discord: a private channel → Integrations → Webhooks → New Webhook → copy URL
2. Settings → Advanced → Developer Mode; right-click yourself → Copy User ID
3. `lib/notify_config.py` (copy from the example) for menu runs; `NOTIFY_DISCORD_WEBHOOK` /
   `NOTIFY_DISCORD_USER_ID` in `docker/.env` for the container
4. Phone: Discord notifications on, the channel not muted
5. `python -m lib.checks.notify_test` (and inside the container)

## Documentation

README: a "Phone alerts" section (setup above). CLAUDE.md: `lib/notify.py` in the layout, and the
rule that alerts never raise into a bot.
