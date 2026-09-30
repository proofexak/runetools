# Split decision logic from screen I/O — design

**Linear:** PRO-13 (sub-tasks PRO-45/46/47) · **Date:** 2026-09-30
**Branch:** `proofexak/pro-13-split-decision-logic-from-screen-io-for-real-unit` (from `main` e824c21)
**Status:** approved in brainstorming (scope "everything with logic", approach A)

## Goal

Every decision the bots make from the screen — where to click, is the
inventory full, is the character standing still, which slot changed, what
number is on screen, should we drink — becomes a pure function over plain data
(numpy frames, PIL images, numbers) that is unit-testable without OSRS, a
display or calibrated configs. Screen capture stays at the edge. Bots don't
change: public functions keep their names, signatures and results.

Acceptance (PRO-13, widened by the user to "everything with logic"):
- Inventory-full detection, energy reading + threshold, GE changed-slot
  detection, and all colour/cluster/click-point logic are unit-tested without
  OSRS running.
- Tests live in `tests/`.

## Conventions

- **Frame:** `numpy.uint8` array `(h, w, 3)` in **BGR** order — exactly what the
  current `np.array(mss_shot)[:, :, :3]` produces (red is channel 2).
- Vision functions work in **frame-local** coordinates; callers add the capture
  offset. Colours in and out stay `(r, g, b)`.
- Anything random takes `rng=random` (object with `.triangular`), so tests pass
  a seeded `random.Random` or a stub.

## `lib/vision.py` (new, pure: numpy + PIL only)

| function | replaces logic in |
|---|---|
| `color_mask(frame, rgb, tol) -> bool[h,w]` | `screen.find_color`, `screen.find_nearest_color`, GN `count_broken_struts`, GN `character_in_any_vein` |
| `polygon_mask(h, w, vertices) -> bool[h,w]` | `screen._poly_mask` |
| `click_point(xs, ys, jitter_pct, rng=random) -> (x, y)` | centroid + triangular ±jitter of the matched pixels' bbox |
| `locate(frame, rgb, tol, polygon=None, jitter_pct=0.25, rng=random) -> ((x, y) \| None, count)` | `find_color` decision |
| `clusters(xs, ys, radius) -> list[index array]` | greedy seed-radius clustering (seed = first remaining pixel; members within `radius` of the seed) — same algorithm, now one copy |
| `nearest_cluster_point(frame, rgb, tol, near, radius=30, jitter_pct=0.15, rng=random) -> ((x, y) \| None, count)` | `find_nearest_color` decision (cluster centroid nearest `near`, strict `<` so the first-found wins ties) |
| `count_clusters(frame, rgb, tol, radius) -> int` | GN `count_broken_struts` (radius 60) |
| `point_in_any_cluster(frame, rgb, tol, point, radius) -> bool` | GN `character_in_any_vein` (point inside a cluster's bbox, radius 40) |
| `filled_slot_count(frame, slots, bg_rgb, tol, box=7, min_pixels=5) -> int` | GN `count_filled_slots` (slot filled if ≥ `min_pixels` pixels in a `2*box` square deviate from `bg_rgb` by > `tol` on any channel) |
| `color_close(rgb, expected, tol) -> bool` | `screen.pixel_matches` |
| `frame_difference(a, b) -> float` | `movement` (mean over pixels of \|gray(a) − gray(b)\|, gray = channel mean) |
| `changed_slot(before, after, slot_w=36, slot_h=32, min_score=1000) -> (x, y) \| None` | GE `_deposit_and_relocate` (half-slot stride scan for the max summed diff) |
| `menu_origin(before, after, threshold=20, min_pixels=20) -> (x, y) \| None` | `mouse.smart_right_click` (top-left of pixels whose summed channel diff > threshold) |

## Capture side

- `lib/screen.py`: `grab(region) -> (frame, (off_x, off_y))` (monitor-1 relative,
  as today). `find_color`, `find_nearest_color`, `get_pixel_color`,
  `pixel_matches` keep their signatures and become capture + vision call.
  Known quirk kept as-is: `get_pixel_color` does not add monitor 1's origin
  while `find_color` does (identical on a single monitor).
- GN `count_filled_slots`, `count_broken_struts`, `character_in_any_vein`,
  GE `_deposit_and_relocate`, `mouse.smart_right_click`,
  `movement.wait_until_stopped` capture with `screen.grab` (or their existing
  grab) and call vision.

## Other pure logic

| where | pure function | caller(s) |
|---|---|---|
| `lib/digit_templates.py` | `parse_number(img, templates) -> (raw, value)` | `read_number` = capture + `parse_number` |
| `lib/energy.py` | `needs_stamina(energy, threshold, force=False, if_unreadable=False) -> bool` | `maybe_drink_stamina` (`if_unreadable=False`), `restock_stamina_at_bank` (`if_unreadable=True`) |
| `lib/movement.py` | `Stillness(thresh, stable_count)`, `.update(diff) -> bool` | `wait_until_stopped` |
| `choc/logic.py` (new) | `restock_due(remaining, grind_count) -> bool` (= `remaining - grind_count < grind_count`) | `choc/run.py` |

Kept, flagged: unreadable energy → `maybe_drink_stamina` does **not** drink,
`restock_stamina_at_bank` **does**. The flag makes that explicit; behaviour
unchanged.

Out of scope: poll/retry loops (bank-open, GE offer, GN depletion — already
fake-clock tested), `woodcutter/`, `calibrate_energy_digits.py` (keeps using
`preprocess`/`segment_glyphs`, which stay).

## Behaviour preservation (TDD order)

1. **Characterisation tests first**, against today's code: a `fake_screen`
   fixture patches `mss.mss` with a synthetic canvas and pins
   `random.triangular` to its mode; tests call the public functions listed
   above and assert their results. They must pass before any refactor.
2. Refactor; the same tests must still pass unchanged (equivalence proof).
3. Unit tests on the pure functions, incl. edges: empty mask, tolerance
   boundary (`== tol` matches, `tol+1` doesn't), equidistant clusters, polygon
   edge, unreadable glyph (`?`), threshold boundary, stillness reset on motion.

Tests needing `lib/energy_config` load `lib/energy_config.example.py` via the
`with_example_config` fixture (extended to take the config module name).

## Documentation

CLAUDE.md: `lib/vision.py` in the layout; a short "Vision / pure logic" note
(frame convention, where new screen logic goes, `rng` for randomness, the
characterisation-test pattern); the energy unreadable-value asymmetry.
