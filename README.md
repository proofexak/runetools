# runetools

OSRS automation suite — currently includes the Al Kharid dragonhide tanner.

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

## Requirements
- Python 3.8+
- `pip install -r requirements.txt` (`pyautogui`, `mss`, `numpy`, `Pillow`, `pynput`)
- `tkinter` (system package — e.g. `sudo apt install python3-tk` on Debian/Ubuntu)
- On Linux, an X11 session (mouse/keyboard simulation does not work under Wayland)

## Credits
Built with [Claude Code](https://claude.ai/code) (Anthropic).
