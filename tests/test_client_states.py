import pytest

import lib.pause as pause
from lib.state_machine import run_machine
from lib.client_states import build_machine, FINAL_STATES

ALL = ["launch", "wait_login", "accept_terms", "click_play", "wait_welcome",
       "click_welcome", "wait_in_game", "set_camera"]


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(pause, "wait", lambda: False)


def drive(script):
    s = build_machine({})
    visited = []

    def make(state):
        def handler():
            visited.append(state)
            return script.pop(0)
        return handler
    final = run_machine(s, {st: make(st) for st in ALL}, s.stats, FINAL_STATES)
    return final, visited


def test_normal_login():
    final, visited = drive(["ok", "ok", "ok", "ok", "ok", "ok", "ok"])
    assert final == "in_game"
    assert visited == ["launch", "wait_login", "click_play", "wait_welcome", "click_welcome",
                       "wait_in_game", "set_camera"]


def test_terms_screen_first():
    final, visited = drive(["ok", "terms", "ok", "ok", "ok", "ok", "ok", "ok", "ok"])
    assert visited[:4] == ["launch", "wait_login", "accept_terms", "wait_login"] and final == "in_game"


def test_already_in_game():
    assert drive(["in_game"]) == ("in_game", ["launch"])
    assert drive(["ok", "in_game"])[0] == "in_game"
    assert drive(["ok", "ok", "ok", "in_game"])[0] == "in_game"


@pytest.mark.parametrize("prefix", [["ok"], ["ok", "ok", "ok"], ["ok", "ok", "ok", "ok", "ok"]])
def test_any_wait_timeout_fails(prefix):
    final, visited = drive(prefix + ["timeout"])
    assert final == "failed"


def test_starts_at_launch():
    assert build_machine({}).state == "launch"
