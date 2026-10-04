# Unattended background run — design

**Linear:** PRO-85 (part 2 of PRO-83) · **Date:** 2026-10-04
**Branch:** `proofexak/pro-85-unattended-background-run-auto-start-auto-restart-external`
**Status:** approved in brainstorming (fully unattended; image templates; approach A)

## Goal

A bot runs in the Docker container with nobody watching: it starts on its own,
keeps RuneLite logged in, restarts after crashes and logouts, can be paused /
stopped from the host, and comes back by itself after a container or host
restart.

Done when (PRO-85): a bot session runs 1h+ in the background while the host is
used normally, and survives a container restart with its configs intact.

User decisions: **fully unattended** (auto-relaunch RuneLite and log in after a
container/RuneLite restart, using RuneLite's saved credentials); screens are
recognised with **image templates**; **approach A** (one Python supervisor).

Already in place (PRO-84 / PRO-15): calibrated configs and session logs live in
the bind-mounted repo (persist across restarts; `python -m lib.logreport` works
on the host); RuneLite's home is a named volume; the container runs as the host
UID.

## Components

| piece | role |
|---|---|
| `lib/headless.py` (`python -m lib.headless`) | container main command in headless mode (PID 1). Reads `BOT`, `LAUNCH`, optional `VALUE` from the environment, resolves them via `lib.bots.discover()`, runs the supervisor loop, installs signal handlers and excepthooks |
| `lib/supervisor.py` | pure restart policy: `decide(outcome, logged_in, budget) -> action`, backoff, rolling restart budget, login-failure counter |
| `lib/client_states.py` | client lifecycle table (bot-style): `launch → wait_login → [accept_terms] → click_play → wait_welcome → click_welcome → in_game`; any wait timeout → `failed` |
| `lib/client.py` | client handlers: start/kill RuneLite (`runelite` command as a subprocess), detect screens with templates, click with `lib.mouse.human_click`; `logged_in()` = in-game template visible |
| `lib.vision.find_template(frame, template, max_diff)` | pure FFT-based matching (numpy, grayscale); returns the centre of the best match or `None` if its mean absolute difference > `max_diff` |
| templates | `lib/client_templates/{terms_accept,login_play,welcome_play,in_game}.png` — gitignored, per user; captured with a new **⚙ Client Templates** menu tool (drag a rectangle in VNC, the crop is saved). `terms_accept` is optional |
| `docker/botctl` | host helper: `pause` / `resume`, `stop`, `kill`, `start`, `status` |
| `docker/docker-compose.yml` | runs `lib.headless` when `BOT` is set, otherwise idles as before (manual mode); `restart: unless-stopped`; `stop_grace_period: 30s` |

### Saved login

RuneLite's client flag `--insecure-write-credentials` writes the Jagex session
to `~/.runelite/credentials.properties` (in the volume) when RuneLite is
launched once from Bolt; afterwards `runelite` logs in without Bolt. That one
Bolt launch with the flag is a manual, documented step (Bolt's settings can't
be verified here). Until the file exists the supervisor logs `waiting` (reason
`no saved credentials`) and re-checks every 60 s. The file holds session tokens
in plain text, only in the local Docker volume — documented.

## Supervisor loop

```
idle  ⇄  (start signal)  →  ensure_logged_in  →  run session  →  decide  → restart | idle
```

- `ensure_logged_in`: if the in-game template is visible, done; else run the
  client machine. On `failed`: kill RuneLite, back off, retry; **3 consecutive
  login failures → idle** (`giving_up`, reason `login`).
- Session = the bot's normal `run_session` (same `.jsonl` session logs).

### Policy (`decide`)

| session outcome | logged in afterwards? | action |
|---|---|---|
| `crashed` (exception) | — | restart (re-login first if needed) |
| `stopped` with a bot reason | no | restart after re-login (logout explains the failure) |
| `stopped` with a bot reason | yes | idle — `giving_up` with the reason |
| `done` | — | idle — `finished` |
| stopped by operator (`stop` / `kill` signal) | — | idle |

- **Backoff** before each automatic restart / login retry: 30 s, 60 s, 120 s, …
  capped at 600 s; reset after a session that ran ≥ 10 min.
- **Budget:** at most 5 automatic restarts per rolling hour; the 6th → idle
  (`giving_up`, reason `restart budget`).
- **Idle never exits**: container, Xvfb and VNC stay up; a `start` signal
  resumes and resets budget and backoff.

### Signals

| `docker/botctl` | signal | effect |
|---|---|---|
| `pause` / `resume` | SIGUSR1 | toggle pause (same as O) |
| `stop` | SIGUSR2 | soft stop: finish the current trip, then idle |
| `kill` | SIGINT | force stop now (same as P; teardown runs), then idle |
| `start` | SIGHUP | leave idle: log in if needed, start the bot |
| (`docker compose stop/down`) | SIGTERM | force stop, teardown, exit 0 |

Handlers only set flags / call `pause.*` (safe in Python signal handlers).
`botctl status` runs `python -m lib.logreport sessions --last 5` plus the last
supervisor events. O/P still work over VNC.

### Events

Supervisor events go to `log/launcher.jsonl` (`bot` = the resolved bot's menu
name): `supervisor_start`, `client_start`, `login` (ok / failed + reason),
`session_end` summary (final, reason, action), `restart` (attempt, delay),
`waiting` (reason), `idle` (`finished` / `giving_up` / `operator`), `signal`.
`lib.logreport stats` counts launcher `error` events as before; a new
`logreport supervisor [--last N]` lists supervisor events.

## Out of scope

Proxy / per-instance identity (PRO-86/87, cancelled). Choc runs headless too via
`VALUE`, but it is not on the scaffold, so it has no session `.jsonl` (its
crashes still reach launcher.jsonl). Detecting a logout *during* a session —
the bot's own failures end the session, then the policy re-logs in.

## Testing

- `find_template`: exact match, within-noise match, absent → `None`, template
  bigger than the frame → `None`, two lookalikes → best wins.
- `client_states`: stub-handler table tests — normal path, optional terms,
  already in game, timeout → `failed`.
- `supervisor.decide` / backoff / budget / login-failure limit: every table row.
- Signal handlers: called directly.
- Integration in the real container (no Jagex login needed): headless mode with
  a stub bot package; `botctl pause/stop/kill/start`; `docker compose stop`
  exits cleanly with session end records; crash → restart per policy.
- Real RuneLite up to its login screen: launch + `terms_accept` click using a
  template cut from a real screenshot.
- User (needs a Jagex login): save credentials via Bolt once, capture the
  login / welcome / in-game templates, run 1h+ unattended, then
  `docker compose restart` and confirm it logs back in and resumes.

## Documentation

`docker/README.md`: "Unattended mode" — one-time credentials + template capture,
`.env` (`BOT`, `LAUNCH`, `VALUE`), `botctl`, policy table, security note on
`credentials.properties`. CLAUDE.md: headless/supervisor layout + where events go.
