"""
Custom Rounded UI Widgets: RoundedCard, RoundedButton, RoundedProgressBar
"""

import math
import threading
import tkinter as tk


def draw_rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    """
    Draws a single, continuous, seamless rounded rectangle polygon.
    Guarantees ZERO internal intersecting lines or cross-artifacts inside the corners.
    """
    if r <= 0:
        return canvas.create_rectangle(x1, y1, x2, y2, **kwargs)

    max_r = min((x2 - x1) / 2.0, (y2 - y1) / 2.0)
    r = min(float(r), max_r)

    steps = 12
    points = []

    # 1. Top-Right Corner
    cx, cy = x2 - r, y1 + r
    for i in range(steps + 1):
        angle = -math.pi / 2.0 + (math.pi / 2.0) * (i / steps)
        points.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])

    # 2. Bottom-Right Corner
    cx, cy = x2 - r, y2 - r
    for i in range(steps + 1):
        angle = 0.0 + (math.pi / 2.0) * (i / steps)
        points.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])

    # 3. Bottom-Left Corner
    cx, cy = x1 + r, y2 - r
    for i in range(steps + 1):
        angle = math.pi / 2.0 + (math.pi / 2.0) * (i / steps)
        points.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])

    # 4. Top-Left Corner
    cx, cy = x1 + r, y1 + r
    for i in range(steps + 1):
        angle = math.pi + (math.pi / 2.0) * (i / steps)
        points.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])

    return canvas.create_polygon(points, **kwargs)


class RoundedCard(tk.Canvas):
    """A card container with seamless rounded corners and zero internal lines."""

    def __init__(
        self,
        parent,
        bg_color="#ffffff",
        border_color="#e2e8f0",
        radius=16,
        **kwargs
    ):
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else "#f1f5f9"
        super().__init__(
            parent,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
            **kwargs
        )
        self.bg_color = bg_color
        self.border_color = border_color
        self.radius = radius
        self.container = tk.Frame(self, bg=bg_color, bd=0, highlightthickness=0)
        self.window_id = None
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        self.delete("card_bg")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 20 or h < 20:
            return

        r = min(self.radius, w // 2, h // 2)

        draw_rounded_rect(
            self,
            1, 1, w - 1, h - 1,
            r,
            fill=self.bg_color,
            outline=self.border_color,
            width=1,
            tags="card_bg"
        )
        self.tag_lower("card_bg")

        pad = r
        if self.window_id is None:
            self.window_id = self.create_window(
                pad, pad,
                window=self.container,
                anchor="nw",
                width=max(10, w - 2 * pad),
                height=max(10, h - 2 * pad)
            )
        else:
            self.coords(self.window_id, pad, pad)
            self.itemconfigure(
                self.window_id,
                width=max(10, w - 2 * pad),
                height=max(10, h - 2 * pad)
            )


class RoundedButton(tk.Canvas):
    """A smooth, colorful rounded button with hover effects and state handling."""

    def __init__(
        self,
        parent,
        text="",
        command=None,
        width=None,
        height=40,
        bg_color="#0284c7",
        hover_color="#0369a1",
        text_color="#ffffff",
        radius=12,
        font=("Segoe UI", 10, "bold"),
        **kwargs
    ):
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else "#ffffff"
        c_kwargs = {
            "height": height,
            "bg": parent_bg,
            "highlightthickness": 0,
            "bd": 0,
            "cursor": "hand2"
        }
        if width is not None:
            c_kwargs["width"] = width
        c_kwargs.update(kwargs)

        super().__init__(parent, **c_kwargs)
        self.parent_bg = parent_bg
        self.command = command
        self.text = text
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.current_bg = bg_color
        self.text_color = text_color
        self.radius = radius
        self.font = font
        self.is_disabled = False

        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return

        r = min(self.radius, h // 2, w // 2)
        color = "#cbd5e1" if self.is_disabled else self.current_bg

        draw_rounded_rect(self, 0, 0, w, h, r, fill=color, outline="")

        self.create_text(
            w // 2,
            h // 2,
            text=self.text,
            fill=self.text_color,
            font=self.font
        )

    def set_text(self, text):
        self.text = text
        self._draw()

    def set_colors(self, bg_color, hover_color):
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.current_bg = bg_color
        self._draw()

    def _on_enter(self, event):
        if not self.is_disabled:
            self.current_bg = self.hover_color
            self._draw()

    def _on_leave(self, event):
        if not self.is_disabled:
            self.current_bg = self.bg_color
            self._draw()

    def _on_click(self, event):
        if not self.is_disabled and self.command:
            self.command()

    def set_state(self, state):
        self.is_disabled = (state == tk.DISABLED)
        self.config(cursor="arrow" if self.is_disabled else "hand2")
        self.current_bg = "#cbd5e1" if self.is_disabled else self.bg_color
        self._draw()


class RoundedProgressBar(tk.Canvas):
    """A sleek progress bar with pill-shaped rounded ends and zero internal lines."""

    def __init__(
        self,
        parent,
        height=14,
        trough_color="#e2e8f0",
        fill_color="#10b981",
        radius=7,
        **kwargs
    ):
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else "#f1f5f9"
        super().__init__(
            parent,
            height=height,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
            **kwargs
        )
        self.trough_color = trough_color
        self.fill_color = fill_color
        self.radius = radius
        self.progress = 0.0
        self.bind("<Configure>", self._draw)

    def set_progress(self, value):
        self.progress = max(0.0, min(100.0, float(value)))
        self._draw()

    def get_progress(self):
        return self.progress

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 5:
            return

        r = min(self.radius, h // 2)

        # Draw background trough
        draw_rounded_rect(self, 0, 0, w, h, r, fill=self.trough_color, outline="")

        # Draw filled progress bar
        fill_w = int(w * (self.progress / 100.0))
        if fill_w > 2:
            fill_r = min(r, fill_w // 2)
            draw_rounded_rect(self, 0, 0, fill_w, h, fill_r, fill=self.fill_color, outline="")
