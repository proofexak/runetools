"""Shell scripts that run inside the Linux container must keep LF line endings,
even when the repo is checked out on Windows (Git for Windows converts to CRLF
by default -> "/bin/bash^M: bad interpreter")."""
import os
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _shebang_scripts():
    out = []
    for name in os.listdir(os.path.join(REPO, "docker")):
        path = os.path.join(REPO, "docker", name)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                if f.read(2) == b"#!":
                    out.append(f"docker/{name}")
    return out


def test_container_scripts_are_forced_to_lf():
    scripts = _shebang_scripts()
    assert {"docker/entrypoint.sh", "docker/runelite", "docker/botctl", "docker/measure.sh"} <= set(scripts)
    for script in scripts:
        attr = subprocess.run(["git", "check-attr", "eol", "--", script], cwd=REPO,
                              capture_output=True, text=True).stdout
        assert attr.strip().endswith("eol: lf"), f"{script} not forced to LF in .gitattributes"


def test_container_scripts_have_no_crlf_now():
    for script in _shebang_scripts():
        with open(os.path.join(REPO, script), "rb") as f:
            assert b"\r\n" not in f.read(), script
