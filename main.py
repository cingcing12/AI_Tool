"""
Video Translate & AI Subtitle Tool
Professional High-Performance Desktop Application with Unified Media Player & Script Extractor.
"""

from __future__ import annotations

import os
import sys
import time
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
# Ensure src is in Python path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from src.ui import RoundedCard, RoundedButton, RoundedProgressBar, YouTubePlayerView
from src.core import VideoEngine, ScriptExtractor, DubbingEngine


class VideoTranslateApp(tk.Tk):
    """Main Application Controller for Video Translate & Subtitle Studio."""

    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Video Translate & Subtitle Studio")
        self.geometry("820x490")
        self.minsize(760, 460)
        # Lock window aspect ratio to maintain stable proportions on resize (avoiding flat/ultra-wide window)
        self.aspect(14, 10, 18, 10)
        self.configure(bg="#f1f5f9")

        # Core Engines
        self.engine = VideoEngine(base_dir=APP_DIR)
        self.script_extractor = ScriptExtractor(model_size="base")
        self.dubbing_engine = DubbingEngine(ffmpeg_path=self.engine.ffmpeg_path, temp_dir=self.engine.temp_dir)

        # Variables
        self.video_path_var = tk.StringVar(value="")
        default_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        self.output_folder = default_downloads if os.path.exists(default_downloads) else os.path.expanduser("~")

        self.voice_type = "Man"
        self.status_var = tk.StringVar(value="Ready")
        self.is_processing = False

        # Thread-safe UI Task Queue (handles Python 3.15 background worker updates)
        self.ui_queue = queue.Queue()

        # Build UI Layout
        self._create_layout()

        # Start UI queue polling loop
        self._poll_ui_queue()

        # Clean shutdown protocol
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Ensure stream processes and audio player are closed gracefully."""
        if hasattr(self, "player_view"):
            self.player_view.destroy()
        self.destroy()

    def _create_layout(self):
        """Construct the 2-column layout (Left: Unified YouTube Player, Right: Controls) & Bottom Progress Bar."""

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

        # Unified YouTube Video Player Screen
        self.player_view = YouTubePlayerView(
            self.left_card.container,
            on_status_change=lambda msg: self.status_var.set(msg),
            radius=12
        )
        self.player_view.pack(fill=tk.BOTH, expand=True)

        # ==========================================
        # RIGHT COLUMN: Rounded Card for Controls
        # 1. Load: Pick and load video file (Top)
        # 2. Extract Script (SRT): Generate subtitles with timestamps
        # 3. Browse: Choose save/output location
        # 4. Voice: Toggle Man / Woman
        # 5. Start: Start dubbing process
        # ==========================================
        self.right_card = RoundedCard(
            content_frame,
            bg_color="#ffffff",
            border_color="#e2e8f0",
            radius=16,
            width=230
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
        right_title.pack(anchor="center", pady=(0, 8))

        # Button 1: Load (Top position, loads video directly into player)
        self.btn_load = RoundedButton(
            self.right_card.container,
            text="Load Video",
            command=self.load_video,
            bg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            radius=12,
            height=36
        )
        self.btn_load.pack(fill=tk.X, pady=(0, 8))

        # Button 2: Extract Script (SRT Subtitles with Timestamps)
        self.btn_extract_script = RoundedButton(
            self.right_card.container,
            text="Extract Script (SRT)",
            command=self.extract_script,
            bg_color="#7c3aed",
            hover_color="#6d28d9",
            text_color="#ffffff",
            radius=12,
            height=36
        )
        self.btn_extract_script.pack(fill=tk.X, pady=(0, 8))

        # Button 3: Browse (Picks destination folder where outputs are saved)
        self.btn_browse = RoundedButton(
            self.right_card.container,
            text="Browse Output",
            command=self.browse_output_folder,
            bg_color="#6366f1",
            hover_color="#4f46e5",
            text_color="#ffffff",
            radius=12,
            height=36
        )
        self.btn_browse.pack(fill=tk.X, pady=(0, 8))

        # Button 4: Toggle Voice Button (Man / Woman)
        self.btn_voice_toggle = RoundedButton(
            self.right_card.container,
            text="Voice: Man",
            command=self.toggle_voice,
            bg_color="#ea580c",
            hover_color="#c2410c",
            text_color="#ffffff",
            radius=12,
            height=36
        )
        self.btn_voice_toggle.pack(fill=tk.X, pady=(0, 8))

        # Button 5: Start Dubbing (Bottom position)
        self.btn_start = RoundedButton(
            self.right_card.container,
            text="Start Dubbing",
            command=self.start_dubbing,
            bg_color="#10b981",
            hover_color="#059669",
            text_color="#ffffff",
            radius=12,
            height=38,
            font=("Segoe UI", 10, "bold")
        )
        self.btn_start.pack(fill=tk.X, side=tk.BOTTOM, pady=(6, 0))

        # ==========================================
        # BOTTOM: Unified Rounded Progress Bar & Status
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

        # Smooth Rounded Progress Bar
        self.progress_bar = RoundedProgressBar(
            bottom_frame,
            height=14,
            trough_color="#e2e8f0",
            fill_color="#10b981",
            radius=7
        )
        self.progress_bar.pack(fill=tk.X)

    def _set_controls_state(self, state):
        """Enable or disable all control buttons safely."""
        self.btn_load.set_state(state)
        self.btn_extract_script.set_state(state)
        self.btn_browse.set_state(state)
        self.btn_voice_toggle.set_state(state)
        self.btn_start.set_state(state)

    def _poll_ui_queue(self):
        """Poll thread-safe UI task queue on Tkinter's main event loop."""
        while not self.ui_queue.empty():
            try:
                fn = self.ui_queue.get_nowait()
                fn()
            except queue.Empty:
                break
            except Exception as e:
                print(f"[UI Queue Error]: {e}")
        self.after(30, self._poll_ui_queue)

    def run_on_ui_thread(self, fn):
        """Safely schedule any UI action to run on the main Tkinter thread."""
        self.ui_queue.put(fn)

    def set_controls_state_safe(self, state):
        """Thread-safe control state dispatcher."""
        self.run_on_ui_thread(lambda: self._set_controls_state(state))

    def update_progress_safe(self, status: str, percent: int):
        """Thread-safe UI dispatcher using Tkinter's after queue."""
        def _apply():
            if status:
                self.status_var.set(status)
            self.progress_bar.set_progress(percent)
            self.percent_label.config(text=f"{int(percent)}%")
        self.run_on_ui_thread(_apply)

    # ==========================================
    # Button Actions
    # ==========================================
    def load_video(self):
        """Action 1 (Load): Select input video file and immediately load into player."""
        filetypes = [
            ("Video Files", "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm"),
            ("All Files", "*.*")
        ]
        selected_file = filedialog.askopenfilename(
            title="Select Video to Load",
            filetypes=filetypes
        )
        if not selected_file:
            return

        if not os.path.exists(selected_file):
            messagebox.showerror("Error", "File not found! Please check file path.")
            return

        self.video_path_var.set(selected_file)

        # Load video and extract first frame via VideoEngine
        self.player_view.load_video(selected_file)
        self.status_var.set("Ready")

    def extract_script(self):
        """Action 2 (Extract Script): Generate standard .srt subtitles from the video."""
        filepath = self.video_path_var.get()
        if not filepath:
            messagebox.showwarning("Notice", "Please click 'Load Video' first!")
            return

        if self.is_processing:
            messagebox.showinfo("In Progress", "Another task is already in progress.")
            return

        # Pause video playback if currently running
        if hasattr(self, "player_view") and self.player_view.is_playing:
            self.player_view.toggle_play_stop()

        # Prepare destination .srt path
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_srt_path = os.path.join(self.output_folder, f"{base_name}_subtitles.srt")

        self.is_processing = True
        self._set_controls_state(tk.DISABLED)
        self.progress_bar.set_progress(0)
        self.percent_label.config(text="0%")
        self.status_var.set("Initializing speech recognition engine...")

        thread = threading.Thread(
            target=self._extract_script_worker,
            args=(filepath, output_srt_path),
            daemon=True
        )
        thread.start()

    def _extract_script_worker(self, filepath, output_srt_path):
        """Worker thread executing speech transcription into .srt file."""
        def on_progress(msg, pct):
            self.update_progress_safe(msg, pct)

        try:
            srt_content = self.script_extractor.extract_script_to_srt(
                video_path=filepath,
                output_srt_path=output_srt_path,
                on_progress=on_progress
            )

            # Sample preview of first 6 subtitle lines
            lines = [l for l in srt_content.strip().splitlines() if l.strip()]
            preview_sample = "\n".join(lines[:6]) if lines else "No speech detected."

            self.run_on_ui_thread(lambda p=output_srt_path, s=preview_sample: messagebox.showinfo(
                "Script Extracted Successfully! 🎉",
                f"Generated SubRip (.srt) subtitle file:\n\n"
                f"Saved to:\n{p}\n\n"
                f"Preview:\n{s}"
            ))
        except RuntimeError as re:
            err_re = str(re)
            self.update_progress_safe("Missing dependency", 0)
            self.run_on_ui_thread(lambda m=err_re: messagebox.showerror(
                "Missing Dependency",
                m
            ))
        except Exception as exc:
            err_exc = str(exc)
            self.update_progress_safe(f"Extraction Error: {err_exc}", 0)
            self.run_on_ui_thread(lambda m=err_exc: messagebox.showerror(
                "Error",
                f"Failed to extract script:\n{m}"
            ))
        finally:
            self.is_processing = False
            self.set_controls_state_safe(tk.NORMAL)

    def browse_output_folder(self):
        """Action 3 (Browse): Select destination folder where outputs will be stored."""
        selected_dir = filedialog.askdirectory(
            title="Select Output Folder",
            initialdir=self.output_folder
        )
        if selected_dir:
            self.output_folder = selected_dir
            self.status_var.set("Ready")

    def toggle_voice(self):
        """Action 4 (Voice): Toggle between Man and Woman on each click."""
        if self.voice_type == "Man":
            self.voice_type = "Woman"
            self.btn_voice_toggle.set_text("Voice: Woman")
            self.btn_voice_toggle.set_colors("#db2777", "#be185d")
        else:
            self.voice_type = "Man"
            self.btn_voice_toggle.set_text("Voice: Man")
            self.btn_voice_toggle.set_colors("#ea580c", "#c2410c")

    def start_dubbing(self):
        """Action 5 (Start): Start dubbing and save output to the destination folder."""
        filepath = self.video_path_var.get()
        if not filepath:
            messagebox.showwarning("Notice", "Please click 'Load Video' first!")
            return

        if self.is_processing:
            messagebox.showinfo("In Progress", "A task is already in progress.")
            return

        # Stop playback if currently running
        if self.player_view.is_playing:
            self.player_view.toggle_play_stop()

        self.is_processing = True
        self._set_controls_state(tk.DISABLED)

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
        """Worker thread executing end-to-end Khmer dubbing pipeline."""
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        source_srt_path = os.path.join(self.output_folder, f"{base_name}_subtitles.srt")
        khmer_srt_path = os.path.join(self.output_folder, f"{base_name}_khmer.srt")
        khmer_txt_path = os.path.join(self.output_folder, f"{base_name}_khmer.txt")
        khmer_audio_path = os.path.join(self.output_folder, f"{base_name}_khmer_{voice.lower()}.mp3")

        def on_progress(msg, pct):
            self.update_progress_safe(msg, pct)

        try:
            # Step 1: Ensure source script is extracted
            if not os.path.exists(source_srt_path) or os.path.getsize(source_srt_path) == 0:
                self.update_progress_safe("Step 1/4: Extracting spoken script from video...", 10)
                self.script_extractor.extract_script_to_srt(
                    video_path=filepath,
                    output_srt_path=source_srt_path,
                    on_progress=lambda m, p: self.update_progress_safe(f"Step 1/4: {m}", min(25, int(p * 0.25)))
                )

            # Step 2: Translate script to Khmer
            self.update_progress_safe("Step 2/4: Translating subtitles to Khmer...", 30)
            khmer_segments, full_khmer_script = self.dubbing_engine.translate_script(
                source_srt_path=source_srt_path,
                output_khmer_srt=khmer_srt_path,
                output_khmer_txt=khmer_txt_path,
                on_progress=on_progress
            )

            # If existing SRT on disk was empty or stale, re-extract fresh script
            if not full_khmer_script or not full_khmer_script.strip():
                self.update_progress_safe("Re-extracting fresh subtitles...", 15)
                self.script_extractor.extract_script_to_srt(
                    video_path=filepath,
                    output_srt_path=source_srt_path,
                    on_progress=lambda m, p: self.update_progress_safe(f"Step 1/4: {m}", min(25, int(p * 0.25)))
                )
                khmer_segments, full_khmer_script = self.dubbing_engine.translate_script(
                    source_srt_path=source_srt_path,
                    output_khmer_srt=khmer_srt_path,
                    output_khmer_txt=khmer_txt_path,
                    on_progress=on_progress
                )

            if not full_khmer_script or not full_khmer_script.strip():
                raise RuntimeError("Translation to Khmer produced no text. Please verify internet connection.")

            # Probe exact video duration for precision timeline alignment
            meta = self.engine.probe_video_metadata(filepath)
            video_duration = meta.get("duration", 0.0)

            # Step 3: Synthesize authentic Khmer voiceover SYNCHRONIZED IN REALTIME with video speech
            self.update_progress_safe(f"Step 3/4: Generating realtime Khmer {voice} voice synced to video speech...", 50)
            generated_audio = self.dubbing_engine.generate_timed_voice(
                khmer_segments=khmer_segments,
                voice_type=voice,
                total_video_duration=video_duration,
                output_audio_path=khmer_audio_path,
                on_progress=on_progress
            )

            # Step 4: Merge Khmer voice into video and REMOVE 100% of the original sound
            self.update_progress_safe("Step 4/4: Replacing original audio with pure Khmer voice...", 85)
            self.dubbing_engine.merge_video(
                video_path=filepath,
                audio_path=generated_audio,
                output_video_path=output_path,
                remove_original_sound=True,
                background_volume=0.0,
                on_progress=on_progress
            )

            self.update_progress_safe("Dubbing Complete! 🎉", 100)

            # Prompt success with details and auto-load dubbed video for instant preview
            def _on_success():
                try:
                    self.player_view.load_video(output_path)
                    self.video_path_var.set(output_path)
                except Exception:
                    pass
                messagebox.showinfo(
                    "Dubbing Complete! 🎉",
                    f"Video successfully dubbed in Khmer ({voice} voice)!\n\n"
                    f"🎬 Output Video:\n{output_path}\n\n"
                    f"🔊 Khmer Audio:\n{khmer_audio_path}\n\n"
                    f"📝 Khmer Subtitles:\n{khmer_srt_path}\n\n"
                    f"The dubbed video is loaded in the player. Click Play to watch!"
                )

            self.run_on_ui_thread(_on_success)
        except Exception as e:
            self.update_progress_safe(f"Error: {e}", 0)
            self.run_on_ui_thread(lambda err=e: messagebox.showerror(
                "Dubbing Error",
                f"Failed to generate Khmer dubbed video:\n{err}"
            ))
        finally:
            self.is_processing = False
            self.set_controls_state_safe(tk.NORMAL)


# Backward compatibility alias
VideoDubbingApp = VideoTranslateApp

if __name__ == "__main__":
    app = VideoTranslateApp()
    app.mainloop()
    try:
        app.destroy()
    except Exception:
        pass
