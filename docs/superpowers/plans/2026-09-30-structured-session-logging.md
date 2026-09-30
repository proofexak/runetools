# Structured Session Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every scaffold bot session writes a JSON-lines event log, every unexpected error ends up in a log, and `python -m lib.logreport` answers "what happened" and "how are the bots doing over time".

**Architecture:** `lib/events.py` owns the per-session `EventLog` and the launcher-level error log; `run_session`/`run_machine` emit events; `run_guarded` and process excepthooks catch what happens outside a session; `lib/logreport.py` is a pure parse/summarize/aggregate core with a thin CLI.

**Tech Stack:** Python 3.8 stdlib (json, datetime, traceback, argparse, glob), pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-structured-session-logging-design.md`

## Global Constraints

- Common fields on every line: `ts` (ISO 8601 local, milliseconds), `session` (`YYYYMMDD_HHMMSS` or `null`), `bot`, `event`.
- Event names and fields exactly as the spec's table: `session_start`, `step`, `pause`, `soft_stop`, `force_stop`, `error`, `session_end`; finals `done` / `stopped` / `crashed` / `interrupted` / bot final state; report shows a missing end as `killed`.
- Logging never raises into the bot: non-serialisable values → `repr()`; a failed write warns once on stderr and is otherwise ignored.
- The `.jsonl` shares the text log's prefix and timestamp; text logs unchanged.
- Launcher log: `<repo root>/log/launcher.jsonl` (root `log/` gitignored).
- No test touches the real screen/mouse/keyboard; temp dirs for all log files.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Exception inside teardown after a handler crash** — the handler's error is the one re-raised; both are logged; `session_end` still written.
2. **Crash before any step** (model build or setup raises) — `error` + `session_end` `crashed` with `last_step` `"starting"`.
3. **Unwritable log directory** — the bot still runs; one warning, no exception.
4. **Error already recorded by a session** — `run_guarded` does not add a duplicate to launcher.jsonl.
5. **Session file cut mid-line by a hard kill** — report skips the partial line, shows the session as `killed`.

---

### Task 1: `lib/events.py`

**Files:** Create `lib/events.py`; test `tests/test_events.py`.
**Produces:** `EventLog(path, bot, session)` with `.emit(event, **fields)` and `.close()`; `events.start(path, bot, session) -> EventLog` (sets current), `events.current() -> Optional[EventLog]`, `events.finish()` (closes + clears current); `events.launcher_error(bot, exc, where, root=ROOT)`; `events.install_excepthooks(root=ROOT)`; `ROOT` = repo root.

- [ ] Tests: emitted line is JSON with `ts` (parses with `datetime.fromisoformat`), `session`, `bot`, `event` + fields; non-serialisable field → its `repr`; each emit is flushed (file readable before `close`); unwritable path (a directory as path) → no exception, one stderr warning across two emits; `current()` set by `start`, cleared by `finish`; `launcher_error` appends `{"event":"error","where":…, "type","message","traceback","bot","session":null}` to `<tmp>/log/launcher.jsonl`, creating `log/`; `install_excepthooks(root=tmp)` then calling `sys.excepthook(type, exc, tb)` writes a launcher error and still calls the previous hook (monkeypatch `sys.__excepthook__`/previous hook to a recorder); same for `threading.excepthook` with an `ExceptHookArgs`-like object.
- [ ] Watch fail → implement → PASS → commit.

### Task 2: Emit from `run_machine` and `run_session`; capture every in-session error

**Files:** `lib/state_machine.py`, `lib/session.py`, `lib/log.py`; tests `tests/test_session_events.py`.
**Consumes:** Task 1 API. **Produces:** `run_session(..., bot, params=None)` (both keyword, `bot` required); `log.setup(prefix, stamp=None) -> file` (stamp → exact filename timestamp).

- [ ] Tests (stub handlers, `tmp_path` log prefix, patched `time.sleep`): normal run → `session_start`, one `step` per handler with `result`/`seconds`/`run`, `session_end` `final="end"`-style final with `active_seconds`, `paused_seconds`; blocked `pause.wait` (stub returning True after advancing a fake clock) → `pause` event and `paused_seconds`; overlay Stop → `soft_stop`; ForceStop → `force_stop` + `session_end` `stopped`, not raised; handler `RuntimeError` → `error` (where `session`, state = handler's state, traceback contains the message) + `session_end` `crashed`, `RuntimeError` re-raised; model build raises → `crashed`, `last_step` `"starting"`; teardown raises after a handler crash → two `error` lines (`session`, `teardown`), the handler's exception is re-raised; `KeyboardInterrupt` → `interrupted`, re-raised; `.jsonl` path = text log path with `.jsonl`; `events.current()` is None after the session in every case. Existing `tests/test_session.py` keeps passing (add `bot="test"` where it calls `run_session`).
- [ ] Implement; runner emits via `events.current()` (no-op when None, so `run_machine` still works standalone). Suite green; commit.

### Task 3: Errors outside a session

**Files:** `lib/bots.py` (`run_guarded(start, stats, bot=None)`), `run.py`, `crafting_run.py` (pass `bot.name`, call `events.install_excepthooks()` at startup); tests in `tests/test_bots.py`.

- [ ] Tests: `start` raising `ModuleNotFoundError` before any session → one launcher error with `bot` and `where="start"`, returns False; `start` that runs a `run_session` which crashes → returns False and launcher.jsonl gets **no** line (already recorded; detect via a flag the session sets on the exception, e.g. `exc._logged = True`).
- [ ] Implement; suite green; `python -c` import checks of `lib.bots`; commit.

### Task 4: Bots identify themselves

**Files:** `tanner/run.py` (`bot="tanner"`, params `hide_type`, `start_from_ge`, `restock_ge`), `miner/golden_nuggets/run.py` (`"golden_nuggets"`), `miner/varrock_exp/run.py` (`"varrock_exp"`), `crafting/run.py` (`"crafting"`, `{"items": n}` non-skipped count).

- [ ] Stubbed dry run per bot (as in earlier sub-projects, example configs where the real one is missing) into a temp log dir: the `.jsonl` has `session_start` with the bot name/params, `step` lines, `session_end`; a forced handler crash in one bot's dry run yields `crashed` + traceback. Suite green; commit.

### Task 5: `lib/logreport.py`

**Files:** Create `lib/logreport.py` (`python -m lib.logreport`); test `tests/test_logreport.py`.
**Produces:** `parse_lines(lines) -> (List[dict], int)`; `summarize(events) -> dict` (keys: `session`, `bot`, `start`, `params`, `final` (`killed` if no end), `reason`, `last_step`, `active_seconds`, `paused_seconds`, `runs`, `runs_per_hour`, `errors` (list), `state_time` {state: seconds}, `state_counts`, `non_ok` [(ts, state, result)], `pauses`, `recoveries`); `aggregate(summaries) -> {bot: {...}}` (keys: `sessions`, `active_hours`, `runs`, `runs_per_hour`, `finals` Counter, `reasons` Counter, `non_ok_by_state` {state: (count, rate)}, `recoveries_per_hour`, `crash_types` Counter); `main(argv, root=ROOT)`.

- [ ] Tests: `parse_lines` skips a truncated line and counts it; `summarize` of a normal session (runs/hour uses active time only), a crashed one (error + traceback kept), a killed one (no end → `killed`, active time = last event − start); `aggregate` over two bots; `non_ok` rate = non-ok results / steps in that state; CLI smoke: temp root with two session files + launcher.jsonl → `sessions`, `session latest`, `stats` print without error and include the bot names, `crashed`, and the launcher error count.
- [ ] Watch fail → implement → PASS → commit.

### Task 6: Docs + ignore

- [ ] `.gitignore`: `/log/`. CLAUDE.md: event log format + where each kind of error is recorded + report commands (under Bot contract / Vision section); README: one line on `python -m lib.logreport`. Suite green; commit.
