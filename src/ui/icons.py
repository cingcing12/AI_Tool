"""
Vector Icon Library for Tkinter Canvas
Renders crisp, resolution-independent vector icons without external dependencies or emojis.
"""

from __future__ import annotations
import math
import tkinter as tk
from typing import Optional


def draw_icon(
    canvas: tk.Canvas,
    name: str,
    cx: float,
    cy: float,
    size: float = 16.0,
    color: str = "#ffffff",
    width: int = 2
) -> None:
    """Draw crisp mathematical vector icons directly onto any Tkinter canvas."""
    s = size / 2.0
    w = max(1, width)

    if name in ("video", "film"):
        # Clapperboard / Video Frame
        canvas.create_rectangle(cx - s, cy - s * 0.75, cx + s, cy + s * 0.75, outline=color, width=w)
        # Play triangle inside
        canvas.create_polygon(
            cx - s * 0.25, cy - s * 0.35,
            cx + s * 0.45, cy,
            cx - s * 0.25, cy + s * 0.35,
            fill=color, outline=""
        )

    elif name == "upload":
        # Tray
        canvas.create_line(cx - s * 0.85, cy + s * 0.3, cx - s * 0.85, cy + s * 0.8, cx + s * 0.85, cy + s * 0.8, cx + s * 0.85, cy + s * 0.3, fill=color, width=w)
        # Up Arrow
        canvas.create_line(cx, cy + s * 0.4, cx, cy - s * 0.8, fill=color, width=w)
        canvas.create_line(cx - s * 0.45, cy - s * 0.35, cx, cy - s * 0.8, cx + s * 0.45, cy - s * 0.35, fill=color, width=w)

    elif name == "download":
        # Tray
        canvas.create_line(cx - s * 0.85, cy + s * 0.3, cx - s * 0.85, cy + s * 0.8, cx + s * 0.85, cy + s * 0.8, cx + s * 0.85, cy + s * 0.3, fill=color, width=w)
        # Down Arrow
        canvas.create_line(cx, cy - s * 0.8, cx, cy + s * 0.4, fill=color, width=w)
        canvas.create_line(cx - s * 0.45, cy - s * 0.05, cx, cy + s * 0.4, cx + s * 0.45, cy - s * 0.05, fill=color, width=w)

    elif name == "cloud_download":
        # Cloud arc + down arrow
        canvas.create_arc(cx - s * 0.8, cy - s * 0.6, cx, cy + s * 0.2, start=0, extent=180, outline=color, width=w, style=tk.ARC)
        canvas.create_arc(cx - s * 0.3, cy - s * 0.9, cx + s * 0.8, cy + s * 0.2, start=0, extent=180, outline=color, width=w, style=tk.ARC)
        # Arrow down
        canvas.create_line(cx, cy - s * 0.2, cx, cy + s * 0.7, fill=color, width=w)
        canvas.create_line(cx - s * 0.4, cy + s * 0.3, cx, cy + s * 0.7, cx + s * 0.4, cy + s * 0.3, fill=color, width=w)

    elif name == "folder":
        # Folder tab + body
        pts = [
            cx - s * 0.9, cy - s * 0.55,
            cx - s * 0.2, cy - s * 0.55,
            cx, cy - s * 0.25,
            cx + s * 0.9, cy - s * 0.25,
            cx + s * 0.9, cy + s * 0.65,
            cx - s * 0.9, cy + s * 0.65
        ]
        canvas.create_polygon(pts, fill="", outline=color, width=w)

    elif name == "mic":
        # Microphone capsule
        canvas.create_rectangle(cx - s * 0.3, cy - s * 0.8, cx + s * 0.3, cy + s * 0.1, outline=color, width=w)
        # Cradle
        canvas.create_arc(cx - s * 0.6, cy - s * 0.4, cx + s * 0.6, cy + s * 0.4, start=180, extent=180, outline=color, width=w, style=tk.ARC)
        # Stem & base
        canvas.create_line(cx, cy + s * 0.4, cx, cy + s * 0.85, fill=color, width=w)
        canvas.create_line(cx - s * 0.45, cy + s * 0.85, cx + s * 0.45, cy + s * 0.85, fill=color, width=w)

    elif name in ("user", "man"):
        # Head
        canvas.create_oval(cx - s * 0.35, cy - s * 0.85, cx + s * 0.35, cy - s * 0.15, outline=color, width=w)
        # Shoulders
        canvas.create_arc(cx - s * 0.8, cy - s * 0.1, cx + s * 0.8, cy + s * 1.3, start=30, extent=120, outline=color, width=w, style=tk.ARC)

    elif name == "woman":
        # Female silhouette with hair wings
        canvas.create_oval(cx - s * 0.32, cy - s * 0.85, cx + s * 0.32, cy - s * 0.21, outline=color, width=w)
        # Hair curls
        canvas.create_line(cx - s * 0.5, cy - s * 0.6, cx - s * 0.45, cy + s * 0.05, fill=color, width=w)
        canvas.create_line(cx + s * 0.5, cy - s * 0.6, cx + s * 0.45, cy + s * 0.05, fill=color, width=w)
        # Shoulders
        canvas.create_arc(cx - s * 0.75, cy - s * 0.1, cx + s * 0.75, cy + s * 1.25, start=35, extent=110, outline=color, width=w, style=tk.ARC)

    elif name == "wave":
        # Equalizer audio waveform bars
        positions = [-0.65, -0.22, 0.22, 0.65]
        heights = [0.45, 0.85, 0.65, 0.95]
        for p, h in zip(positions, heights):
            canvas.create_line(cx + p * s, cy - h * s * 0.8, cx + p * s, cy + h * s * 0.8, fill=color, width=w)

    elif name == "subtitles":
        # CC / Subtitle box with dual lines
        canvas.create_rectangle(cx - s * 0.95, cy - s * 0.65, cx + s * 0.95, cy + s * 0.65, outline=color, width=w)
        canvas.create_line(cx - s * 0.6, cy - s * 0.12, cx + s * 0.3, cy - s * 0.12, fill=color, width=w)
        canvas.create_line(cx - s * 0.6, cy + s * 0.25, cx + s * 0.6, cy + s * 0.25, fill=color, width=w)

    elif name == "blur":
        # Lens / Blur focus frame
        canvas.create_rectangle(cx - s * 0.85, cy - s * 0.6, cx + s * 0.85, cy + s * 0.6, outline=color, width=w)
        # Diagonal scan / blur hash lines
        canvas.create_line(cx - s * 0.5, cy + s * 0.3, cx - s * 0.1, cy - s * 0.3, fill=color, width=w)
        canvas.create_line(cx - s * 0.1, cy + s * 0.3, cx + s * 0.3, cy - s * 0.3, fill=color, width=w)
        canvas.create_line(cx + s * 0.3, cy + s * 0.3, cx + s * 0.7, cy - s * 0.3, fill=color, width=w)

    elif name == "save":
        # Floppy disk
        canvas.create_rectangle(cx - s * 0.8, cy - s * 0.8, cx + s * 0.8, cy + s * 0.8, outline=color, width=w)
        canvas.create_rectangle(cx - s * 0.45, cy - s * 0.8, cx + s * 0.45, cy - s * 0.3, fill=color, outline="")
        canvas.create_rectangle(cx - s * 0.5, cy + s * 0.15, cx + s * 0.5, cy + s * 0.8, fill=color, outline="")

    elif name == "play":
        # Crisp play triangle
        pts = [cx - s * 0.45, cy - s * 0.7, cx + s * 0.75, cy, cx - s * 0.45, cy + s * 0.7]
        canvas.create_polygon(pts, fill=color, outline="")

    elif name == "sparkle_play":
        # Play triangle + dynamic speed/sparkle accent
        pts = [cx - s * 0.4, cy - s * 0.7, cx + s * 0.7, cy, cx - s * 0.4, cy + s * 0.7]
        canvas.create_polygon(pts, fill=color, outline="")
        # Radiant star on top right
        sx, sy = cx - s * 0.6, cy - s * 0.5
        canvas.create_line(sx, sy - s * 0.3, sx, sy + s * 0.3, fill=color, width=1)
        canvas.create_line(sx - s * 0.3, sy, sx + s * 0.3, sy, fill=color, width=1)

    elif name == "pause":
        # Dual pause bars
        canvas.create_rectangle(cx - s * 0.6, cy - s * 0.7, cx - s * 0.2, cy + s * 0.7, fill=color, outline="")
        canvas.create_rectangle(cx + s * 0.2, cy - s * 0.7, cx + s * 0.6, cy + s * 0.7, fill=color, outline="")

    elif name == "stop":
        # Solid rounded stop square
        canvas.create_rectangle(cx - s * 0.6, cy - s * 0.6, cx + s * 0.6, cy + s * 0.6, fill=color, outline="")

    elif name == "volume":
        # Speaker body
        canvas.create_polygon(
            cx - s * 0.8, cy - s * 0.3,
            cx - s * 0.4, cy - s * 0.3,
            cx + s * 0.05, cy - s * 0.75,
            cx + s * 0.05, cy + s * 0.75,
            cx - s * 0.4, cy + s * 0.3,
            cx - s * 0.8, cy + s * 0.3,
            fill=color, outline=""
        )
        # Sound waves
        canvas.create_arc(cx - s * 0.2, cy - s * 0.5, cx + s * 0.6, cy + s * 0.5, start=-45, extent=90, outline=color, width=w, style=tk.ARC)
        canvas.create_arc(cx - s * 0.2, cy - s * 0.8, cx + s * 0.9, cy + s * 0.8, start=-45, extent=90, outline=color, width=w, style=tk.ARC)

    elif name == "volume_mute":
        # Speaker body
        canvas.create_polygon(
            cx - s * 0.8, cy - s * 0.3,
            cx - s * 0.4, cy - s * 0.3,
            cx + s * 0.05, cy - s * 0.75,
            cx + s * 0.05, cy + s * 0.75,
            cx - s * 0.4, cy + s * 0.3,
            cx - s * 0.8, cy + s * 0.3,
            fill=color, outline=""
        )
        # Slash
        canvas.create_line(cx + s * 0.3, cy - s * 0.4, cx + s * 0.8, cy + s * 0.4, fill=color, width=w)
        canvas.create_line(cx + s * 0.8, cy - s * 0.4, cx + s * 0.3, cy + s * 0.4, fill=color, width=w)

    elif name == "check":
        # Checkmark
        canvas.create_line(cx - s * 0.7, cy, cx - s * 0.15, cy + s * 0.55, cx + s * 0.75, cy - s * 0.55, fill=color, width=w)

    elif name == "lock":
        # Padlock shackle
        canvas.create_arc(cx - s * 0.4, cy - s * 0.85, cx + s * 0.4, cy - s * 0.05, start=0, extent=180, outline=color, width=w, style=tk.ARC)
        # Padlock body
        canvas.create_rectangle(cx - s * 0.55, cy - s * 0.15, cx + s * 0.55, cy + s * 0.75, fill=color, outline="")

    elif name == "unlock":
        # Open padlock shackle
        canvas.create_arc(cx - s * 0.5, cy - s * 0.95, cx + s * 0.3, cy - s * 0.15, start=0, extent=180, outline=color, width=w, style=tk.ARC)
        # Padlock body
        canvas.create_rectangle(cx - s * 0.55, cy - s * 0.15, cx + s * 0.55, cy + s * 0.75, fill=color, outline="")

    elif name == "sparkles":
        # Quad AI sparkle
        canvas.create_line(cx, cy - s * 0.85, cx, cy + s * 0.85, fill=color, width=w)
        canvas.create_line(cx - s * 0.85, cy, cx + s * 0.85, cy, fill=color, width=w)
        canvas.create_oval(cx - s * 0.2, cy - s * 0.2, cx + s * 0.2, cy + s * 0.2, fill=color, outline="")

    elif name == "chevron_left":
        canvas.create_line(cx + s * 0.4, cy - s * 0.6, cx - s * 0.3, cy, cx + s * 0.4, cy + s * 0.6, fill=color, width=w)

    elif name == "chevron_right":
        canvas.create_line(cx - s * 0.4, cy - s * 0.6, cx + s * 0.3, cy, cx - s * 0.4, cy + s * 0.6, fill=color, width=w)

    elif name == "settings":
        # Sliders
        for off, knob in [(-0.5, -0.2), (0.0, 0.3), (0.5, -0.1)]:
            canvas.create_line(cx - s * 0.8, cy + off * s, cx + s * 0.8, cy + off * s, fill=color, width=w)
            canvas.create_rectangle(cx + knob * s - s * 0.15, cy + off * s - s * 0.3, cx + knob * s + s * 0.15, cy + off * s + s * 0.3, fill=color, outline="")

    elif name == "dot":
        canvas.create_oval(cx - s * 0.4, cy - s * 0.4, cx + s * 0.4, cy + s * 0.4, fill=color, outline="")

    else:
        # Default fallback circle
        canvas.create_oval(cx - s * 0.5, cy - s * 0.5, cx + s * 0.5, cy + s * 0.5, outline=color, width=w)
