"""
Crafting bot session loop.
"""
import time, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lib.pause as pause
import lib.log as log
import crafting.config as config
from crafting.crafting import grab_currency, craft_item, release

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def run(stats):
    log.setup(os.path.join(os.path.dirname(__file__), "log", "crafting"))

    print("Starting in 3s — switch to the game. Press P to pause, End to stop.")
    time.sleep(3)

    stats.update({"run": 0, "step": "starting", "start": None, "stop": False})
    pause.reset()

    items = [item for item in config.ITEMS if not item.get("skip")]
    total = len(items)
    item_n = 0
    start_time = time.time()
    stats["start"] = start_time

    try:
        stats["step"] = "grabbing currency"
        grab_currency()

        for item in items:
            if stats["stop"]:
                print("Stop requested via overlay.")
                break

            pause.wait()

            item_n += 1
            stats["run"] = item_n
            stats["step"] = f"item {item_n}/{total}"
            print(f"\n{'='*40}\n  ITEM {item_n}/{total}\n{'='*40}")

            craft_item(item)
            print(f"  Item {item_n} done — moving to next.")
        else:
            stats["step"] = "done"
            print("\nAll items done.")

    except pause.ForceStop:
        print("Force stopped (End key or overlay).")
    finally:
        release()

    elapsed = time.time() - start_time
    h, rem = divmod(int(elapsed), 3600)
    m, s   = divmod(rem, 60)
    print(f"Session ended. Items: {item_n}/{total} | Time: {h:02d}:{m:02d}:{s:02d}")
