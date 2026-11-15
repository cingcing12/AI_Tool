"""
Unified YouTube Player View Widget: Real Video Frame preview + YouTube controls.
High-Performance 25 FPS Smooth Streaming with Zero Lag and Native Windows Audio!
"""

import os
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
    - Upper area: High-performance 25 FPS video preview streamed directly from FFmpeg into memory
    - Bottom area: Seamless YouTube controls (Red scrubber, Play/Stop toggle, Speaker, Volume, Time)
    - Native synchronized Windows audio via WinMM MCI (0% latency, volume control, instant seek)
    - Thread-safe Queue-based frame ingestion for Python 3.15+ (Zero lag, zero GUI freezes)
    - Clean white aesthetic, zero muddy gray!
    """

    def __init__(self, parent, on_status_change=None, radius=14, **kwargs):
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else "#ffffff"
        super().__init__(parent, bg=parent_bg, highlightthickness=0, bd=0, cursor="hand2", **kwargs)

        self.radius = radius
        self.on_status_change = on_status_change

        # Video & Audio Engines
        self.engine = VideoEngine()
        self.audio_player = WindowsAudioPlayer()
        self.audio_wav_path = None

        # Video State
        self.filepath = ""
        self.filename = ""
        self.is_playing = False
        self.is_muted = False
        self.current_time = 0.0
        self.duration = 0.0
        self.volume = 0.8
        self.previous_volume = 0.8

        # Image & Stream Control
        self.current_frame_image = None
        self._stream_proc = None
        self._stream_thread = None
        self._stop_stream_event = threading.Event()

        # Thread-safe Frame Queue
        self.frame_queue = queue.Queue(maxsize=8)
        self._poll_job = None

        # Canvas Item IDs for fast updates
        self.img_item_id = None
        self.scrub_fill_id = None
        self.scrub_knob_id = None
        self.time_text_id = None

        # Scrubbing & UI Dragging
        self.is_scrubbing = False
        self.is_adjusting_vol = False
        self._was_playing_before_scrub = False

        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_mouse_down)
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

        # Apply single seek frame if requested
        if single_frame:
            self._apply_frame_data(single_frame)

        # Apply latest streaming frame
        if latest_stream_frame and self.is_playing:
            self.current_time = latest_timestamp
            self._apply_frame_data(latest_stream_frame)
            self._update_progress_only()

        # Handle completion
        if finished and self.is_playing:
            self._on_playback_finished()

        # Reschedule next poll
        self._schedule_poll()

    def _format_time(self, seconds):
        s = max(0, int(seconds))
        m = s // 60
        sec = s % 60
        return f"{m}:{sec:02d}"

    def load_video(self, filepath):
        """Load a video file, probe duration, extract audio, and render first frame."""
        self.stop_playback()

        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.current_time = 0.0
        self.is_playing = False
        self.current_frame_image = None

        # 1. Probe duration
        self.duration = self.engine.probe_duration(filepath)

        # 2. Extract audio in background for preview playback
        self.audio_wav_path = os.path.join(self.engine.temp_dir, f"audio_{int(time.time())}.wav")
        threading.Thread(target=self._prepare_audio, daemon=True).start()

        # 3. Extract first frame in memory and render
        tw, th = self._get_target_dimensions()
        threading.Thread(target=self._extract_frame_worker, args=(0.1, tw, th), daemon=True).start()
        self._redraw_full()

    def _prepare_audio(self):
        """Extract audio to WAV and load into native Windows audio player."""
        if not self.filepath:
            return
        wav = self.engine.extract_audio(self.filepath, self.audio_wav_path)
        if wav and os.path.exists(wav):
            self.audio_player.load(wav)
            vol = 0.0 if self.is_muted else self.volume
            self.audio_player.set_volume(vol)

    def _get_target_dimensions(self):
        try:
            w = max(280, self.winfo_width() - 16)
            h = max(160, self.winfo_height() - 56)
        except Exception:
            w, h = 480, 270
        target_w = min(w, int(h * 16.0 / 9.0))
        target_h = int(target_w * 9.0 / 16.0)
        target_w = target_w - (target_w % 2)
        target_h = target_h - (target_h % 2)
        return max(64, target_w), max(36, target_h)

    def _extract_frame_worker(self, timestamp, target_w, target_h):
        """Background thread single-frame fast extraction."""
        if not self.filepath:
            return
        ppm_data = self.engine.extract_frame_ppm(self.filepath, timestamp, target_w, target_h)
        if ppm_data:
            self.frame_queue.put(("single_frame", ppm_data, None))

    def _apply_frame_data(self, ppm_data):
        """Update PhotoImage on UI thread with raw PPM data."""
        try:
            if self.current_frame_image is None:
                self.current_frame_image = tk.PhotoImage(data=ppm_data)
                self._redraw_full()
            else:
                self.current_frame_image.configure(data=ppm_data)
                if self.img_item_id is not None:
                    self.itemconfigure(self.img_item_id, image=self.current_frame_image)
                else:
                    self._redraw_full()
        except Exception:
            pass

    def toggle_play_stop(self):
        """Toggle between smooth playback and stop/reset."""
        if not self.filepath:
            return False

        if not self.is_playing:
            self.start_playback()
        else:
            self.stop_playback(reset_to_start=True)
        return self.is_playing

    def toggle_play(self):
        return self.toggle_play_stop()

    def start_playback(self):
        """Start smooth 25 FPS video stream and synchronized audio."""
        if not self.filepath or self.is_playing:
            return

        self.is_playing = True
        self._stop_stream_event.clear()

        # Clear any stale frames from previous run
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

        # If already at or near end, rewind
        if self.duration > 0 and self.current_time >= self.duration - 0.2:
            self.current_time = 0.0

        if self.on_status_change:
            self.on_status_change("Playing video smoothly... ▶ (Click Stop to stop & reset)")

        # Play audio
        vol = 0.0 if self.is_muted else self.volume
        self.audio_player.set_volume(vol)
        self.audio_player.play(start_ms=self.current_time * 1000)

        # Start video stream thread
        target_w, target_h = self._get_target_dimensions()
        self._stream_thread = threading.Thread(
            target=self._stream_worker,
            args=(self.current_time, target_w, target_h),
            daemon=True
        )
        self._stream_thread.start()
        self._redraw_full()

    def stop_playback(self, reset_to_start=False):
        """Stop streaming, pause audio, and optionally reset to 0:00."""
        self.is_playing = False
        self._stop_stream_event.set()

        # Terminate FFmpeg stream process if running
        if self._stream_proc:
            try:
                self._stream_proc.kill()
            except Exception:
                pass
            self._stream_proc = None

        # Stop audio
        self.audio_player.stop()

        if reset_to_start:
            self.current_time = 0.0
            if self.on_status_change:
                self.on_status_change("Video stopped and reset to 0:00. ■")
            tw, th = self._get_target_dimensions()
            threading.Thread(target=self._extract_frame_worker, args=(0.1, tw, th), daemon=True).start()

        self._redraw_full()

    def _stream_worker(self, start_time, target_w, target_h, fps=25):
        """Background thread streaming continuous frames from FFmpeg pipe at 25 FPS."""
        stream_res = self.engine.start_video_stream(self.filepath, start_time, target_w, target_h, fps)
        if not stream_res:
            self.frame_queue.put(("finished", None, None))
            return

        proc, w, h = stream_res
        self._stream_proc = proc

        frame_size = w * h * 3
        frame_interval = 1.0 / float(fps)
        header = f"P6\n{w} {h}\n255\n".encode("ascii")

        clock_start = time.perf_counter()
        frame_index = 0

        try:
            while not self._stop_stream_event.is_set():
                raw_frame = proc.stdout.read(frame_size)
                if len(raw_frame) < frame_size:
                    # Video stream reached end
                    break

                frame_index += 1
                cur_t = start_time + (frame_index / float(fps))
                ppm_data = header + raw_frame

                # Push to queue (drop if full to avoid any lag)
                try:
                    self.frame_queue.put_nowait(("stream_frame", ppm_data, cur_t))
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait(("stream_frame", ppm_data, cur_t))
                    except Exception:
                        pass

                # High-precision frame timing
                target_clock = clock_start + (frame_index * frame_interval)
                sleep_sec = target_clock - time.perf_counter()
                if sleep_sec > 0:
                    time.sleep(sleep_sec)

        except Exception:
            pass
        finally:
            try:
                proc.stdout.close()
                proc.kill()
            except Exception:
                pass

        if not self._stop_stream_event.is_set():
            self.frame_queue.put(("finished", None, None))

    def _on_playback_finished(self):
        """Handle end of video reached."""
        self.is_playing = False
        self.current_time = 0.0
        self.audio_player.stop()
        if self.on_status_change:
            self.on_status_change("Playback finished and reset to 0:00.")
        self._redraw_full()
        tw, th = self._get_target_dimensions()
        threading.Thread(target=self._extract_frame_worker, args=(0.1, tw, th), daemon=True).start()

    def _update_progress_only(self):
        """Fast flicker-free update of scrubber and time readout only."""
        w = self.winfo_width()
        scrub_pad = 12
        scrub_w = w - 2 * scrub_pad
        scrub_y = self.winfo_height() - 44 + 8

        if self.duration > 0 and scrub_w > 0:
            prog = max(0.0, min(1.0, self.current_time / self.duration))
            played_w = scrub_pad + int(scrub_w * prog)
            if self.scrub_fill_id is not None:
                self.coords(self.scrub_fill_id, scrub_pad, scrub_y, played_w, scrub_y + 3)
            if self.scrub_knob_id is not None:
                self.coords(self.scrub_knob_id, played_w - 5, scrub_y - 3, played_w + 5, scrub_y + 6)

        if self.time_text_id is not None:
            time_text = f"{self._format_time(self.current_time)} / {self._format_time(self.duration)}"
            self.itemconfigure(self.time_text_id, text=time_text)

    def _on_configure(self, event=None):
        self._redraw_full()

    def _redraw_full(self, event=None):
        """Complete redraw of the unified video canvas and YouTube controls."""
        self.delete("all")
        self.img_item_id = None
        self.scrub_fill_id = None
        self.scrub_knob_id = None
        self.time_text_id = None

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
                self.img_item_id = self.create_image(mid_x, mid_y, image=self.current_frame_image)

            # Center Play Overlay when paused
            if not self.is_playing:
                self.create_oval(mid_x - 24, mid_y - 24, mid_x + 24, mid_y + 24, fill="#ef4444", outline="")
                self.create_polygon(
                    mid_x - 7, mid_y - 11,
                    mid_x + 13, mid_y,
                    mid_x - 7, mid_y + 11,
                    fill="#ffffff", outline=""
                )
        else:
            # Idle placeholder when no video is loaded
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
        scrub_w = w - 2 * scrub_pad

        # Scrubber Background track
        self.create_rectangle(scrub_pad, scrub_y, w - scrub_pad, scrub_y + 3, fill="#e2e8f0", outline="")

        # Scrubber Progress Red Bar and Knob
        prog = 0.0
        if self.duration > 0:
            prog = max(0.0, min(1.0, self.current_time / self.duration))
        played_w = scrub_pad + int(scrub_w * prog)
        self.scrub_fill_id = self.create_rectangle(scrub_pad, scrub_y, played_w, scrub_y + 3, fill="#ff0000", outline="")
        self.scrub_knob_id = self.create_oval(played_w - 5, scrub_y - 3, played_w + 5, scrub_y + 6, fill="#ff0000", outline="")

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
        self.time_text_id = self.create_text(
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

        # 1. Clicking on Video Screen toggles Play / Stop
        if event.y < screen_bottom:
            self.toggle_play_stop()
            return

        # 2. Clicking on Scrubber
        if (scrub_y - 6) <= event.y <= (scrub_y + 8) and scrub_w > 0:
            if self.duration > 0:
                self._was_playing_before_scrub = self.is_playing
                if self.is_playing:
                    self.stop_playback(reset_to_start=False)

                self.is_scrubbing = True
                prog = max(0.0, min(1.0, (event.x - scrub_pad) / float(scrub_w)))
                self.current_time = prog * self.duration
                tw, th = self._get_target_dimensions()
                threading.Thread(target=self._extract_frame_worker, args=(self.current_time, tw, th), daemon=True).start()
                self._update_progress_only()
                if self.on_status_change:
                    self.on_status_change(f"Seeked to {self._format_time(self.current_time)}")
            return

        # 3. Play / Stop Button Click
        if 10 <= event.x <= 40:
            self.toggle_play_stop()
            return

        # 4. Speaker / Mute Button Click
        if 46 <= event.x <= 70:
            self.is_muted = not self.is_muted
            vol = 0.0 if self.is_muted else self.volume
            self.audio_player.set_volume(vol)
            self._redraw_full()
            if self.on_status_change:
                self.on_status_change("Sound muted." if self.is_muted else f"Sound unmuted ({int(self.volume*100)}%).")
            return

        # 5. Volume Slider Bar Click
        if 74 <= event.x <= 128:
            self.is_adjusting_vol = True
            v = max(0.0, min(1.0, (event.x - 76) / 48.0))
            self.volume = v
            self.is_muted = (v == 0)
            self.audio_player.set_volume(0.0 if self.is_muted else self.volume)
            self._redraw_full()
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
            tw, th = self._get_target_dimensions()
            threading.Thread(target=self._extract_frame_worker, args=(self.current_time, tw, th), daemon=True).start()
            self._update_progress_only()
        elif self.is_adjusting_vol:
            v = max(0.0, min(1.0, (event.x - 76) / 48.0))
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
        if self._poll_job:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

        self.stop_playback()
        self.audio_player.close()
        super().destroy()
