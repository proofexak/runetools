"""
Live check for re-pricing an offer (lib.ge.follow_offer) on its own — spends a little gp.

Puts in a buy too low to fill, so the first re-price has to open it, collect, edit the
price up to the live price + margin, which should then fill. Needs the GE open on the
overview, slot 1 empty, coins in the inventory, and EDIT_BTN calibrated (GE Config →
Re-price → Edit Offer Button).

    .venv/bin/python -m lib.checks.follow_offer [item] [quantity] [start price] [minutes]

Defaults: 100 feather at 1 gp, re-priced every 1 minute, 3 rounds. P stops it.
"""
import sys, time


def main():
    import lib.pause as pause
    import lib.ge as ge
    from lib.restock import Restock

    item = sys.argv[1] if len(sys.argv) > 1 else "feather"
    qty = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    start = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    minutes = float(sys.argv[4]) if len(sys.argv) > 4 else 1
    if not ge._can_edit():
        print("EDIT_BTN isn't calibrated yet — GE Config → Re-price → Edit Offer Button.")
        raise SystemExit(1)

    r = Restock(buy_item=item, quantity=qty, buy_price=start, max_price=0, live_prices=True,
                margin_pct=5, offer_timeout=60, reprice_minutes=minutes, reprice_rounds=3)
    pause.setup()
    print(f"Buying {qty} x {item} at {start} gp, re-pricing every {minutes} min — switch to the "
          f"game, starting in 5 s. P stops.")
    time.sleep(5)
    ge.buy(item, qty, start)
    try:
        print(ge.follow_offer(r, "buy", start))
    except pause.ForceStop:
        print("Stopped (P) — check GE slot 1 by hand.")


if __name__ == "__main__":
    main()
