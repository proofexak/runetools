"""
What a bot restocks at the GE, and at what price — pure, no input or screen.

Each bot keeps its own GE_* settings in its own config.py (tanner and choc used
to share one GE_BUY_PRICE in lib/ge_config.py and overwrote each other's). A
setting missing there falls back to lib/ge_config.py, where older calibrated
configs still have it, then to DEFAULTS.
"""
from dataclasses import dataclass

import lib.prices as prices

DEFAULTS = {
    "GE_QUANTITY":      1,
    "GE_BUY_PRICE":     2000,   # used when live prices are off or the API can't be reached
    "GE_MAX_PRICE":     0,      # never offer more than this per item (0 = no cap)
    "GE_LIVE_PRICES":   True,   # price both offers from prices.runescape.wiki (hour avg ± 1 gp)
    "GE_OFFER_TIMEOUT": 60,     # seconds to wait for an offer when re-pricing is off
    "GE_REPRICE_MINUTES": 5,    # an offer not complete after this long: collect, edit its price (0 = off)
    "GE_REPRICE_ROUNDS":  6,    # price edits before the restock gives up
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
    sell_item:     str = None   # what's sold first, by name for its live price (None: GE's guide price)
    max_price:     int = 0
    live_prices:   bool = True
    offer_timeout: float = 60
    reprice_minutes: float = 5
    reprice_rounds:  int = 6
    sell_inv_slot: tuple = None   # inventory slot the item to sell is in, clicked to sell it
    # The bot's own bank layout, for a trip that banks at the GE (lib.ge.run_ge_flow):
    bank_tab:    tuple = None   # tab holding the item to sell (tanner: HIDE_TAB)
    sell_slot:   tuple = None   # its slot there, withdrawn as notes (tanner: BANK_SLOT_2)
    deposit_btn: tuple = None

    @classmethod
    def from_config(cls, bot_cfg, buy_item, quantity=None, sell_item=None, **bank):
        s = lambda name: setting(bot_cfg, name)
        return cls(buy_item=buy_item, sell_item=sell_item,
                   quantity=quantity if quantity is not None else s("GE_QUANTITY"),
                   buy_price=s("GE_BUY_PRICE"), max_price=s("GE_MAX_PRICE"),
                   live_prices=s("GE_LIVE_PRICES"),
                   offer_timeout=s("GE_OFFER_TIMEOUT"), reprice_minutes=s("GE_REPRICE_MINUTES"),
                   reprice_rounds=s("GE_REPRICE_ROUNDS"), **bank)


def _over_cap(r, price, source):
    return f"{r.buy_item} at {price} gp ({source}) is above GE_MAX_PRICE {r.max_price}"


def buy_offer_price(r, quote=None):
    """(price, where it came from) to offer for r.buy_item — the hour's average instant-buy
    + 1 gp — or (None, reason) above the cap. No quote (live prices off / API unreachable)
    → the fallback GE_BUY_PRICE."""
    price, source = prices.buy_price(quote) if r.live_prices else (None, None)
    if price is None:
        price, source = r.buy_price, "config"
    if r.max_price and price > r.max_price:
        return None, _over_cap(r, price, source)
    return price, source


def sell_offer_price(r, quote=None):
    """(price, source) to sell r.sell_item at: the hour's average instant-sell - 1 gp.
    (None, "GE guide price") without one — then the price the GE fills in is kept."""
    price, source = prices.sell_price(quote) if r.live_prices else (None, None)
    return (price, source) if price is not None else (None, "GE guide price")


def reprice(r, current, quote=None, side="buy"):
    """New price for an offer that sat unfilled at `current`: a fresh check — the latest
    trade + 1 gp (buy) / - 1 gp (sell). (price, source), or (None, reason) to leave the
    offer as it is: no live price, the same price, or a buy past GE_MAX_PRICE."""
    if not r.live_prices:
        return None, "live prices are off"
    price, source = prices.buy_price(quote, latest=True) if side == "buy" else prices.sell_price(quote, latest=True)
    if price is None:
        return None, "no live price"
    if price == current:
        return None, f"still {price} gp ({source})"
    if side == "buy" and r.max_price and price > r.max_price:
        return None, _over_cap(r, price, source)
    return price, source
