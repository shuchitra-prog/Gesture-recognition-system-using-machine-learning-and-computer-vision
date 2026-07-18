# cv/overlay.py
# Renders the real-time HUD overlay onto the OpenCV frame.
# Includes FPS, gesture info, volume bar, brightness bar, profile badge.

import cv2
import numpy as np
from typing import Dict, Any, Optional
from utils.helpers import map_range


# ── colour palette ────────────────────────────────────────────────────────────
_GREEN  = (0, 255, 136)
_CYAN   = (255, 220, 0)
_RED    = (60, 60, 255)
_WHITE  = (230, 230, 230)
_BLACK  = (10, 10, 10)
_DARK   = (20, 20, 30)
_ALPHA  = 0.55   # overlay panel transparency


def draw_hud(frame: np.ndarray,
             fps: float,
             hud: Dict[str, Any],
             volume_pct: float = 0.0,
             brightness_pct: float = 50.0) -> np.ndarray:
    """
    Draw a HUD panel in the top-left corner of *frame*.

    Parameters
    ----------
    frame          : BGR image (mutated in-place, then returned)
    fps            : current frames-per-second
    hud            : dict with keys gesture, action, profile, confidence
    volume_pct     : 0-100
    brightness_pct : 0-100
    """
    h, w = frame.shape[:2]
    panel_w, panel_h = 300, 180

    # Semi-transparent background panel
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (10 + panel_w, 10 + panel_h), _DARK, -1)
    cv2.addWeighted(overlay, _ALPHA, frame, 1 - _ALPHA, 0, frame)

    # ── Text rows ─────────────────────────────
    font  = cv2.FONT_HERSHEY_SIMPLEX
    small = 0.55
    med   = 0.65
    y     = 35

    def row(label: str, value: str, color=_WHITE, lcolor=_CYAN):
        nonlocal y
        cv2.putText(frame, label, (18, y), font, small, lcolor, 1, cv2.LINE_AA)
        cv2.putText(frame, value, (130, y), font, small, color, 1, cv2.LINE_AA)
        y += 22

    cv2.putText(frame, "GESTURE HUD", (18, y - 10), font, med, _GREEN, 2, cv2.LINE_AA)
    y += 15

    row("FPS",       f"{fps:.1f}")
    row("Profile",   hud.get("profile",    "—"))
    row("Gesture",   hud.get("gesture",    "—"), color=_GREEN)
    row("Action",    hud.get("action",     "—"))
    row("Confidence",f"{hud.get('confidence', 0.0):.0%}")

    # ── Volume bar ────────────────────────────
    _draw_bar(frame, x=10, y=200, length=100,
              pct=volume_pct, label="VOL", color=_GREEN)

    # ── Brightness bar ────────────────────────
    _draw_bar(frame, x=120, y=200, length=100,
              pct=brightness_pct, label="BRI", color=_CYAN)

    # ── Profile badge (top-right) ─────────────
    badge = hud.get("profile", "Normal")
    badge_w = 160
    cv2.rectangle(frame, (w - badge_w - 10, 10), (w - 10, 42), _DARK, -1)
    cv2.rectangle(frame, (w - badge_w - 10, 10), (w - 10, 42), _GREEN, 1)
    cv2.putText(frame, badge, (w - badge_w + 5, 32),
                font, 0.6, _GREEN, 1, cv2.LINE_AA)

    return frame


def _draw_bar(frame: np.ndarray, x: int, y: int, length: int,
              pct: float, label: str, color: tuple):
    """Horizontal percentage bar with label."""
    bar_h = 10
    pct   = max(0.0, min(1.0, pct / 100.0))
    filled = int(length * pct)

    cv2.rectangle(frame, (x, y), (x + length, y + bar_h), _DARK, -1)
    cv2.rectangle(frame, (x, y), (x + filled, y + bar_h), color, -1)
    cv2.rectangle(frame, (x, y), (x + length, y + bar_h), color, 1)

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, label, (x, y - 3), font, 0.4, color, 1, cv2.LINE_AA)
    cv2.putText(frame, f"{int(pct*100)}%",
                (x + length + 4, y + bar_h - 1), font, 0.4, color, 1, cv2.LINE_AA)


def draw_pinch_line(frame: np.ndarray,
                    p1: tuple, p2: tuple,
                    distance: float,
                    threshold: float):
    """Visualise pinch gesture with a coloured line between two points."""
    color = (0, 255, 0) if distance < threshold else (0, 100, 255)
    cv2.line(frame, p1, p2, color, 2)
    mid = ((p1[0]+p2[0])//2, (p1[1]+p2[1])//2)
    cv2.circle(frame, mid, 8, color, -1)
    cv2.putText(frame, f"{int(distance)}px", (mid[0]+10, mid[1]),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
