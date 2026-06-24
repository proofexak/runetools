"""
OSRS Bot Launcher — opens the tanner with the in-overlay hide selector.
"""
import subprocess, sys, os

script = os.path.join(os.path.dirname(__file__), "tanner", "run.py")
subprocess.Popen([sys.executable, script, "--select"], creationflags=subprocess.CREATE_NEW_CONSOLE)
