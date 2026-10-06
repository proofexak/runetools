"""Manual mode's main process (PRO-90): starts RuneLite + the bot menu when the web
app asks through data/manual_request.json, reports in data/manual_status.json."""
import json
import threading

import pytest

import lib.manual as manual

RUNELITE = ["/opt/jre/bin/java", "-Xmx512m", "-cp", "/home/runetools/.runelite/repository2/client-1.13.1.jar",
            "net.runelite.client.RuneLite"]
MENU = ["python3", "run.py"]


def test_detects_runelite_and_the_menu_from_argv():
    assert manual.is_runelite(RUNELITE) and not manual.is_runelite(MENU)
    assert manual.is_menu(MENU) and manual.is_menu(["/opt/venv/bin/python", "/app/run.py"])
    assert not manual.is_menu(["python3", "-m", "lib.manual"])
    assert not manual.is_menu(["python3", "-m", "pytest", "tests/test_run.py"])
    assert not manual.is_runelite(["sh", "-c", "echo runelite"])
    assert manual.running([RUNELITE, ["sleep", "infinity"]]) == (True, False)
    assert manual.running([]) == (False, False)


@pytest.mark.parametrize("runelite,menu,launches", [
    (False, False, ["runelite", "menu"]),
    (True, False, ["menu"]),
    (False, True, ["runelite"]),
    (True, True, []),
])
def test_plan_starts_only_what_is_missing(runelite, menu, launches):
    assert manual.plan(runelite, menu) == launches


def test_read_request(tmp_path):
    p = tmp_path / "r.json"
    assert manual.read_request(str(p)) == (None, None)
    p.write_text("{not json")
    assert manual.read_request(str(p)) == (None, None)
    p.write_text(json.dumps({"id": "abc", "action": "start"}))
    assert manual.read_request(str(p)) == ("abc", "start")


class _World:
    """Fake processes: launching adds the process; RuneLite's window shows after a while."""
    def __init__(self, runelite=False, menu=False, window_after=0):
        self.procs = ([RUNELITE] if runelite else []) + ([MENU] if menu else [])
        self.launched, self.window_checks, self.window_after = [], 0, window_after
        self.now = 0.0

    def launch(self, what):
        self.launched.append(what)
        self.procs.append(RUNELITE if what == "runelite" else MENU)

    def window_up(self):
        self.window_checks += 1
        return self.window_checks > self.window_after

    def sleep(self, s):
        self.now += s


def _manual(tmp_path, world):
    return manual.Manual(root=str(tmp_path), launch=world.launch, scan=lambda: list(world.procs),
                         window_up=world.window_up, clock=lambda: world.now, sleep=world.sleep)


def _request(tmp_path, rid, action="start"):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "manual_request.json").write_text(json.dumps({"id": rid, "action": action}))


def _status(tmp_path):
    return json.loads((tmp_path / "data" / "manual_status.json").read_text())


def _settle():
    for t in threading.enumerate():
        if t.name == "manual-start":
            t.join(5)


def test_start_launches_runelite_waits_for_its_window_then_the_menu(tmp_path):
    world = _World(window_after=3)
    m = _manual(tmp_path, world)
    _request(tmp_path, "r1")
    m.poll_once(None)
    _settle()
    assert world.launched == ["runelite", "menu"] and world.window_checks == 4
    m.poll_once("r1")
    s = _status(tmp_path)
    assert s["runelite"] and s["menu"] and s["phase"] == "idle" and s["handled"] == "r1" and s["error"] is None
    assert s["pid"] > 0 and s["ts"] > 0


def test_start_twice_never_gives_two_of_either(tmp_path):
    world = _World(runelite=True, menu=True)
    m = _manual(tmp_path, world)
    _request(tmp_path, "r1")
    seen = m.poll_once(None)
    _settle()
    m.poll_once(seen)                         # the same request again: nothing
    _request(tmp_path, "r2")                  # a new one with both running: nothing either
    m.poll_once(seen)
    _settle()
    assert world.launched == []
    assert _status(tmp_path)["handled"] in ("r1", "r2")


def test_menu_only_when_runelite_already_runs(tmp_path):
    world = _World(runelite=True)
    m = _manual(tmp_path, world)
    _request(tmp_path, "r1")
    m.poll_once(None)
    _settle()
    assert world.launched == ["menu"] and world.window_checks == 0


def test_runelite_window_that_never_appears_is_an_error_and_no_menu(tmp_path):
    world = _World(window_after=10_000)
    m = _manual(tmp_path, world)
    _request(tmp_path, "r1")
    m.poll_once(None)
    _settle()
    m.poll_once("r1")
    s = _status(tmp_path)
    assert world.launched == ["runelite"]
    assert s["handled"] == "r1" and "didn't appear" in s["error"]


def test_status_is_written_even_without_a_request(tmp_path):
    m = _manual(tmp_path, _World(runelite=True))
    assert m.poll_once(None) is None
    s = _status(tmp_path)
    assert s["runelite"] is True and s["menu"] is False and s["phase"] == "idle"


def test_unknown_action_is_acknowledged_and_ignored(tmp_path):
    world = _World()
    m = _manual(tmp_path, world)
    _request(tmp_path, "r9", action="explode")
    assert m.poll_once(None) == "r9"
    _settle()
    assert world.launched == [] and _status(tmp_path)["handled"] == "r9"


def test_waits_for_the_client_window_not_the_launcher():
    launcher = '     0x400007 "RuneLite Launcher": ("RuneLite Launcher" "RuneLite Launcher")  600x400+500+250  +500+250'
    client = '     0x600007 "RuneLite": ("RuneLite" "RuneLite")  1200x800+200+50  +200+50'
    logged_in = '     0x600007 "RuneLite - Zezima": ("RuneLite" "RuneLite")  1200x800+200+50  +200+50'
    assert not manual.client_window_in(launcher)
    assert manual.client_window_in(client) and manual.client_window_in(logged_in)


def test_proc_cmdlines_reads_argv_and_skips_vanished_processes(tmp_path):
    (tmp_path / "7").mkdir()
    (tmp_path / "7" / "cmdline").write_bytes(b"python3\0run.py\0")
    (tmp_path / "8").mkdir()                   # exited between listdir and open: no cmdline
    (tmp_path / "9").mkdir()
    (tmp_path / "9" / "cmdline").write_bytes(b"")   # kernel thread: empty
    (tmp_path / "self").mkdir()
    assert manual.proc_cmdlines(str(tmp_path)) == [["python3", "run.py"]]
