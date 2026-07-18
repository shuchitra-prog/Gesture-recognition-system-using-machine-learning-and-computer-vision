# gui/settings_page.py
# Settings page — camera, sensitivity, thresholds, theme, app launcher.

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from gui import styles as s
import config


class SettingsPage(tk.Frame):
    """Provides controls for all tunable parameters, saved to SQLite."""

    def __init__(self, parent, app_controller, **kwargs):
        super().__init__(parent, bg=s.BG, **kwargs)
        self.ctrl = app_controller
        self.db   = app_controller.db
        self._vars = {}     # key → StringVar
        self._build()
        self._load_values()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        hdr = tk.Frame(self, bg=s.BG)
        hdr.pack(fill="x", padx=40, pady=(30, 10))
        tk.Label(hdr, text="SETTINGS", bg=s.BG, fg=s.ACCENT,
                 font=s.FONT_TITLE).pack(anchor="w")
        tk.Label(hdr, text="Adjust camera, sensitivity and threshold parameters.",
                 bg=s.BG, fg=s.TEXT_MUTED, font=s.FONT_SMALL).pack(anchor="w")

        _div(self)

        # Scrollable container
        canvas   = tk.Canvas(self, bg=s.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self._scroll_frame = tk.Frame(canvas, bg=s.BG)
        self._scroll_frame.bind("<Configure>",
                                lambda e: canvas.configure(
                                    scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ── Sections ──────────────────────────────
        self._build_section("CAMERA",
            [("Camera Index",   "camera_index",    "0",    "int"),
             ("Width (px)",     "camera_width",    "960", "int"),
             ("Height (px)",    "camera_height",   "540",  "int"),
             ("FPS Limit",      "fps_limit",       "30",   "int")])

        self._build_section("MOUSE",
            [("Sensitivity",       "sensitivity",       "2.5", "float"),
             ("Smoothing Window",  "smoothing",         "5",   "int"),
             ("Pinch Threshold",   "pinch_threshold",   "40",  "int"),
             ("Click Cooldown ms", "click_cooldown_ms", "450", "int")])

        self._build_section("MEDIAPIPE",
            [("Detection Confidence",  "mp_detection_conf",  "0.75", "float"),
             ("Tracking Confidence",   "mp_tracking_conf",   "0.65", "float"),
             ("Max Hands",             "mp_max_hands",       "1",   "int")])

        self._build_app_section()

        _div(self._scroll_frame)

        # Save button
        tk.Button(self._scroll_frame, text="💾  Save Settings",
                  command=self._save, **s.BTN_ACCENT).pack(
                  anchor="e", padx=40, pady=16)

    def _build_section(self, title, fields):
        parent = self._scroll_frame
        tk.Label(parent, text=title, bg=s.BG, fg=s.ACCENT2,
                 font=s.FONT_HEADING).pack(anchor="w", padx=40, pady=(16, 4))

        card = tk.Frame(parent, bg=s.SURFACE, padx=20, pady=12)
        card.pack(fill="x", padx=40, pady=(0, 4))

        for label, key, default, dtype in fields:
            row = tk.Frame(card, bg=s.SURFACE)
            row.pack(fill="x", pady=3)

            tk.Label(row, text=label, bg=s.SURFACE, fg=s.TEXT_MUTED,
                     font=s.FONT_BODY, width=22, anchor="w").pack(side="left")

            var = tk.StringVar(value=default)
            self._vars[key] = (var, dtype)
            tk.Entry(row, textvariable=var, **s.ENTRY, width=14).pack(side="left")

    def _build_app_section(self):
        parent = self._scroll_frame
        tk.Label(parent, text="APP LAUNCHER", bg=s.BG, fg=s.ACCENT2,
                 font=s.FONT_HEADING).pack(anchor="w", padx=40, pady=(16, 4))

        card = tk.Frame(parent, bg=s.SURFACE, padx=20, pady=12)
        card.pack(fill="x", padx=40, pady=(0, 4))

        self._app_vars = {}
        for app_name, default_cmd in config.DEFAULT_APPS.items():
            row = tk.Frame(card, bg=s.SURFACE)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=app_name, bg=s.SURFACE, fg=s.TEXT_MUTED,
                     font=s.FONT_BODY, width=14, anchor="w").pack(side="left")
            var = tk.StringVar(value=default_cmd)
            self._app_vars[app_name] = var
            tk.Entry(row, textvariable=var, **s.ENTRY, width=40).pack(side="left", padx=4)
            tk.Button(row, text="Browse",
                      command=lambda v=var: self._browse(v),
                      **s.BTN).pack(side="left")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_values(self):
        all_settings = self.db.get_all_settings()
        for key, (var, dtype) in self._vars.items():
            if key in all_settings:
                var.set(all_settings[key])

    def _save(self):
        try:
            for key, (var, dtype) in self._vars.items():
                raw = var.get().strip()
                # Validate type
                if dtype == "int":
                    int(raw)
                elif dtype == "float":
                    float(raw)
                self.db.set_setting(key, raw)

            # App commands
            for app_name, var in self._app_vars.items():
                self.db.set_setting(f"app_{app_name.lower().replace(' ', '_')}", var.get())

            messagebox.showinfo("Settings Saved", "Settings have been saved.\n"
                                "Restart the camera to apply hardware changes.")
        except ValueError as e:
            messagebox.showerror("Validation Error", str(e))

    def _browse(self, var: tk.StringVar):
        path = filedialog.askopenfilename(title="Select Executable")
        if path:
            var.set(path)


# ── helpers ───────────────────────────────────────────────────────────────────

def _div(parent):
    tk.Frame(parent, bg=s.BORDER, height=1).pack(fill="x", padx=40, pady=4)
