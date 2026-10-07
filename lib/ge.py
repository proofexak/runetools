"""
Grand Exchange — the building blocks every bot's restock uses, plus tanner's full
restock trip (run_ge_flow).

Building blocks (positions from lib/ge_config.py, the GE interface is the same for
every bot): open_bank / open_ge, withdraw_noted, sell / buy / wait_offer / collect,
edit_offer, follow_offer (edits the price of an offer that sits unfilled), and
trade(), which sells the first inventory item then buys a lib.restock.Restock.
What to buy, how many and at what price is the bot's, not this module's.
"""
import time, random

import pyautogui

from lib.mouse     import smart_right_click, human_click, menu_click, jitter, human_typewrite
from lib.screen    import pixel_matches
from lib.interface import open_interface, close_interface, wait_for, shows
from lib.camera    import face
from lib.log       import say
from lib.restock   import buy_offer_price, sell_offer_price, reprice
import lib.prices    as prices
import lib.ge_config as cfg

# The price / quantity box is a popup that needs a moment to open and take focus —
# typed too early, the digits and the Enter go to public chat instead.
BOX_FOCUS = (0.7, 1.0)
OFFER_TOL = 30    # the "complete" pixel varied by 17 in one channel while genuinely complete


def _pause(lo=0.3, hi=0.5):
    time.sleep(random.uniform(lo, hi))


def _click(point, lo=0.3, hi=0.5):
    human_click(*jitter(*point))
    _pause(lo, hi)


# ── Bank ──────────────────────────────────────────────────────────────────────

def open_bank(region):
    """Find the blue banker in `region`, click, confirm the bank opened."""
    return open_interface(cfg.BLUE, cfg.BLUE_TOL, region, cfg.BANK_CHECK, cfg.MAX_BANKER_TRIES,
                          what="[GE] Banker")


def set_notes(on):
    """Withdraw-as-note on or off — clicked only when it isn't already, then checked."""
    for _ in range(2):
        if pixel_matches(*cfg.NOTES_CHECK) == on:
            return True
        _click(cfg.NOTES_BTN)
    return pixel_matches(*cfg.NOTES_CHECK) == on


def withdraw_noted(slot):
    """Bank open on the right tab: withdraw `slot` as notes, notes back off."""
    if not set_notes(True):
        say("[GE] Could not turn notes on.")
        return False
    _click(slot)
    if not set_notes(False):
        say("[GE] Could not turn notes off.")
        return False
    return True


def close_bank():
    close_interface(still_open=shows(cfg.BANK_CHECK))


# ── GE interface ──────────────────────────────────────────────────────────────

def open_ge():
    """Find the magenta GE clerk in GE_REGION, click, confirm the GE opened."""
    return open_interface(cfg.MAGENTA, cfg.MAGENTA_TOL, cfg.GE_REGION, cfg.GE_CHECK,
                          cfg.MAX_AGENT_TRIES, what="[GE] Exchange")


def _type_into(box, text):
    human_click(*jitter(*box))
    time.sleep(random.uniform(*BOX_FOCUS))
    human_typewrite(text)
    pyautogui.press("enter")
    _pause()


def sell(price=None):
    """GE open: offer the first inventory item at `price` (None: keep the GE's guide price)."""
    _click(cfg.SELL_SLOT, 0.4, 0.7)
    if price is not None:
        _type_into(cfg.PRICE_BTN, str(price))
    _click(cfg.CONFIRM_BTN, 0.5, 0.8)


def buy(item, quantity, price):
    """GE open: put in a buy offer for `quantity` × `item` at `price` each."""
    _click(cfg.BUY_BTN, 0.5, 0.8)
    human_typewrite(item)
    _pause(0.4, 0.7)
    _click(cfg.BUY_SEARCH_RESULT, 0.4, 0.7)
    _type_into(cfg.BUY_QUANTITY_BTN, str(quantity))
    _type_into(cfg.PRICE_BTN, str(price))
    _click(cfg.CONFIRM_BTN, 0.5, 0.8)


def wait_offer(timeout):
    """Wait up to `timeout` s for the offer to complete, then open it. O / P work."""
    x, y, rgb = cfg.OFFER_COMPLETE
    if not wait_for(lambda: pixel_matches(x, y, rgb, OFFER_TOL), timeout,
                    poll=lambda: random.uniform(1.5, 2.5)):
        return False
    _click((x, y))
    return True


def collect(both=False):
    """Collect the completed offer: slot 1 (coins / items), and slot 2 with `both`."""
    _click(cfg.RETRIEVE_SLOT_1, 0.4, 0.7)
    if both:
        _click(cfg.RETRIEVE_SLOT_2)


def close_ge():
    close_interface(still_open=shows(cfg.GE_CHECK))


# ── Following an offer that doesn't fill ───────────────────────────────────────

def _can_edit():
    return tuple(getattr(cfg, "EDIT_BTN", (0, 0))) != (0, 0)


def edit_offer(price, both):
    """Open slot 1's offer, collect what it has done so far, change its price to `price`.
    The game keeps the quantity still to go."""
    x, y, _ = cfg.OFFER_COMPLETE
    _click((x, y), 0.6, 0.9)
    collect(both)
    _click(cfg.EDIT_BTN, 0.5, 0.8)
    _type_into(cfg.PRICE_BTN, str(price))
    _click(cfg.CONFIRM_BTN, 0.5, 0.8)


def follow_offer(restock, side, price):
    """The `side` ("buy" / "sell") offer is in slot 1 at `price` (None: the GE's guide price):
    wait for it and collect. With re-pricing on (and EDIT_BTN calibrated), every
    reprice_minutes it hasn't completed: collect what it did, edit the price to reprice().
    Ends on the overview with everything collected. (True, None) or (False, reason)."""
    both = side == "buy"                 # a buy leaves items + change; a sell just coins
    item = restock.buy_item if side == "buy" else restock.sell_item
    shown = f"{price} gp" if price is not None else "guide price"
    if not restock.reprice_minutes or not _can_edit():
        if not wait_offer(restock.offer_timeout):
            return False, f"{side} offer never completed ({shown})"
        collect(both)
        return True, None

    for round_ in range(restock.reprice_rounds + 1):
        if wait_offer(restock.reprice_minutes * 60):
            collect(both)
            return True, None
        if round_ == restock.reprice_rounds:
            break
        quote = prices.latest(item, max_age=60) if restock.live_prices and item else None
        new, source = reprice(restock, price, quote, side)
        if new is None:
            say(f"[GE] {source} — the {side} stays at {shown}")
            continue
        say(f"[GE] {side.capitalize()} not complete after {restock.reprice_minutes} min — "
            f"collecting, price {shown} → {new} gp ({source})")
        edit_offer(new, both)
        price, shown = new, f"{new} gp"
    return False, f"{side} offer not complete after {restock.reprice_rounds} price edits ({shown})"


def offer_price(restock):
    """(price, source) for the buy — live when enabled — or (None, reason) above the cap."""
    return buy_offer_price(restock, prices.latest(restock.buy_item) if restock.live_prices else None)


def trade(restock):
    """GE open, the item to sell first in the inventory: sell it, buy `restock`,
    collect both. (True, None) or (False, reason)."""
    price, source = offer_price(restock)
    if price is None:
        return False, source
    quote = prices.latest(restock.sell_item) if restock.live_prices and restock.sell_item else None
    sell_at, sell_source = sell_offer_price(restock, quote)
    say(f"[GE] Selling {restock.sell_item or 'the first item'} at "
        f"{f'{sell_at} gp' if sell_at is not None else 'the guide price'} ({sell_source})")
    sell(sell_at)
    ok, why = follow_offer(restock, "sell", sell_at)
    if not ok:
        return False, why
    say(f"[GE] Buying {restock.quantity} x {restock.buy_item} at {price} gp ({source})")
    buy(restock.buy_item, restock.quantity, price)
    return follow_offer(restock, "buy", price)


# ── Tanner's restock trip ─────────────────────────────────────────────────────

def _teleport():
    """Ring of wealth → GE (left-click when swapped in RuneLite's Menu Entry Swapper)."""
    say("[GE] Teleporting to the GE")
    pyautogui.press("escape")
    _pause()
    pyautogui.press("f4")
    _pause(0.6, 1.0)
    if getattr(cfg, "RING_LEFT_CLICK_TP", False):
        human_click(*jitter(*cfg.RING_SLOT, n=3))
    else:
        _, _, mx, my = smart_right_click(*cfg.RING_SLOT, menu_scan_region=cfg.RING_MENU_REGION)
        _pause(0.35, 0.55)
        menu_click(mx + 5, my + cfg.MENU_HEADER + cfg.RING_MENU_ROW * cfg.MENU_ROW_H + cfg.MENU_ROW_H // 2)
    time.sleep(random.uniform(4.5, 5.5))   # the character lands in place: no walk to wait out


def run_ge_flow(restock):
    """Tanner's restock: teleport → bank (leather out, noted) → sell the leather, buy
    `restock` → deposit all. (True, None) or (False, reason). The bank positions are
    the bot's (restock.bank_tab / sell_slot / deposit_btn): the bank interface is the
    same at every bank, and deposit-all puts the hides back on their own slot (the bot
    withdraws all-but-1, so the stack never leaves the bank). The price is checked
    first, so one over the cap costs no ring teleport."""
    price, why = offer_price(restock)
    if price is None:
        return False, why

    _teleport()
    for attempt in range(cfg.GE_MAX_RETRIES):    # a retry turns the camera again, never re-teleports
        face("west", cfg)
        if open_bank(cfg.GE_APPROACH_REGION):
            break
        say(f"[GE] Banker not found — retrying ({attempt + 1}/{cfg.GE_MAX_RETRIES})...")
    else:
        return False, "banker not found at the GE"

    _click(restock.bank_tab)
    if not withdraw_noted(restock.sell_slot):
        return False, "notes toggle didn't respond"
    close_bank()

    if not open_ge():
        return False, "could not open the GE"
    ok, why = trade(restock)
    if not ok:
        return False, why
    close_ge()

    if not open_bank(cfg.GE_REGION):
        return False, "could not open the bank after the GE"
    _click(restock.deposit_btn, 0.6, 0.9)
    close_bank()
    say("[GE] Restock complete.")
    return True, None
