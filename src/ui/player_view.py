"""
Unified YouTube Player View Widget: Real Video Frame preview + YouTube controls.
High-Performance 25 FPS Smooth Streaming with Aspect Ratio Preservation,
YouTube-style Double Click Skip (Left: -10s, Right: +10s), and Seamless Rounded Corners!
"""

from __future__ import annotations

import os
import math
import time
import queue
import threading
import tkinter as tk
from .widgets import draw_rounded_rect
from ..core.video_engine import VideoEngine
from ..core.audio_player import WindowsAudioPlayer


class YouTubePlayerView(tk.Canvas):
    """
    One Single Unified Video Player:
    - Entire screen has smooth rounded corners (radius=14)
    - Proportional Video Viewport: Fits original video aspect ratio without giant side wings
    - YouTube-style Double Click Skip: Left side = -10s, Right side = +10s with visual indicator!
    - Automatic Windows Audio sync on headphone plug & unplug
    - Bottom area: Seamless YouTube controls (Red scrubber, Play/Stop toggle, Speaker, Volume, Time)
    """

    def __init__(self, parent, on_status_change=None, radius=14, **kwargs):
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else "#ffffff"
        super().__init__(parent, bg=parent_bg, highlightthickness=0, bd=0, cursor="hand2", **kwargs)

        self.radius = radius
        self.on_status_change = on_status_change

        # Video & Audio Engines
        self.engine = VideoEngine()
        self.audio_player = WindowsAudioPlayer(ffmpeg_path=self.engine.ffmpeg_path, temp_dir=self.engine.temp_dir)

        # Video State & Metadata
        self.filepath = ""
        self.filename = ""
        self.is_playing = False
        self.is_muted = False
        self.current_time = 0.0
        self.duration = 0.0
        self.video_width = 640
        self.video_height = 360
        self.has_audio = False
        self.volume = 0.8
        self.previous_volume = 0.8

        # Image & Stream Control
        self.current_frame_image = None
        self._stream_proc = None
        self._stream_thread = None
        self._stream_gen = 0
        self._stop_stream_event = threading.Event()

        # Thread-safe Frame Queue
        self.frame_queue = queue.Queue(maxsize=8)
        self._poll_job = None

        # Resize Debounce & Dimensions Cache
        self._resize_timer = None
        self._last_rendered_dims = None

        # Canvas Item IDs for fast updates
        self.img_item_id = None
        self.scrub_fill_id = None
        self.scrub_knob_id = None
        self.time_text_id = None

        # Scrubbing & UI Dragging
        self.is_scrubbing = False
        self.is_adjusting_vol = False
        self._was_playing_before_scrub = False

        # Click regions & timers
        self._screen_bounds = None
        self._scrub_bounds = None
        self._controls_start_x = 12
        self._controls_y = 100
        self._single_click_timer = None

        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_mouse_down)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<B1-Motion>", self._on_mouse_drag)
        self.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Start UI event poll loop
        self._schedule_poll()

    def _schedule_poll(self):
        """Schedule main thread queue processing every 16ms (~60 FPS)."""
        self._poll_job = self.after(16, self._poll_queue)

    def _poll_queue(self):
        """Process frames and status updates sent from background threads."""
        latest_stream_frame = None
        latest_timestamp = None
        single_frame = None
        finished = False

        try:
            while not self.frame_queue.empty():
                msg_type, payload, extra = self.frame_queue.get_nowait()
                if msg_type == "stream_frame":
                    latest_stream_frame = payload
                    latest_timestamp = extra
                elif msg_type == "single_frame":
                    single_frame = payload
                elif msg_type == "finished":
                    finished = True
        except queue.Empty:
            pass

        # Update stream frame
        if latest_stream_frame is not None and self.is_playing:
            self._apply_frame_data(latest_stream_frame)
            if latest_timestamp is not None:
                self.current_time = latest_timestamp
                self._update_progress_only()

        # Update seek / initial frame
        elif single_frame is not None:
            self._apply_frame_data(single_frame)

        if finished:
            self.stop_playback(reset_to_start=True)

        self._schedule_poll()

    def _on_configure(self, event):
        """Handle window resizing with debounce for smooth updates."""
        if self._resize_timer:
            try:
                self.after_cancel(self._resize_timer)
            except Exception:
                pass

        if self.is_playing:
            tw, th = self._get_target_dimensions()
            if self._stream_proc and hasattr(self._stream_proc, "target_dims"):
                if self._stream_proc.target_dims != (tw, th):
                    self._restart_stream_at_current_time()
            self._redraw_full()
        else:
            self._redraw_full()
            self._resize_timer = self.after(40, self._render_current_frame)

    def _restart_stream_at_current_time(self):
        """Seamlessly restart the FFmpeg pipe with new resolution dimensions."""
        self._stop_stream_event.set()
        if self._stream_proc:
            try:
                self._stream_proc.kill()
            except Exception:
                pass
            self._stream_proc = None

        self._stop_stream_event.clear()
        self._stream_gen += 1
        gen = self._stream_gen
        tw, th = self._get_target_dimensions()

        self._stream_thread = threading.Thread(
            target=self._stream_worker,
            args=(self.current_time, tw, th, 25, gen),
            daemon=True
        )
        self._stream_thread.start()

    def load_video(self, filepath):
        """Prepare player for a newly selected video file."""
        if not filepath or not os.path.exists(filepath):
            return

        self.stop_playback(reset_to_start=True)
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.current_time = 0.0
        self.current_frame_image = None

        # 1. Fast probe metadata (Duration, Width, Height, Audio)
        meta = self.engine.probe_video_metadata(filepath)
        self.duration = meta["duration"]
        self.video_width = meta["width"]
        self.video_height = meta["height"]
        self.has_audio = meta["has_audio"]

        # 2. Setup audio player
        self.audio_player.load(filepath, has_audio=self.has_audio)
        self.audio_player.set_volume(0.0 if self.is_muted else self.volume)

        # 3. Extract first frame in memory and render keeping exact aspect ratio
        tw, th = self._get_target_dimensions()
        threading.Thread(target=self._extract_frame_worker, args=(0.1, tw, th), daemon=True).start()
        if self.on_status_change:
            self.on_status_change("Ready")
        self._redraw_full()

    def _get_target_dimensions(self):
        """
        Calculate preview dimensions fitting inside container while strictly
        preserving original video aspect ratio with zero wasted space above or below.
        """
        ctl_h = 44
        pad = 6
        try:
            avail_w = max(64, self.winfo_width() - 2 * pad)
            avail_h = max(36, self.winfo_height() - ctl_h - 2 * pad)
        except Exception:
            avail_w, avail_h = 480, 270

        vw = max(1, self.video_width)
        vh = max(1, self.video_height)
        video_aspect = float(vw) / float(vh)

        tw = avail_w
        th = int(tw / video_aspect)
        if th > avail_h:
            th = avail_h
            tw = int(th * video_aspect)

        tw = tw - (tw % 2)
        th = th - (th % 2)
        return max(64, tw), max(36, th)

    def _extract_frame_worker(self, timestamp, target_w, target_h):
        """Background thread single-frame fast extraction."""
        if not self.filepath:
            return
        ppm_data = self.engine.extract_frame_ppm(self.filepath, timestamp, target_w, target_h)
        if ppm_data:
            self.frame_queue.put(("single_frame", ppm_data, None))

    def _apply_frame_data(self, ppm_data):
        """Update PhotoImage on UI thread with raw PPM data and ensure corner masks stay on top."""
        try:
            if self.current_frame_image is None:
                self.current_frame_image = tk.PhotoImage(data=ppm_data)
                self._last_rendered_dims = (self.current_frame_image.width(), self.current_frame_image.height())
                self._redraw_full()
            else:
                self.current_frame_image.configure(data=ppm_data)
                self._last_rendered_dims = (self.current_frame_image.width(), self.current_frame_image.height())
                if self.img_item_id is not None:
                    self.itemconfigure(self.img_item_id, image=self.current_frame_image)
                    self.tag_raise("corner_mask")
                    self.tag_raise("screen_border")
                    self.tag_raise("play_overlay")
                    self.tag_raise("skip_feedback")
                else:
                    self._redraw_full()
        except Exception:
            pass

    def toggle_play_pause(self):
        """Toggle between Play ▶ and Pause || (preserves current timestamp, does NOT reset to 0:00)."""
        if not self.filepath:
            return False

        if not self.is_playing:
            self.start_playback()
        else:
            self.pause_playback()
        return self.is_playing

    def toggle_play_stop(self):
        return self.toggle_play_pause()

    def toggle_play(self):
        return self.toggle_play_pause()

    def pause_playback(self):
        """Pause playback at current frame without resetting position."""
        self.is_playing = False
        self._stop_stream_event.set()

        if self._stream_proc:
            try:
                self._stream_proc.kill()
            except Exception:
                pass
            self._stream_proc = None

        self.audio_player.stop()

        if self.on_status_change:
            self.on_status_change("Paused")

        self._redraw_full()

    def start_playback(self):
        """Start or resume smooth 25 FPS video stream and synchronized audio."""
        if not self.filepath or self.is_playing:
            return

        self.is_playing = True
        self._stop_stream_event.clear()

        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

        if self.duration > 0 and self.current_time >= self.duration - 0.2:
            self.current_time = 0.0

        if self.on_status_change:
            self.on_status_change("Playing")

        # Play audio with automatic device sync (Headphones / Speakers)
        self.audio_player.set_volume(0.0 if self.is_muted else self.volume)
        self.audio_player.play(start_seconds=self.current_time)

        # Start video stream thread with preserved aspect ratio
        self._stream_gen += 1
        gen = self._stream_gen
        tw, th = self._get_target_dimensions()
        self._stream_thread = threading.Thread(
            target=self._stream_worker,
            args=(self.current_time, tw, th, 25, gen),
            daemon=True
        )
        self._stream_thread.start()
        self._redraw_full()

    def stop_playback(self, reset_to_start=False):
        """Stop streaming, pause audio, and optionally reset to 0:00."""
        self.is_playing = False
        self._stop_stream_event.set()

        if self._stream_proc:
            try:
                self._stream_proc.kill()
            except Exception:
                pass
            self._stream_proc = None

        self.audio_player.stop()

        if reset_to_start:
            self.current_time = 0.0

        if self.on_status_change:
            self.on_status_change("Ready")

        self._redraw_full()

    def seek_relative(self, delta_seconds: float):
        """
        YouTube-Style Fast Seeking: Skip forward (+10s) or backward (-10s).
        Instantly updates audio and video stream with visual feedback!
        """
        if not self.filepath or self.duration <= 0:
            return

        new_time = max(0.0, min(self.duration, self.current_time + delta_seconds))
        self.current_time = new_time

        # Seek audio
        self.audio_player.seek(new_time)

        # Seek video
        if self.is_playing:
            self.audio_player.play(start_seconds=new_time)
            self._restart_stream_at_current_time()
        else:
            tw, th = self._get_target_dimensions()
            threading.Thread(target=self._extract_frame_worker, args=(new_time, tw, th), daemon=True).start()

        self._show_skip_feedback(delta_seconds)
        self._update_progress_only()

    def _show_skip_feedback(self, delta_seconds: float):
        """Draw animated ripple overlay showing ◀◀ 10s or 10s ▶▶."""
        screen_bounds = getattr(self, "_screen_bounds", None)
        if not screen_bounds:
            return

        sx1, sy1, sx2, sy2 = screen_bounds
        mid_y = (sy1 + sy2) // 2
        mid_x = (sx1 + sx2) // 2

        self.delete("skip_feedback")

        if delta_seconds < 0:
            pos_x = sx1 + (mid_x - sx1) // 2
            text = "◀◀ 10s"
            self.create_oval(pos_x - 36, mid_y - 24, pos_x + 36, mid_y + 24, fill="#0f172a", outline="#38bdf8", width=1.5, tags="skip_feedback")
            self.create_text(pos_x, mid_y, text=text, fill="#ffffff", font=("Segoe UI", 10, "bold"), tags="skip_feedback")
            if self.on_status_change:
                self.on_status_change("Skipped -10s")
        else:
            pos_x = mid_x + (sx2 - mid_x) // 2
            text = "10s ▶▶"
            self.create_oval(pos_x - 36, mid_y - 24, pos_x + 36, mid_y + 24, fill="#0f172a", outline="#38bdf8", width=1.5, tags="skip_feedback")
            self.create_text(pos_x, mid_y, text=text, fill="#ffffff", font=("Segoe UI", 10, "bold"), tags="skip_feedback")
            if self.on_status_change:
                self.on_status_change("Skipped +10s")

        # Automatically dismiss ripple after 600ms
        self.after(600, lambda: self.delete("skip_feedback"))

    def _stream_worker(self, start_time, target_w, target_h, fps, gen):
        """Persistent FFmpeg stdout pipe decoding frames continuously into RAM."""
        proc = self.engine.create_video_stream(self.filepath, start_time, target_w, target_h, fps)
        if not proc:
            self.frame_queue.put(("finished", None, None))
            return

        proc.target_dims = (target_w, target_h)
        self._stream_proc = proc

        header_prefix = f"P6\n{target_w} {target_h}\n255\n".encode("ascii")
        frame_bytes_len = target_w * target_h * 3
        frame_interval = 1.0 / float(fps)
        current_ts = float(start_time)

        try:
            while not self._stop_stream_event.is_set():
                if gen != self._stream_gen:
                    break

                t_start = time.perf_counter()
                raw_frame = proc.stdout.read(frame_bytes_len)
                if not raw_frame or len(raw_frame) < frame_bytes_len:
                    break

                ppm_data = header_prefix + raw_frame
                current_ts += frame_interval

                try:
                    if self.frame_queue.full():
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self.frame_queue.put_nowait(("stream_frame", ppm_data, current_ts))
                except Exception:
                    pass

                elapsed = time.perf_counter() - t_start
                sleep_left = frame_interval - elapsed
                if sleep_left > 0.001:
                    time.sleep(sleep_left)

        except Exception:
            pass
        finally:
            try:
                proc.kill()
            except Exception:
                pass

            if gen == self._stream_gen and not self._stop_stream_event.is_set():
                self.frame_queue.put(("finished", None, None))

    def _render_current_frame(self):
        """Re-render current frame when idle."""
        if not self.filepath or self.is_playing:
            return
        tw, th = self._get_target_dimensions()
        threading.Thread(target=self._extract_frame_worker, args=(self.current_time, tw, th), daemon=True).start()

    def _draw_corner_masks(self, x1, y1, x2, y2, r=10, fill_color="#ffffff", border_color="#e2e8f0"):
        """Draw mathematically exact corner cutouts and a rounded outline over the video frame."""
        if r <= 0:
            return

        steps = 10

        # 1. Top-Left Corner Cutout
        cx, cy = x1 + r, y1 + r
        tl = [x1, y1, x1 + r, y1]
        for i in range(steps + 1):
            a = -math.pi / 2.0 - (math.pi / 2.0) * (i / steps)
            tl.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
        tl.extend([x1, y1 + r, x1, y1])
        self.create_polygon(tl, fill=fill_color, outline="", tags="corner_mask")

        # 2. Top-Right Corner Cutout
        cx, cy = x2 - r, y1 + r
        tr = [x2, y1, x2, y1 + r]
        for i in range(steps + 1):
            a = 0.0 - (math.pi / 2.0) * (i / steps)
            tr.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
        tr.extend([x2 - r, y1, x2, y1])
        self.create_polygon(tr, fill=fill_color, outline="", tags="corner_mask")

        # 3. Bottom-Right Corner Cutout
        cx, cy = x2 - r, y2 - r
        br = [x2, y2, x2 - r, y2]
        for i in range(steps + 1):
            a = math.pi / 2.0 - (math.pi / 2.0) * (i / steps)
            br.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
        br.extend([x2, y2 - r, x2, y2])
        self.create_polygon(br, fill=fill_color, outline="", tags="corner_mask")

        # 4. Bottom-Left Corner Cutout
        cx, cy = x1 + r, y2 - r
        bl = [x1, y2, x1, y2 - r]
        for i in range(steps + 1):
            a = math.pi - (math.pi / 2.0) * (i / steps)
            bl.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
        bl.extend([x1 + r, y2, x1, y2])
        self.create_polygon(bl, fill=fill_color, outline="", tags="corner_mask")

        # Crisp rounded border outline on top
        draw_rounded_rect(self, x1, y1, x2, y2, r, fill="", outline=border_color, width=1.5, tags="screen_border")

    def _redraw_full(self):
        """Full redraw of canvas, background, video image, corner masks, and controls."""
        self.delete("all")
        self.img_item_id = None

        w = self.winfo_width()
        h = self.winfo_height()
        if w < 50 or h < 50:
            return

        r = self.radius
        ctl_h = 44
        view_pad = 6
        screen_bottom = h - ctl_h

        # 1. Outer Container (Clean White with Rounded Corners)
        draw_rounded_rect(self, 1, 1, w - 1, h - 1, r, fill="#ffffff", outline="#e2e8f0", width=1)

        # 2. Upper Video Preview Screen
        mid_x = w // 2
        mid_y = (screen_bottom + view_pad) // 2

        if self.filepath:
            tw, th = self._get_target_dimensions()
            self._current_tw = tw
            self._current_th = th

            # Proportional cinema viewport fitting the video snuggly without giant side wings
            screen_x1 = max(view_pad, mid_x - tw // 2)
            screen_x2 = min(w - view_pad, mid_x + tw // 2)
            screen_y1 = view_pad
            screen_y2 = screen_y1 + th

            self._screen_bounds = (screen_x1, screen_y1, screen_x2, screen_y2)
            frame_mid_x = (screen_x1 + screen_x2) // 2
            frame_mid_y = (screen_y1 + screen_y2) // 2

            # Cinema Black Screen (#000000)
            draw_rounded_rect(
                self,
                screen_x1, screen_y1,
                screen_x2, screen_y2,
                10,
                fill="#000000",
                outline="#000000",
                width=1
            )

            # Draw current frame
            if self.current_frame_image:
                self.img_item_id = self.create_image(frame_mid_x, frame_mid_y, image=self.current_frame_image)

            # Rounded corner masks
            self._draw_corner_masks(screen_x1, screen_y1, screen_x2, screen_y2, r=10, fill_color="#ffffff", border_color="#cbd5e1")

            # Center Play Overlay when paused
            if not self.is_playing:
                self.create_oval(frame_mid_x - 24, frame_mid_y - 24, frame_mid_x + 24, frame_mid_y + 24, fill="#ef4444", outline="", tags="play_overlay")
                self.create_polygon(
                    frame_mid_x - 7, frame_mid_y - 11,
                    frame_mid_x + 13, frame_mid_y,
                    frame_mid_x - 7, frame_mid_y + 11,
                    fill="#ffffff", outline="", tags="play_overlay"
                )

            # Scrubber track aligned directly under the video frame
            scrub_pad = screen_x1 + 4
            scrub_w = max(40, (screen_x2 - screen_x1) - 8)
            scrub_y = screen_y2 + 8
            self._scrub_y = scrub_y
            self._scrub_bounds = (scrub_pad, scrub_w)
            self._controls_y = scrub_y + 16
            self._controls_start_x = scrub_pad

        else:
            # Idle placeholder when no video is loaded
            tw = min(w - 2 * view_pad, 480)
            th = int(tw * 9.0 / 16.0)
            tw = tw - (tw % 2)
            th = th - (th % 2)
            screen_x1 = max(view_pad, mid_x - tw // 2)
            screen_x2 = min(w - view_pad, mid_x + tw // 2)
            screen_y1 = view_pad
            screen_y2 = screen_y1 + th

            self._screen_bounds = (screen_x1, screen_y1, screen_x2, screen_y2)
            frame_mid_x = (screen_x1 + screen_x2) // 2
            frame_mid_y = (screen_y1 + screen_y2) // 2

            draw_rounded_rect(
                self,
                screen_x1, screen_y1,
                screen_x2, screen_y2,
                10,
                fill="#f8fafc",
                outline="#e2e8f0",
                width=1
            )
            self.create_oval(
                frame_mid_x - 28, frame_mid_y - 28,
                frame_mid_x + 28, frame_mid_y + 28,
                fill="#ffffff",
                outline="#cbd5e1",
                width=2
            )
            self.create_polygon(
                frame_mid_x - 6, frame_mid_y - 11,
                frame_mid_x + 12, frame_mid_y,
                frame_mid_x - 6, frame_mid_y + 11,
                fill="#0284c7",
                outline=""
            )

            scrub_pad = screen_x1 + 4
            scrub_w = max(40, (screen_x2 - screen_x1) - 8)
            scrub_y = screen_y2 + 8
            self._scrub_y = scrub_y
            self._scrub_bounds = (scrub_pad, scrub_w)
            self._controls_y = scrub_y + 16
            self._controls_start_x = scrub_pad

        # 3. YouTube Bottom Controls
        # Scrubber Background track
        self.create_rectangle(scrub_pad, scrub_y, scrub_pad + scrub_w, scrub_y + 3, fill="#e2e8f0", outline="")

        # Scrubber Progress Red Bar and Knob
        prog = 0.0
        if self.duration > 0:
            prog = max(0.0, min(1.0, self.current_time / self.duration))
        played_w = scrub_pad + int(scrub_w * prog)
        self.scrub_fill_id = self.create_rectangle(scrub_pad, scrub_y, played_w, scrub_y + 3, fill="#ff0000", outline="")
        self.scrub_knob_id = self.create_oval(played_w - 5, scrub_y - 3, played_w + 5, scrub_y + 6, fill="#ff0000", outline="")

        # Controls Row aligned snugly with video frame
        cy = self._controls_y
        cs_x = self._controls_start_x
        icon_color = "#0f172a"

        # Play / Pause toggle icon
        px = cs_x + 12
        if not self.is_playing:
            self.create_polygon(px - 5, cy - 7, px + 7, cy, px - 5, cy + 7, fill=icon_color, outline="")
        else:
            self.create_rectangle(px - 5, cy - 6, px - 2, cy + 6, fill=icon_color, outline="")
            self.create_rectangle(px + 2, cy - 6, px + 5, cy + 6, fill=icon_color, outline="")

        # Speaker icon
        sx = cs_x + 40
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
        vx1, vx2 = cs_x + 58, cs_x + 106
        self.create_rectangle(vx1, cy - 1, vx2, cy + 2, fill="#e2e8f0", outline="")
        cur_v = 0.0 if self.is_muted else self.volume
        vol_fill_w = vx1 + int((vx2 - vx1) * cur_v)
        self.create_rectangle(vx1, cy - 1, vol_fill_w, cy + 2, fill=icon_color, outline="")
        self.create_oval(vol_fill_w - 3, cy - 3, vol_fill_w + 3, cy + 3, fill=icon_color, outline="")

        # Time readout
        time_text = f"{self._format_time(self.current_time)} / {self._format_time(self.duration)}"
        self.time_text_id = self.create_text(
            cs_x + 118, cy,
            text=time_text,
            fill=icon_color,
            font=("Segoe UI", 9, "bold"),
            anchor="w"
        )

    def _update_progress_only(self):
        """Update only the timeline scrubber and timestamp text without full redraw."""
        if not self.filepath or self.duration <= 0:
            return

        w = self.winfo_width()
        scrub_pad, scrub_w = getattr(self, "_scrub_bounds", (12, max(40, w - 24)))
        prog = max(0.0, min(1.0, self.current_time / self.duration))
        played_w = scrub_pad + int(scrub_w * prog)
        scrub_y = getattr(self, "_scrub_y", self.winfo_height() - 36)

        if self.scrub_fill_id is not None:
            self.coords(self.scrub_fill_id, scrub_pad, scrub_y, played_w, scrub_y + 3)
        if self.scrub_knob_id is not None:
            self.coords(self.scrub_knob_id, played_w - 5, scrub_y - 3, played_w + 5, scrub_y + 6)
        if self.time_text_id is not None:
            time_text = f"{self._format_time(self.current_time)} / {self._format_time(self.duration)}"
            self.itemconfigure(self.time_text_id, text=time_text)

    def _format_time(self, seconds):
        """Format floating seconds into M:SS or H:MM:SS."""
        s = int(max(0, seconds))
        m = s // 60
        s = s % 60
        h = m // 60
        m = m % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _on_mouse_down(self, event):
        w = self.winfo_width()
        h = self.winfo_height()

        if not self.filepath:
            return

        screen_bounds = getattr(self, "_screen_bounds", None)
        scrub_bounds = getattr(self, "_scrub_bounds", (12, max(40, w - 24)))
        scrub_pad, scrub_w = scrub_bounds
        scrub_y = getattr(self, "_scrub_y", h - 36)
        controls_y = getattr(self, "_controls_y", h - 20)
        cs_x = getattr(self, "_controls_start_x", 12)

        # 1. Clicking on Video Screen (Debounced by 250ms for YouTube double-click differentiation)
        if screen_bounds:
            sx1, sy1, sx2, sy2 = screen_bounds
            if sx1 <= event.x <= sx2 and sy1 <= event.y <= sy2:
                if self._single_click_timer:
                    try:
                        self.after_cancel(self._single_click_timer)
                    except Exception:
                        pass
                    self._single_click_timer = None

                # Wait 250ms: if not a double-click, toggle play/pause!
                self._single_click_timer = self.after(250, self.toggle_play_pause)
                return

        # 2. Clicking on Scrubber
        if (scrub_y - 6) <= event.y <= (scrub_y + 8) and scrub_w > 0:
            if scrub_pad - 8 <= event.x <= scrub_pad + scrub_w + 8:
                if self.duration > 0:
                    self._was_playing_before_scrub = self.is_playing
                    if self.is_playing:
                        self.pause_playback()

                    self.is_scrubbing = True
                    prog = max(0.0, min(1.0, (event.x - scrub_pad) / float(scrub_w)))
                    self.current_time = prog * self.duration
                    tw, th = self._get_target_dimensions()
                    threading.Thread(target=self._extract_frame_worker, args=(self.current_time, tw, th), daemon=True).start()
                    self._update_progress_only()
                return

        # 3. Controls Click (Play/Pause, Speaker, Volume)
        if (controls_y - 14) <= event.y <= (controls_y + 14):
            # Play / Pause icon
            if cs_x <= event.x <= cs_x + 28:
                self.toggle_play_pause()
                return

            # Speaker Mute toggle
            if cs_x + 32 <= event.x <= cs_x + 52:
                self.is_muted = not self.is_muted
                vol = 0.0 if self.is_muted else self.volume
                self.audio_player.set_volume(vol)
                self._redraw_full()
                return

            # Volume slider
            if cs_x + 56 <= event.x <= cs_x + 110:
                self.is_adjusting_vol = True
                v = max(0.0, min(1.0, (event.x - (cs_x + 58)) / 48.0))
                self.volume = v
                self.is_muted = (v == 0)
                self.audio_player.set_volume(0.0 if self.is_muted else self.volume)
                self._redraw_full()
                return

    def _on_double_click(self, event):
        """
        YouTube-Style Double Click:
        - Double click on LEFT side: Skip backward 10s (-10s)
        - Double click on RIGHT side: Skip forward 10s (+10s)
        """
        if not self.filepath or self.duration <= 0:
            return

        # Cancel single-click play/pause timer immediately!
        if self._single_click_timer:
            try:
                self.after_cancel(self._single_click_timer)
            except Exception:
                pass
            self._single_click_timer = None

        screen_bounds = getattr(self, "_screen_bounds", None)
        if not screen_bounds:
            return

        sx1, sy1, sx2, sy2 = screen_bounds
        if sx1 <= event.x <= sx2 and sy1 <= event.y <= sy2:
            mid_x = (sx1 + sx2) // 2
            if event.x < mid_x:
                # Left side: -10s
                self.seek_relative(-10.0)
            else:
                # Right side: +10s
                self.seek_relative(10.0)

    def _on_mouse_drag(self, event):
        w = self.winfo_width()
        scrub_bounds = getattr(self, "_scrub_bounds", (12, max(40, w - 24)))
        scrub_pad, scrub_w = scrub_bounds
        cs_x = getattr(self, "_controls_start_x", 12)

        if self.is_scrubbing and self.duration > 0 and scrub_w > 0:
            prog = max(0.0, min(1.0, (event.x - scrub_pad) / float(scrub_w)))
            self.current_time = prog * self.duration
            tw, th = self._get_target_dimensions()
            threading.Thread(target=self._extract_frame_worker, args=(self.current_time, tw, th), daemon=True).start()
            self._update_progress_only()
        elif self.is_adjusting_vol:
            v = max(0.0, min(1.0, (event.x - (cs_x + 58)) / 48.0))
            self.volume = v
            self.is_muted = (v == 0)
            self.audio_player.set_volume(0.0 if self.is_muted else self.volume)
            self._redraw_full()

    def _on_mouse_up(self, event):
        if self.is_scrubbing:
            self.is_scrubbing = False
            if self._was_playing_before_scrub:
                self._was_playing_before_scrub = False
                self.start_playback()

        self.is_adjusting_vol = False

    def destroy(self):
        """Cleanup poll loop, process and audio device on destroy."""
        if self._single_click_timer:
            try:
                self.after_cancel(self._single_click_timer)
            except Exception:
                pass
            self._single_click_timer = None

        if self._resize_timer:
            try:
                self.after_cancel(self._resize_timer)
            except Exception:
                pass
            self._resize_timer = None

        if self._poll_job:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

        self.stop_playback()
        self.audio_player.close()
        super().destroy()
