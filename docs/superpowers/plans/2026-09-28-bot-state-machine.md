# Bot State Machine (sub-project 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drive Tanner and Golden Nuggets from explicit `transitions`-backed state machines through one shared runner, and document it as the standard bot pattern.

**Architecture:** `lib/state_machine.py` holds a bot-agnostic `run_machine()` loop (pause gate → handler → fire returned event). Each bot has a `states.py` (states, transition table, session model, pure event-mapping helpers — no screen/config imports) and a `run.py` that builds real handlers as closures over the session and calls the runner.

**Tech Stack:** Python 3.8 (`.venv`), `transitions` 0.9.3, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-28-bot-state-machine-design.md` — read it first; the transition tables there are authoritative.

## Global Constraints

- Python 3.8: no `match`, no `X | Y` type unions, no `list[str]` in annotations at runtime.
- All commands run from repo root with `.venv/bin/python`.
- `Machine(..., auto_transitions=False)` everywhere; triggers fired only via `model.trigger(name)`.
- `states.py` files must not import `pyautogui`, `mss`, the bot's actions module, or its gitignored `config.py`.
- Same-trigger transitions are declared in exactly the order of the spec's tables (conditions depend on it).
- Do not modify `tanner/tanner.py`, `miner/golden_nuggets/miner.py`, `lib/ge.py`, `choc/`, `woodcutter/`.
- Match surrounding code style: module docstring, `sys.path.insert` header in `run.py` files, `print`/`_log` messages in the existing tone.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A wrapped action returns something unexpected** (`None`, `"restock"` from the wrong place) — a handler must never hand `None` to `trigger`; mapping lives in tested pure helpers (`bank_event`, `ok_or_fail`, `mining_event`).
2. **Recovery charge boundary** — exactly 6 recoveries succeed, the 7th `fail` goes to `stopped`; "Run from GE" consumes one of the 6.
3. **Soft stop pressed mid-trip** — trip (including any restock → recover) finishes, then stops at `walk_to_tanner`/`seek_vein`; never mid-trip.
4. **Stale `stats["stop"]` from a previous session** — each `run()` resets it to `False` before building the machine.
5. **P during Golden Nuggets** — returns to the menu with a summary line, no traceback.

---

### Task 0: Commit pending working-tree changes

**Files:** already modified/untracked — `.gitignore`, `CLAUDE.md`, `lib/mouse.py`, `lib/pause.py`, `run.py`, `tanner/run.py`, `choc/` (tracked parts only — `choc/config.py` and `choc/log/` are gitignored), `test_choc_sequence.py`, `RuneTools.desktop`.

- [ ] **Step 1: Confirm nothing ignored slips in**

Run: `git status --short && git check-ignore choc/config.py choc/log`
Expected: both paths printed by `check-ignore`; status shows only the files listed above.

- [ ] **Step 2: Commit**

```bash
git add .gitignore CLAUDE.md lib/mouse.py lib/pause.py run.py tanner/run.py choc test_choc_sequence.py RuneTools.desktop
git commit -m "Add chocolate grind bot, split O pause / P force-stop hotkeys

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: `git status --short` is empty afterwards.

---

### Task 1: Dependencies, pytest setup, shared runner

**Files:**
- Modify: `requirements.txt` (append `transitions`)
- Create: `requirements-dev.txt` (`-r requirements.txt`, `pytest`)
- Create: `pytest.ini` (`testpaths = tests`, `pythonpath = .` — keeps the root-level live `test_*.py` scripts out of collection)
- Create: `lib/state_machine.py`
- Test: `tests/test_state_machine.py`

**Interfaces:**
- Produces: `run_machine(model, handlers, stats, final_states, cycle_start=None) -> str` — returns the final state name. `handlers: dict[str, Callable[[], str]]`.

- [ ] **Step 1: Install deps**

Run: `.venv/bin/pip install -r requirements-dev.txt`
Expected: `transitions` and `pytest` installed; `.venv/bin/python -c "import transitions; print(transitions.__version__)"` prints `0.9.3`.

- [ ] **Step 2: Write failing tests** in `tests/test_state_machine.py`

Fixtures: a tiny machine built in the test (`a --ok--> b --ok--> a`, `a --stop--> end`, `b --quit--> end`, final `{"end"}`), `pause.wait` monkeypatched to a counter, handlers returning scripted events from a list.

```python
def test_calls_pause_wait_before_each_handler(): ...      # 3 handler calls -> 3 waits, waits precede calls
def test_stats_step_names_running_state(): ...            # handler records stats["step"] == its own state
def test_returns_final_state(): ...                       # a->b->end returns "end"; stats["step"] == "b"
def test_undeclared_event_raises_attribute_error(): ...   # handler returns "nope" -> AttributeError
def test_invalid_event_for_state_raises_machine_error(): ...  # in a, handler returns "quit" -> MachineError
def test_force_stop_from_pause_propagates(): ...          # pause.wait raises ForceStop -> propagates, no handler called
def test_force_stop_from_handler_propagates(): ...
def test_soft_stop_only_at_cycle_start(): ...             # stats["stop"]=True set by b's handler; b finishes, a's handler never runs, returns "end"
def test_soft_stop_ignored_without_cycle_start(): ...     # cycle_start=None -> stop flag has no effect
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_state_machine.py -v`
Expected: collection error — `lib.state_machine` not found.

- [ ] **Step 4: Implement `run_machine` in `lib/state_machine.py`**

Loop exactly as spec § "lib/state_machine.py — the runner" steps 1–6. Call `pause.wait()` via the module (`import lib.pause as pause`) so monkeypatching works. No try/except.

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt requirements-dev.txt pytest.ini lib/state_machine.py tests/test_state_machine.py
git commit -m "Add shared state-machine runner on transitions (PRO-42)"
```

---

### Task 2: Tanner states and session model

**Files:**
- Create: `tanner/states.py`
- Test: `tests/test_tanner_states.py`

**Interfaces:**
- Consumes: `run_machine` (tests drive the machine through it with stub handlers).
- Produces:
  - `STATES`, `FINAL_STATES = {"done", "stopped"}`, `CYCLE_START = "walk_to_tanner"`, `MAX_CHARGES = 6`
  - `class TannerSession` — attributes `charges`, `skip_restock`, `runs`, `restock_enabled`, `start_from_ge`, `stats`; condition method `has_charges()`; `restock_enabled` and `start_from_ge` are used directly as condition names (plain bool attributes — verified to work in 0.9.3); callbacks `on_enter_walk_to_tanner`, `on_enter_recover`, `clear_skip_restock`.
  - `build_machine(stats, restock_enabled, start_from_ge, charges=MAX_CHARGES) -> TannerSession` — constructs `Machine`, fires `begin`, returns session.
  - `ok_or_fail(result) -> str` — truthy → `"ok"`, else `"fail"`.
  - `bank_event(result) -> str` — `"restock"` → `"restock"`, truthy → `"ok"`, else `"fail"`.

- [ ] **Step 1: Write failing tests** in `tests/test_tanner_states.py`

Helper: `drive(session, events)` — runs `run_machine` with handlers that pop from `events` (any state), `pause.wait` monkeypatched to no-op; last event sequence ends in a final state.

```python
def test_begin_normal_enters_walk_to_tanner_and_counts_run():
    s = build_machine({}, restock_enabled=True, start_from_ge=False)
    assert s.state == "walk_to_tanner" and s.runs == 1 and s.stats["run"] == 1 and s.charges == 6

def test_begin_from_ge_enters_recover_and_uses_charge():
    s = build_machine({}, True, start_from_ge=True)
    assert s.state == "recover" and s.charges == 5 and s.skip_restock is True

def test_happy_trip_loops_back():  # ok x5 from walk_to_tanner -> walk_to_tanner, runs == 2, skip_restock False

@pytest.mark.parametrize("state_events", [[], ["ok"], ["ok","ok","ok"], ["ok","ok","ok","ok"]])
def test_fail_in_action_state_goes_to_recover(state_events):  # reach walk_to_tanner/trade_ellis/walk_to_bank/banking, "fail" -> recover, charges 5

def test_six_recoveries_then_stopped():  # fail/ok(recover) six times, seventh fail -> stopped, charges == 0
def test_recover_fail_stops():
def test_restock_enabled_goes_restock_then_recover():  # banking --restock--> restock --ok--> recover, charges 5, skip_restock True
def test_restock_disabled_goes_done():
def test_restock_ok_without_charges_stops():  # charges=0 via build_machine(..., charges=0)
def test_restock_fail_stops():
def test_skip_restock_lifecycle():  # True at start, False after banking ok, True after recover
def test_soft_stop_at_walk_to_tanner():  # stats["stop"]=True during banking handler -> returns "stopped", stats["step"] == "banking"

def test_bank_event_mapping():
    assert [bank_event(r) for r in ("restock", True, False, None)] == ["restock", "ok", "fail", "fail"]

def test_ok_or_fail_mapping():
    assert [ok_or_fail(r) for r in (True, 1, False, None)] == ["ok", "ok", "fail", "fail"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_tanner_states.py -v`
Expected: collection error — `tanner.states` not found.

- [ ] **Step 3: Implement `tanner/states.py`**

Transition list copied row-for-row from the spec's Tanner table (including both `begin` rows, `start` state). Banking→walk_to_tanner `ok` row gets `"after": "clear_skip_restock"`. `on_enter_walk_to_tanner` increments `runs` and writes `stats["run"]`. `on_enter_recover` decrements `charges`, sets `skip_restock = True`. Imports: `transitions.Machine` only.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass (Task 1 + Task 2).

- [ ] **Step 5: Commit**

```bash
git add tanner/states.py tests/test_tanner_states.py
git commit -m "Add Tanner state machine table and session model (PRO-43)"
```

---

### Task 3: Rewire `tanner/run.py` onto the runner

**Files:**
- Modify: `tanner/run.py` (whole `run()` body)

**Interfaces:**
- Consumes: `build_machine`, `ok_or_fail`, `bank_event`, `FINAL_STATES`, `CYCLE_START` from `tanner.states`; `run_machine` from `lib.state_machine`; existing actions from `tanner.tanner`; `run_ge_flow` from `lib.ge`.
- Produces: `run(stats, start_from_ge=False)` — signature unchanged (root `run.py` calls it).

- [ ] **Step 1: Rewrite `run()`**

Keep: log setup, hide-type print, the O/P hint + 3s sleep, `stats.update({"run": 0, "step": "starting", "start": None, "stop": False})`, `pause.reset()`, `orient_west()`, `stats["start"]`, the `except pause.ForceStop` message, the elapsed-time summary.
Replace the loop with: `session = build_machine(stats, config.RESTOCK_GE, start_from_ge)`, a handlers dict per the spec's Tanner handler table (each wrapped with `ok_or_fail` / `bank_event`; `tanning` returns `"ok"` after `_wait_stopped()`; `banking` sleeps `random.uniform(0.5, 1.2)` only when the event is `"ok"`; `restock` passes `on_complete=lambda: True`), then `final = run_machine(session, handlers, stats, FINAL_STATES, CYCLE_START)`.
Summary line: `Session ended ({final} after {last_step}). Runs: {session.runs} | Time: HH:MM:SS` — capture `last_step = stats["step"]` right after `run_machine` returns (or at `ForceStop`), then set `stats["step"] = final` (or `"stopped"` on ForceStop). Keep the `"All hides tanned"`-style message for `done`: `"[DONE] Hides depleted and restock disabled — stopping."`. Remove `recover` import only if unused (it's used by the `recover` handler — keep).

- [ ] **Step 2: Import smoke check**

Run: `.venv/bin/python -c "import tanner.run"`
Expected: no output, exit 0 (uses the local calibrated `tanner/config.py`).

- [ ] **Step 3: Full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tanner/run.py
git commit -m "Drive Tanner session from the state machine (PRO-43)"
```

---

### Task 4: Golden Nuggets states and session model

**Files:**
- Create: `miner/golden_nuggets/states.py`
- Test: `tests/test_golden_nuggets_states.py`

**Interfaces:**
- Produces:
  - `STATES`, `FINAL_STATES = {"stopped"}`, `CYCLE_START = "seek_vein"`, `DEPOSITS_PER_SACK = 4`
  - `class NuggetsSession` — attributes `vein_pos` (None), `vein_n` (0), `hopper_deposits` (0), `stats`; condition `sack_full()` → `hopper_deposits >= DEPOSITS_PER_SACK`.
  - `build_machine(stats) -> NuggetsSession` — initial `seek_vein` (no entry callbacks needed, so no `start` state).
  - `mining_event(reason) -> str` — `"full"` → `"full"`, anything else → `"ok"`.

- [ ] **Step 1: Write failing tests** in `tests/test_golden_nuggets_states.py`

Handlers in tests mutate the session the way the real ones will (e.g. stub `deposit` does `s.hopper_deposits += 1` before returning `"ok"`).

```python
def test_vein_mining_cycle():            # seek ok -> mining ok -> seek full -> deposit ok -> seek
def test_mining_full_goes_to_deposit():
def test_fourth_deposit_processes_sack():  # after 4th ok deposit -> process_sack; stub resets counter; -> seek_vein
def test_third_deposit_returns_to_seek():
def test_failed_deposit_returns_to_seek_counter_unchanged():
def test_not_found_loops_on_seek_vein():
def test_soft_stop_at_seek_vein():       # stop set during mining -> "stopped", stats["step"] == "mining"

def test_mining_event_mapping():
    assert [mining_event(r) for r in ("full", "depleted", "idle", None)] == ["full", "ok", "ok", "ok"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_golden_nuggets_states.py -v`
Expected: collection error — module not found.

- [ ] **Step 3: Implement** — table row-for-row from the spec's Golden Nuggets table.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add miner/golden_nuggets/states.py tests/test_golden_nuggets_states.py
git commit -m "Add Golden Nuggets state machine table and session model (PRO-44)"
```

---

### Task 5: Rewire `miner/golden_nuggets/run.py` onto the runner

**Files:**
- Modify: `miner/golden_nuggets/run.py`

**Interfaces:**
- Consumes: `build_machine`, `mining_event`, `FINAL_STATES`, `CYCLE_START`, `DEPOSITS_PER_SACK` from `miner.golden_nuggets.states`; `run_machine`; existing actions (same import list as today).
- Produces: `run(stats)` — signature unchanged.

- [ ] **Step 1: Rewrite `run()`**

Keep: log setup, `_log` start message + 3s sleep, `stats.update({"run": 0, "sack": 0, "step": "starting", "start": session_start, "stop": False})`, `pause.reset()`, `orient_south()`, starting-inventory log.
Handlers exactly per the spec's Golden Nuggets handler table (same calls, same log lines, same 3s retry sleep, same orient calls in the same branches as today's loop). `deposit` success increments `session.hopper_deposits`, mirrors `stats["sack"]`, logs `Hopper deposit #n/4`; calls `orient_south()` only when not `session.sack_full()`. `process_sack` resets counter and `stats["sack"]`.
Wrap `run_machine(...)` in `try/except pause.ForceStop` → `_log("Force stopped via overlay.")`. Final line: `_log(f"Session ended ({final} after {last_step}). Veins: {session.vein_n} | Ores: {stats['run']} | Time: {_elapsed(session_start)}")`.

- [ ] **Step 2: Import smoke check**

Run: `.venv/bin/python -c "import miner.golden_nuggets.run"`
Expected: exit 0. If `miner/golden_nuggets/config.py` is missing locally, report that instead of creating it.

- [ ] **Step 3: Full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add miner/golden_nuggets/run.py
git commit -m "Drive Golden Nuggets session from the state machine (PRO-44)"
```

---

### Task 6: Document the pattern

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md` only if it has an install section listing packages (add `transitions`; mention `requirements-dev.txt` + `.venv/bin/python -m pytest`)

- [ ] **Step 1: Update CLAUDE.md**

- Repo layout: add `lib/state_machine.py`, `tanner/states.py`, `miner/golden_nuggets/states.py`, `tests/`, and `choc/` (brief — chocolate grind bot, not yet on the state machine).
- New `**Bot control flow (standard for all bots)**` under Key design decisions, ≤ 25 lines: handlers return events; transition table with ordered `conditions`; `run_machine` contract (pause gate per state, `stats["step"]`, soft stop at `cycle_start`, `ForceStop` propagates); `states.py` import rule; `start`/`begin` trick for initial `on_enter`; `MachineError` vs `AttributeError`; tests via stub handlers (`.venv/bin/python -m pytest`).
- What's working / WIP: Tanner line notes state machine + glory-charge accounting change; add Golden Nuggets line; note Varrock Exp menu entry crashes (module missing, PRO-7).

- [ ] **Step 2: Verify**

Run: `.venv/bin/python -m pytest -q && git diff --stat`
Expected: all pass; only doc files changed.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "Document state-machine bot pattern as the standard (PRO-12)"
```

---

### Task 7: Live verification (human, in game) and Linear

Not automatable — hand the checklist to the user and wait for results before closing issues.

- [ ] Tanner: ≥ 3 normal trips; overlay step label follows states.
- [ ] Tanner: forced failure (hide Ellis's RuneLite highlight) → `recover` runs, charge count drops, bot resumes.
- [ ] Tanner: "Run from GE" start → recover → normal trips.
- [ ] Tanner: overlay Stop mid-trip → finishes trip, ends `stopped after banking`.
- [ ] Golden Nuggets: several veins, ≥ 1 full-sack cycle; O-pause between steps; P → back to menu, no traceback.
- [ ] Optional: one GE restock (costs gold).
- [ ] On success: PRO-42/43/44 → Done with a comment linking the branch; PRO-12 → Done after merge.
