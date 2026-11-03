# 🎯 Head Zone Tracker

> Turn your head, switch your focus. A webcam-driven monitor-zone tracker for multi-monitor Windows setups.

Head Zone Tracker watches your webcam feed, figures out which screen you're
looking at — **LEFT** monitor, **LAPTOP**, **RIGHT** monitor, or **TOP**
monitor in a vertical 2-monitor setup — and automatically restores Windows
keyboard focus to whatever window you last used on that screen. No hotkeys,
no mouse — just turn your head.

---

## ✨ Features

- 🖥️ **Multi-layout support** — 3-monitor (laptop in the middle) or
  2-monitor (side-by-side or vertical stack)
- 🎛️ **Guided setup wizard** — pick your layout and calibrate thresholds
  through a clean tkinter UI, no config file editing required
- 🧭 **Auto Calibrate** — just turn your head and hold still; thresholds are
  measured and saved automatically
- 🪟 **Automatic window-focus switching** — Windows-only, restores keyboard
  focus to the right window the instant your confirmed zone changes
- 🧘 **Hysteresis + dwell delay** — tuned to avoid flicker from quick
  glances or boundary jitter
- 📺 **Live preview overlay** — raw/smoothed yaw & pitch, candidate zone, and
  confirmed zone, right on the webcam feed

---

## 📦 Requirements

- Windows (for window-focus switching — the tracker itself works
  cross-platform, but `pywin32` is Windows-only)
- Python 3.10+
- A webcam

---

## 🚀 Setup

Run these from this folder, in your own terminal (PowerShell or cmd):

```powershell
cd C:\Users\arpisain\head-tracker-mvp
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Then download the face landmark model file (one-time, a few MB, from
Google's public model storage) into this same folder:

```powershell
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task" -OutFile "face_landmarker.task"
```

You should end up with `face_landmarker.task` sitting next to
`head_tracker_mvp.py`.

---

## ▶️ Run

```powershell
python head_tracker_mvp.py
```

This opens the **setup window** first:

1. **Choose your monitor layout**
   - **3-window setup** — laptop screen in the middle, one external
     monitor on each side.
   - **2-window setup** — laptop + one external monitor, either
     **side-by-side** (beside the laptop, left or right) or
     **vertical stack** (above/below the laptop).
2. **Set your thresholds**, either:
   - **Manual Adjust** — type the angle (in degrees) you want to require
     for each zone directly, then Save.
   - **Auto Calibrate** — opens the webcam. For each zone it asks for
     (e.g. *"Turn LEFT and hold still"*), just turn your head that way and
     hold the position — no key press needed. Once you've held still for
     about a second it captures that angle automatically and moves to the
     next zone. Press `Esc` at any point to cancel without saving.
3. Click **Start Tracking**.

All of this is saved to `tracker_config.json` next to the script, so the
next time you run `head_tracker_mvp.py` the setup window reopens with your
last layout and thresholds already filled in — you only need to touch
"Manual Adjust"/"Auto Calibrate" again if you want to change something.

Once tracking starts, a webcam window shows:

| Readout | Meaning |
|---|---|
| raw yaw/pitch | degrees, straight from the current frame |
| smoothed yaw/pitch | after EMA smoothing |
| candidate zone | what it's leaning toward right now |
| **CONFIRMED ZONE** | what's actually "locked in" after the dwell delay |

Press `q` or `Esc` to quit.

---

## 🧭 How zones work

There's no neutral/CENTER zone. Each zone other than LAPTOP has its own
explicit *entry* threshold (e.g. yaw past -15° → LEFT); LAPTOP also has its
own explicit "tilt down" pitch threshold in the 3-window and side-by-side
layouts (so looking down at the laptop keyboard/screen reliably claims it
back, rather than relying on "whatever isn't LEFT or RIGHT"). If nothing's
threshold is currently crossed, classification falls back to LAPTOP, since
it's the physically central/default screen in every supported layout
(including the bottom screen in the vertical 2-window layout).

Each zone's *exit* threshold (smaller magnitude than its *enter* threshold)
creates a hysteresis gap, so a zone doesn't flicker right at the boundary —
once you're in a zone, you have to drift back further before it lets go.

---

## 🔧 Tuning tips

- **Auto Calibrate** is the easiest way to get reasonable thresholds — it
  measures your actual head angles and sets each enter/exit pair from them
  automatically (margin already applied, so you don't have to turn all the
  way to the edge every time in normal use).
- Prefer to tune by hand? Use **Manual Adjust**: enter thresholds are in
  degrees; exit thresholds are always derived as roughly 2/3 of the enter
  value and saved automatically.
- `yaw_sign` / `pitch_sign` in `tracker_config.json` flip the sign
  convention if, e.g., turning left shows a positive yaw instead of
  negative on your particular setup. (Delete the file or edit it by hand
  if you need to fix this outside the UI.)
- In `head_tracker_mvp.py`: `EMA_ALPHA` (0–1, lower = smoother but slower
  to react) and `DWELL_SECONDS` (how long a new zone must hold before it's
  "confirmed" — raise this if quick glances trigger false zone changes).

---

## 🪟 Window-focus switching

Turning your head toward a zone restores keyboard focus to whichever
window you last used on that monitor (Windows-only; `pywin32` is installed
via `requirements.txt`).

- The monitor layout you picked in setup tells it how your physical
  monitors map to zones. If the detected monitor count doesn't match the
  chosen layout, the script raises an error telling you to fix your setup
  or pick a different layout.
- `ENABLE_WINDOW_SWITCHING = False` in `head_tracker_mvp.py` turns this off
  entirely if you just want the zone visualizer.
- On startup, the script seeds each zone with whatever window is currently
  on top on that monitor (printed to the console as `seeded ZONE: '...'`),
  so focus-restore works immediately without having to click into each
  monitor first. Clicking into a different window on a monitor updates
  that zone's target going forward.
- Switches happen every time the CONFIRMED ZONE changes. Each switch
  prints a line to the console (target zone + window title).

---

## 📁 Project layout

```
head-tracker-mvp/
├── head_tracker_mvp.py     # main tracking loop — run this
├── calibration_ui.py       # the tkinter setup window
├── calibration_wizard.py   # auto-detect-settle calibration capture loop
├── head_pose.py            # shared webcam + FaceLandmarker pipeline
├── zone_classifier.py      # rule-based LEFT/RIGHT/LAPTOP/TOP classifier
├── config_store.py         # loads/saves tracker_config.json
├── window_focus.py         # Windows monitor/window mapping + focus switching
└── requirements.txt
```

---

## 🛠️ Built with

[OpenCV](https://opencv.org/) · [MediaPipe](https://developers.google.com/mediapipe) · [NumPy](https://numpy.org/) · [pywin32](https://github.com/mhammond/pywin32) · [Tkinter](https://docs.python.org/3/library/tkinter.html)
