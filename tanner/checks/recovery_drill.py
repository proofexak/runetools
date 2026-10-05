"""
Live check: test the amulet-of-glory recovery in a real session. Opening bank
and one normal trip (tanner → bank), then the recovery sequence (teleport →
double doors → TP Walk Region → booth in TP Booth Region → bank), then stop.
Uses one glory charge. Start standing at the Al Kharid bank with hides banked.

    .venv/bin/python -m tanner.checks.recovery_drill ["black dragonhide"]

O pauses/resumes, P force-stops.
"""


def main():
    import sys
    import lib.pause as pause
    import tanner.config as config
    import tanner.run as run
    from tanner.states import recovery_drill

    if not all(getattr(config, "TP_BOOTH_REGION", (0, 0, 0, 0))[2:]):
        print("TP Booth Region not calibrated — Tanning → ⚙ Configure first.")
        raise SystemExit(1)
    if len(sys.argv) > 1:
        config.HIDE_TYPE = sys.argv[1]
    pause.setup(pause_hotkey="o", stop_hotkey="p")

    normal = run._handlers
    stats = {}
    run._handlers = lambda session: recovery_drill(normal(session), stats)
    run.run(stats)


if __name__ == "__main__":
    main()
