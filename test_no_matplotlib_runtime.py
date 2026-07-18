"""Regression test: the hand-tracking import must work when Matplotlib is blocked."""

import subprocess
import sys
import textwrap
import unittest


class NoMatplotlibRuntimeTests(unittest.TestCase):
    def test_hand_tracker_never_imports_matplotlib(self):
        code = textwrap.dedent(
            """
            import builtins
            import sys

            original_import = builtins.__import__
            def guarded_import(name, *args, **kwargs):
                if name == 'matplotlib' or name.startswith('matplotlib.'):
                    raise ImportError('Matplotlib is intentionally unavailable')
                return original_import(name, *args, **kwargs)

            builtins.__import__ = guarded_import
            import cv.hand_tracker
            assert not any(name == 'matplotlib' or name.startswith('matplotlib.') for name in sys.modules)
            print('MediaPipe hand tracker loaded without Matplotlib')
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", code], text=True, capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

