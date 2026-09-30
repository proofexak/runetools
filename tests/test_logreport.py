import json

import pytest

from lib import logreport as lr


def ev(event, t, **f):
    """Event at 12:00:00 + t seconds."""
    m, s = divmod(t, 60)
    return {"ts": f"2026-09-30T12:{int(m):02d}:{s:06.3f}", "session": "20260930_120000",
            "bot": "tanner", "event": event, **f}


NORMAL = [
    ev("session_start", 0, params={"hide_type": "green"}),
    ev("step", 10, state="walk_to_tanner", result="ok", seconds=10.0, run=1),
    ev("step", 15, state="trade_ellis", result="fail", seconds=5.0, run=1),
    ev("step", 45, state="recover", result="ok", seconds=30.0, run=1),
    ev("pause", 945, state="walk_to_tanner", seconds=900.0),
    ev("step", 960, state="walk_to_tanner", result="ok", seconds=15.0, run=2),
    ev("session_end", 3600 + 900, final="stopped", reason="stopped via overlay", last_step="banking",
       stats={"run": 20}, active_seconds=3600.0, paused_seconds=900.0),
]


def test_parse_lines_skips_bad_lines():
    lines = [json.dumps(NORMAL[0]), "", '{"ts": "2026-09-30T12:0', json.dumps({"no_event": 1})]
    events, bad = lr.parse_lines(lines)
    assert events == [NORMAL[0]] and bad == 2


def test_summarize_normal_session():
    s = lr.summarize(NORMAL)
    assert s["session"] == "20260930_120000" and s["bot"] == "tanner"
    assert s["params"] == {"hide_type": "green"}
    assert s["final"] == "stopped" and s["reason"] == "stopped via overlay" and s["last_step"] == "banking"
    assert s["active_seconds"] == 3600.0 and s["paused_seconds"] == 900.0
    assert s["runs"] == 20 and s["runs_per_hour"] == 20.0          # paused time excluded
    assert s["state_time"] == {"walk_to_tanner": 25.0, "trade_ellis": 5.0, "recover": 30.0}
    assert s["state_counts"] == {"walk_to_tanner": 2, "trade_ellis": 1, "recover": 1}
    assert s["non_ok"] == [(NORMAL[2]["ts"], "trade_ellis", "fail")]
    assert s["recoveries"] == 1 and s["pauses"] == 1 and s["errors"] == []


def test_summarize_crashed_session_keeps_traceback():
    events = NORMAL[:3] + [
        ev("error", 16, where="session", state="trade_ellis", type="RuntimeError",
           message="boom", traceback="Traceback ...\nRuntimeError: boom\n"),
        ev("session_end", 16, final="crashed", reason=None, last_step="trade_ellis",
           stats={"run": 1}, active_seconds=16.0, paused_seconds=0.0)]
    s = lr.summarize(events)
    assert s["final"] == "crashed"
    (err,) = s["errors"]
    assert err["type"] == "RuntimeError" and "RuntimeError: boom" in err["traceback"]


def test_summarize_killed_session_without_end():
    s = lr.summarize(NORMAL[:6])
    assert s["final"] == "killed" and s["reason"] is None
    assert s["paused_seconds"] == 900.0
    assert s["active_seconds"] == 960.0 - 900.0          # last event - start - paused
    assert s["runs"] == 2                                  # last step's run count


def test_aggregate_per_bot():
    tanner = lr.summarize(NORMAL)
    crash = dict(lr.summarize(NORMAL), final="crashed",
                 errors=[{"type": "RuntimeError", "where": "session"}], runs=0, active_seconds=1800.0)
    gn = dict(lr.summarize(NORMAL), bot="golden_nuggets")
    agg = lr.aggregate([tanner, crash, gn])
    t = agg["tanner"]
    assert t["sessions"] == 2 and t["active_hours"] == 1.5 and t["runs"] == 20
    assert t["runs_per_hour"] == pytest.approx(20 / 1.5)
    assert t["finals"] == {"stopped": 1, "crashed": 1}
    assert t["reasons"]["stopped via overlay"] == 2
    assert t["failures_by_state"]["trade_ellis"] == (2, 1.0)
    assert t["recoveries_per_hour"] == pytest.approx(2 / 1.5)
    assert t["crash_types"] == {"RuntimeError": 1}
    assert agg["golden_nuggets"]["sessions"] == 1


def _write(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events))


@pytest.fixture
def root(tmp_path):
    _write(tmp_path / "tanner" / "log" / "tanner_20260930_120000.jsonl", NORMAL)
    crashed = [dict(e, session="20260930_130000", bot="golden_nuggets") for e in NORMAL[:2]] + [
        dict(ev("error", 20, where="session", state="deposit", type="AttributeError",
                message="STRUT_COLOR", traceback="Traceback\nAttributeError: STRUT_COLOR\n"),
             session="20260930_130000", bot="golden_nuggets"),
        dict(ev("session_end", 20, final="crashed", reason=None, last_step="deposit", stats={"run": 0},
                active_seconds=20.0, paused_seconds=0.0), session="20260930_130000", bot="golden_nuggets")]
    _write(tmp_path / "miner" / "golden_nuggets" / "log" / "golden_nuggets_20260930_130000.jsonl", crashed)
    _write(tmp_path / "log" / "launcher.jsonl",
           [{"ts": "2026-09-30T14:00:00.000", "session": None, "bot": "Choco Grind", "event": "error",
             "where": "start", "type": "ModuleNotFoundError", "message": "choc.config", "traceback": "..."}])
    return str(tmp_path)


def test_cli_sessions(root, capsys):
    lr.main(["sessions"], root=root)
    out = capsys.readouterr().out
    assert "tanner" in out and "golden_nuggets" in out and "crashed" in out and "stopped" in out


def test_cli_session_latest_shows_traceback(root, capsys):
    lr.main(["session", "latest"], root=root)
    out = capsys.readouterr().out
    assert "golden_nuggets" in out and "AttributeError: STRUT_COLOR" in out


def test_cli_stats_and_launcher_errors(root, capsys):
    lr.main(["stats"], root=root)
    out = capsys.readouterr().out
    assert "tanner" in out and "golden_nuggets" in out
    assert "Launcher errors: 1" in out


def test_cli_bot_filter(root, capsys):
    lr.main(["sessions", "--bot", "tanner"], root=root)
    assert "golden_nuggets" not in capsys.readouterr().out


def test_routing_results_are_not_failures():
    events = [ev("session_start", 0),
              ev("step", 5, state="seek_vein", result="full", seconds=1.0, run=0),
              ev("step", 9, state="seek_vein", result="not_found", seconds=1.0, run=0),
              ev("step", 12, state="banking", result="restock", seconds=1.0, run=0)]
    s = lr.summarize(events)
    assert [r for _, _, r in s["non_ok"]] == ["full", "not_found", "restock"]   # detail view: all
    agg = lr.aggregate([s])["tanner"]
    assert agg["failures_by_state"] == {"seek_vein": (1, 0.5)}                   # stats: failures only


def test_rate_hidden_for_sessions_under_a_minute(capsys):
    s = lr.summarize(NORMAL)
    lr._print_sessions([dict(s, active_seconds=30.0, runs_per_hour=240.0)], 20)
    assert "240.0" not in capsys.readouterr().out
