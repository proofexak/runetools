import dataclasses
import os
import random
import subprocess
import sys

import lib.human as human

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    assert len(outs) == 1 and "Profile(" in outs.pop()


def test_profile_fields_in_range():
    p = human.profile_for("alt1")
    assert 0.13 <= p.fitts_b <= 0.20 and 0.25 <= p.peak_at <= 0.38 and p.curve_side in (-1.0, 1.0)


def test_next_tempo_stays_bounded():
    rng, t = random.Random(4), 1.0
    for _ in range(100_000):
        t = human.next_tempo(t, rng)
        assert 0.85 <= t <= 1.2


def test_lapse_is_capped():
    p = dataclasses.replace(human.DEFAULT, lapse_p=1.0)
    rng = random.Random(8)
    worst = max(human.delay(0.3, 0.5, rng, p) for _ in range(20000))
    assert worst <= 0.3 + 0.2 * p.delay_scale * 4.0 + 3 * p.lapse_mean + 1e-9


def test_hold_time_is_a_finger_not_zero():
    rng = random.Random(9)
    hs = sorted(human.hold_time(rng) for _ in range(20000))
    assert hs[0] > 0.05 and hs[-1] <= 0.2            # capped: never long enough to auto-repeat
    assert 0.09 <= hs[10000] <= 0.13                 # Dhakal 2018: 116 ± 24 ms
