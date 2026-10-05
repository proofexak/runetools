"""
Golden Nuggets miner actions.
"""
import time, random, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from lib.screen import find_nearest_color, find_color, pixel_matches, grab
import lib.vision as vision
from lib.movement import wait_until_stopped
from lib.inventory import get_slots
from lib.mouse import human_click, jitter, hesitate
from lib.camera import face
from lib.log import say
import lib.pause as pause
import miner.golden_nuggets.config as config


def orient_north():
    face("north", config)


def orient_east():
    face("east", config)


def orient_south():
    face("south", config)


def count_filled_slots():
    """Filled inventory slots (slot 0, the hammer, is skipped) — one capture of
    the inventory area, decided by vision.filled_slot_count."""
    slots = get_slots(config.INV_ANCHORS)
    xs = [x for x, _ in slots]
    ys = [y for _, y in slots]
    pad = 10
    l, t = min(xs) - pad, min(ys) - pad
    frame, _ = grab((l, t, max(xs) - l + pad, max(ys) - t + pad))
    _, _, bg_rgb = config.SLOT_BG_COLOR
    local = [(x - l, y - t) for x, y in slots[1:]]
    return vision.filled_slot_count(frame, local, bg_rgb, config.SLOT_BG_TOL)


def wait_stopped():
    wait_until_stopped(config.MOVEMENT_REGION)


def deposit_to_hopper():
    """Orient north, click the hopper, verify items were transferred."""
    say("Inventory full — depositing to hopper")
    orient_north()
    hesitate()
    pos, _ = find_color(config.RED, config.RED_TOL, region=config.HOPPER_REGION, whole_screen=True)
    if pos is None:
        say("Hopper not found — skipping deposit")
        return False
    before = count_filled_slots()
    ix, iy = round(pos[0]), round(pos[1])
    say(f"Clicking hopper at ({ix}, {iy})")
    human_click(ix, iy)
    wait_stopped()
    after = count_filled_slots()
    if after < before:
        say(f"Deposited  ({before} -> {after} items)")
        return True
    say(f"WARNING: Hopper deposit may have failed (inv {before} -> {after})")
    return False


def count_broken_struts(region):
    """Count distinct broken-strut clusters in region."""
    frame, _ = grab(region)
    return vision.count_clusters(frame, config.STRUT_COLOR, config.STRUT_TOL, radius=60)


def check_and_fix_struts():
    """
    The machine runs fine with 1 broken strut — only intervene if both are
    broken. Fixing just 1 is enough to restore operation.
    """
    n = count_broken_struts(config.STRUT_REGION)
    if n < 2:
        say(f"{n} strut(s) broken — machine still running, no fix needed")
        return
    say(f"{n} struts broken — machine stopped, fixing one")
    pos, _ = find_nearest_color(
        config.STRUT_COLOR, config.STRUT_TOL,
        region=config.STRUT_REGION, near=config.CHARACTER, whole_screen=True,
    )
    if pos is None:
        say("Could not locate strut to fix")
        return
    ix, iy = round(pos[0]), round(pos[1])
    say(f"Clicking strut at ({ix}, {iy})")
    hesitate()
    human_click(ix, iy)
    wait_stopped()


def click_struts():
    """
    1. Check STRUT_REGION (hopper view) — click if found, wait_stopped.
    2. Check STRUT_NEAR_REGION — click up to 2 remaining struts.
    """
    pos, _ = find_nearest_color(
        config.STRUT_COLOR, config.STRUT_TOL,
        region=config.STRUT_REGION, near=config.CHARACTER,
    )
    if pos is None:
        say("No strut visible from hopper view")
    else:
        ix, iy = round(pos[0]), round(pos[1])
        say(f"Clicking strut (hopper view) at ({ix}, {iy})")
        hesitate()
        human_click(ix, iy)
        wait_stopped()

    for _ in range(2):
        pos, _ = find_nearest_color(
            config.STRUT_COLOR, config.STRUT_TOL,
            region=config.STRUT_NEAR_REGION, near=config.CHARACTER,
        )
        if pos is None:
            say("No more struts in near region")
            break
        ix, iy = round(pos[0]), round(pos[1])
        say(f"Clicking strut (near view) at ({ix}, {iy})")
        hesitate()
        human_click(ix, iy)
        wait_stopped()


def click_sack(region):
    """Find green sack in region (retry up to 10s), click it, wait_stopped, return new item delta."""
    before = count_filled_slots()
    hesitate()
    deadline = time.time() + 10
    pos = None
    while time.time() < deadline:
        pause.wait()
        pos, _ = find_color(config.GREEN, config.GREEN_TOL, region=region)
        if pos is not None:
            break
        say("Sack not visible yet — retrying...")
        time.sleep(1)
    if pos is None:   # one last look, over the whole screen
        pos, _ = find_color(config.GREEN, config.GREEN_TOL, region=region, whole_screen=True)
    if pos is None:
        say("Sack not found after 10s")
        return 0
    ix, iy = round(pos[0]), round(pos[1])
    say(f"Clicking sack at ({ix}, {iy})")
    human_click(ix, iy)
    wait_stopped()
    after = count_filled_slots()
    delta = max(0, after - before)
    say(f"Sack gave {delta} items  (inv {after}/28)")
    return delta


def open_bank():
    """Click the bank booth and wait for the interface to open."""
    hesitate()
    pos, _ = find_color(config.BLUE, config.BLUE_TOL, region=config.BANK_REGION, whole_screen=True)
    if pos is None:
        say("Bank not found")
        return
    ix, iy = round(pos[0]), round(pos[1])
    say(f"Clicking bank at ({ix}, {iy})")
    human_click(ix, iy)
    bx, by, expected = config.BANK_CHECK
    deadline = time.time() + 10
    while time.time() < deadline:
        pause.wait()
        time.sleep(0.4)
        if pixel_matches(bx, by, expected):
            say("Bank opened")
            return
    say("Bank open timeout — proceeding anyway")


def deposit_all():
    """Click the Deposit-All button in the bank interface, verify inventory actually emptied."""
    before = count_filled_slots()
    hesitate()
    dpx, dpy = jitter(*config.DEPOSIT_ALL_BTN, n=3)
    say(f"Clicking Deposit-All at ({dpx}, {dpy})")
    human_click(dpx, dpy)
    time.sleep(random.uniform(0.5, 0.8))
    after = count_filled_slots()
    if before > 0 and after >= before:
        say(f"WARNING: Deposit-All didn't seem to work (inv {before} -> {after}) — check DEPOSIT_ALL_BTN calibration")
    else:
        say(f"Deposited all  (inv {before} -> {after})")


def process_full_sack(stats):
    """Full sack processing: orient east → fix struts → collect sack → bank loop → resume."""
    say("=== Sack full — processing ===")
    orient_east()

    # 1. Click any broken struts
    click_struts()

    # 2. Poll STRUT_NEAR_REGION every 3s until no struts visible
    say("Waiting for struts to clear...")
    while True:
        pause.wait()
        time.sleep(3)
        pos, _ = find_nearest_color(
            config.STRUT_COLOR, config.STRUT_TOL,
            region=config.STRUT_NEAR_REGION, near=config.CHARACTER,
        )
        if pos is None:
            break
        say("Struts still visible — waiting...")

    # 3. Collect from sack (walking distance)
    click_sack(config.SACK_REGION)
    orient_north()

    # 4. Bank loop — always deposit first, then check if sack has more
    open_bank()
    while True:
        deposit_all()
        pos, _ = find_color(config.GREEN, config.GREEN_TOL, region=config.SACK_BANK_REGION)
        if pos is None:
            say("Sack empty (no green) — done banking")
            break
        click_sack(config.SACK_BANK_REGION)  # closes bank
        open_bank()

    say("=== Sack processing done ===")
    orient_south()


def click_nearest_vein():
    """Click the pay-dirt vein closest to CHARACTER. Returns clicked (x, y) or None."""
    hesitate()
    pos, _ = find_nearest_color(
        config.MAGENTA, config.MAGENTA_TOL,
        region=config.PAY_DIRT_REGION,
        near=config.CHARACTER,
        jitter_pct=0.40,
    )
    if not pos:
        say("No pay-dirt vein found")
        return None
    ix = round(pos[0])
    iy = round(pos[1] - random.uniform(15, 35))  # bias upward
    say(f"Clicking vein at ({ix}, {iy})")
    human_click(ix, iy)
    return (ix, iy)


def character_in_any_vein():
    """
    Return True if CHARACTER falls inside the bounding box of any vein cluster
    in PAY_DIRT_REGION. False means the character is no longer at any vein.
    """
    l, t, _, _ = config.PAY_DIRT_REGION
    frame, _ = grab(config.PAY_DIRT_REGION)
    cx, cy = config.CHARACTER
    return vision.point_in_any_cluster(frame, config.MAGENTA, config.MAGENTA_TOL,
                                       (cx - l, cy - t), radius=40)


def wait_for_vein_depletion(clicked_pos, stats, idle_timeout=10):
    """
    Polls every ~1s. Increments stats['run'] immediately on each ore gain.
    Returns reason string: 'shifted' | 'idle' | 'no_veins' | 'left_vein' | 'full'
    """
    last_count = count_filled_slots()
    last_gain_t = time.time()

    while time.time() - last_gain_t < idle_timeout:
        if pause.wait():
            last_gain_t = time.time()   # a long pause isn't "idle — switch vein"
        time.sleep(random.uniform(0.8, 1.2))

        current = count_filled_slots()
        if current > last_count:
            gained = current - last_count
            stats["run"] += gained
            say(f"  +{gained} pay-dirt  (inv {current}/28, total {stats['run']})")
            last_count = current
            last_gain_t = time.time()

        # upgrade 3 — full inventory: exit immediately so hopper runs next iteration
        if current >= 27:
            say("Inventory full — heading to hopper")
            return "full"

        if not character_in_any_vein():
            say("Character outside all vein boxes — depleted")
            return "depleted"

    say(f"Idle {idle_timeout}s with no new ore — switching vein")
    return "idle"
