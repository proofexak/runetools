# runetools — Claude context doc

OSRS bot suite running on Windows. Uses pyautogui for input, mss for screen capture, RuneLite for NPC/tile highlights, tkinter for the overlay UI.

## Repo layout

```
lib/                    universal helpers used by all bots
  screen.py             find_color(), pixel_matches()
  mouse.py              human_click, smart_right_click, drag_and_drop, human_typewrite, hesitate
  movement.py           wait_until_stopped() — polls MOVEMENT_REGION for screen diff; O/P-pausable
  camera.py             face(direction, cfg) — compass camera orientation for every bot
  overlay.py            floating tkinter overlay with pause/menu/stats
  config_editor.py      generic point/region/point_color/number calibration UI; save_attr()
  pause.py              O-key pause/resume, P-key force-stop — used everywhere
  log.py                session logger (setup) + say() timestamped print
  state_machine.py      run_machine() — shared bot runner on the `transitions` library (see
                         "Bot control flow" below)
  session.py            run_session() — standard session lifecycle every bot's run() uses
  bots.py               Bot/Launch descriptors, discover(), build_menu() — see "Bot contract"
  ge.py                 universal GE restock flow (sell leathers, buy hides, bank)
  ge_config.py          calibrated GE positions — GITIGNORED, copy from ge_config.example.py
  ge_config.example.py  zeroed template for ge_config.py
  ge_config_editor.py   config editor wired to ge_config.py
  digit_templates.py    template-matching digit reader for small in-game bitmap fonts —
                         Tesseract OCR proved unreliable on this font (drops/misreads digits
                         even on clean, correctly-segmented single-character crops), so this
                         does exact pixel-template comparison instead. Templates are
                         gitignored, per-user calibration data — build with
                         calibrate_energy_digits.py (repo root).
  energy.py             read_energy(), drink_stamina(), restock_stamina_at_bank() — reads
                         run energy via digit_templates + ENERGY_REGION, drinks a whole
                         stamina potion bottle (4 clicks, ~1.3s apart — potions have a
                         per-dose action cooldown, faster clicks silently drop doses) when
                         below DRINK_THRESHOLD. restock_stamina_at_bank() assumes the bank is
                         already open; wired into tanner's do_bank().
  energy_config.py      calibrated energy/stamina positions — GITIGNORED, copy from
                         energy_config.example.py
  energy_config_editor.py  config editor wired to energy_config.py

tanner/                 Al Kharid leather tanning bot
  bot.py                menu descriptor (4 hide launches + GE side buttons)
  run.py                run(stats) — handlers + run_session()
  states.py             states, transition table, TannerSession (glory charges, skip_restock)
  actions.py            walk_to_tanner, trade_ellis, walk_to_bank, do_bank, recover
  config.py             calibrated positions — GITIGNORED, copy from config.example.py
  config.example.py     zeroed template for config.py
  config_editor.py      config editor wired to tanner/config.py (GE: prefix routes to ge_config.py)

miner/                  mining bots grouped under one "Mining" menu entry (miner/bot.py)
  golden_nuggets/       Motherlode Mine bot — run.py, states.py, actions.py, config trio
  miner.py, config*.py  Varrock Exp copper actions/config — no loop or menu entry yet (PRO-7)

choc/                   chocolate dust grind bot — has bot.py; loop NOT yet on the state machine
                         (roadmap step 3)

tests/                  pytest suite for runner + bot transition tables (stub handlers, no game
                         needed): `.venv/bin/python -m pytest`. Root-level test_*.py are live
                         in-game scripts, not part of the suite (pytest.ini: testpaths = tests).

woodcutter/             WIP — not functional yet; standalone script, not a package (so its
                         bot.py is never picked up by discovery)

run.py                  overlay menu + session loop; bots come from discover(), no per-bot code
launcher.sh / .bat      start run.py (RuneTools.desktop points at launcher.sh)
```

## How to run

```
./launcher.sh        # Linux/macOS (or launcher.bat on Windows) — runs root run.py
```

Press **O** to pause/resume, **P** to force-stop (O/P are ignored while the bot itself is
typing). Overlay menu: one entry per discovered bot (Tanning, Mining, Choco Grind), then
GE Config, Energy Config, Exit.

## Config system

- Calibrated positions are in each bot's `config.py` (`tanner/`, `miner/golden_nuggets/`, `choc/`), `lib/ge_config.py`, and `lib/energy_config.py` — all gitignored, as is `lib/digit_templates/` (per-user digit template bitmaps).
- On fresh clone: copy `*.example.py` → remove `.example`, then calibrate via the in-game config editors. Energy/stamina needs an extra step first — see README's "Stamina potions" section (`calibrate_energy_digits.py`).
- Config editors draw coloured overlays on screen (regions = rectangles, points = crosshairs).
- `config_editor.py` supports ftypes: `point`, `point_color`, `region`, `number`.
- In `tanner/config_editor.py`, prefix `GE:` routes reads/writes to `ge_config.py`; prefix `IB:` routes to `INTERFACE_BUTTONS` dict.

## Key design decisions

**find_color** returns the centroid of all matched pixels (not the first hit), with a small triangular-distributed jitter. This means it clicks the centre of RuneLite NPC hull/tile outlines, not their edges.

**RuneLite highlight colours** must match these constants exactly:
- BLUE `(0,0,255)` — Ellis (tanner), GE banker
- MAGENTA `(255,0,255)` — bank booth, GE exchange agent

**smart_right_click(x, y, menu_scan_region)** takes a before/after screenshot diff limited to `menu_scan_region` to find where the right-click menu actually appeared (handles menus that open upward). Always pass `menu_scan_region` — without it the diff covers a huge area and picks up game animation noise.

**GE flow** (`lib/ge.py`):
1. F4 → right-click ring → teleport to GE (sleep 4.5–5.5s, no wait_stopped — character lands in place)
2. Orient camera west
3. Find banker (BLUE) in `GE_APPROACH_REGION` → click → confirm bank opened via `BANK_CHECK` pixel
4. Second tab → enable notes → withdraw slot 1 → disable notes → close bank
5. Find GE agent (MAGENTA) in `GE_REGION` → sell leathers at price 1 → buy hides at `GE_BUY_PRICE`
6. Retrieve coins + hides → close GE
7. Find banker (BLUE) in `GE_REGION` → deposit all → snapshot diff to find changed slot → drag to `SECOND_TAB`
8. Call `on_complete` callback (tanner passes a no-op; its state machine goes to `recover` next)

`do_bank(skip_restock_check=True)` skips the empty-slot-2 check (used after GE restock to prevent infinite loop).

**Recovery path** (amulet of glory, max 6 charges):
Escape → F4 → right-click amulet → teleport Al Kharid → orient west → click double doors → find booth in `TP_BANK_REGION` → `do_bank(skip_restock_check=True)`

**Bot contract (standard for all bots).** A bot is a package (`__init__.py`) with:
- `bot.py` — `BOT = Bot(name, launches=[Launch(label, start, colors, alt=, ask_int=)], order=,
  colors=, configure=, stats_line=)`. Import-light: import config/actions/run *inside* the
  callables — `tests/test_bots.py` checks discovery pulls in no config, pyautogui or mss.
- `run.py` — `run(stats, ...)` builds handlers and calls `lib.session.run_session(...)`, which
  owns logging, the 3s countdown, pause/stats reset, P-during-countdown, ForceStop and the
  closing summary line.
- `states.py` (table + session model, below), `actions.py` (in-game actions),
  `config.py` / `config.example.py` / `config_editor.py` (editors save via `save_attr`).
- Grouped bots (`miner/`) put one `bot.py` at the group level; launches point into sub-packages.
- Shared helpers to use instead of copying: `lib.camera.face`, `lib.mouse.hesitate`,
  `lib.log.say`, `lib.movement.wait_until_stopped` (pausable by default), `lib.session.format_elapsed`.
- Long waits inside actions call `pause.wait()` each iteration; it returns True if it blocked,
  so an idle/timeout clock can be reset after a pause (see golden_nuggets `wait_for_vein_depletion`).

Adding a bot: create the package with the files above, calibrate, done — it appears in the
menu automatically (`discover()` runs at startup; a bot.py that fails to import is skipped and
reported, not fatal).

**Bot control flow (standard for all bots).** Every bot's session is an explicit state machine:
- `bot/states.py`: `STATES`, a `TRANSITIONS` list (`transitions` library dicts), a session model
  class, `build_machine(stats, ...) -> session`, and bot-specific event-mapping helpers
  (generic truthy→`"ok"`/`"fail"` is `lib.state_machine.ok_or_fail`). It must NOT
  import pyautogui/mss, the bot's actions module, or its gitignored config — so tests can import it.
- `bot/run.py`: builds `{state: handler}` closures over the session; each handler does one step
  of real work and returns an **event name** (`"ok"`, `"fail"`, `"full"`, ...), never a state.
  The table decides where the event leads. Then `run_machine(session, handlers, stats,
  FINAL_STATES, CYCLE_START)`, catching `pause.ForceStop` for the session summary.
- Guards are `conditions=` on transitions (methods or plain bool attributes); same-trigger
  transitions are tried in list order, so put the conditional row first.
- `run_machine` gates every step on `pause.wait()` (O-pause, P raises ForceStop), sets
  `stats["step"]` to the running state, and only honours the overlay's soft Stop when about to run
  `CYCLE_START` — the table needs a `stop` trigger from `CYCLE_START` to a final state.
- `transitions` does not fire `on_enter_<state>` for the initial state: if the first real state
  needs its entry callback, start in a transient `start` state and fire `begin` in `build_machine`
  (see tanner/states.py).
- Always `auto_transitions=False`. A declared event invalid from the current state raises
  `MachineError`; an undeclared event name raises `AttributeError`; an event whose rows all fail
  their conditions raises `MachineError` from the runner (transitions alone would silently re-run
  the handler) — always give guarded rows an unconditional fallback.
- Test the table with stub handlers through the real `run_machine` (tests/test_tanner_states.py).

**wait_until_stopped** polls a screen region for pixel diff. Returns when stable for N consecutive frames. Used after walking, not after teleports (teleports are instant).

## What's working / WIP

- Tanner bot: fully functional, recovery path + GE restock both tested and working. Now driven by the
  state machine (PRO-12). Every glory teleport — failure recovery, post-GE return, "Run from GE"
  start — goes through the `recover` state and uses one of the 6 charges; a failed "Run from GE"
  start now stops the session. With 0 charges left it won't start a GE restock (no way back).
  The session summary prints why it stopped (`TannerSession.stop_reason`).
- Golden Nuggets miner: on the state machine and the scaffold; O/P work inside long waits (walking,
  mining, sack processing) too, and a pause during mining doesn't count toward the idle timeout.
  A failed hopper deposit fixes struts and retries once; only a successful (re)try counts toward
  the 3-deposit sack. Stops after 3 failed deposits (retry included) in a row (MAX_DEPOSIT_FAILS).
- Varrock Exp miner: `miner/varrock_exp/` (loop added on main) is not yet on the state machine or
  in the menu; the legacy loose copy in `miner/miner.py` + `miner/config*.py` predates it.
- GE flow: `BANK_CHECK` and `GE_CHECK` both use `(70,61,50)` — if those pixels are always that colour on your screen before the interfaces open, the checks are effectively no-ops. Recalibrate to a pixel that only exists inside the open interface window.
- Same class of bug bit the tanner's own restock check: it used to reuse `BANK_CHECK`'s background colour paired with `BANK_SLOT_2`'s position as an "is this slot empty" proxy, which produced false positives (bot thought it was out of hides when it wasn't). Fixed by adding `EMPTY_SLOT_CHECK`, a point+colour sampled directly on the actual slot while genuinely empty — don't reintroduce the reused-colour pattern elsewhere.
- Stamina potions: tested and working (`lib/energy.py`, wired into `tanner/tanner.py`'s `do_bank()`). Cost analysis (see conversation, not saved anywhere else) found plain Energy potions are ~2.6x cheaper than Stamina potions for a bot's purposes despite Stamina's drain-reduction buff — the buff is genuinely valuable but doesn't close the price-per-restore gap. Not switched over since the user wanted Stamina specifically; worth revisiting if potion cost ever matters.
- Woodcutter: WIP, don't touch.
