"""
Live GE prices from the OSRS Wiki real-time prices API (prices.runescape.wiki —
RuneLite's GE trade data). Used by lib.ge to price restock offers.

- quote(name) → {"high", "low"}: the latest instant-buy / instant-sell trade, plus
  {"avg_high", "avg_low"}: their averages over the last finished hour (any of them
  None when there was no such trade). None if the item is unknown or the API can't
  be reached — the caller then falls back. Never raises. Cached for CACHE_SECONDS.
- buy_price / sell_price are the pure part: instant-buy + 1 gp / instant-sell - 1 gp.
  A new offer goes by the hour's average (steadier than one trade — an item that
  trades in bursts can have a latest price minutes old and far off); a re-price
  (latest=True) by the latest trade, since an offer that sat unfilled means the
  average is out of date.

The API asks for a descriptive User-Agent (generic ones get blocked) and no tight
polling — two small requests per item per check is well inside that.
"""
import json, time, urllib.parse, urllib.request

API            = "https://prices.runescape.wiki/api/v1/osrs"
USER_AGENT     = "runetools GE restock (github.com/proofexak/runetools)"
TIMEOUT        = 5.0
CACHE_SECONDS  = 300
AVG_LOOKBACK   = 3      # hours back to look for an average when the last hour had no trade

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


def hour_average(series, lookback=AVG_LOOKBACK):
    """(avg_high, avg_low) from a /timeseries?timestep=1h list (oldest first): each from
    the newest of the last `lookback` hours that had such a trade."""
    recent = series[-lookback:][::-1]
    high = next((p["avgHighPrice"] for p in recent if p.get("avgHighPrice")), None)
    low = next((p["avgLowPrice"] for p in recent if p.get("avgLowPrice")), None)
    return high, low


def quote(name, opener=None, clock=time.monotonic, max_age=CACHE_SECONDS):
    """{"high", "low", "avg_high", "avg_low"} for `name`, or None if unknown/unreachable.
    A cached quote younger than `max_age` seconds is reused."""
    iid = item_id(name, opener)
    if iid is None:
        return None
    hit = _cache.get(iid)
    if hit and clock() - hit[0] < max_age:
        return hit[1]
    try:
        last = _get_json(f"latest?{urllib.parse.urlencode({'id': iid})}", opener)["data"].get(str(iid)) or {}
        series = _get_json(f"timeseries?{urllib.parse.urlencode({'timestep': '1h', 'id': iid})}",
                           opener).get("data") or []
    except Exception as e:
        print(f"  [prices] {name}: price unavailable: {e!r}")
        return None
    avg_high, avg_low = hour_average(series)
    q = {"high": last.get("high"), "low": last.get("low"), "avg_high": avg_high, "avg_low": avg_low}
    if not any(q.values()):
        return None
    _cache[iid] = (clock(), q)
    return q


_LABEL = {"high": "latest buy", "low": "latest sell", "avg_high": "1h avg buy", "avg_low": "1h avg sell"}


def _base(q, side, latest):
    """(key, price) a buy ("high") / sell ("low") goes by: the hour's average, or with
    `latest` the latest trade — each falling back to the other, then to the other side."""
    other = "low" if side == "high" else "high"
    pair = lambda s: (s, "avg_" + s) if latest else ("avg_" + s, s)
    return next(((k, q[k]) for k in pair(side) + pair(other) if q.get(k)), (None, None))


def buy_price(q, latest=False):
    """(price, what it's based on) to buy at: instant-buy + 1 gp; (None, None) without a quote."""
    key, base = _base(q, "high", latest) if q else (None, None)
    return (base + 1, f"{_LABEL[key]} {base} +1") if base else (None, None)


def sell_price(q, latest=False):
    """(price, what it's based on) to sell at: instant-sell - 1 gp, at least 1."""
    key, base = _base(q, "low", latest) if q else (None, None)
    return (max(1, base - 1), f"{_LABEL[key]} {base} -1") if base else (None, None)
