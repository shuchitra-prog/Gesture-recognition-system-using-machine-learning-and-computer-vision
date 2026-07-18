import os
import tempfile
import unittest

from database.db_manager import DBManager


class DefaultMappingTests(unittest.TestCase):
    def test_defaults_match_gestures_emitted_by_the_detector(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DBManager(os.path.join(directory, "gesture.sqlite"))
            normal = {item["gesture_name"]: item["action_name"] for item in db.get_gestures("Normal")}
            drawing = {item["gesture_name"]: item["action_name"] for item in db.get_gestures("Drawing")}
            self.assertEqual(normal["OPEN_PALM_HOLD"], "screenshot")
            self.assertEqual(normal["FIST_HOLD"], "drag")
            self.assertEqual(normal["VOLUME_CONTROL"], "volume_control")
            self.assertEqual(normal["BRIGHTNESS_CONTROL"], "brightness_control")
            self.assertEqual(drawing["INDEX_POINT"], "draw")
            self.assertEqual(drawing["FIST_HOLD"], "eraser")
            self.assertEqual(drawing["OPEN_PALM_HOLD"], "save_drawing")
            db.close()

    def test_existing_drawing_eraser_mapping_is_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "gesture.sqlite")
            db = DBManager(path)
            db._conn.execute(
                "UPDATE gestures SET gesture_name='FIST' "
                "WHERE action_name='eraser' AND profile='Drawing'"
            )
            db._conn.commit()
            db.close()

            repaired = DBManager(path)
            self.assertEqual(
                repaired.get_action_for_gesture("FIST_HOLD", "Drawing"),
                "eraser",
            )
            repaired.close()
