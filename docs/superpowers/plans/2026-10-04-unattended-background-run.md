# Unattended Background Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m lib.headless` keeps RuneLite logged in, runs the chosen bot, restarts it per policy, and is controllable from the host via `docker/botctl`.

**Architecture:** pure pieces first (`vision.find_template`, `supervisor` policy, `client_states` table), then I/O wrappers (`client.py`, template capture tool, `headless.py` loop + signals), then Docker wiring and an in-container integration run.

**Tech Stack:** Python 3.8 (host venv) / 3.12 (container), numpy, transitions, pytest, Docker Compose v2.

**Spec:** `docs/superpowers/specs/2026-10-04-unattended-background-run-design.md`

## Global Constraints

- Template names exactly: `terms_accept` (optional), `login_play`, `welcome_play`, `in_game`; stored as `lib/client_templates/<name>.png` (gitignored).
- Policy numbers exactly: backoff 30, 60, 120 … capped 600 s, reset after a session ≥ 600 s; ≤ 5 automatic restarts per rolling 3600 s; 3 consecutive login failures → idle; credentials re-check every 60 s.
- Signals exactly: SIGUSR1 pause toggle, SIGUSR2 soft stop → idle, SIGINT force stop → idle, SIGHUP start, SIGTERM force stop + exit 0.
- Idle never exits the process. Supervisor events go to `log/launcher.jsonl` via `lib.events` (new helper `events.launcher_event(bot, event, **fields)`).
- `lib/supervisor.py`, `lib/client_states.py` and `vision.find_template` stay pure (no mss / pyautogui / subprocess / time.sleep).
- No test touches the real screen/mouse/keyboard; docker integration uses a stub bot and runs only inside the container's virtual display.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Signal arrives while idle-sleeping or mid-backoff** — `stop`/`kill` keep it idle, `start` wakes it immediately (no waiting out a 10-min backoff), SIGTERM exits promptly.
2. **Restart budget window** — restarts older than an hour stop counting; exactly 5 in an hour allowed, the 6th idles.
3. **Template partly off-screen / client not yet drawn** — `find_template` returns `None`, never a bogus match on a black frame (mean diff of an all-black template vs black frame must still require the template to actually match).
4. **`BOT`/`LAUNCH` that don't resolve** — launcher `error` event + idle with a clear reason, not a crash loop.
5. **RuneLite process already running when the client machine starts** — no second instance launched.

---

### Task 1: `vision.find_template`

**Files:** `lib/vision.py`; test `tests/test_vision.py`.
**Produces:** `find_template(frame, template, max_diff=8.0) -> Optional[(int, int)]` — frame-local centre of the best match; frames/templates BGR uint8; grayscale SSD via FFT (`numpy.fft.rfft2`); `max_diff` = max mean absolute grayscale difference of the best window.

- [ ] Tests: exact match centre; match with ±3 noise ≤ max_diff; absent pattern → None; template larger than frame → None; two copies, one exact one degraded → exact wins; low-contrast template (std < 1, e.g. all black) → None (can't be located reliably). Watch fail → implement → PASS → commit.

### Task 2: `lib/supervisor.py` — policy

**Produces:** constants `BACKOFF_START=30, BACKOFF_MAX=600, LONG_SESSION=600, BUDGET=5, BUDGET_WINDOW=3600, MAX_LOGIN_FAILURES=3, CREDENTIALS_RECHECK=60`; `Outcome(final: str, reason: Optional[str], crashed: bool, operator: bool, seconds: float)`; `decide(outcome, logged_in) -> str` in {`"restart"`, `"idle_finished"`, `"idle_giving_up"`, `"idle_operator"`}; class `Budget(now_fn)` with `.allow() -> bool` (records + checks rolling window), `.reset()`; class `Backoff()` with `.next() -> float`, `.reset()`, `.session_ran(seconds)`.

- [ ] Tests: every spec table row via `decide`; backoff 30/60/120/…/600/600; reset after a ≥600 s session; budget allows 5, refuses 6th, allows again once the oldest is > 3600 s old (fake clock). Watch fail → implement → PASS → commit.

### Task 3: Client state table + handlers

**Files:** `lib/client_states.py` (pure), `lib/client.py`; tests `tests/test_client_states.py`, `tests/test_client.py`.
**Produces:** `client_states.build_machine(stats) -> ClientSession` (states `launch, wait_login, accept_terms, click_play, wait_welcome, click_welcome, in_game, failed`; finals `{in_game, failed}`; events `ok`, `terms`, `in_game`, `timeout`); `client.templates(dir=TEMPLATE_DIR) -> dict`, `client.screen_has(name, frame=None) -> Optional[pt]`, `client.logged_in() -> bool`, `client.running() -> bool`, `client.start()`, `client.kill()`, `client.handlers(session, templates, clock, wait) -> dict`, `client.ensure_logged_in(log) -> bool`.

- [ ] Table tests: normal path; `wait_login` sees `terms` → `accept_terms` → back to `wait_login`; `launch` when already in game → `in_game`; any wait `timeout` → `failed`.
- [ ] Handler tests with fake screen frames + recorded clicks: `wait_login` returns `ok` when `login_play` appears, `terms` when only `terms_accept` does, `timeout` after its deadline (fake clock); `start` not called when `running()` is True; missing optional `terms_accept` template is fine; missing required template → `failed` with reason.
- [ ] Commit.

### Task 4: ⚙ Client Templates capture tool

**Files:** `lib/client_templates_editor.py`; `run.py` tools list; `.gitignore` (`lib/client_templates/`); test `tests/test_client_templates.py`.
- [ ] Test: the editor's save function, given a region, grabs it (fake screen) and writes `<dir>/<name>.png` with exactly that crop; overwriting works. Implement with `lib.config_editor.run_editor` (`region` fields named after the templates, values kept in `lib/client_templates/regions.json`). Commit.

### Task 5: `lib/headless.py`

**Produces:** `resolve(bot, launch, value, bots) -> (Bot, start_callable)` raising `ValueError` with a clear message; `Supervisor(bot, start, client, clock, sleeper, log)` with `.run_forever()` and signal entry points `.on_pause()`, `.on_soft_stop()`, `.on_kill()`, `.on_start()`, `.on_term()`; `main()` installs handlers + excepthooks, reads env.
- [ ] Tests (all dependencies stubbed, fake clock/sleeper that returns early when a flag is set): resolve ok / unknown bot / unknown launch / ask_int launch without VALUE; loop: crash → restart with backoff; logged-out stop → relogin + restart; logged-in stop → idle giving_up; done → idle finished; budget exhaustion → idle; 3 login failures → idle; missing credentials → `waiting` every 60 s; SIGUSR2 during session → idle after it; SIGHUP while idle or mid-backoff → wakes immediately; SIGTERM → force stop + returns; events written to launcher.jsonl. Commit.

### Task 6: Docker wiring, botctl, logreport

**Files:** `docker/docker-compose.yml` (command, env `BOT`/`LAUNCH`/`VALUE`, `stop_grace_period: 30s`), `docker/botctl`, `lib/events.py` (`launcher_event`), `lib/logreport.py` (`supervisor` command); tests `tests/test_logreport.py`, `tests/test_events.py`.
- [ ] Tests: `launcher_event` writes the common fields; `logreport supervisor` lists supervisor events newest-last and skips `error`-only noise filters correctly. `bash -n docker/botctl`; `docker compose config` with and without `BOT`. Commit.

### Task 7: In-container integration

- [ ] Stub bot package (scratch, mounted at `/app/zz_stubbot` via a compose override in the scratchpad) whose launch runs a tiny `run_session` that loops / crashes on demand; stub client templates from synthetic PNGs drawn by a helper inside the container; run headless with `BOT=Stub`: verify `botctl pause/resume/stop/start/kill`, crash → restart with logged backoff, `docker compose stop` → clean `session_end` + exit 0 within the grace period.
- [ ] Real RuneLite: cut `terms_accept` from the earlier login screenshot, run `client.ensure_logged_in` in the container up to clicking Accept (no credentials → stops at `wait_login`, logs `waiting`/`login failed` as designed).
- [ ] Record results in the ledger; commit any fixes test-first.

### Task 8: Docs

- [ ] `docker/README.md` "Unattended mode" (credentials step, template capture, `.env`, `botctl`, policy table, security note); CLAUDE.md layout + events. Suite green; commit.
