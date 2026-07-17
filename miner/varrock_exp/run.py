"""
Varrock Exp session loop.
"""
import time, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import lib.pause as pause
import lib.log as log
from miner.varrock_exp.miner import orient_south, click_magenta_rock, click_blue_rock, wait_and_drop

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def run(stats):
    log.setup(os.path.join(os.path.dirname(__file__), "log", "varrock_exp"))

    print("Starting in 3s — switch to OSRS. Press P to pause.")
    time.sleep(3)

    stats.update({"run": 0, "step": "starting", "start": time.time(), "stop": False})
    pause.reset()
    orient_south()

    run_n = 0
    start_time = time.time()

    try:
        while True:
            pause.wait()
            if stats["stop"]:
                print("Stop requested via overlay.")
                break

            stats["step"] = "magenta rock"
            if not click_magenta_rock():
                print("  Magenta not found — trying blue")
                stats["step"] = "blue rock (fallback)"
                if not click_blue_rock():
                    print("  No rocks found — waiting 10s")
                    time.sleep(10)
                    continue

            wait_and_drop()

            pause.wait()
            if stats["stop"]:
                break

            stats["step"] = "blue rock"
            if not click_blue_rock():
                print("  Blue not found — trying magenta")
                stats["step"] = "magenta rock (fallback)"
                if not click_magenta_rock():
                    print("  No rocks found — waiting 10s")
                    time.sleep(10)
                    continue

            found = wait_and_drop()
            if found:
                run_n += 1
                stats["run"] = run_n

    except pause.ForceStop:
        print("Force stopped via overlay.")

    elapsed = time.time() - start_time
    h, rem = divmod(int(elapsed), 3600)
    m, s   = divmod(rem, 60)
    print(f"Session ended. Ores dropped: {run_n} | Time: {h:02d}:{m:02d}:{s:02d}")
