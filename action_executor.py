# gestures/action_executor.py
# Translates gesture names → concrete system actions.
# Each action method is called by GestureController when a gesture is confirmed.

import os
import time
import subprocess
import threading
from typing import Tuple, Optional, Callable
from datetime import datetime

import pyautogui
import numpy as np

from utils.helpers import CursorSmoother, Cooldown
from utils import get_logger
import config

logger = get_logger(__name__)

# Keep the PyAutoGUI fail-safe enabled: moving the cursor to the top-left corner
# remains an immediate escape hatch if a gesture is misread.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0

# ── Optional system-level imports (graceful fallback) ─────────────────────────

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    _PYCAW_AVAILABLE = True
except ImportError:
    _PYCAW_AVAILABLE = False
    logger.warning("pycaw not available — volume control will use pyautogui fallback.")

try:
    import screen_brightness_control as sbc
    _SBC_AVAILABLE = True
except ImportError:
    _SBC_AVAILABLE = False
    logger.warning("screen-brightness-control not available — brightness control disabled.")

try:
    from plyer import notification as _plyer_notification
    _PLYER_AVAILABLE = True
except ImportError:
    _PLYER_AVAILABLE = False
    logger.warning("plyer not available — screenshot notifications will use fallback.")


class ActionExecutor:
    """
    Executes system actions triggered by gestures.

    Maintains internal state for:
      - mouse smoothing
      - drag-and-drop
      - volume / brightness tracking
      - drawing canvas state
    """

    def __init__(self, screen_w: int, screen_h: int,
                 frame_w: int, frame_h: int,
                 sensitivity: float = None,
                 smoothing: int = None):

        self.screen_w = screen_w
        self.screen_h = screen_h
        self.frame_w  = frame_w
        self.frame_h  = frame_h
        self.sensitivity = sensitivity or config.MOUSE_SENSITIVITY
        # Use the One Euro based CursorSmoother for jitter-free, low-lag cursor
        self.smoother = CursorSmoother()

        # Click cooldowns
        self._click_cd  = Cooldown(config.CLICK_COOLDOWN_MS)
        self._action_cd = Cooldown(500)   # generic action cooldown
        self._screenshot_cd = Cooldown(config.SCREENSHOT_COOLDOWN_MS)
        self._scroll_cd = Cooldown(45)
        self._level_cd = Cooldown(55)
        self._pending_volume_delta = 0.0
        self._pending_brightness_delta = 0.0
        self._pending_scroll_delta = 0.0
        self._volume_motion_state = 0.0
        self._brightness_motion_state = 0.0

        # Drag state
        self._dragging   = False
        self._drag_start: Optional[Tuple[int, int]] = None
        self._drag_release_grace = 0   # frames remaining before actual release

        # Volume
        self._vol_interface = None
        self._volume_thread_id = None

        # Current brightness (cached)
        self._brightness = 50
        self._volume = 50.0
        if _SBC_AVAILABLE:
            try:
                self._brightness = sbc.get_brightness(display=0)[0]
            except Exception:
                pass

        # Drawing canvas (shared numpy array, written by caller)
        self.draw_canvas: Optional[np.ndarray] = None
        self._drawing      = False
        self._prev_draw_pt: Optional[Tuple[int, int]] = None
        self.brush_color   = config.DEFAULT_BRUSH_COLOR
        self.brush_size    = config.DEFAULT_BRUSH_SIZE
        self.eraser_mode   = False

        # Status string for HUD
        self.last_action = "—"

        logger.info("ActionExecutor ready (screen %dx%d).", screen_w, screen_h)

    # ── Volume init ───────────────────────────────────────────────────────────

    def _init_volume(self):
        """Create a Core Audio endpoint in the thread that uses it.

        The controller is constructed on Tk's thread but actions run on the
        processing thread. COM interfaces are apartment-bound, so creating the
        endpoint in ``__init__`` made volume calls fail on Windows.
        """
        if not _PYCAW_AVAILABLE:
            return False
        thread_id = threading.get_ident()
        if self._vol_interface is not None and self._volume_thread_id == thread_id:
            return True
        try:
            import comtypes
            comtypes.CoInitialize()
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._vol_interface = interface.QueryInterface(IAudioEndpointVolume)
            self._volume_thread_id = thread_id
            self._volume = self._vol_interface.GetMasterVolumeLevelScalar() * 100.0
            logger.info("Windows audio interface acquired.")
            return True
        except Exception as e:
            logger.warning("Volume init failed: %s", e)
            self._vol_interface = None
            self._volume_thread_id = None
            return False

    # ── MOUSE MOVE ────────────────────────────────────────────────────────────

    def mouse_move(self, index_tip: Tuple[int, int], **_):
        """Map index finger position to screen coordinates and move the cursor."""
        tx, ty = self._screen_point(index_tip)
        sx, sy = self.smoother.update(tx, ty)
        sx, sy = int(sx), int(sy)
        try:
            pyautogui.moveTo(sx, sy, _pause=False)
        except Exception as e:
            logger.debug("moveTo error: %s", e)
        self.last_action = f"Mouse → ({sx},{sy})"

    def _screen_point(self, point: Tuple[int, int]) -> Tuple[int, int]:
        """Map the active camera region to every pixel of the primary screen."""
        region = max(0.4, min(1.0, config.MOUSE_CONTROL_REGION))
        margin_x = self.frame_w * (1.0 - region) / 2.0
        margin_y = self.frame_h * (1.0 - region) / 2.0
        rx = max(0.0, min(1.0, (point[0] - margin_x) / (self.frame_w - 2 * margin_x)))
        ry = max(0.0, min(1.0, (point[1] - margin_y) / (self.frame_h - 2 * margin_y)))
        if rx <= config.MOUSE_EDGE_SNAP:
            rx = 0.0
        elif rx >= 1.0 - config.MOUSE_EDGE_SNAP:
            rx = 1.0
        if ry <= config.MOUSE_EDGE_SNAP:
            ry = 0.0
        elif ry >= 1.0 - config.MOUSE_EDGE_SNAP:
            ry = 1.0
        sx = int(rx * (self.screen_w - 1))
        sy = int(ry * (self.screen_h - 1))
        # MODIFIED — Clamp to avoid PyAutoGUI failsafe zone (top-left corner)
        # and ensure cursor stays within usable screen bounds.
        sx = max(2, min(self.screen_w - 3, sx))
        sy = max(2, min(self.screen_h - 3, sy))
        return sx, sy

    # ── CLICKS ────────────────────────────────────────────────────────────────

    def left_click(self, **_):
        if self._click_cd.ready():
            pyautogui.click(_pause=False)
            self.last_action = "Left Click"
            logger.debug("Left click.")

    def right_click(self, **_):
        if self._click_cd.ready():
            pyautogui.rightClick(_pause=False)
            self.last_action = "Right Click"

    def double_click(self, **_):
        if self._click_cd.ready():
            pyautogui.doubleClick(interval=0.12, _pause=False)
            self.last_action = "Double Click"

    # ── DRAG AND DROP ─────────────────────────────────────────────────────────

    def drag(self, index_tip: Tuple[int, int], **_):
        tx, ty = self._screen_point(index_tip)

        # Cancel any pending release — the user is still dragging
        self._drag_release_grace = 0

        if not self._dragging:
            # Start the drag at the tracked finger, not at a stale cursor
            # position from before the gesture began.
            self.mouse_move(index_tip)
            pyautogui.mouseDown(_pause=False)
            self._dragging = True
            self._drag_start = (tx, ty)
            self.last_action = "Drag Start"
        else:
            sx, sy = self.smoother.update(tx, ty)
            pyautogui.moveTo(int(sx), int(sy), _pause=False)
            self.last_action = "Dragging…"

    def request_drag_release(self):
        """Begin a grace-period countdown before releasing a drag.

        This prevents a single flickered frame from releasing the drag.
        Call this every frame where drag is NOT in the active set.
        Returns True when the drag has actually been released.
        """
        if not self._dragging:
            return True
        self._drag_release_grace += 1
        if self._drag_release_grace >= config.DRAG_RELEASE_GRACE_FRAMES:
            self.release_drag()
            return True
        return False

    def release_drag(self):
        if self._dragging:
            pyautogui.mouseUp(_pause=False)
            self._dragging = False
            self._drag_release_grace = 0
            self.last_action = "Drag Release"

    # ── SCROLL ────────────────────────────────────────────────────────────────

    def _emit_scroll(self, direction: str, amount: int):
        if direction == "up":
            pyautogui.scroll(abs(amount), _pause=False)
            self.last_action = "Scroll ↑"
        else:
            pyautogui.scroll(-abs(amount), _pause=False)
            self.last_action = "Scroll ↓"

    def scroll_up(self, amount: float = 0.0, **_):
        self.scroll_motion(amount, direction="up")

    def scroll_down(self, amount: float = 0.0, **_):
        self.scroll_motion(amount, direction="down")

    def scroll_motion(self, vertical_delta: float = 0.0, direction: str = "up"):
        """Accumulate vertical motion and emit smooth, continuous scroll events.

        The *direction* parameter is used as a fallback when the sign of
        ``vertical_delta`` is ambiguous (e.g. zero).  For non-zero deltas, the
        sign of the delta itself determines the scroll direction — this fixes
        the old sign-confusion bug where the direction parameter and delta
        sometimes disagreed.
        """
        if vertical_delta is None:
            vertical_delta = 0.0
        if abs(vertical_delta) < config.SCROLL_JITTER_THRESHOLD:
            return

        # Use the sign of the actual delta to decide direction, regardless of
        # the `direction` parameter.  This avoids the old bug where
        # ``scroll_motion(-dy, direction="up")`` would double-invert the sign.
        effective_movement = abs(vertical_delta)
        if vertical_delta > 0:
            effective_direction = "down"
        elif vertical_delta < 0:
            effective_direction = "up"
        else:
            effective_direction = direction

        self._pending_scroll_delta += effective_movement * config.SCROLL_SENSITIVITY

        # Lower threshold for event-based scroll (from detector) to be more
        # responsive.  The old value was too high for the small deltas.
        threshold = max(2.0, config.SCROLL_TRIGGER_DISTANCE * 0.5)
        if self._pending_scroll_delta < threshold:
            return
        if not self._scroll_cd.ready():
            return

        step_amount = max(1, min(
            config.SCROLL_STEP,
            int(self._pending_scroll_delta / threshold),
        ))
        self._emit_scroll(effective_direction, step_amount)
        self._pending_scroll_delta -= threshold * step_amount
        # Don't let the accumulator go negative
        self._pending_scroll_delta = max(0.0, self._pending_scroll_delta)

    # ── VOLUME ────────────────────────────────────────────────────────────────

    def volume_control(self, vertical_delta: float = 0.0, **_):
        """Adjust volume from upward/downward motion while thumb-only is held."""
        if vertical_delta is None:
            vertical_delta = 0.0

        # Lazily initialise COM in the real-time processing thread. If this
        # fails (for example, no Windows endpoint), the keyboard fallback below
        # remains available.
        if _PYCAW_AVAILABLE:
            self._init_volume()

        if abs(vertical_delta) <= config.VOLUME_DEADZONE:
            return

        alpha = config.VOLUME_SMOOTHING_ALPHA
        smoothed_delta = alpha * vertical_delta + (1.0 - alpha) * self._volume_motion_state
        self._volume_motion_state = smoothed_delta
        self._pending_volume_delta += smoothed_delta * config.VOLUME_SENSITIVITY

        step_size = max(
            3.0,
            config.VOLUME_PIXELS_PER_STEP * 0.8 * max(0.1, config.VOLUME_SENSITIVITY),
        )
        if abs(self._pending_volume_delta) < step_size:
            return
        if not self._level_cd.ready():
            return

        delta = self._pending_volume_delta
        # Keep fractional remainder — don't zero the whole accumulator
        steps_consumed = int(abs(delta) / step_size)
        consumed = np.copysign(step_size * steps_consumed, delta)
        self._pending_volume_delta = delta - consumed
        delta_pct = -consumed / step_size
        self._volume = max(0.0, min(100.0, self._volume + delta_pct))
        try:
            if _PYCAW_AVAILABLE and self._vol_interface:
                self._vol_interface.SetMasterVolumeLevelScalar(self._volume / 100.0, None)
            else:
                raise RuntimeError("pycaw not available")
        except Exception as e:
            logger.debug("Volume set error: %s", e)
            key = "volumeup" if delta_pct > 0 else "volumedown"
            pyautogui.press(key, presses=max(1, round(abs(delta_pct))), _pause=False)
        self.last_action = f"Volume {int(self._volume)}%"

    # ── BRIGHTNESS ────────────────────────────────────────────────────────────

    def brightness_increase(self, **_):
        if not _SBC_AVAILABLE or not self._action_cd.ready():
            return
        try:
            cur = sbc.get_brightness(display=0)[0]
            sbc.set_brightness(min(100, cur + config.BRIGHTNESS_STEP), display=0)
            self.last_action = f"Brightness ↑ {min(100, cur + config.BRIGHTNESS_STEP)}%"
        except Exception as e:
            logger.debug("Brightness error: %s", e)

    def brightness_decrease(self, **_):
        if not _SBC_AVAILABLE or not self._action_cd.ready():
            return
        try:
            cur = sbc.get_brightness(display=0)[0]
            sbc.set_brightness(max(0, cur - config.BRIGHTNESS_STEP), display=0)
            self.last_action = f"Brightness ↓ {max(0, cur - config.BRIGHTNESS_STEP)}%"
        except Exception as e:
            logger.debug("Brightness error: %s", e)

    def brightness_control(self, vertical_delta: float = 0.0, **_):
        """Adjust brightness from vertical motion while four fingers are held."""
        if vertical_delta is None:
            vertical_delta = 0.0

        # Dead zone — ignore tiny jitter (same approach as volume)
        if abs(vertical_delta) <= config.BRIGHTNESS_DEADZONE:
            return

        # Temporal smoothing to prevent erratic jumps
        alpha = config.BRIGHTNESS_SMOOTHING_ALPHA
        smoothed = alpha * vertical_delta + (1.0 - alpha) * self._brightness_motion_state
        self._brightness_motion_state = smoothed

        self._pending_brightness_delta += smoothed
        if not _SBC_AVAILABLE or not self._level_cd.ready():
            return
        delta = self._pending_brightness_delta
        self._pending_brightness_delta = 0.0
        if abs(delta) < 1.0:
            return
        try:
            bri = int(max(0, min(100, self._brightness - delta / config.BRIGHTNESS_PIXELS_PER_STEP)))
            sbc.set_brightness(bri, display=0)
            self._brightness = bri
            self.last_action = f"Brightness {bri}%"
        except Exception as e:
            logger.debug("Brightness error: %s", e)

    def reset_level_motion(self, action: str):
        """Discard any motion collected before a continuous level pose ended."""
        if action == "volume_control":
            self._pending_volume_delta = 0.0
            self._volume_motion_state = 0.0
        elif action == "brightness_control":
            self._pending_brightness_delta = 0.0
            self._brightness_motion_state = 0.0
        elif action in {"scroll_up", "scroll_down"}:
            self._pending_scroll_delta = 0.0

    def full_reset(self):
        """Clear all internal state.  Called on tracking loss."""
        self.smoother.reset()
        self.release_drag()
        self.stop_drawing()
        self._pending_volume_delta = 0.0
        self._pending_brightness_delta = 0.0
        self._pending_scroll_delta = 0.0
        self._volume_motion_state = 0.0
        self._brightness_motion_state = 0.0
        self._drag_release_grace = 0
        self.last_action = "—"

    # ── MEDIA CONTROLS ────────────────────────────────────────────────────────

    def play_pause(self, **_):
        if self._action_cd.ready():
            pyautogui.press("playpause")
            self.last_action = "Play/Pause"

    def next_track(self, **_):
        if self._action_cd.ready():
            pyautogui.press("nexttrack")
            self.last_action = "Next Track"

    def prev_track(self, **_):
        if self._action_cd.ready():
            pyautogui.press("prevtrack")
            self.last_action = "Prev Track"

    # ── PRESENTATION ──────────────────────────────────────────────────────────

    def next_slide(self, **_):
        if self._action_cd.ready():
            pyautogui.press("right")
            self.last_action = "→ Next Slide"

    def prev_slide(self, **_):
        if self._action_cd.ready():
            pyautogui.press("left")
            self.last_action = "← Prev Slide"

    def laser_pointer(self, index_tip: Tuple[int, int], **_):
        """Move cursor to simulate a laser pointer."""
        self.mouse_move(index_tip)
        self.last_action = "🔴 Laser Pointer"

    # ── SCREENSHOT ────────────────────────────────────────────────────────────

    def screenshot(self, callback: Callable = None, **_):
        """Capture screen and save to SCREENSHOTS_DIR."""
        if not self._screenshot_cd.ready():
            return

        def _do():
            try:
                os.makedirs(config.SCREENSHOTS_DIR, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                path = os.path.join(config.SCREENSHOTS_DIR, f"screenshot_{ts}.png")
                img = pyautogui.screenshot()
                img.save(path)
                logger.info("Screenshot saved: %s", path)
                # Desktop notification
                self._notify_screenshot(path)
                if callback:
                    callback(path)
            except Exception as e:
                logger.error("Screenshot error: %s", e)

        threading.Thread(target=_do, daemon=True).start()
        self.last_action = "📸 Screenshot"

    def _notify_screenshot(self, path: str):
        """Show a desktop toast notification that a screenshot was saved."""
        try:
            if _PLYER_AVAILABLE:
                _plyer_notification.notify(
                    title="Screenshot Captured",
                    message=f"Saved to:\n{os.path.basename(path)}",
                    app_name="Gesture Control",
                    timeout=4,
                )
            else:
                # Fallback: use Windows-native PowerShell toast
                import platform
                if platform.system() == "Windows":
                    ps_cmd = (
                        f'powershell -Command "'
                        f"[Windows.UI.Notifications.ToastNotificationManager, "
                        f"Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
                        f"$template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02; "
                        f"$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template); "
                        f"$text = $xml.GetElementsByTagName('text'); "
                        f"$text[0].AppendChild($xml.CreateTextNode('Screenshot Captured')) | Out-Null; "
                        f"$text[1].AppendChild($xml.CreateTextNode('{os.path.basename(path)}')) | Out-Null; "
                        f"$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Gesture Control'); "
                        f"$notifier.Show([Windows.UI.Notifications.ToastNotification]::new($xml))"
                        f'"'
                    )
                    subprocess.Popen(ps_cmd, shell=True,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.debug("Notification error: %s", e)

    # ── DRAWING ───────────────────────────────────────────────────────────────

    def draw(self, index_tip: Tuple[int, int], canvas: np.ndarray, **_):
        """Draw on the numpy canvas at index_tip position."""
        if canvas is None:
            return
        pt = index_tip
        if self._prev_draw_pt is not None:
            color = (255, 255, 255) if self.eraser_mode else self.brush_color
            size  = config.ERASER_SIZE if self.eraser_mode else self.brush_size
            cv2_module = __import__("cv2")
            cv2_module.line(canvas, self._prev_draw_pt, pt, color, size)
        self._prev_draw_pt = pt
        self.last_action = "✏️ Drawing"

    def stop_drawing(self):
        self._prev_draw_pt = None

    def save_drawing(self, canvas: np.ndarray, callback: Callable = None, **_):
        if canvas is None:
            return

        def _do():
            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(config.DRAWINGS_DIR, f"drawing_{ts}.png")
                import cv2
                cv2.imwrite(path, canvas)
                logger.info("Drawing saved: %s", path)
                if callback:
                    callback(path)
            except Exception as e:
                logger.error("Save drawing error: %s", e)

        threading.Thread(target=_do, daemon=True).start()
        self.last_action = "💾 Drawing Saved"

    # ── APPLICATION LAUNCHER ──────────────────────────────────────────────────

    def launch_app(self, app_name: str, **_):
        """Launch a named application."""
        if not self._action_cd.ready():
            return
        cmd = config.DEFAULT_APPS.get(app_name)
        if cmd:
            try:
                subprocess.Popen(cmd, shell=True)
                self.last_action = f"🚀 Launched {app_name}"
                logger.info("Launched: %s", cmd)
            except Exception as e:
                logger.error("Launch error for %s: %s", app_name, e)
        else:
            logger.warning("Unknown app: %s", app_name)
