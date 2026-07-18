# config.py
# Central configuration file for Gesture Controlled Computer
# All tuneable parameters live here — change once, reflected everywhere.

import os

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")
DRAWINGS_DIR    = os.path.join(BASE_DIR, "drawings")
ASSETS_DIR      = os.path.join(BASE_DIR, "assets")
MODELS_DIR      = os.path.join(BASE_DIR, "models")
DB_PATH         = os.path.join(BASE_DIR, "database", "gesture_db.sqlite")
LOG_PATH        = os.path.join(BASE_DIR, "gesture_app.log")

# Ensure runtime directories exist
for _d in (SCREENSHOTS_DIR, DRAWINGS_DIR, ASSETS_DIR, MODELS_DIR,
           os.path.dirname(DB_PATH)):
    os.makedirs(_d, exist_ok=True)

# ─────────────────────────────────────────────
#  CAMERA
# ─────────────────────────────────────────────
CAMERA_INDEX     = 0          # Webcam index (0 = default)
CAMERA_WIDTH     = 960        # Capture width  (px); lower latency than 720p
CAMERA_HEIGHT    = 540        # Capture height (px)
CAMERA_FPS_LIMIT = 30         # Max frames per second

# ─────────────────────────────────────────────
#  MEDIAPIPE HAND TRACKING
# ─────────────────────────────────────────────
MP_MAX_HANDS            = 1     # One hand is intentionally used for control
MP_MIN_DETECTION_CONF   = 0.55  # Lower threshold for reliable detection in varied lighting
MP_MIN_TRACKING_CONF    = 0.45  # Lower threshold so tracking doesn't drop out frequently
MP_MODEL_COMPLEXITY     = 1     # More accurate model; worth the small CPU cost
ENABLE_ML_PRIMARY       = True  # Use a trained classifier for action decisions
ENABLE_ML_OVERLAY       = False # Draw the optional ML label on the camera image
CONTROL_HAND_MIN_CONF   = 0.55  # Accept hands above 55% confidence
LANDMARK_SMOOTHING_ALPHA = 0.45 # Heavier EMA on raw landmarks to reduce noise before cursor filter

# ─────────────────────────────────────────────
#  VIRTUAL MOUSE
# ─────────────────────────────────────────────
MOUSE_SENSITIVITY      = 2.5   # Cursor speed multiplier
MOUSE_SMOOTHING        = 4     # Rolling-average window size (frames)
# A slightly smaller active region lets a hand reach every screen edge without
# having to put the fingertip outside the camera image (especially bottom-left).
MOUSE_CONTROL_REGION   = 0.78
MOUSE_EDGE_SNAP        = 0.035 # Snap the outer 3.5% of the active region to an edge
CLICK_COOLDOWN_MS      = 350   # Minimum ms between successive clicks
PINCH_THRESHOLD        = 50    # Pixel distance for pinch detection
PINCH_RELEASE_MULTIPLIER = 1.35 # Hysteresis prevents pinch flicker at threshold
HOLD_DURATION          = 0.75  # Seconds required for drag / screenshot confirmation
HOLD_GAP_TOLERANCE     = 2     # Frames of dropout allowed without resetting hold timer
SCREENSHOT_COOLDOWN_MS = 1500  # Prevent accidental duplicate captures
GESTURE_STABLE_FRAMES  = 2     # Fast two-frame confirmation prevents flicker without lag
GESTURE_TRANSITION_FRAMES = 2  # New static pose must be seen this many frames
GESTURE_RELEASE_FRAMES = 3     # Frames without a one-shot pose before re-arming it
GESTURE_VOTE_WINDOW    = 3     # Rolling history size for majority voting  # MODIFIED — was 5, now 3 frames ≈ 100ms at 30fps for fast gesture transitions
GESTURE_VOTE_THRESHOLD = 2     # Minimum votes in the window to confirm a gesture
SCROLL_TRIGGER_DISTANCE = 8    # Vertical pixels accumulated before one scroll tick  # MODIFIED — was 14, lowered for faster scroll start
SCROLL_JITTER_THRESHOLD = 0.5  # Ignore tiny hand jitter before scrolling
SCROLL_SENSITIVITY = 4.0       # >1.0 makes scrolling more responsive  # MODIFIED — was 3.5
SCROLL_STEP            = 5     # OS scroll clicks per recognised movement tick
VOLUME_PIXELS_PER_STEP = 4     # Up/down thumb movement for 1 percent volume change
VOLUME_SENSITIVITY = 2.0       # >1.0 makes volume changes more responsive
VOLUME_DEADZONE = 0.8          # Ignore tiny thumb jitter before changing volume
VOLUME_SMOOTHING_ALPHA = 0.5   # Temporal smoothing for thumb motion
BRIGHTNESS_PIXELS_PER_STEP = 5
BRIGHTNESS_DEADZONE        = 0.5   # Ignore tiny jitter before changing brightness
BRIGHTNESS_SMOOTHING_ALPHA = 0.5   # Temporal smoothing for brightness motion
DRAG_RELEASE_GRACE_FRAMES  = 3    # Frames of non-drag before releasing drag

# ─────────────────────────────────────────────
#  ONE EURO FILTER (cursor smoothing)
# ─────────────────────────────────────────────
CURSOR_MIN_CUTOFF  = 1.0   # Hz: lower = smoother when stationary  # MODIFIED — was 0.8
CURSOR_BETA        = 0.07  # Speed coefficient: higher = more responsive to fast moves  # MODIFIED — was 0.04
CURSOR_D_CUTOFF    = 1.0   # Derivative filter cutoff Hz
CURSOR_DEAD_ZONE   = 1.5   # Screen-px: ignore moves smaller than this  # MODIFIED — was 2.0
CURSOR_MAX_JUMP    = 200   # Screen-px: clamp single-frame jumps  # MODIFIED — was 150

# ─────────────────────────────────────────────
#  VOLUME CONTROL
# ─────────────────────────────────────────────
VOLUME_MIN_DIST = 20    # Finger distance → 0 % volume
VOLUME_MAX_DIST = 200   # Finger distance → 100 % volume

# ─────────────────────────────────────────────
#  BRIGHTNESS CONTROL
# ─────────────────────────────────────────────
BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 100
BRIGHTNESS_STEP = 5     # % changed per gesture tick

# ─────────────────────────────────────────────
#  DRAWING BOARD
# ─────────────────────────────────────────────
DEFAULT_BRUSH_COLOR = (0, 0, 255)   # BGR red
DEFAULT_BRUSH_SIZE  = 5             # px
ERASER_SIZE         = 30            # px

# ─────────────────────────────────────────────
#  GESTURE CLASSIFICATION (ML)
# ─────────────────────────────────────────────
ML_MODEL_PATH      = os.path.join(MODELS_DIR, "gesture_classifier.pkl")
ML_LABEL_PATH      = os.path.join(MODELS_DIR, "gesture_labels.pkl")
ML_CONFIDENCE_MIN  = 0.80           # Reject uncertain classifier output
ML_VOTING_WINDOW   = 5              # Majority-vote history
ML_MIN_VOTES       = 3              # Required matching predictions in the history

# ─────────────────────────────────────────────
#  GUI APPEARANCE
# ─────────────────────────────────────────────
GUI_THEME          = "dark"         # "dark" | "light"
GUI_ACCENT         = "#00FF88"      # Neon green accent
GUI_BG             = "#0D0D0D"
GUI_SURFACE        = "#1A1A2E"
GUI_TEXT           = "#E8E8E8"
GUI_WIDTH          = 1100
GUI_HEIGHT         = 700

# ─────────────────────────────────────────────
#  PROFILES
# ─────────────────────────────────────────────
PROFILES = ["Normal", "Presentation", "Gaming", "Drawing"]
DEFAULT_PROFILE = "Normal"

# ─────────────────────────────────────────────
#  APPLICATION LAUNCHER DEFAULTS
# ─────────────────────────────────────────────
DEFAULT_APPS = {
    "Chrome":     "google-chrome",       # Linux; overridden on Windows below
    "VS Code":    "code",
    "Notepad":    "notepad",
    "Calculator": "gnome-calculator",
}

import platform
if platform.system() == "Windows":
    DEFAULT_APPS = {
        "Chrome":     r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "VS Code":    r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        "Notepad":    "notepad.exe",
        "Calculator": "calc.exe",
    }
elif platform.system() == "Darwin":
    DEFAULT_APPS = {
        "Chrome":     "open -a 'Google Chrome'",
        "VS Code":    "open -a 'Visual Studio Code'",
        "Notepad":    "open -a TextEdit",
        "Calculator": "open -a Calculator",
    }
