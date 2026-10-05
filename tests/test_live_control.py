import json, os, threading, time

import pytest

import lib.live_control as live_control
import lib.pause as pause


@pytest.fixture(autouse=True)
def clean_pause(monkeypatch):
    monkeypatch.setattr(pause, "_held", False)
    monkeypatch.setattr(pause, "_sessions", 0)
    monkeypatch.setattr(pause, "_suppress_until", 0.0)
    pause.reset()
    yield
    pause.unhold()
    pause.reset()


@pytest.fixture
def watcher(tmp_path):
    return live_control.Watcher(root=tmp_path)


def request(w, rid, held):
    live_control.write_json(w.request, {"id": rid, "held": held})


def ack(w):
    with open(w.ack, encoding="utf-8") as f:
        return json.load(f)


# ── pause: hold / unhold ───────────────────────────────────────────────────────

def test_hold_pauses_and_ignores_hotkeys():
    pause.hold()
    assert pause.is_paused() and pause.is_held()
    pause._handle_char("o")            # the human typing into the game
    pause._handle_char("p")
    assert pause.is_paused()
    assert pause._force_stop is False


def test_unhold_restores_the_previous_pause_state():
    pause.hold()
    pause.unhold()
    assert not pause.is_paused()
    pause.set_paused(True)             # paused by O / botctl before the take-over
    pause.hold()
    pause.unhold()
    assert pause.is_paused()


def test_nothing_resumes_a_held_bot():
    pause.hold()
    pause.toggle()                     # overlay button
    pause.set_paused(False)            # botctl resume
    pause.reset()                      # a new session starting
    assert pause.is_paused()
    pause.unhold()
    assert not pause.is_paused()


def test_idle_without_a_session_and_while_blocked_on_the_pause():
    assert pause.idle()
    with pause.session():
        assert not pause.idle()        # a step may be running
        pause.hold()
        t = threading.Thread(target=pause.wait)
        t.start()
        deadline = time.time() + 2
        while not pause.idle() and time.time() < deadline:
            time.sleep(0.01)
        assert pause.idle()            # the bot is parked in wait()
        pause.unhold()
        t.join(2)
        assert not pause.idle()
    assert pause.idle()


# ── watcher ────────────────────────────────────────────────────────────────────

def test_no_request_does_nothing(watcher):
    watcher.poll_once()
    assert not pause.is_paused()
    assert not os.path.exists(watcher.ack)


def test_take_and_release(watcher):
    request(watcher, "a1", True)
    watcher.poll_once()
    assert pause.is_held()
    assert ack(watcher) == {"id": "a1", "held": True, "safe": True, "pid": os.getpid()}
    request(watcher, "a2", False)
    watcher.poll_once()
    assert not pause.is_held() and not pause.is_paused()
    assert ack(watcher)["id"] == "a2" and ack(watcher)["held"] is False


def test_safe_follows_the_bot_reaching_the_pause(watcher, monkeypatch):
    request(watcher, "a1", True)
    with pause.session():
        watcher.poll_once()
        assert ack(watcher)["safe"] is False      # mid-step: not yet
        monkeypatch.setattr(pause, "_waiting", True)
        watcher.poll_once()
        assert ack(watcher)["safe"] is True


def test_unchanged_state_is_not_rewritten(watcher, monkeypatch):
    request(watcher, "a1", True)
    watcher.poll_once()
    writes = []
    monkeypatch.setattr(live_control, "write_json", lambda *a: writes.append(a) or True)
    watcher.poll_once()
    assert writes == []


def test_unreadable_request_means_released(watcher):
    request(watcher, "a1", True)
    watcher.poll_once()
    with open(watcher.request, "w", encoding="utf-8") as f:
        f.write("{half a wri")
    watcher.poll_once()
    assert not pause.is_held()
