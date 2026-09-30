"""
Logging — redirect stdout to both console and a timestamped log file.
"""
import sys, time


class _Tee:
    def __init__(self, *files): self._files = files
    def write(self, data):
        for f in self._files: f.write(data)
    def flush(self):
        for f in self._files: f.flush()


def say(msg):
    """Print with a [HH:MM:SS] timestamp — the standard bot log line."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def setup(prefix, stamp=None):
    """
    Tee stdout and stderr to a timestamped log file named <prefix>_<stamp>.log
    (stamp defaults to now, YYYYMMDD_HHMMSS). Returns the open file handle.
    """
    stamp = stamp or time.strftime("%Y%m%d_%H%M%S")
    f = open(f"{prefix}_{stamp}.log", "w", buffering=1, encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, f)
    sys.stderr = _Tee(sys.__stderr__, f)
    return f
