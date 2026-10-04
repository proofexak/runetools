"""
Session report from the structured event logs (see lib/events.py).

    python -m lib.logreport                      # recent sessions (default)
    python -m lib.logreport sessions --bot tanner --last 50
    python -m lib.logreport session latest       # one session in detail, incl. tracebacks
    python -m lib.logreport session 20260930_210455
    python -m lib.logreport stats --since 2026-09-01
    python -m lib.logreport supervisor --last 30 # unattended-mode events (log/launcher.jsonl)

parse_lines / summarize / aggregate are pure; main() only finds files and prints.
"""
import argparse, glob, json, os, sys
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Step results that mean "this step failed". Other non-"ok" results ("full",
# "restock", ...) are normal routing and only show in the per-session timeline.
FAILURE_RESULTS = {"fail", "not_found"}
MIN_RATE_SECONDS = 60   # runs/hour isn't shown for shorter sessions


# ── Pure core ─────────────────────────────────────────────────────────────────

def parse_lines(lines):
    """JSON-lines -> (events, number of unusable lines). Blank lines are ignored;
    a line cut short by a hard kill, or one without an "event", counts as bad."""
    events, bad = [], 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(record, dict) and "event" in record:
            events.append(record)
        else:
            bad += 1
    return events, bad


def _ts(event):
    return datetime.fromisoformat(event["ts"])


def summarize(events):
    """One session's events (file order) -> summary dict. No session_end means
    the process was killed: final "killed", times taken from the last event."""
    first = events[0]
    start = next((e for e in events if e["event"] == "session_start"), first)
    end = next((e for e in reversed(events) if e["event"] == "session_end"), None)
    steps = [e for e in events if e["event"] == "step"]
    pauses = [e for e in events if e["event"] == "pause"]

    state_time, state_counts = {}, {}
    for s in steps:
        state_time[s["state"]] = state_time.get(s["state"], 0.0) + s.get("seconds", 0.0)
        state_counts[s["state"]] = state_counts.get(s["state"], 0) + 1

    if end is not None:
        active = end.get("active_seconds", 0.0)
        paused = end.get("paused_seconds", 0.0)
        runs = (end.get("stats") or {}).get("run") or 0
    else:
        paused = sum(p.get("seconds", 0.0) for p in pauses)
        active = (_ts(events[-1]) - _ts(start)).total_seconds() - paused
        runs = (steps[-1].get("run") if steps else 0) or 0

    return {
        "session": first.get("session"), "bot": first.get("bot"),
        "start": start["ts"], "params": start.get("params", {}),
        "final": end["final"] if end else "killed",
        "reason": end.get("reason") if end else None,
        "last_step": end.get("last_step") if end else (steps[-1]["state"] if steps else None),
        "active_seconds": active, "paused_seconds": paused,
        "runs": runs, "runs_per_hour": runs / (active / 3600) if active > 0 else 0.0,
        "errors": [e for e in events if e["event"] == "error"],
        "state_time": state_time, "state_counts": state_counts,
        "non_ok": [(s["ts"], s["state"], s.get("result")) for s in steps if s.get("result") != "ok"],
        "pauses": len(pauses),
        "recoveries": sum(1 for s in steps if s["state"] == "recover"),
    }


def aggregate(summaries):
    """Session summaries -> long-term stats per bot."""
    out = {}
    for bot in sorted({s["bot"] for s in summaries}):
        mine = [s for s in summaries if s["bot"] == bot]
        hours = sum(s["active_seconds"] for s in mine) / 3600
        runs = sum(s["runs"] for s in mine)
        steps, failed = Counter(), Counter()
        for s in mine:
            steps.update(s["state_counts"])
            failed.update(state for _, state, result in s["non_ok"] if result in FAILURE_RESULTS)
        out[bot] = {
            "sessions": len(mine),
            "active_hours": hours,
            "runs": runs,
            "runs_per_hour": runs / hours if hours > 0 else 0.0,
            "finals": Counter(s["final"] for s in mine),
            "reasons": Counter(s["reason"] for s in mine if s["reason"]),
            "failures_by_state": {st: (n, n / steps[st] if steps[st] else 0.0) for st, n in failed.items()},
            "recoveries_per_hour": sum(s["recoveries"] for s in mine) / hours if hours > 0 else 0.0,
            "crash_types": Counter(e["type"] for s in mine for e in s["errors"]),
        }
    return out


# ── Files + printing ──────────────────────────────────────────────────────────

def _hms(seconds):
    seconds = int(max(0, seconds))
    return f"{seconds // 3600:d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def load_sessions(root):
    """(summaries sorted by start, unusable line count, launcher error events)."""
    summaries, bad = [], 0
    paths = glob.glob(os.path.join(root, "*", "log", "*.jsonl")) + \
        glob.glob(os.path.join(root, "*", "*", "log", "*.jsonl"))
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as f:
            events, n = parse_lines(f)
        bad += n
        if events:
            summaries.append(summarize(events))
    launcher = []
    lpath = os.path.join(root, "log", "launcher.jsonl")
    if os.path.exists(lpath):
        with open(lpath, encoding="utf-8", errors="replace") as f:
            launcher, n = parse_lines(f)
        bad += n
    return sorted(summaries, key=lambda s: s["start"]), bad, launcher


def _print_sessions(summaries, last):
    print(f"{'start':19s} {'bot':15s} {'active':>8s} {'paused':>8s} {'final':11s} "
          f"{'runs':>5s} {'runs/h':>7s} {'err':>3s}  reason / last step")
    for s in summaries[-last:]:
        why = s["reason"] or f"after {s['last_step']}"
        rate = f"{s['runs_per_hour']:.1f}" if s["active_seconds"] >= MIN_RATE_SECONDS else "-"
        print(f"{s['start'][:19]:19s} {s['bot'] or '?':15s} {_hms(s['active_seconds']):>8s} "
              f"{_hms(s['paused_seconds']):>8s} {s['final']:11s} {s['runs']:>5} "
              f"{rate:>7s} {len(s['errors']):>3}  {why}")


def _print_session(s):
    print(f"Session {s['session']}  bot={s['bot']}  started {s['start']}")
    print(f"  params: {json.dumps(s['params'])}")
    print(f"  ended:  {s['final']}" + (f" — {s['reason']}" if s["reason"] else "")
          + f" (last step: {s['last_step']})")
    rate = f"{s['runs_per_hour']:.1f}/h" if s["active_seconds"] >= MIN_RATE_SECONDS else "-/h"
    print(f"  active {_hms(s['active_seconds'])}, paused {_hms(s['paused_seconds'])} "
          f"in {s['pauses']} pause(s); runs {s['runs']} ({rate}); "
          f"recoveries {s['recoveries']}")
    print("  time per state:")
    for state, secs in sorted(s["state_time"].items(), key=lambda kv: -kv[1]):
        print(f"    {state:20s} {_hms(secs):>8s}  x{s['state_counts'][state]}")
    if s["non_ok"]:
        print("  non-ok results:")
        for ts, state, result in s["non_ok"]:
            print(f"    {ts[11:19]}  {state} -> {result}")
    for e in s["errors"]:
        print(f"  ERROR ({e.get('where')}) in {e.get('state')}: {e.get('type')}: {e.get('message')}")
        for line in (e.get("traceback") or "").rstrip().splitlines():
            print(f"    {line}")


def _print_stats(agg, launcher):
    for bot, a in agg.items():
        print(f"== {bot}: {a['sessions']} session(s), {a['active_hours']:.2f} active h, "
              f"{a['runs']} runs ({a['runs_per_hour']:.1f}/h), "
              f"{a['recoveries_per_hour']:.2f} recoveries/h")
        print("   ends:    " + ", ".join(f"{k} {v}" for k, v in a["finals"].most_common()))
        if a["reasons"]:
            print("   reasons: " + ", ".join(f"{k} ({v})" for k, v in a["reasons"].most_common(5)))
        for state, (n, rate) in sorted(a["failures_by_state"].items(), key=lambda kv: -kv[1][0]):
            print(f"   fails:   {state} {n}x ({rate:.0%} of runs of that step)")
        if a["crash_types"]:
            print("   crashes: " + ", ".join(f"{k} ({v})" for k, v in a["crash_types"].most_common()))
    print(f"Launcher errors: {len(launcher)}")
    for e in launcher[-5:]:
        print(f"   {e['ts'][:19]}  {e.get('bot') or '-'}  {e.get('where')}: {e.get('type')}: {e.get('message')}")


def _print_supervisor(launcher, last):
    events = [e for e in launcher if e["event"] != "error" or e.get("where") == "headless"]
    if not events:
        print("No supervisor events logged yet.")
        return
    skip = {"ts", "session", "bot", "event", "traceback"}
    for e in events[-last:]:
        details = "  ".join(f"{k}={e[k]}" for k in e if k not in skip and e[k] is not None)
        print(f"{e['ts'][:19].replace('T', ' ')}  {e.get('bot') or '-':12s} {e['event']:16s} {details}")


def main(argv=None, root=None):
    root = root or ROOT
    p = argparse.ArgumentParser(prog="python -m lib.logreport", description="Bot session report")
    sub = p.add_subparsers(dest="cmd")
    ps = sub.add_parser("sessions", help="one row per session (default)")
    ps.add_argument("--bot"); ps.add_argument("--last", type=int, default=20)
    p1 = sub.add_parser("session", help="one session in detail")
    p1.add_argument("id", help="session id (YYYYMMDD_HHMMSS) or 'latest'"); p1.add_argument("--bot")
    pst = sub.add_parser("stats", help="long-term stats per bot")
    pst.add_argument("--bot"); pst.add_argument("--since", help="YYYY-MM-DD")
    psv = sub.add_parser("supervisor", help="unattended-mode supervisor events")
    psv.add_argument("--last", type=int, default=30)
    args = p.parse_args(argv)

    summaries, bad, launcher = load_sessions(root)
    if getattr(args, "bot", None):
        summaries = [s for s in summaries if s["bot"] == args.bot]
    if bad:
        print(f"({bad} unreadable log line(s) skipped)")

    if args.cmd == "supervisor":
        _print_supervisor(launcher, args.last)
    elif args.cmd == "session":
        chosen = summaries[-1:] if args.id == "latest" else [s for s in summaries if s["session"] == args.id]
        if not chosen:
            print("No such session.")
            return 1
        _print_session(chosen[-1])
    elif args.cmd == "stats":
        if args.since:
            since = args.since.replace("-", "")
            summaries = [s for s in summaries if (s["session"] or "") >= since]
        _print_stats(aggregate(summaries), launcher)
    else:
        if not summaries:
            print("No sessions logged yet.")
        else:
            _print_sessions(summaries, getattr(args, "last", 20))
    return 0


if __name__ == "__main__":
    sys.exit(main())
