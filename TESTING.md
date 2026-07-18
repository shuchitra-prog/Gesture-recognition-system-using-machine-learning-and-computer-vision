# Gesture Verification Checklist

Run the app, start the camera, and verify each item in this order. Keep your control hand clearly in the frame and wait briefly for the HUD to show the gesture before expecting a one-shot action.

The launcher automatically runs the logic tests, including a clean-process check that blocks all Matplotlib imports before loading MediaPipe's hand tracker. To run them again manually:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

| Check | Gesture | Expected result |
| --- | --- | --- |
| Cursor | Index finger | Smooth movement to all four screen corners |
| Left click | Thumb + index pinch | One left click; release before repeating |
| Volume | Thumbs-up, move hand up/down | Volume rises/falls while the thumb pose is held |
| Right click | Thumb + middle pinch | One right click |
| Double click | Thumb + pinky pinch | One double click |
| Drag | Hold a fist for 0.75 seconds | Mouse button stays down; opening the hand releases it |
| Scroll | Index + middle fingers, move hand up/down about 2 cm; thumb may be open or closed | Scrolls in the same direction as the hand movement |
| Screenshot | Hold open palm for 0.75 seconds | One PNG appears in `screenshots` |
| Brightness | Index, middle, ring and pinky up, move hand up/down | Brightness rises/falls while pose is held |
| Presentation | Presentation profile + index-finger swipe left/right | Previous/next slide |
| Drawing | Drawing profile + index finger | Draw; hold a fist for 0.75 seconds to enable eraser; hold palm saves |

If tracking is noisy, use a brighter room, keep the webcam at eye level, and increase **Detection Confidence** in Settings before raising the pinch threshold.
