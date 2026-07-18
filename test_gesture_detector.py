import unittest

from gestures.gesture_detector import GestureDetector


class FakeHand:
    def __init__(self, fingers, distances=None, point=(100, 100), handedness="Right"):
        self._fingers = fingers
        self._distances = distances or {}
        self._point = point
        self.handedness = handedness

    def fingers_up(self):
        return self._fingers

    def pinch_distance(self, _thumb, finger):
        return self._distances.get(finger, 500)

    def tip(self, _finger):
        return self._point


class GestureDetectorTests(unittest.TestCase):
    def test_thumb_only_is_volume_not_a_left_click(self):
        detector = GestureDetector()
        hand = FakeHand([True, False, False, False, False], {"INDEX": 5})
        # Majority voting needs GESTURE_VOTE_THRESHOLD (3) votes
        for _ in range(4):
            result = detector.detect(hand)
        self.assertEqual(result, "VOLUME_CONTROL")

    def test_index_pinch_requires_vote_threshold(self):
        detector = GestureDetector()
        hand = FakeHand([False, True, False, False, False], {"INDEX": 5})
        results = []
        for _ in range(5):
            results.append(detector.detect(hand))
        self.assertIn("THUMB_INDEX", results)

    def test_index_pointer_requires_vote_threshold(self):
        detector = GestureDetector()
        hand = FakeHand([False, True, False, False, False])
        results = []
        for _ in range(5):
            results.append(detector.detect(hand))
        self.assertIn("INDEX_POINT", results)

    def test_fist_hold_is_emitted_after_the_hold_duration(self):
        detector = GestureDetector()
        hand = FakeHand([False, False, False, False, False])
        # Pre-seed the hold timer so it has already elapsed
        detector._hold_start[hand.handedness] = 0.0
        detector._hold_name[hand.handedness] = "FIST_HOLD"
        detector._hold_gap[hand.handedness] = 0
        # Feed enough frames for majority voting to confirm
        results = []
        for _ in range(5):
            results.append(detector.detect(hand))
        self.assertIn("FIST_HOLD", results)

    def test_scroll_uses_accumulated_two_finger_motion(self):
        detector = GestureDetector()
        pose = [False, True, True, False, False]
        self.assertIsNone(detector.detect(FakeHand(pose, point=(100, 100))))
        self.assertEqual(
            detector.detect(FakeHand(pose, point=(100, 125))),
            "TWO_FINGERS_DOWN",
        )

    def test_scroll_allows_an_open_thumb(self):
        detector = GestureDetector()
        pose = [True, True, True, False, False]
        self.assertIsNone(detector.detect(FakeHand(pose, point=(100, 100))))
        self.assertEqual(
            detector.detect(FakeHand(pose, point=(100, 75))),
            "TWO_FINGERS_UP",
        )
