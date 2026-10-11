"""
Grand Exchange — the building blocks every bot's restock uses, plus the restock trip
tanner and choc both make (run_ge_flow).

Building blocks (positions from lib/ge_config.py, the GE interface is the same for
every bot): open_bank / open_ge, withdraw_noted, sell / buy / wait_offer / collect,
edit_offer, follow_offer (edits the price of an offer that sits unfilled), and
trade(), which sells an inventory item then buys a lib.restock.Restock.
What to buy, how many and at what price is the bot's, not this module's.
"""
import time, random

import pyautogui

from lib.mouse     import smart_right_click, human_click, human_move, menu_click, jitter, human_typewrite, human_press
from lib.screen    import pixel_matches, grab
import lib.vision    as vision
from lib.interface import open_interface, close_interface, wait_for, shows
from lib.camera    import face
from lib.log       import say
from lib.restock   import buy_offer_price, sell_offer_price, reprice
import lib.prices    as prices
import lib.ge_config as cfg
import lib.human as human

# The price / quantity box is a popup that needs a moment to open and take focus —
# typed too early, the digits and the Enter go to public chat instead.
BOX_FOCUS = (0.7, 1.0)
OFFER_TOL = 30    # the "complete" pixel varied by 17 in one channel while genuinely complete
# The game logs out after 5 minutes without input — and an offer can sit for longer than
# that. Moving the cursor inside the game window resets the timer (OSRS Wiki, "Idle"), so a
# wait nudges it now and then: skewed 45-150 s gaps, never more than KEEP_AWAKE_MAX.
KEEP_AWAKE = (45, 150)
KEEP_AWAKE_MAX = 270
# The edit pencil shows "Please wait..." for 1-2 s before the set-up screen — and from that
# click until Confirm, the offer is withdrawn. Clicks during the wait do nothing.
EDIT_LOAD = (2.5, 3.5)
# Spread of a click's random offset: ±8 px for big targets, ±3 for the ~20 px icon buttons
# (the edit pencil, the price "..." button).
SMALL = 3


def _pause(lo=0.3, hi=0.5):
    human.sleep(lo, hi)


def _click(point, lo=0.3, hi=0.5, spread=8):
    human_click(*jitter(*point, n=spread))
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


def stack_shown(region):
    """Bank open: does the stack under `region` (the corner its count is drawn in) show a
    count? True = 2 or more, False = 1 or none, None = no region to read."""
    if not region or region[2] <= 0 or region[3] <= 0:
        return None
    frame, _ = grab(region)
    return vision.stack_number_shown(frame)


# ── GE interface ──────────────────────────────────────────────────────────────

def open_ge():
    """Find the magenta GE clerk in GE_REGION, click, confirm the GE opened."""
    return open_interface(cfg.MAGENTA, cfg.MAGENTA_TOL, cfg.GE_REGION, cfg.GE_CHECK,
                          cfg.MAX_AGENT_TRIES, what="[GE] Exchange")


def _type_into(box, text, spread=8):
    human_click(*jitter(*box, n=spread))
    human.sleep(*BOX_FOCUS)
    human_typewrite(text)
    human_press("enter")
    _pause()


def sell(inv_slot, price=None):
    """GE open: click the item in inventory slot `inv_slot` — that opens its sell offer with
    the quantity already at all — and offer it at `price` (None: keep the GE's guide price)."""
    _click(inv_slot, 0.4, 0.7)
    if price is not None:
        _type_into(cfg.PRICE_BTN, str(price), spread=SMALL)
    _click(cfg.CONFIRM_BTN, 0.5, 0.8)


def buy(item, quantity, price):
    """GE open: put in a buy offer for `quantity` × `item` at `price` each."""
    _click(cfg.BUY_BTN, 0.5, 0.8)
    human_typewrite(item)
    _pause(0.4, 0.7)
    _click(cfg.BUY_SEARCH_RESULT, 0.4, 0.7)
    _type_into(cfg.BUY_QUANTITY_BTN, str(quantity), spread=SMALL)
    _type_into(cfg.PRICE_BTN, str(price), spread=SMALL)
    _click(cfg.CONFIRM_BTN, 0.5, 0.8)


def next_nudge(rng=random):
    """Seconds until the next keep_awake(): skewed, never past KEEP_AWAKE_MAX."""
    return min(KEEP_AWAKE_MAX, human.delay(*KEEP_AWAKE, rng, human.active()))


def keep_awake(rng=random):
    """Input that changes nothing: the cursor drifts 8-47 px from where it rests (no click,
    no keys), so a long wait doesn't end in the 5-minute idle logout."""
    x, y = pyautogui.position()
    while True:
        dx, dy = rng.randint(-40, 40), rng.randint(-25, 25)
        if dx * dx + dy * dy >= 64:
            break
    human_move(x + dx, y + dy)


def wait_offer(timeout):
    """Wait up to `timeout` s for the offer to complete, then open it. O / P work, and
    keep_awake() nudges the cursor every next_nudge() seconds meanwhile."""
    x, y, rgb = cfg.OFFER_COMPLETE
    next_tap = [time.time() + next_nudge()]

    def complete():
        if time.time() >= next_tap[0]:
            keep_awake()
            next_tap[0] = time.time() + next_nudge()
        return pixel_matches(x, y, rgb, OFFER_TOL)

    if not wait_for(complete, timeout, poll=lambda: random.uniform(1.5, 2.5)):
        return False
    _click((x, y))
    return True


def collect(both=False):
    """Collect the offer: slot 1 (coins / items), with `both` slot 2 (a buy's change) first.
    Slot 2 first: the click that empties the offer closes its view, and a click after it
    would land on the overview (slot 8's Sell button sits where slot 2 is). An empty slot's
    click does nothing."""
    if both:
        _click(cfg.RETRIEVE_SLOT_2)
    _click(cfg.RETRIEVE_SLOT_1, 0.4, 0.7)


def close_ge():
    close_interface(still_open=shows(cfg.GE_CHECK))


# ── Following an offer that doesn't fill ───────────────────────────────────────

def _can_edit():
    return tuple(getattr(cfg, "EDIT_BTN", (0, 0))) != (0, 0)


def edit_offer(price, both):
    """Open slot 1's offer, collect what it has done so far, change its price to `price`.
    The game keeps the quantity still to go. Collecting sends the GE back to the overview,
    so the offer is opened again before the pencil (with nothing to collect it stays open,
    and that click lands harmlessly on its "Quantity" label)."""
    x, y, _ = cfg.OFFER_COMPLETE
    _click((x, y), 0.6, 0.9)
    collect(both)
    _click((x, y), 0.6, 0.9)
    _click(cfg.EDIT_BTN, *EDIT_LOAD, spread=SMALL)       # "Please wait..." — then the set-up screen
    _type_into(cfg.PRICE_BTN, str(price), spread=SMALL)
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
        quote = prices.quote(item, max_age=60) if restock.live_prices and item else None
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
    return buy_offer_price(restock, prices.quote(restock.buy_item) if restock.live_prices else None)


def trade(restock, sell_first=True):
    """GE open: sell the item in inventory slot restock.sell_inv_slot (unless not
    `sell_first`: nothing to sell, buy with the coins carried), buy `restock`, collect.
    (True, None) or (False, reason)."""
    if sell_first and not restock.sell_inv_slot:
        return False, "no inventory slot for the item to sell (SELL_INV_SLOT)"
    price, source = offer_price(restock)
    if price is None:
        return False, source
    if sell_first:
        quote = prices.quote(restock.sell_item) if restock.live_prices and restock.sell_item else None
        sell_at, sell_source = sell_offer_price(restock, quote)
        say(f"[GE] Selling {restock.sell_item or 'the first item'} at "
            f"{f'{sell_at} gp' if sell_at is not None else 'the guide price'} ({sell_source})")
        sell(restock.sell_inv_slot, sell_at)
        ok, why = follow_offer(restock, "sell", sell_at)
        if not ok:
            return False, why
    say(f"[GE] Buying {restock.quantity} x {restock.buy_item} at {price} gp ({source})")
    buy(restock.buy_item, restock.quantity, price)
    return follow_offer(restock, "buy", price)


# ── The restock trip (tanner, choc) ───────────────────────────────────────────

def _teleport():
    """Ring of wealth → GE (left-click when swapped in RuneLite's Menu Entry Swapper)."""
    say("[GE] Teleporting to the GE")
    human_press("escape")
    _pause()
    human_press("f4")
    _pause(0.6, 1.0)
    if getattr(cfg, "RING_LEFT_CLICK_TP", False):
        human_click(*jitter(*cfg.RING_SLOT, n=3))
    else:
        _, _, mx, my = smart_right_click(*cfg.RING_SLOT, menu_scan_region=cfg.RING_MENU_REGION)
        _pause(0.35, 0.55)
        menu_click(mx + 5, my + cfg.MENU_HEADER + cfg.RING_MENU_ROW * cfg.MENU_ROW_H + cfg.MENU_ROW_H // 2)
    human.sleep(4.5, 5.5)   # the character lands in place: no walk to wait out


def run_ge_flow(restock, teleport=True, bank_open=False):
    """A bot's restock: teleport → bank (the item to sell out, noted) → sell it, buy
    `restock` → deposit all (→ withdraw restock.withdraw_slot, if set). (True, None) or
    (False, reason). The bank positions are the bot's (restock.bank_tab / sell_slot /
    deposit_btn / withdraw_slot): the bank interface is the same at every bank, and
    deposit-all puts the hides back on their own slot (tanner withdraws all-but-1, so the
    stack never leaves the bank). The price is checked first, so one over the cap costs no
    ring teleport. teleport=False: already at the GE (tanner started there; choc grinds
    there) — the banker is looked for around the GE centre (GE_REGION) instead of where
    the teleport lands (GE_APPROACH_REGION), and the camera isn't turned (nothing moved it)
    unless the banker needs a second look. bank_open: the GE bank is already open
    (tanner's GE start read the hide count there) — one bank visit, not two."""
    price, why = offer_price(restock)
    if price is None:
        return False, why

    if teleport:
        _teleport()
    region = cfg.GE_APPROACH_REGION if teleport else cfg.GE_REGION
    for attempt in range(0 if bank_open else cfg.GE_MAX_RETRIES):
        if teleport or attempt:                  # the teleport turns the camera; a retry looks again
            face("west", cfg)
        if open_bank(region):
            break
        say(f"[GE] Banker not found — retrying ({attempt + 1}/{cfg.GE_MAX_RETRIES})...")
    else:
        if not bank_open:
            return False, "banker not found at the GE"

    _click(restock.bank_tab)
    # the tab just clicked shows RuneLite's "View tab" tooltip right over the leather's count box
    # (its white text reads as a count): rest the mouse on Deposit, whose tooltip is far away
    human_move(*jitter(*restock.deposit_btn, n=SMALL))
    _pause(0.4, 0.6)
    # no count on the leather stack = 1 or none left (all-but-1): nothing to sell, only buy
    sell_first = stack_shown(restock.sell_count_region) is not False
    if not sell_first:
        say(f"[GE] No {restock.sell_item or 'item'} to sell — buying only.")
    elif not withdraw_noted(restock.sell_slot):
        return False, "notes toggle didn't respond"
    close_bank()

    if not open_ge():
        return False, "could not open the GE"
    ok, why = trade(restock, sell_first)
    if not ok:
        return False, why
    close_ge()

    if not open_bank(cfg.GE_REGION):
        return False, "could not open the bank after the GE"
    _click(restock.deposit_btn, 0.6, 0.9)
    if restock.withdraw_slot:            # the bank reopens on bank_tab, the tab it was left on
        _click(restock.withdraw_slot, 0.4, 0.6)
    close_bank()
    say("[GE] Restock complete.")
    return True, None
