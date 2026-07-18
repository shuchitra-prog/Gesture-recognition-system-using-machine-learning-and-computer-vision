# gui/home_page.py
# Home page of the Gesture Controlled Computer GUI.
# Shows title, camera start/stop, profile selector, and status.

import tkinter as tk
from tkinter import ttk, messagebox
from gui import styles as s
import config


class HomePage(tk.Frame):
    """
    Main dashboard displayed when the app starts.
    Communicates with the parent App via callbacks.
    """

    def __init__(self, parent, app_controller, **kwargs):
        super().__init__(parent, bg=s.BG, **kwargs)
        self.ctrl = app_controller   # reference to App instance
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Title bar ─────────────────────────────
        title_frame = tk.Frame(self, bg=s.BG)
        title_frame.pack(fill="x", pady=(30, 10), padx=40)

        tk.Label(title_frame,
                 text="GESTURE CONTROLLED COMPUTER",
                 bg=s.BG, fg=s.ACCENT,
                 font=("Consolas", 20, "bold")).pack(anchor="w")

        tk.Label(title_frame,
                 text="Real-Time Hand Gesture Interface  •  Powered by MediaPipe",
                 bg=s.BG, fg=s.TEXT_MUTED,
                 font=s.FONT_SMALL).pack(anchor="w")

        _divider(self)

        # ── Camera control card ───────────────────
        card = _card(self, title="CAMERA CONTROL")

        self._cam_status = tk.StringVar(value="● Stopped")
        status_lbl = tk.Label(card, textvariable=self._cam_status,
                              bg=s.SURFACE, fg=s.ACCENT_WARN,
                              font=("Consolas", 12, "bold"))
        status_lbl.pack(anchor="w", pady=(0, 12))

        btn_frame = tk.Frame(card, bg=s.SURFACE)
        btn_frame.pack(anchor="w")

        self._start_btn = tk.Button(btn_frame, text="▶  Start Camera",
                                    command=self._start_camera, **s.BTN_ACCENT)
        self._start_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = tk.Button(btn_frame, text="■  Stop Camera",
                                   command=self._stop_camera,
                                   state="disabled", **s.BTN)
        self._stop_btn.pack(side="left")

        _divider(self)

        # ── Profile selector ──────────────────────
        prof_card = _card(self, title="ACTIVE PROFILE")
        self._profile_var = tk.StringVar(value=self.ctrl.active_profile)

        for p in config.PROFILES:
            rb = tk.Radiobutton(
                prof_card, text=p,
                variable=self._profile_var, value=p,
                command=self._change_profile,
                bg=s.SURFACE, fg=s.TEXT_PRIMARY,
                selectcolor=s.SURFACE2,
                activebackground=s.SURFACE2,
                activeforeground=s.ACCENT,
                font=s.FONT_BODY,
            )
            rb.pack(side="left", padx=14)

        _divider(self)

        # ── Quick stats row ───────────────────────
        stats_card = _card(self, title="SESSION STATS")
        self._fps_var    = tk.StringVar(value="FPS:  —")
        self._gest_var   = tk.StringVar(value="Last Gesture:  —")
        self._action_var = tk.StringVar(value="Last Action:  —")

        for var in (self._fps_var, self._gest_var, self._action_var):
            tk.Label(stats_card, textvariable=var,
                     bg=s.SURFACE, fg=s.TEXT_PRIMARY,
                     font=s.FONT_BODY).pack(anchor="w", pady=2)

        # ── Feature grid ──────────────────────────
        _divider(self)
        feat_frame = tk.Frame(self, bg=s.BG)
        feat_frame.pack(fill="x", padx=40, pady=10)

        tk.Label(feat_frame, text="FEATURES", bg=s.BG, fg=s.ACCENT2,
                 font=s.FONT_HEADING).pack(anchor="w", pady=(0, 8))

        features = [
            ("🖱️  Virtual Mouse",       "Index finger → cursor"),
            ("👆  Click Gestures",       "Pinch combos for L/R click"),
            ("🔊  Volume Control",       "Thumb-Index distance"),
            ("🔆  Brightness",           "Left hand gesture"),
            ("📸  Screenshot",           "Open palm"),
            ("🎨  Drawing Board",        "Drawing profile"),
            ("📊  Presentation Mode",    "Swipe gestures"),
            ("🚀  App Launcher",         "Assign any app to a gesture"),
        ]

        cols = tk.Frame(feat_frame, bg=s.BG)
        cols.pack(fill="x")
        for i, (name, desc) in enumerate(features):
            col = i % 2
            row = i // 2
            cell = tk.Frame(cols, bg=s.SURFACE, pady=6, padx=10)
            cell.grid(row=row, column=col, sticky="ew", padx=4, pady=4)
            cols.grid_columnconfigure(col, weight=1)
            tk.Label(cell, text=name, bg=s.SURFACE, fg=s.TEXT_PRIMARY,
                     font=("Consolas", 10, "bold")).pack(anchor="w")
            tk.Label(cell, text=desc, bg=s.SURFACE, fg=s.TEXT_MUTED,
                     font=s.FONT_SMALL).pack(anchor="w")

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _start_camera(self):
        success = self.ctrl.start_camera()
        if success:
            self._cam_status.set("● Running")
            self._start_btn.config(state="disabled")
            self._stop_btn.config(state="normal")
            # Update status label colour via widget config
            for widget in self.winfo_children():
                pass  # label is a StringVar, updated via variable

    def _stop_camera(self):
        self.ctrl.stop_camera()
        self._cam_status.set("● Stopped")
        self._start_btn.config(state="normal")
        self._stop_btn.config(state="disabled")

    def _change_profile(self):
        self.ctrl.set_profile(self._profile_var.get())

    # ── Live update (called by App tick) ──────────────────────────────────────

    def update_stats(self, fps: float, gesture: str, action: str):
        self._fps_var.set(f"FPS:  {fps:.1f}")
        self._gest_var.set(f"Last Gesture:  {gesture}")
        self._action_var.set(f"Last Action:  {action}")

    @property
    def active_profile(self):
        return self._profile_var.get()


# ── Shared layout helpers ─────────────────────────────────────────────────────

def _divider(parent):
    tk.Frame(parent, bg=s.BORDER, height=1).pack(fill="x", padx=40, pady=8)


def _card(parent, title: str) -> tk.Frame:
    outer = tk.Frame(parent, bg=s.BG)
    outer.pack(fill="x", padx=40, pady=4)
    tk.Label(outer, text=title, bg=s.BG, fg=s.ACCENT2,
             font=("Consolas", 10, "bold")).pack(anchor="w", pady=(0, 4))
    inner = tk.Frame(outer, bg=s.SURFACE, padx=16, pady=12)
    inner.pack(fill="x")
    return inner
