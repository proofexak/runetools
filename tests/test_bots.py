import os
import subprocess
import sys

from lib.bots import Bot, Launch, discover, build_menu

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pkg(root, name, body):
    d = root / name
    d.mkdir()
    (d / "__init__.py").write_text("")
    (d / "bot.py").write_text(body)


def test_discover_sorts_by_order_and_skips_broken(tmp_path, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(tmp_path))
    _pkg(tmp_path, "zz_bot_a", "from lib.bots import Bot\nBOT = Bot('A', [], order=2)\n")
    _pkg(tmp_path, "zz_bot_b", "from lib.bots import Bot\nBOT = Bot('B', [], order=1)\n")
    _pkg(tmp_path, "zz_bot_c", "raise RuntimeError('boom')\n")
    (tmp_path / "not_a_bot").mkdir()
    script = tmp_path / "zz_script_dir"          # e.g. woodcutter/: bot.py is a script, not a package
    script.mkdir()
    (script / "bot.py").write_text("raise SystemExit('must never be imported')\n")
    assert [b.name for b in discover(str(tmp_path))] == ["B", "A"]
    assert "zz_bot_c" in capsys.readouterr().out


def test_discover_repo_finds_the_bots():
    assert [b.name for b in discover(REPO)] == ["Tanning", "Mining", "Choco Grind"]


def test_descriptors_import_lazily():
    # Discovery must work on a fresh clone: no calibrated config, no screen libs.
    code = ("import sys, lib.bots as b; b.discover('.'); "
            "print(sorted(m for m in ['tanner.config', 'miner.golden_nuggets.config', "
            "'choc.config', 'pyautogui', 'mss'] if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
    assert out.stdout.strip() == "[]", out.stderr


def _bots():
    plain = Launch("Go", start=lambda stats: None, colors=("#1", "#2"))
    with_alt = Launch("Hide", start=lambda stats: None, colors=("#3", "#4"),
                      alt=("GE", lambda stats: None))
    asking = Launch("Run", start=lambda stats, n: None, ask_int="How many?")
    return [Bot("One", [plain, with_alt], configure=lambda: None, colors=("#a", "#b")),
            Bot("Two", [asking])]


def test_build_menu_shape():
    tool = lambda: None
    menu = build_menu(_bots(), begin=lambda b, f: None, ask_int=lambda p, cb: None,
                      tools=[("⚙ GE Config", tool)])
    assert [m[0] for m in menu] == ["One", "Two", "⚙ GE Config", "Exit"]
    one = menu[0]
    assert one[2:] == ("#a", "#b")
    labels = [item[0] for item in one[1]]
    assert labels == ["Go", "Hide", "⚙ Configure"]
    assert len(one[1][0]) == 4                      # no side button
    assert one[1][1][4][0] == "GE"                  # alt side button
    assert [item[0] for item in menu[1][1]] == ["Run"]   # no configure -> no button
    assert menu[2][1] is tool


def test_launch_click_calls_begin_with_bot_and_start():
    bots = _bots()
    begun = []
    menu = build_menu(bots, begin=lambda b, f: begun.append((b, f)), ask_int=None, tools=[])
    menu[0][1][0][1]()           # click "Go"
    assert begun == [(bots[0], bots[0].launches[0].start)]
    menu[0][1][1][4][1]()        # click the "GE" side button
    assert begun[-1] == (bots[0], bots[0].launches[1].alt[1])


def test_ask_int_launch_prompts_then_begins_with_value():
    got = []
    bots = [Bot("Two", [Launch("Run", start=lambda stats, n: got.append((stats, n)),
                               ask_int="How many?")])]
    prompts, begun = [], []
    menu = build_menu(bots, begin=lambda b, f: begun.append(f),
                      ask_int=lambda p, cb: prompts.append((p, cb)), tools=[])
    menu[0][1][0][1]()           # click "Run"
    assert prompts[0][0] == "How many?" and not begun
    prompts[0][1](7)             # user enters 7
    begun[0]({"run": 0})
    assert got == [({"run": 0}, 7)]


def test_discover_skips_descriptor_that_is_not_a_bot(tmp_path, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(tmp_path))
    _pkg(tmp_path, "zz_bot_d", "from lib.bots import Bot\nBOT = Bot('D', [])\n")
    _pkg(tmp_path, "zz_bot_e", "BOT = None\n")
    assert [b.name for b in discover(str(tmp_path))] == ["D"]
    assert "zz_bot_e" in capsys.readouterr().out


def test_run_guarded_survives_a_crashing_session(capsys):
    from lib.bots import run_guarded

    def crash(stats):
        raise ModuleNotFoundError("No module named 'tanner.config'")
    assert run_guarded(crash, {}) is False
    assert "tanner.config" in capsys.readouterr().err
    assert run_guarded(lambda stats: None, {}) is True
