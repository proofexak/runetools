# Varrock Exp + Crafting on the Scaffold — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Move `miner/varrock_exp` and `crafting` onto the state machine + scaffold.
**Architecture:** as in the spec; reuse `run_machine`, `run_session`, `lib/bots`.
**Tech Stack:** Python 3.8, transitions, pytest.
**Spec:** `docs/superpowers/specs/2026-09-28-new-bots-on-scaffold-design.md`

## Global Constraints

- Python 3.8; `states.py`/`bot.py` import nothing heavy; never run anything that moves the mouse or opens Tk.
- Tests that need a bot's config load its `config.example.py` via a `tests/conftest.py` fixture (`example_config`), never the user's calibrated file.
- Keep main's in-game behaviour for both bots except what the spec lists.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Crafting exits by any path (done, Stop, P/End, exception) → shift released.
2. Crafting must not appear in the OSRS menu; OSRS bots must not appear in the crafting launcher.
3. Varrock overlay Stop pressed after the first drop → stops before the second rock (main did).
4. Mining submenu: each sub-bot's ⚙ opens its own editor.
5. Crafting with zero non-skipped items → grabs currency, reports done, releases shift.

---

### Task 1: Shared lib extensions
Files: `lib/pause.py`, `lib/session.py`, `lib/state_machine.py`, `lib/bots.py`, `tests/conftest.py`; tests in `tests/test_pause.py`, `test_session.py`, `test_state_machine.py`, `test_bots.py`.
- [ ] Tests: `pause.hint()` for default O/P and for `setup`-less override (set module keys) P/None + stop_key "end" → `"Press P to pause, End to force-stop."`; `run_session` prints `switch to the game` when `game="the game"`; `teardown` called once on normal end, ForceStop, and a raising handler (exception still propagates); runner `cycle_start={"a","b"}` stops at either; `discover(suite=)` filter; `build_menu(flat=True)`; launch `configure` → side button `("⚙", fn)`; alt+configure → `ValueError`.
- [ ] Implement; suite green; commit.

### Task 2: Varrock Exp
Files: `git mv miner/varrock_exp/miner.py miner/varrock_exp/actions.py`; create `miner/varrock_exp/states.py`; rewrite `miner/varrock_exp/run.py`; update `miner/varrock_exp/config_editor.py` (save_attr), `miner/bot.py`; delete `miner/miner.py`, `miner/config.example.py`, `miner/config_editor.py`; tests `tests/test_varrock_states.py`, `tests/test_varrock_actions.py`.
- [ ] Tests: table cycle; `not_found` from each mine state; Stop at `mine_first` and at `mine_second`; ore counted only on second drop found; `wait_and_drop` calls `pause.wait` each poll (example config).
- [ ] Implement; dry run with stubs; suite green; commit.

### Task 3: Crafting
Files: `git mv crafting/crafting.py crafting/actions.py`; create `crafting/states.py`, `crafting/bot.py`; rewrite `crafting/run.py`, `crafting_run.py`; `crafting/config_editor.py` (save_attr); tests `tests/test_crafting_states.py`.
- [ ] Tests: skips `skip` items; zero items → done; per-item stats run/step; Stop before next item; `has_more` boundary.
- [ ] Implement; dry run (teardown on done/ForceStop/crash); crafting menu dry build; suite green; commit.

### Task 4: Docs
CLAUDE.md (suites, both bots, launchers, deleted legacy miner files), README bots list. Commit.
