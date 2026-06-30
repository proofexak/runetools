"""
Miner bot dispatcher — routes to the correct sub-bot based on LOCATION.
"""
import miner.config as cfg


def run(stats):
    if cfg.LOCATION == "varrock exp":
        from miner.varrock_exp.run import run as _run
        _run(stats)
    elif cfg.LOCATION == "golden nuggets":
        from miner.golden_nuggets.run import run as _run
        _run(stats)
    else:
        print(f"[MINER] Unknown location: {cfg.LOCATION}")
