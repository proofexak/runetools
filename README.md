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
   .venv/bin/python test_energy.py                 # just reads energy, Ctrl+C to stop
   .venv/bin/python test_drink_sequence.py --force  # runs the full withdraw+drink+redeposit sequence once
   ```

Digit templates and the energy/stamina config are gitignored (per-user calibration data, tied to your specific screen/RuneLite rendering) — recalibrate on any new machine.

## Requirements
- Python 3.8+
- `pip install -r requirements.txt` (`pyautogui`, `mss`, `numpy`, `Pillow`, `pynput`, `transitions`)
- Development: `pip install -r requirements-dev.txt`, then `.venv/bin/python -m pytest` (runs `tests/`)
- Session history: `.venv/bin/python -m lib.logreport` (add `session latest` for the last run's details and errors, `stats` for long-term totals)
- `tkinter` (system package — e.g. `sudo apt install python3-tk` on Debian/Ubuntu)
- On Linux, an X11 session (mouse/keyboard simulation does not work under Wayland)

## Credits
Built with [Claude Code](https://claude.ai/code) (Anthropic).
