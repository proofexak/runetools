# runetools — Claude context doc

OSRS bot suite (plus one Path of Exile bot) running on Windows/Linux. Uses pyautogui for input, mss for screen capture, RuneLite for NPC/tile highlights, tkinter for the overlay UI.

## Repo layout

```
lib/                    universal helpers used by all bots
  screen.py             capture only: grab() + find_color(), find_nearest_color(), pixel_matches()
  vision.py             pure screen-decision logic on numpy frames (masks, clusters, click points,
                         filled slots, frame/slot/menu diffs) — see "Vision / pure logic" below
  mouse.py              human_click, smart_right_click, drag_and_drop, human_typewrite, hesitate
  movement.py           wait_until_stopped() — polls MOVEMENT_REGION for screen diff; O/P-pausable
  camera.py             face(direction, cfg) — compass camera orientation for every bot;
                         zoom_out_top_down(x, y) — wheel out + middle-drag down, run after login
  overlay.py            floating tkinter overlay with pause/menu/stats
  config_editor.py      generic point/region/point_color/number calibration UI; save_attr()
  pause.py              O-key pause/resume, P-key force-stop — used everywhere
  log.py                session text log (setup tees stdout/stderr) + say() timestamped print
  events.py             structured JSON-lines session events + launcher error log + excepthooks;
                         also pushes each session line to the web app (Pusher, PRO-99)
  heartbeat.py          per-session daemon thread: heartbeat every 30 s, pause_start / pause_end
  logreport.py          `python -m lib.logreport` — sessions / session <id|latest> / stats / supervisor
  headless.py           unattended mode (`python -m lib.headless`, container main command when BOT
                         is set): keeps RuneLite logged in, runs one bot, restarts per policy;
                         signals from docker/botctl (USR1 pause, HUP resume/start, USR2 stop, INT kill,
                         TERM exit)
  supervisor.py         pure restart policy: decide(), Backoff (30 s→600 s), Budget (5/hour)
  client.py, client_states.py  RuneLite lifecycle (launch → terms → Play → welcome → in game → camera) by image
                         templates (lib/client_templates/*.png, gitignored; vision.find_template)
  client_templates_editor.py  "⚙ Client Templates" capture tool in the menu
  state_machine.py      run_machine() — shared bot runner on the `transitions` library (see
                         "Bot control flow" below)
  session.py            run_session() — standard session lifecycle every bot's run() uses
  bots.py               Bot/Launch descriptors, discover(), build_menu() — see "Bot contract"
  ge.py                 GE building blocks (open_bank/open_ge, withdraw_noted, sell/buy/wait_offer/
                         collect, trade) + tanner's restock trip run_ge_flow — see "GE flow" below
  restock.py            Restock (what a bot buys, how many, price settings) + buy_offer_price — pure
  prices.py             live GE prices from prices.runescape.wiki (quote(): latest trade + last hour's
                         average; buy_price / sell_price: ± 1 gp) — never raises
  interface.py          open_interface (click highlight → wait for check pixel), wait_for, close_interface
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
  accounts.py           active() = RUNETOOLS_ACCOUNT, else data/active_account (written by the web
                         app); run_session tags session_start with it as `account`
  live_control.py       web app "Take control" (PRO-89): watcher thread (run.py, headless) reads
                         data/live_control.json → pause.hold()/unhold() (paused, O/P ignored), answers
                         in data/live_control_ack.json with `safe` = pause.idle() (no step running)
  manual.py             manual mode's main process in the bot container (PRO-90, BOT unset): on the web
                         app's data/manual_request.json starts what's missing — RuneLite (waits for its
                         window), then run.py; reports in data/manual_status.json every 2 s; as PID 1 reaps
                         orphans and on docker stop SIGINTs the menu (session ends "interrupted")

webapp/                 web app (PRO-88): per-account stats + encrypted login vault, not a bot —
                         TypeScript pnpm monorepo, see webapp/README.md. Reads the bots' *.jsonl
                         logs, writes data/active_account + data/bot_token; bots only push log
                         lines to it (POST /api/ingest, best effort — the files stay the truth)
  packages/shared       zod schemas + API types shared by api and web
  apps/api              Fastify + Drizzle/Postgres: src/ingest (tail logs + pushed lines →
                         sessions/steps/errors, logreport's rules, cursor per file), src/stats.ts, src/vault (argon2id →
                         AES-256-GCM, key only in memory), src/accounts.ts; drizzle/ = migrations
  apps/web              React + Vite + TanStack Query + Tailwind (shadcn-style ui/), Recharts
  e2e/                  Playwright specs (pnpm e2e)

tanner/                 Al Kharid leather tanning bot
  bot.py                menu descriptor (4 hide launches + GE side buttons)
  run.py                run(stats) — handlers + run_session()
  states.py             states, transition table, TannerSession (glory charges, skip_restock)
  actions.py            walk_to_tanner, trade_ellis, walk_to_bank, do_bank, recover
  config.py             calibrated positions — GITIGNORED, copy from config.example.py
  config.example.py     zeroed template for config.py
  config_editor.py      config editor wired to tanner/config.py

miner/                  mining bots grouped under one "Mining" menu entry (miner/bot.py);
                         each sub-bot is a launch with its own ⚙ editor side button
  golden_nuggets/       Motherlode Mine bot — run.py, states.py, actions.py, config trio
  varrock_exp/          two-rock copper mine-and-drop bot — run.py, states.py, actions.py, config trio

crafting/               Path of Exile shift+alt-orb crafting bot — same contract, `suite="poe"`,
                         so it is listed only by crafting_run.py (never by the OSRS menu)
crafting_run.py         PoE launcher: flat menu from discover(suite="poe"), P pause / End stop,
                         top-right overlay, "Log Done Checks" diagnostic
docker/                 Ubuntu 24.04 + Xvfb/VNC sandbox for running the suite headless (docker/README.md):
                         two-stage build, Temurin JRE, no window manager, Mesa removed (RuneLite's
                         GPU plugin must stay off — software GL burns CPU), runs as host UID 1000;
                         `docker/runelite` starts the client with FPS cap + JVM flags;
                         `docker/botctl` controls unattended mode (see docker/README.md) and
                         saves/restores RuneLite's profile (`profile-save`/`profile-load` →
                         docker/runelite-profile/, gitignored; a fresh container seeds from it);
                         `docker/measure.sh <image>` measures size/RAM/CPU (438 MB, ~395 MiB, ~43%);
                         compose also runs the web app: `postgres` + `webapp` (127.0.0.1:8778)

choc/                   chocolate dust grind bot — states.py (withdraw → grind ⇄ restock), run.py,
                         choc.py (actions), logic.py (restock_due), config trio

tests/                  pytest suite (stub handlers, fake screen — no game needed):
                         `.venv/bin/python -m pytest`. Only tests/ is collected (pytest.ini).
<bot>/checks/, lib/checks/  live in-game check scripts, run by hand (see "Live checks" below):
                         tanner (inventory_check, slot_check, recovery_drill — one trip, then a forced glory recovery), golden_nuggets (struts),
                         choc (sequence), lib (read_energy, drink_stamina, drink_sequence, follow_offer)

woodcutter/             WIP — not functional yet; standalone script, not a package (so its
                         bot.py is never picked up by discovery)

run.py                  overlay menu + session loop; bots come from discover(), no per-bot code
launcher.sh / .bat      start run.py (RuneTools.desktop points at launcher.sh)
```

## How to run

```
./launcher.sh        # Linux/macOS (or launcher.bat on Windows) — runs root run.py
python crafting_run.py   # Path of Exile crafting bot (separate launcher)
docker compose -f docker/docker-compose.yml up -d postgres webapp   # web app, http://127.0.0.1:8778/
```

Press **O** to pause/resume, **P** to force-stop (O/P are ignored while the bot itself is
typing). Overlay menu: one entry per discovered bot (Tanning, Mining, Choco Grind), then
GE Config, Energy Config, Exit.

## Config system

- Calibrated positions are in each bot's `config.py` (`tanner/`, `miner/golden_nuggets/`, `miner/varrock_exp/`, `choc/`, `crafting/`), `lib/ge_config.py`, and `lib/energy_config.py` — all gitignored, as is `lib/digit_templates/` (per-user digit template bitmaps).
- On fresh clone: copy `*.example.py` → remove `.example`, then calibrate via the in-game config editors. Energy/stamina needs an extra step first — see README's "Stamina potions" section (`calibrate_energy_digits.py`).
- Config editors draw coloured overlays on screen (regions = rectangles, points = crosshairs).
- `config_editor.py` supports ftypes: `point`, `point_color`, `region`, `number`.
- In `tanner/config_editor.py`, prefix `IB:` routes to `INTERFACE_BUTTONS` dict.
- GE restock settings (`GE_QUANTITY`, `GE_BUY_PRICE`, `GE_MAX_PRICE`, `GE_LIVE_PRICES`, `GE_MARGIN_PCT`,
  `GE_OFFER_TIMEOUT`) are each bot's own config (`lib.restock.setting`: bot config → `lib/ge_config.py`,
  where older configs kept them → `DEFAULTS`). `lib/ge_config.py` holds only the shared GE interface positions.

## Key design decisions

**find_color** returns the centroid of all matched pixels (not the first hit), with a small triangular-distributed jitter. This means it clicks the centre of RuneLite NPC hull/tile outlines, not their edges.

**Whole-screen last try.** `find_color` / `find_nearest_color(..., whole_screen=True)`: if the colour isn't in its
region, search all of monitor 1 once and take the cluster nearest the region (or `near`), skipping areas registered
with `screen.exclude()` (the overlay registers its window: its stats text is pure green). Bots pass it on the
**final** attempt at a click target only — tanner Ellis / bank booth / recovery booth, GE banker + agent (lib/ge.py,
choc), energy's booth, golden_nuggets hopper / strut to fix / sack / bank. Never on "is it still there?" checks
(Varrock rocks, pay-dirt veins, struts/sack polls): a respawning target must read as gone.

**RuneLite highlight colours** must match these constants exactly:
- BLUE `(0,0,255)` — Ellis (tanner), GE banker
- MAGENTA `(255,0,255)` — bank booth, GE exchange agent

**smart_right_click(x, y, menu_scan_region)** takes a before/after screenshot diff limited to `menu_scan_region` to find where the right-click menu actually appeared (handles menus that open upward). Always pass `menu_scan_region` — without it the diff covers a huge area and picks up game animation noise.

**GE flow** (`lib/ge.py`). Bots build a `lib.restock.Restock` from their config (`Restock.from_config(cfg,
buy_item, quantity=None, sell_item=None, ...)`); `ge.trade(restock)` (GE open, item to sell first in the inventory)
sells, buys, collects, and returns `(ok, reason)` — the bot keeps the reason for its `stop_reason`. Prices come
from the Wiki API (`lib/prices.py`): sell at the last hour's average instant-sell − 1 gp, buy at its average
instant-buy + 1 gp (the average, not the latest trade: an item that trades in bursts can have a latest price
minutes old and far off). Normal prices raise no low-price warning, so there's no Yes click. No live price: the sell keeps the
price the GE fills in (guide price), the buy uses `GE_BUY_PRICE`; a buy is never above `GE_MAX_PRICE` (then it
stops instead). Typed numbers wait `BOX_FOCUS` for the popup box to take focus (typed too early they go to
public chat). O/P work in every wait.
An offer that sits unfilled is followed (`follow_offer`, sell and buy): every `GE_REPRICE_MINUTES` it opens
slot 1's offer, collects what it did so far, and edits its price (`EDIT_BTN` → `PRICE_BTN` → `CONFIRM_BTN`;
the game keeps the quantity left) to `restock.reprice` — always a fresh check: the latest trade + 1 gp (buy) /
− 1 gp (sell), no minimum step. Same price as now, no live price, or a buy past `GE_MAX_PRICE` → the offer
stays as it is. Gives up after
`GE_REPRICE_ROUNDS`. `EDIT_BTN` uncalibrated (or `GE_REPRICE_MINUTES = 0`) → a plain `GE_OFFER_TIMEOUT` wait.
Live check: `lib.checks.follow_offer`.
Tanner's trip, `run_ge_flow(restock)` — bank positions are the bot's (`Restock.bank_tab` / `sell_slot` /
`deposit_btn`; tanner: `HIDE_TAB`, `BANK_SLOT_2`, `DEPOSIT_BTN`), not lib/ge_config.py's:
1. Price check (over the cap → stop before spending a ring teleport)
2. F4 → left-click ring (`RING_LEFT_CLICK_TP`, RuneLite Menu Entry Swapper makes it the GE teleport) or right-click ring → menu row → teleport to GE (sleep 4.5–5.5s, no wait_stopped — character lands in place)
3. Face west → find banker (BLUE) in `GE_APPROACH_REGION` → confirm via `BANK_CHECK`; not found → face west and look again (`GE_MAX_RETRIES`, never a second teleport)
4. Bot's tab → `withdraw_noted(sell_slot)` (notes toggled only when `NOTES_CHECK` says so, then checked) → close bank
5. `open_ge()` (MAGENTA in `GE_REGION`, `GE_CHECK`) → `trade(restock)` → close GE
6. Find banker (BLUE) in `GE_REGION` → deposit all → close. The hides go back on their own slot (tanner withdraws
   all-but-1, so the stack never leaves the bank) — no tab click, no moving them
7. Tanner's state machine goes to `recover` next (glory back to Al Kharid)
Choc's `restock_ge` uses the same blocks without the teleport.

`do_bank(skip_restock_check=True)` skips the empty-slot-2 check (used after GE restock to prevent infinite loop).

**Look around before recovering.** A bot that's lost first looks at the whole screen once and goes by what it
sees: `lib.screen.look_for({name: (rgb, tol, near)})` → `{name: point | None}` (one grab, overlay excluded,
cluster nearest `near`; pure part `vision.find_targets`). Tanner: a failed walk / trade / bank → state
`look_around` (need = Ellis while carrying hides, the bank while carrying leather): blue (Ellis) seen and needed →
click + tan → `tanning`; purple (booth) seen → click → `banking` (banking again also puts it back on its usual
spot); nothing useful → `lost` → glory `recover`. One look per problem (`looked`, reset by a tan or a recovery),
so it can't loop. Other bots: add the same state with their own colours / decision table.

**Recovery path** (amulet of glory, max 6 charges):
Escape → F4 → left-click amulet (`AMULET_LEFT_CLICK_TP`, swapped to "Al Kharid" in RuneLite's Menu Entry Swapper —
unswapped a left-click *removes* it, so a config without the flag keeps the right-click menu) → teleport Al Kharid → orient west → click double doors → wait stopped →
click inside `TP_BANK_REGION` ("TP Walk Region") → wait stopped → find booth in `TP_BOOTH_REGION` → `do_bank(skip_restock_check=True)`.
An uncalibrated (zero-size) `TP_BOOTH_REGION` fails recovery before the teleport, so no charge is spent.
`save_attr` appends a field missing from an older calibrated config, so new fields can be captured in the editor.

**Bot contract (standard for all bots).** A bot is a package (`__init__.py`) with:
- `bot.py` — `BOT = Bot(name, launches=[Launch(label, start, colors, alt=, ask_int=, configure=)],
  order=, colors=, configure=, stats_line=, suite="osrs")`. A launch has at most one side button:
  `alt` (e.g. Tanner's "GE") or its own `configure` (⚙). `suite` picks the launcher. Import-light: import config/actions/run *inside* the
  callables — `tests/test_bots.py` checks discovery pulls in no config, pyautogui or mss.
- `run.py` — `run(stats, ...)` builds handlers and calls `lib.session.run_session(...)`, which
  owns logging, the 3s countdown (hint from `pause.hint()`, `game=` names the client),
  pause/stats reset, P-during-countdown, ForceStop, `teardown=` (always runs — e.g. crafting
  releases shift) and the closing summary line.
- `states.py` (table + session model, below), `actions.py` (in-game actions),
  `config.py` / `config.example.py` / `config_editor.py` (editors save via `save_attr`).
- Grouped bots (`miner/`) put one `bot.py` at the group level; launches point into sub-packages.
- `CYCLE_START` may be one state or a set (Varrock honours Stop before either rock).
- Action-level tests that need a config use the `with_example_config` fixture (tests/conftest.py),
  which loads `config.example.py` — never the user's calibrated file.
- Shared helpers to use instead of copying: `lib.camera.face`, `lib.mouse.hesitate`,
  `lib.log.say`, `lib.movement.wait_until_stopped` (pausable by default), `lib.session.format_elapsed`.
- Long waits inside actions call `pause.wait()` each iteration; it returns True if it blocked,
  so an idle/timeout clock can be reset after a pause (see golden_nuggets `wait_for_vein_depletion`).
- Optional `checks/` package (PRO-10): **live checks** — small scripts you run by hand against the
  real game to verify one piece (a pixel check, a click sequence) before trusting a full session.
  One module per check, run from the repo root with `.venv/bin/python -m <bot>.checks.<name>`
  (shared lib pieces: `lib.checks.<name>`). Rules, enforced by tests/test_live_checks.py: never
  name them `test_*` (pytest must never import code that clicks) and put all work in `main()`
  behind `if __name__ == "__main__":` — importing a check must do nothing.

Adding a bot: create the package with the files above, calibrate, done — it appears in the
menu automatically (`discover()` runs at startup; a bot.py that fails to import is skipped and
reported, not fatal; a session that raises prints its traceback and returns to the menu via
`lib.bots.run_guarded`).

**Structured session logs (PRO-15).** Every scaffold session writes `<bot>/log/<name>_<stamp>.jsonl`
next to its text `.log` (same stamp). Events: `session_start` (bot, params, account), `step` (state, result,
seconds, run), `pause`, `soft_stop`, `force_stop`, `error` (type, message, traceback, state),
`session_end` (always: final done/stopped/crashed/interrupted/…, reason, stats, active/paused time).
Live status (PRO-99): `state_enter` (state, run — before each handler), `heartbeat` (state, run, paused —
at start, then every 30 s), `pause_start` / `pause_end` (state — the moment O pauses / resumes, also
inside an action's own wait; `pause` with seconds is still the runner's gate). From `lib/heartbeat.py`'s
thread, which `run_session` stops before `session_end`. A session killed while paused stops its active
clock at `pause_start` (logreport + app).
They come from `run_session`/`run_machine` — bots only pass `bot=` and `params=`.
- Errors always land in a log: in a session → `error` + `session_end` "crashed", then re-raised
  (menu returns via `run_guarded`); a bot failing before its session starts → `log/launcher.jsonl`
  (repo root, gitignored); a broken `bot.py` at discovery → same file (`where: discover`); overlay
  button-callback errors (Tk) → the running session's log, else launcher.jsonl (`where: overlay`);
  anything else uncaught → launcher.jsonl via the excepthooks both launchers install *before* any
  other import (so even an import failure is recorded). Teardown + `session_end` sit in a `finally`,
  so they happen even if handling an error fails. A missing `session_end` = the process was killed
  (or the overlay's Exit button was used mid-session).
- Logging never raises into a bot (repr() for odd values, one warning if the file can't be written).
- Report: `python -m lib.logreport` (recent sessions), `session latest` (timeline + tracebacks),
  `stats [--bot B] [--since YYYY-MM-DD]` (per-bot totals; failures = results `fail`/`not_found`).
- Tests never write the real launcher log (autouse fixture points `events.ROOT` at tmp) and never
  push (it sets `RUNETOOLS_APP_URL` empty; tests that push pass `EventLog(..., push=(url, token))`).
- These files are an interface: the web app (webapp/) tails them. Adding fields is fine; renaming or
  dropping an event or field means updating webapp/apps/api/src/ingest/apply.ts too.
- Written in binary mode ("\n" on every OS) so `tell()` is the exact byte offset each pushed line
  carries. Push = `events.Pusher`: one daemon thread, bounded queue (full → drop), 1 s timeout, no
  retries, 5 s backoff after a failure; to `RUNETOOLS_APP_URL` (default `http://127.0.0.1:8778`,
  empty = off) with `data/bot_token` (no token = off). launcher.jsonl is never pushed.
- Timestamps are naive local wall time. The web app splits days by them (its TZ must match the bots')
  and decides "running" from the file's mtime instead (no session_end + written < 90 s ago when the
  session sends heartbeats, < 15 min for older logs).

**Vision / pure logic (PRO-13).** Every decision made from the screen is a pure function that
takes plain data; capture happens only in `lib/screen.grab`.
- Frames are `uint8 (h, w, 3)` **BGR** (what `np.array(mss_shot)[:, :, :3]` gives); vision works
  in frame-local coords, callers add the offset back. Colours in/out are `(r, g, b)`.
- New screen logic goes in `lib/vision.py` (or a bot's pure helper, e.g. `choc/logic.py`,
  `energy.needs_stamina`, `movement.Stillness`, `digit_templates.parse_number`) with a unit test
  on a synthetic frame. Anything random takes `rng=random` so tests pass a stub.
- `grab(region)` is relative to monitor 1 like `find_color` always was; `grab(..., absolute=True)`
  keeps the absolute coordinates movement, `get_pixel_color` and `read_number` always used.
- Tests: `fake_screen` (tests/conftest.py + tests/fakescreen.py) replaces mss with numpy canvases.
  `tests/test_characterise_*.py` pin the pre-refactor results of the public functions — treat
  them as frozen; if one must change, that is a behaviour change and needs a reason.

**Bot control flow (standard for all bots).** Every bot's session is an explicit state machine:
- `bot/states.py`: `STATES`, a `TRANSITIONS` list (`transitions` library dicts), a session model
  class, `build_machine(stats, ...) -> session`, and bot-specific event-mapping helpers
  (generic truthy→`"ok"`/`"fail"` is `lib.state_machine.ok_or_fail`). It must NOT
  import pyautogui/mss, the bot's actions module, or its gitignored config — so tests can import it.
- `bot/run.py`: builds `{state: handler}` closures over the session; each handler does one step
  of real work and returns an **event name** (`"ok"`, `"fail"`, `"full"`, ...), never a state.
  The table decides where the event leads. `run()` passes the handler builder, session builder,
  `FINAL_STATES` and `CYCLE_START` to `lib.session.run_session`, which calls `run_machine` and
  handles `pause.ForceStop` and the summary (see "Bot contract" above).
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
  A normal start (not "Run from GE") banks first: face west → `walk_to_bank` (click the booth) →
  `banking` (deposit + withdraw, empty-slot check skipped) → the usual trip.
- Golden Nuggets miner: on the state machine and the scaffold; O/P work inside long waits (walking,
  mining, sack processing) too, and a pause during mining doesn't count toward the idle timeout.
  A failed hopper deposit fixes struts and retries once; only a successful (re)try counts toward
  the 3-deposit sack. Stops after 3 failed deposits (retry included) in a row (MAX_DEPOSIT_FAILS).
- Varrock Exp miner: on the state machine and scaffold (Mining menu). Counts one ore per drop from
  either rock (`VarrockSession.count_drop`; the old loop counted only the second rock's, PRO-95).
- Choco Grind: on the state machine and scaffold (PRO-95): `start → withdraw → grind ⇄ restock`, soft
  Stop before a batch, failures stop with a reason; O/P work inside its waits (bank open, the grind
  clicks, the minutes-long GE offer wait). `run` = batches ground (the old loop counted the batch in
  progress). Same actions as the old loop — live-check with `choc.checks.sequence` before a long run.
- Crafting (PoE): on the state machine and scaffold, own launcher; shift is released on any exit.
- GE flow: `BANK_CHECK` and `GE_CHECK` both use `(70,61,50)` — if those pixels are always that colour on your screen before the interfaces open, the checks are effectively no-ops. Recalibrate to a pixel that only exists inside the open interface window.
- Same class of bug bit the tanner's own restock check: it used to reuse `BANK_CHECK`'s background colour paired with `BANK_SLOT_2`'s position as an "is this slot empty" proxy, which produced false positives (bot thought it was out of hides when it wasn't). Fixed by adding `EMPTY_SLOT_CHECK`, a point+colour sampled directly on the actual slot while genuinely empty — don't reintroduce the reused-colour pattern elsewhere.
- Energy reading unreadable (`None`): `maybe_drink_stamina` does NOT drink, `restock_stamina_at_bank`
  DOES (safe side at the bank) — explicit via `needs_stamina(..., if_unreadable=)`.
- Stamina potions: tested and working (`lib/energy.py`, wired into `tanner/actions.py`'s `do_bank()`). Cost analysis (see conversation, not saved anywhere else) found plain Energy potions are ~2.6x cheaper than Stamina potions for a bot's purposes despite Stamina's drain-reduction buff — the buff is genuinely valuable but doesn't close the price-per-restore gap. Not switched over since the user wanted Stamina specifically; worth revisiting if potion cost ever matters.
- Web app (PRO-88): dashboard, sessions, bot stats, accounts + active account, vault, settings;
  live status (PRO-99: current state + time in it, Paused badge, ticking active time, pushed lines);
  unit tests (`pnpm test`, PGlite) + Playwright e2e (`pnpm e2e`). It replaced the stdlib Python
  prototype (`python -m dashboard`), which is deleted.
- Live view (PRO-89): noVNC (react-vnc) on the account page of the running session, collapsed
  behind "Watch live" (dashboard session cards link there with `?watch=1`); the API bridges the WebSocket to x11vnc
  itself (`/api/live/vnc`, `VNC_ADDR`) — no websockify, no extra port. Take control / Release via
  `lib/live_control.py` (see webapp/README.md "Live view"). Checked view-only against the real
  container; take control against a real running bot not yet tried.
- Bot container Start / Stop (PRO-90): web app panel → `dockerproxy` compose service (allowlist proxy, the only
  holder of the Docker socket: inspect / start / stop of `runetools-runetools-1`, nothing else) + `lib/manual.py`
  through data/ files. Start = docker start if stopped, then RuneLite + menu; Stop = docker stop -t 30 (never
  removed). Unattended containers (BOT set) are only started. See webapp/README.md "Bot container".
- Woodcutter: WIP, don't touch.
