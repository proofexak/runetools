"""
OSRS Bot Launcher — choose a bot to open.
"""
import subprocess, sys, os

_here = os.path.dirname(__file__)

bots = {
    "1": ("Tanner", os.path.join(_here, "tanner", "run.py"), ["--select"]),
    "2": ("Miner",  os.path.join(_here, "miner",  "run.py"), []),
}

print("Select bot:")
for key, (name, _, _) in bots.items():
    print(f"  {key}. {name}")

choice = input("> ").strip()
if choice in bots:
    name, script, args = bots[choice]
    print(f"Launching {name}...")
    subprocess.Popen([sys.executable, script] + args, creationflags=subprocess.CREATE_NEW_CONSOLE)
else:
    print("Invalid choice.")
