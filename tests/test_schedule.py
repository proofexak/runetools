"""lib/schedule.py: reading data/schedules/<account>.json (written by the web app, PRO-102)."""
import json
import os

import pytest

import lib.schedule as schedule
from lib.schedule import Block


def write(tmp_path, data):
    path = tmp_path / "alt1.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return str(path)


def row(id, start, end, bot="Tanning", launch="Green Dragonhide", value="Al Kharid"):
    return {"id": id, "start": start, "end": end, "bot": bot, "launch": launch, "value": value}


def test_path_for():
    assert schedule.path_for("alt1", "/r") == os.path.join("/r", "data", "schedules", "alt1.json")
    assert schedule.path_for(None) is None
    assert schedule.path_for("") is None


def test_load_reads_blocks(tmp_path):
    path = write(tmp_path, {"account": "alt1", "enabled": True, "timezone": "Europe/Warsaw",
                            "blocks": [row(2, 300, 400, value=None), row(1, 100, 200)]})
    enabled, blocks = schedule.load(path)
    assert enabled is True
    assert blocks == [Block(1, 100, 200, "Tanning", "Green Dragonhide", "Al Kharid"),
                      Block(2, 300, 400, "Tanning", "Green Dragonhide", None)]


@pytest.mark.parametrize("content", [None, "{", "[]", {"enabled": True}, {"enabled": True, "blocks": "x"}])
def test_load_bad_files(tmp_path, content):
    path = None if content is None else write(tmp_path, content)
    assert schedule.load(path) == (False, [])


def test_load_missing_file(tmp_path):
    assert schedule.load(str(tmp_path / "nope.json")) == (False, [])


def test_load_drops_bad_rows(tmp_path):
    bad = row(3, 500, 600)
    del bad["bot"]
    path = write(tmp_path, {"enabled": True, "blocks": [row(1, 100, 200), bad, row(4, 700, 700), "x"]})
    assert [b.id for b in schedule.load(path)[1]] == [1]


def test_disabled_file_has_no_play(tmp_path):
    path = write(tmp_path, {"enabled": False, "blocks": [row(1, 100, 200)]})
    enabled, blocks = schedule.load(path)
    assert enabled is False and len(blocks) == 1


def test_current_and_next():
    b = [Block(1, 100, 200, "a", "b", None), Block(2, 300, 400, "a", "b", None)]
    assert schedule.current(b, 150).id == 1
    assert schedule.current(b, 100).id == 1
    assert schedule.current(b, 200) is None
    assert schedule.current(b, 250) is None
    assert schedule.next_start(b, 250) == 300
    assert schedule.next_start(b, 50) == 100
    assert schedule.next_start(b, 400) is None
