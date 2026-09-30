"""
Always-on-top overlay with an optional bot/hide selector followed by a live stats panel.

Usage:
    from lib.overlay import start as start_overlay
    import lib.overlay as overlay

    start_overlay(
        stats          = stats_dict,        # {run, step, start, stop}
        hide_selected  = threading.Event(), # set when selection is done
        use_selector   = True,              # False → go straight to stats
        menu           = [                  # top-level menu items
            ("Tanning", [                   # value is a list → submenu page
                ("Green Dragonhide", "green dragonhide", "#1a4a1a", "#2d7a2d"),
                ...
            ], "#1a3a1a", "#2d6a2d"),
        ],
        on_select      = lambda val: ...,   # called with the chosen value
        stats_extra    = lambda s: f"Hides: {s['run'] * 27}",  # optional extra line
    )

    # After a session ends, go back to the selector:
    new_event = threading.Event()
    overlay.show_selector(new_event)
    new_event.wait()
"""
import time, os, threading, traceback
import tkinter as tk
import lib.events as events
import lib.pause as pause
from lib.session import format_elapsed, emergency_teardown

BG        = "#0d0d0d"
FG        = "#aaaacc"
FG_STAT   = "#00ff00"
FONT      = ("Consolas", 10)
FONT_B    = ("Consolas", 10, "bold")
FONT_STAT = ("Consolas", 11)
FONT_BTN  = ("Consolas", 9)
WIDTH     = 210
BTN_W     = 18

# Module-level refs so show_selector() can be called from outside the thread
_root_ref        = [None]
_show_main_ref   = [None]
_build_stats_ref = [None]
_hide_sel_ref    = [None]   # mutable ref to current hide_selected event


def show_selector(new_hide_selected):
    """Switch the overlay back to the bot selector after a session ends."""
    _hide_sel_ref[0] = new_hide_selected
    if _root_ref[0] and _show_main_ref[0]:
        _root_ref[0].after(0, _show_main_ref[0])


def switch_to_stats():
    """Switch overlay to the stats panel (used when a callable triggers the session)."""
    if _root_ref[0] and _build_stats_ref[0]:
        _root_ref[0].after(0, _build_stats_ref[0])


def _btn_h(n_items):
    return 50 + n_items * 38 + 10


def start(stats, hide_selected, use_selector, menu, on_select, stats_extra=None, corner="top-left"):
    """Launch the overlay in a daemon thread. Returns immediately.
    corner: "top-left" (default), "top-right", "bottom-left", or "bottom-right"."""
    _hide_sel_ref[0] = hide_selected
    threading.Thread(target=_run, daemon=True,
                     args=(stats, use_selector, menu, on_select, stats_extra, corner)).start()


def _run(stats, use_selector, menu, on_select, stats_extra, corner="top-left"):
    root = tk.Tk()

    def _report_callback_exception(exc_type, exc, tb):
        # Tk swallows callback errors (only prints them); record them too.
        events.record_error(exc, "overlay")
        traceback.print_exception(exc_type, exc, tb)
    root.report_callback_exception = _report_callback_exception
    root.overrideredirect(True)
    root.wm_attributes("-topmost", True)
    root.wm_attributes("-alpha", 0.9)
    root.configure(bg=BG)

    _root_ref[0] = root
    _current = [None]

    _MARGIN = 10

    def _pos(w, h):
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = sw - w - _MARGIN if corner in ("top-right", "bottom-right") else _MARGIN
        y = sh - h - _MARGIN if corner in ("bottom-left", "bottom-right") else _MARGIN
        return x, y

    def _clear():
        if _current[0]:
            _current[0].destroy()
        _current[0] = None

    # ── Selector pages ────────────────────────────────────────────────────────

    def _show_page(items, title, back_fn=None):
        _clear()
        h = _btn_h(len(items) + (1 if back_fn else 0))
        x, y = _pos(WIDTH, h)
        root.geometry(f"{WIDTH}x{h}+{x}+{y}")
        f = tk.Frame(root, bg=BG)
        f.pack(fill="both", expand=True, padx=6, pady=6)
        _current[0] = f

        tk.Label(f, text=title, fg=FG, bg=BG, font=FONT_B).pack(pady=(4, 6))

        for item in items:
            label, value, bg, hover = item[0], item[1], item[2], item[3]
            extra_btn = item[4] if len(item) > 4 else None  # (small_label, cmd)

            if isinstance(value, list):
                cmd = lambda lbl=label, sub=value: _show_page(sub, lbl, back_fn=_show_main)
            elif callable(value):
                cmd = value
            else:
                def cmd(v=value):
                    on_select(v)
                    _clear()
                    _build_stats()
                    _hide_sel_ref[0].set()

            if extra_btn:
                row = tk.Frame(f, bg=BG)
                row.pack(fill="x", pady=2)
                tk.Button(row, text=label, bg=bg, fg="white",
                          font=FONT, relief="flat", pady=4,
                          activebackground=hover, activeforeground="white",
                          command=cmd).pack(side="left", fill="x", expand=True)
                tk.Button(row, text=extra_btn[0], bg="#1a2a3a", fg="#88aacc",
                          font=FONT_BTN, relief="flat", pady=4, padx=4,
                          activebackground="#2a3a4a", activeforeground="white",
                          command=extra_btn[1]).pack(side="left", padx=(2, 0))
            else:
                tk.Button(f, text=label, bg=bg, fg="white",
                          font=FONT, width=BTN_W, relief="flat", pady=4,
                          activebackground=hover, activeforeground="white",
                          command=cmd).pack(pady=2)

        if back_fn:
            tk.Button(f, text="← Back", bg="#222222", fg="#888888",
                      font=FONT_BTN, width=BTN_W, relief="flat", pady=3,
                      command=back_fn).pack(pady=(4, 0))

    def _show_main():
        _show_page(menu, title="OSRS Bot")

    _show_main_ref[0] = _show_main

    # ── Stats panel ───────────────────────────────────────────────────────────


    def _build_stats():
        _clear()
        x, y = _pos(WIDTH, 155)
        root.geometry(f"{WIDTH}x155+{x}+{y}")

        f = tk.Frame(root, bg=BG)
        f.pack(fill="both", expand=True)
        _current[0] = f

        lbl = tk.Label(f, text="", fg=FG_STAT, bg=BG,
                       font=FONT_STAT, justify="left", padx=8, pady=6)
        lbl.pack(fill="both", expand=True)

        bf = tk.Frame(f, bg=BG)
        bf.pack(fill="x", padx=6, pady=(0, 6))

        def _exit():
            emergency_teardown()   # e.g. release a held key before the process ends
            os._exit(0)

        pause_btn = tk.Button(bf, text="Pause", width=5,
                              bg="#333355", fg="white", font=FONT_BTN, relief="flat")
        pause_btn.pack(side="left", padx=2)
        tk.Button(bf, text="End", width=4, bg="#553300", fg="white",
                  font=FONT_BTN, relief="flat",
                  command=lambda: stats.update({"stop": True})).pack(side="left", padx=2)
        tk.Button(bf, text="F.End", width=5, bg="#884400", fg="white",
                  font=FONT_BTN, relief="flat",
                  command=pause.force_stop).pack(side="left", padx=2)
        tk.Button(bf, text="Exit", width=4, bg="#550000", fg="white",
                  font=FONT_BTN, relief="flat",
                  command=_exit).pack(side="left", padx=2)

        def _do_pause():
            pause.toggle()
            pause_btn.config(text="Resume" if pause.is_paused() else "Pause")

        pause_btn.config(command=_do_pause)

        def _tick():
            if _current[0] is not f:
                return  # stats frame was destroyed, stop loop
            pause_btn.config(text="Resume" if pause.is_paused() else "Pause")
            start_t = stats.get("start")
            elapsed = format_elapsed(time.time() - start_t if start_t else 0)
            lines = [f"Runs:    {stats.get('run', 0)}"]
            extra = stats_extra(stats) if stats_extra else None
            if extra:
                lines.append(extra)
            lines += [f"Time:    {elapsed}", f"Step:    {stats.get('step', '')}"]
            lbl.config(text="\n".join(lines))
            root.after(500, _tick)

        _tick()

    _build_stats_ref[0] = _build_stats

    # ── Start ─────────────────────────────────────────────────────────────────

    if use_selector:
        _show_main()
    else:
        _build_stats()

    root.mainloop()
