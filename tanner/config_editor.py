"""
Interactive config editor — click to capture positions, drag to capture regions.
Changes are applied in-memory immediately and written to config.py.
"""
import tkinter as tk
import threading, re, os, sys
import numpy as np
import mss

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tanner.config as cfg

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")

BG    = "#0f0f1e"
BG2   = "#1a1a33"
FG    = "#ccccee"
FG2   = "#888899"
FONT  = ("Consolas", 9)
FONTB = ("Consolas", 9, "bold")

FIELDS = [
    # (section, label, attr, type)
    # types: "point"        → (x, y)
    #        "point_color"  → (x, y, (r,g,b))
    #        "region"       → (left, top, width, height)  or  [(x,y), ...]
    ("Navigation",  "Compass",          "COMPASS",              "point"),
    ("Navigation",  "Character",        "CHARACTER",            "point"),
    ("Navigation",  "Tanner Area",       "TANNER_AREA",          "region"),
    ("Navigation",  "Ellis Region",      "ELLIS_REGION",         "region"),
    ("Bank",        "Bank Check",        "BANK_CHECK",           "point_color"),
    ("Bank",        "Deposit Button",    "DEPOSIT_BTN",          "point"),
    ("Bank",        "Hide Slot",         "HIDE_SLOT",            "point"),
    ("Bank",        "Bank Slot 2",       "BANK_SLOT_2",          "point"),
    ("Bank",        "Bank Region",       "BANK_REGION",          "region"),
    ("Tanning",     "Tanning Check",     "TANNING_CHECK",        "point_color"),
    ("Interface",   "Green Dragonhide",  "IB:green dragonhide",  "point_color"),
    ("Interface",   "Blue Dragonhide",   "IB:blue dragonhide",   "point_color"),
    ("Interface",   "Red Dragonhide",    "IB:red dragonhide",    "point_color"),
    ("Interface",   "Black Dragonhide",  "IB:black dragonhide",  "point_color"),
    ("Movement",    "Movement Region",   "MOVEMENT_REGION",      "region"),
]

# Colors used by the Show overlay
DOT_COLOR = "#00ff88"
REGION_COLORS = {
    "TANNER_AREA":    "#ff8800",   # orange
    "ELLIS_REGION":   "#00ccff",   # cyan
    "BANK_REGION":    "#ff44cc",   # pink
    "MOVEMENT_REGION":"#ffff00",   # yellow
}
DEFAULT_REGION_COLOR = "#ffffff"


# ── Value helpers ─────────────────────────────────────────────────────────────

def _get(attr):
    if attr.startswith("IB:"):
        return cfg.INTERFACE_BUTTONS.get(attr[3:])
    return getattr(cfg, attr, None)


def _fmt(val):
    if val is None:
        return "—"
    if isinstance(val, list) and val and isinstance(val[0], (tuple, list)):
        return f"polygon ({len(val)} pts)"
    if isinstance(val, tuple) and len(val) == 3 and isinstance(val[2], tuple):
        x, y, (r, g, b) = val
        return f"({x}, {y})  #{r:02x}{g:02x}{b:02x}"
    if isinstance(val, tuple) and len(val) == 2:
        return f"({val[0]}, {val[1]})"
    if isinstance(val, tuple) and len(val) == 4:
        return f"({val[0]}, {val[1]}, {val[2]}, {val[3]})"
    return str(val)


def _apply(attr, val):
    if attr.startswith("IB:"):
        cfg.INTERFACE_BUTTONS[attr[3:]] = val
    else:
        setattr(cfg, attr, val)


def _save(attr, val):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    if attr.startswith("IB:"):
        hide = attr[3:]
        x, y, (r, g, b) = val
        new_val = f"({x}, {y}, ({r}, {g}, {b}))"
        pattern = rf'("{re.escape(hide)}":\s*)(\([^(]+\([^)]+\)[^)]*\))'
        content = re.sub(pattern, rf'\g<1>{new_val}', content)
    else:
        pattern = rf'^({re.escape(attr)}\s*=\s*).*$'
        content = re.sub(pattern, rf'\g<1>{repr(val)}', content, flags=re.MULTILINE)

    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write(content)


# ── Screen capture helpers ────────────────────────────────────────────────────

def _grab_pixel(x, y):
    with mss.MSS() as sct:
        shot = sct.grab({"left": x, "top": y, "width": 1, "height": 1})
    px = np.array(shot)[0, 0]
    return int(px[2]), int(px[1]), int(px[0])


# ── Capture overlays ──────────────────────────────────────────────────────────

def _capture_point(root, with_color, callback):
    root.withdraw()
    ov = tk.Toplevel()
    ov.attributes('-fullscreen', True)
    ov.attributes('-alpha', 0.18)
    ov.attributes('-topmost', True)
    ov.configure(bg='black', cursor='crosshair')

    tk.Label(ov, text="Click the target position\n(ESC to cancel)",
             bg='#111133', fg='white', font=("Consolas", 13, "bold"),
             pady=12, padx=20).place(relx=0.5, rely=0.05, anchor='n')

    def on_click(event):
        x, y = ov.winfo_pointerx(), ov.winfo_pointery()
        ov.destroy()
        if with_color:
            r, g, b = _grab_pixel(x, y)
            callback((x, y, (r, g, b)))
        else:
            callback((x, y))
        root.deiconify()

    def on_esc(event):
        ov.destroy()
        root.deiconify()

    ov.bind('<Button-1>', on_click)
    ov.bind('<Escape>', on_esc)
    ov.focus_force()


def _capture_region(root, callback):
    root.withdraw()
    ov = tk.Toplevel()
    ov.attributes('-fullscreen', True)
    ov.attributes('-alpha', 0.25)
    ov.attributes('-topmost', True)
    ov.configure(bg='black', cursor='crosshair')

    canvas = tk.Canvas(ov, bg='black', highlightthickness=0)
    canvas.place(relwidth=1, relheight=1)

    lbl = tk.Label(ov, text="Click top-left corner\n(ESC to cancel)",
                   bg='#111133', fg='white', font=("Consolas", 13, "bold"),
                   pady=12, padx=20)
    lbl.place(relx=0.5, rely=0.05, anchor='n')

    points = []
    rect = [None]

    def on_motion(event):
        if len(points) == 1 and rect[0]:
            canvas.coords(rect[0], points[0][0], points[0][1], event.x_root, event.y_root)

    def on_click(event):
        x, y = ov.winfo_pointerx(), ov.winfo_pointery()
        points.append((x, y))
        if len(points) == 1:
            lbl.config(text="Now click bottom-right corner\n(ESC to cancel)")
            rect[0] = canvas.create_rectangle(x, y, x, y, outline='#00ff88', width=2)
        else:
            ov.destroy()
            x1, y1 = points[0]; x2, y2 = points[1]
            callback((min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1)))
            root.deiconify()

    def on_esc(event):
        ov.destroy()
        root.deiconify()

    canvas.bind('<Button-1>', on_click)
    canvas.bind('<Motion>', on_motion)
    ov.bind('<Escape>', on_esc)
    ov.focus_force()


def _capture_polygon(root, callback):
    root.withdraw()
    ov = tk.Toplevel()
    ov.attributes('-fullscreen', True)
    ov.attributes('-alpha', 0.3)
    ov.attributes('-topmost', True)
    ov.configure(bg='black', cursor='crosshair')

    canvas = tk.Canvas(ov, bg='black', highlightthickness=0)
    canvas.place(relwidth=1, relheight=1)

    lbl = tk.Label(ov,
                   text="Click to add vertices\nDouble-click or Enter to finish  ·  ESC to cancel",
                   bg='#111133', fg='white', font=("Consolas", 13, "bold"),
                   pady=12, padx=20)
    lbl.place(relx=0.5, rely=0.05, anchor='n')

    points = []
    dots = []
    lines = []
    preview = [None]

    def _redraw():
        for ln in lines:
            canvas.delete(ln)
        lines.clear()
        for i in range(len(points) - 1):
            lines.append(canvas.create_line(
                points[i][0], points[i][1], points[i+1][0], points[i+1][1],
                fill='#00ff88', width=2))

    def on_motion(event):
        if not points:
            return
        if preview[0]:
            canvas.delete(preview[0])
        preview[0] = canvas.create_line(
            points[-1][0], points[-1][1], event.x_root, event.y_root,
            fill='#00aa55', width=1, dash=(4, 4))

    def _finish():
        if len(points) < 3:
            return
        ov.destroy()
        callback(list(points))
        root.deiconify()

    def on_click(event):
        x, y = ov.winfo_pointerx(), ov.winfo_pointery()
        points.append((x, y))
        dots.append(canvas.create_oval(x-4, y-4, x+4, y+4, fill='#00ff88', outline=''))
        _redraw()
        lbl.config(text=f"{len(points)} pts  ·  Double-click or Enter to finish  ·  ESC to cancel")

    def on_double_click(event):
        if points:
            points.pop()
            if dots:
                canvas.delete(dots.pop())
        _finish()

    def on_esc(event):
        ov.destroy()
        root.deiconify()

    canvas.bind('<Button-1>', on_click)
    canvas.bind('<Double-Button-1>', on_double_click)
    canvas.bind('<Motion>', on_motion)
    canvas.bind('<Return>', lambda e: _finish())
    canvas.bind('<Escape>', on_esc)
    ov.bind('<Return>', _finish)
    ov.bind('<Escape>', on_esc)
    canvas.focus_force()


# ── Show overlay (small per-item windows) ─────────────────────────────────────

_DOT_SIZE = 14
_BORDER_T = 3


def _create_item_overlay(root, attr, label, ftype, sx, sy):
    """
    Create small always-on-top windows visualising one config item.
    Returns list of Toplevels, empty if the value is not configured yet.
    Each Toplevel uses the anti-cascade after(0, geometry) fix.
    """
    val = _get(attr)
    if val is None:
        return []

    wins = []

    def _solid(px, py, pw, ph, bg):
        lx = round(px * sx);  ly = round(py * sy)
        lw = max(1, round(pw * sx));  lh = max(1, round(ph * sy))
        w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=bg)
        g = f"{lw}x{lh}+{lx}+{ly}"
        w.geometry(g)
        w.after(0, lambda _w=w, _g=g: _w.geometry(_g))
        wins.append(w)

    def _labeled(px, py, text, fg):
        lx = round(px * sx);  ly = round(py * sy)
        w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg='#111111')
        tk.Label(w, text=text, bg='#111111', fg=fg,
                 font=('Consolas', 9, 'bold'), pady=1, padx=3).pack()
        w.update_idletasks()
        w.geometry(f"+{lx}+{ly}")
        w.after(0, lambda _w=w, _lx=lx, _ly=ly: _w.geometry(f"+{_lx}+{_ly}"))
        wins.append(w)

    if ftype == "region":
        color = REGION_COLORS.get(attr, DEFAULT_REGION_COLOR)
        if isinstance(val, list) and val and isinstance(val[0], (tuple, list)):
            # Polygon — draw actual outline on a small bounding-box canvas
            xs = [p[0] for p in val];  ys = [p[1] for p in val]
            l, t = min(xs) - 2, min(ys) - 2
            lw_ = max(1, round((max(xs) - l + 2) * sx))
            lh_ = max(1, round((max(ys) - t + 2) * sy))
            lx_ = round(l * sx);  ly_ = round(t * sy)
            w = tk.Toplevel(root)
            w.overrideredirect(True)
            w.attributes('-topmost', True)
            w.configure(bg='black')
            cv_ = tk.Canvas(w, bg='black', highlightthickness=0, bd=0,
                            width=lw_, height=lh_)
            cv_.pack()
            flat = [c for p in val
                    for c in (round((p[0] - l) * sx), round((p[1] - t) * sy))]
            cv_.create_polygon(flat, outline=color, fill='', width=2)
            g_ = f"{lw_}x{lh_}+{lx_}+{ly_}"
            w.geometry(g_)
            w.update_idletasks()
            w.wm_attributes('-transparentcolor', 'black')
            w.after(0, lambda _w=w, _g=g_: (
                _w.geometry(_g), _w.wm_attributes('-transparentcolor', 'black')))
            wins.append(w)
            _labeled(l + 6, t + 4, label, color)
        else:
            l, t, rw, rh = val
            T = _BORDER_T
            _solid(l,      t,      rw, T,  color)  # top
            _solid(l,      t + rh, rw, T,  color)  # bottom
            _solid(l,      t,      T,  rh, color)  # left
            _solid(l + rw, t,      T,  rh, color)  # right
            _labeled(l + 6, t + 4, label, color)

    else:
        if not (isinstance(val, tuple) and len(val) >= 2):
            return []
        x, y = val[0], val[1]
        _solid(x - _DOT_SIZE // 2, y - _DOT_SIZE // 2, _DOT_SIZE, _DOT_SIZE, DOT_COLOR)
        _labeled(x + _DOT_SIZE // 2 + 3, y - 10, label, DOT_COLOR)

    return wins


# ── Editor window ─────────────────────────────────────────────────────────────

def open_editor():
    threading.Thread(target=_run_editor, daemon=True).start()


def _run_editor():
    root = tk.Tk()
    root.title("Tanner Config Editor")
    root.configure(bg=BG)
    root.geometry("560x600+150+80")
    root.wm_attributes("-topmost", True)
    root.resizable(False, True)

    # Physical → logical coordinate scale (handles DPI-scaled screens)
    with mss.MSS() as _sct:
        _mon = _sct.monitors[1]
        _sx = root.winfo_screenwidth()  / _mon['width']  if _mon['width']  else 1.0
        _sy = root.winfo_screenheight() / _mon['height'] if _mon['height'] else 1.0

    ov_wins = {}  # attr → list[Toplevel]
    shown   = {}  # attr → bool
    _label_for = {a: lbl  for _, lbl,  a, _    in FIELDS}
    _ftype_for = {a: ftyp for _, _,    a, ftyp  in FIELDS}

    def _show_item(a):
        """Destroy and (if shown) recreate overlay windows for one item."""
        for w in ov_wins.pop(a, []):
            try: w.destroy()
            except: pass
        if not shown.get(a):
            return
        ws = _create_item_overlay(root, a, _label_for[a], _ftype_for[a], _sx, _sy)
        if ws:
            ov_wins[a] = ws

    def _refresh():
        """Refresh all currently-shown item overlays (called after a capture)."""
        for a in list(shown):
            if shown.get(a):
                _show_item(a)

    def _cleanup():
        for ws in ov_wins.values():
            for w in ws:
                try: w.destroy()
                except: pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _cleanup)

    # Scrollable area
    outer = tk.Frame(root, bg=BG)
    outer.pack(fill="both", expand=True)

    cv_scroll = tk.Canvas(outer, bg=BG, highlightthickness=0)
    sb = tk.Scrollbar(outer, orient="vertical", command=cv_scroll.yview)
    cv_scroll.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    cv_scroll.pack(side="left", fill="both", expand=True)

    frame = tk.Frame(cv_scroll, bg=BG)
    fid = cv_scroll.create_window((0, 0), window=frame, anchor="nw")

    cv_scroll.bind("<Configure>", lambda e: cv_scroll.itemconfig(fid, width=e.width))
    frame.bind("<Configure>", lambda e: cv_scroll.configure(scrollregion=cv_scroll.bbox("all")))
    cv_scroll.bind_all("<MouseWheel>", lambda e: cv_scroll.yview_scroll(int(-1*(e.delta/120)), "units"))

    # Build rows
    current_section = [None]

    for section, label, attr, ftype in FIELDS:
        if section != current_section[0]:
            current_section[0] = section
            sh = tk.Frame(frame, bg=BG2)
            sh.pack(fill="x", padx=4, pady=(12, 2))
            tk.Label(sh, text=f"  {section}", bg=BG2, fg=FG,
                     font=FONTB, pady=3).pack(side="left")

        row = tk.Frame(frame, bg=BG)
        row.pack(fill="x", padx=10, pady=2)

        tk.Label(row, text=label, bg=BG, fg=FG2, font=FONT,
                 width=15, anchor="w").pack(side="left")

        var = tk.StringVar(value=_fmt(_get(attr)))
        tk.Label(row, textvariable=var, bg=BG, fg=FG, font=FONT,
                 width=22, anchor="w").pack(side="left")

        def _cb(val, a=attr, v=var):
            _apply(a, val)
            _save(a, val)
            v.set(_fmt(val))
            _refresh()  # update overlay if it's showing this field

        # Capture buttons
        if ftype == "region":
            tk.Button(row, text="▭", bg="#223366", fg="white", font=FONT,
                      relief="flat", padx=5,
                      command=lambda a=attr, v=var: _capture_region(
                          root, lambda val, _a=a, _v=v: _cb(val, _a, _v))
                      ).pack(side="left", padx=(4, 1))
            tk.Button(row, text="⬡", bg="#1a3322", fg="white", font=FONT,
                      relief="flat", padx=5,
                      command=lambda a=attr, v=var: _capture_polygon(
                          root, lambda val, _a=a, _v=v: _cb(val, _a, _v))
                      ).pack(side="left", padx=(0, 4))
        elif ftype == "point_color":
            tk.Button(row, text="📍+🎨", bg="#223366", fg="white", font=FONT,
                      relief="flat", padx=5,
                      command=lambda a=attr, v=var: _capture_point(
                          root, True, lambda val, _a=a, _v=v: _cb(val, _a, _v))
                      ).pack(side="left", padx=4)
        else:
            tk.Button(row, text="📍", bg="#223366", fg="white", font=FONT,
                      relief="flat", padx=5,
                      command=lambda a=attr, v=var: _capture_point(
                          root, False, lambda val, _a=a, _v=v: _cb(val, _a, _v))
                      ).pack(side="left", padx=4)

        # Show toggle button
        show_btn = tk.Button(row, text="Show", bg="#222233", fg=FG2, font=FONT,
                             relief="flat", padx=5, width=5)

        def _toggle(a=attr, btn=show_btn):
            shown[a] = not shown.get(a, False)
            if shown[a]:
                btn.config(text="Hide", bg="#1a3322", fg="#00ff88")
            else:
                btn.config(text="Show", bg="#222233", fg=FG2)
            _show_item(a)

        show_btn.config(command=_toggle)
        show_btn.pack(side="left", padx=(4, 0))

    # Close button
    bf = tk.Frame(root, bg=BG, pady=8)
    bf.pack(side="bottom", fill="x")
    tk.Button(bf, text="Close", bg="#332233", fg="white", font=FONT,
              relief="flat", padx=24, command=_cleanup).pack(side="right", padx=10)

    root.mainloop()
