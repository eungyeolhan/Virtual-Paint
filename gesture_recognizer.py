"""
gesture_recognizer.py - everything about turning a camera frame into hand data.

Wraps Google's MediaPipe Gesture Recognizer: downloading/loading the model,
building the recognizer, and turning its raw output into a simple `Hand`
object. Also holds the pure-geometry gesture logic (finger up/down, pointing,
which control gesture is being shown) - none of it depends on OpenCV drawing
or the app's UI state.
"""
from __future__ import annotations

import math
import platform
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/1/gesture_recognizer.task"
)
DEFAULT_MODEL = Path(__file__).resolve().with_name("gesture_recognizer.task")

THUMB_OUT_RATIO = 0.85  # thumb tip distance from index knuckle / palm width - "thumb out" threshold


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class Hand:
    label: str        # "Left" / "Right" - the user's actual hand (see parse_hands)
    pts: list         # 21 (x, y) pixel coordinates
    gesture: str      # MediaPipe canned gesture name, e.g. "Thumb_Up"
    score: float


# --------------------------------------------------------------------------- #
# Gesture logic (pure landmark geometry, rotation-invariant)
# --------------------------------------------------------------------------- #
def finger_states(pts):
    """Return (index, middle, ring, pinky, thumb_out) booleans."""
    wrist = pts[0]
    up = [dist(pts[t], wrist) > dist(pts[p], wrist) * 1.10
          for t, p in ((8, 6), (12, 10), (16, 14), (20, 18))]
    palm_width = max(dist(pts[5], pts[17]), 1e-6)
    thumb_out = dist(pts[4], pts[5]) > THUMB_OUT_RATIO * palm_width
    return (*up, thumb_out)


def is_pointing(pts) -> bool:
    i, m, r, p, _ = finger_states(pts)
    return i and not m and not r and not p


def classify_control(pts, gesture: str):
    """Return a tool id, 'open' (open palm), or None (fist / unknown -> keep tool)."""
    if gesture == "Thumb_Up":
        return "eraser"
    i, m, r, p, thumb = finger_states(pts)
    pattern = (i, m, r, p)
    if pattern == (False, False, False, False):
        return "fist"
    if pattern == (True, False, False, False):
        return "pen"
    if pattern == (True, True, False, False):
        return "marker"
    if pattern == (True, True, True, False):
        return "spray"
    if pattern == (True, True, True, True):
        return "open" if thumb else "neon"
    return None


# --------------------------------------------------------------------------- #
# MediaPipe plumbing
# --------------------------------------------------------------------------- #
def ensure_model(path: Path = DEFAULT_MODEL):
    """Download the gesture model next to this file, once."""
    if path.exists():
        return
    print(f"Downloading MediaPipe gesture model to {path} (one-time, ~8 MB)...")
    tmp = path.with_suffix(".part")
    ctx = None
    try:
        import ssl
        import certifi  # optional; fixes cert errors on some macOS Python installs
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        with urllib.request.urlopen(MODEL_URL, context=ctx, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(path)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        sys.exit(f"Could not download the model ({e}).\n"
                 f"Download it manually from:\n  {MODEL_URL}\n"
                 f"and save it as:\n  {path}")


def check_mediapipe_version():
    """mediapipe 1.x currently hard-aborts on macOS ("Service is unavailable"), which
    can't be caught from Python - so detect it up front and explain the fix."""
    ver = getattr(mp, "__version__", "0")
    try:
        major = int(ver.split(".")[0])
    except ValueError:
        return
    if platform.system() == "Darwin" and major >= 1:
        sys.exit(
            f"mediapipe {ver} is installed, but the 1.x releases currently crash on macOS "
            "('Service is unavailable').\n"
            "Fix: reinstall the 0.10 series, using Python 3.12 (see README > Troubleshooting):\n"
            "    pip uninstall -y mediapipe opencv-python opencv-contrib-python opencv-python-headless\n"
            "    pip install -r requirements.txt\n"
            "(Run with --skip-version-check to try anyway.)")


def create_recognizer(model_path: Path):
    """Build a ready-to-use GestureRecognizer (VIDEO mode, up to 2 hands, CPU delegate)."""
    options = vision.GestureRecognizerOptions(
        base_options=mp_tasks.BaseOptions(
            model_asset_buffer=model_path.read_bytes(),
            delegate=mp_tasks.BaseOptions.Delegate.CPU,
        ),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.GestureRecognizer.create_from_options(options)


def parse_hands(result, w, h) -> list[Hand]:
    """Convert one recognizer result into a list of Hand objects.

    MediaPipe's handedness label is computed as if the image were NOT mirrored,
    but the app mirrors the camera frame before this (so it behaves like a
    mirror on screen). That flips left and right, so we invert the label here
    to match what the user actually sees and feels.
    """
    hands = []
    for i, lms in enumerate(result.hand_landmarks):
        pts = [(lm.x * w, lm.y * h) for lm in lms]
        raw_label = result.handedness[i][0].category_name
        label = "Left" if raw_label == "Right" else "Right"
        gesture, score = "", 0.0
        if i < len(result.gestures) and result.gestures[i]:
            gesture, score = result.gestures[i][0].category_name, result.gestures[i][0].score
        hands.append(Hand(label, pts, gesture, score))
    return hands
