"""
Golden Nuggets miner actions.
"""
import time, random, sys, os
import numpy as np
import mss

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from lib.screen import find_nearest_color, find_color, pixel_matches
from lib.movement import wait_until_stopped
from lib.inventory import get_slots
from lib.mouse import human_click, human_right_click, menu_click, jitter
import miner.golden_nuggets.config as config


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _pre_action():
    time.sleep(random.uniform(0.3, 0.8))


def orient_north():
    _log("Orienting camera north")
    _pre_action()
    cpx, cpy = jitter(*config.COMPASS, n=5)
    human_click(cpx, cpy)
    time.sleep(random.uniform(0.4, 0.7))


def orient_east():
    _log("Orienting camera east")
    _pre_action()
    cpx, cpy = jitter(*config.COMPASS, n=5)
    ax, ay = human_right_click(cpx, cpy)
    time.sleep(random.uniform(0.25, 0.45))
    menu_click(ax + 5, ay + config.MENU_HEADER + config.LOOK_EAST_ROW * config.MENU_ROW_H + config.MENU_ROW_H // 2)
    time.sleep(random.uniform(0.4, 0.7))
    _log("Camera oriented east")


def orient_south():
    _log("Orienting camera south")
    _pre_action()
    cpx, cpy = jitter(*config.COMPASS, n=5)
    ax, ay = human_right_click(cpx, cpy)
    time.sleep(random.uniform(0.25, 0.45))
    menu_click(ax + 5, ay + config.MENU_HEADER + config.LOOK_SOUTH_ROW * config.MENU_ROW_H + config.MENU_ROW_H // 2)
    time.sleep(random.uniform(0.4, 0.7))
    _log("Camera oriented")


def _inv_patches():
    """Grab inventory screenshot and return (frame, l, t, slots)."""
    slots = get_slots(config.INV_ANCHORS)
    xs = [x for x, _ in slots]
    ys = [y for _, y in slots]
    pad = 10
    l, t = min(xs) - pad, min(ys) - pad
    rw, rh = max(xs) - l + pad, max(ys) - t + pad
    with mss.MSS() as sct:
        mon  = sct.monitors[1]
        shot = sct.grab({"left": mon["left"] + l, "top": mon["top"] + t,
                         "width": rw, "height": rh})
    return np.array(shot)[:, :, :3], l, t, slots


_MIN_DEVIATING_PIXELS = 5  # pixels that must clearly differ from bg to count a slot filled


def _patch_deviating_count(patch, br, bg_, bb, tol):
    dr = np.abs(patch[:, :, 2].astype(int) - br)
    dg = np.abs(patch[:, :, 1].astype(int) - bg_)
    db = np.abs(patch[:, :, 0].astype(int) - bb)
    return int(((dr > tol) | (dg > tol) | (db > tol)).sum())



def count_filled_slots():
    """
    Grab the inventory region once. For each slot, count pixels in a 14×14 patch
    whose color clearly deviates from the calibrated empty-slot color. A slot is
    filled if enough pixels deviate — robust to items whose average color is
    close to background (e.g. small/bright icons surrounded by bg padding).
    """
    frame, l, t, slots = _inv_patches()
    _, _, (br, bg_, bb) = config.SLOT_BG_COLOR
    tol = config.SLOT_BG_TOL
    box = 7
    count = 0
    for sx, sy in slots[1:]:  # slot 0 is the hammer — always skip
        lx, ly = sx - l, sy - t
        patch = frame[max(0, ly - box):ly + box, max(0, lx - box):lx + box]
        if patch.size == 0:
            continue
        if _patch_deviating_count(patch, br, bg_, bb, tol) >= _MIN_DEVIATING_PIXELS:
            count += 1
    return count


def wait_stopped():
    wait_until_stopped(config.MOVEMENT_REGION)


def deposit_to_hopper():
    """Orient north, click the hopper, verify items were transferred."""
    _log("Inventory full — depositing to hopper")
    orient_north()
    _pre_action()
    pos, _ = find_color(config.RED, config.RED_TOL, region=config.HOPPER_REGION)
    if pos is None:
        _log("Hopper not found — skipping deposit")
        return False
    before = count_filled_slots()
    ix, iy = round(pos[0]), round(pos[1])
    _log(f"Clicking hopper at ({ix}, {iy})")
    human_click(ix, iy)
    wait_stopped()
    after = count_filled_slots()
    if after < before:
        _log(f"Deposited  ({before} -> {after} items)")
        return True
    _log(f"WARNING: Hopper deposit may have failed (inv {before} -> {after})")
    return False


def count_broken_struts(region):
    """Count distinct broken-strut clusters (magenta) in region."""
    l, t, w, h = region
    mr, mg, mb = config.MAGENTA
    tol = config.MAGENTA_TOL

    with mss.MSS() as sct:
        mon  = sct.monitors[1]
        shot = sct.grab({"left": mon["left"] + l, "top": mon["top"] + t,
                         "width": w, "height": h})
    frame = np.array(shot)[:, :, :3]
    mask = (
        (frame[:, :, 2] >= mr - tol) & (frame[:, :, 2] <= mr + tol) &
        (frame[:, :, 1] >= mg - tol) & (frame[:, :, 1] <= mg + tol) &
        (frame[:, :, 0] >= mb - tol) & (frame[:, :, 0] <= mb + tol)
    )
    if not mask.any():
        return 0

    ys_i, xs_i = np.where(mask)
    abs_xs = xs_i.astype(float)
    abs_ys = ys_i.astype(float)
    remaining = np.ones(len(abs_xs), dtype=bool)
    count = 0
    while remaining.any():
        idx = int(np.argmax(remaining))
        sx_, sy_ = abs_xs[idx], abs_ys[idx]
        in_c = remaining & (
            (abs_xs - sx_) ** 2 + (abs_ys - sy_) ** 2 <= 60 ** 2
        )
        remaining &= ~in_c
        count += 1
    return count


def check_and_fix_struts():
    """
    The machine runs fine with 1 broken strut — only intervene if both are
    broken. Fixing just 1 is enough to restore operation.
    """
    n = count_broken_struts(config.STRUT_REGION)
    if n < 2:
        _log(f"{n} strut(s) broken — machine still running, no fix needed")
        return
    _log(f"{n} struts broken — machine stopped, fixing one")
    pos, _ = find_nearest_color(
        config.MAGENTA, config.MAGENTA_TOL,
        region=config.STRUT_REGION, near=config.CHARACTER,
    )
    if pos is None:
        _log("Could not locate strut to fix")
        return
    ix, iy = round(pos[0]), round(pos[1])
    _log(f"Clicking strut at ({ix}, {iy})")
    _pre_action()
    human_click(ix, iy)
    wait_stopped()


def click_struts():
    """
    1. Check STRUT_REGION (hopper view) — click if found, wait_stopped.
    2. Loop STRUT_NEAR_REGION — click all remaining struts one by one.
    """
    pos, _ = find_nearest_color(
        config.MAGENTA, config.MAGENTA_TOL,
        region=config.STRUT_REGION, near=config.CHARACTER,
    )
    if pos is None:
        _log("No strut visible from hopper view")
    else:
        ix, iy = round(pos[0]), round(pos[1])
        _log(f"Clicking strut (hopper view) at ({ix}, {iy})")
        _pre_action()
        human_click(ix, iy)
        wait_stopped()

    while True:
        pos, _ = find_nearest_color(
            config.MAGENTA, config.MAGENTA_TOL,
            region=config.STRUT_NEAR_REGION, near=config.CHARACTER,
        )
        if pos is None:
            _log("No more struts in near region")
            break
        ix, iy = round(pos[0]), round(pos[1])
        _log(f"Clicking strut (near view) at ({ix}, {iy})")
        _pre_action()
        human_click(ix, iy)
        wait_stopped()


def click_sack(region):
    """Find green sack in region (retry up to 10s), click it, wait_stopped, return new item delta."""
    before = count_filled_slots()
    _pre_action()
    deadline = time.time() + 10
    pos = None
    while time.time() < deadline:
        pos, _ = find_color(config.GREEN, config.GREEN_TOL, region=region)
        if pos is not None:
            break
        _log("Sack not visible yet — retrying...")
        time.sleep(1)
    if pos is None:
        _log("Sack not found after 10s")
        return 0
    ix, iy = round(pos[0]), round(pos[1])
    _log(f"Clicking sack at ({ix}, {iy})")
    human_click(ix, iy)
    wait_stopped()
    after = count_filled_slots()
    delta = max(0, after - before)
    _log(f"Sack gave {delta} items  (inv {after}/28)")
    return delta


def open_bank():
    """Click the bank booth and wait for the interface to open."""
    _pre_action()
    pos, _ = find_color(config.BLUE, config.BLUE_TOL, region=config.BANK_REGION)
    if pos is None:
        _log("Bank not found")
        return
    ix, iy = round(pos[0]), round(pos[1])
    _log(f"Clicking bank at ({ix}, {iy})")
    human_click(ix, iy)
    bx, by, expected = config.BANK_CHECK
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(0.4)
        if pixel_matches(bx, by, expected):
            _log("Bank opened")
            return
    _log("Bank open timeout — proceeding anyway")


def deposit_all():
    """Click the Deposit-All button in the bank interface, verify inventory actually emptied."""
    before = count_filled_slots()
    _pre_action()
    dpx, dpy = jitter(*config.DEPOSIT_ALL_BTN, n=3)
    _log(f"Clicking Deposit-All at ({dpx}, {dpy})")
    human_click(dpx, dpy)
    time.sleep(random.uniform(0.5, 0.8))
    after = count_filled_slots()
    if before > 0 and after >= before:
        _log(f"WARNING: Deposit-All didn't seem to work (inv {before} -> {after}) — check DEPOSIT_ALL_BTN calibration")
    else:
        _log(f"Deposited all  (inv {before} -> {after})")


def process_full_sack(stats):
    """Full sack processing: orient east → fix struts → collect sack → bank loop → resume."""
    _log("=== Sack full — processing ===")
    orient_east()

    # 1. Click any broken struts
    click_struts()

    # 2. Poll STRUT_NEAR_REGION every 3s until no struts visible
    _log("Waiting for struts to clear...")
    while True:
        time.sleep(3)
        pos, _ = find_nearest_color(
            config.MAGENTA, config.MAGENTA_TOL,
            region=config.STRUT_NEAR_REGION, near=config.CHARACTER,
        )
        if pos is None:
            break
        _log("Struts still visible — waiting...")

    # 3. Collect from sack (walking distance)
    click_sack(config.SACK_REGION)
    orient_north()

    # 4. Bank loop — always deposit first, then check if sack has more
    open_bank()
    while True:
        deposit_all()
        pos, _ = find_color(config.GREEN, config.GREEN_TOL, region=config.SACK_BANK_REGION)
        if pos is None:
            _log("Sack empty (no green) — done banking")
            break
        click_sack(config.SACK_BANK_REGION)  # closes bank
        open_bank()

    _log("=== Sack processing done ===")
    orient_south()


def click_nearest_vein():
    """Click the pay-dirt vein closest to CHARACTER. Returns clicked (x, y) or None."""
    _pre_action()
    pos, _ = find_nearest_color(
        config.MAGENTA, config.MAGENTA_TOL,
        region=config.PAY_DIRT_REGION,
        near=config.CHARACTER,
        jitter_pct=0.40,
    )
    if not pos:
        _log("No pay-dirt vein found")
        return None
    ix = round(pos[0])
    iy = round(pos[1] - random.uniform(15, 35))  # bias upward
    _log(f"Clicking vein at ({ix}, {iy})")
    human_click(ix, iy)
    return (ix, iy)


def character_in_any_vein():
    """
    Return True if CHARACTER falls inside the bounding box of any magenta cluster
    in PAY_DIRT_REGION. False means the character is no longer at any vein.
    """
    l, t, w, h = config.PAY_DIRT_REGION
    mr, mg, mb = config.MAGENTA
    tol = config.MAGENTA_TOL

    with mss.MSS() as sct:
        mon  = sct.monitors[1]
        shot = sct.grab({"left": mon["left"] + l, "top": mon["top"] + t,
                         "width": w, "height": h})
    frame = np.array(shot)[:, :, :3]
    mask = (
        (frame[:, :, 2] >= mr - tol) & (frame[:, :, 2] <= mr + tol) &
        (frame[:, :, 1] >= mg - tol) & (frame[:, :, 1] <= mg + tol) &
        (frame[:, :, 0] >= mb - tol) & (frame[:, :, 0] <= mb + tol)
    )
    if not mask.any():
        return False

    ys_i, xs_i = np.where(mask)
    abs_xs = (xs_i + l).astype(float)
    abs_ys = (ys_i + t).astype(float)
    cx, cy  = config.CHARACTER

    remaining = np.ones(len(abs_xs), dtype=bool)
    while remaining.any():
        idx     = int(np.argmax(remaining))
        sx, sy  = abs_xs[idx], abs_ys[idx]
        in_clus = remaining & (
            (abs_xs - sx) ** 2 + (abs_ys - sy) ** 2 <= 40 ** 2
        )
        remaining &= ~in_clus
        x0, x1 = abs_xs[in_clus].min(), abs_xs[in_clus].max()
        y0, y1 = abs_ys[in_clus].min(), abs_ys[in_clus].max()
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return True
    return False


def wait_for_vein_depletion(clicked_pos, stats, idle_timeout=10):
    """
    Polls every ~1s. Increments stats['run'] immediately on each ore gain.
    Returns reason string: 'shifted' | 'idle' | 'no_veins' | 'left_vein' | 'full'
    """
    last_count = count_filled_slots()
    last_gain_t = time.time()

    while time.time() - last_gain_t < idle_timeout:
        time.sleep(random.uniform(0.8, 1.2))

        current = count_filled_slots()
        if current > last_count:
            gained = current - last_count
            stats["run"] += gained
            _log(f"  +{gained} pay-dirt  (inv {current}/28, total {stats['run']})")
            last_count = current
            last_gain_t = time.time()

        # upgrade 3 — full inventory: exit immediately so hopper runs next iteration
        if current >= 27:
            _log("Inventory full — heading to hopper")
            return "full"

        if not character_in_any_vein():
            _log("Character outside all vein boxes — depleted")
            return "depleted"

    _log(f"Idle {idle_timeout}s with no new ore — switching vein")
    return "idle"
