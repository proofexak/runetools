import importlib, importlib.util, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def with_example_config(monkeypatch):
    """Import <pkg>.<module> against <pkg>/config.example.py instead of the
    user's gitignored, calibrated config.py: with_example_config("crafting", "actions")."""
    def load(pkg, module):
        path = os.path.join(ROOT, *pkg.split("."), "config.example.py")
        spec = importlib.util.spec_from_file_location(f"{pkg}.config", path)
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        monkeypatch.setitem(sys.modules, f"{pkg}.config", cfg)
        monkeypatch.setattr(importlib.import_module(pkg), "config", cfg, raising=False)
        monkeypatch.delitem(sys.modules, f"{pkg}.{module}", raising=False)
        return importlib.import_module(f"{pkg}.{module}")
    return load
