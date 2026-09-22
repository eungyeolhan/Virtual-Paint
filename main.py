#!/usr/bin/env python3
"""
Virtual Paint - draw in the air with your webcam (Windows / macOS / Linux).

  DRAW HAND    (default: right)  point with your index finger to draw
  CONTROL HAND (default: left)   choose the tool with a gesture:
        1 finger            -> Pen
        2 fingers           -> Marker (thick, translucent)
        3 fingers           -> Spray paint
        4 fingers, thumb in -> Neon glow
        Thumbs up           -> Eraser
        Fist / open palm    -> keep the current tool
        Wave open palm      -> clear the canvas (undoable)

  Toolbar (top): click with the mouse, or hover your drawing fingertip over a
  button for ~1 second. Pick brush, eraser, colour, thickness, undo, clear, save.

  Motion sensing: a live motion meter (frame differencing) is shown in the HUD;
  press M to overlay the moving pixels. Wave detection uses hand motion tracking.

Keys: 1-5 tools | [ ] size | c next colour | u undo | x clear | s save
      n next camera | w swap hands | k skeleton | m motion view | b whiteboard
      f fullscreen | h help | q / Esc quit

Ways to quit: the QUIT button (click it, or hover a fingertip on it ~1.5 s),
      hold BOTH thumbs down for 2 s, press q / Esc (click the video window first so
      it has keyboard focus), close the window, or press Ctrl+C in the terminal.

Install:  pip install -r requirements.txt
Run:      python main.py
"""
from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp

from gesture_recognizer import (
    DEFAULT_MODEL, check_mediapipe_version, classify_control, create_recognizer,
    dist, ensure_model, is_pointing, parse_hands,
)
from motion import MotionSensor, Smoother, WaveDetector
from overlay import COLORS, Overlay, TOOLS, dwell_time, paint_segment

WIN = "Virtual Paint"
SAVE_DIR = Path(__file__).resolve().parent / "drawings"
CAMERA_FILE = Path(__file__).resolve().with_name(".virtual_paint_camera")

MIN_SIZE, MAX_SIZE = 2, 60
TOOL_COMMIT_FRAMES = 5       # frames a control gesture must be held (and steady)
STEADY_SPEED = 0.012         # max wrist speed (fraction of frame width / frame)
QUIT_HOLD_SECONDS = 2.0      # how long to hold both thumbs down to quit


# --------------------------------------------------------------------------- #
# The application
# --------------------------------------------------------------------------- #
class App(Overlay):
    """Holds all app state and control logic. Rendering/layout come from the
    Overlay mixin (overlay.py); gesture geometry comes from gesture_recognizer.py.
    """

    def __init__(self, w, h, draw_hand="Right", wave_enabled=True):
        self.w, self.h = w, h
        self.draw_label = draw_hand
        self.wave_enabled = wave_enabled

        self.paint = np.zeros((h, w, 3), np.uint8)
        self.mask = np.zeros((h, w), np.uint8)
        self.undo_stack = deque(maxlen=20)
        self.rng = np.random.default_rng()

        self.tool = "pen"
        self.color_idx = 4
        self.size = 8

        self.smoother = Smoother()
        self.cursor = None
        self.drawing = False
        self.last_pt = None
        self.point_frames = 0
        self.lost_frames = 0

        self.cand, self.cand_n = None, 0
        self.prev_ctrl = None
        self.ctrl_speed = 0.0
        self.ctrl_pose = None
        self.wave = WaveDetector()
        self.wave_cooldown = 0.0

        self.dwell_key, self.dwell_start = None, 0.0
        self.dwell_fired, self.dwell_progress = False, 0.0
        self.click = None

        self.toast_text, self.toast_until = "", 0.0
        self.show_help = True
        self.show_skeleton = True
        self.show_motion = False
        self.whiteboard = False
        self.hands = (None, None)     # (draw hand, control hand)
        self.quit_requested = False
        self.switch_cam_requested = False
        self.camera_index = 0
        self.quit_hold_start, self.quit_progress = None, 0.0
        self.last_base = None

        self.build_layout()  # from Overlay

    # ---------------- actions ---------------- #
    def toast(self, text, seconds=1.6):
        self.toast_text, self.toast_until = text, time.time() + seconds

    def activate(self, b):
        if b.kind == "tool":
            self.tool = b.value
        elif b.kind == "color":
            self.color_idx = b.value
            if self.tool == "eraser":
                self.tool = "pen"
        elif b.kind == "size":
            self.set_size(self.size + b.value)
        elif b.kind == "undo":
            self.undo()
        elif b.kind == "clear":
            self.clear()
        elif b.kind == "save":
            self.save()
        elif b.kind == "cam":
            self.switch_cam_requested = True
        elif b.kind == "quit":
            self.quit_requested = True

    def set_size(self, value):
        self.size = int(np.clip(value, MIN_SIZE, MAX_SIZE))

    def push_undo(self):
        self.undo_stack.append((self.paint.copy(), self.mask.copy()))

    def undo(self):
        if self.undo_stack:
            self.paint, self.mask = self.undo_stack.pop()
            self.toast("Undo")
        else:
            self.toast("Nothing to undo")

    def clear(self):
        if self.mask.any():
            self.push_undo()
        self.paint[:] = 0
        self.mask[:] = 0
        self.toast("Canvas cleared")

    def save(self):
        SAVE_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.last_base if self.last_base is not None else np.full((self.h, self.w, 3), 255, np.uint8)
        cv2.imwrite(str(SAVE_DIR / f"virtualpaint_{stamp}.png"), self.composite(base))
        cv2.imwrite(str(SAVE_DIR / f"virtualpaint_{stamp}_transparent.png"),
                    np.dstack([self.paint, self.mask]))
        self.toast(f"Saved to {SAVE_DIR.name}/")

    # ---------------- drawing ---------------- #
    def brush_radius(self):
        mult = {"pen": 1, "marker": 2.4, "spray": 2.5, "neon": 1.5, "eraser": 3}[self.tool]
        return max(3, int(self.size * mult / 2 + (2 if self.tool == "spray" else 0)))

    def begin_stroke(self):
        self.push_undo()
        self.drawing = True
        self.show_help = False
        self.last_pt = self.cursor
        paint_segment(self, self.cursor, self.cursor)

    def end_stroke(self):
        self.drawing = False
        self.last_pt = None

    def stroke_to(self, pt):
        paint_segment(self, self.last_pt or pt, pt)
        self.last_pt = pt

    # ---------------- per-frame logic ---------------- #
    def assign_roles(self, hands):
        draw = ctrl = None
        if len(hands) == 1:
            if hands[0].label == self.draw_label:
                draw = hands[0]
            else:
                ctrl = hands[0]
        elif len(hands) >= 2:
            a, b = hands[0], hands[1]
            if a.label != b.label:
                draw, ctrl = (a, b) if a.label == self.draw_label else (b, a)
            else:  # same label reported twice -> fall back to screen position
                left, right = sorted((a, b), key=lambda hd: hd.pts[0][0])
                draw, ctrl = (right, left) if self.draw_label == "Right" else (left, right)
        return draw, ctrl

    def update(self, hands, t):
        thumbs_down = [hd for hd in hands if hd.gesture == "Thumb_Down" and hd.score >= 0.55]
        if len(hands) == 2 and len(thumbs_down) == 2:
            if self.quit_hold_start is None:
                self.quit_hold_start = t
            self.quit_progress = min(1.0, (t - self.quit_hold_start) / QUIT_HOLD_SECONDS)
            if self.quit_progress >= 1.0:
                self.quit_requested = True
        else:
            self.quit_hold_start, self.quit_progress = None, 0.0

        draw, ctrl = self.assign_roles(hands)
        self.hands = (draw, ctrl)
        self.handle_control(ctrl, t)
        self.handle_draw(draw, t)
        if self.click:
            x, y = self.click
            self.click = None
            b = self.button_at(x, y)
            if b:
                self.activate(b)

    def handle_control(self, hand, t):
        if hand is None:
            self.cand, self.cand_n = None, 0
            self.prev_ctrl, self.ctrl_speed, self.ctrl_pose = None, 0.0, None
            self.wave.reset()
            return
        wrist = hand.pts[9]
        speed = dist(wrist, self.prev_ctrl) if self.prev_ctrl else 0.0
        self.ctrl_speed = 0.6 * self.ctrl_speed + 0.4 * speed
        self.prev_ctrl = wrist
        gesture = hand.gesture if hand.score >= 0.55 else ""
        pose = classify_control(hand.pts, gesture)
        self.ctrl_pose = pose
        steady = self.ctrl_speed < STEADY_SPEED * self.w

        if pose in TOOLS:
            if pose != self.cand:
                self.cand, self.cand_n = pose, 0
            if steady:
                self.cand_n += 1
            if self.cand_n >= TOOL_COMMIT_FRAMES:
                self.tool = pose
        else:
            self.cand, self.cand_n = None, 0

        if self.wave_enabled and pose in ("open", "neon"):
            if t > self.wave_cooldown and self.wave.update(wrist[0], t, self.w):
                self.clear()
                self.toast("Canvas cleared (wave) - press U to undo")
                self.wave.reset()
                self.wave_cooldown = t + 2.0
        else:
            self.wave.reset()

    def handle_draw(self, hand, t):
        if hand is None:
            self.end_stroke()
            self.smoother.reset()
            self.cursor = None
            self.point_frames = self.lost_frames = 0
            self.dwell_key, self.dwell_progress = None, 0.0
            return

        tip = self.smoother.update(hand.pts[8])
        self.cursor = (int(tip[0]), int(tip[1]))

        # Fingertip over the toolbar: hover-to-press, never draw.
        if self.cursor[1] < self.toolbar_h:
            self.end_stroke()
            self.point_frames = 0
            b = self.button_at(*self.cursor)
            if b is None:
                self.dwell_key, self.dwell_progress, self.dwell_fired = None, 0.0, False
            elif b is not self.dwell_key:
                self.dwell_key, self.dwell_start, self.dwell_fired = b, t, False
                self.dwell_progress = 0.0
            elif not self.dwell_fired:
                self.dwell_progress = min(1.0, (t - self.dwell_start) / dwell_time(b))
                if self.dwell_progress >= 1.0:
                    self.activate(b)
                    self.dwell_fired = True
                    if b.kind == "size":            # keep repeating while hovering
                        self.dwell_start, self.dwell_fired = t, False
            return
        self.dwell_key, self.dwell_progress = None, 0.0

        # Pen up/down with a little hysteresis so tracking flicker doesn't split strokes.
        if is_pointing(hand.pts):
            self.point_frames += 1
            self.lost_frames = 0
        else:
            self.lost_frames += 1
            self.point_frames = 0
        if not self.drawing and self.point_frames >= 2:
            self.begin_stroke()
        elif self.drawing and self.lost_frames >= 3:
            self.end_stroke()
        elif self.drawing and self.point_frames > 0:
            self.stroke_to(self.cursor)


# --------------------------------------------------------------------------- #
# Camera helpers
# --------------------------------------------------------------------------- #
def open_camera(index, width, height):
    system = platform.system()
    if system == "Windows":
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    elif system == "Darwin":
        backends = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
    else:
        backends = [cv2.CAP_ANY]
    for backend in backends:
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            continue
        if system == "Windows":
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        ok, _ = cap.read()
        if ok:
            return cap
        cap.release()
    return None


def fit_frame(frame, w, h):
    """Centre-crop to the app's aspect ratio and resize, so switching cameras is seamless."""
    fh, fw = frame.shape[:2]
    if (fw, fh) == (w, h):
        return frame
    target, cur = w / h, fw / fh
    if cur > target + 0.01:
        nw = int(fh * target)
        x0 = (fw - nw) // 2
        frame = frame[:, x0:x0 + nw]
    elif cur < target - 0.01:
        nh = int(fw / target)
        y0 = (fh - nh) // 2
        frame = frame[y0:y0 + nh]
    return cv2.resize(frame, (w, h))


def load_saved_camera() -> int:
    try:
        return max(0, int(CAMERA_FILE.read_text().strip()))
    except Exception:
        return 0


def save_camera(index: int):
    try:
        CAMERA_FILE.write_text(str(index))
    except Exception:
        pass


def switch_camera(cap, current, width, height, max_index=5):
    """Move to the next working camera index (wrapping around). Keeps the old one if none work."""
    for step in range(1, max_index + 1):
        idx = (current + step) % (max_index + 1)
        if idx == current:
            continue
        new = open_camera(idx, width, height)
        if new is not None:
            cap.release()
            return new, idx
    return cap, current


def list_cameras(width, height, count=6):
    print("Probing cameras (this can take a few seconds)...")
    for idx in range(count):
        cap = open_camera(idx, width, height)
        if cap is None:
            print(f"  camera {idx}: not available")
            continue
        print(f"  camera {idx}: OK ({int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
              f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})")
        cap.release()
    print("Pick one with --camera N (or press N inside the app to cycle). "
          "On a Mac, a nearby iPhone (Continuity Camera) can take index 0.")


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Draw in the air with your webcam.")
    ap.add_argument("--camera", type=int, default=None,
                    help="camera index (default: the last one you used, else 0). Press N in the app to switch.")
    ap.add_argument("--list-cameras", action="store_true", help="probe camera indexes and exit")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--draw-hand", choices=["Left", "Right"], default="Right",
                    help="which hand draws (the other one is the control hand)")
    ap.add_argument("--no-wave-clear", action="store_true", help="disable wave-to-clear")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="path to gesture_recognizer.task")
    ap.add_argument("--skip-version-check", action="store_true", help="skip the macOS mediapipe 1.x check")
    args = ap.parse_args()

    if args.list_cameras:
        list_cameras(args.width, args.height)
        return
    if not args.skip_version_check:
        check_mediapipe_version()

    ensure_model(args.model)
    cam_idx = args.camera if args.camera is not None else load_saved_camera()
    cap = open_camera(cam_idx, args.width, args.height)
    if cap is None and args.camera is None and cam_idx != 0:
        cam_idx = 0
        cap = open_camera(0, args.width, args.height)
    if cap is None:
        sys.exit("Could not open the camera. Check that no other app is using it and that this "
                 "program has camera permission (macOS: System Settings > Privacy & Security > "
                 "Camera; Windows: Settings > Privacy > Camera). Run with --list-cameras to see "
                 "which camera indexes work.")
    print(f"Using camera {cam_idx}. Wrong camera (e.g. your iPhone)? Press N in the window, "
          f"click CAM in the toolbar, or run with --camera N.")

    recognizer = create_recognizer(args.model)

    ok, frame = cap.read()
    if not ok:
        sys.exit("Camera opened but returned no frames.")
    h, w = frame.shape[:2]
    app = App(w, h, args.draw_hand, wave_enabled=not args.no_wave_clear)
    app.camera_index = cam_idx
    motion = MotionSensor()

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, min(w, 1280), min(h, 720))
    cv2.setMouseCallback(WIN, lambda ev, x, y, fl, p: setattr(app, "click", (x, y))
                         if ev == cv2.EVENT_LBUTTONDOWN else None)

    fullscreen, last_ts, fps, prev_t, frames = False, 0, 0.0, time.time(), 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = fit_frame(frame, w, h)
            frame = cv2.flip(frame, 1)      # mirror: feels like a mirror & makes handedness correct
            t = time.time()
            fps = 0.9 * fps + 0.1 / max(t - prev_t, 1e-3) if fps else 1.0 / max(t - prev_t, 1e-3)
            prev_t = t

            motion.update(frame)

            small = frame if w <= 640 else cv2.resize(frame, (640, int(640 * h / w)))
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            ts = max(int(time.monotonic() * 1000), last_ts + 1)
            last_ts = ts
            result = recognizer.recognize_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)

            app.update(parse_hands(result, w, h), t)
            cv2.imshow(WIN, app.render(frame, motion, fps))

            if app.quit_requested:
                break
            if app.switch_cam_requested:
                app.switch_cam_requested = False
                cap, cam_idx = switch_camera(cap, cam_idx, args.width, args.height)
                app.camera_index = cam_idx
                save_camera(cam_idx)
                motion.prev = None
                app.toast(f"Camera {cam_idx}  (press N for the next one)", 2.5)

            key = cv2.waitKey(1) & 0xFF
            frames += 1
            if key in (27, ord("q")):
                break
            if frames > 10 and cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == 255:
                continue
            ch = chr(key).lower()
            if ch in "12345":
                app.tool = TOOLS[int(ch) - 1]
            elif ch == "[":
                app.set_size(app.size - 2)
            elif ch == "]":
                app.set_size(app.size + 2)
            elif ch == "c":
                app.color_idx = (app.color_idx + 1) % len(COLORS)
                if app.tool == "eraser":
                    app.tool = "pen"
            elif ch == "u":
                app.undo()
            elif ch in ("x", "\x08"):
                app.clear()
            elif ch == "s":
                app.save()
            elif ch == "n":
                app.switch_cam_requested = True
            elif ch == "w":
                app.draw_label = "Left" if app.draw_label == "Right" else "Right"
                app.toast(f"Draw hand: {app.draw_label}")
            elif ch == "k":
                app.show_skeleton = not app.show_skeleton
            elif ch == "m":
                app.show_motion = not app.show_motion
            elif ch == "b":
                app.whiteboard = not app.whiteboard
            elif ch == "h":
                app.show_help = not app.show_help
            elif ch == "f":
                fullscreen = not fullscreen
                cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        try:
            recognizer.close()
        except Exception:
            pass
        cv2.destroyAllWindows()
        for _ in range(5):          # macOS only actually closes the window after a few event-loop ticks
            cv2.waitKey(1)


if __name__ == "__main__":
    main()
    # Hard-exit so a lingering camera/MediaPipe thread can never keep the process alive.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
