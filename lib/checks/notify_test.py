"""
Live check for lib/notify.py: does a phone alert reach Discord, with a screenshot?

Set the webhook first (README "Phone alerts"): lib/notify_config.py (copy notify_config.example.py),
or NOTIFY_DISCORD_WEBHOOK / NOTIFY_DISCORD_USER_ID in the environment (docker/.env in the container).
Then, with the game on screen:

    .venv/bin/python -m lib.checks.notify_test
    docker/botctl <account> compose exec runetools python3 -m lib.checks.notify_test   # in the container

It sends one test alert and prints how it went (the `notify` / `notify_error` event it logged to
log/launcher.jsonl). Pass: the post says 200, your phone buzzed (with DISCORD_USER_ID set), and
the message shows the screenshot.
"""
import json
import os
import socket
import time


def _last_notify_event(path, since):
    try:
        with open(path, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if '"notify' in l]
    except OSError:
        return None
    lines = [e for e in lines if e.get("ts", "") >= since]
    return lines[-1] if lines else None


def main():
    import lib.accounts as accounts
    import lib.events as events
    import lib.notify as notify

    s = notify.settings()
    if not s.url:
        print("No webhook set: lib/notify_config.py DISCORD_WEBHOOK_URL (copy notify_config.example.py)\n"
              f"or {notify.ENV_WEBHOOK} in the environment. Nothing sent.")
        return 1
    print(f"Webhook set ({'env' if os.environ.get(notify.ENV_WEBHOOK) else 'lib/notify_config.py'}); "
          f"user id {'set' if s.user_id.isdigit() else 'NOT set — no @mention, your phone may not buzz'}; "
          f"screenshot {'on' if s.screenshot else 'off'}.")
    since = time.strftime("%Y-%m-%dT%H:%M:%S")
    alert = notify.Alert(account=accounts.active(), bot="runetools", launch="lib.checks.notify_test",
                         reason=f"test alert from {socket.gethostname()} at {time.strftime('%H:%M:%S')} "
                                "— if your phone buzzed, alerts work",
                         last_step="notify_test", seconds=0, runs=0, source="test")
    thread = notify.send(alert)
    if thread is None:
        print("Not sent (held back by the limiter? see log/launcher.jsonl notify_suppressed).")
        return 1
    thread.join(notify.TIMEOUT * 2 + notify.MAX_RETRY_AFTER + 5)
    event = _last_notify_event(os.path.join(events.ROOT, "log", "launcher.jsonl"), since)
    if event is None:
        print("No result logged (still sending?). Check log/launcher.jsonl.")
        return 1
    print(f"{event['event']}: status {event.get('status')}, screenshot {event.get('screenshot')}")
    if event["event"] != "notify":
        print("Failed. 401 / 403 / 404: the webhook URL is wrong or was deleted — make a new one. "
              "timeout / URLError: no route to discord.com from here.")
        return 1
    print("Sent. Check Discord (and your phone).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
