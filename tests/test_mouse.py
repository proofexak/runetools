import math
import random
from types import SimpleNamespace

import pytest

import lib.human as human
import lib.motion as motion
import lib.mouse as mouse

START = (10, 10)


@pytest.fixture
def fake_input(monkeypatch):
    """Cursor starts at START; a fake clock that only sleep() moves; every moveTo and click recorded."""
    s = SimpleNamespace(screen=(1920, 1080), now=0.0, moves=[], move_kwargs=[], clicks=0, time_at_click=None, time_at_last_move=None)
    pos = [START]

    def sleep(sec):
        s.now += max(0.0, sec)

    def move_to(x, y, duration=None, **kw):
        s.moves.append((x, y)); s.move_kwargs.append({"duration": duration, **kw})
        s.time_at_last_move = s.now
        pos[0] = (x, y)

    def click(*a, **kw):
        s.clicks += 1
        s.time_at_click = s.now

    monkeypatch.setattr(mouse.time, "sleep", sleep)
    monkeypatch.setattr(mouse.time, "perf_counter", lambda: s.now)
    monkeypatch.setattr(mouse.pyautogui, "moveTo", move_to)
    monkeypatch.setattr(mouse.pyautogui, "position", lambda: pos[0])
    monkeypatch.setattr(mouse.pyautogui, "size", lambda: s.screen)
    monkeypatch.setattr(mouse.pyautogui, "click", click)
    human.reset(None)
    return s


def test_human_click_moves_in_steps_then_clicks_once(fake_input):
    mouse.human_click(400, 300)
    assert len(fake_input.moves) >= 5 and fake_input.clicks == 1
    ex, ey = fake_input.moves[-1]
    assert abs(ex - 400) <= 3 and abs(ey - 300) <= 3


def test_human_click_dwells_before_clicking(fake_input):
    dwells = []
    for _ in range(30):
        mouse.human_click(400, 300)
        dwells.append(fake_input.time_at_click - fake_input.time_at_last_move)
    assert min(dwells) > 0 and sorted(dwells)[15] >= 0.17      # Chapuis 2007: 185-277 ms


def test_move_is_paced_by_the_plan(fake_input):
    mouse._move(410, 10)
    assert fake_input.now >= motion.fitts_time(math.dist(START, (410, 10)), 16, human.active()) * 0.85


def test_quick_click_no_longer_tweens_straight(fake_input):
    mouse.quick_click(100, 140)
    assert all(kw.get("duration") in (None, 0) for kw in fake_input.move_kwargs)
    assert len(fake_input.moves) >= 3 and fake_input.clicks == 1


def test_jitter_is_gaussian_within_n():
    rng = random.Random(5)
    xs = [mouse.jitter(0, 0, n=8, rng=rng)[0] for _ in range(20000)]
    assert max(map(abs, xs)) <= 8 and xs.count(0) > xs.count(8)


def test_move_stays_off_the_bottom_right_corner(fake_input):
    fake_input.screen = (200, 150)
    for _ in range(50):
        mouse._move(20, 20)          # far away again, so every approach can overshoot
        mouse._move(196, 146)
    assert max(x for x, _ in fake_input.moves) <= 198 and max(y for _, y in fake_input.moves) <= 148


@pytest.fixture
def keys(fake_input, monkeypatch):
    log = []
    monkeypatch.setattr(mouse.pyautogui, "keyDown", lambda k: log.append(("down", k, fake_input.now)))
    monkeypatch.setattr(mouse.pyautogui, "keyUp", lambda k: log.append(("up", k, fake_input.now)))
    monkeypatch.setattr(mouse.pyautogui, "press", lambda *a, **k: pytest.fail("instant press"))
    monkeypatch.setattr(mouse.pyautogui, "typewrite", lambda *a, **k: pytest.fail("instant typewrite"))
    return log


def test_human_press_holds_the_key(keys):
    mouse.human_press("escape")
    (d, k1, t0), (u, k2, t1) = keys
    assert (d, k1, u, k2) == ("down", "escape", "up", "escape") and 0.05 < t1 - t0 <= 0.2


def test_typing_holds_every_key(keys):
    mouse.human_typewrite("ab 1")
    assert [(e, k) for e, k, _ in keys] == [("down", "a"), ("up", "a"), ("down", "b"), ("up", "b"),
                                            ("down", "space"), ("up", "space"), ("down", "1"), ("up", "1")]
    holds = [b[2] - a[2] for a, b in zip(keys[::2], keys[1::2])]
    assert all(h > 0.05 for h in holds)
