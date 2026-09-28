import pytest

import lib.pause as pause
import lib.mouse as mouse


@pytest.fixture(autouse=True)
def clean_pause_state(monkeypatch):
    pause.reset()
    monkeypatch.setattr(pause, "_suppress_until", 0.0)
    yield
    pause.reset()


def test_o_toggles_pause():
    pause._handle_char("o")
    assert pause.is_paused()
    pause._handle_char("O")
    assert not pause.is_paused()


def test_p_force_stops():
    pause._handle_char("p")
    with pytest.raises(pause.ForceStop):
        pause.wait()


def test_suppressed_hotkeys_are_ignored():
    pause.suppress_hotkeys(5)
    pause._handle_char("o")
    pause._handle_char("p")
    assert not pause.is_paused()
    pause.wait()   # no ForceStop


def test_bot_typing_does_not_trigger_hotkeys(monkeypatch):
    # The key listener sees the bot's own synthetic keystrokes; simulate that.
    monkeypatch.setattr(mouse.pyautogui, "typewrite", lambda ch, interval=0: pause._handle_char(ch))
    monkeypatch.setattr(mouse.pyautogui, "press", lambda key: None)
    monkeypatch.setattr(mouse.time, "sleep", lambda s: None)
    mouse.human_typewrite("blue dragonhide")   # contains an 'o'
    assert not pause.is_paused()
    mouse.human_typewrite("pop")               # 'p' would force-stop
    pause.wait()


def test_wait_returns_false_when_not_paused():
    assert pause.wait() is False


def test_wait_returns_true_after_blocking():
    import threading
    pause.toggle()
    threading.Timer(0.3, pause.toggle).start()
    assert pause.wait() is True


def test_hint_default_keys(monkeypatch):
    monkeypatch.setattr(pause, "_pause_hotkey", "o")
    monkeypatch.setattr(pause, "_stop_hotkey", "p")
    monkeypatch.setattr(pause, "_stop_key", None)
    assert pause.hint() == "Press O to pause, P to force-stop."


def test_hint_special_stop_key(monkeypatch):
    monkeypatch.setattr(pause, "_pause_hotkey", "p")
    monkeypatch.setattr(pause, "_stop_hotkey", None)
    monkeypatch.setattr(pause, "_stop_key", "end")
    assert pause.hint() == "Press P to pause, End to force-stop."
