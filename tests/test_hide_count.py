"""PRO-100: tanner restocks when the hide stack is down to its last 1 — OSRS draws no
count number on a stack of 1, so "1 left" = no number on the hide stack."""
import pytest

from lib import vision
from tests.fakescreen import canvas, paint

BANK_BG = (62, 53, 41)          # bank background
SHADOW = (0, 0, 1)              # the number's black drop shadow
HIDE = (40, 40, 44)             # a dark dragonhide icon


def _slot_top(number_rgb=None):
    """The top-left corner of a bank slot: icon, and a '1920'-like count when number_rgb."""
    f = paint(canvas(26, 10, BANK_BG), 4, 4, 18, 6, HIDE)
    if number_rgb:
        for i, x in enumerate((1, 6, 11, 16)):            # four 1-px-stroke digits
            paint(f, x + 1, 2, 3, 6, SHADOW)
            paint(f, x, 1, 1, 6, number_rgb)
            paint(f, x, 1, 3 if i % 2 else 1, 1, number_rgb)
    return f


@pytest.mark.parametrize("rgb", [(255, 255, 0), (255, 255, 255), (0, 255, 128)])   # < 100K, K, M
def test_a_count_in_any_of_the_bank_colours_shows(rgb):
    assert vision.stack_number_shown(_slot_top(rgb)) is True


def test_no_number_is_the_last_1():
    assert vision.stack_number_shown(_slot_top()) is False
    assert vision.stack_number_shown(canvas(26, 10, BANK_BG)) is False


def test_a_few_stray_pixels_are_not_a_number():
    f = paint(_slot_top(), 3, 3, 1, 2, (255, 255, 0))          # 2 px of yellow in the icon
    assert vision.stack_number_shown(f) is False


# ── tanner: the bank's restock decision ───────────────────────────────────────

from tests.test_stamina_reopen import tanner, _withdrew   # noqa: E402,F401  (fixture)


@pytest.fixture
def bank(tanner, monkeypatch):
    actions, energy, calls = tanner
    monkeypatch.setattr(actions, "bank_is_open", lambda timeout=5.0: True)
    monkeypatch.setattr(energy, "restock_stamina_at_bank", lambda **k: False)
    return actions, calls


def test_hides_left_restocks_only_without_a_number(bank, monkeypatch):
    actions, calls = bank
    monkeypatch.setattr(actions, "hide_count_shown", lambda: True)
    assert actions.do_bank() is True and _withdrew(actions, calls)

    calls.clear()
    monkeypatch.setattr(actions, "hide_count_shown", lambda: False)     # the last 1
    assert actions.do_bank() == "restock"
    assert not _withdrew(actions, calls) and ("press", "escape") in calls


def test_skip_flag_never_reads_the_count(bank, monkeypatch):
    actions, calls = bank
    monkeypatch.setattr(actions, "hide_count_shown", lambda: pytest.fail("read the count"))
    assert actions.do_bank(skip_restock_check=True) is True


def test_uncalibrated_region_never_restocks(bank, monkeypatch):
    actions, calls = bank
    monkeypatch.setattr(actions, "hide_count_shown", lambda: None)
    assert actions.do_bank() is True and _withdrew(actions, calls)


def test_hide_count_shown_reads_the_region(fake_screen, with_example_config, monkeypatch):
    actions = with_example_config("tanner", "actions")
    assert actions.hide_count_shown() is None                            # zero-size: not calibrated
    monkeypatch.setattr(actions, "HIDE_COUNT_REGION", (100, 50, 26, 10))
    screen = canvas(300, 200, BANK_BG)
    screen[50:60, 100:126] = _slot_top((255, 255, 0))
    fake_screen.show(screen)
    assert actions.hide_count_shown() is True
    fake_screen.show(canvas(300, 200, BANK_BG))
    assert actions.hide_count_shown() is False


@pytest.mark.parametrize("from_ge", [False, True])
def test_tanner_wont_start_without_the_hide_count_region(with_example_config, monkeypatch, capsys, from_ge):
    # without it the bot can't see it's out of hides: all-but-1 withdraws nothing and it
    # walks to Ellis empty-handed, then spends glory charges recovering
    with_example_config("lib", "energy", config="energy_config")
    with_example_config("lib", "ge", config="ge_config")
    run = with_example_config("tanner", "run")
    monkeypatch.setattr(run, "run_session", lambda *a, **k: pytest.fail("session started"))
    run.run({}, start_from_ge=from_ge)
    assert "Hide Count Region" in capsys.readouterr().out


def test_tanner_starts_once_it_is_calibrated(with_example_config, monkeypatch):
    with_example_config("lib", "energy", config="energy_config")
    with_example_config("lib", "ge", config="ge_config")
    run = with_example_config("tanner", "run")
    monkeypatch.setattr(run.actions, "HIDE_COUNT_REGION", (100, 50, 26, 10))
    started = []
    monkeypatch.setattr(run, "run_session", lambda *a, **k: started.append(k["bot"]))
    run.run({})
    assert started == ["tanner"]
