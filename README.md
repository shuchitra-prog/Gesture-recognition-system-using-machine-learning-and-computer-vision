# ◈ Gesture Controlled Computer

> Real-time hand gesture interface built with Python · OpenCV · MediaPipe

Control your entire computer — mouse, volume, brightness, media, screenshots, drawing and more — using nothing but hand gestures captured by your webcam.

---

## ✨ Features

| Category | Gestures / Actions |
|---|---|
| 🖱️ **Virtual Mouse** | Index finger → cursor, smooth movement with configurable sensitivity |
| 👆 **Mouse Actions** | Thumb+Index = left click · Thumb+Middle = right click · Thumb+Pinky = double click · Fist hold = drag |
| 🔊 **Volume Control** | Thumb–Index pinch distance maps to system volume (0–100%) |
| 🔆 **Brightness** | Same pinch gesture on left hand adjusts screen brightness |
| 🎵 **Media Controls** | Play/Pause, Next/Prev track via hand gestures |
| 📊 **Presentation Mode** | Swipe left/right = prev/next slide · Index point = laser pointer |
| 🎨 **Drawing Board** | Draw with index finger · multiple brush colours · eraser · save |
| 📸 **Screenshot** | Open palm → auto-save + confirmation popup |
| 🚀 **App Launcher** | Custom gestures launch Chrome, VS Code, Notepad, Calculator |
| 🧠 **ML Classification** | Optional scikit-learn model (Random Forest / SVM / KNN) overlay |
| ⚙️ **Gesture Profiles** | Normal · Presentation · Gaming · Drawing |
| 🗄️ **SQLite Storage** | All gestures, settings and stats persisted locally |

---

## 🗂 Project Structure

```
gesture_controlled_computer/
│
├── app.py                  ← Main entry point (App class + Tkinter root)
├── config.py               ← All tuneable parameters
├── requirements.txt
│
├── cv/
│   ├── hand_tracker.py     ← MediaPipe Hands wrapper → Hand objects
│   ├── camera_thread.py    ← Background webcam capture thread
│   └── overlay.py          ← HUD / FPS / bar rendering on OpenCV frames
│
├── gestures/
│   ├── gesture_detector.py ← Rule-based gesture recognition
│   ├── action_executor.py  ← System actions (pyautogui, pycaw, sbc…)
│   └── gesture_controller.py ← Orchestrator: hands → detect → execute
│
├── gui/
│   ├── styles.py           ← Dark-mode colour palette + font constants
│   ├── home_page.py        ← Dashboard: start/stop, profile selector
│   ├── gesture_manager_page.py ← CRUD for gesture→action mappings
│   ├── settings_page.py    ← All settings with SQLite persistence
│   └── stats_page.py       ← Session stats and top-gesture table
│
├── database/
│   └── db_manager.py       ← SQLite wrapper (users, gestures, settings, stats)
│
├── ml/
│   ├── data_collector.py   ← Collect landmark CSV training data
│   ├── trainer.py          ← Train + compare RF / SVM / KNN classifiers
│   └── predictor.py        ← Runtime inference wrapper
│
├── utils/
│   ├── logger.py           ← Structured logging to file + console
│   └── helpers.py          ← FPSCounter, MovingAverage, Cooldown, geometry
│
├── models/                 ← Saved .pkl classifier + label encoder
├── screenshots/            ← Auto-saved screenshots
├── drawings/               ← Auto-saved drawings
└── assets/                 ← UI icons / images
```

---

## 🚀 Installation

### Prerequisites
- Python 3.9 – 3.11 (MediaPipe is not yet compatible with 3.12+)
- Webcam

### 1 · Clone
```bash
git clone https://github.com/your-username/gesture-controlled-computer.git
cd gesture-controlled-computer
```

### 2 · Virtual environment (recommended)
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3 · Install dependencies
```bash
pip install -r requirements.txt
```

> **Windows only:** `pycaw` requires the Windows Audio Session API — already in requirements.txt.
> **Linux:** Volume control falls back to key-press simulation. Brightness uses `screen-brightness-control`.

### 4 · Run
```bash
python app.py
```

---

## 🎯 Usage Guide

### Starting the camera
1. Launch the app with `python app.py`
2. On the **Home** page, click **▶ Start Camera**
3. An OpenCV window opens showing your webcam with the hand skeleton overlaid
4. Press **Q** or **ESC** inside the OpenCV window to close it, or click **■ Stop Camera** in the GUI

### Gesture reference (Normal profile)

| Gesture | Action |
|---|---|
| ☝️ Index finger only | Move mouse cursor |
| 🤏 Thumb + Index pinch | Left click |
| 🤏 Thumb + Middle pinch | Right click |
| 🤏 Thumb + Pinky pinch | Double click |
| ✊ Closed fist (hold) | Drag and drop |
| ✌️ Index + Middle up | Scroll up |
| 🖐️ Open palm | Screenshot |
| 🤏 Partial Thumb+Index gap | Volume control (distance = volume) |

### Updated control mapping

The current stable controls are: index finger for the cursor; thumb + index/middle/pinky for left/right/double click; thumbs-up plus vertical motion for volume; index + middle fingers plus vertical motion for scroll (thumb open or closed); a held fist for drag; a held open palm for a screenshot; and four fingers (without thumb) plus vertical motion for brightness. See `RUNNING.md` and `TESTING.md` for the authoritative mapping and verification steps.

### Profile switching
Select a profile from the radio buttons on the Home page.
Profiles change which actions are bound to which gestures — switching is instant with no restart needed.

### Gesture Manager
Go to **Gesture Manager** to add, edit or delete any gesture→action mapping per profile.

### Custom ML model
```bash
# 1. Collect 200 samples per gesture
python ml/data_collector.py --gesture THUMB_UP --samples 200
python ml/data_collector.py --gesture FIST --samples 200
# ... repeat for all gestures you want

# 2. Train and compare classifiers
python ml/trainer.py
# The best model is saved to models/gesture_classifier.pkl
# It is automatically loaded the next time app.py runs.
```

---

## 🏗 Architecture

```
Webcam
  │
  ▼
CameraThread (daemon thread — latest frame always available)
  │
  ▼
HandTracker (MediaPipe Hands) ──► Hand objects (21 landmarks × 2 hands)
  │                                        │
  │                                        ▼
  │                               GesturePredictor (optional ML)
  │                                        │
  ▼                                        ▼
GestureDetector (rule-based) ──────► gesture_name
  │
  ▼
DBManager.get_action_for_gesture(gesture_name, profile)
  │
  ▼
ActionExecutor ── pyautogui, pycaw, sbc, subprocess
  │
  ▼
OpenCV overlay ── draw_hud, pinch line, FPS counter
```

---

## 📦 Packaging with PyInstaller

```bash
pip install pyinstaller
pyinstaller --onefile --windowed \
    --add-data "assets:assets" \
    --add-data "models:models" \
    app.py
```

The executable will be in `dist/app` (Linux/macOS) or `dist/app.exe` (Windows).

---

## 🛣 Future Improvements

- [ ] Voice + gesture hybrid control (whisper/SpeechRecognition)
- [ ] Face recognition login (DeepFace / face_recognition)
- [ ] Cloud sync of gesture profiles (Firebase / Supabase)
- [ ] Mobile companion app as secondary camera
- [ ] Multi-monitor support with per-monitor zone mapping
- [ ] Gesture recording / replay macros
- [ ] Plugin system for third-party action modules
- [ ] Dark / Light mode toggle in GUI

---

## 📋 SQLite Schema

```sql
CREATE TABLE users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT    NOT NULL UNIQUE,
    created  TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE gestures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    gesture_name TEXT    NOT NULL,
    action_name  TEXT    NOT NULL,
    profile      TEXT    NOT NULL DEFAULT 'Normal',
    params       TEXT    DEFAULT '{}',
    UNIQUE(gesture_name, profile)
);

CREATE TABLE settings (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    key   TEXT    NOT NULL UNIQUE,
    value TEXT    NOT NULL
);

CREATE TABLE stats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    gesture_name TEXT    NOT NULL,
    action_name  TEXT    NOT NULL,
    timestamp    TEXT    DEFAULT (datetime('now'))
);
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-gesture`
3. Commit your changes
4. Open a pull request

---

## 📄 License

MIT © 2024  — free to use, modify and distribute.
