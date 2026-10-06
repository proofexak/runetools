"""
Live GE prices from the OSRS Wiki real-time prices API (prices.runescape.wiki —
RuneLite's GE trade data). Used by lib.ge to price restock offers.

- latest(name) → {"high": instant-buy, "low": instant-sell} or None. Never raises:
  no network / slow API / unknown item → None, and the caller falls back to its
  config price. One small request per item, cached for CACHE_SECONDS.
- buy_price is the pure part: quote + margin → offer price. (Sells stay at 1 gp: a GE
  trade goes through at the price of the offer that was already waiting, so dumping
  at 1 still gets the best buyer's price — and the same way an overpaying buy pays
  the seller's price. The live price is what keeps a buy above the market.)

The API asks for a descriptive User-Agent (generic ones get blocked) and no tight
polling — one fetch per restock is well inside that.
"""
import json, math, time, urllib.parse, urllib.request

API            = "https://prices.runescape.wiki/api/v1/osrs"
USER_AGENT     = "runetools GE restock (github.com/proofexak/runetools)"
TIMEOUT        = 5.0
CACHE_SECONDS  = 300

# Items the bots trade — skips downloading /mapping (~4.7k items) for them.
ITEM_IDS = {
    "green dragonhide": 1753, "green dragon leather": 1745,
    "blue dragonhide":  1751, "blue dragon leather":  2505,
    "red dragonhide":   1749, "red dragon leather":   2507,
    "black dragonhide": 1747, "black dragon leather": 2509,
    "chocolate bar":    1973, "chocolate dust":       1975,
}

_mapping = None    # name (lower) → id, from /mapping, for names not in ITEM_IDS
_cache = {}        # id → (fetched_at, quote)


def _get_json(path, opener=None):
    req = urllib.request.Request(f"{API}/{path}", headers={"User-Agent": USER_AGENT})
    with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT) as res:
        return json.loads(res.read().decode("utf-8"))


def item_id(name, opener=None):
    """GE item id for `name` (case-insensitive), or None."""
    global _mapping
    key = name.strip().lower()
    if key in ITEM_IDS:
        return ITEM_IDS[key]
    if _mapping is None:
        try:
            _mapping = {i["name"].lower(): i["id"] for i in _get_json("mapping", opener)}
        except Exception as e:
            print(f"  [prices] item list unavailable: {e!r}")
            return None
    return _mapping.get(key)


def latest(name, opener=None, clock=time.monotonic, max_age=CACHE_SECONDS):
    """{"high": int|None, "low": int|None} for `name`, or None if unknown/unreachable.
    A cached quote younger than `max_age` seconds is reused."""
    iid = item_id(name, opener)
    if iid is None:
        return None
    hit = _cache.get(iid)
    if hit and clock() - hit[0] < max_age:
        return hit[1]
    try:
        data = _get_json(f"latest?{urllib.parse.urlencode({'id': iid})}", opener)["data"].get(str(iid))
    except Exception as e:
        print(f"  [prices] {name}: price unavailable: {e!r}")
        return None
    if not data or (data.get("high") is None and data.get("low") is None):
        return None
    quote = {"high": data.get("high"), "low": data.get("low")}
    _cache[iid] = (clock(), quote)
    return quote


def buy_price(quote, margin):
    """Instant-buy price plus `margin` (0.05 = 5 %), rounded up; None without a quote."""
    base = quote and (quote.get("high") or quote.get("low"))
    return math.ceil(base * (1 + margin)) if base else None

