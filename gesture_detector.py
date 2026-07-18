"""Stable rule-based gestures for a single control hand."""

import time
from collections import deque, Counter
from typing import Dict, Optional, Tuple

import config
from cv.hand_tracker import Hand
from utils.helpers import Cooldown


class GestureDetector:
    """Recognise gestures only after they are stable across several frames."""

    _EVENT_GESTURES = {"SWIPE_LEFT", "SWIPE_RIGHT", "TWO_FINGERS_UP", "TWO_FINGERS_DOWN"}

    def __init__(self, pinch_threshold: float = None):
        self.pinch_thresh = pinch_threshold or config.PINCH_THRESHOLD
        self._previous: Dict[str, Tuple[Tuple[int, int], float]] = {}
        self._candidate: Dict[str, Optional[str]] = {}
        self._candidate_frames: Dict[str, int] = {}
        self._hold_start: Dict[str, float] = {}
        self._hold_name: Dict[str, str] = {}
        self._hold_gap: Dict[str, int] = {}   # dropout frames during a hold
        self._active_pinch: Dict[str, str] = {}
        self._scroll_anchor: Dict[str, int] = {}
        self._scroll_cd = Cooldown(45)
        self._swipe_cd = Cooldown(450)
        # Majority voting history: rolling deque of recent raw gestures
        self._vote_history: Dict[str, deque] = {}
        self._last_emitted: Dict[str, Optional[str]] = {}
        # Public diagnostics consumed by GestureController's per-frame log.
        self.last_raw: Optional[str] = None
        self.last_smoothed: Optional[str] = None
        self.last_confidence: float = 0.0
        self.last_event_motion_y: float = 0.0
        self.last_scroll_pose_active: bool = False

    def detect(self, hand: Hand) -> Optional[str]:
        """Return one stable gesture name or ``None`` for this frame."""
        motion = self._motion(hand)
        self.last_event_motion_y = 0.0
        self.last_scroll_pose_active = self._is_scroll_pose(hand.fingers_up())
        raw = self._raw_gesture(hand, motion)
        self.last_raw = raw
        if raw in self._EVENT_GESTURES:
            self.last_smoothed = raw
            self.last_confidence = 1.0
            return raw
        stable = self._stabilise(hand.handedness, raw)
        self.last_smoothed = stable
        return stable

    def _raw_gesture(self, hand: Hand, motion: Tuple[float, float, float]) -> Optional[str]:
        fingers = hand.fingers_up()
        key = hand.handedness

        # Scroll uses the current hand position as a reference point while the
        # pose is held. Clear that reference as soon as the pose changes.
        if not self._is_scroll_pose(fingers):
            self._scroll_anchor.pop(key, None)

        if fingers == [False, False, False, False, False]:
            return self._held(key, "FIST_HOLD")
        if fingers == [True, True, True, True, True]:
            return self._held(key, "OPEN_PALM_HOLD")
        # Don't clear hold immediately — tolerate gap frames
        self._hold_gap_check(key)

        # Unique continuous controls. Neither pose can be mistaken for the
        # thumb-index click pose.
        if fingers == [True, False, False, False, False]:
            return "VOLUME_CONTROL"
        if fingers == [False, True, True, True, True]:
            return "BRIGHTNESS_CONTROL"

        # Check this before pinch detection. A valid two-finger scroll with an
        # open thumb can place thumb and index close together; the old order
        # converted that scroll pose into a left click.
        if self._is_scroll_pose(fingers):
            self._active_pinch.pop(key, None)
        scroll = self._detect_scroll(hand, fingers)
        if scroll:
            return scroll

        pinch = self._detect_pinch(hand, fingers)
        if pinch:
            self._clear_hold(key)
            return pinch
        swipe = self._detect_swipe(fingers, motion)
        if swipe:
            return swipe

        if fingers == [False, True, False, False, False]:
            return "INDEX_POINT"
        return None

    def _detect_pinch(self, hand: Hand, fingers) -> Optional[str]:
        key = hand.handedness
        choices = (
            ("INDEX", 1, "THUMB_INDEX"),
            ("MIDDLE", 2, "THUMB_MIDDLE"),
            ("PINKY", 4, "THUMB_PINKY"),
        )
        active = self._active_pinch.get(key)
        for finger, finger_index, name in choices:
            if name == active:
                extended = self._is_finger_reachable(hand, finger, finger_index, fingers)
                if extended and hand.pinch_distance("THUMB", finger) < self.pinch_thresh * config.PINCH_RELEASE_MULTIPLIER:
                    return name
                self._active_pinch.pop(key, None)
                break

        for finger, finger_index, name in choices:
            # For INDEX: require full extension (tip above pip) to avoid
            # conflicts with volume control's folded-hand pose.
            # For MIDDLE/PINKY: use a relaxed check (tip above mcp) because
            # the act of pinching curls the finger below pip.
            extended = self._is_finger_reachable(hand, finger, finger_index, fingers)
            if extended and hand.pinch_distance("THUMB", finger) < self.pinch_thresh:
                self._active_pinch[key] = name
                return name
        return None

    @staticmethod
    def _is_finger_reachable(hand: Hand, finger: str, finger_index: int, fingers) -> bool:
        """Check if a finger is sufficiently extended to participate in a pinch.

        For INDEX: strict check (tip above pip) — the standard fingers_up test.
        For MIDDLE/PINKY: relaxed check (tip above mcp) because curling the
        finger toward the thumb naturally lowers the tip below the pip joint.
        """
        if finger == "INDEX":
            return fingers[finger_index]
        # Relaxed: tip y < mcp y (tip is above the knuckle)
        tip_y = hand.tip(finger)[1]
        mcp_y = hand.mcp(finger)[1]
        return tip_y < mcp_y + 30  # 30px tolerance for partially curled finger

    def _held(self, key: str, name: str) -> Optional[str]:
        """Track a hold gesture, tolerating brief dropout frames."""
        now = time.perf_counter()
        # Reset gap counter — the pose is active this frame
        self._hold_gap[key] = 0
        if self._hold_name.get(key) != name:
            self._hold_name[key] = name
            self._hold_start[key] = now
            return None
        return name if now - self._hold_start[key] >= config.HOLD_DURATION else None

    def _hold_gap_check(self, key: str):
        """Called when fingers don't match a hold pose.

        Instead of clearing immediately, allow up to HOLD_GAP_TOLERANCE
        consecutive non-matching frames before resetting the timer.  This
        prevents a single noisy frame from forcing the user to re-hold for
        another 0.75 s.
        """
        if key not in self._hold_name:
            return  # no active hold to protect
        gap = self._hold_gap.get(key, 0) + 1
        if gap > config.HOLD_GAP_TOLERANCE:
            self._clear_hold(key)
            self._hold_gap.pop(key, None)
        else:
            self._hold_gap[key] = gap

    def _clear_hold(self, key: str):
        self._hold_start.pop(key, None)
        self._hold_name.pop(key, None)
        self._hold_gap.pop(key, None)

    def _motion(self, hand: Hand) -> Tuple[float, float, float]:
        key, now, point = hand.handedness, time.perf_counter(), hand.tip("INDEX")
        previous = self._previous.get(key)
        self._previous[key] = (point, now)
        if previous is None:
            return 0.0, 0.0, 0.0
        (px, py), then = previous
        return point[0] - px, point[1] - py, max(now - then, 0.0001)

    @staticmethod
    def _is_scroll_pose(fingers) -> bool:
        """Index and middle up, with the thumb relaxed in either position."""
        return len(fingers) == 5 and fingers[1] and fingers[2] and not fingers[3] and not fingers[4]

    def _detect_scroll(self, hand: Hand, fingers) -> Optional[str]:
        if not self._is_scroll_pose(fingers):
            return None
        key = hand.handedness
        y = hand.tip("INDEX")[1]
        anchor = self._scroll_anchor.get(key)
        if anchor is None:
            self._scroll_anchor[key] = y
            return None

        dy = y - anchor
        if abs(dy) >= config.SCROLL_TRIGGER_DISTANCE and self._scroll_cd.ready():
            self._scroll_anchor[key] = y
            self.last_event_motion_y = float(dy)
            return "TWO_FINGERS_DOWN" if dy > 0 else "TWO_FINGERS_UP"
        return None

    def _detect_swipe(self, fingers, motion: Tuple[float, float, float]) -> Optional[str]:
        if fingers != [False, True, False, False, False]:
            return None
        dx, dy, elapsed = motion
        if abs(dx) > abs(dy) and abs(dx) / elapsed >= 850 and self._swipe_cd.ready():
            return "SWIPE_RIGHT" if dx > 0 else "SWIPE_LEFT"
        return None

    def _stabilise(self, key: str, gesture: Optional[str]) -> Optional[str]:
        """Use majority voting over a rolling window for stable recognition.

        A gesture must appear at least ``GESTURE_VOTE_THRESHOLD`` times in the
        last ``GESTURE_VOTE_WINDOW`` frames to be emitted.

        MODIFIED — When a completely new gesture appears and the previous
        gesture has zero remaining votes, the history is cleared immediately
        so the new gesture can be confirmed within 2 frames (~66ms at 30fps)
        instead of waiting for the old votes to scroll out of the window.
        """
        # Maintain rolling vote history per hand
        if key not in self._vote_history:
            self._vote_history[key] = deque(maxlen=config.GESTURE_VOTE_WINDOW)
        history = self._vote_history[key]

        # MODIFIED — Fast transition: if the incoming gesture is completely
        # different from the last emitted one, and the last emitted gesture
        # has no remaining support in the history, clear immediately.
        last_emitted = self._last_emitted.get(key)
        if (gesture is not None
                and last_emitted is not None
                and gesture != last_emitted):
            old_support = sum(1 for g in history if g == last_emitted)
            if old_support == 0:
                # The old gesture is already gone — fast-track the new one
                history.clear()  # MODIFIED

        history.append(gesture)

        if gesture is None:
            self.last_confidence = 0.0
            # Keep emitting the last gesture for a few frames to prevent
            # flicker, but only if the history still supports it.
            last = self._last_emitted.get(key)
            if last is not None:
                count = sum(1 for g in history if g == last)
                if count >= config.GESTURE_VOTE_THRESHOLD:
                    self.last_confidence = count / len(history)
                    return last
                # MODIFIED — If the last gesture has lost all support, stop
                # emitting it immediately instead of lingering.
                if count == 0:
                    self._last_emitted.pop(key, None)
            return None

        # Count occurrences of each gesture in the window
        counts = Counter(g for g in history if g is not None)
        if not counts:
            self.last_confidence = 0.0
            return None

        winner, winner_count = counts.most_common(1)[0]
        self.last_confidence = winner_count / len(history)

        if winner_count >= config.GESTURE_VOTE_THRESHOLD:
            self._last_emitted[key] = winner
            return winner

        # Not yet enough votes — return the last emitted only if it IS the
        # current gesture (prevents stale gestures from lingering).  # MODIFIED
        if last_emitted is not None and last_emitted == gesture:
            count_last = sum(1 for g in history if g == last_emitted)
            if count_last >= max(1, config.GESTURE_VOTE_THRESHOLD - 1):
                return last_emitted

        return None

    def reset(self):
        self._previous.clear()
        self._candidate.clear()
        self._candidate_frames.clear()
        self._hold_start.clear()
        self._hold_name.clear()
        self._hold_gap.clear()
        self._active_pinch.clear()
        self._scroll_anchor.clear()
        self._scroll_cd.reset()
        self._swipe_cd.reset()
        self._vote_history.clear()
        self._last_emitted.clear()
        self.last_raw = None
        self.last_smoothed = None
        self.last_confidence = 0.0
        self.last_event_motion_y = 0.0
        self.last_scroll_pose_active = False
