# Virtual Paint

Draw in the air with your webcam. Point with one hand to draw on the screen, and use gestures with your other hand to switch brushes and the eraser. There's also an on-screen toolbar for brushes, colours and thickness, plus motion sensing.

Runs on **Windows** and **macOS** (Linux works too). Built with Python, OpenCV and Google's MediaPipe. Everything runs locally on your computer; no video is uploaded anywhere.

---

## Contents

1. [What it does](#1-what-it-does)
2. [Project layout](#2-project-layout)
3. [What you need](#3-what-you-need)
4. [Setup: Windows](#4-setup-windows-step-by-step)
5. [Setup: macOS](#5-setup-macos-step-by-step)
6. [Running it](#6-running-it)
7. [How to use it](#7-how-to-use-it)
8. [Command-line options](#8-command-line-options)
9. [Tuning](#9-tuning)
10. [Troubleshooting](#10-troubleshooting)
11. [How it works](#11-how-it-works)

---

## 1. What it does

- **Two-hand control.** One hand draws, the other picks the tool.
  - **Drawing hand** (right by default): point with your index finger and it draws at your fingertip.
  - **Control hand** (left by default): the number of fingers you hold up chooses the brush, and a thumbs up is the eraser.
- **5 tools:** Pen, Marker (thick and translucent), Spray paint, Neon glow, Eraser.
- **10 colours** and adjustable brush thickness.
- **On-screen toolbar** at the top (compact): click with the mouse, or hover your drawing fingertip over a button for about a second.
- **Camera switching:** if it picks the wrong camera (for example your iPhone), press `N` or use the CAM button to cycle cameras. Your choice is remembered.
- **Motion sensing:**
  - A live motion meter (frame differencing) in the corner, with an optional overlay showing which pixels are moving.
  - Hand-motion tracking that detects a **wave** to clear the canvas.
- **Several ways to quit:** QUIT button, both thumbs down, `Q`/`Esc`, closing the window, or `Ctrl+C`.
- **Undo** (up to 20 steps), **clear**, and **save** (PNG plus a transparent PNG of just your drawing).
- **Extras:** whiteboard mode (draw on white instead of the camera image), skeleton overlay, fullscreen.

---

## 2. Project layout

```
Virtual-Paint/
├── main.py                   # entry point: App state/control logic, camera handling, the run loop
├── gesture_recognizer.py     # MediaPipe setup, hand landmarks, finger/gesture geometry
├── motion.py                 # cursor smoothing, wave detection, frame-differencing motion sensor
├── overlay.py                # toolbar layout, canvas paint primitives, all on-screen drawing/HUD
├── requirements.txt          # Python packages to install
├── README.md                 # this file
├── gesture_recognizer.task   # MediaPipe model (auto-downloaded on first run)
├── drawings/                 # created when you save a drawing
└── .venv/                    # your virtual environment (created during setup)
```

Run `main.py` - the other three modules are imported by it and aren't run directly.

| File | Responsibility |
|---|---|
| `main.py` | The `App` class (drawing state, tool logic, hand-role assignment, undo/save), camera opening/switching, argument parsing, and the main loop |
| `gesture_recognizer.py` | Downloading and loading the MediaPipe model, building the recognizer, the `Hand` data type, and the pure finger/gesture geometry (pointing, which brush gesture is being shown) |
| `motion.py` | `Smoother` (fingertip smoothing), `WaveDetector` (wave-to-clear), `MotionSensor` (the HUD motion meter) |
| `overlay.py` | Toolbar layout and buttons, the brush/eraser pixel primitives, and every bit of on-screen drawing (cursor, toolbar, HUD, help panel) |

---

## 3. What you need

| Requirement | Details |
|---|---|
| Computer | Windows 10/11, or macOS (Intel or Apple Silicon) |
| Webcam | Built-in or USB, at 720p or better ideally |
| Python | **3.12 recommended** (3.10 to 3.12 work). Avoid 3.14 for now (see note below) |
| Python packages | `mediapipe` (0.10 series) and `numpy`, installed from `requirements.txt`. MediaPipe brings OpenCV with it |
| Internet | Only for setup: installing Python, the packages, and a one-time ~8 MB model download |
| Good lighting | Front-facing light on your hands makes tracking much more reliable |

You do not need a GPU.

> **Python and MediaPipe versions matter.** MediaPipe 1.x currently crashes on Macs (see Troubleshooting), and it is the only version that supports Python 3.14. So use **Python 3.12** and the pinned `mediapipe` 0.10 series in `requirements.txt`. If `pip install` says it can't find a matching `mediapipe`, your Python is probably too new: install Python 3.12 (steps below).

---

## 4. Setup: Windows (step by step)

### Step 1: Install Python

1. Go to <https://www.python.org/downloads/windows/> and download a **Python 3.12** installer (Windows installer, 64-bit).
2. Run it. On the first screen, **tick "Add python.exe to PATH"**, then click **Install Now**.
3. Open **Command Prompt** (press the Windows key, type `cmd`, press Enter) and check it worked:
   ```
   python --version
   ```
   You should see something like `Python 3.12.x`. (If `python` isn't found, try `py --version`, and use `py` instead of `python` in the commands below.)

> **Already have Python installed, but not 3.12?** You don't need to remove it - the Windows installer can add 3.12 side by side with whatever you have. Check what's already there with the Python Launcher, which lists every version it knows about:
> ```
> py --list
> ```
> If `3.12` isn't in that list, install it as above; the launcher will pick it up automatically. Either way, target it explicitly by version so you don't accidentally use a different one:
> ```
> py -3.12 --version
> py -3.12 -m venv .venv
> ```
> Then activate `.venv` as normal (Step 4) - once it's activated, plain `python` inside that environment is always the 3.12 you created it with, regardless of what `python --version` shows outside of it. If you don't have the `py` launcher (rare, only on very old installs), use the full path instead, e.g. `"C:\Users\YourName\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv`.

### Step 2: Put the project folder in place

Put the whole `Virtual-Paint` folder (with `main.py`, `gesture_recognizer.py`, `motion.py`, `overlay.py`, `requirements.txt`, `README.md`) somewhere convenient, e.g. `C:\Users\YourName\Virtual-Paint`.

### Step 3: Open a terminal in that folder

Open the folder in File Explorer, click the address bar, type `cmd`, and press Enter. A Command Prompt opens already in the right folder.

### Step 4: Create a virtual environment (recommended)

A virtual environment keeps this project's packages separate from everything else on your computer.

```
python -m venv .venv
.venv\Scripts\activate
```

Your prompt should now start with `(.venv)`.

> **Using PowerShell?** Activate with `.\.venv\Scripts\Activate.ps1`. If Windows blocks it with a "running scripts is disabled" error, run this once in that window and try again:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

### Step 5: Install the packages

```
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This downloads MediaPipe (which brings OpenCV with it) and NumPy - a few hundred MB in total. It can take a few minutes.

Check it installed correctly:
```
python -c "import cv2, mediapipe, numpy; print('All good')"
```

### Step 6: Allow camera access

Open **Settings > Privacy & security > Camera** and make sure **Camera access** and **Let desktop apps access your camera** are both **On**.

Then continue to [Running it](#6-running-it).

---

## 5. Setup: macOS (step by step)

### Step 1: Install Python

Pick **one** of these:

**Option A: python.org installer (simplest)**
1. Go to <https://www.python.org/downloads/macos/> and download the **Python 3.12** macOS installer.
2. Open the `.pkg` file and click through the installer.
3. Open the folder **Applications > Python 3.12** and double-click **Install Certificates.command** once. This avoids a common SSL error when the model downloads.

**Option B: Homebrew**
1. Install Homebrew from <https://brew.sh> (copy the one-line command from that page into Terminal).
2. Then run:
   ```
   brew install python@3.12
   ```

Check it worked. Open **Terminal** (press Cmd+Space, type `Terminal`, press Enter):
```
python3 --version
```
You should see `Python 3.12.x` (3.10 to 3.12 work; **not** 3.14). If `python3` shows a different version but you installed 3.12, use `python3.12` instead of `python3` in the commands below.

> **Already have Python installed, but not 3.12?** macOS ships its own Python and you may also have others from Homebrew or a previous install - you don't need to remove any of them. Install 3.12 alongside them with either option above, then check specifically for it:
> ```
> python3.12 --version
> ```
> (Homebrew installs it as `python3.12`; the python.org installer adds both `python3.12` and a `python3` symlink under `/Library/Frameworks/Python.framework`, listed first on your `PATH` after install.) If `python3.12` isn't found right after installing, close and reopen Terminal so it picks up the updated `PATH`. Once you have it, target it explicitly so you don't accidentally build the virtual environment with the wrong version:
> ```
> python3.12 -m venv .venv
> ```
> After activating `.venv` (Step 4), plain `python` inside that environment is always the 3.12 you created it with, regardless of what `python3 --version` shows outside of it.

### Step 2: Put the project folder in place

Put the whole `Virtual-Paint` folder somewhere convenient, e.g. your home folder.

### Step 3: Open Terminal in that folder

```
cd ~/Virtual-Paint
```

(Adjust the path if you put the folder somewhere else. Tip: type `cd ` then drag the folder from Finder into the Terminal window.)

### Step 4: Create a virtual environment (recommended)

```
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`.

### Step 5: Install the packages

```
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Check it installed correctly:
```
python -c "import cv2, mediapipe, numpy; print('All good')"
```

### Step 6: Allow camera access

The first time you run the app, macOS asks whether **Terminal** (or VS Code, iTerm, etc.) can use the camera. Click **Allow** (or **OK**).

If you clicked "Don't Allow" by mistake:
1. Open **System Settings > Privacy & Security > Camera**.
2. Turn on the toggle for the app you run Python from (Terminal, iTerm, VS Code...).
3. Quit and reopen that app, then run the script again.

Then continue to [Running it](#6-running-it).

---

## 6. Running it

With your virtual environment active (you see `(.venv)` in the prompt), run:

```
python main.py
```

**First run only:** the app downloads a small MediaPipe gesture model (`gesture_recognizer.task`, about 8 MB) and saves it in the project folder. This needs internet once; after that it works offline.

A window titled **Virtual Paint** opens with a help panel showing the gestures. Hold your hands up in front of the camera, so that both are clearly visible, and start drawing. The help panel disappears when you draw your first stroke (press `H` to bring it back).

**Coming back later:** you only need to re-activate the environment and run the script.

| | Windows | macOS |
|---|---|---|
| Open a terminal in the folder | Address bar > `cmd` | `cd ~/Virtual-Paint` |
| Activate | `.venv\Scripts\activate` | `source .venv/bin/activate` |
| Run | `python main.py` | `python main.py` |

### If the model download fails

If you're offline, behind a firewall, or get a certificate error, download the model manually:

1. Open this link in your browser (it downloads a file):
   <https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task>
2. Save it as `gesture_recognizer.task` **in the `Virtual-Paint` folder**, next to `main.py`.
3. Run the app again.

You can also keep the model somewhere else and point to it with `--model path/to/gesture_recognizer.task`.

---

## 7. How to use it

### Setting up your space
- Sit about an arm's length or more from the camera so both hands fit in the frame.
- Light your hands from the front. A bright window behind you makes tracking worse.
- The view is mirrored, so it behaves like a mirror: move your hand right and the cursor moves right. Handedness is also corrected for this - see [How it works](#11-how-it-works) if you're curious why that matters.

### Drawing hand (default: right)

| What you do | What happens |
|---|---|
| Point with your index finger (other fingers curled) | Draws at your fingertip |
| Any other hand shape (open hand, fist, etc.) | Pen lifts; you just see a hover circle |
| Hold your fingertip over a toolbar button for ~1 second | Presses that button (a ring fills as you hold) |

### Control hand (default: left)

| Gesture | Tool |
|---|---|
| 1 finger (index) | **Pen**: thin, solid line |
| 2 fingers (index + middle) | **Marker**: thick, translucent |
| 3 fingers | **Spray**: speckled spray paint that builds up as you linger |
| 4 fingers, thumb tucked in | **Neon**: glowing line with a bright core |
| Thumbs up | **Eraser** |
| Fist or open palm | Keeps whatever tool is selected |
| Wave open palm side to side | **Clears the canvas** (undoable with `U`) |

Tool changes only register when your control hand is held fairly **still** for a fraction of a second. That's deliberate, so moving your hand around doesn't flip tools by accident. The current tool's name is shown next to your control hand.

If drawing with the wrong hand feels backwards, press `W` any time to swap which hand draws - see [Quitting](#quitting) and [Troubleshooting](#10-troubleshooting) if it's showing the wrong hand label rather than just feeling backwards.

### The toolbar

The top bar has two rows:

- **Row 1:** Pen, Marker, Spray, Neon, Eraser, thickness `-`, a live brush-size preview, thickness `+`, Undo, Clear, Save, **CAM** (next camera), **QUIT**.
- **Row 2:** 10 colour dots (red, orange, yellow, green, cyan, blue, purple, pink, white, black). The whole slot around each dot is clickable/hoverable, so they're easy to hit even though they look small.

Use it with the **mouse** (click), or with your **drawing fingertip** (hover about 0.8 s; QUIT needs about 1.6 s and CAM about 1.2 s, so you can't hit them by accident). The thickness buttons repeat while you keep hovering. No drawing happens while your fingertip is over the toolbar.

Picking a colour while the eraser is active switches back to the pen.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `1` `2` `3` `4` `5` | Pen, Marker, Spray, Neon, Eraser |
| `[` and `]` | Thinner / thicker |
| `c` | Next colour |
| `u` | Undo (up to 20 steps) |
| `x` or Backspace | Clear canvas |
| `s` | Save |
| `n` | Switch to the next camera |
| `w` | Swap which hand draws |
| `k` | Show/hide hand skeleton overlay |
| `m` | Show/hide motion overlay (moving pixels tinted green) |
| `b` | Whiteboard mode (draw on white instead of camera image) |
| `f` | Fullscreen on/off |
| `h` | Show/hide help |
| `q` or `Esc` | Quit (click the video window first so it has keyboard focus) |

### Quitting

Any of these works:

| Method | How |
|---|---|
| **QUIT button** | Click it with the mouse, or hover your drawing fingertip on it for about 1.6 seconds |
| **Both thumbs down** | Hold both thumbs down for 2 seconds (a red progress bar shows). A single thumbs down does nothing |
| **Keyboard** | `Q` or `Esc`. The keyboard only works when the video window has focus, so click on it first |
| **Window close button** | The red close button on the window |
| **Terminal** | `Ctrl+C` in the terminal you launched it from |

Quitting does not auto-save. Press `S` first if you want to keep your drawing.

### Choosing the camera

On a Mac, a nearby iPhone can show up as a webcam ("Continuity Camera") and take camera slot 0. To pick the right one:

- Press `N` (or hover/click **CAM**) to cycle to the next camera. The HUD shows `Camera: N`. Your choice is saved and used next time.
- Or start it with a specific camera: `python main.py --camera 1`
- To see which camera numbers exist: `python main.py --list-cameras`
- To stop the iPhone from being offered at all: on the iPhone go to **Settings > General > AirPlay & Handoff** and turn **Continuity Camera** off (or just lock the phone / move it away from the Mac).

### Saving your drawing

Press `s` (or the SAVE button). Two files are written to a `drawings` folder inside the project:

- `virtualpaint_YYYYMMDD_HHMMSS.png`: your drawing on top of the current camera image (or white, in whiteboard mode)
- `virtualpaint_YYYYMMDD_HHMMSS_transparent.png`: only your drawing, on a transparent background

### Motion sensing

- **Motion meter** (bottom right): compares each camera frame with the previous one and shows how much of the picture is moving. It reads "still" or "ACTIVE".
- **Motion overlay** (`M`): tints the moving parts of the image green so you can see what the sensor sees.
- **Wave detection:** tracks the horizontal movement of your control hand's palm. A few quick left-right swings with an open palm counts as a wave and clears the canvas. There's a 2-second cooldown, and you can undo it. Turn it off with `--no-wave-clear`.

---

## 8. Command-line options

```
python main.py [options]
```

| Option | Default | What it does |
|---|---|---|
| `--draw-hand Left\|Right` | `Right` | Which hand draws (the other becomes the control hand). Left-handed? Use `--draw-hand Left`. |
| `--camera N` | last one used, else `0` | Which camera to use. Try `1`, `2`... if the wrong one opens (e.g. an iPhone). You can also switch inside the app with `N`. |
| `--list-cameras` | off | Prints which camera numbers work, then exits. |
| `--width W` / `--height H` | `1280` / `720` | Requested camera resolution. Lower it (e.g. `--width 640 --height 480`) if it's slow. |
| `--no-wave-clear` | off | Disable the wave-to-clear gesture. |
| `--model PATH` | `gesture_recognizer.task` in the project folder | Path to the MediaPipe model file. |
| `--skip-version-check` | off | Skip the macOS mediapipe-1.x crash check. |

Example:
```
python main.py --draw-hand Left --width 640 --height 480
```

---

## 9. Tuning

If gestures feel off on your camera or in your lighting, here's where the relevant constants live:

| Constant | File | Default | Effect |
|---|---|---|---|
| `DWELL_SECONDS` | `overlay.py` | `0.8` | How long you hover a fingertip over a toolbar button to press it. |
| `DWELL_QUIT`, `DWELL_CAM` | `overlay.py` | `1.6`, `1.2` | Hover time for the QUIT and CAM buttons. |
| `TOOLBAR_ROW_FRACTION` | `overlay.py` | `0.056` | Size of the toolbar and colour palette (fraction of the frame height). Lower = smaller, higher = bigger. |
| `TOOL_COMMIT_FRAMES` | `main.py` | `5` | How many steady frames a control gesture must be held before the tool switches. Higher = fewer accidents, slower switching. |
| `STEADY_SPEED` | `main.py` | `0.012` | How still the control hand must be to switch tools (fraction of frame width per frame). |
| `QUIT_HOLD_SECONDS` | `main.py` | `2.0` | How long to hold both thumbs down to quit. |
| `MIN_SIZE`, `MAX_SIZE` | `main.py` | `2`, `60` | Brush thickness range. |
| `THUMB_OUT_RATIO` | `gesture_recognizer.py` | `0.85` | Decides "thumb tucked in" vs "thumb out". If Neon (4 fingers) is often read as an open palm, raise it slightly. If it's the other way around, lower it. |

Inside `motion.py`, `WaveDetector`'s `min_swing` and `reversals` control how big and how many swings count as a wave. `Smoother`'s `0.35` base value controls how much the cursor is smoothed (lower = smoother but laggier).

---

## 10. Troubleshooting

**It shows my left hand as "Right" (or vice versa)**
- This is fixed: MediaPipe reports handedness as if the picture weren't mirrored, but the app mirrors the camera feed so it behaves like a mirror on screen - which used to flip the label. `gesture_recognizer.py`'s `parse_hands` now corrects for that, so the label should match your actual hand. If you're still seeing it reversed, make sure you're running the current `main.py`/`gesture_recognizer.py`, and check `HUD Draw hand (...)` / `Control hand (...)` on screen against which hand you're actually moving.
- Prefer drawing with your other hand regardless of labels? Press `W` any time to swap roles, or run with `--draw-hand Left`.

**It uses my iPhone's camera instead of my computer's webcam (Mac)**
- Press `N` in the window, or hover/click **CAM** in the toolbar, to cycle to the next camera. It remembers your choice.
- Or run `python main.py --list-cameras` and then `python main.py --camera 1` (use the number of your Mac's camera).
- To stop the iPhone being offered: iPhone **Settings > General > AirPlay & Handoff > Continuity Camera > off**.

**I can't quit the program**
- Click the **QUIT** button (mouse), or hover your drawing fingertip on it for ~1.6 s.
- Hold **both thumbs down** for 2 seconds.
- `Q` / `Esc` only work if the video window has keyboard focus. Click on the video window first.
- Press `Ctrl+C` in the terminal.
- Last resort on a Mac: close the terminal window, or run `pkill -f main.py` from another terminal.

**"Could not open the camera"**
- Close any other app using the camera (Zoom, Teams, FaceTime, browser tabs).
- Check camera permissions (see the setup step for your OS).
- Run `python main.py --list-cameras` and try `--camera 1` (or another number) if you have more than one camera.
- On macOS, after changing permissions, fully quit and reopen Terminal.

**`pip install` can't find `mediapipe` / "No matching distribution"**
- Your Python is probably too new (or 32-bit). Check with `python --version` and install Python 3.12 64-bit.
- Make sure the virtual environment was created with that Python version.

**Crash on startup with `Check failed: service_ Service is unavailable` (macOS)**
- This is a bug in MediaPipe **1.x** on Macs: it aborts while building the hand-tracking graph, and forcing the CPU doesn't avoid it. MediaPipe **0.10.x** works. Check what you have with `pip show mediapipe`; if `Version` starts with `1.`, reinstall using Python 3.12:
  ```
  deactivate
  rm -rf .venv
  brew install python@3.12          # or use the python.org installer; skip if you already have 3.12
  python3.12 -m venv .venv
  source .venv/bin/activate
  python --version                  # should say 3.12.x
  pip install -r requirements.txt
  pip show mediapipe                # Version should start with 0.10
  python main.py
  ```
- `main.py` checks for this on macOS and stops with a message instead of crashing. (`--skip-version-check` bypasses that check.)

**The window doesn't open, or OpenCV errors about "GUI"**
- You probably have `opencv-python-headless` (which has no windows) installed alongside MediaPipe's own OpenCV. Fix:
  ```
  pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python
  pip install --force-reinstall -r requirements.txt
  ```

**Left and right hands feel swapped even though the label looks right**
- Press `W` to swap roles, or run with `--draw-hand Left`.

**It's laggy or the frame rate is low**
- Run with `--width 640 --height 480`.
- Close other heavy apps.
- Make sure the room is well lit (webcams drop their frame rate in low light).

**Drawing is broken into dots or stops mid-stroke**
- Improve lighting and keep your hand fully in frame.
- Keep your other three fingers clearly curled while pointing. A half-open hand isn't read as "pointing".

**The wrong tool gets selected**
- Hold the gesture steady for about a fifth of a second and face your palm toward the camera.
- Keep the control hand well apart from the drawing hand so the two don't overlap.
- Adjust `TOOL_COMMIT_FRAMES` / `THUMB_OUT_RATIO` (see [Tuning](#9-tuning)), or press `1`-`5` on the keyboard.

**Canvas got cleared by accident**
- Press `U` to undo. If it keeps happening, run with `--no-wave-clear`.

**Toolbar buttons don't respond to the mouse when the window is resized**
- Click with the window at its native size, or use fingertip hover / keyboard shortcuts.

---

## 11. How it works

**Pipeline, one frame at a time (in `main.py`, using the other modules):**

1. **Capture** a frame from the webcam (OpenCV). The best available camera backend is chosen per OS: DirectShow on Windows, AVFoundation on macOS.
2. **Mirror** the frame so it acts like a mirror. This is why handedness needs correcting - see the next point.
3. **Detect hands and gestures** with MediaPipe's *Gesture Recognizer* (`gesture_recognizer.py`), which returns, for up to 2 hands: 21 landmarks each, a left/right label, and a built-in gesture name (such as `Thumb_Up`). MediaPipe's label assumes the raw, unmirrored feed, but the app already mirrored the frame for display - so `parse_hands` flips the label to match what the user actually sees and feels.
4. **Assign roles:** the drawing hand and control hand are picked using that corrected label. If MediaPipe ever reports the same label for both hands, screen position is used as a fallback.
5. **Control hand:**
   - The MediaPipe `Thumb_Up` gesture selects the eraser.
   - Otherwise, finger geometry decides: a finger counts as "up" if its tip is farther from the wrist than its middle joint. A tucked thumb is told apart from an open one by the thumb tip's distance from the index knuckle relative to palm width.
   - A tool only switches after the same gesture is held steady for several frames. That filters out flicker and passing hand shapes.
6. **Drawing hand:**
   - "Pointing" = index up, others curled. Pen down needs 2 consecutive frames and pen up needs 3, so tracking flicker doesn't chop strokes apart.
   - The fingertip position is smoothed (`motion.py`'s `Smoother`) with an adaptive filter: steady when you move slowly, responsive when you move fast.
   - If the fingertip is in the toolbar area, it acts as a hover-to-press cursor instead of drawing.
7. **Canvas** (`overlay.py`'s paint primitives): drawings live in a separate colour layer plus a transparency (alpha) layer, not burned into the camera image. That's what makes the marker translucent, the neon glow soft, and the eraser feather properly. Each frame the layers are blended over the camera image.
8. **Undo:** a snapshot of the canvas is stored at the start of every stroke (last 20 kept).
9. **Motion** (`motion.py`): the frame is shrunk to 160 px wide, blurred, and differenced against the previous frame. The fraction of changed pixels is the motion level. Separately, the control palm's horizontal position over the last ~1.4 seconds is analysed for left-right reversals to detect a wave.

**Brushes:**

| Brush | Technique |
|---|---|
| Pen | Solid anti-aliased line |
| Marker | 2.4x thicker line at ~78% opacity |
| Spray | Random Gaussian-scattered speckles that accumulate while you linger |
| Neon | Two soft, wide translucent lines under a thin, brightened core |
| Eraser | Reduces the transparency layer with a soft-edged brush |

To uninstall, just delete the folder. Nothing is installed system-wide when you use a virtual environment (Python itself, if you installed it, can be removed like any other app).

---

**Credits:** built on [OpenCV](https://opencv.org/) and [MediaPipe](https://ai.google.dev/edge/mediapipe) by Google. The gesture model is Google's `gesture_recognizer` model, downloaded from Google's public MediaPipe model storage.
