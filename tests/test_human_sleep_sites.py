import os
import re

import lib.human as human
import lib.mouse as mouse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPE = ["lib", "tanner", "miner", "choc"]


def iter_py(dirs, skip=()):
    """Every *.py under dirs (relative to the repo root), skipping paths with a `skip` part."""
    for d in dirs:
        for base, subdirs, files in os.walk(os.path.join(ROOT, d)):
            parts = set(os.path.relpath(base, ROOT).split(os.sep))
            if parts & set(skip) or "__pycache__" in parts:
                continue
            for f in files:
                if f.endswith(".py"):
                    yield os.path.join(base, f)


def test_no_uniform_sleeps_left():
    hits = [f"{os.path.relpath(p, ROOT)}:{i}" for p in iter_py(SCOPE, skip=("checks",))
            for i, line in enumerate(open(p, encoding="utf-8"), 1)
            if re.search(r"time\.sleep\((random|rng)\.uniform", line) and "# poll" not in line]
    assert hits == []


def test_hesitate_uses_human_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr(human, "sleep", lambda lo, hi, rng=None: calls.append((lo, hi)))
    mouse.hesitate()
    assert calls == [(0.3, 0.8)]


def test_no_instant_key_presses_left():
    hits = [f"{os.path.relpath(p, ROOT)}:{i}" for p in iter_py(SCOPE, skip=("checks",))
            for i, line in enumerate(open(p, encoding="utf-8"), 1)
            if re.search(r"pyautogui\.(press|typewrite)\(", line)]
    assert hits == []


def test_no_fixed_wait_next_to_a_key_press():
    hits = []
    for p in iter_py(SCOPE, skip=("checks",)):
        lines = open(p, encoding="utf-8").read().splitlines()
        for i, line in enumerate(lines):
            if "human_press(" in line and "def human_press" not in line:
                near = lines[max(0, i - 1):i + 2]
                if any(re.search(r"time\.sleep\(\d", l) for l in near):
                    hits.append(f"{os.path.relpath(p, ROOT)}:{i + 1}")
    assert hits == []
