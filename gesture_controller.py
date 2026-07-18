# gestures/gesture_controller.py
# High-level controller that:
#   1. Receives detected Hand objects from HandTracker
#   2. Runs GestureDetector to get gesture names
#   3. Looks up the action in the active profile (DB)
#   4. Calls the appropriate ActionExecutor method
#   5. Returns overlay data for the HUD

import numpy as np
from typing import List, Optional, Dict, Any, Callable

from cv.hand_tracker import Hand
from gestures.gesture_detector import GestureDetector
from gestures.action_executor import ActionExecutor
from database.db_manager import DBManager
from utils import get_logger
import config

logger = get_logger(__name__)


class GestureController:
    """
    Orchestrates the full pipeline for a single frame:
      hands → gesture_names → actions → HUD overlay data
    """

    _ML_LABEL_ALIASES = {
        "THUMB_UP": "VOLUME_CONTROL",
        "VOLUME_PINCH": "VOLUME_CONTROL",
        "BRIGHTNESS_SWIPE": "BRIGHTNESS_CONTROL",
        "FIST": "FIST_HOLD",
        "OPEN_PALM": "OPEN_PALM_HOLD",
        "INDEX_DRAW": "INDEX_POINT",
        "INDEX": "INDEX_POINT",
        "PINCH_INDEX": "THUMB_INDEX",
        "PINCH_MIDDLE": "THUMB_MIDDLE",
        "PINCH_PINKY": "THUMB_PINKY",
    }
    _PRIORITY = {
        "EMERGENCY_STOP": 0,
        "FIST_HOLD": 1,
        "OPEN_PALM_HOLD": 1,       # MODIFIED — added, same priority as drag
        "VOLUME_CONTROL": 2,
        "BRIGHTNESS_CONTROL": 2,   # MODIFIED — added, same priority as volume
        "TWO_FINGERS_UP": 3,
        "TWO_FINGERS_DOWN": 3,
        "THUMB_INDEX": 4,
        "THUMB_MIDDLE": 4,
        "THUMB_PINKY": 4,
        "INDEX_POINT": 5,
    }

    def __init__(self,
                 db: DBManager,
                 screen_size: tuple,
                 frame_size: tuple,
                 on_screenshot: Callable = None,
                 on_drawing_saved: Callable = None,
                 predictor: Any = None):

        self.db      = db
        self.profile = db.get_setting("active_profile", config.DEFAULT_PROFILE)

        sensitivity = float(db.get_setting("sensitivity", config.MOUSE_SENSITIVITY))
        smoothing   = int(db.get_setting("smoothing",    config.MOUSE_SMOOTHING))
        self.pinch_threshold = float(db.get_setting("pinch_threshold", config.PINCH_THRESHOLD))

        self.detector = GestureDetector(pinch_threshold=self.pinch_threshold)
        self.predictor = predictor
        self.executor = ActionExecutor(
            screen_w   = screen_size[0],
            screen_h   = screen_size[1],
            frame_w    = frame_size[0],
            frame_h    = frame_size[1],
            sensitivity= sensitivity,
            smoothing  = smoothing,
        )

        # Optional callbacks for confirmations
        self.on_screenshot    = on_screenshot
        self.on_drawing_saved = on_drawing_saved

        # Drawing canvas — lazily created
        self.draw_canvas: Optional[np.ndarray] = None
        self._canvas_shape = (frame_size[1], frame_size[0], 3)

        # HUD state
        self.hud: Dict[str, Any] = {
            "gesture":    "—",
            "action":     "—",
            "profile":    self.profile,
            "confidence": 0.0,
        }
        self._active_discrete_actions = set()
        self._discrete_release_frames: Dict[str, int] = {}
        self._continuous_actions = {
            "mouse_move", "drag", "volume_control", "brightness_control",
            "draw", "laser_pointer", "scroll_up", "scroll_down",
        }
        self._motion_y: Dict[str, Optional[int]] = {}
        self._scroll_motion_y: Dict[str, Optional[int]] = {}

        logger.info("GestureController ready. Profile=%s ML=%s", self.profile,
                    bool(self.predictor and self.predictor.ready))

    # ── Frame processing ──────────────────────────────────────────────────────

    def process_hands(self, hands: List[Hand],
                      frame: np.ndarray) -> np.ndarray:
        """
        Process a list of Hand objects detected in the current frame.
        Mutates *frame* with overlays and returns it.
        """
        if self.draw_canvas is None:
            self.draw_canvas = np.zeros(self._canvas_shape, dtype=np.uint8)

        if not hands:
            self._full_tracking_loss_reset()
            logger.info("Frame predicted=NONE confidence=0.00 smoothed=NONE action=NONE")
            self.hud["gesture"] = "—"
            self.hud["action"]  = "—"
            return frame

        # One hand owns the controls. Otherwise two detected hands can issue
        # conflicting mouse moves or duplicate clicks in the same frame.
        hand = next((item for item in hands if item.handedness == "Right"), hands[0])
        if hand.score < config.CONTROL_HAND_MIN_CONF:
            self._full_tracking_loss_reset()
            logger.info("Frame predicted=NONE confidence=0.00 smoothed=NONE action=TRACKING_REJECTED")
            self.hud["gesture"] = "—"
            self.hud["action"] = "Tracking hand…"
            return frame
        current_discrete_actions = set()
        active_continuous_actions = set()
        gesture = None
        action_executed = "NONE"
        prediction_name = "NONE"
        prediction_confidence = 0.0
        for hand in (hand,):
            rule_gesture = self.detector.detect(hand)
            ml_prediction = self.predictor.predict(hand) if self.predictor and self.predictor.ready else None
            if ml_prediction:
                prediction_name, prediction_confidence = ml_prediction
            gesture, source = self._select_gesture(ml_prediction, rule_gesture)
            if gesture is None:
                continue

            action = self.db.get_action_for_gesture(gesture, self.profile)
            if action is None and source == "ML" and rule_gesture:
                # A custom model may contain a label without a configured
                # action mapping; do not let it suppress the safe fallback.
                gesture, source = rule_gesture, "RULE_FALLBACK"
                action = self.db.get_action_for_gesture(gesture, self.profile)
            if action is None:
                continue

            self.hud["gesture"]    = gesture
            self.hud["action"]     = action
            confidence = prediction_confidence if source == "ML" else self.detector.last_confidence
            self.hud["confidence"] = round(confidence, 2)

            if action in self._continuous_actions:
                active_continuous_actions.add(action)
                self._dispatch(action, hand, gesture)
                action_executed = self.executor.last_action
            else:
                current_discrete_actions.add(action)
                if action not in self._active_discrete_actions:
                    self._dispatch(action, hand, gesture)
                    self.db.log_gesture(gesture, action)
                    action_executed = self.executor.last_action
                    self._active_discrete_actions.add(action)
                self._discrete_release_frames.pop(action, None)

        self._update_discrete_latches(current_discrete_actions)

        # Drag uses a grace-period release to tolerate gesture flicker
        if "drag" not in active_continuous_actions:
            self.executor.request_drag_release()
        if "draw" not in active_continuous_actions:
            self.executor.stop_drawing()

        # Motion-driven controls must not retain the last position when the
        # user changes pose; that caused the first volume step to jump.
        for action in tuple(self._motion_y):
            if action not in active_continuous_actions:
                self._motion_y.pop(action, None)
                self.executor.reset_level_motion(action)
        for action in tuple(self._scroll_motion_y):
            if action not in active_continuous_actions:
                self._scroll_motion_y.pop(action, None)
        if not self.detector.last_scroll_pose_active:
            self.executor.reset_level_motion("scroll_up")
            self.executor.reset_level_motion("scroll_down")

        # Blend drawing canvas onto frame
        if self.profile == "Drawing" and self.draw_canvas is not None:
            frame = self._blend_canvas(frame)

        raw = prediction_name if prediction_name != "NONE" else (self.detector.last_raw or "NONE")
        smoothed = gesture or self.detector.last_smoothed or "NONE"
        if gesture is None:
            self.hud["gesture"] = raw if raw != "NONE" else "-"
            self.hud["action"] = "Recognising..." if raw != "NONE" else "-"
            self.hud["confidence"] = round(self.detector.last_confidence, 2)
        logger.info(
            "Frame predicted=%s confidence=%.2f smoothed=%s action=%s",
            raw, prediction_confidence or self.detector.last_confidence, smoothed, action_executed,
        )
        return frame

    # ── Tracking loss ─────────────────────────────────────────────────────────

    def _full_tracking_loss_reset(self):
        """Clear every piece of state when the hand disappears or confidence
        drops.  This prevents stale holds, pinches, drags, accumulators and
        cursor velocity from persisting across a tracking gap.
        """
        self.executor.full_reset()
        # A hand that left the frame must not retain a pinch or hold state.
        # Otherwise returning to the frame can immediately trigger a click,
        # drag, or screenshot based on a pose from before tracking was lost.
        self.detector.reset()
        if self.predictor:
            self.predictor.reset()
        self._active_discrete_actions.clear()
        self._discrete_release_frames.clear()
        self._motion_y.clear()
        self._scroll_motion_y.clear()
        self.hud["confidence"] = 0.0

    # ── Action dispatcher ─────────────────────────────────────────────────────

    def _select_gesture(self, ml_prediction, rule_gesture: Optional[str]):
        """Prefer confident ML poses; retain geometry for holds and motion."""
        ml_gesture = None
        if ml_prediction:
            name, _confidence = ml_prediction
            ml_gesture = self._ML_LABEL_ALIASES.get(name, name)

        # A static landmark frame cannot prove a hold duration or scroll
        # direction, so those temporal conditions remain rule-based.
        if ml_gesture in {"FIST_HOLD", "OPEN_PALM_HOLD"} and rule_gesture != ml_gesture:
            return None, "ML_PENDING_HOLD"

        if rule_gesture and ml_gesture:
            if self._PRIORITY.get(rule_gesture, 99) < self._PRIORITY.get(ml_gesture, 99):
                return rule_gesture, "RULE_PRIORITY"
            return ml_gesture, "ML"
        if ml_gesture:
            return ml_gesture, "ML"
        if rule_gesture:
            return rule_gesture, "RULE_FALLBACK"
        return None, "NONE"

    def _update_discrete_latches(self, active_actions):
        """Re-arm clicks, screenshots, and media only after a stable release."""
        for action in tuple(self._active_discrete_actions):
            if action in active_actions:
                self._discrete_release_frames.pop(action, None)
                continue
            released = self._discrete_release_frames.get(action, 0) + 1
            if released >= config.GESTURE_RELEASE_FRAMES:
                self._active_discrete_actions.discard(action)
                self._discrete_release_frames.pop(action, None)
            else:
                self._discrete_release_frames[action] = released

    def _dispatch(self, action: str, hand: Hand, gesture: str = ""):
        """Map action string → ActionExecutor method call."""
        index_tip     = hand.tip("INDEX")
        motion_y = self._vertical_motion(action, hand.tip("THUMB")[1])
        scroll_motion_y = (self.detector.last_event_motion_y
                           if gesture in {"TWO_FINGERS_UP", "TWO_FINGERS_DOWN"}
                           else self._scroll_vertical_motion(action, hand.tip("INDEX")[1]))

        dispatch_map = {
            "mouse_move":         lambda: self.executor.mouse_move(index_tip),
            "left_click":         lambda: self.executor.left_click(),
            "right_click":        lambda: self.executor.right_click(),
            "double_click":       lambda: self.executor.double_click(),
            "drag":               lambda: self.executor.drag(index_tip),
            # Pass raw motion delta — scroll_motion() determines direction from sign
            "scroll_up":          lambda: self.executor.scroll_motion(scroll_motion_y, direction="up"),
            "scroll_down":        lambda: self.executor.scroll_motion(scroll_motion_y, direction="down"),
            "volume_control":     lambda: self.executor.volume_control(motion_y),
            "brightness_control": lambda: self.executor.brightness_control(motion_y),
            "play_pause":         lambda: self.executor.play_pause(),
            "next_track":         lambda: self.executor.next_track(),
            "prev_track":         lambda: self.executor.prev_track(),
            "next_slide":         lambda: self.executor.next_slide(),
            "prev_slide":         lambda: self.executor.prev_slide(),
            "laser_pointer":      lambda: self.executor.laser_pointer(index_tip),
            "screenshot":         lambda: self.executor.screenshot(callback=self.on_screenshot),
            "draw":               lambda: self.executor.draw(index_tip, self.draw_canvas),
            "eraser":             self._enable_eraser,
            "save_drawing":       lambda: self.executor.save_drawing(
                                        self.draw_canvas, callback=self.on_drawing_saved),
        }

        fn = dispatch_map.get(action)
        if fn:
            fn()
        else:
            logger.debug("No dispatch handler for action: %s", action)

    def _vertical_motion(self, action: str, y: int) -> float:
        """Return vertical movement for volume and brightness only."""
        if action not in {"volume_control", "brightness_control"}:
            return 0.0
        previous = self._motion_y.get(action)
        self._motion_y[action] = y
        return 0.0 if previous is None else y - previous

    def _scroll_vertical_motion(self, action: str, y: int) -> float:
        """Return vertical motion for scroll gestures without affecting mouse movement."""
        if action not in {"scroll_up", "scroll_down"}:
            return 0.0
        previous = self._scroll_motion_y.get(action)
        self._scroll_motion_y[action] = y
        return 0.0 if previous is None else y - previous

    def _enable_eraser(self):
        self.executor.eraser_mode = True
        self.executor.stop_drawing()

    # ── Canvas blending ───────────────────────────────────────────────────────

    def _blend_canvas(self, frame: np.ndarray) -> np.ndarray:
        """Overlay drawing canvas on top of camera frame."""
        mask = self.draw_canvas.astype(bool)
        result = frame.copy()
        result[mask] = self.draw_canvas[mask]
        return result

    def clear_canvas(self):
        if self.draw_canvas is not None:
            self.draw_canvas[:] = 0
        self.executor.eraser_mode = False

    # ── Profile switching ─────────────────────────────────────────────────────

    def set_profile(self, profile: str):
        if profile in config.PROFILES:
            self.profile = profile
            self.hud["profile"] = profile
            self.db.set_setting("active_profile", profile)
            self.detector.reset()
            if self.predictor:
                self.predictor.reset()
            self.executor.full_reset()
            self._active_discrete_actions.clear()
            self._discrete_release_frames.clear()
            self._motion_y.clear()
            self._scroll_motion_y.clear()
            logger.info("Profile switched to: %s", profile)
