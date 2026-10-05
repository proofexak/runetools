"""Active account (lib/accounts.py) and the session_start tag it feeds."""
import json

from transitions import Machine

import lib.accounts as accounts
import lib.events as events
import lib.pause as pause
import lib.session as session


def test_active_account_file_env_and_garbage(tmp_path, monkeypatch):
    assert accounts.active() is None
    accounts.save({"active": "Main", "accounts": [{"name": "Main"}]})
    assert accounts.active() == "Main"
    monkeypatch.setenv(accounts.ENV_VAR, "Alt")
    assert accounts.active() == "Alt"
    monkeypatch.delenv(accounts.ENV_VAR)
    (tmp_path / "data" / "accounts.json").write_text("[1, 2")
    assert accounts.active() is None


def test_session_start_records_active_account(tmp_path, monkeypatch):
    accounts.save({"active": "Main", "accounts": [{"name": "Main"}]})
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    monkeypatch.setattr(session.log, "setup", lambda prefix, stamp=None: None)
    pause.reset()

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
