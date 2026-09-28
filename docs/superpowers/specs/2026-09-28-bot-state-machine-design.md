# Bot control flow as an explicit state machine — design

**Linear:** PRO-12 (parent), PRO-42, PRO-43, PRO-44
**Date:** 2026-09-28
**Status:** approved in brainstorming, awaiting spec review

## Goal

Replace the implicit, sequential control flow in bot session loops with an
explicit state machine, starting with Tanner and Golden Nuggets, and make it the
documented standard for all bots.

Success criteria (from PRO-12, as clarified):

- Tanner's and Golden Nuggets' control flow is driven by explicit states and a
  declarative transition table, not by the order of `if not …: continue` blocks.
- O-pause keeps resuming exactly where it paused (no change in mechanism);
  recovery transitions land in the correct state.
- The pattern is documented in CLAUDE.md as the standard for new bots.

### Decisions made during brainstorming

- **Resume semantics: pause only.** O-pause already resumes mid-step because
  actions call `pause.wait()`. P force-stop still ends the session; the next start
  begins fresh. No state is persisted, in memory or on disk.
- **Approach: shared runner + per-bot transition table** (option A), built on the
  [`transitions`](https://github.com/pytransitions/transitions) library
  (0.9.3 — pure Python, Python 3.8 compatible, only dep `six`).
  `python-statemachine` was rejected: current versions need Python ≥ 3.10 and its
  class-declarative style doesn't match this codebase's plain-function style.
- **Handlers return events, the table picks the next state.** Guards (recovery
  charges, `RESTOCK_GE`, sack-full) are `conditions=` on transitions, relying on
  `transitions` evaluating same-trigger transitions in declaration order.

### Out of scope

- **Varrock Exp miner.** `miner/run.py` routes to `miner.varrock_exp.run`, which
  has never existed in git — selecting it crashes today. Building it is PRO-7.
- **Choc bot**, woodcutter, `lib/ge.py` internals, action functions in
  `tanner/tanner.py` and `miner/golden_nuggets/miner.py`.
- **Launcher/bot auto-discovery** — that's PRO-11.
- Uncommitted working-tree changes unrelated to this work (choc bot, O/P hotkey
  split in `lib/pause.py`, root `run.py` choc menu) are not part of this branch.

## Architecture

```
lib/state_machine.py            shared runner — knows nothing about any bot
tanner/states.py                Tanner states, transition table, session model
tanner/run.py                   setup + wire real handlers + run_machine() + summary
miner/golden_nuggets/states.py  Golden Nuggets states, table, session model
miner/golden_nuggets/run.py     same shape as tanner/run.py
tests/                          pytest, stub handlers, no game/screen needed
```

### `lib/state_machine.py` — the runner

```python
def run_machine(model, handlers, stats, final_states, cycle_start=None):
    """Drive a transitions-backed model until it reaches a final state."""
```

Loop, per iteration:

1. If `model.state in final_states`: return `model.state`.
2. If `model.state == cycle_start` and `stats.get("stop")`: `model.trigger("stop")`
   (every bot's table has `stop` from `cycle_start` to its stop state), then continue.
3. `pause.wait()` — blocks while O-paused; raises `pause.ForceStop` on P.
4. `stats["step"] = model.state`.
5. `event = handlers[model.state]()`.
6. `model.trigger(event)`.

Properties:

- `ForceStop` is not caught — it propagates to the bot's `run.py`.
- An event with no matching transition raises `transitions.MachineError`
  (the library default) — a missing table entry is a loud bug.
- A handler state missing from `handlers` raises `KeyError` — same reasoning.
- The runner does not touch `stats["run"]` or any other counter; bots own those.

The model is a plain object whose state is managed by a `transitions.Machine`
constructed in each bot's `states.py` (`Machine(model=..., states=..., transitions=...,
initial=..., auto_transitions=False)`).

### Handler injection

Each bot's `states.py` exposes a `build_machine(...)` that takes the handler
functions and any config values as arguments. `states.py` must **not** import the
bot's actions module or its gitignored `config.py` — this keeps it importable in
tests without a display, pyautogui, or calibrated config. `run.py` imports the
real actions/config and passes them in.

## Tanner

### States

`walk_to_tanner`, `trade_ellis`, `tanning`, `walk_to_bank`, `banking`, `restock`,
`recover`, and final states `done`, `stopped`.

### Transition table

Same-trigger transitions are listed in evaluation order.

| trigger   | source                                                  | dest             | condition             |
|-----------|---------------------------------------------------------|------------------|-----------------------|
| `ok`      | `walk_to_tanner`                                        | `trade_ellis`    |                       |
| `ok`      | `trade_ellis`                                           | `tanning`        |                       |
| `ok`      | `tanning`                                               | `walk_to_bank`   |                       |
| `ok`      | `walk_to_bank`                                          | `banking`        |                       |
| `ok`      | `banking`                                               | `walk_to_tanner` |                       |
| `restock` | `banking`                                               | `restock`        | `restock_enabled`     |
| `restock` | `banking`                                               | `done`           |                       |
| `ok`      | `restock`                                               | `recover`        | `has_charges`         |
| `ok`      | `restock`                                               | `stopped`        |                       |
| `fail`    | `restock`                                               | `stopped`        |                       |
| `fail`    | `walk_to_tanner`, `trade_ellis`, `walk_to_bank`, `banking` | `recover`     | `has_charges`         |
| `fail`    | `walk_to_tanner`, `trade_ellis`, `walk_to_bank`, `banking` | `stopped`     |                       |
| `ok`      | `recover`                                               | `walk_to_tanner` |                       |
| `fail`    | `recover`                                               | `stopped`        |                       |
| `stop`    | `walk_to_tanner`                                        | `stopped`        |                       |

`cycle_start = "walk_to_tanner"`, `final_states = {"done", "stopped"}`.

### Session model (`TannerSession`)

- `charges` — glory charges remaining; starts at 6. Decremented `on_enter_recover`.
- `skip_restock` — starts `True`; set `True` `on_enter_recover`; set `False` when
  leaving `banking` via `ok`.
- `runs` — incremented `on_enter_walk_to_tanner`, which also writes it to
  `stats["run"]` (the session holds a reference to the `stats` dict, passed to
  `build_machine`).
- `restock_enabled` — from `config.RESTOCK_GE`.
- `has_charges()` — `charges > 0`.
- `stop_reason` — short string set when entering `stopped`/`done` for the summary line.

### Handlers (in `tanner/run.py`, wrapping existing actions)

| state            | calls                                            | returns                          |
|------------------|--------------------------------------------------|----------------------------------|
| `walk_to_tanner` | `walk_to_tanner()`                               | `ok` / `fail`                    |
| `trade_ellis`    | `trade_ellis()`                                  | `ok` / `fail`                    |
| `tanning`        | `_wait_stopped()`                                | `ok`                             |
| `walk_to_bank`   | `walk_to_bank()`                                 | `ok` / `fail`                    |
| `banking`        | `do_bank(skip_restock_check=session.skip_restock)`; on `True` sleeps 0.5–1.2s | `ok` / `restock` / `fail` |
| `restock`        | `run_ge_flow(config.HIDE_TYPE, on_complete=lambda: True)` | `ok` / `fail`           |
| `recover`        | `recover()`                                      | `ok` / `fail`                    |

### Startup

- Normal: `initial = "walk_to_tanner"`.
- "Run from GE": `initial = "recover"`. The startup teleport now consumes a charge
  and a failure stops the session.

### Behaviour changes vs. today (approved)

1. **Every glory teleport consumes a charge.** Today only failure recoveries are
   counted; the post-GE `recover()` and the "Run from GE" startup `recover()` are
   not, so the bot can believe it has charges it doesn't. Now all three go through
   the `recover` state.
2. **"Run from GE" startup failure stops the session.** Today its result is
   ignored and the bot walks toward Ellis from wherever it ended up.
3. Dead `result == "done"` branches are removed (`recover()` never returns it).

Unchanged: soft stop only takes effect at the start of a trip; first bank of a
session skips the restock check; run counter per trip; 0.5–1.2s gap between trips;
`orient_west()` once at startup; `ForceStop` caught in `run.py` with the same
session summary.

## Golden Nuggets

### States

`seek_vein`, `mining`, `deposit`, `process_sack`, and final state `stopped`.

### Transition table

| trigger     | source         | dest           | condition   |
|-------------|----------------|----------------|-------------|
| `full`      | `seek_vein`    | `deposit`      |             |
| `ok`        | `seek_vein`    | `mining`       |             |
| `not_found` | `seek_vein`    | `seek_vein`    |             |
| `full`      | `mining`       | `deposit`      |             |
| `ok`        | `mining`       | `seek_vein`    |             |
| `ok`        | `deposit`      | `process_sack` | `sack_full` |
| `ok`        | `deposit`      | `seek_vein`    |             |
| `fail`      | `deposit`      | `seek_vein`    |             |
| `ok`        | `process_sack` | `seek_vein`    |             |
| `stop`      | `seek_vein`    | `stopped`      |             |

`cycle_start = "seek_vein"`, `final_states = {"stopped"}`.

### Session model (`NuggetsSession`)

- `vein_pos` — set by the `seek_vein` handler, read by `mining`.
- `vein_n` — veins clicked, for logging.
- `hopper_deposits` — incremented by the `deposit` handler on success, reset to 0
  by the `process_sack` handler after `process_full_sack()` returns; the handlers
  mirror it to `stats["sack"]`.
- `sack_full()` — `hopper_deposits >= 4`.

### Handlers (in `miner/golden_nuggets/run.py`)

| state          | does (same as today's loop body)                                                                                   | returns                     |
|----------------|--------------------------------------------------------------------------------------------------------------------|-----------------------------|
| `seek_vein`    | if `count_filled_slots() >= 27` → `full`; else `click_nearest_vein()`; `None` → log, sleep 3s → `not_found`; else store pos, `wait_stopped()`, `vein_n += 1` | `full` / `ok` / `not_found` |
| `mining`       | `wait_for_vein_depletion(session.vein_pos, stats)`; reason `"full"` → `full`                                        | `full` / `ok`               |
| `deposit`      | `deposit_to_hopper()`; on failure `orient_south()` → `fail`; on success `hopper_deposits += 1`, `orient_east()`, `check_and_fix_struts()`, and if not sack-full `orient_south()` | `ok` / `fail` |
| `process_sack` | `process_full_sack(stats)`; reset `hopper_deposits` and `stats["sack"]`                                             | `ok`                        |

Startup unchanged: log setup, 3s delay, `orient_south()`, log starting inventory.

### Behaviour changes vs. today (approved)

1. **O-pause takes effect between every step**, not only at the top of the loop
   (Golden Nuggets' actions never call `pause.wait()`; the runner does, per state).
2. **P force-stop is caught** in `run.py` with a session summary. Today
   `ForceStop` escapes Golden Nuggets' loop into the root `run.py` loop.
3. `mining --full--> deposit` goes directly to the hopper instead of via the
   top-of-loop inventory check — same destination.

## Dependencies

- `requirements.txt`: add `transitions`.
- New `requirements-dev.txt`: `-r requirements.txt` + `pytest`.

## Testing

### Automated (pytest, `tests/`)

Stub handlers return scripted event sequences; `pause.wait` is monkeypatched.
No display, pyautogui, or calibrated config is required.

`tests/test_state_machine.py` — runner:
- calls `pause.wait()` once before each handler
- `stats["step"]` matches the state whose handler is running
- returns the final state name when reached
- unknown event → `MachineError`
- `ForceStop` raised by `pause.wait` or a handler propagates
- soft stop only fires at `cycle_start`, not mid-cycle

`tests/test_tanner_states.py`:
- full happy-path trip returns to `walk_to_tanner`; `runs` increments per trip
- `fail` from each of the four action states → `recover` while charges remain
- charges exhausted → `fail` goes to `stopped`
- `restock` with `restock_enabled` → `restock` → `recover`; without → `done`
- `restock --ok-->` with zero charges → `stopped`
- "Run from GE" initial state `recover` consumes a charge
- `skip_restock`: `True` at start, `False` after a successful bank, `True` after recover

`tests/test_golden_nuggets_states.py`:
- vein → mining → seek → full → deposit → seek cycle
- fourth successful deposit → `process_sack`, counter reset afterwards
- failed deposit → `seek_vein`, counter unchanged
- `not_found` loops on `seek_vein`
- soft stop fires at `seek_vein`

### Live, in game (user)

Tanner: several normal trips; one forced failure (e.g. hide Ellis's highlight) to
observe recovery; one "Run from GE" start. GE restock run optional (costs gold).

Golden Nuggets: several veins and at least one full-sack processing cycle; O-pause
mid-cycle; P force-stop returns to the menu without a traceback.

## Documentation

Add a **"Bot control flow"** section to CLAUDE.md: the runner contract, handlers
return events, transition table with conditions, handler injection so `states.py`
stays test-importable, soft-stop via `cycle_start`, and that this is the standard
for all new bots. Update the Tanner and Miner entries under "What's working / WIP".
