import importlib, importlib.util, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def with_example_config(monkeypatch):
    """Import <pkg>.<module> against <pkg>/config.example.py instead of the
    user's gitignored, calibrated config.py: with_example_config("crafting", "actions").
    `config` names a differently-called config module, e.g. ("lib", "ge", config="ge_config")."""
    def load(pkg, module, config="config"):
        path = os.path.join(ROOT, *pkg.split("."), f"{config}.example.py")
        spec = importlib.util.spec_from_file_location(f"{pkg}.{config}", path)
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        monkeypatch.setitem(sys.modules, f"{pkg}.{config}", cfg)
        monkeypatch.setattr(importlib.import_module(pkg), config, cfg, raising=False)
        monkeypatch.delitem(sys.modules, f"{pkg}.{module}", raising=False)
        return importlib.import_module(f"{pkg}.{module}")
    return load


@pytest.fixture
def fake_screen(monkeypatch):
    """Replace mss with a synthetic canvas and pin random.triangular to its
    mode, so screen-reading code is deterministic. Returns the controller."""
    import random
    import mss
    from tests.fakescreen import FakeScreen
    screen = FakeScreen()
    monkeypatch.setattr(mss, "mss", screen.mss)
    monkeypatch.setattr(random, "triangular", lambda low, high, mode: mode)
    return screen


@pytest.fixture(autouse=True)
def _launcher_log_in_tmp(monkeypatch, tmp_path):
    """No test may write the real <repo>/log/launcher.jsonl."""
    import lib.events as events
    monkeypatch.setattr(events, "ROOT", str(tmp_path))
    # ... nor tag sessions with (or write) the user's real data/accounts.json
    import lib.accounts as accounts
    monkeypatch.setattr(accounts, "ROOT", str(tmp_path))
    monkeypatch.delenv(accounts.ENV_VAR, raising=False)
    # ... nor push events to a web app running on this machine (ROOT has no
    # data/bot_token either; tests that push pass push= explicitly)
    monkeypatch.setenv(events.APP_URL_VAR, "")
