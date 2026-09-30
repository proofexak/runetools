"""
Live in-game check scripts live in <bot>/checks/ (see CLAUDE.md) and are run by
hand with `python -m`. They drive the real game, so pytest must never import
them: no test_*.py outside tests/, and every check is main-guarded.
Static checks only — nothing here imports a check.
"""
import ast
import glob
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".venv", ".git", "tests", "woodcutter", "docs", "__pycache__"}


def _py_files():
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".")]
        for f in filenames:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


def test_no_test_named_scripts_outside_tests():
    offenders = [os.path.relpath(p, REPO) for p in _py_files()
                 if os.path.basename(p).startswith("test_")]
    assert offenders == []


def _has_main_guard(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.If) and "__main__" in ast.dump(node.test):
            return True
    return False


def _top_level_side_effects(path):
    """Top-level statements other than imports, defs, docstrings, constants and the main guard."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    bad = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign)):
            continue
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
            continue
        if isinstance(node, ast.If) and "__main__" in ast.dump(node.test):
            continue
        bad.append(node.lineno)
    return bad


def _checks():
    return [p for p in glob.glob(os.path.join(REPO, "**", "checks", "*.py"), recursive=True)
            if os.path.basename(p) != "__init__.py" and ".venv" not in p]


def test_live_checks_exist_and_are_main_guarded():
    checks = _checks()
    assert len(checks) >= 7
    for path in checks:
        rel = os.path.relpath(path, REPO)
        assert _has_main_guard(path), f"{rel} has no __main__ guard"
        assert _top_level_side_effects(path) == [], f"{rel} runs code at import"
