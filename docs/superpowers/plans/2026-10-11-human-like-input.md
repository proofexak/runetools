# Human-like Input (PRO-8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the bots' input look human at the resolution the OSRS server sees it (cursor every 50 ms, click x/y + ms since last click, key + ms since last key): skewed delays, Fitts-timed moves with an early speed peak and an end correction, Gaussian click scatter, a human-tempo choc grind, and an irregular cursor nudge instead of the ←/→ keep-awake.

**Architecture:** Two new pure modules: `lib/human.py` (per-account profile, skewed delays, slow tempo drift) and `lib/motion.py` (timestamped move plans, click offsets, dwell). `lib/mouse.py` plays the plans on a deadline clock. Call sites keep their `lo, hi` ranges and their `jitter(x, y, n)` calls; only the distributions behind them change.

**Tech Stack:** Python 3.11, stdlib `random` / `hashlib` / `math`, pyautogui (only in `lib/mouse.py`), pytest.

**Spec:** Research doc "Human-like mouse input research (PRO-8)" — https://claude.ai/code/artifact/d05808b3-de2e-471b-8a04-faf84766864a (the "Applied to runetools" table, changes 1–6) and the PRO-8 Linear comment of 2026-10-11.

## Global Constraints

- No new dependencies: stdlib + what's already in `.venv`.
- `lib/human.py` and `lib/motion.py` are pure: no pyautogui, mss, `time.sleep`, or config imports at module level; randomness only through an `rng` parameter (CLAUDE.md "Vision / pure logic").
- `tests/test_characterise_*.py` are frozen. `smart_right_click` keeps calling `_move(ax, ay)` with exactly two positional args and keeps its own `random.randint(-3, 3)` offset (the characterisation test patches both).
- A delay never comes out below the caller's `lo` (callers chose `lo` as a minimum the game needs). Only the upper side may grow.
- No point a move plan emits may have `x < 1` or `y < 1` (pyautogui's corner failsafe raises at (0, 0)).
- Profiles are stable per account across processes: seed with `hashlib.sha256`, never `hash()`.
- Commits: short messages, no co-author line (user preference).

## Review Focus

1. **Move of 0–1 px** (cursor already on the target): no ZeroDivision, plan is one point at the target. → Task 3 `test_plan_move_zero_distance`.
2. **Target near the top-left corner**: an overshoot or curve must not reach x ≤ 0 or y ≤ 0. → Task 3 `test_plan_move_never_touches_corner`.
3. **No active account / odd names** (None, "", non-ASCII): default profile, no exception, same profile in a fresh process. → Task 1 `test_profile_for_none_is_default`, `test_profile_stable_across_processes`.
4. **Callers that rely on a minimum wait** (potion cooldown 1.3 s, GE `EDIT_LOAD`, teleport landing): never shorter than `lo`. → Task 1 `test_delay_never_below_lo`.
5. **Keep-awake gap reaching the 5-minute logout**: every nudge interval < 270 s even with a lapse. → Task 5 `test_next_nudge_bounds`.

---

### Task 1: `lib/human.py` — profile, skewed delay, tempo

**Files:**
- Create: `lib/human.py`
- Modify: `lib/session.py:58` (reset the profile at session start)
- Test: `tests/test_human.py`, `tests/test_session.py` (one added test)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Profile` with float fields `fitts_a, fitts_b, peak_at, curvature, curve_side, undershoot_p, reach_short, reach_long, dwell_median, click_sd_frac, delay_scale, lapse_p, lapse_mean`
  - `DEFAULT: Profile` — the midpoint of every range below, `curve_side = 1.0`
  - `profile_for(name: str | None) -> Profile`
  - `delay(lo: float, hi: float, rng=random, profile: Profile = DEFAULT, tempo: float = 1.0) -> float`
  - `next_tempo(cur: float, rng=random) -> float`
  - `reset(account: str | None) -> None`, `active() -> Profile`, `tempo() -> float`
  - `sleep(lo: float, hi: float, rng=random) -> None` — the one impure function: steps `_tempo = next_tempo(_tempo, rng)`, then `time.sleep(delay(lo, hi, rng, active(), _tempo))`

Profile ranges (each drawn uniformly once per account from `random.Random(int.from_bytes(sha256(name.encode()).digest()[:8], "big"))`):

| Field | Range | From |
|---|---|---|
| `fitts_a` (s) | 0.05–0.15 | MacKenzie 1991, faster than lab for practised players |
| `fitts_b` (s/bit) | 0.13–0.20 | idem; spread per Chapuis 2007 |
| `peak_at` | 0.25–0.38 | Phillips & Triggs: ~70% deceleration |
| `curvature` (× distance) | 0.015–0.05 | MacKenzie 2001: ~3% deviation |
| `curve_side` | −1 or +1 (p = 0.5) | per-user consistency (Zheng 2011) |
| `undershoot_p` | 0.55–0.85 | Müller 2017 vs Phillips & Triggs |
| `reach_short` | 0.94–0.985 | Müller 2017: 94–99% |
| `reach_long` | 1.025–1.05 | Phillips & Triggs: 2.5–5% |
| `dwell_median` (s) | 0.18–0.28 | Chapuis 2007: 185 lab / 277 field |
| `click_sd_frac` (× width) | 0.20–0.26 | ISO 9241-9: 1/4.133 = 0.242 |
| `delay_scale` | 0.85–1.20 | per-person speed |
| `lapse_p` | 0.01–0.04 | vigilance lapses |
| `lapse_mean` (s) | 0.8–2.5 | idem |

`delay` algorithm (the tests pin the bounds, not the shape):

```python
span = (hi - lo) * profile.delay_scale * tempo
x = min(rng.lognormvariate(math.log(0.4), 0.55), 4.0)   # median 0.4 of the span, right tail
d = lo + span * x
if rng.random() < profile.lapse_p:
    d += rng.expovariate(1 / profile.lapse_mean)
return d
```

`next_tempo`: `min(1.2, max(0.85, cur * math.exp(rng.gauss(0, 0.02))))`. Module state `_profile`, `_tempo`; `reset()` sets `_profile = profile_for(account)`, `_tempo = 1.0`; `active()` lazily calls `reset(accounts.active())` on first use.

- [ ] **Step 1: Write the failing tests** in `tests/test_human.py`

```python
def test_delay_never_below_lo():
    rng = random.Random(1)
    assert min(human.delay(0.3, 0.5, rng) for _ in range(5000)) >= 0.3

def test_delay_is_right_skewed():
    rng = random.Random(2)
    ds = sorted(human.delay(0.3, 0.5, rng) for _ in range(5000))
    median, mean = ds[2500], sum(ds) / len(ds)
    assert 0.3 < median < 0.5 and mean > median
    assert ds[-1] > 0.5            # a tail past hi exists

def test_delay_without_lapses_is_capped():
    p = dataclasses.replace(human.DEFAULT, lapse_p=0.0)
    rng = random.Random(3)
    assert max(human.delay(0.3, 0.5, rng, p) for _ in range(5000)) <= 0.3 + 0.2 * p.delay_scale * 4.0 + 1e-9

def test_profile_for_none_is_default():
    assert human.profile_for(None) == human.DEFAULT
    assert human.profile_for("") == human.DEFAULT

def test_profile_differs_per_account_and_is_stable():
    assert human.profile_for("alt1") == human.profile_for("alt1")
    assert human.profile_for("alt1") != human.profile_for("alt2")
    assert human.profile_for("żółw") == human.profile_for("żółw")

def test_profile_stable_across_processes():
    code = "import lib.human as h; print(repr(h.profile_for('alt1')))"
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={**os.environ, "PYTHONHASHSEED": seed}, cwd=ROOT).stdout
            for seed in ("1", "2")}
    assert len(outs) == 1

def test_profile_fields_in_range():
    p = human.profile_for("alt1")
    assert 0.13 <= p.fitts_b <= 0.20 and 0.25 <= p.peak_at <= 0.38 and p.curve_side in (-1.0, 1.0)

def test_next_tempo_stays_bounded():
    rng, t = random.Random(4), 1.0
    for _ in range(100_000):
        t = human.next_tempo(t, rng)
        assert 0.85 <= t <= 1.2

# in tests/test_session.py, reusing its `calls` fixture and `_run` helper:
def test_session_start_resets_profile(calls, monkeypatch):
    monkeypatch.setenv("RUNETOOLS_ACCOUNT", "alt1")
    _run({}, calls)
    assert human.active() == human.profile_for("alt1") and human.tempo() == 1.0
```

- [ ] **Step 2: Run the tests to make sure they fail**

Run: `.venv/Scripts/python -m pytest tests/test_human.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'lib.human'`

- [ ] **Step 3: Implement `lib/human.py`** per the Interfaces block and the algorithm above. In `lib/session.py`, read `account = accounts.active()` once, pass it to `session_start`, and call `human.reset(account)` right after.

- [ ] **Step 4: Run the tests to make sure they pass**

Run: `.venv/Scripts/python -m pytest tests/test_human.py tests/test_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lib/human.py lib/session.py tests/test_human.py
git commit -m "human: per-account profile, skewed delays, tempo drift"
```

---

### Task 2: Move every pre-input sleep onto `human.sleep`

**Files:**
- Modify: the 44 `time.sleep(random.uniform(...))` / `time.sleep(rng.uniform(...))` sites in `lib/camera.py`, `lib/energy.py`, `lib/ge.py`, `lib/mouse.py`, `tanner/actions.py`, `tanner/run.py`, `miner/golden_nuggets/actions.py`, `miner/varrock_exp/actions.py`, `choc/choc.py`, `choc/run.py`; `lib/ge.py:40` `_pause`; `lib/mouse.py:162` `hesitate`; `lib/mouse.py:124` `human_typewrite`'s per-character delay
- Test: `tests/test_human_sleep_sites.py`

**Interfaces:**
- Consumes: `human.sleep(lo, hi, rng=random)` (Task 1)

Mechanical rule: `time.sleep(random.uniform(a, b))` → `human.sleep(a, b)`; `time.sleep(rng.uniform(a, b))` → `human.sleep(a, b, rng=rng)`. Leave alone: `poll=lambda: random.uniform(...)` screen-poll intervals (not input), fixed `time.sleep(0.6)`-style waits, anything under `*/checks/`, `woodcutter/`, `crafting/`.

- [ ] **Step 1: Write the failing test**

```python
SCOPE = ["lib", "tanner", "miner", "choc"]

# iter_py(dirs, skip): helper in this file — every *.py under dirs, skipping paths containing a `skip` part
def test_no_uniform_sleeps_left():
    hits = [f"{p}:{i}" for p in iter_py(SCOPE, skip=("checks",))
            for i, line in enumerate(open(p, encoding="utf-8"), 1)
            if re.search(r"time\.sleep\((random|rng)\.uniform", line)]
    assert hits == []

def test_hesitate_uses_human_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr(human, "sleep", lambda lo, hi, rng=None: calls.append((lo, hi)))
    mouse.hesitate()
    assert calls == [(0.3, 0.8)]
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `.venv/Scripts/python -m pytest tests/test_human_sleep_sites.py -v`
Expected: FAIL listing the 44 sites

- [ ] **Step 3: Rewrite the sites** per the rule above. `_pause(lo, hi)` becomes `human.sleep(lo, hi)`.

- [ ] **Step 4: Run the whole suite and time it**

Run: `.venv/Scripts/python -m pytest -q --durations=5`
Expected: all pass; no test in the top 5 durations is new compared with `git stash; pytest -q --durations=5; git stash pop` (lapses must not turn into real sleeps in tests — existing tests patch `time.sleep` on the shared `time` module, which `human.sleep` uses)

- [ ] **Step 5: Commit**

```bash
git add -A lib tanner miner choc tests/test_human_sleep_sites.py
git commit -m "Delays before input: skewed per-account instead of uniform"
```

---

### Task 3: `lib/motion.py` — move plans, click offsets, dwell

**Files:**
- Create: `lib/motion.py`
- Test: `tests/test_motion.py`

**Interfaces:**
- Consumes: `human.Profile`, `human.DEFAULT` (Task 1)
- Produces:
  - `plan_move(start: tuple[int, int], end: tuple[int, int], width: float, profile: Profile, rng=random, mode: str = "aim", tempo: float = 1.0) -> list[tuple[float, int, int]]` — `(t seconds from 0, x, y)`, t strictly increasing, last point `== end`
  - `fitts_time(distance: float, width: float, profile: Profile) -> float` = `profile.fitts_a + profile.fitts_b * log2(distance / width + 1)`
  - `click_offset(width: float, profile: Profile, rng=random) -> int` — `round(gauss(0, profile.click_sd_frac * width))` clamped to ±`width // 2`
  - `dwell(profile: Profile, rng=random, mode: str = "aim") -> float` — aim: `lognormvariate(log(profile.dwell_median), 0.3)`; reciprocal: `uniform(0.04, 0.09)`

`plan_move` algorithm (the tests check its output, not these steps):

1. `D = dist(start, end)`; `D < 2` → `[(0.0, *end)]`.
2. `MT = fitts_time(D, width, profile) * tempo`; `mode == "reciprocal"` → `MT *= 0.6`, no correction.
3. Correction if aim and `D >= 2 * width` with p = 0.85, else p = 0.2. With a correction the primary aims at `start + (end - start) * r`, with `r = reach_short` (p = `undershoot_p`) or `reach_long` (each ± `uniform(-0.01, 0.01)`), and takes `0.75 * MT`. Without one, it aims at `end` and takes `MT`.
4. Primary path: a cubic Bézier from start to the primary aim. Control points sit at 30% and 70% along the line, pushed perpendicular by `curve_side * curvature * D * uniform(0.5, 1.5)` and `-curve_side * curvature * D * uniform(0, 0.6)` respectively (the second makes some paths cross the line).
5. Time warp: the fraction of the path done at normalised time τ is the Beta(2, β) CDF with `β = 1 / peak_at`: `u(τ) = 1 - (1 - τ)**β * (1 + β * τ)`. This peaks speed at τ = `peak_at`.
6. With a correction: a pause of `uniform(0.03, 0.09)` s (no points), then a near-straight segment to `end` taking `max(0.06, 0.25 * MT)` with the same warp at `peak_at = 0.4`.
7. Sample times: start at 0, step `uniform(0.006, 0.010)` s, always include the segment's end time. Round to int and clamp `x, y >= 1`.

- [ ] **Step 1: Write the failing tests** (seeded `random.Random`, `DEFAULT` profile unless stated)

```python
def test_plan_move_zero_distance():
    assert motion.plan_move((100, 100), (100, 101), 16, DEFAULT, random.Random(0)) == [(0.0, 100, 101)]

def test_plan_ends_exactly_on_target_with_increasing_time():
    pts = motion.plan_move((50, 60), (450, 300), 16, DEFAULT, random.Random(1))
    assert pts[-1][1:] == (450, 300)
    assert all(b[0] > a[0] for a, b in zip(pts, pts[1:]))

def test_plan_move_never_touches_corner():
    for s in range(300):
        pts = motion.plan_move((500, 500), (2, 2), 16, DEFAULT, random.Random(s))
        assert min(min(x, y) for _, x, y in pts) >= 1

def test_duration_follows_fitts():
    for s in range(100):
        pts = motion.plan_move((10, 10), (410, 10), 30, DEFAULT, random.Random(s))
        mt = motion.fitts_time(400, 30, DEFAULT)
        assert mt - 1e-6 <= pts[-1][0] <= mt + 0.1

def test_sample_intervals_vary():
    pts = motion.plan_move((10, 10), (410, 210), 16, DEFAULT, random.Random(2))
    dts = [b[0] - a[0] for a, b in zip(pts, pts[1:])]
    steps = [d for d in dts if d <= 0.0101]
    gaps = [d for d in dts if d > 0.0101]           # the pause before a correction
    assert statistics.pstdev(steps) > 0.0005
    assert len(gaps) <= 1 and all(0.03 <= g <= 0.0901 for g in gaps)

def test_reciprocal_is_fast_and_single():
    pts = motion.plan_move((100, 100), (100, 140), 30, DEFAULT, random.Random(3), mode="reciprocal")
    assert pts[-1][0] < 0.25

def test_click_offset_gaussian_and_clamped():
    rng = random.Random(4)
    xs = [motion.click_offset(16, DEFAULT, rng) for _ in range(20000)]
    assert max(map(abs, xs)) <= 8
    assert 0.8 * 0.23 * 16 < statistics.pstdev(xs) < 1.1 * 0.23 * 16
    assert xs.count(0) > xs.count(7)          # peaked, not uniform
```

Human-likeness at the server's resolution (resample each plan by holding the last position at t = 0, 0.05, 0.10, …):

```python
def test_human_likeness_at_50ms():
    peaks, devs, subs = [], [], []
    for s in range(200):
        pts = motion.plan_move((100, 300), (500, 300), 16, DEFAULT, random.Random(s))
        xy = resample_50ms(pts)                         # helper in this test file
        speed = [dist(a, b) for a, b in zip(xy, xy[1:])]
        peaks.append(speed.index(max(speed)) / len(speed))
        devs.append(max(abs(y - 300) for _, y in xy) / 400)
        subs.append(count_local_maxima(speed, floor=0.1 * max(speed)))
    assert 0.15 <= statistics.median(peaks) <= 0.45
    assert 0.01 <= statistics.median(devs) <= 0.08
    assert sum(1 <= n <= 3 for n in subs) >= 0.9 * len(subs)
```

(The doc's "path / distance 1.2–1.7" check is dropped: Chapuis measured full-rate field paths with all wandering, which isn't comparable to one planned move at 50 ms. MacKenzie 2001's ~3% deviation is used instead.)

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/Scripts/python -m pytest tests/test_motion.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'lib.motion'`

- [ ] **Step 3: Implement `lib/motion.py`** per the Interfaces block and the algorithm.

- [ ] **Step 4: Run them to make sure they pass**

Run: `.venv/Scripts/python -m pytest tests/test_motion.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lib/motion.py tests/test_motion.py
git commit -m "motion: Fitts-timed move plans with end correction, Gaussian click scatter"
```

---

### Task 4: Wire `lib/mouse.py` to the plans; choc's grind on the new model; document

**Files:**
- Modify: `lib/mouse.py:14-47` (`_make_ease`, `_bezier`, `_move` replaced), `:56-60` `human_click`, `:63-71` `human_right_click`, `:138-148` `menu_click` + `jitter`, `:167-174` `quick_click`
- Modify: `CLAUDE.md` (new "Human-like input (PRO-8)" paragraph under Key design decisions; `lib/` layout lines for `human.py`, `motion.py`)
- Test: `tests/test_mouse.py`

**Interfaces:**
- Consumes: `motion.plan_move`, `motion.click_offset`, `motion.dwell` (Task 3); `human.active()`, `human.tempo()`, `human.sleep` (Task 1)
- Produces (signatures callers already use stay valid):
  - `_move(x2, y2, width=16, mode="aim")` — plans from `pyautogui.position()`, then plays: `t0 = time.perf_counter()`; for each `(t, x, y)` sleep until `t0 + t`, then `_set_cursor(x, y)`
  - `jitter(x, y, n=8, rng=random)` → `(x + click_offset(2 * n), y + click_offset(2 * n))` with `human.active()`
  - `human_click(x, y)` / `human_right_click(x, y)`: `human.sleep(0.1, 0.18)` → `_move(ax, ay)` with `ax, ay = x + click_offset(6), y + click_offset(6)` → `time.sleep(motion.dwell(...))` → click. `human_right_click` still returns `(ax, ay)`
  - `menu_click(x, y)`: target width 30 in x and 4 in y, then `_move`, dwell, click
  - `quick_click(x, y)`: `_move(*jitter(x, y), mode="reciprocal")`, `time.sleep(motion.dwell(..., mode="reciprocal"))`, click
  - `smart_right_click`: unchanged apart from what `_move` does (Global Constraints)

`choc/choc.py:108-113` needs no edit: it calls `quick_click`, and Task 2 already moved its sleeps.

- [ ] **Step 1: Write the failing tests** in `tests/test_mouse.py`. A `fake_input` fixture (in this file) starts the cursor at `START = (10, 10)` and uses a fake clock: patch `mouse.time.perf_counter` to return `now[0]`, and `mouse.time.sleep` to add its argument to `now[0]`; record `pyautogui.moveTo` positions and `pyautogui.click` calls; set `pyautogui.position` to return the last recorded move.

```python
def test_human_click_moves_in_steps_then_clicks_once(fake_input):
    mouse.human_click(400, 300)
    assert len(fake_input.moves) >= 5 and fake_input.clicks == 1
    ex, ey = fake_input.moves[-1]
    assert abs(ex - 400) <= 3 and abs(ey - 300) <= 3

def test_human_click_dwells_before_clicking(fake_input):
    mouse.human_click(400, 300)
    assert fake_input.time_at_click - fake_input.time_at_last_move >= 0.1

def test_move_is_paced_by_the_plan(fake_input):
    mouse._move(410, 10)
    assert fake_input.now >= motion.fitts_time(dist(START, (410, 10)), 16, human.active()) * 0.85

def test_quick_click_no_longer_tweens_straight(fake_input):
    mouse.quick_click(100, 140)
    assert all(kw.get("duration") in (None, 0) for kw in fake_input.move_kwargs)
    assert len(fake_input.moves) >= 3

def test_jitter_is_gaussian_within_n():
    rng = random.Random(5)
    xs = [mouse.jitter(0, 0, n=8, rng=rng)[0] for _ in range(20000)]
    assert max(map(abs, xs)) <= 8 and xs.count(0) > xs.count(8)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/Scripts/python -m pytest tests/test_mouse.py -v`
Expected: FAIL (dwell, pacing and quick_click assertions)

- [ ] **Step 3: Implement** per the Interfaces block. Delete `_make_ease` and `_bezier`. Write the CLAUDE.md paragraph: what the server sees (50 ms cursor, click x/y + ms, key + ms, no hold times), the profile per account (`lib/human.py`), skewed delays with `lo` as a floor, `motion.plan_move`, `jitter` = Gaussian within ±n, and the rule for new bots: use `human.sleep` / `human_click` / `jitter`, never raw `random.uniform` sleeps or `pyautogui.moveTo(duration=…)`.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass, `tests/test_characterise_io.py` included

- [ ] **Step 5: Live check before trusting a session.** Run `.venv/Scripts/python -m choc.checks.sequence` with the client open. Expected: one full grind batch completes, and every click lands on its slot (watch for misclicks on the knife/bar).

- [ ] **Step 6: Commit**

```bash
git add lib/mouse.py tests/test_mouse.py CLAUDE.md
git commit -m "mouse: play motion plans, dwell before clicks, Gaussian jitter"
```

---

### Task 5: Keep-awake by irregular cursor nudges

**Files:**
- Modify: `lib/ge.py:31` (`KEEP_AWAKE`), `:127-146` (`keep_awake`, `wait_offer`)
- Create: `lib/checks/keep_awake.py`
- Modify: `CLAUDE.md` GE-flow sentence "every offer wait taps ← then → …"
- Test: `tests/test_ge_restock.py` (add tests)

**Interfaces:**
- Consumes: `human.delay`, `human.active()` (Task 1), `mouse.human_move` (Task 4)
- Produces:
  - `KEEP_AWAKE = (45, 150)`, `KEEP_AWAKE_MAX = 270`
  - `next_nudge(rng=random) -> float` = `min(KEEP_AWAKE_MAX, human.delay(*KEEP_AWAKE, rng, human.active()))`
  - `keep_awake(rng=random)` — `human_move` to the current position + an offset of `rng.randint(-40, 40)`, `rng.randint(-25, 25)`, redrawn until it's at least 8 px. No click, no keys
  - `wait_offer` schedules with `next_nudge()` instead of `random.uniform(*KEEP_AWAKE)`

The wiki's Idle page says cursor movement inside the game window resets the 5-minute logout even when the window is inactive. The cursor rests on the GE interface during a wait, so it is inside the window.

- [ ] **Step 1: Write the failing tests**

```python
def test_next_nudge_bounds():
    rng = random.Random(6)
    xs = [ge.next_nudge(rng) for _ in range(20000)]
    assert min(xs) >= 45 and max(xs) <= 270 and len(set(xs)) > 1000

def test_keep_awake_moves_without_keys(monkeypatch):
    moved, keys = [], []
    monkeypatch.setattr(ge, "human_move", lambda x, y: moved.append((x, y)))
    monkeypatch.setattr(ge.pyautogui, "position", lambda: (300, 200))
    monkeypatch.setattr(ge.pyautogui, "keyDown", lambda k: keys.append(k))
    ge.keep_awake(random.Random(7))
    (x, y), = moved
    assert keys == [] and 8 <= math.hypot(x - 300, y - 200) <= math.hypot(40, 25)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/Scripts/python -m pytest tests/test_ge_restock.py -k "nudge or keep_awake" -v`
Expected: FAIL (`next_nudge` missing; `keep_awake` presses keys)

- [ ] **Step 3: Implement** per the Interfaces block. Then write `lib/checks/keep_awake.py`, following the live-check rules: work in `main()` behind `if __name__ == "__main__":`, never named `test_*`. With the game logged in and the cursor over the game view, it loops for 8 minutes, calling `keep_awake()` every `next_nudge()` seconds and printing each nudge. Update the CLAUDE.md sentence to "every offer wait nudges the cursor (`keep_awake`, no click) at skewed 45–150 s intervals, never more than 270 s apart".

- [ ] **Step 4: Run the suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Live check.** `.venv/Scripts/python -m lib.checks.keep_awake` with the client logged in, then leave it untouched. Expected: still logged in after 8 minutes. If it logs out, stop: the wiki's cursor-reset claim doesn't hold for this client, and `keep_awake` goes back to keys.

- [ ] **Step 6: Commit**

```bash
git add lib/ge.py lib/checks/keep_awake.py tests/test_ge_restock.py CLAUDE.md
git commit -m "GE waits: keep awake with irregular cursor nudges instead of arrow keys"
```

---

## Not in this plan

- **Choc idle inventories** (one knife-on-bar click, then let it auto-grind): waiting on the open question in the research doc, and on how long an auto-ground inventory takes.
- **Raw `pyautogui.press` audit**: PRO-29 / PRO-30. Key timing is already covered by Task 2's skewed sleeps before each press.
- **Breaks and fatigue across a session**: PRO-60.
