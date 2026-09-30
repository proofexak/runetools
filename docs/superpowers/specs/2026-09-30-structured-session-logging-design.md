# Structured session logging — design

**Linear:** PRO-15 (sub-tasks PRO-51/52/53) · **Date:** 2026-09-30
**Branch:** `proofexak/pro-15-add-structured-session-logging` (from `main` 209de06)
**Status:** approved in brainstorming (approach A)

## Goal

Every session of every bot on the scaffold writes a machine-readable event log,
so the user can (1) debug a session after the fact — "why did last night's run
stop?" — and (2) track long-term stats across sessions. **Any unexpected error
that ends a bot must end up in a log**, wherever it happens.

User decisions: purpose = debugging + long-term stats; approach A (events
emitted by the shared session layer + a report command); explicit requirement
that unexpected errors are always logged.

Acceptance (PRO-15): session logs are machine-parseable (JSON lines); Tanner
and Miner emit the same format — here every bot on the scaffold does
(Tanner, Golden Nuggets, Varrock Exp, crafting). Choc is not on the scaffold
yet and keeps its text log only.

## Event log

File: `<bot dir>/log/<name>_YYYYMMDD_HHMMSS.jsonl`, same prefix as the existing
text `.log` (which is unchanged). One JSON object per line, flushed per line.
Launcher-level errors go to `log/launcher.jsonl` at the repo root (gitignored).

Common fields on every line: `ts` (ISO 8601, local time, milliseconds),
`session` (the file's `YYYYMMDD_HHMMSS`; `null` in launcher.jsonl), `bot`,
`event`.

| event | emitted by | extra fields |
|---|---|---|
| `session_start` | `run_session` | `params` (dict, JSON-safe), `pid` |
| `step` | `run_machine`, once per handler run | `state`, `result` (event returned), `seconds` (handler duration), `run` (`stats["run"]` after the step) |
| `pause` | `run_machine` pause gate, when `pause.wait()` blocked | `state`, `seconds` |
| `soft_stop` | `run_machine`, when the overlay Stop fires at a cycle start | `state` |
| `force_stop` | `run_session` on `pause.ForceStop` | `state` (last step) |
| `error` | `run_session` on any other exception (see below) | `where` (`"session"` or `"teardown"`), `state`, `type`, `message`, `traceback` |
| `session_end` | `run_session`, always (in `finally`) | `final` (`done` / `stopped` / `crashed` / `interrupted` / the bot's final state), `reason` (`model.stop_reason` if present), `last_step`, `stats` (JSON-safe copy of the stats dict), `active_seconds`, `paused_seconds` |

`active_seconds` = wall time from `session_start` to `session_end` minus
`paused_seconds` (sum of `pause` events).

### `lib/events.py`

```python
class EventLog:                      # one per session
    def __init__(self, path, bot, session): ...
    def emit(self, event, **fields): ...   # one JSON line, flushed
    def close(self): ...

def current() -> Optional[EventLog]   # the active session's log (None outside a session)
def launcher_error(bot, exc, where)   # append an `error` line to <root>/log/launcher.jsonl
def install_excepthooks()             # sys.excepthook + threading.excepthook -> launcher_error
```

Values that aren't JSON-serialisable are written with `repr()` (never raise
while logging). A failure to *write* a log line is swallowed after one stderr
warning — logging must never be what stops a bot.

## Error capture (the user's requirement)

1. **Inside a session** — model build, setup, any handler, the runner, or
   teardown: `run_session` catches `BaseException`. `pause.ForceStop` →
   `force_stop` + `session_end(final="stopped")`, not re-raised (as today).
   `KeyboardInterrupt` → `error` + `session_end(final="interrupted")`,
   re-raised. Any other exception → `error` (full traceback, current state) +
   `session_end(final="crashed")`, teardown still runs, then **re-raised** so
   `run_guarded` behaves as today (traceback in the text log, menu returns).
   An exception raised by teardown itself is logged as `error(where="teardown")`
   and does not mask the original one.
2. **Before a session log exists** (e.g. a bot's `start()` fails importing its
   missing config): `run_guarded(start, stats, bot=None)` calls
   `events.launcher_error(bot, exc, where="start")` when no session log was
   active — i.e. the error wasn't already recorded by `run_session`.
3. **Anything else** — launcher code, the overlay thread: both launchers call
   `events.install_excepthooks()` at startup; uncaught exceptions are written to
   `log/launcher.jsonl`, then the default hook runs.
4. A hard kill leaves a file with no `session_end`; the report shows it as
   `killed`.

## Bot changes

`run_session(..., bot, params=None)`: each bot's `run()` passes its name and
parameters — Tanner `{"hide_type", "start_from_ge", "restock_ge"}`, crafting
`{"items": n}`, Golden Nuggets / Varrock `{}`. `run_guarded` gets the bot name
from the launchers (`bot.name`).

## Report: `python -m lib.logreport`

| command | output |
|---|---|
| `sessions [--bot B] [--last N=20]` (default) | per session: start, bot, active/paused time, final, reason or last step, runs, runs per active hour, errors |
| `session <id\|latest> [--bot B]` | params; time + count per state; every non-`ok` step result with time; pauses; recoveries (steps in state `recover`); error + traceback; the end record |
| `stats [--bot B] [--since YYYY-MM-DD]` | per bot: sessions, active hours, total runs, runs per active hour, finals breakdown + top reasons, non-ok results per state (count and rate), recoveries per active hour, crash types; count of launcher errors |

Files read: `<root>/*/log/*.jsonl`, `<root>/*/*/log/*.jsonl`, `<root>/log/launcher.jsonl`.
Unparseable lines (e.g. a line cut by a hard kill) are skipped and counted.

Pure core (unit-tested): `parse_lines(lines) -> (events, bad_count)`,
`summarize(events) -> SessionSummary` (one session), `aggregate(summaries) ->
per-bot stats`. The CLI only globs files and formats text.

## Testing

- Events: `run_machine`/`run_session` with stub handlers and a temp log dir;
  normal end, soft stop, force stop, pause time, crash in a handler / setup /
  model build / teardown (crash → `error` + `session_end` `crashed`, original
  exception re-raised), KeyboardInterrupt → `interrupted`; every line valid
  JSON with the common fields.
- `run_guarded` writes `launcher.jsonl` when `start()` fails before a session;
  does not duplicate an error already recorded by a session; excepthooks
  record an uncaught exception.
- Report: `summarize`/`aggregate` on hand-written event lists (killed session,
  bad line, crash, runs/hour excludes paused time); CLI smoke test on a temp dir.
- Bots: stubbed dry runs of Tanner, Golden Nuggets, Varrock, crafting produce a
  well-formed `.jsonl`.

## Documentation

CLAUDE.md: event log format, where errors are recorded, `python -m lib.logreport`;
README: one line on the report command. `.gitignore`: root `log/`.
