"""lib.accounts: the active account (data/active_account, written by the web app) and
session_start tagging. conftest points accounts.ROOT at tmp_path."""
import json

import lib.accounts as accounts
import lib.events as events
import lib.pause as pause
import lib.session as session


def write_active(tmp_path, text):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "active_account").write_text(text, encoding="utf-8")


def test_active_account_file_env_and_garbage(tmp_path, monkeypatch):
    assert accounts.active() is None                  # no file yet
    write_active(tmp_path, "Lynx Titan\n")
    assert accounts.active() == "Lynx Titan"
    monkeypatch.setenv(accounts.ENV_VAR, "Alt")
    assert accounts.active() == "Alt"
    monkeypatch.delenv(accounts.ENV_VAR)
    write_active(tmp_path, "\n")
    assert accounts.active() is None
    write_active(tmp_path, "Main\nleftover")
    assert accounts.active() == "Main"                # first line only


def test_unreadable_file_never_raises(tmp_path):
    (tmp_path / "data" / "active_account").mkdir(parents=True)   # a directory, not a file
    assert accounts.active() is None


def test_session_start_records_active_account(tmp_path, monkeypatch):
    write_active(tmp_path, "Main\n")
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    monkeypatch.setattr(session.log, "setup", lambda prefix, stamp=None: None)
    pause.reset()
    from transitions import Machine

    class M:
        pass

    def model():
        m = M()
        Machine(model=m, states=["a", "end"], initial="a", auto_transitions=False,
                transitions=[{"trigger": "ok", "source": "a", "dest": "end"}])
        return m
    try:
        session.run_session({}, bot="demo", log_prefix=str(tmp_path / "bot"), intro=[],
                            setup=lambda: None, session=model, handlers=lambda m: {"a": lambda: "ok"},
                            final_states={"end"}, cycle_start="a", summary=lambda m, f, l: "")
    finally:
        events.finish()
    (path,) = tmp_path.glob("bot_*.jsonl")
    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert first["event"] == "session_start" and first["account"] == "Main"
