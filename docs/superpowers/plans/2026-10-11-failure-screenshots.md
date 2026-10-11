# Failure screenshots (PRO-91) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** every failing `step` (`fail` / `not_found`) and every session `error` leaves a PNG of the screen
next to the session log, with the regions that state uses drawn on it; the event names the file; logreport and
the web app's session page show them.

**Architecture:** a new `lib/screenshots.py` owns the per-session shooter (module-level current, like
`lib/events.py`): grab monitor 1 → pure `vision.draw_marks` → PNG. `run_machine` asks it for a shot after a
failing handler result; `run_session` starts / finishes it and asks for one when it records an `error` (the file
name travels on the exception and `events.error_fields` adds it). Bots declare `STATE_MARKS` (state → config
names) in their `states.py`; `run.py` passes them to `run_session(marks=...)`. The web app stores
`steps.screenshot` / `errors.screenshot` and serves the PNG through an authenticated route that only reads a
file recorded for that session, in that session log's own folder.

**Tech Stack:** Python (numpy, Pillow, mss), Fastify + Drizzle, React.

**Spec:** Linear PRO-91 (no spec file).

## Global Constraints

- File name: `<log name>_<stamp>_<n>_<state>.png` in the session log's folder (`<n>` 1-based per session)
- Event field: `screenshot: "<file name>"` (name only, no folder), only on events that have one
- Cap: `MAX_PER_SESSION = 20` screenshots per session; after it, no file and no field
- Never raises into a bot; a failing grab / save = the event without `screenshot`
- No screenshot for `ForceStop`, `KeyboardInterrupt`, `SystemExit` (not failures of the bot)
- `lib/events.py`, `lib/session.py`: small additive changes only (PRO-93 works on them in parallel)
- LF line endings; no commit trailers

## Review Focus

- A grab that throws (no display, mss error) → step still logged, no `screenshot` field — test in Task 2
- Uncalibrated (zero) regions / points in a state's marks → not drawn, no crash — test in Task 1
- A config name the config doesn't have (older config) → skipped — test in Task 2
- A URL file name with `..`, `/`, `%2F`, or a PNG not recorded for that session → 404 — test in Task 4
- A session whose log is keyed by absolute path (second log root) → its screenshots still served — test in Task 4

---

### Task 1: `vision.draw_marks` — pure overlay drawing

**Files:** Modify `lib/vision.py`; Test `tests/test_vision.py`

**Interfaces — Produces:**
- `mark_shape(value) -> ("rect", (l, t, w, h)) | ("point", (x, y)) | ("poly", [(x, y), ...]) | None` —
  4 numbers = rect (None if w or h ≤ 0); 2 numbers or `(x, y, (r, g, b))` = point (None at (0, 0));
  a list/tuple of ≥ 3 points = polygon (None if every vertex is (0, 0)); anything else None
- `draw_marks(frame, marks, title=None) -> frame` — `marks` = `[(label, value)]`; returns a new BGR frame with
  each shape outlined (2 px, colour cycling `MARK_COLORS`), its label next to it, a crosshair (± 10 px) for points,
  and `title` on a dark banner top-left. The input frame is unchanged.

- [ ] Tests: `mark_shape` table (rect, zero rect, point, zero point, point_color, polygon, zero polygon, colour
  triple-looking dict/str → None); `draw_marks` on a black 200×200 frame draws the first colour on a rect's edge
  `(10..60, 20)` and not inside it; a point crosshair pixel set; uncalibrated marks draw nothing; input not mutated;
  title paints the banner.
- [ ] Implement with PIL `ImageDraw` (already imported), RGB↔BGR flip at the edges.
- [ ] Commit `Vision: draw a state's regions and points on a frame (PRO-91)`

### Task 2: `lib/screenshots.py` + the runner / session wiring

**Files:** Create `lib/screenshots.py`; Modify `lib/state_machine.py`, `lib/session.py`, `lib/events.py`;
Tests `tests/test_screenshots.py`, `tests/test_session_events.py`

**Interfaces — Produces:**
- `MAX_PER_SESSION = 20`
- `config_marks(table, config) -> callable(state) -> [(name, value)]` — `table`: `{state: [names]}`; a name
  `"ge.X"` reads `lib.ge_config.X`, `"energy.X"` reads `lib.energy_config.X`, others the bot's config; missing → skipped
- `Shooter(log_path, marks=None, cap=MAX_PER_SESSION)`; `.take(state, title) -> file name | None` (never raises)
- module current: `start(log_path, marks=None)`, `current()`, `finish()`, `take(state, title)`,
  `tag_error(exc, state)` (takes one for an `Exception`, stores the name on `exc._runetools_screenshot`, once)
- `events.error_fields(exc)` adds `screenshot` when the exception carries one
- `run_session(..., marks=None)`; `run_machine` emits `step` with `screenshot` for a failing result
- Grab = `screen.grab(screen.screen_rect())`, regions are monitor-1 coordinates = frame coordinates

- [ ] Tests (fake_screen, tmp log dir): `fail` step → PNG `<name>_<stamp>_1_<state>.png` exists, step event has
  `screenshot`; `ok` / `full` → no file, no field; cap 2 → third failure has no field; grab raising → step logged
  without field, run goes on; handler raising `RuntimeError` → `error` event with `screenshot`, ForceStop → none;
  setup raising → `error` with screenshot; `config_marks` skips missing names and reads `ge.` names from a stub;
  the drawn PNG has the state's rect colour on its edge.
- [ ] Implement; `run_machine` takes the shot after computing `seconds`.
- [ ] Full suite green. Commit `Session logs: screenshot on a failed step or an error, regions drawn (PRO-91)`

### Task 3: bot declarations + logreport

**Files:** Modify `tanner/states.py`, `tanner/run.py`, `choc/states.py`, `choc/run.py`,
`miner/golden_nuggets/states.py`, `miner/golden_nuggets/run.py`, `miner/varrock_exp/states.py`,
`miner/varrock_exp/run.py`, `lib/logreport.py`; Tests `tests/test_tanner_states.py`, `tests/test_logreport.py`

**Interfaces — Produces:** `STATE_MARKS` in each bot's `states.py` (tanner: `walk_to_tanner → TANNER_AREA,
CHARACTER, INVENTORY_CHECK`, `trade_ellis → ELLIS_REGION, TANNING_CHECK`, `walk_to_bank → BANK_REGION`,
`banking → BANK_REGION, BANK_CHECK, HIDE_TAB, BANK_SLOT_1, HIDE_COUNT_REGION, DEPOSIT_BTN`,
`recover → AMULET_SLOT, DOUBLE_DOORS_REGION, TP_BANK_REGION, TP_BOOTH_REGION, BANK_CHECK`,
`ge_bank → ge.GE_REGION, ge.BANK_CHECK, HIDE_TAB, HIDE_COUNT_REGION`, `restock → ge.GE_APPROACH_REGION,
ge.GE_REGION, ge.BANK_CHECK, ge.GE_CHECK`, `look_around → CHARACTER`); `summarize()` adds
`screenshots: [(ts, state, what, file)]`; `session` prints them as paths in the log's folder.

- [ ] Tests: every `STATE_MARKS` key is in `STATES` and every name exists in that bot's `config.example.py`
  (or `lib/ge_config.example.py` for `ge.`); `summarize` collects step + error screenshots; `main(["session",
  "latest"])` prints the absolute PNG path.
- [ ] Commit `Bots: regions per state for failure screenshots; logreport lists them (PRO-91)`

### Task 4: web app — store, serve, show

**Files:** Modify `webapp/apps/api/src/db/schema.ts` (+ generated migration), `ingest/apply.ts`, `stats.ts`,
`routes/stats.ts`, `packages/shared/src/index.ts`, `apps/web/src/pages/session-detail.tsx`; Tests
`apps/api/test/*` (ingest + route), e2e not needed.

**Interfaces — Produces:** `steps.screenshot`, `errors.screenshot` (text, null); `StepRow.screenshot`,
`ErrorRow.screenshot`, `SessionDetail.screenshots: {ts, state, label, file}[]` (all of the session's, oldest first);
`GET /api/sessions/:id/screenshots/:file` → `image/png` — 404 unless `file` matches `^[A-Za-z0-9_.-]+\.png$`,
is recorded in that session's steps/errors, the session's log is one `findLogFiles(getLogRoots())` finds, and the
PNG's real path sits in that log's real folder; behind the login (all /api routes are).

- [ ] Tests: ingest stores the field; detail returns `screenshots`; the route serves the bytes with
  `image/png`, 404s an unrecorded name, `..%2F` names, a missing file, an unknown session; 401 without login.
- [ ] Session page: "Screenshots" card (thumbnails linking to full size, caption time · state → result), the
  error card shows its screenshot; Playwright screenshot of the page with a dev API.
- [ ] Commit `Web app: failure screenshots on the session page (PRO-91)`

### Task 5: docs

- [ ] CLAUDE.md (layout line for lib/screenshots.py, a "Failure screenshots" design note, events list), webapp/README.md.
- [ ] Commit `Docs: failure screenshots (PRO-91)`
