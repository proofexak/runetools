"""The miners wait before they report "not_found" (a rock / vein may respawn meanwhile): the
failure screenshot is taken at the miss, before that wait (PRO-91 review)."""
import lib.screenshots as screenshots


def test_varrock_no_rock_shot_before_the_wait(with_example_config, monkeypatch):
    with_example_config("miner.varrock_exp", "actions")
    run = with_example_config("miner.varrock_exp", "run")
    order = []
    monkeypatch.setattr(screenshots, "failed_now", lambda result: order.append(("shot", result)))
    monkeypatch.setattr(run.time, "sleep", lambda s: order.append(("sleep", s)))
    assert run._mine({}, lambda: False, lambda: False, "magenta", "blue") == "not_found"
    assert order == [("shot", "not_found"), ("sleep", 10)]


def test_golden_nuggets_no_vein_shot_before_the_wait(with_example_config, monkeypatch):
    with_example_config("miner.golden_nuggets", "actions")
    run = with_example_config("miner.golden_nuggets", "run")
    order = []
    monkeypatch.setattr(screenshots, "failed_now", lambda result: order.append(("shot", result)))
    monkeypatch.setattr(run.time, "sleep", lambda s: order.append(("sleep", s)))
    monkeypatch.setattr(run, "count_filled_slots", lambda: 3)
    monkeypatch.setattr(run, "click_nearest_vein", lambda: None)
    handlers = run._handlers(object(), {"start": 0})
    assert handlers["seek_vein"]() == "not_found"
    assert order == [("shot", "not_found"), ("sleep", 3)]
