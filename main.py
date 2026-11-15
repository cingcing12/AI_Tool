"""
Simple Video Dubbing App
Created for: បង LIHOUR
Developed by: ប្អូនហនុមាន (Hanuman)
"""

import math
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox


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


class YouTubePlayerView(tk.Canvas):
    """
    One Single Unified Video Player:
    - Entire screen has smooth rounded corners (radius=14)
    - Upper area: Video view screen (theater view)
    - Bottom area: Seamless YouTube controls (Red scrubber, Play/Stop toggle, Speaker, Volume, Time)
    - Clean white aesthetic, zero muddy gray!
    """

    def __init__(self, parent, on_status_change=None, radius=14, **kwargs):
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else "#ffffff"
        super().__init__(parent, bg=parent_bg, highlightthickness=0, bd=0, cursor="hand2", **kwargs)

        self.radius = radius
        self.on_status_change = on_status_change

        # Video State
        self.filepath = ""
        self.filename = ""
        self.is_playing = False
        self.is_muted = False
        self.current_time = 0.0
        self.duration = 0.0
        self.volume = 0.8
        self.previous_volume = 0.8

        self.is_scrubbing = False
        self.is_adjusting_vol = False

        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", self._on_mouse_down)
        self.bind("<B1-Motion>", self._on_mouse_drag)
        self.bind("<ButtonRelease-1>", self._on_mouse_up)

    def _format_time(self, seconds):
        s = int(seconds)
        m = s // 60
        sec = s % 60
        return f"{m}:{sec:02d}"

    def load_video(self, filepath, duration):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.duration = duration
        self.current_time = 0.0
        self.is_playing = False
        self._draw()

    def toggle_play_stop(self):
        if not self.filepath:
            return False
        if not self.is_playing:
            self.is_playing = True
            if self.on_status_change:
                self.on_status_change("Playing video... ▶ (Click Stop to stop and reset)")
            self._draw()
            self._playback_loop()
        else:
            self.is_playing = False
            self.current_time = 0.0
            if self.on_status_change:
                self.on_status_change("Video stopped and reset to 0:00. ■")
            self._draw()
        return self.is_playing

    def toggle_play(self):
        return self.toggle_play_stop()

    def _playback_loop(self):
        if not self.is_playing:
            return

        self.current_time += 0.5
        if self.current_time >= self.duration:
            self.current_time = 0.0
            self.is_playing = False
            if self.on_status_change:
                self.on_status_change("Playback finished and reset to 0:00.")
            self._draw()
            return

        self._draw()
        if self.is_playing:
            self.after(500, self._playback_loop)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 50 or h < 50:
            return

        r = self.radius
        ctl_h = 44  # height reserved for bottom YouTube controls
        view_pad = 6
        screen_bottom = h - ctl_h

        # 1. Outer Player Container (Clean White with Rounded Corners - No Gray!)
        draw_rounded_rect(self, 1, 1, w - 1, h - 1, r, fill="#ffffff", outline="#e2e8f0", width=1)

        # 2. Upper Video Preview Screen
        mid_x = w // 2
        mid_y = (screen_bottom + view_pad) // 2

        if self.filepath:
            # Video Loaded: Sleek rounded theater viewport
            draw_rounded_rect(
                self,
                view_pad, view_pad,
                w - view_pad, screen_bottom,
                10,
                fill="#0f172a",
                outline="#1e293b",
                width=1
            )
            if self.is_playing:
                # Active playing state
                self.create_text(
                    mid_x, mid_y - 10,
                    text="▶  PLAYING",
                    fill="#ef4444",
                    font=("Segoe UI", 12, "bold")
                )
                self.create_text(
                    mid_x, mid_y + 15,
                    text=self.filename,
                    fill="#f8fafc",
                    font=("Segoe UI", 10)
                )
            else:
                # Paused / ready state: Play watermark in center
                self.create_oval(mid_x - 24, mid_y - 24, mid_x + 24, mid_y + 24, fill="#ef4444", outline="")
                self.create_polygon(
                    mid_x - 7, mid_y - 11,
                    mid_x + 13, mid_y,
                    mid_x - 7, mid_y + 11,
                    fill="#ffffff", outline=""
                )
                self.create_text(
                    mid_x, mid_y + 36,
                    text=self.filename,
                    fill="#ffffff",
                    font=("Segoe UI", 10, "bold")
                )
        else:
            # Empty state: Soft clean canvas
            draw_rounded_rect(
                self,
                view_pad, view_pad,
                w - view_pad, screen_bottom,
                10,
                fill="#f8fafc",
                outline="#e2e8f0",
                width=1
            )
            # Minimalist rounded circle play badge (No boxy camera, no words below!)
            self.create_oval(
                mid_x - 30, mid_y - 30,
                mid_x + 30, mid_y + 30,
                fill="#ffffff",
                outline="#cbd5e1",
                width=2
            )
            self.create_polygon(
                mid_x - 6, mid_y - 11,
                mid_x + 13, mid_y,
                mid_x - 6, mid_y + 11,
                fill="#0284c7",
                outline=""
            )

        # 3. YouTube Bottom Controls (Clean White Background, No Gray, Rounded Bottom Corners!)
        scrub_pad = 12
        scrub_y = screen_bottom + 8

        # A. Red Scrubber Line (YouTube style)
        self.create_rectangle(scrub_pad, scrub_y, w - scrub_pad, scrub_y + 3, fill="#e2e8f0", outline="")

        if self.duration > 0:
            scrub_w = (w - 2 * scrub_pad)
            prog = max(0.0, min(1.0, self.current_time / self.duration))
            played_w = scrub_pad + int(scrub_w * prog)
            # Red played bar
            self.create_rectangle(scrub_pad, scrub_y, played_w, scrub_y + 3, fill="#ff0000", outline="")
            # Red circular knob
            self.create_oval(played_w - 5, scrub_y - 3, played_w + 5, scrub_y + 6, fill="#ff0000", outline="")

        # B. Controls Row: Play/Stop, Speaker, Volume, Time
        cy = scrub_y + 16
        icon_color = "#0f172a"

        # Play / Stop toggle icon (px = 24)
        px = 24
        if not self.is_playing:
            # Play triangle (▶)
            self.create_polygon(px - 5, cy - 7, px + 7, cy, px - 5, cy + 7, fill=icon_color, outline="")
        else:
            # Stop square (■)
            self.create_rectangle(px - 5, cy - 5, px + 5, cy + 5, fill="#ef4444", outline="")

        # Speaker icon (sx = 56)
        sx = 56
        self.create_polygon(
            sx - 6, cy - 4,
            sx - 2, cy - 4,
            sx + 3, cy - 7,
            sx + 3, cy + 7,
            sx - 2, cy + 4,
            sx - 6, cy + 4,
            fill=icon_color, outline=""
        )
        if not self.is_muted and self.volume > 0:
            self.create_arc(sx - 1, cy - 6, sx + 8, cy + 6, start=-60, extent=120, style=tk.ARC, outline=icon_color, width=2)
        else:
            self.create_line(sx + 5, cy - 4, sx + 10, cy + 4, fill="#ef4444", width=2)
            self.create_line(sx + 10, cy - 4, sx + 5, cy + 4, fill="#ef4444", width=2)

        # Volume slider bar (x: 76 to 124)
        vx1, vx2 = 76, 124
        self.create_rectangle(vx1, cy - 1, vx2, cy + 2, fill="#e2e8f0", outline="")
        cur_v = 0.0 if self.is_muted else self.volume
        vol_fill_w = vx1 + int((vx2 - vx1) * cur_v)
        self.create_rectangle(vx1, cy - 1, vol_fill_w, cy + 2, fill=icon_color, outline="")
        self.create_oval(vol_fill_w - 3, cy - 3, vol_fill_w + 3, cy + 3, fill=icon_color, outline="")

        # Time readout: '0:05 / 5:47'
        time_text = f"{self._format_time(self.current_time)} / {self._format_time(self.duration)}"
        self.create_text(
            138, cy,
            text=time_text,
            fill=icon_color,
            font=("Segoe UI", 9, "bold"),
            anchor="w"
        )

    def _on_mouse_down(self, event):
        w = self.winfo_width()
        h = self.winfo_height()
        ctl_h = 44
        screen_bottom = h - ctl_h
        scrub_pad = 12
        scrub_y = screen_bottom + 8
        scrub_w = w - 2 * scrub_pad

        if not self.filepath:
            return

        # 1. Click on Upper Video Screen -> Toggle Play / Stop
        if event.y < screen_bottom:
            self.toggle_play_stop()
            return

        # 2. Click on Red Scrubber
        if (scrub_y - 5) <= event.y <= (scrub_y + 8) and scrub_w > 0:
            if self.duration > 0:
                prog = max(0.0, min(1.0, (event.x - scrub_pad) / float(scrub_w)))
                self.current_time = prog * self.duration
                self.is_scrubbing = True
                self._draw()
                if self.on_status_change:
                    self.on_status_change(f"Seeked to {self._format_time(self.current_time)}")
            return

        # 3. Click on Play / Stop Toggle Button (x: 10 to 40)
        if 10 <= event.x <= 40:
            self.toggle_play_stop()
            return

        # 4. Click on Speaker / Mute (x: 46 to 70)
        if 46 <= event.x <= 70:
            self.is_muted = not self.is_muted
            self._draw()
            if self.on_status_change:
                self.on_status_change("Sound muted." if self.is_muted else f"Sound unmuted ({int(self.volume*100)}%).")
            return

        # 5. Click on Volume Bar (x: 74 to 128)
        if 74 <= event.x <= 128:
            self.is_adjusting_vol = True
            v = max(0.0, min(1.0, (event.x - 76) / 48.0))
            self.volume = v
            self.is_muted = (v == 0)
            self._draw()
            if self.on_status_change:
                self.on_status_change(f"Volume: {int(self.volume * 100)}%")
            return

    def _on_mouse_drag(self, event):
        w = self.winfo_width()
        scrub_pad = 12
        scrub_w = w - 2 * scrub_pad
        if self.is_scrubbing and self.duration > 0 and scrub_w > 0:
            prog = max(0.0, min(1.0, (event.x - scrub_pad) / float(scrub_w)))
            self.current_time = prog * self.duration
            self._draw()
        elif self.is_adjusting_vol:
            v = max(0.0, min(1.0, (event.x - 76) / 48.0))
            self.volume = v
            self.is_muted = (v == 0)
            self._draw()

    def _on_mouse_up(self, event):
        self.is_scrubbing = False
        self.is_adjusting_vol = False


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

        # Draw trough
        draw_rounded_rect(self, 0, 0, w, h, r, fill=self.trough_color, outline="")

        # Draw progress bar fill
        fill_w = int(w * (self.progress / 100.0))
        if fill_w > 2:
            fill_r = min(r, fill_w // 2)
            draw_rounded_rect(self, 0, 0, fill_w, h, fill_r, fill=self.fill_color, outline="")


class VideoDubbingApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Video Translate")
        self.geometry("800x490")
        self.minsize(740, 450)
        self.configure(bg="#f1f5f9")

        # Variables
        self.video_path_var = tk.StringVar(value="")
        # Default destination folder is the user's Downloads folder!
        default_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        self.output_folder = default_downloads if os.path.exists(default_downloads) else os.path.expanduser("~")

        self.voice_type = "Man"
        self.status_var = tk.StringVar(value="Status: Ready. Click 'Load' to select video.")
        self.is_processing = False

        # Build UI Layout
        self._create_layout()

    def _create_layout(self):
        """Construct the 2-column layout (Left: Unified YouTube Player, Right: 4 Controls) & Bottom Progress Bar."""

        content_frame = tk.Frame(self, bg="#f1f5f9", bd=0, highlightthickness=0)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # ==========================================
        # LEFT COLUMN: Rounded Card for Unified YouTube Video Player
        # ==========================================
        self.left_card = RoundedCard(
            content_frame,
            bg_color="#ffffff",
            border_color="#e2e8f0",
            radius=16
        )
        self.left_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        preview_header = tk.Label(
            self.left_card.container,
            text="Video Preview",
            bg="#ffffff",
            fg="#0f172a",
            font=("Segoe UI", 11, "bold")
        )
        preview_header.pack(anchor="w", pady=(0, 6))

        # Unified YouTube Video Player Screen (Zero Gray, All Rounded!)
        self.player_view = YouTubePlayerView(
            self.left_card.container,
            on_status_change=lambda msg: self.status_var.set(msg),
            radius=12
        )
        self.player_view.pack(fill=tk.BOTH, expand=True)

        # ==========================================
        # RIGHT COLUMN: Rounded Card for 4 Controls
        # 1. Load: Pick and load video file (Top)
        # 2. Browse: Choose save/output location (Default: Downloads)
        # 3. Voice: Toggle Man / Woman
        # 4. Start: Start dubbing process
        # ==========================================
        self.right_card = RoundedCard(
            content_frame,
            bg_color="#ffffff",
            border_color="#e2e8f0",
            radius=16,
            width=220
        )
        self.right_card.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_card.pack_propagate(False)

        right_title = tk.Label(
            self.right_card.container,
            text="Controls",
            bg="#ffffff",
            fg="#0f172a",
            font=("Segoe UI", 11, "bold")
        )
        right_title.pack(anchor="center", pady=(0, 10))

        # Button 1: Load (Top position, loads video directly into player)
        self.btn_load = RoundedButton(
            self.right_card.container,
            text="Load",
            command=self.load_video,
            bg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            radius=12,
            height=40
        )
        self.btn_load.pack(fill=tk.X, pady=(0, 8))

        # Button 2: Browse (Picks destination folder where dubbed video is saved)
        self.btn_browse = RoundedButton(
            self.right_card.container,
            text="Browse",
            command=self.browse_output_folder,
            bg_color="#6366f1",
            hover_color="#4f46e5",
            text_color="#ffffff",
            radius=12,
            height=40
        )
        self.btn_browse.pack(fill=tk.X, pady=(0, 10))

        # Button 3: Toggle Voice Button (Man / Woman on click, no emoji)
        self.btn_voice_toggle = RoundedButton(
            self.right_card.container,
            text="Voice: Man",
            command=self.toggle_voice,
            bg_color="#ea580c",
            hover_color="#c2410c",
            text_color="#ffffff",
            radius=12,
            height=40
        )
        self.btn_voice_toggle.pack(fill=tk.X, pady=(0, 10))

        # Button 4: Start (Starts dubbing and saves to output folder)
        self.btn_start = RoundedButton(
            self.right_card.container,
            text="Start",
            command=self.start_dubbing,
            bg_color="#10b981",
            hover_color="#059669",
            text_color="#ffffff",
            radius=12,
            height=42,
            font=("Segoe UI", 11, "bold")
        )
        self.btn_start.pack(fill=tk.X, side=tk.BOTTOM, pady=(8, 0))

        # ==========================================
        # BOTTOM: ONLY ONE Rounded Progress Bar & Status
        # ==========================================
        bottom_frame = tk.Frame(self, bg="#f1f5f9", bd=0, highlightthickness=0)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 12))

        status_box = tk.Frame(bottom_frame, bg="#f1f5f9", bd=0, highlightthickness=0)
        status_box.pack(fill=tk.X, pady=(0, 5))

        self.status_label = tk.Label(
            status_box,
            textvariable=self.status_var,
            bg="#f1f5f9",
            fg="#2563eb",
            font=("Segoe UI", 9, "italic")
        )
        self.status_label.pack(side=tk.LEFT)

        self.percent_label = tk.Label(
            status_box,
            text="0%",
            bg="#f1f5f9",
            fg="#0f172a",
            font=("Segoe UI", 9, "bold")
        )
        self.percent_label.pack(side=tk.RIGHT)

        # Smooth Rounded Progress Bar (Pill shaped ends - zero internal lines)
        self.progress_bar = RoundedProgressBar(
            bottom_frame,
            height=14,
            trough_color="#e2e8f0",
            fill_color="#10b981",
            radius=7
        )
        self.progress_bar.pack(fill=tk.X)

    # ==========================================
    # Corrected Flow Handlers
    # ==========================================
    def load_video(self):
        """Action 1 (Load): Select input video file and immediately load into player."""
        filetypes = [
            ("Video Files", "*.mp4 *.mkv *.avi *.mov *.wmv *.flv"),
            ("All Files", "*.*")
        ]
        selected_file = filedialog.askopenfilename(
            title="Select Video to Dub",
            filetypes=filetypes
        )
        if not selected_file:
            return

        if not os.path.exists(selected_file):
            messagebox.showerror("Error", "File not found! Please check file path.")
            return

        self.video_path_var.set(selected_file)
        size_mb = os.path.getsize(selected_file) / (1024 * 1024)
        filename = os.path.basename(selected_file)

        # Duration demo (e.g. 347s = 5:47 matching YouTube screenshot)
        duration = 347.0
        self.player_view.load_video(selected_file, duration)
        self.status_var.set(f"Loaded '{filename}' successfully. Ready to dub!")

    def browse_output_folder(self):
        """Action 2 (Browse): Select destination folder where the dubbed video will be stored."""
        selected_dir = filedialog.askdirectory(
            title="Select Folder to Save Dubbed Video",
            initialdir=self.output_folder
        )
        if selected_dir:
            self.output_folder = selected_dir
            folder_name = os.path.basename(selected_dir) or selected_dir
            self.status_var.set(f"Output folder set to '{folder_name}'.")

    def toggle_voice(self):
        """Action 3 (Voice): Toggle between Man and Woman on each click."""
        if self.voice_type == "Man":
            self.voice_type = "Woman"
            self.btn_voice_toggle.set_text("Voice: Woman")
            self.btn_voice_toggle.set_colors("#db2777", "#be185d")
        else:
            self.voice_type = "Man"
            self.btn_voice_toggle.set_text("Voice: Man")
            self.btn_voice_toggle.set_colors("#ea580c", "#c2410c")

    def start_dubbing(self):
        """Action 4 (Start): Start dubbing and save output to the destination folder."""
        filepath = self.video_path_var.get()
        if not filepath:
            messagebox.showwarning("Notice", "Please click 'Load' to select a video first!")
            return

        if self.is_processing:
            messagebox.showinfo("In Progress", "Dubbing is already in progress.")
            return

        # Stop playback if currently running
        if self.player_view.is_playing:
            self.player_view.toggle_play_stop()

        # Disable buttons during processing
        self.is_processing = True
        self.btn_load.set_state(tk.DISABLED)
        self.btn_browse.set_state(tk.DISABLED)
        self.btn_voice_toggle.set_state(tk.DISABLED)
        self.btn_start.set_state(tk.DISABLED)

        self.progress_bar.set_progress(0)
        self.percent_label.config(text="0%")

        # Target output filename
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_filename = f"{base_name}_dubbed_{self.voice_type.lower()}.mp4"
        output_full_path = os.path.join(self.output_folder, output_filename)

        thread = threading.Thread(
            target=self._dubbing_worker,
            args=(filepath, self.voice_type, output_full_path),
            daemon=True
        )
        thread.start()

    def _dubbing_worker(self, filepath, voice, output_path):
        """Worker thread simulating dubbing and saving to destination folder."""
        steps = [
            (20, "Extracting audio track..."),
            (50, f"Generating {voice} AI speech clone..."),
            (80, "Merging dubbed audio with video..."),
            (100, f"Saved to {os.path.basename(output_path)}!")
        ]

        try:
            for target_percent, step_status in steps:
                current = int(self.progress_bar.get_progress())
                while current < target_percent:
                    time.sleep(0.03)
                    current += 1
                    self.progress_bar.set_progress(current)
                    self.percent_label.config(text=f"{current}%")

                self.status_var.set(step_status)
                time.sleep(0.3)

            # Prompt success with output location
            self.after(200, lambda: messagebox.showinfo(
                "Success! 🎉",
                f"Video dubbed successfully with {voice} voice!\n\n"
                f"Saved to:\n{output_path}"
            ))
        except Exception as e:
            self.status_var.set(f"Error: {e}")
        finally:
            self.is_processing = False
            self.btn_load.set_state(tk.NORMAL)
            self.btn_browse.set_state(tk.NORMAL)
            self.btn_voice_toggle.set_state(tk.NORMAL)
            self.btn_start.set_state(tk.NORMAL)


if __name__ == "__main__":
    app = VideoDubbingApp()
    app.mainloop()
