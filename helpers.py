# utils/helpers.py
# Small pure-function helpers used across the project.

import math
import time
from collections import deque
from typing import Tuple, List


# ──────────────────────────────────────────────
#  GEOMETRY
# ──────────────────────────────────────────────

def euclidean(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Euclidean distance between two 2-D points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def midpoint(p1: Tuple[float, float], p2: Tuple[float, float]) -> Tuple[float, float]:
    """Midpoint of a segment."""
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


def map_range(value: float, in_min: float, in_max: float,
              out_min: float, out_max: float) -> float:
    """
    Linearly map *value* from [in_min, in_max] to [out_min, out_max].
    Clamps the result to the output range.
    """
    if in_max == in_min:
        return out_min
    mapped = (value - in_min) / (in_max - in_min) * (out_max - out_min) + out_min
    return max(out_min, min(out_max, mapped))


# ──────────────────────────────────────────────
#  SMOOTHING / FILTERING
# ──────────────────────────────────────────────

class MovingAverage:
    """Rolling-average smoother for (x, y) cursor coordinates."""

    def __init__(self, window: int = 5):
        self.wx = deque(maxlen=window)
        self.wy = deque(maxlen=window)

    def update(self, x: float, y: float) -> Tuple[float, float]:
        self.wx.append(x)
        self.wy.append(y)
        return sum(self.wx) / len(self.wx), sum(self.wy) / len(self.wy)

    def reset(self):
        self.wx.clear()
        self.wy.clear()


class AdaptiveSmoother:
    """Low-lag cursor filter that becomes more responsive during fast moves."""

    def __init__(self, min_alpha: float = 0.28, max_alpha: float = 0.82):
        self.min_alpha = min_alpha
        self.max_alpha = max_alpha
        self._point = None

    def update(self, x: float, y: float) -> Tuple[float, float]:
        if self._point is None:
            self._point = (x, y)
            return self._point
        px, py = self._point
        distance = math.hypot(x - px, y - py)
        # Small movements are filtered heavily; quick deliberate movements are
        # allowed through so the cursor reaches screen edges without lag.
        alpha = min(self.max_alpha, self.min_alpha + distance / 500.0)
        self._point = (px + (x - px) * alpha, py + (y - py) * alpha)
        return self._point

    def reset(self):
        self._point = None


class OneEuroFilter:
    """The 1€ Filter — adaptive low-pass whose cutoff rises with speed.

    Reference: Casiez, Roussel & Vogel, CHI 2012.
    ``min_cutoff``  controls jitter (lower = smoother when still).
    ``beta``        controls lag   (higher = less lag during fast motion).
    ``d_cutoff``    smooths the speed estimate itself.
    """

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007,
                 d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev: float = 0.0
        self._dx_prev: float = 0.0
        self._t_prev: float = 0.0
        self._initialized = False

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / max(dt, 1e-9))

    def __call__(self, x: float, t: float) -> float:
        if not self._initialized:
            self._x_prev = x
            self._dx_prev = 0.0
            self._t_prev = t
            self._initialized = True
            return x

        dt = max(t - self._t_prev, 1e-9)
        self._t_prev = t

        # Derivative (speed) estimate
        dx = (x - self._x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        self._dx_prev = dx_hat

        # Adaptive cutoff based on speed
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev
        self._x_prev = x_hat
        return x_hat

    def reset(self):
        self._initialized = False
        self._x_prev = 0.0
        self._dx_prev = 0.0
        self._t_prev = 0.0


class CursorSmoother:
    """Smooth cursor filter combining One Euro with dead zone & velocity clamp.

    Parameters are read from ``config`` at construction time so that run-time
    tuning via the settings page takes effect on next camera restart.
    """

    def __init__(self,
                 min_cutoff: float = None,
                 beta: float = None,
                 d_cutoff: float = None,
                 dead_zone: float = None,
                 max_jump: float = None):
        import config as _cfg
        self._fx = OneEuroFilter(
            min_cutoff=min_cutoff if min_cutoff is not None else _cfg.CURSOR_MIN_CUTOFF,
            beta=beta if beta is not None else _cfg.CURSOR_BETA,
            d_cutoff=d_cutoff if d_cutoff is not None else _cfg.CURSOR_D_CUTOFF,
        )
        self._fy = OneEuroFilter(
            min_cutoff=min_cutoff if min_cutoff is not None else _cfg.CURSOR_MIN_CUTOFF,
            beta=beta if beta is not None else _cfg.CURSOR_BETA,
            d_cutoff=d_cutoff if d_cutoff is not None else _cfg.CURSOR_D_CUTOFF,
        )
        self._dead_zone = dead_zone if dead_zone is not None else _cfg.CURSOR_DEAD_ZONE
        self._max_jump = max_jump if max_jump is not None else _cfg.CURSOR_MAX_JUMP
        self._last_out: Tuple[float, float] = None

    def update(self, x: float, y: float) -> Tuple[float, float]:
        t = time.perf_counter()

        # First frame — seed filter and output position without movement
        if self._last_out is None:
            sx = self._fx(x, t)
            sy = self._fy(y, t)
            self._last_out = (sx, sy)
            return self._last_out

        lx, ly = self._last_out

        # Velocity clamp — reject single-frame jumps from noisy landmarks
        dx, dy = x - lx, y - ly
        dist = math.hypot(dx, dy)
        if dist > self._max_jump:
            scale = self._max_jump / dist
            x = lx + dx * scale
            y = ly + dy * scale

        sx = self._fx(x, t)
        sy = self._fy(y, t)

        # Dead zone — suppress micro-tremor when the hand is nearly still
        out_dx = sx - lx
        out_dy = sy - ly
        if math.hypot(out_dx, out_dy) < self._dead_zone:
            return self._last_out

        self._last_out = (sx, sy)
        return self._last_out

    def reset(self):
        """Clear filter state but PRESERVE the last output position.  # MODIFIED

        When MediaPipe temporarily loses tracking, the next detection may
        start at a wildly different landmark position.  By keeping
        ``_last_out`` intact, the velocity clamp in ``update()`` will limit
        the jump instead of letting the cursor teleport to (0, 0) or
        bottom-left.  The One Euro filters are reset so they re-seed from
        the new input, but the dead-zone and clamp still reference the old
        cursor position.
        """
        self._fx.reset()
        self._fy.reset()
        # NOTE: intentionally NOT clearing self._last_out  # MODIFIED


# ──────────────────────────────────────────────
#  FPS COUNTER
# ──────────────────────────────────────────────

class FPSCounter:
    """Compute a rolling FPS using timestamps of the last N frames."""

    def __init__(self, window: int = 30):
        self._times: deque = deque(maxlen=window)

    def tick(self) -> float:
        self._times.append(time.perf_counter())
        if len(self._times) < 2:
            return 0.0
        elapsed = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / elapsed if elapsed > 0 else 0.0


# ──────────────────────────────────────────────
#  COOLDOWN GUARD
# ──────────────────────────────────────────────

class Cooldown:
    """Prevent an action from firing more often than *ms* milliseconds."""

    def __init__(self, ms: float = 400):
        self.ms = ms
        self._last = 0.0

    def ready(self) -> bool:
        now = time.perf_counter() * 1000
        if now - self._last >= self.ms:
            self._last = now
            return True
        return False

    def reset(self):
        self._last = 0.0
