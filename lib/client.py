"""
Keep RuneLite running and logged in (unattended mode, lib/headless.py).

Screens are recognised with image templates (lib/client_templates/*.png,
captured once with the menu's "⚙ Client Templates"): terms_accept (optional,
first run only), login_play, welcome_play, in_game. Logging in relies on
RuneLite's saved Jagex credentials (~/.runelite/credentials.properties, written
by --insecure-write-credentials — see docker/README.md).

Everything that touches the outside world goes through an Env, so the
handlers are tested with synthetic screens and a fake clock.
"""
import os, subprocess, time

import numpy as np

import lib.vision as vision
from lib.client_states import build_machine, FINAL_STATES
from lib.state_machine import run_machine

ROOT         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(ROOT, "lib", "client_templates")
REQUIRED     = ("login_play", "welcome_play", "in_game")
OPTIONAL     = ("terms_accept",)

LAUNCH_TIMEOUT   = 180   # s from launch to the login screen (first start downloads the client)
LOGIN_TIMEOUT    = 60    # s for the login screen after accepting the terms
WELCOME_TIMEOUT  = 90    # s from clicking Play to the welcome screen
IN_GAME_TIMEOUT  = 45    # s from "Click here to play" to the game view
POLL             = 2     # s between screen checks
MATCH_DIFF       = 12.0  # vision.find_template max_diff


# ── Outside world ─────────────────────────────────────────────────────────────

def load_templates(directory=TEMPLATE_DIR):
    """{name: BGR template} for every <name>.png in directory."""
    from PIL import Image
    out = {}
    if os.path.isdir(directory):
        for fname in os.listdir(directory):
            if fname.endswith(".png"):
                rgb = np.array(Image.open(os.path.join(directory, fname)).convert("RGB"))
                out[fname[:-4]] = rgb[:, :, ::-1].copy()
    return out


def missing_templates(templates):
    return [name for name in REQUIRED if name not in templates]


def credentials_saved(home=None):
    home = home or os.path.expanduser("~")
    return os.path.isfile(os.path.join(home, ".runelite", "credentials.properties"))


def running():
    return subprocess.run(["pgrep", "-f", "net.runelite"], stdout=subprocess.DEVNULL).returncode == 0


def start():
    log = open("/tmp/runelite.log", "ab")
    subprocess.Popen(["runelite"], stdout=log, stderr=log, start_new_session=True)


def kill():
    subprocess.run(["pkill", "-f", "net.runelite"], stdout=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "RuneLite.jar"], stdout=subprocess.DEVNULL)


def grab_screen():
    """(frame, offset) of the whole display."""
    import mss
    from lib.screen import grab
    with mss.mss() as sct:
        mon = sct.monitors[1]
    return grab((0, 0, mon["width"], mon["height"]))


def gated_sleep(seconds, step=0.25):
    """Sleep in small steps through the pause gate, so a force stop (P,
    botctl kill, docker stop) interrupts a long wait for a screen."""
    import lib.pause as pause
    end = time.time() + seconds
    while True:
        pause.wait()
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(step, left))


def _human_click(x, y):
    from lib.mouse import human_click
    human_click(x, y)


def _set_camera(x, y):
    from lib.camera import zoom_out_top_down
    zoom_out_top_down(x, y)


class Env:
    def __init__(self, templates=None, grab=grab_screen, click=_human_click, clock=time.time,
                 wait=gated_sleep, running=running, start=start, camera=_set_camera):
        self.templates = load_templates() if templates is None else templates
        self.grab, self.click, self.clock, self.wait = grab, click, clock, wait
        self.camera = camera
        self.running, self.start = running, start


def find(templates, name, frame):
    tpl = templates.get(name)
    return None if tpl is None else vision.find_template(frame, tpl, max_diff=MATCH_DIFF)


def logged_in(templates, frame):
    return find(templates, "in_game", frame) is not None


# ── Handlers ──────────────────────────────────────────────────────────────────

def handlers(session, env):
    def wait_for(wanted, reason):
        """Poll until one of wanted [(event, template)] is on screen or the deadline passes."""
        while env.clock() < session.deadline:
            frame, (ox, oy) = env.grab()
            for event, name in wanted:
                pt = find(env.templates, name, frame)
                if pt is not None:
                    session.target = (pt[0] + ox, pt[1] + oy)
                    return event
            env.wait(POLL)
        session.reason = reason
        return "timeout"

    def click_then(timeout):
        env.click(*session.target)
        session.deadline = env.clock() + timeout
        return "ok"

    def click_welcome():
        session.view = session.target
        return click_then(IN_GAME_TIMEOUT)

    def set_camera():
        env.camera(*session.view)
        return "ok"

    def launch():
        frame, _ = env.grab()
        if logged_in(env.templates, frame):
            return "in_game"
        if not env.running():
            env.start()
        session.deadline = env.clock() + LAUNCH_TIMEOUT
        return "ok"

    return {
        "launch":        launch,
        "wait_login":    lambda: wait_for([("in_game", "in_game"), ("ok", "login_play"),
                                           ("terms", "terms_accept")], "login screen never appeared"),
        "accept_terms":  lambda: click_then(LOGIN_TIMEOUT),
        "click_play":    lambda: click_then(WELCOME_TIMEOUT),
        "wait_welcome":  lambda: wait_for([("in_game", "in_game"), ("ok", "welcome_play")],
                                          "welcome screen never appeared"),
        "click_welcome": click_welcome,
        "wait_in_game":  lambda: wait_for([("ok", "in_game")], "game view never appeared"),
        "set_camera":    set_camera,
    }


def ensure_logged_in(env=None):
    """Bring RuneLite to the in-game view. Returns (ok, reason-if-not)."""
    env = env or Env()
    missing = missing_templates(env.templates)
    if missing:
        return False, f"missing client templates: {', '.join(missing)}"
    session = build_machine({})
    final = run_machine(session, handlers(session, env), session.stats, FINAL_STATES)
    return (True, None) if final == "in_game" else (False, session.reason)
