"""
motion.py - anything to do with movement over time: smoothing a fingertip's
path, detecting a wave gesture, and sensing overall motion in the frame.
"""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np


class Smoother:
    """Adaptive exponential smoothing: steady when slow, responsive when fast.

    Used on the drawing fingertip so strokes look clean without lagging behind
    a fast-moving hand.
    """

    def __init__(self):
        self.p = None

    def reset(self):
        self.p = None

    def update(self, pt):
        pt = np.asarray(pt, dtype=float)
        if self.p is None:
            self.p = pt.copy()
        else:
            d = float(np.linalg.norm(pt - self.p))
            a = float(np.clip(0.35 + d / 80.0, 0.35, 0.95))
            self.p += a * (pt - self.p)
        return self.p


class WaveDetector:
    """Detects left-right waving from a stream of (time, x) samples."""

    def __init__(self, window=1.4, min_swing=0.06, reversals=3):
        self.window, self.min_swing, self.reversals = window, min_swing, reversals
        self.hist = deque()

    def reset(self):
        self.hist.clear()

    def update(self, x, t, width) -> bool:
        self.hist.append((t, x))
        while self.hist and t - self.hist[0][0] > self.window:
            self.hist.popleft()
        xs = [p[1] for p in self.hist]
        if len(xs) < 8:
            return False
        thr = self.min_swing * width
        last, direction, rev = xs[0], 0, 0
        for v in xs[1:]:
            if direction == 0:
                if v - last > thr:
                    direction, last = 1, v
                elif last - v > thr:
                    direction, last = -1, v
            elif direction == 1:
                if v > last:
                    last = v
                elif last - v > thr:
                    direction, last, rev = -1, v, rev + 1
            else:
                if v < last:
                    last = v
                elif v - last > thr:
                    direction, last, rev = 1, v, rev + 1
        return rev >= self.reversals


class MotionSensor:
    """Cheap frame-differencing motion detector, used for the HUD motion meter
    and the optional moving-pixels overlay."""

    def __init__(self):
        self.prev = None
        self.level = 0.0
        self.mask = None

    def update(self, frame):
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (160, max(1, int(160 * h / w))))
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (7, 7), 0)
        if self.prev is None or self.prev.shape != gray.shape:
            self.prev = gray
            self.mask = np.zeros_like(gray)
            return
        diff = cv2.absdiff(gray, self.prev)
        self.prev = gray
        _, mask = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
        self.mask = cv2.dilate(mask, None, iterations=1)
        raw = np.count_nonzero(self.mask) / self.mask.size
        self.level = 0.7 * self.level + 0.3 * raw
