"""
How this account's player behaves — PRO-8.

The OSRS server sees the cursor every 50 ms, each click's x/y with ms since the
last click, and each key with ms since the last key. It never sees hold times or
whether input was injected. So what has to look human is the timing and the
shape at that resolution; this module holds the timing half (lib/motion.py the
movement half).

- Profile: one player's habits, drawn once per account (seeded by sha256 of the
  name, so the same account behaves the same in every process). No account →
  DEFAULT, the middle of every range.
- delay(lo, hi): never below `lo` (callers chose it as the minimum the game
  needs), right-skewed above it, now and then a long lapse.
- next_tempo: a slow drift of the player's overall pace over a session.

Pure apart from sleep() and the module state reset() / active() keep.
"""
import hashlib
import math
import random
import time
from dataclasses import dataclass

import lib.accounts as accounts


@dataclass(frozen=True)
class Profile:
    fitts_a: float          # s — movement time = a + b·log2(D/W + 1)
    fitts_b: float          # s/bit
    peak_at: float          # fraction of a move at which speed peaks
    curvature: float        # sideways bow, × distance
    curve_side: float       # -1 / +1: which way this player's moves bow
    undershoot_p: float     # chance the first movement lands short
    reach_short: float      # fraction of the distance a short first movement covers
    reach_long: float       # … and a long one
    dwell_median: float     # s from stopping on a target to clicking it
    click_sd_frac: float    # click scatter SD, × target width
    delay_scale: float      # overall slowness
    lapse_p: float          # chance a delay gets an attention lapse added
    lapse_mean: float       # s, mean length of a lapse


RANGES = {
    "fitts_a": (0.05, 0.15),
    "fitts_b": (0.13, 0.20),
    "peak_at": (0.25, 0.38),
    "curvature": (0.015, 0.05),
    "undershoot_p": (0.55, 0.85),
    "reach_short": (0.94, 0.985),
    "reach_long": (1.025, 1.05),
    "dwell_median": (0.18, 0.28),
    "click_sd_frac": (0.20, 0.26),
    "delay_scale": (0.85, 1.20),
    "lapse_p": (0.01, 0.04),
    "lapse_mean": (0.8, 2.5),
}

DEFAULT = Profile(curve_side=1.0, **{k: (lo + hi) / 2 for k, (lo, hi) in RANGES.items()})

TEMPO_RANGE = (0.85, 1.2)
LAPSE_CAP = 3          # × lapse_mean


def profile_for(name):
    """This account's habits; DEFAULT for no account."""
    if not name:
        return DEFAULT
    seed = int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    drawn = {k: rng.uniform(lo, hi) for k, (lo, hi) in RANGES.items()}
    return Profile(curve_side=rng.choice((-1.0, 1.0)), **drawn)


def delay(lo, hi, rng=random, profile=DEFAULT, tempo=1.0):
    """Seconds to wait: `lo` plus a right-skewed share of the span (median 0.4 of
    it, capped at 4×), plus now and then a lapse (capped at LAPSE_CAP × its mean)."""
    span = (hi - lo) * profile.delay_scale * tempo
    x = min(rng.lognormvariate(math.log(0.4), 0.55), 4.0)
    d = lo + span * x
    if rng.random() < profile.lapse_p:   # capped: O / P can't cut a sleep short
        d += min(rng.expovariate(1 / profile.lapse_mean), LAPSE_CAP * profile.lapse_mean)
    return d


def hold_time(rng=random):
    """Seconds a key stays down: median ~110 ms, skewed (Dhakal 2018: 116 ± 24 ms). No lapses,
    and capped below the OS auto-repeat delay, so a held Escape or arrow never repeats."""
    return min(0.2, max(0.06, rng.lognormvariate(math.log(0.11), 0.2)))


def next_tempo(cur, rng=random):
    """One step of the session's slow pace drift, kept inside TEMPO_RANGE."""
    lo, hi = TEMPO_RANGE
    return min(hi, max(lo, cur * math.exp(rng.gauss(0, 0.02))))


# ── The running session's player ─────────────────────────────────────────────

_profile = None
_tempo = 1.0


def reset(account):
    """Start of a session: this account's profile, pace back to normal."""
    global _profile, _tempo
    _profile = profile_for(account)
    _tempo = 1.0


def active():
    if _profile is None:
        reset(accounts.active())
    return _profile


def tempo():
    return _tempo


def sleep(lo, hi, rng=random):
    """time.sleep for a human delay between lo and hi (see delay)."""
    global _tempo
    _tempo = next_tempo(_tempo, rng)
    time.sleep(delay(lo, hi, rng, active(), _tempo))
