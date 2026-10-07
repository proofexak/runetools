"""GE restock: live prices (lib/prices.py), per-bot settings and the offer price
(lib/restock.py), and the GE building blocks (lib/ge.py) — no network, no game."""
import io, json, types

import pytest

import lib.pause as pause
import lib.prices as prices
from lib.restock import Restock, buy_offer_price, sell_offer_price, reprice, setting, DEFAULTS


# ── prices ────────────────────────────────────────────────────────────────────

class _Opener:
    """Stands in for urllib's urlopen: answers by path, records each request."""
    def __init__(self, routes):
        self.routes, self.urls, self.agents = routes, [], []

    def __call__(self, req, timeout):
        self.urls.append(req.full_url)
        self.agents.append(req.get_header("User-agent"))
        for path, body in self.routes.items():
            if path in req.full_url:
                if isinstance(body, Exception):
                    raise body
                return io.BytesIO(json.dumps(body).encode())
        raise OSError("404")


@pytest.fixture(autouse=True)
def _fresh_price_cache(monkeypatch):
    monkeypatch.setattr(prices, "_cache", {})
    monkeypatch.setattr(prices, "_mapping", None)


def test_latest_quotes_a_known_item_with_a_named_user_agent():
    op = _Opener({"latest?id=1753": {"data": {"1753": {"high": 1570, "low": 1527}}}})
    assert prices.latest("Green dragonhide", opener=op) == {"high": 1570, "low": 1527}
    assert op.urls == [f"{prices.API}/latest?id=1753"]
    assert op.agents == [prices.USER_AGENT]


def test_latest_is_cached_for_a_while():
    op = _Opener({"latest?id=1973": {"data": {"1973": {"high": 30, "low": 28}}}})
    now = [1000.0]
    for _ in range(2):
        prices.latest("chocolate bar", opener=op, clock=lambda: now[0])
    now[0] += prices.CACHE_SECONDS + 1
    prices.latest("chocolate bar", opener=op, clock=lambda: now[0])
    assert len(op.urls) == 2


def test_latest_never_raises():
    assert prices.latest("green dragonhide", opener=_Opener({"latest": OSError("offline")})) is None
    assert prices.latest("green dragonhide", opener=_Opener({"latest": {"data": {}}})) is None
    assert prices.latest("Not an item", opener=_Opener({"mapping": [{"id": 1, "name": "Coins"}]})) is None
    assert prices.latest("Not an item", opener=_Opener({})) is None    # item list unreachable


def test_unknown_names_come_from_the_item_list():
    op = _Opener({"mapping": [{"id": 314, "name": "Feather"}],
                  "latest?id=314": {"data": {"314": {"high": 3, "low": 2}}}})
    assert prices.latest("feather", opener=op) == {"high": 3, "low": 2}


@pytest.mark.parametrize("quote, margin, expected", [
    ({"high": 1570, "low": 1527}, 0.05, 1649),     # ceil(1570 * 1.05)
    ({"high": None, "low": 1527}, 0.0, 1527),      # no recent instant-buy: the instant-sell price
    ({"high": 30, "low": 28}, 0.05, 32),
    (None, 0.05, None),
])
def test_buy_price(quote, margin, expected):
    assert prices.buy_price(quote, margin) == expected


@pytest.mark.parametrize("quote, margin, expected", [
    ({"high": 1811, "low": 1752}, 0.05, 1664),     # floor(1752 * 0.95)
    ({"high": 1811, "low": None}, 0.0, 1811),      # no recent instant-sell: the instant-buy price
    ({"high": 1, "low": 1}, 0.05, 1),              # never below 1
    (None, 0.05, None),
])
def test_sell_price(quote, margin, expected):
    assert prices.sell_price(quote, margin) == expected


# ── per-bot settings + offer price ────────────────────────────────────────────

@pytest.fixture
def ge_cfg(with_example_config):
    return with_example_config("lib", "ge", config="ge_config").cfg


def test_settings_come_from_the_bot_then_the_old_shared_config_then_defaults(ge_cfg, monkeypatch):
    bot = types.SimpleNamespace(GE_BUY_PRICE=40)
    monkeypatch.setattr(ge_cfg, "GE_QUANTITY", 500, raising=False)      # an older calibrated ge_config
    assert setting(bot, "GE_BUY_PRICE") == 40
    assert setting(bot, "GE_QUANTITY") == 500
    assert setting(bot, "GE_OFFER_TIMEOUT") == DEFAULTS["GE_OFFER_TIMEOUT"]


def test_restock_from_config_takes_the_quantity_it_is_given(ge_cfg):
    bot = types.SimpleNamespace(GE_QUANTITY=1, GE_BUY_PRICE=40, GE_MAX_PRICE=60, GE_LIVE_PRICES=True,
                                GE_MARGIN_PCT=5, GE_OFFER_TIMEOUT=360)
    r = Restock.from_config(bot, "chocolate bar", quantity=270)
    assert (r.buy_item, r.quantity, r.buy_price, r.max_price, r.offer_timeout) == \
           ("chocolate bar", 270, 40, 60, 360)


def _r(**kw):
    return Restock(**{"buy_item": "green dragonhide", "quantity": 100, "buy_price": 2000, **kw})


def test_offer_price_live_fallback_and_cap():
    quote = {"high": 1570, "low": 1527}
    assert buy_offer_price(_r(), quote)[0] == 1649
    assert buy_offer_price(_r(), None) == (2000, "config")                  # API unreachable
    assert buy_offer_price(_r(live_prices=False), quote) == (2000, "config")
    price, why = buy_offer_price(_r(max_price=1600), quote)
    assert price is None and "1649" in why and "GE_MAX_PRICE 1600" in why
    assert buy_offer_price(_r(max_price=1500), None)[0] is None             # the cap covers the fallback too


# ── GE building blocks ────────────────────────────────────────────────────────

@pytest.fixture
def ge(with_example_config, monkeypatch):
    ge = with_example_config("lib", "ge", config="ge_config")
    log = []
    monkeypatch.setattr(ge.time, "sleep", lambda s: log.append(("sleep", s)))
    monkeypatch.setattr(ge, "human_click", lambda x, y: log.append(("click", x, y)))
    monkeypatch.setattr(ge, "jitter", lambda x, y, n=8: (x, y))
    monkeypatch.setattr(ge, "human_typewrite", lambda t: log.append(("type", t)))
    monkeypatch.setattr(ge.pyautogui, "press", lambda k: log.append(("press", k)))
    return ge, log


def test_typed_numbers_wait_for_the_box_to_take_focus(ge):
    ge, log = ge
    ge._type_into((10, 20), "1")
    click, focus, typed = log[0], log[1], log[2]
    assert click == ("click", 10, 20) and typed == ("type", "1") and log[3] == ("press", "enter")
    assert focus[0] == "sleep" and focus[1] >= ge.BOX_FOCUS[0]


@pytest.mark.parametrize("shown, want, clicks", [
    ([False, True], True, 1),        # off → one click → on
    ([True], True, 0),               # already on: no click
    ([False, False, False], True, 2),
])
def test_set_notes_clicks_only_until_it_shows(ge, monkeypatch, shown, want, clicks):
    ge, log = ge
    reads = iter(shown)
    monkeypatch.setattr(ge, "pixel_matches", lambda *a, **k: next(reads))
    assert ge.set_notes(want) is (shown[-1] == want)
    assert sum(1 for c in log if c[0] == "click") == clicks


QUOTES = {"green dragonhide": {"high": 1570, "low": 1527}, "green dragon leather": {"high": 1811, "low": 1752}}


def test_trade_sells_then_buys_at_live_prices(ge, monkeypatch):
    ge, log = ge
    steps = []
    monkeypatch.setattr(ge.prices, "latest", lambda name, max_age=None: QUOTES[name])
    monkeypatch.setattr(ge, "sell", lambda price=None: steps.append(("sell", price)))
    monkeypatch.setattr(ge, "buy", lambda *a: steps.append(("buy",) + a))
    monkeypatch.setattr(ge, "wait_offer", lambda t: steps.append(("wait", t)) or True)
    monkeypatch.setattr(ge, "collect", lambda both=False: steps.append(("collect", both)))
    assert ge.trade(_r(sell_item="green dragon leather", reprice_minutes=0, offer_timeout=30)) == (True, None)
    assert steps == [("sell", 1664), ("wait", 30), ("collect", False),
                     ("buy", "green dragonhide", 100, 1649), ("wait", 30), ("collect", True)]


def test_sell_without_a_live_price_keeps_the_guide_price(ge):
    ge, log = ge
    assert sell_offer_price(_r(sell_item="green dragon leather"), None) == (None, "GE guide price")
    ge.sell(None)
    assert not any(c[0] == "type" for c in log)
    assert [c[1:] for c in log if c[0] == "click"] == [ge.cfg.SELL_SLOT, ge.cfg.CONFIRM_BTN]


def test_trade_stops_before_selling_when_the_price_is_over_the_cap(ge, monkeypatch):
    ge, log = ge
    monkeypatch.setattr(ge.prices, "latest", lambda name: {"high": 1570, "low": 1527})
    monkeypatch.setattr(ge, "sell", lambda price=None: pytest.fail("sold"))
    ok, why = ge.trade(_r(max_price=1000))
    assert not ok and "GE_MAX_PRICE" in why


def test_trade_names_the_offer_that_never_completed(ge, monkeypatch):
    ge, log = ge
    monkeypatch.setattr(ge.prices, "latest", lambda name: None)
    monkeypatch.setattr(ge, "sell", lambda price=None: None)
    monkeypatch.setattr(ge, "collect", lambda both=False: None)
    monkeypatch.setattr(ge, "buy", lambda *a: None)
    results = iter([True, False])
    monkeypatch.setattr(ge, "wait_offer", lambda t: next(results))
    assert ge.trade(_r(reprice_minutes=0)) == (False, "buy offer never completed (2000 gp)")


@pytest.fixture
def flow(ge, monkeypatch):
    ge, log = ge
    calls = []
    monkeypatch.setattr(ge.prices, "latest", lambda name: None)
    monkeypatch.setattr(ge, "_teleport", lambda: calls.append("teleport"))
    monkeypatch.setattr(ge, "face", lambda d, cfg: calls.append("face"))
    monkeypatch.setattr(ge, "withdraw_noted", lambda slot: calls.append(("withdraw", slot)) or True)
    monkeypatch.setattr(ge, "close_bank", lambda: None)
    monkeypatch.setattr(ge, "close_ge", lambda: None)
    monkeypatch.setattr(ge, "open_ge", lambda: True)
    monkeypatch.setattr(ge, "trade", lambda r: (True, None))
    return ge, calls, log


def _trip(**kw):
    return _r(bank_tab=(720, 253), sell_slot=(736, 294), deposit_btn=(1043, 675), **kw)


def test_run_ge_flow_uses_the_bots_bank_and_just_deposits_all(flow, monkeypatch):
    ge, calls, log = flow
    monkeypatch.setattr(ge, "open_bank", lambda region: True)
    assert ge.run_ge_flow(_trip()) == (True, None)
    clicks = [c[1:] for c in log if c[0] == "click"]
    assert clicks == [(720, 253), (1043, 675)]                 # hide tab, then deposit all at the end
    assert ("withdraw", (736, 294)) in calls


def test_run_ge_flow_retries_the_banker_without_teleporting_again(flow, monkeypatch):
    ge, calls, log = flow
    banker = iter([False, False, True, True])       # approach region twice, then found; bank after the GE
    monkeypatch.setattr(ge, "open_bank", lambda region: next(banker))
    assert ge.run_ge_flow(_trip()) == (True, None)
    assert [c for c in calls if isinstance(c, str)] == ["teleport", "face", "face", "face"]


def test_run_ge_flow_spends_no_teleport_on_a_price_over_the_cap(flow):
    ge, calls, log = flow
    ok, why = ge.run_ge_flow(_trip(max_price=1000))     # fallback 2000 > 1000
    assert not ok and "GE_MAX_PRICE" in why and calls == []


def test_run_ge_flow_reports_why(flow, monkeypatch):
    ge, calls, log = flow
    monkeypatch.setattr(ge, "open_bank", lambda region: False)
    assert ge.run_ge_flow(_trip()) == (False, "banker not found at the GE")
    assert calls.count("teleport") == 1 and calls.count("face") == ge.cfg.GE_MAX_RETRIES


# ── wait_for ──────────────────────────────────────────────────────────────────

def test_wait_for_does_not_count_a_pause_against_the_timeout(monkeypatch):
    import lib.interface as interface
    now = [0.0]
    monkeypatch.setattr(interface.time, "time", lambda: now[0])
    monkeypatch.setattr(interface.time, "sleep", lambda s: now.__setitem__(0, now[0] + s))
    paused = iter([False, True] + [False] * 100)     # the 2nd poll had blocked on O for a while

    def wait():
        blocked = next(paused)
        if blocked:
            now[0] += 100
        return blocked
    monkeypatch.setattr(interface.pause, "wait", wait)
    checks = []
    assert interface.wait_for(lambda: checks.append(1) and False, timeout=5, poll=1) is False
    assert len(checks) == 7      # 1 before the pause, then the clock restarts: 6 more (t = 0..5)


def test_wait_for_lets_p_through(monkeypatch):
    import lib.interface as interface

    def stop():
        raise pause.ForceStop()
    monkeypatch.setattr(interface.pause, "wait", stop)
    with pytest.raises(pause.ForceStop):
        interface.wait_for(lambda: False, timeout=5)


# ── re-pricing an offer that doesn't fill ─────────────────────────────────────

def test_reprice_buy_follows_the_market_up_never_down():
    assert reprice(_r(), 1649, {"high": 1800, "low": 1750})[0] == 1890           # live 1800 +5 %
    assert reprice(_r(), 1649, {"high": 1500, "low": 1490})[0] == 1732           # live lower: still +5 %
    assert reprice(_r(), 1649, None)[0] == 1732                                  # API down: +5 %
    assert reprice(_r(margin_pct=0), 30, None)[0] == 31                          # always at least +1
    price, why = reprice(_r(max_price=1700), 1649, None)
    assert price is None and "GE_MAX_PRICE 1700" in why


def test_reprice_sell_follows_the_market_down_never_up():
    def sell(**kw):
        return _r(sell_item="green dragon leather", **kw)
    assert reprice(sell(), 1664, {"high": 1600, "low": 1500}, "sell")[0] == 1425  # live 1500 -5 %
    assert reprice(sell(), 1664, {"high": 1900, "low": 1850}, "sell")[0] == 1580  # live higher: still -5 %
    assert reprice(sell(margin_pct=0), 30, None, "sell")[0] == 29                 # always at least -1
    assert reprice(sell(), 1, None, "sell")[0] is None                            # can't go under 1 gp
    assert reprice(sell(), None, None, "sell")[0] is None                         # guide price, no live: leave it
    assert reprice(sell(), None, {"high": 1600, "low": 1500}, "sell")[0] == 1425


@pytest.fixture
def follow(ge, monkeypatch):
    ge, log = ge
    steps = []
    monkeypatch.setattr(ge.cfg, "EDIT_BTN", (50, 50))
    monkeypatch.setattr(ge.prices, "latest", lambda name, max_age=None: None)
    monkeypatch.setattr(ge, "collect", lambda both=False: steps.append(("collect", both)))
    monkeypatch.setattr(ge, "edit_offer", lambda price, both: steps.append(("edit", price, both)))

    def waits(*results):
        it = iter(results)
        monkeypatch.setattr(ge, "wait_offer", lambda t: steps.append(("wait", t)) or next(it))
    return ge, steps, waits


def test_follow_offer_that_completes_just_collects(follow):
    ge, steps, waits = follow
    waits(True)
    assert ge.follow_offer(_r(), "buy", 1649) == (True, None)
    assert steps == [("wait", 300), ("collect", True)]


def test_follow_offer_edits_the_price_every_interval(follow, monkeypatch):
    ge, steps, waits = follow
    waits(False, False, True)
    monkeypatch.setattr(ge.prices, "latest", lambda name, max_age=None: {"high": 1800, "low": 1750})
    assert ge.follow_offer(_r(), "buy", 1649) == (True, None)
    assert steps == [("wait", 300), ("edit", 1890, True),
                     ("wait", 300), ("edit", 1985, True),
                     ("wait", 300), ("collect", True)]


def test_follow_offer_sell_goes_down_and_collects_only_coins(follow, monkeypatch):
    ge, steps, waits = follow
    waits(False, True)
    monkeypatch.setattr(ge.prices, "latest", lambda name, max_age=None: {"high": 1600, "low": 1500})
    assert ge.follow_offer(_r(sell_item="green dragon leather"), "sell", 1664) == (True, None)
    assert steps == [("wait", 300), ("edit", 1425, False), ("wait", 300), ("collect", False)]


def test_follow_offer_over_the_cap_leaves_the_offer_and_keeps_waiting(follow):
    ge, steps, waits = follow
    waits(False, True)
    assert ge.follow_offer(_r(max_price=1700), "buy", 1649) == (True, None)
    assert not any(st[0] == "edit" for st in steps)


def test_follow_offer_gives_up_after_its_rounds(follow):
    ge, steps, waits = follow
    waits(False, False, False)
    ok, why = ge.follow_offer(_r(reprice_rounds=2), "buy", 1000)
    assert not ok and "after 2 price edits" in why
    assert sum(1 for st in steps if st[0] == "edit") == 2


def test_follow_offer_uncalibrated_or_off_just_waits(follow, monkeypatch):
    ge, steps, waits = follow
    waits(True)
    monkeypatch.setattr(ge.cfg, "EDIT_BTN", (0, 0))
    assert ge.follow_offer(_r(offer_timeout=45), "buy", 1649) == (True, None)
    assert steps == [("wait", 45), ("collect", True)]
    steps.clear()
    waits(False)
    monkeypatch.setattr(ge.cfg, "EDIT_BTN", (50, 50))
    assert ge.follow_offer(_r(offer_timeout=45, reprice_minutes=0), "sell", None) == \
        (False, "sell offer never completed (guide price)")


def test_edit_offer_collects_then_types_the_new_price(ge, monkeypatch):
    ge, log = ge
    monkeypatch.setattr(ge.cfg, "EDIT_BTN", (50, 50))
    ge.edit_offer(1890, both=True)
    clicks = [c[1:] for c in log if c[0] == "click"]
    x, y, _ = ge.cfg.OFFER_COMPLETE
    assert clicks == [(x, y), ge.cfg.RETRIEVE_SLOT_1, ge.cfg.RETRIEVE_SLOT_2, (50, 50),
                      ge.cfg.PRICE_BTN, ge.cfg.CONFIRM_BTN]
    assert ("type", "1890") in log
