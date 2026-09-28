import re

from lib.config_editor import save_attr
import lib.log as log


def test_say_prefixes_timestamp(capsys):
    log.say("hi")
    assert re.match(r"^\[\d\d:\d\d:\d\d\] hi$", capsys.readouterr().out.strip())


def test_save_attr_replaces_only_exact_attr(tmp_path):
    p = tmp_path / "config.py"
    p.write_text("BANK_SLOT_1 = (0, 0)\nBANK_SLOT_10 = (5, 5)\n", encoding="utf-8")
    save_attr(str(p), "BANK_SLOT_1", (1, 2))
    assert p.read_text(encoding="utf-8") == "BANK_SLOT_1 = (1, 2)\nBANK_SLOT_10 = (5, 5)\n"


def test_save_attr_keeps_other_lines(tmp_path):
    p = tmp_path / "config.py"
    p.write_text('"""doc"""\nA = 1   # comment kept? no - value line replaced\nB = [1, 2]\n', encoding="utf-8")
    save_attr(str(p), "B", [3])
    assert p.read_text(encoding="utf-8").splitlines() == [
        '"""doc"""', "A = 1   # comment kept? no - value line replaced", "B = [3]"]
