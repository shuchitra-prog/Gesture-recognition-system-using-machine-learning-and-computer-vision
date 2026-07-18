# gui/styles.py
# Dark-mode colour palette and font definitions for all Tkinter pages.
# Import this in every page module.

import tkinter.font as tkfont

# ── Colours ───────────────────────────────────────────────────────────────────
BG           = "#0D0D0D"    # window background
SURFACE      = "#161625"    # card / panel background
SURFACE2     = "#1E1E35"    # slightly lighter card
BORDER       = "#2A2A4A"    # divider / border colour
ACCENT       = "#00FF88"    # neon green primary accent
ACCENT2      = "#00C8FF"    # cyan secondary accent
ACCENT_WARN  = "#FF4060"    # error / warning
TEXT_PRIMARY = "#EAEAEA"    # main text
TEXT_MUTED   = "#6B7280"    # secondary / hints
TEXT_ACCENT  = ACCENT

# ── Typography helpers ────────────────────────────────────────────────────────
FONT_TITLE   = ("Consolas", 22, "bold")
FONT_HEADING = ("Consolas", 14, "bold")
FONT_BODY    = ("Consolas", 11)
FONT_SMALL   = ("Consolas", 9)
FONT_MONO    = ("Courier New", 10)

# ── Widget common kwargs ──────────────────────────────────────────────────────
BTN = dict(
    bg=SURFACE2, fg=TEXT_PRIMARY,
    activebackground=ACCENT, activeforeground=BG,
    relief="flat", cursor="hand2",
    padx=12, pady=6,
    font=FONT_BODY,
)

BTN_ACCENT = dict(
    bg=ACCENT, fg=BG,
    activebackground="#00CC70", activeforeground=BG,
    relief="flat", cursor="hand2",
    padx=12, pady=6,
    font=("Consolas", 11, "bold"),
)

BTN_WARN = dict(
    bg=ACCENT_WARN, fg=TEXT_PRIMARY,
    activebackground="#CC3350", activeforeground=TEXT_PRIMARY,
    relief="flat", cursor="hand2",
    padx=12, pady=6,
    font=FONT_BODY,
)

ENTRY = dict(
    bg=SURFACE2, fg=TEXT_PRIMARY,
    insertbackground=ACCENT,
    relief="flat",
    font=FONT_BODY,
)

LABEL = dict(
    bg=BG, fg=TEXT_PRIMARY,
    font=FONT_BODY,
)

LABEL_MUTED = dict(
    bg=BG, fg=TEXT_MUTED,
    font=FONT_SMALL,
)

FRAME = dict(bg=BG)
SURFACE_FRAME = dict(bg=SURFACE)
