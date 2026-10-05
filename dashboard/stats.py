"""
Dashboard numbers from session summaries (lib.logreport.summarize). Pure: takes
summaries + "now", returns JSON-able dicts.

Only a session's total active time is logged, so a session that spans midnight
is split across days in proportion to its wall-clock time on each day (pauses
are assumed spread evenly). Runs are split the same way.
"""
from datetime import datetime, timedelta

LIVE_WINDOW = 15 * 60   # s: an unfinished session with an event this recent counts as running
UNASSIGNED = ""         # account key for sessions logged before tagging / with no active account


def _dt(ts):
    return datetime.fromisoformat(ts)


def account_of(summary):
    return summary.get("account") or UNASSIGNED


def day_shares(start, end):
    """[(date, fraction of the session's wall time on that date)]."""
    if end <= start:
        return [(start.date(), 1.0)]
    total = (end - start).total_seconds()
    out, cur = [], start
    while cur < end:
        nxt = min(datetime.combine(cur.date() + timedelta(days=1), datetime.min.time()), end)
        out.append((cur.date(), (nxt - cur).total_seconds() / total))
        cur = nxt
    return out


def is_live(summary, now):
    return summary["final"] == "killed" and (now - _dt(summary["end"])).total_seconds() <= LIVE_WINDOW


def daily(summaries, first_day, last_day):
    """{iso date: {"hours", "runs", "bots": {bot: hours}}} for every day in range."""
    days = {}
    d = first_day
    while d <= last_day:
        days[d.isoformat()] = {"hours": 0.0, "runs": 0.0, "bots": {}}
        d += timedelta(days=1)
    for s in summaries:
        for day, share in day_shares(_dt(s["start"]), _dt(s["end"])):
            row = days.get(day.isoformat())
            if row is None:
                continue
            hours = s["active_seconds"] * share / 3600
            row["hours"] += hours
            row["runs"] += s["runs"] * share
            bot = s["bot"] or "?"
            row["bots"][bot] = row["bots"].get(bot, 0.0) + hours
    return days


def _session_row(s, now):
    return {"session": s["session"], "bot": s["bot"], "account": account_of(s),
            "start": s["start"], "end": s["end"],
            "final": "running" if is_live(s, now) else s["final"],
            "reason": s["reason"] or (f"after {s['last_step']}" if s["last_step"] else None),
            "active_hours": s["active_seconds"] / 3600, "runs": s["runs"],
            "errors": len(s["errors"])}


def live(summaries, now):
    """Sessions running right now (newest first)."""
    rows = []
    for s in reversed(summaries):
        if is_live(s, now):
            row = _session_row(s, now)
            row["state"] = s["last_step"]
            row["idle_seconds"] = (now - _dt(s["end"])).total_seconds()
            rows.append(row)
    return rows


def overview(summaries, now, days=14, recent=25):
    """Everything one account view needs; summaries already filtered to it."""
    today = now.date()
    by_day = daily(summaries, today - timedelta(days=days - 1), today)
    week = [by_day[(today - timedelta(days=i)).isoformat()] for i in range(7)]
    week_start = datetime.combine(today - timedelta(days=6), datetime.min.time())
    t = by_day[today.isoformat()]
    return {
        "today": {"hours": t["hours"], "runs": round(t["runs"]), "bots": t["bots"],
                  "sessions": sum(1 for s in summaries if _dt(s["end"]).date() >= today)},
        "week": {"hours": sum(d["hours"] for d in week), "runs": round(sum(d["runs"] for d in week)),
                 "crashes": sum(1 for s in summaries
                                if s["final"] == "crashed" and _dt(s["start"]) >= week_start)},
        "total_hours": sum(s["active_seconds"] for s in summaries) / 3600,
        "daily": [{"date": k, **v} for k, v in by_day.items()],
        "live": live(summaries, now),
        "recent": [_session_row(s, now) for s in reversed(summaries[-recent:])],
    }


def build(summaries, accounts, now):
    """{"accounts": [...], "views": {key: overview}}; "*" = all accounts.
    Accounts seen only in logs (renamed/deleted) still get a view."""
    known = [a["name"] for a in accounts]
    seen = {account_of(s) for s in summaries}
    keys = known + sorted(k for k in seen if k not in known and k != UNASSIGNED)
    views = {"*": overview(summaries, now)}
    for key in keys + ([UNASSIGNED] if UNASSIGNED in seen else []):
        views[key] = overview([s for s in summaries if account_of(s) == key], now)
    return {"accounts": keys, "unassigned": UNASSIGNED in seen, "views": views,
            "now": now.isoformat(timespec="seconds")}

