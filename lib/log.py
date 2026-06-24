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


def setup(prefix):
    """
    Tee stdout and stderr to a timestamped log file named <prefix>_YYYYMMDD_HHMMSS.log.
    Returns the open file handle.
    """
    f = open(f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.log", "w", buffering=1, encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, f)
    sys.stderr = _Tee(sys.__stderr__, f)
    return f
