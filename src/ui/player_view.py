"""
Unified YouTube Player View Widget: Real Video Frame preview + YouTube controls.
"""

import os
import threading
import tkinter as tk
from .widgets import draw_rounded_rect
from ..core.video_engine import VideoEngine


class YouTubePlayerView(tk.Canvas):
    """
    One Single Unified Video Player:
    - Entire screen has smooth rounded corners (radius=14)
    - Upper area: Real video frame preview extracted via FFmpeg!
    - Bottom area: Seamless YouTube controls (Red scrubber, Play/Stop toggle, Speaker, Volume, Time)
    - Clean white aesthetic, zero muddy gray!
    """

    def __init__(self, parent, on_status_change=None, radius=14, **kwargs):
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else "#ffffff"
        super().__init__(parent, bg=parent_bg, highlightthickness=0, bd=0, cursor="hand2", **kwargs)

        self.radius = radius
        self.on_status_change = on_status_change

        # Video Engine
        self.engine = VideoEngine()

        # Video State
        self.filepath = ""
        self.filename = ""
        self.is_playing = False
        self.is_muted = False
        self.current_time = 0.0
        self.duration = 0.0
        self.volume = 0.8
        self.previous_volume = 0.8

        # Real video frame image
        self.current_frame_image = None
        self._extract_lock = threading.Lock()

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

    def load_video(self, filepath):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.current_time = 0.0
        self.is_playing = False
        self.current_frame_image = None

        # 1. Probe real duration
        self.duration = self.engine.probe_duration(filepath)

        # 2. Extract first real frame
        threading.Thread(target=self._extract_frame, args=(1.0,), daemon=True).start()
        self._draw()

    def _extract_frame(self, timestamp=1.0):
        """Extract real video frame at timestamp using VideoEngine."""
        if not self.filepath:
            return

        with self._extract_lock:
            w = max(280, self.winfo_width() - 16)
            h = max(160, self.winfo_height() - 56)
            target_w = min(w, int(h * 16.0 / 9.0))
            target_h = int(target_w * 9.0 / 16.0)

            frame_file = self.engine.extract_frame(self.filepath, timestamp, target_w, target_h)
            if frame_file and os.path.exists(frame_file) and os.path.getsize(frame_file) > 0:
                try:
                    self.current_frame_image = tk.PhotoImage(file=frame_file)
                    self.after(0, self._draw)
                except Exception:
                    pass

    def toggle_play_stop(self):
        if not self.filepath:
            return False
        if not self.is_playing:
            self.is_playing = True
            if self.on_status_change:
                self.on_status_change("Playing video... ▶ (Click Stop to stop & reset)")
            self._draw()
            self._playback_loop()
        else:
            self.is_playing = False
            self.current_time = 0.0
            if self.on_status_change:
                self.on_status_change("Video stopped and reset to 0:00. ■")
            threading.Thread(target=self._extract_frame, args=(1.0,), daemon=True).start()
            self._draw()
        return self.is_playing

    def toggle_play(self):
        return self.toggle_play_stop()

    def _playback_loop(self):
        if not self.is_playing:
            return

        self.current_time += 1.0
        if self.current_time >= self.duration:
            self.current_time = 0.0
            self.is_playing = False
            if self.on_status_change:
                self.on_status_change("Playback finished and reset to 0:00.")
            self._draw()
            return

        threading.Thread(target=self._extract_frame, args=(self.current_time,), daemon=True).start()
        self._draw()

        if self.is_playing:
            self.after(1000, self._playback_loop)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 50 or h < 50:
            return

        r = self.radius
        ctl_h = 44
        view_pad = 6
        screen_bottom = h - ctl_h

        # 1. Outer Player Container (Clean White with Rounded Corners)
        draw_rounded_rect(self, 1, 1, w - 1, h - 1, r, fill="#ffffff", outline="#e2e8f0", width=1)

        # 2. Upper Video Preview Screen
        mid_x = w // 2
        mid_y = (screen_bottom + view_pad) // 2

        if self.filepath:
            draw_rounded_rect(
                self,
                view_pad, view_pad,
                w - view_pad, screen_bottom,
                10,
                fill="#0f172a",
                outline="#1e293b",
                width=1
            )
            if self.current_frame_image:
                self.create_image(mid_x, mid_y, image=self.current_frame_image)

            if not self.is_playing:
                self.create_oval(mid_x - 22, mid_y - 22, mid_x + 22, mid_y + 22, fill="#ef4444", outline="")
                self.create_polygon(
                    mid_x - 6, mid_y - 10,
                    mid_x + 12, mid_y,
                    mid_x - 6, mid_y + 10,
                    fill="#ffffff", outline=""
                )
        else:
            draw_rounded_rect(
                self,
                view_pad, view_pad,
                w - view_pad, screen_bottom,
                10,
                fill="#f8fafc",
                outline="#e2e8f0",
                width=1
            )
            self.create_oval(
                mid_x - 28, mid_y - 28,
                mid_x + 28, mid_y + 28,
                fill="#ffffff",
                outline="#cbd5e1",
                width=2
            )
            self.create_polygon(
                mid_x - 6, mid_y - 11,
                mid_x + 12, mid_y,
                mid_x - 6, mid_y + 11,
                fill="#0284c7",
                outline=""
            )

        # 3. YouTube Bottom Controls
        scrub_pad = 12
        scrub_y = screen_bottom + 8

        # Red Scrubber Line
        self.create_rectangle(scrub_pad, scrub_y, w - scrub_pad, scrub_y + 3, fill="#e2e8f0", outline="")

        if self.duration > 0:
            scrub_w = (w - 2 * scrub_pad)
            prog = max(0.0, min(1.0, self.current_time / self.duration))
            played_w = scrub_pad + int(scrub_w * prog)
            self.create_rectangle(scrub_pad, scrub_y, played_w, scrub_y + 3, fill="#ff0000", outline="")
            self.create_oval(played_w - 5, scrub_y - 3, played_w + 5, scrub_y + 6, fill="#ff0000", outline="")

        # Controls Row
        cy = scrub_y + 16
        icon_color = "#0f172a"

        # Play / Stop toggle icon
        px = 24
        if not self.is_playing:
            self.create_polygon(px - 5, cy - 7, px + 7, cy, px - 5, cy + 7, fill=icon_color, outline="")
        else:
            self.create_rectangle(px - 5, cy - 5, px + 5, cy + 5, fill="#ef4444", outline="")

        # Speaker icon
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

        # Volume slider bar
        vx1, vx2 = 76, 124
        self.create_rectangle(vx1, cy - 1, vx2, cy + 2, fill="#e2e8f0", outline="")
        cur_v = 0.0 if self.is_muted else self.volume
        vol_fill_w = vx1 + int((vx2 - vx1) * cur_v)
        self.create_rectangle(vx1, cy - 1, vol_fill_w, cy + 2, fill=icon_color, outline="")
        self.create_oval(vol_fill_w - 3, cy - 3, vol_fill_w + 3, cy + 3, fill=icon_color, outline="")

        # Time readout
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

        if event.y < screen_bottom:
            self.toggle_play_stop()
            return

        if (scrub_y - 5) <= event.y <= (scrub_y + 8) and scrub_w > 0:
            if self.duration > 0:
                prog = max(0.0, min(1.0, (event.x - scrub_pad) / float(scrub_w)))
                self.current_time = prog * self.duration
                self.is_scrubbing = True
                threading.Thread(target=self._extract_frame, args=(self.current_time,), daemon=True).start()
                self._draw()
                if self.on_status_change:
                    self.on_status_change(f"Seeked to {self._format_time(self.current_time)}")
            return

        if 10 <= event.x <= 40:
            self.toggle_play_stop()
            return

        if 46 <= event.x <= 70:
            self.is_muted = not self.is_muted
            self._draw()
            if self.on_status_change:
                self.on_status_change("Sound muted." if self.is_muted else f"Sound unmuted ({int(self.volume*100)}%).")
            return

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
            threading.Thread(target=self._extract_frame, args=(self.current_time,), daemon=True).start()
            self._draw()
        elif self.is_adjusting_vol:
            v = max(0.0, min(1.0, (event.x - 76) / 48.0))
            self.volume = v
            self.is_muted = (v == 0)
            self._draw()

    def _on_mouse_up(self, event):
        self.is_scrubbing = False
        self.is_adjusting_vol = False
