# Standard Bot Scaffold (sub-project 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every bot one contract (`bot.py` descriptor + `run.py`/`states.py`/`actions.py`/config trio), move duplicated helpers into `lib/`, and build the overlay menu from discovered bots.

**Architecture:** `lib/bots.py` discovers `<pkg>/bot.py` descriptors and builds the overlay menu; `lib/session.py` owns the session lifecycle around `run_machine`; small shared helpers (`camera.face`, `mouse.hesitate`, `log.say`, `config_editor.save_attr`, `session.format_elapsed`) replace per-bot copies.

**Tech Stack:** Python 3.8, `transitions`, pytest, tkinter overlay (unchanged API).

**Spec:** `docs/superpowers/specs/2026-09-28-bot-scaffold-design.md`

## Global Constraints

- Python 3.8 syntax; `typing` generics (`List`, `Optional`, `Tuple`, `Callable`).
- `bot.py` and `states.py` must not import pyautogui/mss, actions modules, or gitignored `config.py` at module level.
- Tests run with `.venv/bin/python -m pytest -q`; tests needing a calibrated config use `pytest.importorskip("<pkg>.config")`.
- Never launch a bot, the overlay, or anything that moves the real mouse; dry runs stub every action.
- Do not change `lib/ge.py`, `choc/choc.py`, `choc/run.py`, `miner/miner.py`, `woodcutter/`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A bot package whose `bot.py` raises on import** — menu still builds with the others; error printed.
2. **Fresh clone without calibrated configs** — `discover()` still finds every bot (descriptors import lazily).
3. **Long pause during Golden Nuggets mining** — resuming must not immediately count as "idle, switch vein".
4. **Config editor save of a value whose attr name is a prefix of another** (e.g. `BANK_SLOT_1` vs `BANK_SLOT_10`) — only the exact attribute line changes.
5. **Session re-entry from the menu** — second session starts with `stop=False`, fresh counters, pause/force-stop cleared.

---

### Task 1: Small shared helpers

**Files:** Modify `lib/pause.py`, `lib/movement.py`, `lib/log.py`, `lib/mouse.py`, `lib/config_editor.py`, all six config editors (`tanner/`, `miner/`, `miner/golden_nuggets/`, `choc/`, `lib/ge_config_editor.py`, `lib/energy_config_editor.py`). Test: `tests/test_helpers.py`, extend `tests/test_pause.py`.

**Produces:** `pause.wait() -> bool` (True if it blocked); `wait_until_stopped(..., paused_fn=pause.wait)` default; `log.say(msg)` → prints `[HH:MM:SS] msg`; `mouse.hesitate()` sleeps `uniform(0.3, 0.8)`; `config_editor.save_attr(path, attr, val)` rewrites the `^ATTR = …$` line with `repr(val)`.

- [ ] Tests: `test_wait_returns_false_when_not_paused`, `test_wait_returns_true_after_blocking` (toggle pause, un-pause from a timer thread), `test_say_prefixes_timestamp` (capsys, regex `^\[\d\d:\d\d:\d\d\] hi$`), `test_save_attr_replaces_only_exact_attr` (temp file with `BANK_SLOT_1 = (0, 0)` and `BANK_SLOT_10 = (5, 5)`; save `BANK_SLOT_1=(1, 2)` → only first line changes), `test_save_attr_keeps_other_lines`. Watch fail.
- [ ] Implement. `save_attr` pattern must anchor on `\s*=` after the escaped name (existing regex already does — keep it). Replace each editor's `_save` body (and `GE:` branches) with `save_attr` calls; tanner's `IB:` branch stays as is.
- [ ] Suite green; `.venv/bin/python -c "import tanner.config_editor, miner.golden_nuggets.config_editor, choc.config_editor, lib.ge_config_editor, lib.energy_config_editor, miner.config_editor"` exits 0.
- [ ] Commit.

### Task 2: `lib/camera.face`

**Files:** Create `lib/camera.py`; test `tests/test_camera.py`.

**Produces:** `face(direction: str, cfg) -> None` — `direction in {"north","east","south","west"}`. North: `hesitate()`, left-click `jitter(*cfg.COMPASS, n=5)`, sleep 0.4–0.7. Others: `hesitate()`, right-click jittered compass → `(ax, ay)`, sleep 0.25–0.45, `menu_click(ax + 5, ay + cfg.MENU_HEADER + getattr(cfg, f"LOOK_{DIR}_ROW") * cfg.MENU_ROW_H + cfg.MENU_ROW_H // 2)`, sleep 0.4–0.7. Prints `  Orienting camera <dir>...`.

- [ ] Tests (patch `camera.human_click/human_right_click/menu_click/jitter/time.sleep/hesitate`): west clicks menu row from `LOOK_WEST_ROW`; north left-clicks compass and never opens the menu; unknown direction raises `ValueError`; missing `LOOK_EAST_ROW` on cfg raises `AttributeError`. Watch fail → implement → green → commit.

### Task 3: `lib/session`

**Files:** Create `lib/session.py`; modify `lib/overlay.py` (use `format_elapsed`); test `tests/test_session.py`.

**Produces:** `format_elapsed(seconds) -> "HH:MM:SS"`; `run_session(stats, *, log_prefix, intro, setup, session, handlers, final_states, cycle_start, summary) -> str` per spec lifecycle. `session()` returns the model; `handlers(model)` returns the dict; `summary(model, final, last_step) -> str`. Countdown via `time.sleep(3)`.

- [ ] Tests (patch `session.log.setup`, `session.time.sleep`, `lib.pause.wait` where needed, a tiny transitions model): `format_elapsed(3725) == "01:02:05"`; lifecycle order `reset → countdown → wait → setup → run` (record calls); P during countdown (set `pause._force_stop` inside patched sleep) → returns `"stopped"`, `setup` never called; ForceStop from a handler → `"stopped"`, summary printed with `stopped`; stale `stats["stop"]=True` from a previous session is cleared; returned final state + `stats["step"] == final`. Watch fail → implement → green → commit.

### Task 4: Actions onto shared helpers

**Files:** `git mv tanner/tanner.py tanner/actions.py`, `git mv miner/golden_nuggets/miner.py miner/golden_nuggets/actions.py`; update imports in `tanner/run.py`, `miner/golden_nuggets/run.py`. Test: `tests/test_golden_nuggets_actions.py` (`importorskip("miner.golden_nuggets.config")`).

- [ ] Test first: `test_depletion_idle_timer_resets_after_pause` — patch `count_filled_slots` constant, `character_in_any_vein` True, `time.sleep` no-op, `pause.wait` returning True once then False, and a fake clock where the pause spans > idle_timeout; assert the function does NOT return `"idle"` on the iteration right after the pause.
- [ ] Tanner: `orient_west()` → `face("west", _cfg)`; `_wait_stopped` drops explicit `pause.wait` arg (default now).
- [ ] GN: `orient_*` → thin `face(dir, config)` calls (keep names, callers unchanged); `_pre_action` → `hesitate`; `_log` → `say` (keep `_log = say` alias only if run.py still imports it — prefer updating run.py to `say`); `wait_stopped` unchanged call (default pause gate); add `pause.wait()` in the four loops named in the spec; depletion loop resets `last_gain_t` when `pause.wait()` returns True.
- [ ] Suite green; `python -c "import tanner.run, miner.golden_nuggets.run"`; commit.

### Task 5: Bot `run.py` onto `run_session`

**Files:** `tanner/run.py`, `miner/golden_nuggets/run.py`.

- [ ] Tanner `run(stats, start_from_ge=False)`: `run_session(stats, log_prefix=…/log/tanner, intro=[f"Hide type: {HIDE_TYPE}"], setup=lambda: face("west", config), session=lambda: build_machine(stats, config.RESTOCK_GE, start_from_ge), handlers=_handlers, final_states, cycle_start, summary=…)` — summary prints `[FINAL] stop_reason` line + `Session ended (final after last). Runs: n`. ForceStop reason `force-stopped (P)` set by summary when `final == "stopped" and model.stop_reason is None`.
- [ ] GN `run(stats)`: setup = `orient_south(); say(inventory at start)`; `stats["sack"] = 0` in setup; summary = veins/ores.
- [ ] Stubbed dry runs of both (same scripts as sub-project 1, patched `lib.session.time.sleep`/`log.setup`); suite green; commit.

### Task 6: Discovery + menu

**Files:** Create `lib/bots.py`, `tanner/bot.py`, `miner/bot.py`, `choc/bot.py`; rewrite root `run.py`; delete `launcher.py`, `miner/run.py`. Test: `tests/test_bots.py`.

**Produces:** `Launch`, `Bot` dataclasses; `discover(root: str) -> List[Bot]`; `build_menu(bots, begin, ask_int, tools) -> list` where `begin(bot, fn)` and `ask_int(prompt, cb)` are callbacks; `tools` is a list of `(label, callable)`.

- [ ] Tests: discover on `tmp_path` fake packages (two good, one raising → 2 bots, sorted by `order`, error printed); discover on repo root → names `["Tanning", "Mining", "Choco Grind"]`, and `"tanner.config"`, `"miner.golden_nuggets.config"`, `"choc.config"`, `"pyautogui"`-free check: after importing only `*.bot` in a subprocess, `sys.modules` has none of the three configs; `build_menu` shape: one submenu per bot with launches then `⚙ Configure`, `alt` rendered as 5th tuple element, tools after bots, `Exit` last; clicking a launch calls `begin(bot, fn)`; an `ask_int` launch calls `ask_int(prompt, cb)` and `cb(7)` → `begin` with a fn that passes 7.
- [ ] Descriptors: Tanner = 4 hide launches (start sets `tanner.config.HIDE_TYPE` then `tanner.run.run(stats)`; alt `("GE", …start_from_ge=True)`), colors as today, `stats_line = Hides: run*27`. Mining = Golden Nuggets launch, configure = GN editor, `Ores: run`. Choc = `Run` with `ask_int="How many chocolate bars do you have?"`, configure = choc editor, `Ground: run * GRIND_COUNT` (lazy config import inside the lambda).
- [ ] Root `run.py`: `discover`, `build_menu` with `begin` setting `_pending = (bot, fn)` + `overlay.switch_to_stats()` + event set; popup code generalised from the choc popup (title = bot name, prompt text, int validation); tools = GE Config, Energy Config; loop runs `fn(stats)`; `stats_extra` uses the pending bot's `stats_line`.
- [ ] Delete `launcher.py`, `miner/run.py`. Suite green; `python -c "import lib.bots as b; print([x.name for x in b.discover('.')])"`; commit.

### Task 7: Docs

**Files:** `CLAUDE.md`, `README.md`.

- [ ] CLAUDE.md: repo layout (new lib modules, `bot.py`/`actions.py` names, deleted files), "Bot contract (standard for all bots)" section incl. "Adding a bot" checklist, Golden Nuggets pause behaviour, Varrock Exp note (no menu entry until PRO-7). README: launch section unchanged (`launcher.sh`/`.bat`), mention bots appear automatically.
- [ ] Suite green; commit.
