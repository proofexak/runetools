"""lib/client.py handlers against synthetic screens (no RuneLite, no mouse)."""
import numpy as np
import pytest

import lib.pause as pause
import lib.client as client
from tests.fakescreen import canvas

REAL_PAUSE_WAIT = pause.wait      # captured before the autouse fixture stubs it out


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(pause, "wait", lambda: False)


def _tpl(seed):
    return np.random.RandomState(seed).randint(30, 230, size=(20, 40, 3)).astype(np.uint8)


TEMPLATES = {"terms_accept": _tpl(1), "login_play": _tpl(2), "welcome_play": _tpl(3), "in_game": _tpl(4)}
SPOT = {"terms_accept": (100, 100), "login_play": (300, 200), "welcome_play": (500, 300), "in_game": (50, 350)}


def screen(*names):
    f = canvas(640, 400)
    for n in names:
        x, y = SPOT[n]
        f[y:y + 20, x:x + 40] = TEMPLATES[n]
    return f


def centre(name):
    x, y = SPOT[name]
    return (x + 20, y + 10)


class Env(client.Env):
    """Scripted environment: screens change after clicks, time is fake."""
    def __init__(self, screens_after_clicks, running=False, templates=TEMPLATES):
        self.t = 0.0
        self.clicks, self.started, self.cameras = [], 0, []
        self._screens = list(screens_after_clicks)
        self._running = running
        super().__init__(templates=templates, grab=self._grab, click=self._click,
                         clock=lambda: self.t, wait=self._wait,
                         running=lambda: self._running, start=self._start,
                         camera=lambda x, y: self.cameras.append((x, y)))

    def _grab(self):
        return self._screens[0], (0, 0)

    def _click(self, x, y):
        self.clicks.append((x, y))
        if len(self._screens) > 1:
            self._screens.pop(0)

    def _wait(self, s):
        self.t += s

    def _start(self):
        self.started += 1
        self._running = True


def test_full_login_clicks_play_then_welcome():
    env = Env([screen("login_play"), screen("welcome_play"), screen("in_game")])
    assert client.ensure_logged_in(env) == (True, None)
    assert env.started == 1
    assert env.clicks == [centre("login_play"), centre("welcome_play")]


def test_camera_is_set_after_login_over_the_welcome_button():
    env = Env([screen("login_play"), screen("welcome_play"), screen("in_game")])
    client.ensure_logged_in(env)
    assert env.cameras == [centre("welcome_play")]


def test_terms_screen_is_accepted_first():
    env = Env([screen("terms_accept"), screen("login_play"), screen("welcome_play"), screen("in_game")])
    assert client.ensure_logged_in(env)[0] is True
    assert env.clicks[0] == centre("terms_accept")


def test_already_in_game_does_nothing():
    env = Env([screen("in_game")], running=True)
    assert client.ensure_logged_in(env) == (True, None)
    assert env.clicks == [] and env.started == 0 and env.cameras == []


def test_does_not_start_a_second_client():
    env = Env([screen("login_play"), screen("welcome_play"), screen("in_game")], running=True)
    client.ensure_logged_in(env)
    assert env.started == 0


def test_login_screen_never_appears_times_out(monkeypatch):
    monkeypatch.setattr(client, "LAUNCH_TIMEOUT", 10)
    monkeypatch.setattr(client, "WELCOME_TIMEOUT", 10)
    env = Env([canvas(640, 400)])
    ok, reason = client.ensure_logged_in(env)
    assert ok is False and "login screen" in reason
    assert env.t >= client.LAUNCH_TIMEOUT


def test_stuck_on_welcome_times_out(monkeypatch):
    monkeypatch.setattr(client, "LAUNCH_TIMEOUT", 10)
    monkeypatch.setattr(client, "WELCOME_TIMEOUT", 10)
    env = Env([screen("login_play"), canvas(640, 400)])
    ok, reason = client.ensure_logged_in(env)
    assert ok is False and "welcome" in reason


def test_missing_required_template_fails_without_touching_anything():
    env = Env([screen("login_play")], templates={k: v for k, v in TEMPLATES.items() if k != "in_game"})
    ok, reason = client.ensure_logged_in(env)
    assert ok is False and "in_game" in reason
    assert env.started == 0 and env.clicks == []


def test_optional_terms_template_may_be_missing():
    env = Env([screen("login_play"), screen("welcome_play"), screen("in_game")],
              templates={k: v for k, v in TEMPLATES.items() if k != "terms_accept"})
    assert client.ensure_logged_in(env)[0] is True


def test_logged_in_and_missing_templates_helpers():
    assert client.logged_in(TEMPLATES, screen("in_game")) is True
    assert client.logged_in(TEMPLATES, screen("login_play")) is False
    assert client.missing_templates({"in_game": TEMPLATES["in_game"]}) == ["login_play", "welcome_play"]


def test_load_templates_reads_pngs_as_bgr(tmp_path):
    from PIL import Image
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    rgb[:, :, 0] = 200                         # red in RGB
    Image.fromarray(rgb).save(tmp_path / "in_game.png")
    loaded = client.load_templates(str(tmp_path))
    assert set(loaded) == {"in_game"} and loaded["in_game"][0, 0].tolist() == [0, 0, 200]


def test_credentials_saved(tmp_path):
    assert client.credentials_saved(str(tmp_path)) is False
    (tmp_path / ".runelite").mkdir()
    (tmp_path / ".runelite" / "credentials.properties").write_text("JX_SESSION_ID=x\n")
    assert client.credentials_saved(str(tmp_path)) is True


def test_default_wait_honours_a_force_stop(monkeypatch):
    monkeypatch.setattr(pause, "wait", REAL_PAUSE_WAIT)
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    pause.force_stop()
    try:
        with pytest.raises(pause.ForceStop):
            client.gated_sleep(5)
    finally:
        pause.reset()
