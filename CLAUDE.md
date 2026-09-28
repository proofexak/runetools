# runetools — Claude context doc

OSRS bot suite running on Windows. Uses pyautogui for input, mss for screen capture, RuneLite for NPC/tile highlights, tkinter for the overlay UI.

## Repo layout

```
lib/                    universal helpers used by all bots
  screen.py             find_color(), pixel_matches()
  mouse.py              human_click, smart_right_click, drag_and_drop, human_typewrite
  movement.py           wait_until_stopped() — polls MOVEMENT_REGION for screen diff
  overlay.py            floating tkinter overlay with pause/menu/stats
  config_editor.py      generic point/region/point_color/number calibration UI
  pause.py              O-key pause/resume, P-key force-stop — used everywhere
  log.py                session logger
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
  run.py                entry point — session loop, overlay menu, handles restock/recovery
  tanner.py             actions: walk_to_tanner, trade_ellis, walk_to_bank, do_bank, recover
  config.py             calibrated positions — GITIGNORED, copy from config.example.py
  config.example.py     zeroed template for config.py
  config_editor.py      config editor wired to tanner/config.py (GE: prefix routes to ge_config.py)

woodcutter/             WIP — not functional yet

launcher.py             launches bots (currently only tanner)
```

## How to run

```
python tanner/run.py           # normal mode (shows hide selector)
python tanner/run.py --select  # same — selector is always shown
```

Press **O** to pause/resume, **P** to force-stop. Overlay menu: Tanning (hide type + Configure), GE Config, Exit.

## Config system

- Calibrated positions are in `tanner/config.py`, `lib/ge_config.py`, and `lib/energy_config.py` — all gitignored, as is `lib/digit_templates/` (per-user digit template bitmaps).
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
8. Call `on_complete` callback (tanner passes `recover`)

`do_bank(skip_restock_check=True)` skips the empty-slot-2 check (used after GE restock to prevent infinite loop).

**Recovery path** (amulet of glory, max 6 charges):
Escape → F4 → right-click amulet → teleport Al Kharid → orient west → click double doors → find booth in `TP_BANK_REGION` → `do_bank(skip_restock_check=True)`

**wait_until_stopped** polls a screen region for pixel diff. Returns when stable for N consecutive frames. Used after walking, not after teleports (teleports are instant).

## What's working / WIP

- Tanner bot: fully functional, recovery path + GE restock both tested and working.
- GE flow: `BANK_CHECK` and `GE_CHECK` both use `(70,61,50)` — if those pixels are always that colour on your screen before the interfaces open, the checks are effectively no-ops. Recalibrate to a pixel that only exists inside the open interface window.
- Same class of bug bit the tanner's own restock check: it used to reuse `BANK_CHECK`'s background colour paired with `BANK_SLOT_2`'s position as an "is this slot empty" proxy, which produced false positives (bot thought it was out of hides when it wasn't). Fixed by adding `EMPTY_SLOT_CHECK`, a point+colour sampled directly on the actual slot while genuinely empty — don't reintroduce the reused-colour pattern elsewhere.
- Stamina potions: tested and working (`lib/energy.py`, wired into `tanner/tanner.py`'s `do_bank()`). Cost analysis (see conversation, not saved anywhere else) found plain Energy potions are ~2.6x cheaper than Stamina potions for a bot's purposes despite Stamina's drain-reduction buff — the buff is genuinely valuable but doesn't close the price-per-restore gap. Not switched over since the user wanted Stamina specifically; worth revisiting if potion cost ever matters.
- Woodcutter: WIP, don't touch.
