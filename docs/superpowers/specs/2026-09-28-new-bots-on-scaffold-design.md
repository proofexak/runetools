# Varrock Exp + Crafting onto the state machine and scaffold — design

**Date:** 2026-09-28 · **Linear:** PRO-7 (Varrock Exp); crafting has no issue
**Branch:** `proofexak/new-bots-on-scaffold`, stacked on the PRO-11 scaffold branch,
which is stacked on PRO-12 — all three rebased onto `main` @ 1895976.
**Builds on:** `2026-09-28-bot-state-machine-design.md`, `2026-09-28-bot-scaffold-design.md`.

## Goal

The two bots that landed on `main` while sub-projects 1–2 were in flight —
`miner/varrock_exp/` (473494e) and `crafting/` (1895976, Path of Exile) — follow
the same standard as Tanner and Golden Nuggets: explicit state table
(`states.py`), `actions.py`, `run.py` through `run_session`, a `bot.py`
descriptor, shared helpers, tests.

User decisions (asked 2026-09-28):
- **Crafting stays separate from the OSRS menu:** same contract, but tagged as a
  PoE bot; `crafting_run.py` keeps its own launcher, P pause / End stop and the
  top-right overlay, and builds its menu from discovery.
- (Golden Nuggets hopper retry — already ported on the PRO-12 branch.)

## Shared changes

| change | why |
|---|---|
| `Bot.suite` (default `"osrs"`); `discover(root, suite="osrs")` | crafting (`suite="poe"`) never appears in the OSRS menu |
| `Launch.configure` → rendered as a `⚙` side button (a launch may have `alt` **or** `configure`, not both — `ValueError`) | Mining now has two sub-bots with their own editors; crafting's old menu had a `⚙` side button |
| `build_menu(..., flat=False)`; `flat=True` puts launches at top level | crafting's launcher had a flat menu |
| `pause.hint()` → `"Press O to pause, P to force-stop."` from the configured keys (incl. special `stop_key` like End) | `run_session`'s hint was hard-coded to O/P |
| `run_session(..., game="OSRS", teardown=None)` — `teardown()` runs in `finally` | crafting must release the held shift key on any exit |
| `run_machine(..., cycle_start=)` accepts one state or a collection | Varrock checked the overlay Stop both before the first and before the second rock |

## Varrock Exp

`miner/varrock_exp/miner.py → actions.py`, camera via `face("south")`,
`hesitate()`, pause gate inside `wait_and_drop`'s 10 s poll.

States: `mine_first` → `drop_first` → `mine_second` → `drop_second` → `mine_first`, final `stopped`.

| trigger | source | dest |
|---|---|---|
| `ok` | mine_first | drop_first |
| `not_found` | mine_first | mine_first (handler waited 10 s) |
| `ok` | drop_first | mine_second |
| `ok` | mine_second | drop_second |
| `not_found` | mine_second | mine_first (as main's `continue`) |
| `ok` | drop_second | mine_first |
| `stop` | mine_first, mine_second | stopped |

`mine_first` prefers magenta then blue; `mine_second` prefers blue then magenta
(main's fallback order). Ore counter increments only when the **second** drop
finds an ore — kept exactly as main does it (flagged to the user: it looks like
it undercounts by half).

`miner/bot.py`: launches **Varrock Exp** then **Golden Nuggets** (main's old
order), each with its own `⚙` editor side button; no bot-level Configure.

Legacy `miner/miner.py`, `miner/config.example.py`, `miner/config_editor.py`
(the pre-package copy of the same bot) are deleted — superseded by
`miner/varrock_exp/`. The gitignored `miner/config.py` is left on disk.

## Crafting

`crafting/crafting.py → actions.py`; `crafting_run.py` keeps being the PoE
launcher. States: `grab_currency` → `craft` (one item per pass) → `done`, final
`done`/`stopped`.

| trigger | source | dest | condition |
|---|---|---|---|
| `ok` | grab_currency | craft | `has_more` |
| `ok` | grab_currency | done | |
| `ok` | craft | craft | `has_more` |
| `ok` | craft | done | |
| `stop` | craft | stopped | |

`CraftingSession` holds the non-skipped items, `index`, `total`;
`next_item()` sets `stats["run"] = n` and `stats["step"] = "item n/total"` (as
main did), `item_done()` advances. `teardown = release` (shift up) on every exit.
`craft_item` keeps its retry-until-done loop (already pause-gated).

## Testing

pytest, no game: `pause.hint`; `run_session` teardown on normal end / ForceStop /
crash and the game name in the hint; runner with multiple cycle starts; bots
suite filter, flat menu, launch `configure` side button, alt+configure
rejected; repo discovery per suite; lazy-import check covers the two new
configs; Varrock and crafting tables with stub handlers; Varrock
`wait_and_drop` pause gate and crafting session item accounting against the
example configs. Stubbed dry runs of both `run()`s and both launchers' menus.

Live (user): Varrock a few rock cycles + Stop between rocks; crafting launcher
(P/End, top-right, ⚙ editor, Log Done Checks) and a short item list.
