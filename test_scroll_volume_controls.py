import unittest
from unittest.mock import patch

import gestures.action_executor as action_executor_module
from gestures.action_executor import ActionExecutor


class ScrollVolumeControlTests(unittest.TestCase):
    def setUp(self):
        self.executor = ActionExecutor(1920, 1080, 640, 480, sensitivity=1.0, smoothing=1)
        self.executor._scroll_cd = type("CooldownStub", (), {"ready": staticmethod(lambda: True)})()
        self.executor._level_cd = type("CooldownStub", (), {"ready": staticmethod(lambda: True)})()
        self.executor._action_cd = type("CooldownStub", (), {"ready": staticmethod(lambda: True)})()
        self.executor._vol_interface = None

    def test_slow_scroll_accumulates_before_emitting(self):
        with patch("gestures.action_executor.pyautogui.scroll") as scroll:
            # With the new lower threshold (~8.0), 3.0*1.25 = 3.75 per call
            # Two calls = 7.5 (below threshold), third should cross it
            self.executor.scroll_motion(3.0, direction="down")
            self.assertEqual(scroll.call_count, 0)
            self.executor.scroll_motion(3.0, direction="down")
            self.assertEqual(scroll.call_count, 0)
            self.executor.scroll_motion(3.0, direction="down")
            self.assertGreaterEqual(scroll.call_count, 1)

    def test_fast_scroll_emits_immediately(self):
        with patch("gestures.action_executor.pyautogui.scroll") as scroll:
            self.executor.scroll_down(20.0)
            self.assertEqual(scroll.call_count, 1)

    def test_continuous_scroll_keeps_moving_while_gesture_is_active(self):
        with patch("gestures.action_executor.pyautogui.scroll") as scroll:
            self.executor.scroll_up(20.0)
            self.executor.scroll_up(6.0)
            self.assertGreaterEqual(scroll.call_count, 2)

    def test_slow_volume_adjustment_accumulates_until_threshold(self):
        with patch("gestures.action_executor.pyautogui.press") as press:
            # Feed enough small deltas to cross the step_size threshold
            for _ in range(8):
                self.executor.volume_control(2.0)
            # Volume should have moved from 50 (some direction)
            self.assertNotAlmostEqual(self.executor._volume, 50.0, delta=0.1)

    def test_fast_volume_adjustment_changes_volume_quickly(self):
        with patch("gestures.action_executor.pyautogui.press") as press:
            self.executor.volume_control(16.0)
            # Volume should have changed from the initial 50
            self.assertNotAlmostEqual(self.executor._volume, 50.0, delta=0.1)

    def test_gesture_switching_resets_accumulators(self):
        with patch("gestures.action_executor.pyautogui.press") as press:
            self.executor.volume_control(16.0)
            self.executor.reset_level_motion("volume_control")
            self.assertEqual(self.executor._pending_volume_delta, 0.0)
            self.assertEqual(self.executor._volume_motion_state, 0.0)

    def test_tracking_loss_clears_pending_motion(self):
        with patch("gestures.action_executor.pyautogui.scroll") as scroll:
            self.executor.scroll_up(20.0)
            self.executor.reset_level_motion("scroll_up")
            self.executor.scroll_up(2.0)
            self.assertEqual(scroll.call_count, 1)
