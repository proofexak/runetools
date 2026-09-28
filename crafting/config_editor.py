"""
Crafting bot config editor. Shared points/color go through the generic lib
editor; the per-item click/done-check points use a custom panel here since
their count is dynamic (grown via the "+ Add Item" button).
"""
import threading, re, os, sys
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import crafting.config as cfg
from lib.config_editor import run_editor, capture_point, fmt_val, BG, BG2, FG, FG2, FONT, FONTB

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")

_DOT_SIZE = 14

SHARED_FIELDS = [
    ("Crafting", "Alt Orb",            "ALT_ORB",            "point"),
    ("Crafting", "Currency Stash Tab", "CURRENCY_STASH_TAB", "point"),
    ("Crafting", "Crafting Stash Tab", "CRAFTING_STASH_TAB", "point"),
    ("Crafting", "Done Check Color",   "DONE_CHECK_COLOR",   "color"),
    ("Crafting", "Done Tolerance",     "DONE_TOL",           "number"),
]


def _get(attr):
    return getattr(cfg, attr, None)


def _apply(attr, val):
    setattr(cfg, attr, val)


def _save_attr(attr, val):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = rf'^({re.escape(attr)}\s*=\s*).*$'
    content = re.sub(pattern, rf'\g<1>{repr(val)}', content, flags=re.MULTILINE)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write(content)


def _make_marker(root, x, y, color, text):
    """Small always-on-top dot + label at absolute screen coords (x, y)."""
    dot = tk.Toplevel(root)
    dot.withdraw()
    dot.overrideredirect(True)
    dot.attributes('-topmost', True)
    dot.configure(bg=color)
    dot.geometry(f"{_DOT_SIZE}x{_DOT_SIZE}+{x - _DOT_SIZE // 2}+{y - _DOT_SIZE // 2}")
    dot.deiconify()

    lbl = tk.Toplevel(root)
    lbl.withdraw()
    lbl.overrideredirect(True)
    lbl.attributes('-topmost', True)
    lbl.configure(bg='#111111')
    tk.Label(lbl, text=text, bg='#111111', fg=color, font=('Consolas', 9, 'bold'),
             padx=3, pady=1).pack()
    lbl.update_idletasks()
    lbl.geometry(f"+{x + _DOT_SIZE // 2 + 3}+{y - 10}")
    lbl.deiconify()

    return [dot, lbl]


def _run_items_editor():
    root = tk.Tk()
    root.title("Crafting Items")
    root.configure(bg=BG)
    root.geometry("560x480+780+80")
    root.wm_attributes("-topmost", True)
    root.resizable(False, True)

    shown       = {}   # idx -> bool
    overlay_wins = {}  # idx -> [Toplevel, ...]

    def _clear_overlays():
        for wins in overlay_wins.values():
            for w in wins:
                try: w.destroy()
                except: pass
        overlay_wins.clear()

    def _refresh_overlay(i):
        for w in overlay_wins.pop(i, []):
            try: w.destroy()
            except: pass
        if not shown.get(i):
            return
        item = cfg.ITEMS[i]
        cx, cy = item.get("click_point", (0, 0))
        dx, dy = item.get("done_point", (0, 0))
        wins = _make_marker(root, cx, cy, "#00ff88", f"#{i + 1} click")
        wins += _make_marker(root, dx, dy, "#ff8800", f"#{i + 1} done")
        overlay_wins[i] = wins

    outer = tk.Frame(root, bg=BG)
    outer.pack(fill="both", expand=True)

    canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
    sb = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    list_frame = tk.Frame(canvas, bg=BG)
    fid = canvas.create_window((0, 0), window=list_frame, anchor="nw")
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(fid, width=e.width))
    list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    def _persist():
        _save_attr("ITEMS", cfg.ITEMS)

    def _remove(idx):
        _clear_overlays()
        shown.clear()
        cfg.ITEMS.pop(idx)
        _persist()
        _render()

    def _capture(idx, key):
        def _cb(val):
            cfg.ITEMS[idx][key] = val
            _persist()
            _refresh_overlay(idx)
            _render()
        capture_point(root, False, _cb)

    def _add_item():
        _clear_overlays()
        shown.clear()
        cfg.ITEMS.append({"click_point": (0, 0), "done_point": (0, 0), "skip": False})
        _persist()
        _render()

    def _toggle_show(i):
        shown[i] = not shown.get(i, False)
        _refresh_overlay(i)
        _render()

    def _show_all():
        for i in range(len(cfg.ITEMS)):
            shown[i] = True
            _refresh_overlay(i)
        _render()

    def _hide_all():
        _clear_overlays()
        shown.clear()
        _render()

    def _toggle_skip(i):
        cfg.ITEMS[i]["skip"] = not cfg.ITEMS[i].get("skip", False)
        _persist()
        _render()

    def _render():
        for w in list_frame.winfo_children():
            w.destroy()

        header = tk.Frame(list_frame, bg=BG2)
        header.pack(fill="x", padx=4, pady=(4, 6))
        tk.Label(header, text="  Items", bg=BG2, fg=FG, font=FONTB, pady=3, anchor="w"
                 ).pack(side="left", fill="x", expand=True)
        tk.Button(header, text="Show All", bg="#1a3322", fg="#00ff88", font=FONT,
                  relief="flat", padx=6, command=_show_all).pack(side="left", padx=(0, 4))
        tk.Button(header, text="Hide All", bg="#222233", fg=FG2, font=FONT,
                  relief="flat", padx=6, command=_hide_all).pack(side="left", padx=(0, 6))

        for i, item in enumerate(cfg.ITEMS):
            skipped = item.get("skip", False)
            row_bg = "#2a1a1a" if skipped else BG2
            row = tk.Frame(list_frame, bg=row_bg)
            row.pack(fill="x", padx=6, pady=3)

            tk.Label(row, text=f"#{i + 1}", bg=row_bg, fg=FG, font=FONTB,
                     width=3, anchor="w").pack(side="left", padx=(4, 0))

            tk.Label(row, text=f"Click {fmt_val(item.get('click_point'))}", bg=row_bg, fg=FG2,
                     font=FONT, width=16, anchor="w").pack(side="left")
            tk.Button(row, text="pt", bg="#223366", fg="white", font=FONT, relief="flat", padx=5,
                      command=lambda i=i: _capture(i, "click_point")).pack(side="left", padx=2)

            tk.Label(row, text=f"Done {fmt_val(item.get('done_point'))}", bg=row_bg, fg=FG2,
                     font=FONT, width=16, anchor="w").pack(side="left")
            tk.Button(row, text="pt", bg="#223366", fg="white", font=FONT, relief="flat", padx=5,
                      command=lambda i=i: _capture(i, "done_point")).pack(side="left", padx=2)

            show_on = shown.get(i, False)
            tk.Button(row, text="Hide" if show_on else "Show",
                      bg="#1a3322" if show_on else "#222233", fg="#00ff88" if show_on else FG2,
                      font=FONT, relief="flat", padx=5,
                      command=lambda i=i: _toggle_show(i)).pack(side="left", padx=2)

            tk.Button(row, text="Skipped" if skipped else "Skip",
                      bg="#552222" if skipped else "#3a3a1a", fg="#ff8888" if skipped else FG2,
                      font=FONT, relief="flat", padx=5,
                      command=lambda i=i: _toggle_skip(i)).pack(side="left", padx=2)

            tk.Button(row, text="✕", bg="#552222", fg="white", font=FONT, relief="flat", padx=5,
                      command=lambda i=i: _remove(i)).pack(side="left", padx=(6, 4))

        tk.Button(list_frame, text="+ Add Item", bg="#1a4a1a", fg="white", font=FONTB,
                  relief="flat", padx=10, pady=6,
                  command=_add_item).pack(fill="x", padx=6, pady=(10, 6))

    def _cleanup():
        _clear_overlays()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _cleanup)
    _render()
    root.mainloop()


def open_editor():
    threading.Thread(daemon=True, target=run_editor, args=(
        "Crafting Config", SHARED_FIELDS, _get, _apply, _save_attr,
    )).start()
    threading.Thread(daemon=True, target=_run_items_editor).start()
