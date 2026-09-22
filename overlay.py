"""
overlay.py - the toolbar, canvas painting, and everything drawn on screen.

`Overlay` is a mixin meant to be combined with the app's state (see main.py's
`App`). It expects `self` to carry the attributes the App class sets up:
w, h, paint, mask, buttons, toolbar_h, tool, color_idx, size, cursor, drawing,
dwell_key, dwell_progress, hands, draw_label, camera_index, quit_progress,
show_help/show_skeleton/show_motion/whiteboard, toast_text/toast_until.

Splitting it out keeps all the pixel-drawing code (toolbar, HUD, cursor, help
panel, and the brush/eraser primitives) in one place, separate from the
gesture logic and the app's control flow.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from gesture_recognizer import dist

FONT = cv2.FONT_HERSHEY_SIMPLEX

TOOLS = ["pen", "marker", "spray", "neon", "eraser"]
POSE_NAMES = {
    "pen": "1 finger", "marker": "2 fingers", "spray": "3 fingers",
    "neon": "4 fingers", "eraser": "thumbs up", "open": "open palm",
    "fist": "idle", None: "-",
}

# (name, BGR)
COLORS = [
    ("Red", (60, 60, 240)), ("Orange", (40, 150, 255)), ("Yellow", (40, 230, 250)),
    ("Green", (90, 210, 80)), ("Cyan", (240, 220, 60)), ("Blue", (240, 110, 40)),
    ("Purple", (200, 70, 160)), ("Pink", (190, 120, 255)),
    ("White", (255, 255, 255)), ("Black", (20, 20, 20)),
]

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
    (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18),
    (18, 19), (19, 20), (0, 17),
]

TOOLBAR_ROW_FRACTION = 0.056  # toolbar row height as a fraction of frame height (smaller = smaller palette)
DWELL_SECONDS = 0.8           # hover time to press a toolbar button with a fingertip
DWELL_CAM = 1.2               # hover time for the CAM button
DWELL_QUIT = 1.6              # hover time for the QUIT button (longer, so it can't be hit by accident)


@dataclass(eq=False)
class Button:
    kind: str         # tool | color | size | sizeview | undo | clear | save | cam | quit
    value: object
    label: str
    rect: tuple       # x0, y0, x1, y1
    scale: float = 0.5


def dwell_time(b: Button) -> float:
    return {"quit": DWELL_QUIT, "cam": DWELL_CAM}.get(b.kind, DWELL_SECONDS)


def put_text(img, text, org, scale=0.55, color=(255, 255, 255), thick=1):
    org = (int(org[0]), int(org[1]))
    cv2.putText(img, text, org, FONT, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, text, org, FONT, scale, color, thick, cv2.LINE_AA)


def fit_scale(text, width, start=0.6, floor=0.28):
    scale = start
    while scale > floor:
        (tw, _), _ = cv2.getTextSize(text, FONT, scale, 1)
        if tw <= width - 8:
            break
        scale -= 0.04
    return scale


# --------------------------------------------------------------------------- #
# Canvas primitives (paint layer + alpha mask, so strokes can be translucent)
# --------------------------------------------------------------------------- #
def roi_line(shape, p0, p1, thickness):
    h, w = shape[:2]
    thickness = max(1, int(thickness))
    pad = thickness // 2 + 3
    x0, x1 = max(min(p0[0], p1[0]) - pad, 0), min(max(p0[0], p1[0]) + pad + 1, w)
    y0, y1 = max(min(p0[1], p1[1]) - pad, 0), min(max(p0[1], p1[1]) + pad + 1, h)
    if x1 <= x0 or y1 <= y0:
        return None
    tmp = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.line(tmp, (p0[0] - x0, p0[1] - y0), (p1[0] - x0, p1[1] - y0),
             255, thickness, cv2.LINE_AA)
    return x0, y0, x1, y1, tmp


def stamp_line(paint, mask, p0, p1, thickness, value, color):
    r = roi_line(mask.shape, p0, p1, thickness)
    if r is None:
        return
    x0, y0, x1, y1, tmp = r
    a = (tmp.astype(np.uint16) * value // 255).astype(np.uint8)
    m = mask[y0:y1, x0:x1]
    sel = (a >= m) & (a > 0)
    m[sel] = a[sel]
    pv = paint[y0:y1, x0:x1]
    pv[sel] = color


def erase_line(mask, p0, p1, thickness):
    r = roi_line(mask.shape, p0, p1, thickness)
    if r is None:
        return
    x0, y0, x1, y1, tmp = r
    m = mask[y0:y1, x0:x1]
    m[:] = (m.astype(np.uint16) * (255 - tmp) // 255).astype(np.uint8)


def spray(paint, mask, rng, p0, p1, size, col, w, h):
    r = max(6, int(size * 2.5))
    steps = max(1, int(dist(p0, p1) / (r * 0.5)))
    n = int(min(120, max(12, r * 1.2)))
    for i in range(1, steps + 1):
        cx = p0[0] + (p1[0] - p0[0]) * i / steps
        cy = p0[1] + (p1[1] - p0[1]) * i / steps
        offs = rng.normal(0, r / 2.2, (n, 2))
        alphas = rng.integers(140, 256, n)
        for (dx, dy), al in zip(offs, alphas):
            x, y = int(cx + dx), int(cy + dy)
            if 0 <= x < w and 0 <= y < h:
                cv2.circle(paint, (x, y), 1, col, -1)
                cv2.circle(mask, (x, y), 1, int(al), -1)


def paint_segment(app, p0, p1):
    """Apply the current tool along a segment, mutating app.paint / app.mask."""
    s, col = app.size, COLORS[app.color_idx][1]
    if app.tool == "pen":
        stamp_line(app.paint, app.mask, p0, p1, s, 255, col)
    elif app.tool == "marker":
        stamp_line(app.paint, app.mask, p0, p1, s * 2.4, 200, col)
    elif app.tool == "neon":
        core = tuple(int(c + (255 - c) * 0.65) for c in col)
        stamp_line(app.paint, app.mask, p0, p1, s * 4 + 4, 55, col)
        stamp_line(app.paint, app.mask, p0, p1, s * 2 + 2, 130, col)
        stamp_line(app.paint, app.mask, p0, p1, max(2, s), 255, core)
    elif app.tool == "spray":
        spray(app.paint, app.mask, app.rng, p0, p1, s, col, app.w, app.h)
    elif app.tool == "eraser":
        erase_line(app.mask, p0, p1, s * 3)


def composite(paint, mask, base):
    m3 = cv2.merge((mask, mask, mask))
    inv3 = cv2.bitwise_not(m3)
    return cv2.add(cv2.multiply(base, inv3, scale=1 / 255.0),
                   cv2.multiply(paint, m3, scale=1 / 255.0))


# --------------------------------------------------------------------------- #
# Layout + rendering (mixed into App - see main.py)
# --------------------------------------------------------------------------- #
class Overlay:
    """Toolbar layout and all on-screen drawing. Mixed into App (main.py)."""

    def build_layout(self):
        w, h = self.w, self.h
        row1 = max(32, int(h * TOOLBAR_ROW_FRACTION))
        row2 = int(row1 * 0.85)
        self.toolbar_h = row1 + row2
        self.buttons: list[Button] = []

        top = [("tool", "pen", "PEN"), ("tool", "marker", "MARK"),
               ("tool", "spray", "SPRAY"), ("tool", "neon", "NEON"),
               ("tool", "eraser", "ERASE"), ("size", -2, "-"),
               ("sizeview", None, ""), ("size", 2, "+"),
               ("undo", None, "UNDO"), ("clear", None, "CLEAR"), ("save", None, "SAVE"),
               ("cam", None, "CAM"), ("quit", None, "QUIT")]
        sw = w / len(top)
        for i, (kind, val, label) in enumerate(top):
            rect = (int(i * sw), 0, int((i + 1) * sw), row1)
            self.buttons.append(Button(kind, val, label, rect, fit_scale(label, sw, 0.55)))

        cw = w / len(COLORS)
        for i, (name, _) in enumerate(COLORS):
            rect = (int(i * cw), row1, int((i + 1) * cw), row1 + row2)
            self.buttons.append(Button("color", i, name, rect))

    def button_at(self, x, y):
        for b in self.buttons:
            if b.kind == "sizeview":
                continue
            x0, y0, x1, y1 = b.rect
            if x0 <= x < x1 and y0 <= y < y1:
                return b
        return None

    def composite(self, base):
        return composite(self.paint, self.mask, base)

    def render(self, frame, motion, fps):
        base = np.full_like(frame, 255) if self.whiteboard else frame
        self.last_base = base
        out = self.composite(base)

        if self.show_motion and motion.mask is not None and not self.whiteboard:
            mm = cv2.resize(motion.mask, (self.w, self.h), interpolation=cv2.INTER_NEAREST)
            tint = np.zeros_like(out)
            tint[:] = (0, 255, 0)
            out = np.where(mm[..., None] > 0, cv2.addWeighted(out, 0.6, tint, 0.4, 0), out)

        if self.show_skeleton:
            self.draw_skeleton(out)
        self.draw_cursor(out)
        self.draw_toolbar(out)
        self.draw_hud(out, motion, fps)
        if self.show_help:
            self.draw_help(out)
        return out

    def draw_skeleton(self, out):
        for hand, colr in ((self.hands[0], (255, 220, 80)), (self.hands[1], (80, 180, 255))):
            if hand is None:
                continue
            pts = [(int(x), int(y)) for x, y in hand.pts]
            for a, b in HAND_CONNECTIONS:
                cv2.line(out, pts[a], pts[b], colr, 2, cv2.LINE_AA)
            for p in pts:
                cv2.circle(out, p, 3, (255, 255, 255), -1, cv2.LINE_AA)
        ctrl = self.hands[1]
        if ctrl is not None:
            x, y = ctrl.pts[0]
            if self.ctrl_pose == "fist":
                label_text = "IDLE"
            else:
                label_text = self.tool.upper()
            put_text(out, label_text, (x - 25, y + 28), 0.6, (80, 220, 255), 2)

    def draw_cursor(self, out):
        if self.cursor is None:
            return
        col = COLORS[self.color_idx][1]
        r = self.brush_radius()
        if self.tool == "eraser":
            cv2.circle(out, self.cursor, r, (255, 255, 255), 2, cv2.LINE_AA)
        elif self.drawing:
            cv2.circle(out, self.cursor, r, col, -1, cv2.LINE_AA)
            cv2.circle(out, self.cursor, r + 1, (255, 255, 255), 1, cv2.LINE_AA)
        else:
            cv2.circle(out, self.cursor, r, col, 2, cv2.LINE_AA)
            cv2.circle(out, self.cursor, 2, (255, 255, 255), -1, cv2.LINE_AA)
        if self.dwell_progress > 0:
            cv2.ellipse(out, self.cursor, (26, 26), 0, -90,
                        -90 + int(360 * self.dwell_progress), (0, 255, 255), 4, cv2.LINE_AA)

    def draw_toolbar(self, out):
        th = self.toolbar_h
        roi = out[:th]
        cv2.addWeighted(roi, 0.35, np.full_like(roi, 25), 0.65, 0, dst=roi)
        for b in self.buttons:
            x0, y0, x1, y1 = b.rect
            hovered = b is self.dwell_key
            if b.kind == "color":
                col = COLORS[b.value][1]
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                r = max(6, min(x1 - x0, y1 - y0) // 2 - 5)
                cv2.circle(out, (cx, cy), r, col, -1, cv2.LINE_AA)
                if b.value == self.color_idx:
                    cv2.circle(out, (cx, cy), r + 3, (255, 255, 255), 2, cv2.LINE_AA)
                elif hovered:
                    cv2.circle(out, (cx, cy), r + 3, (0, 255, 255), 2, cv2.LINE_AA)
                else:
                    cv2.circle(out, (cx, cy), r, (110, 110, 110), 1, cv2.LINE_AA)
            elif b.kind == "sizeview":
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                r = int(np.clip(self.size / 2, 2, (y1 - y0) // 2 - 4))
                if self.tool == "eraser":
                    cv2.circle(out, (cx, cy), r, (255, 255, 255), 2, cv2.LINE_AA)
                else:
                    cv2.circle(out, (cx, cy), r, COLORS[self.color_idx][1], -1, cv2.LINE_AA)
                    cv2.circle(out, (cx, cy), r, (255, 255, 255), 1, cv2.LINE_AA)
                put_text(out, str(self.size), (x0 + 6, y1 - 6), 0.4)
            else:
                active = b.kind == "tool" and b.value == self.tool
                fill = (200, 140, 40) if active else ((115, 115, 115) if hovered else (70, 70, 70))
                if b.kind == "quit":
                    fill = (90, 90, 230) if hovered else (60, 60, 180)
                cv2.rectangle(out, (x0 + 2, y0 + 3), (x1 - 2, y1 - 3), fill, -1)
                (tw, tth), _ = cv2.getTextSize(b.label, FONT, b.scale, 1)
                cv2.putText(out, b.label, (x0 + (x1 - x0 - tw) // 2, y0 + (y1 - y0 + tth) // 2),
                            FONT, b.scale, (255, 255, 255), 1, cv2.LINE_AA)

    def draw_hud(self, out, motion, fps):
        h, w = out.shape[:2]
        draw, ctrl = self.hands
        other = "Left" if self.draw_label == "Right" else "Right"
        d_state = "not detected" if draw is None else ("DRAWING" if self.drawing else "hover")
        c_state = "not detected" if ctrl is None else POSE_NAMES.get(self.ctrl_pose, "-")
        lines = [
            f"Draw hand ({self.draw_label}): {d_state}",
            f"Control hand ({other}): {c_state}",
            f"Tool: {self.tool.upper()}   Size: {self.size}   Camera: {self.camera_index}   FPS: {fps:.0f}   [H] help",
        ]
        y = h - 12
        for line in reversed(lines):
            put_text(out, line, (12, y), 0.5)
            y -= 22

        # motion meter (bottom-right)
        bw, bh = 150, 10
        x0, y0 = w - bw - 14, h - 20
        cv2.rectangle(out, (x0, y0), (x0 + bw, y0 + bh), (40, 40, 40), -1)
        fill = int(bw * min(1.0, motion.level * 6))
        cv2.rectangle(out, (x0, y0), (x0 + fill, y0 + bh), (80, 220, 80), -1)
        cv2.rectangle(out, (x0, y0), (x0 + bw, y0 + bh), (200, 200, 200), 1)
        state = "ACTIVE" if motion.level > 0.02 else "still"
        put_text(out, f"MOTION {state}", (x0, y0 - 6), 0.45)

        if self.quit_progress > 0:
            msg = "Keep BOTH thumbs down to quit..."
            (tw, _), _ = cv2.getTextSize(msg, FONT, 0.8, 2)
            bx, by, bw2 = (w - 260) // 2, self.toolbar_h + 90, 260
            put_text(out, msg, ((w - tw) // 2, by - 12), 0.8, (80, 80, 255), 2)
            cv2.rectangle(out, (bx, by), (bx + bw2, by + 14), (40, 40, 40), -1)
            cv2.rectangle(out, (bx, by), (bx + int(bw2 * self.quit_progress), by + 14), (80, 80, 255), -1)
            cv2.rectangle(out, (bx, by), (bx + bw2, by + 14), (220, 220, 220), 1)

        if time.time() < self.toast_until:
            (tw, _), _ = cv2.getTextSize(self.toast_text, FONT, 0.7, 2)
            put_text(out, self.toast_text, ((w - tw) // 2, self.toolbar_h + 34), 0.7, (0, 255, 255), 2)

    def draw_help(self, out):
        lines = [
            "VIRTUAL PAINT - gesture cheat sheet",
            "",
            f"DRAW HAND ({self.draw_label}): point with your index finger to draw",
            "CONTROL HAND: 1 finger = Pen | 2 = Marker | 3 = Spray",
            "              4 fingers (thumb in) = Neon | Thumbs up = Eraser",
            "              Open palm = keep tool | Wave palm = clear",
            "              Fist = pause drawing",
            "",
            "Hover your drawing fingertip over the toolbar ~1s to press a button",
            "Keys: 1-5 tools  [ ] size  c colour  u undo  x clear  s save  n next camera",
            "      w swap hands  k skeleton  m motion  b whiteboard  f fullscreen",
            "QUIT: toolbar QUIT button, both thumbs down (2s), q / Esc, or Ctrl+C",
            "Press H to close this help",
        ]
        h, w = out.shape[:2]
        scale, lh = 0.55, 26
        pw, ph = min(w - 40, 760), lh * len(lines) + 30
        x0, y0 = (w - pw) // 2, max(self.toolbar_h + 20, (h - ph) // 2)
        panel = out[y0:y0 + ph, x0:x0 + pw]
        cv2.addWeighted(panel, 0.25, np.zeros_like(panel), 0.75, 0, dst=panel)
        for i, line in enumerate(lines):
            colr = (0, 255, 255) if i == 0 else (255, 255, 255)
            cv2.putText(out, line, (x0 + 18, y0 + 30 + i * lh), FONT, scale, colr, 1, cv2.LINE_AA)
