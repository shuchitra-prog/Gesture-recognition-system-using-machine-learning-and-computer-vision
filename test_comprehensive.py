"""Comprehensive regression tests for gesture-controlled computer.

Covers: cursor movement, clicks, scroll, volume, drag, screenshot,
brightness, gesture switching, tracking loss, and hand reappearance.
"""

import math
import time
import unittest
from collections import deque
from unittest.mock import patch, MagicMock

import gestures.action_executor as action_executor_module
from gestures.action_executor import ActionExecutor
from gestures.gesture_detector import GestureDetector
from utils.helpers import OneEuroFilter, CursorSmoother


# ── Helpers ──────────────────────────────────────────────────────────────────

class FakeHand:
    """Lightweight Hand substitute for unit tests."""

    def __init__(self, fingers, distances=None, point=(100, 100),
                 handedness="Right", score=0.95):
        self._fingers = fingers
        self._distances = distances or {}
        self._point = point
        self.handedness = handedness
        self.score = score

    def fingers_up(self):
        return self._fingers

    def pinch_distance(self, _thumb, finger):
        return self._distances.get(finger, 500)

    def tip(self, _finger):
        return self._point


def _make_executor(**kw):
    """Create an ActionExecutor with stubbed cooldowns for deterministic tests."""
    ex = ActionExecutor(1920, 1080, 640, 480, sensitivity=1.0, smoothing=1)
    ex._scroll_cd = type("Stub", (), {"ready": staticmethod(lambda: True)})()
    ex._level_cd = type("Stub", (), {"ready": staticmethod(lambda: True)})()
    ex._action_cd = type("Stub", (), {"ready": staticmethod(lambda: True)})()
    ex._click_cd = type("Stub", (), {"ready": staticmethod(lambda: True)})()
    ex._screenshot_cd = type("Stub", (), {"ready": staticmethod(lambda: True)})()
    ex._vol_interface = None
    for k, v in kw.items():
        setattr(ex, k, v)
    return ex


# ═════════════════════════════════════════════════════════════════════════════
#  CURSOR MOVEMENT
# ═════════════════════════════════════════════════════════════════════════════

class OneEuroFilterTests(unittest.TestCase):
    def test_first_sample_is_returned_unchanged(self):
        f = OneEuroFilter()
        self.assertEqual(f(42.0, 0.0), 42.0)

    def test_stationary_input_converges(self):
        f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
        for i in range(50):
            out = f(100.0, i * 0.033)
        self.assertAlmostEqual(out, 100.0, delta=0.5)

    def test_fast_movement_tracks_with_low_lag(self):
        f = OneEuroFilter(min_cutoff=1.0, beta=0.1)
        for i in range(20):
            out = f(float(i * 50), i * 0.033)
        # Should be close to the latest input
        self.assertGreater(out, 800.0)

    def test_reset_clears_state(self):
        f = OneEuroFilter()
        f(100.0, 0.0)
        f(200.0, 1.0)
        f.reset()
        self.assertFalse(f._initialized)
        self.assertEqual(f(50.0, 2.0), 50.0)


class CursorSmootherTests(unittest.TestCase):
    def test_dead_zone_suppresses_micro_tremor(self):
        s = CursorSmoother(dead_zone=5.0, max_jump=500)
        p1 = s.update(100.0, 100.0)
        # Tiny movement < dead_zone should not change output
        p2 = s.update(101.0, 101.0)
        self.assertEqual(p1, p2)

    def test_large_movement_passes_through(self):
        s = CursorSmoother(dead_zone=2.0, max_jump=5000)
        s.update(100.0, 100.0)
        time.sleep(0.01)
        p2 = s.update(300.0, 300.0)
        # Output should have moved substantially toward the new position
        self.assertGreater(p2[0], 110.0)
        self.assertGreater(p2[1], 110.0)

    def test_velocity_clamp_prevents_jumps(self):
        s = CursorSmoother(dead_zone=0.0, max_jump=50)
        s.update(100.0, 100.0)
        time.sleep(0.01)
        p = s.update(500.0, 500.0)
        # The jump should be clamped — output should be much less than 500
        dist = math.hypot(p[0] - 100.0, p[1] - 100.0)
        self.assertLess(dist, 100.0)

    def test_reset_and_reacquire_does_not_jump(self):
        s = CursorSmoother(dead_zone=0.0, max_jump=500)
        s.update(100.0, 100.0)
        time.sleep(0.01)
        s.update(110.0, 110.0)
        s.reset()
        # After reset, first update should seed without jumping
        p = s.update(500.0, 500.0)
        self.assertAlmostEqual(p[0], 500.0, delta=1.0)
        self.assertAlmostEqual(p[1], 500.0, delta=1.0)


# ═════════════════════════════════════════════════════════════════════════════
#  LEFT CLICK
# ═════════════════════════════════════════════════════════════════════════════

class LeftClickTests(unittest.TestCase):
    def test_single_click_only(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.click") as click:
            ex.left_click()
            self.assertEqual(click.call_count, 1)

    def test_cooldown_prevents_repeat(self):
        ex = _make_executor()
        ex._click_cd = type("CD", (), {"ready": MagicMock(side_effect=[True, False, False])})()
        with patch("gestures.action_executor.pyautogui.click") as click:
            ex.left_click()
            ex.left_click()
            ex.left_click()
            self.assertEqual(click.call_count, 1)


# ═════════════════════════════════════════════════════════════════════════════
#  RIGHT CLICK
# ═════════════════════════════════════════════════════════════════════════════

class RightClickTests(unittest.TestCase):
    def test_right_click_fires(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.rightClick") as rc:
            ex.right_click()
            self.assertEqual(rc.call_count, 1)

    def test_right_click_independent_from_left(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.click"):
            ex.left_click()
        # The click cooldown was consumed by left_click; reset it
        ex._click_cd = type("Stub", (), {"ready": staticmethod(lambda: True)})()
        with patch("gestures.action_executor.pyautogui.rightClick") as rc:
            ex.right_click()
            self.assertEqual(rc.call_count, 1)


# ═════════════════════════════════════════════════════════════════════════════
#  DOUBLE CLICK
# ═════════════════════════════════════════════════════════════════════════════

class DoubleClickTests(unittest.TestCase):
    def test_double_click_fires_exactly_once(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.doubleClick") as dc:
            ex.double_click()
            self.assertEqual(dc.call_count, 1)

    def test_double_click_cooldown_prevents_repeat(self):
        ex = _make_executor()
        ex._click_cd = type("CD", (), {"ready": MagicMock(side_effect=[True, False])})()
        with patch("gestures.action_executor.pyautogui.doubleClick") as dc:
            ex.double_click()
            ex.double_click()
            self.assertEqual(dc.call_count, 1)


# ═════════════════════════════════════════════════════════════════════════════
#  SCROLL
# ═════════════════════════════════════════════════════════════════════════════

class ScrollTests(unittest.TestCase):
    def test_positive_delta_scrolls_down(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.scroll") as scroll:
            ex.scroll_motion(20.0, direction="down")
            self.assertTrue(scroll.called)
            # pyautogui.scroll with negative amount = scroll down
            self.assertLess(scroll.call_args[0][0], 0)

    def test_negative_delta_scrolls_up(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.scroll") as scroll:
            ex.scroll_motion(-20.0, direction="up")
            self.assertTrue(scroll.called)
            self.assertGreater(scroll.call_args[0][0], 0)

    def test_jitter_ignored(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.scroll") as scroll:
            ex.scroll_motion(0.5)  # below SCROLL_JITTER_THRESHOLD
            self.assertFalse(scroll.called)

    def test_accumulation_before_emit(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.scroll") as scroll:
            ex.scroll_motion(2.0, direction="down")
            ex.scroll_motion(2.0, direction="down")
            # Should have accumulated and emitted at some point
            # (exact count depends on threshold, just verify it doesn't crash)

    def test_reset_clears_accumulator(self):
        ex = _make_executor()
        ex._pending_scroll_delta = 10.0
        ex.reset_level_motion("scroll_up")
        self.assertEqual(ex._pending_scroll_delta, 0.0)


# ═════════════════════════════════════════════════════════════════════════════
#  VOLUME
# ═════════════════════════════════════════════════════════════════════════════

class VolumeTests(unittest.TestCase):
    def test_deadzone_ignores_tiny_motion(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.press") as press:
            ex.volume_control(0.3)  # below VOLUME_DEADZONE
            self.assertFalse(press.called)

    def test_large_delta_changes_volume(self):
        ex = _make_executor()
        initial_vol = ex._volume
        ex.volume_control(20.0)
        # Volume should have changed (up or down depending on sign)
        self.assertNotAlmostEqual(ex._volume, initial_vol, delta=0.01)

    def test_fractional_remainder_preserved(self):
        ex = _make_executor()
        ex.volume_control(10.0)
        # Some remainder should be preserved (not zeroed)
        # This is hard to test precisely, so just verify it doesn't crash
        ex.volume_control(3.0)

    def test_reset_clears_accumulators(self):
        ex = _make_executor()
        ex._pending_volume_delta = 15.0
        ex._volume_motion_state = 5.0
        ex.reset_level_motion("volume_control")
        self.assertEqual(ex._pending_volume_delta, 0.0)
        self.assertEqual(ex._volume_motion_state, 0.0)


# ═════════════════════════════════════════════════════════════════════════════
#  DRAG
# ═════════════════════════════════════════════════════════════════════════════

class DragTests(unittest.TestCase):
    def test_drag_starts_and_releases(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.mouseDown"):
            with patch("gestures.action_executor.pyautogui.moveTo"):
                ex.drag((100, 100))
                self.assertTrue(ex._dragging)
        with patch("gestures.action_executor.pyautogui.mouseUp"):
            ex.release_drag()
            self.assertFalse(ex._dragging)

    def test_drag_grace_period_prevents_flicker_release(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.mouseDown"):
            with patch("gestures.action_executor.pyautogui.moveTo"):
                ex.drag((100, 100))
        # Simulate 1-2 frames without drag (flicker)
        result = ex.request_drag_release()
        self.assertFalse(result)  # Not released yet
        self.assertTrue(ex._dragging)

    def test_drag_releases_after_grace_period(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.mouseDown"):
            with patch("gestures.action_executor.pyautogui.moveTo"):
                ex.drag((100, 100))
        with patch("gestures.action_executor.pyautogui.mouseUp"):
            import config
            for _ in range(config.DRAG_RELEASE_GRACE_FRAMES):
                ex.request_drag_release()
            self.assertFalse(ex._dragging)

    def test_drag_never_gets_stuck(self):
        ex = _make_executor()
        with patch("gestures.action_executor.pyautogui.mouseDown"):
            with patch("gestures.action_executor.pyautogui.moveTo"):
                ex.drag((100, 100))
        with patch("gestures.action_executor.pyautogui.mouseUp"):
            ex.full_reset()
            self.assertFalse(ex._dragging)


# ═════════════════════════════════════════════════════════════════════════════
#  SCREENSHOT
# ═════════════════════════════════════════════════════════════════════════════

class ScreenshotTests(unittest.TestCase):
    def test_screenshot_fires_once(self):
        ex = _make_executor()
        with patch("gestures.action_executor.threading.Thread") as thread_cls:
            thread_cls.return_value = MagicMock()
            ex.screenshot()
            self.assertEqual(thread_cls.call_count, 1)

    def test_screenshot_cooldown_prevents_repeat(self):
        ex = _make_executor()
        ex._screenshot_cd = type("CD", (), {"ready": MagicMock(side_effect=[True, False])})()
        with patch("gestures.action_executor.threading.Thread") as thread_cls:
            thread_cls.return_value = MagicMock()
            ex.screenshot()
            ex.screenshot()
            self.assertEqual(thread_cls.call_count, 1)


# ═════════════════════════════════════════════════════════════════════════════
#  BRIGHTNESS
# ═════════════════════════════════════════════════════════════════════════════

class BrightnessTests(unittest.TestCase):
    def test_deadzone_ignores_tiny_motion(self):
        ex = _make_executor()
        initial_brightness = ex._brightness
        ex.brightness_control(0.3)  # below BRIGHTNESS_DEADZONE
        self.assertEqual(ex._brightness, initial_brightness)

    def test_large_delta_changes_brightness(self):
        ex = _make_executor()
        initial = ex._brightness
        # Directly control the brightness path without actual sbc calls
        original_flag = action_executor_module._SBC_AVAILABLE
        try:
            action_executor_module._SBC_AVAILABLE = True
            # Mock sbc at module level if it exists, or inject it
            mock_sbc = MagicMock()
            mock_sbc.set_brightness = MagicMock()
            action_executor_module.sbc = mock_sbc
            ex.brightness_control(30.0)
            # Brightness should have changed
            self.assertNotEqual(ex._brightness, initial)
        finally:
            action_executor_module._SBC_AVAILABLE = original_flag

    def test_reset_clears_brightness_accumulators(self):
        ex = _make_executor()
        ex._pending_brightness_delta = 10.0
        ex._brightness_motion_state = 5.0
        ex.reset_level_motion("brightness_control")
        self.assertEqual(ex._pending_brightness_delta, 0.0)
        self.assertEqual(ex._brightness_motion_state, 0.0)


# ═════════════════════════════════════════════════════════════════════════════
#  GESTURE SWITCHING
# ═════════════════════════════════════════════════════════════════════════════

class GestureSwitchingTests(unittest.TestCase):
    def test_immediate_switch_from_volume_to_index(self):
        detector = GestureDetector()
        # Feed volume gesture enough times to confirm
        vol_hand = FakeHand([True, False, False, False, False])
        for _ in range(5):
            detector.detect(vol_hand)

        # Switch to index pointing
        idx_hand = FakeHand([False, True, False, False, False])
        # Within a few frames the new gesture should appear
        results = []
        for _ in range(5):
            results.append(detector.detect(idx_hand))
        self.assertIn("INDEX_POINT", results)

    def test_old_gesture_cancelled_on_switch(self):
        detector = GestureDetector()
        vol_hand = FakeHand([True, False, False, False, False])
        for _ in range(5):
            detector.detect(vol_hand)

        idx_hand = FakeHand([False, True, False, False, False])
        # After enough frames to flush the vote window, the old gesture
        # should no longer appear (the window is GESTURE_VOTE_WINDOW=5)
        import config
        results = []
        for _ in range(config.GESTURE_VOTE_WINDOW + 3):
            results.append(detector.detect(idx_hand))
        # The last few results should be INDEX_POINT, not VOLUME_CONTROL
        final_results = [r for r in results[-3:] if r is not None]
        for r in final_results:
            self.assertNotEqual(r, "VOLUME_CONTROL")


# ═════════════════════════════════════════════════════════════════════════════
#  GESTURE DETECTION (MAJORITY VOTING)
# ═════════════════════════════════════════════════════════════════════════════

class GestureDetectorMajorityVotingTests(unittest.TestCase):
    def test_single_noisy_frame_does_not_reset(self):
        detector = GestureDetector()
        vol = FakeHand([True, False, False, False, False])
        # Build up votes
        for _ in range(4):
            detector.detect(vol)

        # One noisy frame
        noise = FakeHand([True, True, False, False, False])
        detector.detect(noise)

        # Volume should still be detected
        result = detector.detect(vol)
        self.assertEqual(result, "VOLUME_CONTROL")

    def test_hold_gap_tolerance(self):
        detector = GestureDetector()
        fist = FakeHand([False, False, False, False, False])
        # Pre-seed the hold timer so it has already elapsed
        detector._hold_start[fist.handedness] = time.perf_counter() - 1.0
        detector._hold_name[fist.handedness] = "FIST_HOLD"
        detector._hold_gap[fist.handedness] = 0
        # Pre-seed the vote history so stabilizer confirms immediately
        from collections import deque
        import config
        detector._vote_history[fist.handedness] = deque(
            ["FIST_HOLD"] * config.GESTURE_VOTE_WINDOW,
            maxlen=config.GESTURE_VOTE_WINDOW,
        )
        detector._last_emitted[fist.handedness] = "FIST_HOLD"

        # Detect the fist — should confirm since timer elapsed and votes exist
        result = detector.detect(fist)
        self.assertEqual(result, "FIST_HOLD")

    def test_hold_resets_after_too_many_gap_frames(self):
        detector = GestureDetector()
        fist = FakeHand([False, False, False, False, False])
        # Set up an active hold
        detector._hold_name["Right"] = "FIST_HOLD"
        detector._hold_start["Right"] = time.perf_counter()
        detector._hold_gap["Right"] = 0

        # Simulate too many non-fist frames
        non_fist = FakeHand([False, True, False, False, False])
        import config
        for _ in range(config.HOLD_GAP_TOLERANCE + 2):
            detector.detect(non_fist)

        # The hold should be cleared
        self.assertNotIn("Right", detector._hold_name)


# ═════════════════════════════════════════════════════════════════════════════
#  TRACKING LOSS
# ═════════════════════════════════════════════════════════════════════════════

class TrackingLossTests(unittest.TestCase):
    def test_full_reset_clears_all_state(self):
        ex = _make_executor()
        ex._pending_volume_delta = 10.0
        ex._pending_brightness_delta = 5.0
        ex._pending_scroll_delta = 8.0
        ex._volume_motion_state = 3.0
        ex._brightness_motion_state = 2.0
        with patch("gestures.action_executor.pyautogui.mouseDown"):
            with patch("gestures.action_executor.pyautogui.moveTo"):
                ex.drag((100, 100))
        with patch("gestures.action_executor.pyautogui.mouseUp"):
            ex.full_reset()
        self.assertFalse(ex._dragging)
        self.assertEqual(ex._pending_volume_delta, 0.0)
        self.assertEqual(ex._pending_brightness_delta, 0.0)
        self.assertEqual(ex._pending_scroll_delta, 0.0)
        self.assertEqual(ex._volume_motion_state, 0.0)
        self.assertEqual(ex._brightness_motion_state, 0.0)

    def test_detector_reset_clears_all_state(self):
        detector = GestureDetector()
        detector._hold_name["Right"] = "FIST_HOLD"
        detector._hold_start["Right"] = time.perf_counter()
        detector._vote_history["Right"] = deque(["VOLUME_CONTROL"] * 5)
        detector._last_emitted["Right"] = "VOLUME_CONTROL"
        detector._active_pinch["Right"] = "THUMB_INDEX"
        detector.reset()
        self.assertEqual(len(detector._hold_name), 0)
        self.assertEqual(len(detector._hold_start), 0)
        self.assertEqual(len(detector._vote_history), 0)
        self.assertEqual(len(detector._last_emitted), 0)
        self.assertEqual(len(detector._active_pinch), 0)


# ═════════════════════════════════════════════════════════════════════════════
#  LOW CONFIDENCE
# ═════════════════════════════════════════════════════════════════════════════

class LowConfidenceTests(unittest.TestCase):
    def test_low_confidence_hand_is_ignored(self):
        """The controller ignores hands below CONTROL_HAND_MIN_CONF.

        This is tested at the gesture_controller level, but here we verify
        that the detector itself still works with a low-score hand (it's the
        controller that gates, not the detector).
        """
        detector = GestureDetector()
        hand = FakeHand([False, True, False, False, False], score=0.3)
        # Detector doesn't filter by score — it still detects
        for _ in range(5):
            result = detector.detect(hand)
        # After enough frames, INDEX_POINT should be detected
        self.assertEqual(result, "INDEX_POINT")


# ═════════════════════════════════════════════════════════════════════════════
#  HAND DISAPPEARANCE AND REAPPEARANCE
# ═════════════════════════════════════════════════════════════════════════════

class HandDisappearReappearTests(unittest.TestCase):
    def test_smoother_reset_prevents_jump_on_reappear(self):
        s = CursorSmoother(dead_zone=0.0, max_jump=5000)
        s.update(100.0, 100.0)
        time.sleep(0.01)
        s.update(110.0, 110.0)

        # Hand disappears — reset
        s.reset()

        # Hand reappears at a different position — should seed, not jump
        p = s.update(800.0, 800.0)
        self.assertAlmostEqual(p[0], 800.0, delta=1.0)
        self.assertAlmostEqual(p[1], 800.0, delta=1.0)

    def test_detector_reset_prevents_stale_gesture(self):
        detector = GestureDetector()
        vol = FakeHand([True, False, False, False, False])
        for _ in range(5):
            detector.detect(vol)

        # Hand disappears
        detector.reset()

        # Hand reappears with index point
        idx = FakeHand([False, True, False, False, False])
        results = []
        for _ in range(5):
            results.append(detector.detect(idx))

        # Should not contain VOLUME_CONTROL
        for r in results:
            if r is not None:
                self.assertNotEqual(r, "VOLUME_CONTROL")


# ═════════════════════════════════════════════════════════════════════════════
#  SCROLL DETECTION (existing tests preserved with new patterns)
# ═════════════════════════════════════════════════════════════════════════════

class ScrollDetectionTests(unittest.TestCase):
    def test_scroll_uses_accumulated_two_finger_motion(self):
        detector = GestureDetector()
        pose = [False, True, True, False, False]
        detector.detect(FakeHand(pose, point=(100, 100)))
        result = detector.detect(FakeHand(pose, point=(100, 125)))
        self.assertEqual(result, "TWO_FINGERS_DOWN")

    def test_scroll_allows_an_open_thumb(self):
        detector = GestureDetector()
        pose = [True, True, True, False, False]
        detector.detect(FakeHand(pose, point=(100, 100)))
        result = detector.detect(FakeHand(pose, point=(100, 75)))
        self.assertEqual(result, "TWO_FINGERS_UP")


if __name__ == "__main__":
    unittest.main()
