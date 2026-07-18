# gui/stats_page.py
# Statistics page — session time, gesture counts, action frequency.

import tkinter as tk
from tkinter import ttk
from gui import styles as s
from gui.gesture_manager_page import _apply_tree_style
import time


class StatsPage(tk.Frame):
    """Displays accumulated usage statistics from the SQLite stats table."""

    def __init__(self, parent, app_controller, **kwargs):
        super().__init__(parent, bg=s.BG, **kwargs)
        self.ctrl = app_controller
        self.db   = app_controller.db
        self._session_start = time.time()
        self._build()
        self.refresh()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        hdr = tk.Frame(self, bg=s.BG)
        hdr.pack(fill="x", padx=40, pady=(30, 10))
        tk.Label(hdr, text="STATISTICS", bg=s.BG, fg=s.ACCENT,
                 font=s.FONT_TITLE).pack(anchor="w")
        tk.Label(hdr, text="Usage data recorded in the local SQLite database.",
                 bg=s.BG, fg=s.TEXT_MUTED, font=s.FONT_SMALL).pack(anchor="w")

        tk.Frame(self, bg=s.BORDER, height=1).pack(fill="x", padx=40, pady=8)

        # Summary cards
        summary = tk.Frame(self, bg=s.BG)
        summary.pack(fill="x", padx=40, pady=(0, 16))
        summary.columnconfigure((0, 1, 2), weight=1)

        self._total_var   = tk.StringVar(value="0")
        self._session_var = tk.StringVar(value="0:00")
        self._top_var     = tk.StringVar(value="—")

        for col, (lbl, var, color) in enumerate([
            ("Total Gestures",   self._total_var,   s.ACCENT),
            ("Session Duration", self._session_var, s.ACCENT2),
            ("Top Gesture",      self._top_var,     "#FFD700"),
        ]):
            card = tk.Frame(summary, bg=s.SURFACE, padx=16, pady=12)
            card.grid(row=0, column=col, sticky="ew", padx=6)
            tk.Label(card, text=lbl, bg=s.SURFACE, fg=s.TEXT_MUTED,
                     font=s.FONT_SMALL).pack(anchor="w")
            tk.Label(card, textvariable=var, bg=s.SURFACE, fg=color,
                     font=("Consolas", 22, "bold")).pack(anchor="w")

        # Top gestures table
        tk.Label(self, text="TOP GESTURES", bg=s.BG, fg=s.ACCENT2,
                 font=s.FONT_HEADING).pack(anchor="w", padx=40, pady=(8, 4))

        tree_frame = tk.Frame(self, bg=s.BG)
        tree_frame.pack(fill="both", expand=True, padx=40, pady=(0, 8))

        cols = ("rank", "gesture", "count")
        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                  show="headings", height=12)
        _apply_tree_style(self._tree)

        for col, width in zip(cols, (50, 250, 100)):
            self._tree.heading(col, text=col.upper())
            self._tree.column(col, width=width, anchor="w")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Refresh button
        tk.Button(self, text="↺ Refresh", command=self.refresh,
                  **s.BTN).pack(anchor="e", padx=40, pady=8)

    # ── Data ──────────────────────────────────────────────────────────────────

    def refresh(self):
        stats = self.db.get_stats()
        self._total_var.set(str(stats["total"]))

        if stats["top_gestures"]:
            self._top_var.set(stats["top_gestures"][0]["gesture_name"])

        for row in self._tree.get_children():
            self._tree.delete(row)
        for rank, g in enumerate(stats["top_gestures"], 1):
            self._tree.insert("", "end",
                              values=(rank, g["gesture_name"], g["cnt"]))

        # Update session time
        elapsed = int(time.time() - self._session_start)
        m, s_  = divmod(elapsed, 60)
        h, m   = divmod(m, 60)
        self._session_var.set(f"{h}:{m:02}:{s_:02}")

    def tick(self):
        """Call every second from the main app loop."""
        elapsed = int(time.time() - self._session_start)
        m, s_ = divmod(elapsed, 60)
        h, m  = divmod(m, 60)
        self._session_var.set(f"{h}:{m:02}:{s_:02}")
