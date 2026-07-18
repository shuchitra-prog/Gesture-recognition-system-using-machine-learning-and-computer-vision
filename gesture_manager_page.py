# gui/gesture_manager_page.py
# Page for viewing, adding, editing and deleting gesture mappings.

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from gui import styles as s
import config


class GestureManagerPage(tk.Frame):
    """CRUD interface for gesture → action mappings stored in SQLite."""

    def __init__(self, parent, app_controller, **kwargs):
        super().__init__(parent, bg=s.BG, **kwargs)
        self.ctrl = app_controller
        self.db   = app_controller.db
        self._build()
        self.refresh()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=s.BG)
        hdr.pack(fill="x", padx=40, pady=(30, 10))
        tk.Label(hdr, text="GESTURE MANAGER", bg=s.BG, fg=s.ACCENT,
                 font=s.FONT_TITLE).pack(anchor="w")
        tk.Label(hdr, text="Add, edit or delete gesture → action mappings per profile.",
                 bg=s.BG, fg=s.TEXT_MUTED, font=s.FONT_SMALL).pack(anchor="w")

        tk.Frame(self, bg=s.BORDER, height=1).pack(fill="x", padx=40, pady=8)

        # Profile filter
        filter_frame = tk.Frame(self, bg=s.BG)
        filter_frame.pack(fill="x", padx=40, pady=(0, 8))
        tk.Label(filter_frame, text="Profile:", bg=s.BG, fg=s.TEXT_MUTED,
                 font=s.FONT_BODY).pack(side="left")

        self._profile_var = tk.StringVar(value="All")
        profiles = ["All"] + config.PROFILES
        prof_menu = ttk.Combobox(filter_frame, textvariable=self._profile_var,
                                 values=profiles, state="readonly", width=14)
        prof_menu.pack(side="left", padx=8)
        prof_menu.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        # Treeview
        tree_frame = tk.Frame(self, bg=s.BG)
        tree_frame.pack(fill="both", expand=True, padx=40, pady=(0, 8))

        cols = ("id", "gesture", "action", "profile")
        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                  show="headings", selectmode="browse")

        _apply_tree_style(self._tree)

        for col, width in zip(cols, (40, 200, 200, 120)):
            self._tree.heading(col, text=col.upper())
            self._tree.column(col, width=width, anchor="w")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical",
                                  command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Action buttons
        btn_row = tk.Frame(self, bg=s.BG)
        btn_row.pack(fill="x", padx=40, pady=(0, 20))

        tk.Button(btn_row, text="＋ Add",    command=self._add,    **s.BTN_ACCENT).pack(side="left", padx=(0,6))
        tk.Button(btn_row, text="✎ Edit",    command=self._edit,   **s.BTN).pack(side="left", padx=(0,6))
        tk.Button(btn_row, text="✕ Delete",  command=self._delete, **s.BTN_WARN).pack(side="left", padx=(0,6))
        tk.Button(btn_row, text="↺ Refresh", command=self.refresh, **s.BTN).pack(side="right")

    # ── Data operations ───────────────────────────────────────────────────────

    def refresh(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        profile = self._profile_var.get()
        gestures = self.db.get_gestures(None if profile == "All" else profile)
        for g in gestures:
            self._tree.insert("", "end",
                              values=(g["id"], g["gesture_name"],
                                      g["action_name"], g["profile"]))

    def _get_selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("Select Row", "Please select a gesture first.")
            return None
        return self._tree.item(sel[0])["values"]

    def _add(self):
        dialog = GestureDialog(self, title="Add Gesture", db=self.db)
        self.wait_window(dialog)
        self.refresh()

    def _edit(self):
        row = self._get_selected()
        if not row:
            return
        dialog = GestureDialog(self, title="Edit Gesture", db=self.db,
                               gesture_id=row[0],
                               gesture_name=row[1],
                               action_name=row[2],
                               profile=row[3])
        self.wait_window(dialog)
        self.refresh()

    def _delete(self):
        row = self._get_selected()
        if not row:
            return
        if messagebox.askyesno("Confirm Delete",
                               f"Delete gesture '{row[1]}'?"):
            self.db.delete_gesture(row[0])
            self.refresh()


# ── Add / Edit dialog ─────────────────────────────────────────────────────────

class GestureDialog(tk.Toplevel):

    KNOWN_ACTIONS = [
        "mouse_move", "left_click", "right_click", "double_click", "drag",
        "scroll_up", "scroll_down", "volume_control", "brightness_control",
        "play_pause", "next_track", "prev_track",
        "next_slide", "prev_slide", "laser_pointer",
        "screenshot", "draw", "eraser", "save_drawing",
    ]

    def __init__(self, parent, title, db,
                 gesture_id=None, gesture_name="", action_name="", profile="Normal"):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=s.BG)
        self.resizable(False, False)
        self.db = db
        self.gesture_id = gesture_id

        self._build(gesture_name, action_name, profile)
        self.grab_set()

    def _build(self, gesture_name, action_name, profile):
        pad = {"padx": 20, "pady": 8}

        tk.Label(self, text="Gesture Name:", **s.LABEL).grid(row=0, column=0, sticky="w", **pad)
        self._name_var = tk.StringVar(value=gesture_name)
        tk.Entry(self, textvariable=self._name_var, **s.ENTRY, width=28).grid(row=0, column=1, **pad)

        tk.Label(self, text="Action:", **s.LABEL).grid(row=1, column=0, sticky="w", **pad)
        self._action_var = tk.StringVar(value=action_name)
        ttk.Combobox(self, textvariable=self._action_var,
                     values=self.KNOWN_ACTIONS, width=26).grid(row=1, column=1, **pad)

        tk.Label(self, text="Profile:", **s.LABEL).grid(row=2, column=0, sticky="w", **pad)
        self._profile_var = tk.StringVar(value=profile)
        ttk.Combobox(self, textvariable=self._profile_var,
                     values=config.PROFILES, state="readonly",
                     width=26).grid(row=2, column=1, **pad)

        btn_row = tk.Frame(self, bg=s.BG)
        btn_row.grid(row=3, column=0, columnspan=2, pady=12)
        tk.Button(btn_row, text="Save", command=self._save, **s.BTN_ACCENT).pack(side="left", padx=6)
        tk.Button(btn_row, text="Cancel", command=self.destroy, **s.BTN).pack(side="left")

    def _save(self):
        name    = self._name_var.get().strip()
        action  = self._action_var.get().strip()
        profile = self._profile_var.get()

        if not name or not action:
            messagebox.showerror("Validation", "Name and Action are required.")
            return

        if self.gesture_id:
            self.db.update_gesture(self.gesture_id, name, action, profile)
        else:
            self.db.add_gesture(name, action, profile)
        self.destroy()


# ── Treeview styling helper ───────────────────────────────────────────────────

def _apply_tree_style(tree: ttk.Treeview):
    style = ttk.Style()
    style.theme_use("default")
    style.configure("Treeview",
                    background=s.SURFACE,
                    foreground=s.TEXT_PRIMARY,
                    fieldbackground=s.SURFACE,
                    rowheight=28,
                    font=s.FONT_BODY)
    style.configure("Treeview.Heading",
                    background=s.SURFACE2,
                    foreground=s.ACCENT2,
                    font=("Consolas", 10, "bold"))
    style.map("Treeview", background=[("selected", s.BORDER)])
