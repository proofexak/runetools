# Play Schedules Implementation Plan (PRO-102)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each account plays to a generated, per-account schedule (default 200 h/month) that its bot container follows by itself, and the web app shows planned blocks next to the sessions that actually ran.

**Architecture:** The web app's API owns schedules: a pure, seeded generator (TypeScript) turns an account's profile into play blocks, stored in Postgres and mirrored to `data/schedules/<account>.json` (the same `data/` hand-over as `data/active_account`). In the bot container, `lib/headless.py` gains a schedule mode (`SCHEDULE=1`) that re-reads that file, logs in and runs each block's launch, soft-stops it at the block's end and closes RuneLite in between. The account page gets a Schedule card: a week grid of planned vs actual plus adherence numbers.

**Tech Stack:** Python 3 (pytest), TypeScript (Fastify, Drizzle/Postgres, PGlite in tests, Vitest), React + TanStack Query + Tailwind.

**Spec:** Linear PRO-102 ("Play schedules: per-account generated schedule (200 h/month) …") and the research doc https://claude.ai/code/artifact/5b50a90e-0d50-476d-9911-e547fd91a75b.

## Global Constraints

- Schedule file: `data/schedules/<account name>.json`, written atomically with `writeDataFile` (apps/api/src/accounts.ts). Shape (the contract between TS and Python):
  `{"account": str, "enabled": bool, "timezone": str, "written": ISO string, "blocks": [{"id": int, "start": int, "end": int, "bot": str, "launch": str, "value": str | null}]}` — `start` / `end` are **epoch seconds (UTC)**, blocks sorted by start, never overlapping.
- Defaults: `monthlyHours = 200`, `timezone = "Europe/Warsaw"` (alt1's proxy IP is Polish), `enabled = false`.
- Generator caps: session ≤ 4.5 h (16 200 s), day ≤ 11 h, gap between sessions 20–180 min, no session length a whole number of minutes (`seconds % 60 != 0`), ≥ 1 day off every Monday–Sunday week, month total = target ± 5 % (target × ramp; a month's target = `monthlyHours × daysInMonth / 30`).
- Ramp: with `rampStart` set, day d (0-based from rampStart) gets factor `min(1, 0.3 + 0.7 × d / 14)`.
- Blocks are kept 14 days ahead (`HORIZON_DAYS = 14`), refilled at API start and every hour.
- Schedule mode timing (Python): file re-read at least every `SCHEDULE_RECHECK = 60` s; soft stop at block end; `pause.force_stop()` `BLOCK_FORCE_GRACE = 1200` s after the end if the session still runs.
- Session times in the DB are naive local wall time in the API's TZ (= the bots' TZ, docker/.env `TZ`): convert with `new Date(naive)` (local parse) — never append `Z`.
- Python waits: no `time.sleep(random.uniform(...))` before input (tests/test_human_sleep_sites.py); the supervisor sleeps through its injectable `_sleep`.
- No commit trailers (`Co-Authored-By`); short commit subjects like the repo's (`Area: what changed`).

## Review Focus

1. **Block already running when the container starts** (start ≤ now < end): it must log in and run the remainder, not wait for the next block — `test_starts_mid_block`.
2. **Schedule file missing, empty or malformed** (web app never wrote it, half-written JSON): no crash, no play — `load()` returns `(False, [])`; `test_load_bad_files`.
3. **Block names an unknown bot/launch** (typo in the activity list): the supervisor logs `schedule_skip` and sits out that block, it doesn't crash or idle forever — `test_unknown_launch_skips_block`.
4. **DST change inside the generated month** (Europe/Warsaw, last Sunday of March / October): blocks still start at the intended local time and never overlap — `generates across DST without overlaps`.
5. **Account renamed or deleted**: the old `data/schedules/<old>.json` is removed and (rename) the new one written, so a container never follows a stale file — `rename moves the schedule file` (API test).

---

### Task 1: `lib/schedule.py` — read the schedule file

**Files:**
- Create: `lib/schedule.py`
- Test: `tests/test_schedule.py`

**Interfaces:**
- Produces:
  - `Block = NamedTuple("Block", id:int, start:float, end:float, bot:str, launch:str, value: str | None)`
  - `path_for(account: str | None, root: str | None = None) -> str | None` → `<root>/data/schedules/<account>.json`, `None` when account is falsy (root defaults to the repo root, like `lib/accounts.py`).
  - `load(path: str | None) -> tuple[bool, list[Block]]` — never raises; missing / unreadable / malformed → `(False, [])`; `enabled` false → `(False, blocks)`; blocks sorted by start, rows missing a field or with `end <= start` dropped.
  - `current(blocks, now: float) -> Block | None` — the block with `start <= now < end`.
  - `next_start(blocks, now: float) -> float | None` — earliest `start > now`.

- [ ] **Step 1: Write the failing tests** in `tests/test_schedule.py`:
  - `test_path_for`: `path_for("alt1", "/r") == os.path.join("/r", "data", "schedules", "alt1.json")`; `path_for(None) is None`.
  - `test_load_reads_blocks(tmp_path)`: a file with `enabled: true` and two blocks given out of order → `(True, [b1, b2])` sorted, values typed (`value` None kept).
  - `test_load_bad_files(tmp_path)`: missing path, `None`, `"{"`, `"[]"`, `{"enabled": true}` (no blocks) → each `(False, [])`; a block without `bot` or with `end <= start` is dropped, the rest kept.
  - `test_disabled_file_has_no_play(tmp_path)`: `enabled: false` → first element False.
  - `test_current_and_next`: blocks [100,200) and [300,400): `current(b,150).id==1`, `current(b,200) is None`, `current(b,250) is None`, `next_start(b,250)==300`, `next_start(b,400) is None`.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/test_schedule.py -q` → FAIL (module not found).
- [ ] **Step 3:** Implement `lib/schedule.py` (module docstring states the file contract from Global Constraints and that the web app writes it).
- [ ] **Step 4:** Same command → PASS.
- [ ] **Step 5:** Commit `Schedule: read data/schedules/<account>.json (PRO-102)`.

### Task 2: Schedule mode in the unattended supervisor

**Files:**
- Modify: `lib/supervisor.py` (pure policy), `lib/headless.py` (Supervisor + main), `docker/bot.yml` (command runs headless when `SCHEDULE=1` too; pass `SCHEDULE`), `docker/accounts/account.env.example` (`#SCHEDULE=1`)
- Test: `tests/test_supervisor.py`, `tests/test_headless.py`

**Interfaces:**
- Consumes: Task 1 (`schedule.load/current/next_start/path_for`, `Block`).
- Produces:
  - `lib/supervisor.py`: `SCHEDULE_RECHECK = 60`, `BLOCK_FORCE_GRACE = 1200`; `schedule_decide(outcome: Outcome, logged_in: bool, block_over: bool) -> str` → `"next_block"` when `block_over` (and not operator/interrupted, which stay `"idle_operator"`); `"skip_block"` when `decide(...) == "idle_finished"`; otherwise `decide(outcome, logged_in)`.
  - `headless.Supervisor(bot, start, client, clock=…, sleeper=None, idle_waiter=None, schedule=None, resolver=None, watcher=None)` — `schedule: () -> (enabled, blocks)`, `resolver: Block -> (Bot, start)` (raises ValueError for unknown names), `watcher(end: float, soft: callable, force: callable) -> stop: callable` (default: a daemon thread polling `self.clock` every 5 s that calls `soft()` once at `end` and `force()` once at `end + BLOCK_FORCE_GRACE`).
  - Supervisor events (launcher.jsonl): `schedule_wait` (next: epoch or None, reason), `schedule_block` (id, bot, launch, end), `schedule_skip` (id, reason), `schedule_logout`.

Behaviour of `run_forever` when `schedule` is set (existing behaviour unchanged when it is None):
1. Not active → idle wait (as now).
2. `enabled, blocks = schedule()`; `block = current(blocks, clock())` if enabled else None.
3. No block → if the client may be up (`self._client_up`), `client.kill()` + `schedule_logout`, `_client_up = False`; emit `schedule_wait` once per distinct next start; `_sleep(min(SCHEDULE_RECHECK, max(1, next - now)))` (next None → `SCHEDULE_RECHECK`); continue.
4. Block skipped earlier (its id in `self._skipped`) → treat as no block, but sleep until `min(block.end, now + SCHEDULE_RECHECK)`.
5. `resolver(block)` raises ValueError → `schedule_skip` with the message, add id to `_skipped`, continue.
6. Otherwise set `self.bot, self.start`, emit `schedule_block`, then the existing credentials → login → session path (`_client_up = True` after a login attempt). The session runs with `watcher(block.end, soft=lambda: self.stats.__setitem__("stop", True), force=pause.force_stop)`; its stop function is called after the session.
7. After the session: `action = schedule_decide(outcome, logged_in, clock() >= block.end)`; `"next_block"` → continue (step 3 logs out); `"skip_block"` → add to `_skipped`, continue; else the existing restart/idle handling.
8. A force stop caused by the watcher must not read as an operator stop: the watcher's force sets `self._deadline_forced = True` before `pause.force_stop()`, `_run_session` treats `pause._force_stop` as operator only when that flag is False, and `pause.reset()` clears the force flag after such a session.

`main()`: `SCHEDULE=1` → `account = accounts.active()`, `schedule = lambda: lib.schedule.load(lib.schedule.path_for(account))`, `resolver = lambda b: resolve(b.bot, b.launch, b.value, bots)`, `bot=Bot("schedule", [])`, `start=None`; BOT/LAUNCH not required. Without `RUNETOOLS_ACCOUNT` → `launcher_error` + idle like a bad BOT.

- [ ] **Step 1: Write failing tests.**
  - `tests/test_supervisor.py::test_schedule_decide`: block over + `final="stopped"` → `"next_block"`; block over + operator → `"idle_operator"`; not over + `final="done"` → `"skip_block"`; not over + crashed → `"restart"`; not over + stopped + logged out → `"restart"`.
  - `tests/test_headless.py` — extend `make()` with `schedule=`, `resolver=`, `watcher=` passthrough; a fake watcher records `(end)` and lets the test fire `soft`/`force`; fake clock as today:
    - `test_waits_logged_out_until_the_block`: blocks [[1000, 2000)], clock 0 → first action is `client.kill()` once, sleep 60 (recheck), …, then at t ≥ 1000 a login and the block's start runs with the watcher's end == 2000.
    - `test_starts_mid_block`: clock 1500 inside [1000, 3000) → logs in and runs immediately, no sleep before the session.
    - `test_soft_stop_at_block_end_moves_on`: the bot's start calls the watcher's `soft`, sets `stats["step"]="stopped"`, advances the clock past end → no restart, the supervisor logs out (`kill`) and waits; events contain `schedule_block` then `schedule_logout`.
    - `test_forced_after_grace_is_not_operator`: the bot's start fires `force` then raises `pause.ForceStop`-equivalent stop (`stats["step"]="interrupted"`) with clock past end → `next_block`, not idle.
    - `test_unknown_launch_skips_block`: resolver raises ValueError → event `schedule_skip`, no login, sleeps until the block end, never idles.
    - `test_done_skips_rest_of_block`: session ends `("done", None)` mid-block → no second session in that block; next block runs.
    - `test_disabled_schedule_never_logs_in`: `schedule=lambda: (False, blocks)` → no login, kill once, only recheck sleeps.
    - `test_file_change_picked_up`: schedule function returns [] first, then a current block → second loop logs in (no restart of the supervisor).
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py tests/test_headless.py -q` → new tests FAIL.
- [ ] **Step 3:** Implement `schedule_decide` + constants in `lib/supervisor.py`; the schedule path in `lib/headless.py` (keep the non-schedule loop byte-for-byte in behaviour — all existing headless tests must pass); `main()` wiring; `docker/bot.yml` command → `if [ -n "$$BOT" ] || [ "$$SCHEDULE" = 1 ]; then exec python3 -m lib.headless; …` and `- SCHEDULE=${SCHEDULE:-}`; `#SCHEDULE=1` (with a one-line comment) in `account.env.example`.
- [ ] **Step 4:** Full suite `.venv/Scripts/python.exe -m pytest -q` → all PASS.
- [ ] **Step 5:** Commit `Headless: schedule mode — log in for each block, soft-stop at its end, logged out between (PRO-102)`.

### Task 3: Schedule generator (TypeScript, pure)

**Files:**
- Create: `webapp/apps/api/src/schedule/generate.ts`, `webapp/apps/api/src/schedule/zone.ts`
- Test: `webapp/apps/api/test/schedule-generate.test.ts`

**Interfaces:**
- Produces:
  - `zone.ts`: `zonedEpoch(tz: string, date: string /* YYYY-MM-DD */, secondsOfDay: number) -> number` (epoch seconds of that local wall time; seconds ≥ 86400 roll into the next day), `zonedDate(tz, epochSeconds) -> string` (local YYYY-MM-DD), `weekday(date: string) -> number` (0 = Monday).
  - `generate.ts`:
    - `interface Activity { bot: string; launch: string; value: string | null; weight: number }`
    - `interface ScheduleProfileInput { account: string; seed: number; timezone: string; monthlyHours: number; activities: Activity[]; rampStart: string | null }`
    - `interface PlannedBlock { start: number; end: number; bot: string; launch: string; value: string | null }` (epoch seconds)
    - `generateMonth(p: ScheduleProfileInput, month: string /* YYYY-MM */) -> PlannedBlock[]` — deterministic for (account, seed, month); sorted; no overlaps; `[]` when `activities` is empty.
    - `generateRange(p, fromEpoch: number, toEpoch: number) -> PlannedBlock[]` — the months covering the range, blocks with `start >= fromEpoch && start < toEpoch`.
    - `traits(account: string, seed: number)` — the per-account profile draws (exported for tests): `{ weekdayAnchor, weekendAnchor (seconds of day), startSd (s), sessionsMean, weibullShape, weekendMult, offTwoProb }`, within: weekday anchor 17:00–20:30, weekend anchor 2–4 h earlier, startSd 60–90 min, sessionsMean 1.1–2.1, shape 0.6–0.8, weekendMult 1.1–1.5.

Algorithm (decided here; the test pins the outcomes):
- RNG: `mulberry32` seeded from the first 4 bytes of sha256(`${account}:${seed}`) for traits, and of sha256(`${account}:${seed}:${month}`) for a month (node:crypto `createHash`).
- Days off: for each Monday–Sunday week touching the month, 1 day off (2 with probability `offTwoProb` 0.2–0.35), weekday picked at random (drawn per week from the week's own Monday date, so a week split across months agrees).
- Day weights: play day w = lognormal(0, 0.25) × (Sat/Sun ? weekendMult : 1) × weekFactor (lognormal(0, 0.15) per week) × ramp factor.
- Day hours = monthTarget × w / Σw, then cap at 11 h, redistributing the excess proportionally over uncapped days (repeat until none exceeds).
- Sessions in a day: k = max(ceil(h / 4.5), 1 + Poisson(sessionsMean − 1)); split h by Weibull(shape) draws normalised to h; any piece > 4.5 h hands its excess to the shortest piece; each piece ≥ 10 min (merge otherwise).
- Gaps: lognormal median 50 min, σ 0.6, clamped to 20–180 min.
- First start = anchor (weekend anchor on Sat/Sun) + N(0, startSd), clamped so the day's span (sessions + gaps) starts ≥ 08:00 and ends ≤ 26:00 local (02:00 next day); if the span is longer than that window, start at 08:00.
- Lengths in whole seconds; a length divisible by 60 gets +(1..59) s from the RNG.
- Activity per session: weighted random with score = weight × (1 + sessions since this activity last ran) (state carried across the month).
- Month total check is a test, not a runtime assertion.

- [ ] **Step 1: Write failing tests** (`schedule-generate.test.ts`), profile `{account: "alt1", seed: 0, timezone: "Europe/Warsaw", monthlyHours: 200, activities: [{bot:"Tanning", launch:"Green Dragonhide", value:"Al Kharid", weight:1}, {bot:"Tanning", launch:"Blue Dragonhide", value:"Al Kharid", weight:1}], rampStart: null}`:
  - `month total within 5% of the target`: for "2026-11" (30 days) Σ(end−start)/3600 ∈ [190, 210]; for "2026-12" target 200×31/30.
  - `sessions respect the caps`: every block ≤ 16 200 s and ≥ 600 s, `(end-start) % 60 !== 0`; per local day Σ ≤ 11 h; gaps inside a day 1200–10 800 s.
  - `at least one day off each week`: for every Monday–Sunday week fully inside the month, ≥ 1 local date with no block start.
  - `generates across DST without overlaps`: "2026-10" and "2027-03" — sorted, `blocks[i].end <= blocks[i+1].start`.
  - `deterministic and per account`: same input → deep-equal; account "alt2" → different starts; seed 1 → different.
  - `evening starts on weekdays`: median local start hour of each weekday's first block ∈ [15, 22].
  - `uses every activity`: both launches appear; with one activity weight 0 it never appears.
  - `ramp lowers the first days`: rampStart "2026-11-01" → hours on Nov 1–3 < hours on Nov 20–22 (sums), and month total ≈ ramped target (± 5 %).
  - `no activities → no blocks`.
  - `zonedEpoch` round-trip: `zonedEpoch("Europe/Warsaw","2026-07-01",0)` = Date.UTC(2026,5,30,22)/1000; `zonedDate` of that = "2026-07-01".
- [ ] **Step 2:** `cd webapp && pnpm --filter @runetools/api test -- schedule-generate` → FAIL.
- [ ] **Step 3:** Implement `zone.ts` (Intl.DateTimeFormat offset lookup, two-pass for DST) and `generate.ts`.
- [ ] **Step 4:** Same command → PASS; `pnpm --filter @runetools/api typecheck` clean.
- [ ] **Step 5:** Commit `Schedule generator: seeded per account, 200 h/month, Weibull sessions, days off (PRO-102)`.

### Task 4: API — storage, schedule file, routes, hourly refill

**Files:**
- Modify: `webapp/apps/api/src/db/schema.ts`, `webapp/packages/shared/src/index.ts`, `webapp/apps/api/src/app.ts`, `webapp/apps/api/src/server.ts`, `webapp/apps/api/src/accounts.ts` (rename/delete move/remove the file), `webapp/apps/api/test/helpers.ts` (TRUNCATE the new tables)
- Create: `webapp/apps/api/drizzle/0003_*.sql` (via `pnpm --filter @runetools/api db:generate`), `webapp/apps/api/src/schedule/store.ts`, `webapp/apps/api/src/routes/schedule.ts`
- Test: `webapp/apps/api/test/schedule.test.ts`

**Interfaces:**
- Consumes: Task 3 (`generateRange`, `Activity`, `ScheduleProfileInput`).
- Produces:
  - Tables: `schedule_profiles` (`account_id` int PK → accounts.id on delete cascade, `enabled` bool default false, `timezone` text default 'Europe/Warsaw', `monthly_hours` int default 200, `activities` jsonb `Activity[]` default '[]', `ramp_start` date null, `seed` int default 0, `updated_at` timestamptz default now); `schedule_blocks` (`id` serial, `account_id` int → accounts.id cascade, `start_at` / `end_at` timestamptz, `bot`, `launch` text, `value` text null, `edited` bool default false; index (account_id, start_at)).
  - Shared (`packages/shared`): zod `ScheduleActivity` ({bot 1–64, launch 1–64, value string ≤ 64 | null, weight number 0–100}), `ScheduleProfileBody` ({enabled, timezone (validated with `Intl.supportedValuesOf("timeZone")` in the API), monthlyHours int 0–400, activities ≤ 12, rampStart iso date | null}), `ScheduleBlockPatch` ({start?, end? epoch seconds, bot?, launch?, value?}); types `ScheduleProfile`, `ScheduleBlock {id, start, end, bot, launch, value, edited}`, `ActualSession {id, start, end, bot, status}` (epoch seconds), `ScheduleResponse {profile, blocks, actual, now}`; FeedEvent `{ type: "schedule"; account: string }`.
  - `store.ts`: `getProfile(db, accountId)` (defaults when no row), `saveProfile(db, accountId, body)`, `refill(db, accountId, now = Date.now()/1000)` (delete blocks with start > now and not edited; insert `generateRange(profile, now, now + 14×86400)` minus those overlapping an edited block or starting before the latest kept block's end; disabled → only deletes), `writeScheduleFile(db, dataDir, accountId)`, `refillAll(db, dataDir)` (every account with a profile row), `scheduleView(db, accountId, from, to)` (blocks overlapping [from, to) + sessions of that account name overlapping it, naive times → `new Date(naive).getTime()/1000`, a session with no end uses `lastEventAt`).
  - Routes: `GET /api/accounts/:id/schedule?from=<epoch>&to=<epoch>` (default this week ±), `PUT /api/accounts/:id/schedule` (profile → save, refill, write file), `POST /api/accounts/:id/schedule/regenerate` (seed + 1, refill, write), `PATCH /api/schedule/blocks/:id` (sets `edited`, rejects end ≤ start or an overlap with another block: 409), `DELETE /api/schedule/blocks/:id`; each change emits `{type:"schedule", account}` and rewrites the file.
  - `server.ts`: `refillAll` once after listen, then `setInterval(… , 3_600_000)` (errors logged, never thrown); cleared on shutdown.

- [ ] **Step 1: Write failing tests** (`schedule.test.ts`, with `makeApp()` + `login()`):
  - `profile defaults then save`: GET on a new account → `enabled:false, monthlyHours:200, timezone:"Europe/Warsaw", activities:[]`, blocks []; PUT enabled with one activity → 200; GET → blocks cover the next 14 days (every start ≥ now, last start < now + 14 d), sum > 0.
  - `writes the schedule file`: after PUT, `<dataDir>/schedules/<name>.json` parses to the Global Constraints shape, `enabled: true`, blocks sorted, ids = DB ids.
  - `disable keeps history, drops the future`: a block whose start is in the past (inserted directly) survives PUT `enabled:false`; future blocks gone; file `enabled:false`.
  - `regenerate changes the plan but keeps edited blocks`: PATCH one future block (moves it 10 min) → edited; regenerate → different block starts, the edited block unchanged, no overlaps.
  - `patch rejects overlaps and empty blocks`: end ≤ start → 400; overlapping a neighbour → 409.
  - `actual sessions come back as epoch seconds`: insert a sessions row (account name, startedAt naive "2026-10-11T18:00:00.000", endedAt "...19:30") → `actual[0].start === new Date("2026-10-11T18:00:00.000").getTime()/1000`, duration 5400.
  - `rename moves the schedule file`: rename the account → old file gone, new file present; delete → file gone.
  - `bad timezone is a 400`.
- [ ] **Step 2:** `pnpm --filter @runetools/api test -- schedule` → FAIL.
- [ ] **Step 3:** Schema + `db:generate` (check the SQL creates both tables, FK cascades, index), shared types, `store.ts`, routes, `app.ts` registration, account rename/delete hooks (inside `updateAccount`/`deleteAccount`'s callers in routes/accounts.ts: after the change, move/remove the file — failures logged, not fatal), server job, helpers TRUNCATE list.
- [ ] **Step 4:** `pnpm test` (whole webapp) + `pnpm typecheck` → PASS.
- [ ] **Step 5:** Commit `Web app: schedules — profile, 14 days of blocks, data/schedules/<account>.json (PRO-102)`.

### Task 5: Web — planned vs actual

**Files:**
- Create: `webapp/apps/web/src/lib/schedule.ts`, `webapp/apps/web/src/lib/schedule.test.ts`, `webapp/apps/web/src/components/schedule.tsx`
- Modify: `webapp/apps/web/src/lib/queries.ts` (key + `useSchedule(accountId, from, to)`, invalidated by the `schedule` feed event where the feed is handled), `webapp/apps/web/src/pages/account-detail.tsx` (the card, after the Login card)

**Interfaces:**
- Consumes: Task 4 types and routes.
- Produces (`lib/schedule.ts`, pure):
  - `weekDays(weekStart: string, tz: string) -> {date: string; start: number; end: number}[]` (7 local days, epoch bounds via an Intl-based local-midnight helper copied from the API's `zonedEpoch` idea).
  - `segments(items: {start:number; end:number}[], day: {start:number; end:number}) -> {left: number; width: number; item}[]` (percent of the day, clipped, items crossing midnight split).
  - `adherence(blocks, actual, from, to, now) -> { plannedHours, ranHours, ranInsideHours, outsideMinutes, missed: number /* past blocks with < 10 % covered */, coverage: number /* ranInside / planned-so-far, 0–1 */ }` — only the part of the window before `now` counts as "so far".
- UI (`components/schedule.tsx`, `ScheduleCard({ account })`):
  - Header: title "Schedule", week navigation (‹ this week ›), Regenerate, an Enabled switch (Button toggling).
  - Grid: one row per day (Mon–Sun, the profile's timezone), 0–24 h axis with 6-hour ticks; planned blocks as outlined bars coloured by `botColors` keyed by bot, actual sessions as filled thinner bars under them, a "now" line on today. Hover title: launch, local times, duration.
  - Adherence tiles for the shown week: planned h, ran h, coverage %, minutes outside, missed blocks.
  - Settings (collapsed by default): monthly hours, timezone (input + datalist of `Intl.supportedValuesOf("timeZone")`), ramp start date, activities table (bot, launch, value, weight; add/remove rows; datalist suggestions: Tanning × Green/Blue/Red/Black Dragonhide with value "Al Kharid", Choco Grind / Run with a number, Mining launches) → Save (PUT).
  - Clicking a planned future block opens a small dialog: start/end time inputs (local) → PATCH, Delete → DELETE.
  - Note line under the grid: "The bot follows this only with SCHEDULE=1 in its account file (docker/README.md)."

- [ ] **Step 1: Write failing tests** (`schedule.test.ts`): `weekDays("2026-10-19", "Europe/Warsaw")` (the week DST ends) gives 7 dates "2026-10-19"…"2026-10-25", the Sunday's `end − start` = 25 h, the others 24 h; `segments` clips a block running past midnight into two days (left/width percents); `adherence` with a 2 h block, 1.5 h of it run, 0.5 h run outside, one past block never run → planned 2+1, ran 2, inside 1.5, outside 30, missed 1, coverage 0.5; future blocks don't count toward coverage.
- [ ] **Step 2:** `pnpm --filter @runetools/web test` → FAIL.
- [ ] **Step 3:** Implement `lib/schedule.ts`, the query hook, the card, and place it on the page.
- [ ] **Step 4:** `pnpm test` + `pnpm typecheck` + `pnpm --filter @runetools/web build` → PASS. Run the app (`run` skill / `pnpm dev` with PGlite or the compose stack) and look at the card with an enabled profile: bars render, a week with sessions shows actual bars, the switch and Regenerate update the grid.
- [ ] **Step 5:** Commit `Web app: Schedule card — planned vs actual week, adherence, profile settings (PRO-102)`.

### Task 6: Docs and close-out

**Files:**
- Modify: `CLAUDE.md` (repo layout: `lib/schedule.py`, `webapp/apps/api/src/schedule/`; a "Play schedules (PRO-102)" key-design paragraph: file contract, generator numbers, schedule mode behaviour, research link; "What's working" line), `docker/README.md` (Unattended mode: `SCHEDULE=1` instead of BOT/LAUNCH, how it behaves, botctl start/stop interplay), `webapp/README.md` (Schedule card, routes, refill job, file).

- [ ] **Step 1:** Write the docs.
- [ ] **Step 2:** Full Python suite + `pnpm test` + `pnpm typecheck` → PASS.
- [ ] **Step 3:** Commit `Docs: play schedules (PRO-102)`.
