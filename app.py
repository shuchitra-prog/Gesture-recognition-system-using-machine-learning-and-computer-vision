#!/usr/bin/env python3
# app.py
# ─────────────────────────────────────────────────────────────────────────────
# Real-Time Gesture Controlled Computer
# Entry point: creates the Tkinter window, starts the camera thread,
# runs the MediaPipe processing loop, and wires all GUI pages together.
# ─────────────────────────────────────────────────────────────────────────────

import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Optional

import cv2
import pyautogui
import numpy as np

# ── Project imports ───────────────────────────────────────────────────────────
import config
from utils              import get_logger
from utils.helpers      import FPSCounter
from database           import DBManager
from cv.hand_tracker    import HandTracker
from cv.camera_thread   import CameraThread
from cv.overlay         import draw_hud, draw_pinch_line
from gestures           import GestureController
from gui                import styles as s
from gui.home_page      import HomePage
from gui.gesture_manager_page import GestureManagerPage
from gui.settings_page  import SettingsPage
from gui.stats_page     import StatsPage

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  APPLICATION
# ─────────────────────────────────────────────────────────────────────────────

class App:
    """
    Top-level application controller.

    Responsibilities:
      - Tkinter root window + navigation sidebar
      - Camera / processing lifecycle (start / stop / process loop)
      - Shared state (db, active_profile, fps …) accessible by all pages
    """

    def __init__(self):
        # ── Database ──────────────────────────────
        self.db = DBManager()
        self.active_profile = self.db.get_setting("active_profile", config.DEFAULT_PROFILE)

        # ── System screen size ────────────────────
        self.screen_w, self.screen_h = pyautogui.size()

        # ── Runtime state ─────────────────────────
        self._camera:     Optional[CameraThread]     = None
        self._tracker:    Optional[HandTracker]      = None
        self._controller: Optional[GestureController] = None
        # The classifier is the primary recogniser when a trained model exists.
        # Its on-screen label remains optional to avoid cluttering the preview.
        self._predictor = None
        if config.ENABLE_ML_PRIMARY or config.ENABLE_ML_OVERLAY:
            from ml import GesturePredictor
            self._predictor = GesturePredictor()
        self._fps         = FPSCounter()
        self._running     = False
        self._proc_thread: Optional[threading.Thread] = None

        # ── Build GUI ─────────────────────────────
        self._build_window()
        self._bind_close()

        logger.info("App initialised. Screen=%dx%d Profile=%s",
                    self.screen_w, self.screen_h, self.active_profile)

    # ──────────────────────────────────────────────────────────────────────────
    #  GUI construction
    # ──────────────────────────────────────────────────────────────────────────

    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("Gesture Controlled Computer")
        self.root.geometry(f"{config.GUI_WIDTH}x{config.GUI_HEIGHT}")
        self.root.configure(bg=s.BG)
        self.root.resizable(True, True)
        self.root.minsize(900, 580)

        # ── Sidebar ───────────────────────────────
        sidebar = tk.Frame(self.root, bg=s.SURFACE, width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Logo
        tk.Label(sidebar,
                 text="◈ GCC",
                 bg=s.SURFACE, fg=s.ACCENT,
                 font=("Consolas", 18, "bold")).pack(pady=(24, 4))
        tk.Label(sidebar,
                 text="Gesture Control",
                 bg=s.SURFACE, fg=s.TEXT_MUTED,
                 font=s.FONT_SMALL).pack(pady=(0, 20))

        tk.Frame(sidebar, bg=s.BORDER, height=1).pack(fill="x", padx=16, pady=4)

        # Content area
        self._content = tk.Frame(self.root, bg=s.BG)
        self._content.pack(side="right", fill="both", expand=True)

        # ── Pages ─────────────────────────────────
        self._pages: dict = {}
        self._active_page: Optional[tk.Frame] = None

        page_classes = [
            ("🏠  Home",             "home",     HomePage),
            ("👌  Gesture Manager",  "gestures", GestureManagerPage),
            ("⚙️  Settings",          "settings", SettingsPage),
            ("📊  Statistics",       "stats",    StatsPage),
        ]

        for label, key, PageClass in page_classes:
            page = PageClass(self._content, app_controller=self)
            self._pages[key] = page

            btn = tk.Button(
                sidebar, text=label,
                command=lambda k=key: self._show_page(k),
                **s.BTN,
                anchor="w", width=18,
            )
            btn.pack(fill="x", padx=12, pady=2)

        # Camera preview label (below nav)
        tk.Frame(sidebar, bg=s.BORDER, height=1).pack(fill="x", padx=16, pady=12)
        self._preview_lbl = tk.Label(sidebar, bg=s.SURFACE,
                                     text="No Camera", fg=s.TEXT_MUTED,
                                     font=s.FONT_SMALL)
        self._preview_lbl.pack(padx=8, pady=4)

        # Show home page by default
        self._show_page("home")

    def _show_page(self, key: str):
        if self._active_page:
            self._active_page.pack_forget()
        self._active_page = self._pages[key]
        self._active_page.pack(fill="both", expand=True)

    def _bind_close(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.stop_camera()
        self.db.close()
        self.root.destroy()

    # ──────────────────────────────────────────────────────────────────────────
    #  Camera lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def start_camera(self) -> bool:
        if self._running:
            return True

        # Re-read settings that might have changed
        w   = int(self.db.get_setting("camera_width",  config.CAMERA_WIDTH))
        h   = int(self.db.get_setting("camera_height", config.CAMERA_HEIGHT))
        fps = int(self.db.get_setting("fps_limit",     config.CAMERA_FPS_LIMIT))
        idx = int(self.db.get_setting("camera_index",  config.CAMERA_INDEX))

        det_conf = float(self.db.get_setting("mp_detection_conf", config.MP_MIN_DETECTION_CONF))
        trk_conf = float(self.db.get_setting("mp_tracking_conf",  config.MP_MIN_TRACKING_CONF))
        max_h    = int(self.db.get_setting("mp_max_hands", config.MP_MAX_HANDS))

        self._camera = CameraThread(index=idx, width=w, height=h, fps_limit=fps)
        if not self._camera.start():
            messagebox.showerror("Camera Error",
                                 f"Cannot open camera index {idx}.\n"
                                 "Check your webcam connection.")
            return False

        self._tracker = HandTracker(
            max_hands=max_h,
            min_detection_confidence=det_conf,
            min_tracking_confidence=trk_conf,
            model_complexity=config.MP_MODEL_COMPLEXITY,
        )
        self._controller = GestureController(
            db=self.db,
            screen_size=(self.screen_w, self.screen_h),
            frame_size=(w, h),
            on_screenshot=self._on_screenshot,
            on_drawing_saved=self._on_drawing_saved,
            predictor=self._predictor,
        )
        self._controller.set_profile(self.active_profile)

        self._running = True
        self._proc_thread = threading.Thread(
            target=self._processing_loop, daemon=True)
        self._proc_thread.start()

        # Start GUI update ticker
        self.root.after(50, self._gui_tick)

        logger.info("Camera started.")
        return True

    def stop_camera(self):
        self._running = False
        if self._camera:
            self._camera.stop()
        if self._tracker:
            self._tracker.close()
        self._camera     = None
        self._tracker    = None
        self._controller = None
        logger.info("Camera stopped.")

    # ──────────────────────────────────────────────────────────────────────────
    #  Processing loop (background thread)
    # ──────────────────────────────────────────────────────────────────────────

    def _processing_loop(self):
        """
        Runs in a daemon thread:
          1. Grab frame from CameraThread
          2. Run MediaPipe HandTracker
          3. Run GestureController (detects gestures → executes actions)
          4. Draw HUD overlay
          5. Show frame in OpenCV window
        """
        cv2.namedWindow("Gesture Camera", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Gesture Camera", 960, 540)

        while self._running:
            frame = self._camera.read() if self._camera else None
            if frame is None:
                if self._camera is not None and not self._camera.running:
                    logger.error("Camera stream stopped unexpectedly.")
                    self.root.after(0, self.stop_camera)
                    break
                time.sleep(0.01)
                continue

            # Track hands
            frame, hands = self._tracker.process(frame)

            # Optional ML prediction overlay
            if self._predictor is not None:
                if not hands:
                    self._predictor.reset()
            if self._predictor is not None and config.ENABLE_ML_OVERLAY:
                for hand in hands:
                    pred = self._predictor.predict(hand)
                    if pred:
                        name, conf = pred
                        tip = hand.tip("INDEX")
                        cv2.putText(frame, f"ML: {name} {conf:.0%}",
                                    (tip[0]+10, tip[1]-10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                                    (200, 200, 0), 1, cv2.LINE_AA)

            # Gesture → action
            frame = self._controller.process_hands(hands, frame)

            # Pinch visualisation for right hand
            for hand in hands:
                if hand.handedness == "Right":
                    draw_pinch_line(frame,
                                    hand.tip("THUMB"), hand.tip("INDEX"),
                                    hand.pinch_distance("THUMB", "INDEX"),
                                    float(self.db.get_setting(
                                        "pinch_threshold", config.PINCH_THRESHOLD)))

            # HUD overlay
            fps = self._fps.tick()
            draw_hud(frame, fps, self._controller.hud)

            # Store for GUI sidebar preview
            self._last_frame = frame
            self._last_fps   = fps

            cv2.imshow("Gesture Camera", frame)
            key = cv2.waitKey(1)
            if key == ord("q") or key == 27:   # Q or ESC
                self._running = False
                break

        cv2.destroyWindow("Gesture Camera")

    # ──────────────────────────────────────────────────────────────────────────
    #  GUI tick (runs on Tkinter main thread)
    # ──────────────────────────────────────────────────────────────────────────

    def _gui_tick(self):
        if not self._running:
            return

        # Update home page stats
        if self._controller:
            hud = self._controller.hud
            home: HomePage = self._pages.get("home")
            if home:
                home.update_stats(
                    fps     = getattr(self, "_last_fps", 0),
                    gesture = hud.get("gesture", "—"),
                    action  = hud.get("action",  "—"),
                )

        # Tick stats page timer
        stats: StatsPage = self._pages.get("stats")
        if stats:
            stats.tick()

        self.root.after(200, self._gui_tick)

    # ──────────────────────────────────────────────────────────────────────────
    #  Callbacks
    # ──────────────────────────────────────────────────────────────────────────

    def set_profile(self, profile: str):
        self.active_profile = profile
        if self._controller:
            self._controller.set_profile(profile)

    def _on_screenshot(self, path: str):
        # Avoid a modal popup: it steals focus and makes gesture control feel
        # frozen. The event is still logged with the exact saved location.
        logger.info("Screenshot saved: %s", path)

    def _on_drawing_saved(self, path: str):
        self.root.after(0, lambda: messagebox.showinfo(
            "Drawing Saved", f"Saved to:\n{path}"))

    # ──────────────────────────────────────────────────────────────────────────
    #  Run
    # ──────────────────────────────────────────────────────────────────────────

    def run(self):
        logger.info("Starting Tkinter main loop.")
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.run()
