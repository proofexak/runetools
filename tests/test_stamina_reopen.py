"""After the stamina potion the bank must really reopen before anything is
clicked on it — otherwise the potion stays in the inventory, the deposit /
withdraw clicks land on the game world and the bot walks off from a wrong spot."""
import pytest


@pytest.fixture
def energy(with_example_config, monkeypatch):
    energy = with_example_config("lib", "energy", config="energy_config")
    clicks = []
    monkeypatch.setattr(energy, "read_energy", lambda: 10)            # needs a drink
    monkeypatch.setattr(energy, "human_click", lambda x, y: clicks.append((x, y)))
    monkeypatch.setattr(energy, "drink_stamina", lambda: clicks.append("drink"))
    monkeypatch.setattr(energy, "pixel_matches", lambda *a, **k: True)
    monkeypatch.setattr(energy.pyautogui, "press", lambda key: None)
    monkeypatch.setattr(energy.time, "sleep", lambda s: None)
    monkeypatch.setattr(energy, "find_color", lambda *a, **k: ((900, 500), 50))
    return energy, clicks


def test_reopened_bank_gets_the_deposit(energy):
    energy, clicks = energy
    assert energy.restock_stamina_at_bank(bank_open=lambda: True) is True
    booth = clicks.index((900, 500))
    assert clicks[booth - 1] == "drink"                              # drink, booth once,
    assert len(clicks) == booth + 2                                  # then the deposit click


def test_second_booth_click_when_the_first_does_not_open_it(energy):
    energy, clicks = energy
    opened = iter([False, True])
    assert energy.restock_stamina_at_bank(bank_open=lambda: next(opened)) is True
    assert clicks.count((900, 500)) == 2


def test_bank_that_never_reopens_is_reported_and_nothing_is_deposited(energy, capsys):
    energy, clicks = energy
    assert energy.restock_stamina_at_bank(bank_open=lambda: False) == energy.BANK_CLOSED
    assert clicks[-1] == (900, 500) and clicks.count((900, 500)) == 2   # no deposit click after
    assert "didn't reopen" in capsys.readouterr().out


def test_booth_gone_after_the_drink_is_bank_closed(energy, monkeypatch):
    energy, clicks = energy
    monkeypatch.setattr(energy, "find_color", lambda *a, **k: (None, 0))
    assert energy.restock_stamina_at_bank(bank_open=lambda: True) == energy.BANK_CLOSED


def test_without_bank_open_the_old_behaviour_stays(energy):
    energy, clicks = energy
    assert energy.restock_stamina_at_bank() is True                  # blind deposit, as before


# ── tanner do_bank ────────────────────────────────────────────────────────────

@pytest.fixture
def tanner(with_example_config, monkeypatch):
    energy = with_example_config("lib", "energy", config="energy_config")
    actions = with_example_config("tanner", "actions")
    calls = []
    monkeypatch.setattr(actions, "energy", energy)
    monkeypatch.setattr(actions, "human_click", lambda x, y: calls.append(("click", x, y)))
    monkeypatch.setattr(actions, "human_move", lambda x, y: None)
    monkeypatch.setattr(actions.pyautogui, "press", lambda key: calls.append(("press", key)))
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions, "pixel_matches", lambda *a, **k: False)   # bank slot 2 not empty
    # the example config is all zeros: tell the buttons apart
    monkeypatch.setattr(actions, "BANK_SLOT_1", (690, 295))
    monkeypatch.setattr(actions, "DEPOSIT_BTN", (1043, 675))
    monkeypatch.setattr(actions, "HIDE_TAB", (720, 253))
    return actions, energy, calls


def _withdrew(actions, calls):
    sx, sy = actions.BANK_SLOT_1
    return any(c[0] == "click" and abs(c[1] - sx) <= 10 and abs(c[2] - sy) <= 10 for c in calls)


def test_do_bank_fails_when_the_bank_does_not_reopen_after_the_potion(tanner, monkeypatch):
    actions, energy, calls = tanner
    monkeypatch.setattr(actions, "bank_is_open", lambda timeout=5.0: True)
    monkeypatch.setattr(energy, "restock_stamina_at_bank", lambda **k: energy.BANK_CLOSED)
    assert actions.do_bank(skip_restock_check=True) is False
    assert not _withdrew(actions, calls)


def test_do_bank_never_withdraws_on_a_closed_bank(tanner, monkeypatch):
    actions, energy, calls = tanner
    states = iter([True, False])              # open on arrival, closed by the time it withdraws
    monkeypatch.setattr(actions, "bank_is_open", lambda timeout=5.0: next(states))
    monkeypatch.setattr(energy, "restock_stamina_at_bank", lambda **k: False)
    assert actions.do_bank() is False
    assert not _withdrew(actions, calls)


def test_do_bank_normal_still_withdraws(tanner, monkeypatch):
    actions, energy, calls = tanner
    seen = {}
    monkeypatch.setattr(actions, "bank_is_open", lambda timeout=5.0: True)
    monkeypatch.setattr(energy, "restock_stamina_at_bank", lambda **k: seen.update(k) or True)
    assert actions.do_bank(skip_restock_check=True) is True
    assert _withdrew(actions, calls)
    assert seen["bank_open"] is actions.bank_is_open


def _near(c, point, tol=10):
    return c[0] == "click" and abs(c[1] - point[0]) <= tol and abs(c[2] - point[1]) <= tol


@pytest.mark.parametrize("stamina", [False, True])
def test_every_bank_switches_to_the_hide_tab_before_reading_or_withdrawing(tanner, monkeypatch, stamina):
    # the bank reopens on whatever tab it was left on — the potion tab after a stamina
    # trip that failed — so the hide tab is clicked on every visit, not only after a top-up
    actions, energy, calls = tanner
    reads = []
    monkeypatch.setattr(actions, "bank_is_open", lambda timeout=5.0: True)
    monkeypatch.setattr(energy, "restock_stamina_at_bank", lambda **k: stamina)
    monkeypatch.setattr(actions, "pixel_matches", lambda *a, **k: reads.append(len(calls)) or False)
    assert actions.do_bank() is True                         # a session's first bank
    del calls[:], reads[:]
    monkeypatch.setattr(energy, "restock_stamina_at_bank", lambda **k: False)
    assert actions.do_bank() is True                         # a later one: no top-up this time
    tab = next(i for i, c in enumerate(calls) if _near(c, actions.HIDE_TAB))
    withdraw = next(i for i, c in enumerate(calls) if _near(c, actions.BANK_SLOT_1))
    assert tab < withdraw
    assert reads and all(r > tab for r in reads)             # slot-2 check reads the hide tab
