# cv/hand_tracker.py
# Core hand-tracking module built on top of MediaPipe Hands.
# Returns normalised and pixel landmarks for downstream gesture modules.

import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict
import config
from utils import get_logger
from cv.mediapipe_compat import install_no_matplotlib_drawing_utils

# Install the OpenCV-only drawing shim before MediaPipe imports its eager
# solutions package. This prevents its optional Matplotlib plotting utility
# from ever being imported at runtime.
install_no_matplotlib_drawing_utils()
import mediapipe as mp

logger = get_logger(__name__)

# ── MediaPipe landmark indices (named for readability) ──────────────────────
LM = {
    "WRIST":          0,
    "THUMB_CMC":      1, "THUMB_MCP": 2, "THUMB_IP": 3,  "THUMB_TIP":  4,
    "INDEX_MCP":      5, "INDEX_PIP": 6, "INDEX_DIP": 7, "INDEX_TIP":  8,
    "MIDDLE_MCP":     9, "MIDDLE_PIP":10,"MIDDLE_DIP":11,"MIDDLE_TIP": 12,
    "RING_MCP":      13, "RING_PIP":  14,"RING_DIP":  15,"RING_TIP":   16,
    "PINKY_MCP":     17, "PINKY_PIP": 18,"PINKY_DIP": 19,"PINKY_TIP":  20,
}


class HandTracker:
    """
    Wrapper around MediaPipe Hands that exposes:
      - process(frame) → annotated frame + list of Hand objects
      - each Hand has .landmarks, .pixel_landmarks, .handedness, .score
    """

    def __init__(self,
                 max_hands: int = 2,
                 min_detection_confidence: float = 0.7,
                 min_tracking_confidence: float = 0.5,
                 model_complexity: int = config.MP_MODEL_COMPLEXITY):

        self._mp_hands = mp.solutions.hands
        self._connections = self._mp_hands.HAND_CONNECTIONS

        self.hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        # Keep smoothing independent for each recognised hand.  A single
        # shared buffer mixes left/right landmarks as hands change order.
        self._smoothed_landmarks: Dict[str, np.ndarray] = {}
        logger.info("HandTracker initialised (max_hands=%d).", max_hands)

    # ── public API ────────────────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> Tuple[np.ndarray, List["Hand"]]:
        """
        Run MediaPipe inference on *frame* (BGR).

        Returns
        -------
        annotated_frame : BGR frame with landmarks drawn
        hands           : list of Hand data-objects (empty if no detection)
        """
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self.hands.process(rgb)
        rgb.flags.writeable = True

        detected: List[Hand] = []

        if not results.multi_hand_landmarks:
            self._smoothed_landmarks.clear()
            return frame, detected

        seen_hands = set()

        for hand_landmarks, handedness_info in zip(
            results.multi_hand_landmarks,
            results.multi_handedness,
        ):
            hand_label = handedness_info.classification[0].label
            seen_hands.add(hand_label)
            # MediaPipe landmarks can jitter by a few pixels even when the hand
            # is stationary. A low-lag EMA removes that noise before both the
            # gesture detector and the OpenCV overlay see it.
            raw_landmarks = np.array(
                [(lm.x, lm.y, lm.z) for lm in hand_landmarks.landmark],
                dtype=np.float32,
            )
            previous = self._smoothed_landmarks.get(hand_label)
            if previous is None:
                smoothed_landmarks = raw_landmarks
            else:
                alpha = config.LANDMARK_SMOOTHING_ALPHA
                smoothed_landmarks = (
                    alpha * raw_landmarks + (1.0 - alpha) * previous
                )
            self._smoothed_landmarks[hand_label] = smoothed_landmarks

            # Build pixel-space landmark list from the stable coordinates.
            pixel_lms = [
                (int(x * w), int(y * h))
                for x, y, _ in smoothed_landmarks
            ]
            self._draw_hand_overlay(frame, pixel_lms)
            norm_lms = [tuple(point) for point in smoothed_landmarks]

            hand = Hand(
                landmarks=norm_lms,
                pixel_landmarks=pixel_lms,
                handedness=handedness_info.classification[0].label,  # "Left"/"Right"
                score=handedness_info.classification[0].score,
                frame_shape=(h, w),
            )
            detected.append(hand)

        # Drop a hand's history as soon as it disappears, so a later
        # re-detection starts from its current landmark position.
        for hand_label in tuple(self._smoothed_landmarks):
            if hand_label not in seen_hands:
                self._smoothed_landmarks.pop(hand_label, None)

        return frame, detected

    def _draw_hand_overlay(self, frame: np.ndarray,
                           landmarks: List[Tuple[int, int]]) -> None:
        """Render the hand skeleton with OpenCV only; no plotting dependency."""
        for start, end in self._connections:
            cv2.line(frame, landmarks[start], landmarks[end], (80, 210, 80), 2,
                     cv2.LINE_AA)
        for point in landmarks:
            cv2.circle(frame, point, 3, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, point, 4, (80, 210, 80), 1, cv2.LINE_AA)

    def close(self):
        self.hands.close()
        self._smoothed_landmarks.clear()
        logger.debug("HandTracker closed.")


# ── Data class ────────────────────────────────────────────────────────────────

class Hand:
    """Holds all landmark data for one detected hand."""

    def __init__(self,
                 landmarks: List[Tuple[float, float, float]],
                 pixel_landmarks: List[Tuple[int, int]],
                 handedness: str,
                 score: float,
                 frame_shape: Tuple[int, int]):

        self.landmarks       = landmarks        # normalised (x,y,z) × 21
        self.pixel_landmarks = pixel_landmarks  # pixel (x,y) × 21
        self.handedness      = handedness       # "Left" | "Right"
        self.score           = score            # detection confidence
        self.frame_shape     = frame_shape      # (height, width)

    # ── landmark shortcuts ────────────────────

    def tip(self, finger: str) -> Tuple[int, int]:
        """Return pixel coords of a finger tip. finger ∈ {THUMB,INDEX,MIDDLE,RING,PINKY}"""
        return self.pixel_landmarks[LM[f"{finger.upper()}_TIP"]]

    def mcp(self, finger: str) -> Tuple[int, int]:
        return self.pixel_landmarks[LM[f"{finger.upper()}_MCP"]]

    def lm(self, idx: int) -> Tuple[int, int]:
        return self.pixel_landmarks[idx]

    # ── finger states ─────────────────────────

    def fingers_up(self) -> List[bool]:
        """
        Returns a 5-element list [thumb, index, middle, ring, pinky].
        True = finger is extended.
        """
        lms = self.pixel_landmarks
        tips   = [4, 8, 12, 16, 20]
        pips   = [3, 6, 10, 14, 18]    # one joint below tip
        result = []

        # Thumb: it may point sideways *or* upward.  Treating only a
        # sideways thumb as extended made the documented thumbs-up volume
        # gesture impossible to recognise.
        vertical_thumb_extension = max(8, int(self.frame_shape[0] * 0.02))
        if self.handedness == "Right":
            sideways_extended = lms[4][0] < lms[3][0]
        else:
            sideways_extended = lms[4][0] > lms[3][0]
        upward_extended = lms[4][1] < lms[3][1] - vertical_thumb_extension
        result.append(sideways_extended or upward_extended)

        # Other four fingers: compare y-axis (tip above pip = extended)
        for tip, pip in zip(tips[1:], pips[1:]):
            result.append(lms[tip][1] < lms[pip][1])

        return result

    def count_fingers(self) -> int:
        return sum(self.fingers_up())

    # ── gesture helpers ───────────────────────

    def pinch_distance(self, finger_a: str = "THUMB", finger_b: str = "INDEX") -> float:
        """Euclidean pixel distance between two finger tips."""
        from utils.helpers import euclidean
        return euclidean(self.tip(finger_a), self.tip(finger_b))

    def bounding_box(self) -> Tuple[int, int, int, int]:
        """(x_min, y_min, x_max, y_max) of the hand bounding box."""
        xs = [p[0] for p in self.pixel_landmarks]
        ys = [p[1] for p in self.pixel_landmarks]
        return min(xs), min(ys), max(xs), max(ys)

    def __repr__(self):
        return f"<Hand {self.handedness} fingers={self.fingers_up()} score={self.score:.2f}>"
