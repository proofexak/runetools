import json
import sys
import threading
from datetime import datetime

import lib.events as events


def _lines(path):
    return [json.loads(l) for l in open(path, encoding="utf-8").read().splitlines()]


def test_emit_writes_common_fields(tmp_path):
    log = events.EventLog(str(tmp_path / "s.jsonl"), bot="tanner", session="20260930_120000")
    log.emit("step", state="banking", result="ok")
    (rec,) = _lines(tmp_path / "s.jsonl")          # readable before close: flushed
    log.close()
    datetime.fromisoformat(rec["ts"])
    assert rec["session"] == "20260930_120000" and rec["bot"] == "tanner"
    assert rec["event"] == "step" and rec["state"] == "banking" and rec["result"] == "ok"


def test_non_serialisable_values_become_repr(tmp_path):
    log = events.EventLog(str(tmp_path / "s.jsonl"), bot="b", session="s")
    log.emit("step", thing=object(), pos=(1, 2))
    log.close()
    (rec,) = _lines(tmp_path / "s.jsonl")
    assert rec["thing"].startswith("<object object") and rec["pos"] == [1, 2]


def test_unwritable_log_never_raises(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(events, "_warned", False)
    log = events.EventLog(str(tmp_path), bot="b", session="s")   # a directory: can't open
    log.emit("step")
    log.emit("step")
    log.close()
    assert capsys.readouterr().err.count("[events]") == 1


def test_current_is_set_by_start_and_cleared_by_finish(tmp_path):
    assert events.current() is None
    log = events.start(str(tmp_path / "s.jsonl"), bot="b", session="s")
    assert events.current() is log
    events.finish()
    assert events.current() is None


def test_launcher_error_appends_to_root_log(tmp_path):
    try:
        raise ModuleNotFoundError("No module named 'tanner.config'")
    except ModuleNotFoundError as e:
        events.launcher_error("Tanning", e, "start", root=str(tmp_path))
    (rec,) = _lines(tmp_path / "log" / "launcher.jsonl")
    assert rec["event"] == "error" and rec["bot"] == "Tanning" and rec["session"] is None
    assert rec["where"] == "start" and rec["type"] == "ModuleNotFoundError"
    assert "tanner.config" in rec["message"] and "Traceback" in rec["traceback"]


def test_sys_excepthook_records_then_chains(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: seen.append(a[0]))
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    events.install_excepthooks(root=str(tmp_path))
    err = ValueError("boom")
    sys.excepthook(ValueError, err, None)
    assert seen == [ValueError]
    (rec,) = _lines(tmp_path / "log" / "launcher.jsonl")
    assert rec["where"] == "uncaught" and rec["type"] == "ValueError"


def test_threading_excepthook_records_then_chains(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: None)
    monkeypatch.setattr(threading, "excepthook", lambda args: seen.append(args))
    events.install_excepthooks(root=str(tmp_path))

    class Args:
        exc_type, exc_value, exc_traceback = RuntimeError, RuntimeError("tk"), None
        thread = threading.current_thread()
    threading.excepthook(Args)
    assert seen == [Args]
    (rec,) = _lines(tmp_path / "log" / "launcher.jsonl")
    assert rec["where"].startswith("thread") and rec["type"] == "RuntimeError"


def test_error_already_logged_by_a_session_is_not_repeated(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", lambda *a: None)
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    events.install_excepthooks(root=str(tmp_path))
    err = KeyboardInterrupt()
    events.mark_logged(err)
    sys.excepthook(KeyboardInterrupt, err, None)
    assert not (tmp_path / "log" / "launcher.jsonl").exists()
