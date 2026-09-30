# Split Decision Logic from Screen I/O Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every screen-based decision becomes a pure, unit-tested function; capture stays at the edge; bots' behaviour is unchanged.

**Architecture:** Characterisation tests pin today's public functions against a fake `mss` canvas; `lib/vision.py` gets the pure logic with its own unit tests; callers are rewired to capture + vision while the characterisation tests stay green.

**Tech Stack:** Python 3.8, numpy, Pillow, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-split-logic-from-screen-io-design.md`

## Global Constraints

- Frames are `uint8 (h, w, 3)` **BGR**; vision works in frame-local coords; colours in/out are `(r, g, b)`.
- `lib/vision.py` imports only numpy, PIL, random — never mss, pyautogui or any config.
- Public signatures unchanged: `find_color`, `find_nearest_color`, `pixel_matches`, `get_pixel_color`, `read_number`, `read_energy`, `maybe_drink_stamina`, `restock_stamina_at_bank`, `wait_until_stopped`, `smart_right_click`, GN `count_filled_slots` / `count_broken_struts` / `character_in_any_vein`.
- Characterisation tests written in Tasks 1–2 are **not edited** after Task 2 — they are the equivalence proof.
- Tests needing a gitignored config use `with_example_config`; nothing touches the real screen, mouse or keyboard.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Colour exactly `tol` away** — matches (`<=`), `tol + 1` doesn't; same in every function that masks.
2. **Two clusters equidistant from `near`** — the first cluster found (row-major seed order) wins, as today.
3. **Polygon region** — only pixels inside the polygon count; the returned point is still screen-absolute.
4. **Unreadable energy (`None`)** — `maybe_drink_stamina` doesn't drink; `restock_stamina_at_bank` does.
5. **Movement that stops then starts again** — the stillness counter resets on any frame above threshold.

---

### Task 1: Fake screen + characterisation of `lib/screen` and Golden Nuggets

**Files:** Create `tests/fakescreen.py` (helper), `tests/test_characterise_screen.py`; modify `tests/conftest.py`.

**Produces:**
- `tests/fakescreen.py`: `canvas(w, h, bgr=(0,0,0))`, `paint(canvas, x, y, w, h, rgb)` (fills BGR), `FakeMSS` whose `.grab(box)` returns a shot with `np.array(shot)` → BGRA crop, `.size`, `.bgra`; `.monitors = [{}, {"left": 0, "top": 0, "width": W, "height": H}]`; the canvas it serves can be swapped (list of frames popped per grab, last one repeats).
- `conftest.py` fixture `fake_screen(monkeypatch)` → patches `mss.mss` with a factory bound to a settable canvas and pins `random.triangular` to `lambda lo, hi, mode: mode`; returns the controller.
- `with_example_config(pkg, module, config="config")` — third arg picks `<pkg>/<config>.example.py` (needed for `lib/energy_config`, `lib/ge_config`).

- [ ] Tests (all must PASS against current code):
  `test_find_color_rect_returns_centroid_and_count` (10×10 magenta blob at (40,20) in region (30,10,50,50) → point (44.5, 24.5), count 100); `test_find_color_not_found` → `(None, 0)`; `test_find_color_polygon_excludes_outside` (blob half inside a triangle → count equals inside pixels only); `test_find_color_tolerance_boundary` (blob colour off by exactly 10 matches with tol=10, 11 doesn't); `test_find_nearest_color_picks_cluster_nearest_to_point` (two blobs 200px apart, `near` beside the right one → its centroid); `test_find_nearest_color_equidistant_takes_first_found`; `test_pixel_matches_and_get_pixel_color` (tol 15 boundary);
  GN via `with_example_config("miner.golden_nuggets", "actions")`: `test_count_filled_slots` (anchors → 28 slots, paint 5 slots ≠ bg, slot 0 painted too → 5, because slot 0 is skipped); `test_count_broken_struts_counts_clusters_60px_apart`; `test_character_in_any_vein_bbox_containment` (CHARACTER inside vs. outside a blob's bbox).
- [ ] Run: `.venv/bin/python -m pytest tests/test_characterise_screen.py -v` → all PASS (on unmodified code). If one fails, the test is wrong — fix the test, not the code.
- [ ] Commit.

### Task 2: Characterisation of mouse, movement, digits, GE, energy

**Files:** Create `tests/test_characterise_io.py`.

- [ ] Tests (must PASS on current code):
  `test_smart_right_click_detects_menu_top_left` (patch `mouse._move`, `mouse.pyautogui.rightClick` to switch the fake canvas to one with a 40×60 box painted at (120,80) inside the scan region; `random.randint` → 0; expect `menu_left, menu_top == 120, 80`); `test_smart_right_click_falls_back_to_click_coords` (no change → returns click coords);
  `test_wait_until_stopped_true_after_stable_frames` (frames: 3 differing then 4 identical; `time.sleep` no-op, `time.time` stepping 0.1) and `…_false_on_timeout` (frames always differ);
  `test_read_number_reads_synthetic_digits` (build templates by running `preprocess`+`segment_glyphs` on single synthetic glyph images for "1","4","7"; paint "47" on the canvas; `read_number` → `("47", 47)`) and `…_unknown_glyph_is_question_mark` (→ `value is None`, `"?"` in raw);
  GE via `with_example_config("lib", "ge", config="ge_config")`: `test_deposit_and_relocate_drags_changed_slot` (patch `human_click` to repaint one 36×32 slot in `GE_BANK_AREA`, `drag_and_drop` recorder → called from that slot's centre); `…_no_change_returns_false`;
  energy via `with_example_config("lib", "energy", config="energy_config")`: `test_maybe_drink_threshold` (patch `read_energy`, `drink_stamina`: 29 < 30 drinks, 30 doesn't, `None` doesn't); `test_restock_unreadable_energy_proceeds` (`read_energy → None`, stop before clicks by making `human_click` raise a sentinel → sentinel raised).
- [ ] Run → all PASS on current code. Commit. **From here on Tasks 1–2 test files are frozen.**

### Task 3: `lib/vision.py` — masks, locate, colour

**Files:** Create `lib/vision.py`; test `tests/test_vision.py`.
**Produces:** `color_mask(frame, rgb, tol) -> np.ndarray[bool]`; `polygon_mask(h, w, vertices) -> np.ndarray[bool]`; `click_point(xs, ys, jitter_pct, rng=random) -> (float, float)`; `locate(frame, rgb, tol, polygon=None, jitter_pct=0.25, rng=random) -> (Optional[(float, float)], int)` (frame-local); `color_close(rgb, expected, tol) -> bool`.

- [ ] Unit tests (seeded/stub rng with `.triangular` returning mode): mask tol boundary per channel; mask respects BGR order (pure red frame matches `(255,0,0)`); polygon mask of a square; `locate` centroid + count; empty → `(None, 0)`; polygon limits count; `click_point` spreads within ±`jitter_pct`×bbox (rng returning `lo` / `hi`); `color_close` boundary. Watch fail → implement → PASS → commit.

### Task 4: `lib/vision.py` — clusters

**Produces:** `clusters(xs, ys, radius) -> List[np.ndarray[bool]]` (member masks over the input points, greedy: seed = first remaining, members within `radius` of seed); `nearest_cluster_point(frame, rgb, tol, near, radius=30, jitter_pct=0.15, rng=random) -> (Optional[pt], int)` (frame-local, `near` frame-local, strict `<`); `count_clusters(frame, rgb, tol, radius) -> int`; `point_in_any_cluster(frame, rgb, tol, point, radius) -> bool`.

- [ ] Unit tests: two separated blobs → 2 clusters; one blob wider than `radius` → split per seed rule (document the case: 2 clusters for a 100px bar at radius 60); nearest picks nearer; equidistant → first; count 0 on empty; point inside bbox True / outside False / empty False. Watch fail → implement → PASS → commit.

### Task 5: `lib/vision.py` — slots, diffs, menu

**Produces:** `filled_slot_count(frame, slots, bg_rgb, tol, box=7, min_pixels=5) -> int`; `frame_difference(a, b) -> float`; `changed_slot(before, after, slot_w=36, slot_h=32, min_score=1000) -> Optional[(int, int)]` (frame-local centre); `menu_origin(before, after, threshold=20, min_pixels=20) -> Optional[(int, int)]` (frame-local top-left).

- [ ] Unit tests: slot filled only when ≥ `min_pixels` deviate (4 → not filled, 5 → filled); slot patch clipped at frame edge doesn't crash; identical frames → difference 0.0, known values → exact mean; changed slot centre on a half-stride grid; score below `min_score` → None; menu origin top-left; ≤ `min_pixels` changed → None. Watch fail → implement → PASS → commit.

### Task 6: Rewire capture callers onto vision

**Files:** `lib/screen.py` (add `grab(region) -> (frame, (off_x, off_y))`; `find_color`/`find_nearest_color`/`get_pixel_color`/`pixel_matches` = capture + vision; delete `_poly_mask`), GN `actions.py` (`count_filled_slots`, `count_broken_struts`, `character_in_any_vein` via `screen.grab` + vision; drop `_patch_deviating_count`), `lib/mouse.py` (`smart_right_click` via `menu_origin`), `lib/ge.py` (`_deposit_and_relocate` via `changed_slot`), `lib/movement.py` (`frame_difference` + `Stillness`), `lib/digit_templates.py` (`parse_number`), `lib/energy.py` (`needs_stamina`), `choc/logic.py` + `choc/run.py` (`restock_due`).
**Produces:** `movement.Stillness(thresh, stable_count)` with `update(diff) -> bool`; `digit_templates.parse_number(img, templates) -> (str, Optional[int])`; `energy.needs_stamina(energy, threshold, force=False, if_unreadable=False) -> bool`; `choc.logic.restock_due(remaining, grind_count) -> bool`.

- [ ] Unit tests first for the four new pure functions (`tests/test_pure_logic.py`): `Stillness` resets on motion, reports True on the `stable_count`-th calm frame; `parse_number` on a synthetic image; `needs_stamina` truth table incl. `force` and both `if_unreadable` values; `restock_due(40, 20) is False`, `restock_due(39, 20) is True`. Watch fail.
- [ ] Rewire each module; after each file run the full suite — Tasks 1–2 characterisation tests must pass **unchanged**.
- [ ] `grep -rn "np.abs\|np.where\|mss.mss" lib/screen.py lib/mouse.py lib/ge.py lib/movement.py miner/golden_nuggets/actions.py` → only capture code (`grab`) remains, no masking/diff maths.
- [ ] Imports: `.venv/bin/python -c "import tanner.run, miner.golden_nuggets.run, miner.varrock_exp.run, choc.run, crafting.run"` needs configs — run what exists locally; the suite covers the rest. Commit.

### Task 7: Docs

- [ ] CLAUDE.md: `lib/vision.py` in the layout; "Vision / pure logic" note (frame convention, new screen logic goes in vision with a unit test, `rng` parameter, characterisation-test pattern with `fake_screen`); the energy unreadable asymmetry. Suite green; commit.
