"""
What a bot restocks at the GE, and at what price — pure, no input or screen.

Each bot keeps its own GE_* settings in its own config.py (tanner and choc used
to share one GE_BUY_PRICE in lib/ge_config.py and overwrote each other's). A
setting missing there falls back to lib/ge_config.py, where older calibrated
configs still have it, then to DEFAULTS.
"""
import math
from dataclasses import dataclass

import lib.prices as prices

DEFAULTS = {
    "GE_QUANTITY":      1,
    "GE_BUY_PRICE":     2000,   # used when live prices are off or the API can't be reached
    "GE_MAX_PRICE":     0,      # never offer more than this per item (0 = no cap)
    "GE_LIVE_PRICES":   True,   # price the buy from prices.runescape.wiki
    "GE_MARGIN_PCT":    5,      # % over the live instant-buy price, so the offer fills at once
    "GE_OFFER_TIMEOUT": 60,     # seconds to wait for the sell (and the buy when re-pricing is off)
    "GE_REPRICE_MINUTES": 5,    # a buy not complete after this long: collect, re-price the rest (0 = off)
    "GE_REPRICE_ROUNDS":  6,    # re-prices before the restock gives up
}


def setting(bot_cfg, name):
    """`name` from the bot's config, else lib/ge_config.py, else DEFAULTS."""
    if hasattr(bot_cfg, name):
        return getattr(bot_cfg, name)
    try:
        import lib.ge_config as ge_cfg
        if hasattr(ge_cfg, name):
            return getattr(ge_cfg, name)
    except ImportError:
        pass
    return DEFAULTS.get(name)


@dataclass
class Restock:
    buy_item:      str      # typed into the GE search, and its price is looked up by this name
    quantity:      int
    buy_price:     int      # fallback price
    max_price:     int = 0
    live_prices:   bool = True
    margin_pct:    int = 5
    offer_timeout: float = 60
    reprice_minutes: float = 5
    reprice_rounds:  int = 6
    # The bot's own bank layout, for a trip that banks at the GE (lib.ge.run_ge_flow):
    bank_tab:    tuple = None   # tab holding the item to sell (tanner: HIDE_TAB)
    sell_slot:   tuple = None   # its slot there, withdrawn as notes (tanner: BANK_SLOT_2)
    deposit_btn: tuple = None

    @classmethod
    def from_config(cls, bot_cfg, buy_item, quantity=None, **bank):
        s = lambda name: setting(bot_cfg, name)
        return cls(buy_item=buy_item,
                   quantity=quantity if quantity is not None else s("GE_QUANTITY"),
                   buy_price=s("GE_BUY_PRICE"), max_price=s("GE_MAX_PRICE"),
                   live_prices=s("GE_LIVE_PRICES"), margin_pct=s("GE_MARGIN_PCT"),
                   offer_timeout=s("GE_OFFER_TIMEOUT"), reprice_minutes=s("GE_REPRICE_MINUTES"),
                   reprice_rounds=s("GE_REPRICE_ROUNDS"), **bank)


def buy_offer_price(r, quote=None):
    """(price, where it came from) to offer for r.buy_item, or (None, reason) above the cap.
    `quote` is prices.latest(r.buy_item) (None = unreachable → the fallback price)."""
    price, source = r.buy_price, "config"
    if r.live_prices:
        live = prices.buy_price(quote, r.margin_pct / 100)
        if live is not None:
            price, source = live, f"live {quote.get('high') or quote.get('low')} +{r.margin_pct}%"
    if r.max_price and price > r.max_price:
        return None, f"{r.buy_item} at {price} gp ({source}) is above GE_MAX_PRICE {r.max_price}"
    return price, source


def reprice(r, current, quote=None):
    """Next price for a buy that sat unfilled at `current`: the fresh live price
    (+ margin), but at least `current` + margin — an offer that hasn't filled is
    below the market, so following it only ever goes up. (price, source), or
    (None, reason) once that passes GE_MAX_PRICE (the offer then stays as it is)."""
    price = max(current + 1, math.ceil(current * (1 + r.margin_pct / 100)))
    source = f"{current} +{r.margin_pct}%"
    live = prices.buy_price(quote, r.margin_pct / 100) if r.live_prices else None
    if live is not None and live > price:
        price, source = live, f"live {quote.get('high') or quote.get('low')} +{r.margin_pct}%"
    if r.max_price and price > r.max_price:
        return None, f"{r.buy_item} at {price} gp ({source}) is above GE_MAX_PRICE {r.max_price}"
    return price, source


def still_to_buy(wanted, done):
    """Items left to buy of `wanted` once the progress bar shows `done` (0..1)."""
    return max(0, wanted - round(wanted * done))
