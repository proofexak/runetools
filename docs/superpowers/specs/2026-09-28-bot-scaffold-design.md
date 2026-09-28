# Standard bot scaffold — design (sub-project 2 of 4)

**Linear:** PRO-11
**Date:** 2026-09-28
**Status:** decided autonomously — the user asked for this sub-project to be done
end-to-end while they were away. Every decision below is listed under
"Decisions" so it can be reviewed and reversed after the fact.
**Builds on:** `docs/superpowers/specs/2026-09-28-bot-state-machine-design.md`
(sub-project 1, branch `proofexak/pro-12-…`). This branch is cut from its tip.

## Goal

One scaffold every bot follows, so adding a bot means adding a package — not
editing the launcher, the menu, or copying helpers. From PRO-11:

- Document the contract every bot must implement.
- Extract shared scaffolding where reasonable, without over-abstracting.
- The menu/launcher auto-discovers bots that follow the contract.

Success: Tanner and Golden Nuggets follow the contract; the overlay menu is built
from discovered bots with no per-bot code in root `run.py`; the contract is in
CLAUDE.md; behaviour in game is unchanged except the approved items below.

## The bot contract

A bot is a top-level package (or, for grouped bots like `miner/`, the group
package) containing:

| file | role |
|---|---|
| `bot.py` | `BOT = Bot(...)` descriptor — menu label/order, launch options, config editor, overlay stats line. Must import nothing heavy at module level (no pyautogui/mss, no gitignored `config.py`) so discovery works on a fresh clone. |
| `run.py` | `run(stats, ...)` — builds handlers, calls `lib.session.run_session`. |
| `states.py` | state table + session model (sub-project 1 rules). |
| `actions.py` | the bot's in-game actions (screen reads, clicks). |
| `config.py` / `config.example.py` / `config_editor.py` | calibration, as today. |

Golden Nuggets lives at `miner/golden_nuggets/` with `miner/bot.py` as the
discovered "Mining" group. Choc gets a `bot.py` only (its internals move in
sub-project 3).

### `lib/bots.py`

```python
@dataclass
class Launch:
    label: str
    start: Callable                 # start(stats) or start(stats, n) if ask_int
    colors: Tuple[str, str]
    alt: Optional[Tuple[str, Callable]] = None   # side button, e.g. ("GE", start_from_ge)
    ask_int: Optional[str] = None                # prompt shown before start

@dataclass
class Bot:
    name: str
    launches: List[Launch]
    order: int = 100
    colors: Tuple[str, str] = ("#1a1a33", "#2a2a55")
    configure: Optional[Callable[[], None]] = None
    stats_line: Optional[Callable[[dict], str]] = None

def discover(root) -> List[Bot]          # import <pkg>.bot for each top-level dir with bot.py; sort by order
def build_menu(bots, begin, ask_int, tools) -> list   # overlay MENU in its existing tuple format
```

- `discover` skips (and prints) a package whose `bot.py` fails to import, so one
  broken bot can't take the menu down.
- `build_menu` produces, per bot, a submenu of its launches (+ `alt` side button)
  followed by `⚙ Configure`; then the shared tools (GE Config, Energy Config) and
  Exit. `begin(bot, fn)` is supplied by root `run.py` and hands the session to the
  main loop; `ask_int(prompt, cb)` shows the integer popup.

Root `run.py` shrinks to: hotkeys, `discover`, `build_menu`, overlay start, and
the session loop. The Varrock Exp menu entry disappears (no descriptor) — which
also removes today's crash when it's clicked. `miner/run.py` (LOCATION dispatcher)
and `launcher.py` (dead: runs `tanner/run.py` as a script, which does nothing)
are deleted.

### `lib/session.py`

```python
def run_session(stats, *, log_prefix, intro, setup, session, handlers,
                final_states, cycle_start, summary) -> str
def format_elapsed(seconds) -> str      # "HH:MM:SS"
```

Standard lifecycle every bot's `run()` delegates to:

1. `log.setup(log_prefix)`; print `intro` lines and the O/P hint.
2. `pause.reset()` **before** the 3s countdown, then `stats.update(run=0, step="starting", start=None, stop=False)`.
3. 3s countdown, then inside `try`: `pause.wait()` (so P pressed during the
   countdown ends the session instead of being discarded), `setup()`,
   `stats["start"] = now`, `run_machine(session(), handlers(...), …)`.
4. `except pause.ForceStop` → final `stopped`.
5. `stats["step"] = final`; print `summary(final, last_step)` + elapsed.

`session` and `handlers` are callables so setup (camera orientation, inventory
log) happens before the machine is built, exactly as today.

### Shared helpers moved into `lib/`

| helper | new home | used by |
|---|---|---|
| camera orientation (`orient_west/east/south/north`) | `lib/camera.py::face(direction, cfg)` | Tanner, Golden Nuggets |
| `_pre_action()` random 0.3–0.8s hesitation | `lib/mouse.py::hesitate()` | Golden Nuggets |
| `_log()` timestamped print | `lib/log.py::say()` | Golden Nuggets, `lib/session` |
| `wait_stopped` wrappers | `lib/movement.wait_until_stopped` now defaults `paused_fn=pause.wait` | all |
| elapsed `HH:MM:SS` formatting (3 copies + overlay) | `lib/session.format_elapsed` | sessions, overlay |
| config editors' regex `_save` (6 copies) | `lib/config_editor.py::save_attr(path, attr, val)` | all editors |

`face()` reads `COMPASS`, `MENU_HEADER`, `MENU_ROW_H` and `LOOK_<DIR>_ROW` from the
config module passed in; `north` is a plain left-click on the compass (as
Golden Nuggets does today). Timings follow Golden Nuggets' randomised version.

`lib/ge.py`'s own `_orient_west` and `miner/miner.py` are left for sub-projects 3
and 4 respectively.

### Pause checks inside long actions

- `pause.wait()` now returns `True` if it actually blocked (backward compatible).
- `wait_until_stopped` gates on `pause.wait` by default (Tanner already passed it).
- Golden Nuggets' long loops call `pause.wait()` each iteration:
  `wait_for_vein_depletion` (and resets its idle timer when a pause happened, so a
  long pause doesn't read as "idle — switch vein"), the strut-clear wait in
  `process_full_sack`, `click_sack`'s retry loop, `open_bank`'s wait loop.

## Decisions (made autonomously — review these)

1. **Descriptor file `bot.py` with a `BOT` dataclass**, discovered by importing
   each top-level package's `bot.py`. Rejected: entry-points/plugins (overkill),
   a registry list in `lib/` (still needs editing per bot).
2. **Grouped bots** (`miner/`) expose one `Bot` whose launches point into
   sub-packages. Only Golden Nuggets is listed until Varrock Exp exists (PRO-7).
3. **`lib/session.run_session`** standardises the session lifecycle; fixes the
   deferred "P during countdown is discarded" finding for every bot on it.
4. **Renames:** `tanner/tanner.py → tanner/actions.py`,
   `miner/golden_nuggets/miner.py → miner/golden_nuggets/actions.py`.
5. **Deletions:** `launcher.py` (dead), `miner/run.py` (LOCATION dispatcher,
   superseded by discovery). `miner/config.py`/`config_editor.py`/`miner.py`
   stay for PRO-7.
6. **Choc** only gains `choc/bot.py` and the shared `save_attr` in its editor;
   its loop is untouched until sub-project 3.
7. **Tanner keeps plain `print`** (no timestamp change); only GN's `_log` moves.
8. **Run counter question** (from sub-project 1 review) left untouched — waiting
   on the user.

## Behaviour changes (all intentional)

- P pressed during the 3s countdown now stops the session (was discarded).
- Golden Nuggets: O/P take effect inside walking waits and inside mining /
  sack-processing waits, not only between steps.
- Tanner camera orientation uses GN's randomised timings (0.3–0.8s hesitation,
  0.25–0.45s menu wait, 0.4–0.7s settle) instead of fixed 0.35s/0.5s.
- Menu: Varrock Exp entry gone (it crashed); order is Tanning, Mining, Choco
  Grind, then tools — same as today.

## Testing

pytest, no game: `discover` against temp packages and the real repo (finds
tanner, miner, choc; importing `bot.py` does not import the bot's config or
pyautogui-heavy modules); `build_menu` output shape; `save_attr` on a temp file;
`format_elapsed`; `run_session` lifecycle with stub machine (countdown P, reset
order, summary, ForceStop); `pause.wait` return value; `face()` click targets
with patched mouse functions; GN depletion loop resets idle timer after a pause.
Stubbed end-to-end dry runs of Tanner and GN `run()` as in sub-project 1.

Live (user): menu shows Tanning / Mining / Choco Grind + tools; each launch and
Configure button works; one Tanner trip, one GN vein; P during countdown.
