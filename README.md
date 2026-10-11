# runetools

OSRS automation suite — Al Kharid dragonhide tanner, Motherlode Mine (golden nuggets) and Varrock
copper miners, and a chocolate dust grinder; every OSRS bot appears in the overlay menu
automatically. Also includes a Path of Exile crafting bot with its own launcher (`crafting_run.py`).

Setting up OSRS itself on Ubuntu (RuneLite + Jagex account login)? See [OSRS_ON_UBUNTU.md](OSRS_ON_UBUNTU.md).

## Bots

### Tanner
Tans dragonhides at Ellis in Al Kharid. Walks between the bank and the tanner, deposits inventory, withdraws hides, and tans them automatically.

**Run:**
```
launcher.bat   # Windows
./launcher.sh  # Linux/macOS
```

**Configure:**
Launch the bot, click `Tanning → ⚙ Configure` in the overlay to open the visual config editor. Click each field to capture positions directly from the screen.

### Stamina potions
The tanner bot can automatically withdraw and drink a stamina potion when run energy drops below a threshold. This needs its own one-time calibration, done in-game with RuneLite visible:

1. Overlay menu → `⚙ Energy Config` → capture **Energy Region** (▭) — a tight box around the run-energy % text under the minimap orb.
2. Run `.venv/bin/python calibrate_energy_digits.py` and follow the prompts. It asks what number your energy currently shows after each capture and builds a digit template library from your actual screen — general OCR (Tesseract) turned out to be unreliable on this font, so this uses exact pixel-template matching instead (see `lib/digit_templates.py`). Keep playing until it reports all 10 digits captured.
3. Back in `⚙ Energy Config`, capture the remaining fields: **Stamina Potion Slot**, **Drink Threshold**, **Bank Check**, **Deposit All**, **Potion Tab**, **Bank Slot 1**, **Inventory Check**, **Bank Booth Region** (a region near your character where the magenta bank booth outline appears).
4. In `Tanning → ⚙ Configure`, also capture **Hide Tab** (the bank tab holding raw hides) and **Empty Slot Check** (a pixel+colour sampled directly on Bank Slot 2 *while it's actually empty*, used to detect when you're out of hides).
5. Sanity-check each piece standalone before trusting it in a real run:
   ```
   .venv/bin/python -m lib.checks.read_energy               # just reads energy, Ctrl+C to stop
   .venv/bin/python -m lib.checks.drink_sequence --force    # runs the full withdraw+drink+redeposit sequence once
   ```

Digit templates and the energy/stamina config are gitignored (per-user calibration data, tied to your specific screen/RuneLite rendering) — recalibrate on any new machine.

## Phone alerts

When a bot stops and can't go on without you — out of hides, no glory charges, recovery or GE
restock failed, a crash, or an unattended container giving up (3 failed logins, restart budget,
missing client templates, no saved credentials) — it posts to a Discord channel: what stopped, why,
the last step, runtime and runs, and a screenshot of the screen at that moment. It @mentions you, so
your phone buzzes. Stopping it yourself (P, overlay Stop, `botctl stop` / `kill`), a finished job and an
automatic restart send nothing. The same account + reason is sent at most once per 10 minutes, at most
10 alerts an hour. A missing or broken webhook never stops a bot.

Setup (once):

1. Discord: a private channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL.
2. Settings → Advanced → Developer Mode on; right-click yourself → Copy User ID.
3. Menu runs: copy `lib/notify_config.example.py` to `lib/notify_config.py` (gitignored) and fill in
   `DISCORD_WEBHOOK_URL` and `DISCORD_USER_ID`. Containers: `NOTIFY_DISCORD_WEBHOOK=…` and
   `NOTIFY_DISCORD_USER_ID=…` in `docker/.env` (they win over the file), then `docker/botctl <account> up`.
   The URL is a password — anyone with it can post to the channel; never commit it.
4. Phone: Discord notifications on, the channel not muted.
5. Test: `.venv/bin/python -m lib.checks.notify_test` (in a container:
   `docker/botctl <account> compose exec runetools python3 -m lib.checks.notify_test`).

Each try is logged to `log/launcher.jsonl` (`notify`, `notify_error` with the HTTP status,
`notify_suppressed`): `python -m lib.logreport supervisor`.

## Web app (stats per account + login vault)

```
docker compose -f docker/docker-compose.yml up -d postgres webapp    # then open http://127.0.0.1:8778/
```

Bot time per account (today, last 7 days, 14-day chart), runs, crashes, what's running right now,
every session's timeline and tracebacks, and per-bot stats. It all comes from the session logs,
which the app reads as the bots write them (old logs are backfilled). Add your accounts there and
pick the one new sessions are tagged with (`account` in `session_start`, via `data/active_account`;
`RUNETOOLS_ACCOUNT` overrides it). Logins can be stored in a vault encrypted with a master password
that can't be recovered. The bots don't use these logins. Details, security and development:
[webapp/README.md](webapp/README.md).

## Requirements
- Python 3.8+
- `pip install -r requirements.txt` (`pyautogui`, `mss`, `numpy`, `Pillow`, `pynput`, `transitions`)
- Development: `pip install -r requirements-dev.txt`, then `.venv/bin/python -m pytest` (runs `tests/`)
- Session history: `.venv/bin/python -m lib.logreport` (add `session latest` for the last run's details and errors, `stats` for long-term totals)
- `tkinter` (system package — e.g. `sudo apt install python3-tk` on Debian/Ubuntu)
- On Linux, an X11 session (mouse/keyboard simulation does not work under Wayland)

## Credits
Built with [Claude Code](https://claude.ai/code) (Anthropic).
