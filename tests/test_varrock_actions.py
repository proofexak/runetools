class FakeTime:
    def __init__(self):
        self.t = 0.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_wait_and_drop_is_pausable_and_pause_extends_the_wait(with_example_config, monkeypatch):
    actions = with_example_config("miner.varrock_exp", "actions")
    clock, waits = FakeTime(), []
    monkeypatch.setattr(actions, "time", clock)
    monkeypatch.setattr(actions, "pixel_matches", lambda x, y, c: True)   # slot stays empty

    def wait():
        waits.append(clock.t)
        if len(waits) == 1:
            clock.t += 100          # paused for 100s on the first poll
            return True
        return False
    monkeypatch.setattr(actions.pause, "wait", wait)

    assert actions.wait_and_drop() is False
    assert len(waits) > 5                              # gated every poll
    assert clock.t >= 100 + actions.ORE_TIMEOUT        # full timeout after resuming


def test_both_drop_handlers_count_an_ore(with_example_config, monkeypatch):
    # the old loop counted only the second rock's drop: half the ore mined
    run = with_example_config("miner.varrock_exp", "run")
    from miner.varrock_exp.states import build_machine
    session = build_machine({})
    drops = iter([True, True, False])
    monkeypatch.setattr(run, "wait_and_drop", lambda: next(drops))
    handlers = run._handlers(session)
    assert handlers["drop_first"]() == "ok" and handlers["drop_second"]() == "ok"
    assert session.ores == 2 and session.stats["run"] == 2
    handlers["drop_first"]()                      # nothing in the slot: no ore
    assert session.ores == 2
