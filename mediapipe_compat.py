"""MediaPipe import compatibility without Matplotlib.

MediaPipe 0.10.x imports ``matplotlib.pyplot`` from its drawing utility module
even when an application only uses hand tracking. This project uses OpenCV for
all overlays, so the plotting helper is neither needed nor loaded.
"""

from dataclasses import dataclass
import sys
import types
from typing import Tuple


@dataclass(frozen=True)
class DrawingSpec:
    """Small API-compatible drawing specification for MediaPipe style imports."""

    color: Tuple[int, int, int] = (224, 224, 224)
    thickness: int = 2
    circle_radius: int = 2


def install_no_matplotlib_drawing_utils() -> None:
    """Pre-register a no-plot drawing module before importing MediaPipe.

    MediaPipe's solution package imports this module during initialisation. The
    replacement exposes the one symbol used by ``drawing_styles`` but never
    imports Matplotlib. The application draws hand landmarks itself with OpenCV.
    """
    module_name = "mediapipe.python.solutions.drawing_utils"
    if module_name in sys.modules:
        return

    module = types.ModuleType(module_name)
    module.DrawingSpec = DrawingSpec
    sys.modules[module_name] = module
