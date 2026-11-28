"""
Custom Rounded UI Widgets: RoundedCard, RoundedButton, RoundedProgressBar, SectionHeader
"""

import math
import threading
import tkinter as tk
import tkinter.font as tkfont
from typing import Optional
from .icons import draw_icon


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
    """A smooth, colorful rounded button with vector icon support, hover effects, and state handling."""

    def __init__(
        self,
        parent,
        text="",
        command=None,
        width=None,
        height=38,
        bg_color="#0284c7",
        hover_color="#0369a1",
        text_color="#ffffff",
        radius=10,
        font=("Segoe UI", 9, "bold"),
        icon: Optional[str] = None,
        icon_size: int = 15,
        icon_color: Optional[str] = None,
        border_color: str = "",
        **kwargs
    ):
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else "#0f172a"
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
        self.icon = icon
        self.icon_size = icon_size
        self.icon_color = icon_color
        self.border_color = border_color
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
        # Use dark slate for disabled states in modern dark UI
        if self.is_disabled:
            fill_color = "#334155"
            content_color = "#64748b"
            out_color = "#1e293b"
        else:
            fill_color = self.current_bg
            content_color = self.text_color
            out_color = self.border_color

        draw_rounded_rect(self, 0, 0, w, h, r, fill=fill_color, outline=out_color, width=1)

        # Draw icon & text with balanced centering
        eff_icon_color = content_color if (self.is_disabled or not self.icon_color) else self.icon_color

        if self.icon and self.text:
            try:
                font_obj = tkfont.Font(font=self.font)
                text_w = font_obj.measure(self.text)
            except Exception:
                text_w = len(self.text) * 7

            gap = 8
            total_w = self.icon_size + gap + text_w
            start_x = max(8, (w - total_w) / 2.0)

            # Icon
            icon_cx = start_x + (self.icon_size / 2.0)
            icon_cy = h / 2.0
            draw_icon(self, self.icon, icon_cx, icon_cy, size=self.icon_size, color=eff_icon_color, width=2)

            # Text
            text_x = start_x + self.icon_size + gap
            self.create_text(
                text_x,
                h / 2.0,
                text=self.text,
                fill=content_color,
                font=self.font,
                anchor="w"
            )
        elif self.icon and not self.text:
            # Centered icon only
            draw_icon(self, self.icon, w / 2.0, h / 2.0, size=self.icon_size, color=eff_icon_color, width=2)
        else:
            # Centered text only
            self.create_text(
                w / 2.0,
                h / 2.0,
                text=self.text,
                fill=content_color,
                font=self.font,
                anchor="center"
            )

    def set_text(self, text: str):
        self.text = text
        self._draw()

    def set_icon(self, icon: Optional[str]):
        self.icon = icon
        self._draw()

    def set_colors(self, bg_color: str, hover_color: str):
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
        self.current_bg = "#334155" if self.is_disabled else self.bg_color
        self._draw()


class SectionHeader(tk.Canvas):
    """Modern categorized section divider with a vector icon, uppercase title, and subtle line."""

    def __init__(
        self,
        parent,
        title: str,
        icon: Optional[str] = None,
        height: int = 24,
        fg_color: str = "#94a3b8",
        line_color: str = "#334155",
        font=("Segoe UI", 8, "bold"),
        **kwargs
    ):
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else "#1e293b"
        super().__init__(
            parent,
            height=height,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
            **kwargs
        )
        self.title = title
        self.icon = icon
        self.fg_color = fg_color
        self.line_color = line_color
        self.font = font
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 5:
            return

        cx = 10
        cy = h / 2.0
        if self.icon:
            draw_icon(self, self.icon, cx, cy, size=12, color=self.fg_color, width=1)
            cx += 12

        self.create_text(
            cx,
            cy,
            text=self.title.upper(),
            fill=self.fg_color,
            font=self.font,
            anchor="w",
            tags="title_text"
        )
        try:
            bbox = self.bbox("title_text")
            line_start_x = bbox[2] + 8 if bbox else cx + 60
        except Exception:
            line_start_x = cx + 60

        if line_start_x < w - 6:
            self.create_line(line_start_x, cy, w - 4, cy, fill=self.line_color, width=1)


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
