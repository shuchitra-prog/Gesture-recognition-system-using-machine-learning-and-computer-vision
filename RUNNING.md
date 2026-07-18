# Running on Windows

1. Install **Python 3.11 (64-bit)** and select **Add Python to PATH** during installation.
2. Extract the project and open its folder in VS Code.
3. Open the integrated PowerShell terminal and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
```

The first run creates `.venv`, installs the required packages, and starts the application. Later runs reuse it.

The application does not import or require Matplotlib. Hand overlays are drawn with OpenCV, so Windows Application Control blocking Matplotlib DLLs does not affect startup.

## Controls

| Gesture | Action |
| --- | --- |
| Index finger | Move cursor |
| Thumb + index | Left click |
| Thumb + middle | Right click |
| Thumb + pinky | Double click |
| Thumbs-up + move hand up/down | Continuous volume control |
| Index + middle + move hand up/down (thumb open or closed) | Scroll up/down |
| Fist held for 0.75 seconds | Drag; open hand to release |
| Open palm held for 0.75 seconds | Screenshot |
| Four fingers (no thumb) + move hand up/down | Brightness control |

Move the mouse to the top-left corner as an emergency stop. This is the built-in PyAutoGUI fail-safe. See `TESTING.md` for the complete gesture test checklist.
