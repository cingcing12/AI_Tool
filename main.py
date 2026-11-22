"""
Video Translate & AI Subtitle Tool
Professional High-Performance Desktop Application with Unified Media Player & Script Extractor.
"""

from __future__ import annotations

import os
import sys
import time
import queue
import shutil
import threading
from typing import Optional
import tkinter as tk
from tkinter import filedialog, messagebox
# Ensure src is in Python path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from src.ui import RoundedCard, RoundedButton, RoundedProgressBar, YouTubePlayerView
from src.core import VideoEngine, ScriptExtractor, DubbingEngine, VoxCPMEngine, WindowsAudioPlayer


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
        self.voxcpm_engine = VoxCPMEngine(ffmpeg_path=self.engine.ffmpeg_path, temp_dir=self.engine.temp_dir)
        self.dubbing_engine = DubbingEngine(
            ffmpeg_path=self.engine.ffmpeg_path,
            temp_dir=self.engine.temp_dir,
            voxcpm_engine=self.voxcpm_engine
        )
        self.sample_player = WindowsAudioPlayer()

        # Variables
        self.video_path_var = tk.StringVar(value="")
        default_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        self.output_folder = default_downloads if os.path.exists(default_downloads) else os.path.expanduser("~")

        self.voice_type = "Man"
        self.custom_reference_audio: Optional[str] = None
        self.status_var = tk.StringVar(value="Ready")
        self.is_processing = False
        self._cancel_event = threading.Event()

        # Review & Manual Save State
        self.last_dubbed_video: Optional[str] = None
        self.last_dubbed_srt: Optional[str] = None
        self.last_dubbed_audio: Optional[str] = None
        self.last_video_basename: str = ""
        self.last_voice_tag: str = ""
        self.original_video_path: Optional[str] = None

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
        if self.is_processing:
            self.cancel_processing()
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
        # 2. Browse: Choose save/output location
        # 3. Voice: Toggle Man / Woman / Clone
        # 4. Start: Start automated dubbing (Auto-extracts SRT -> Translates -> Voices -> Merges)
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

        # Button 2: Browse (Picks destination folder where outputs are saved)
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

        # Button 4: Toggle Voice Button (Man / Woman / Clone VoxCPM 2)
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
        self.btn_voice_toggle.pack(fill=tk.X, pady=(0, 6))

        # Button 4b: Voice Reference / Clone Sample (For VoxCPM 2)
        self.btn_voice_sample = RoundedButton(
            self.right_card.container,
            text="Sample: Video Audio",
            command=self.on_voice_sample_clicked,
            bg_color="#94a3b8",
            hover_color="#64748b",
            text_color="#ffffff",
            radius=12,
            height=32
        )
        self.btn_voice_sample.pack(fill=tk.X, pady=(0, 8))
        self.btn_voice_sample.bind("<Button-3>", lambda e: self.configure_clone_sample())

        # Button: Save Video (Manual save after review)
        self.btn_save = RoundedButton(
            self.right_card.container,
            text="Save Video",
            command=self.save_video,
            bg_color="#059669",
            hover_color="#047857",
            text_color="#ffffff",
            radius=12,
            height=36,
            font=("Segoe UI", 10, "bold")
        )
        self.btn_save.pack(fill=tk.X, pady=(0, 8))
        self.btn_save.set_state(tk.DISABLED)

        # Stop / Cancel Processing Button (At bottom)
        self.btn_cancel = RoundedButton(
            self.right_card.container,
            text="Stop Processing",
            command=self.cancel_processing,
            bg_color="#ef4444",
            hover_color="#dc2626",
            text_color="#ffffff",
            radius=12,
            height=34,
            font=("Segoe UI", 9, "bold")
        )
        self.btn_cancel.pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))
        self.btn_cancel.set_state(tk.DISABLED)

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

        # Pre-warm voice samples in a background thread for instant (0.001s) sample playback
        def _prewarm_samples():
            try:
                temp_dir = self.engine.temp_dir
                man_p = os.path.join(temp_dir, "sample_man.mp3")
                wom_p = os.path.join(temp_dir, "sample_woman.mp3")
                sample_text = "សួស្តីបងប្អូន នេះជាសំឡេងនិយាយភាសាខ្មែរ"
                if not (os.path.exists(man_p) and os.path.getsize(man_p) > 100):
                    self.dubbing_engine.synthesize_single_line(sample_text, "Man", man_p)
                if not (os.path.exists(wom_p) and os.path.getsize(wom_p) > 100):
                    self.dubbing_engine.synthesize_single_line(sample_text, "Woman", wom_p)
            except Exception:
                pass
        threading.Thread(target=_prewarm_samples, daemon=True).start()

    def _set_controls_state(self, state):
        """Enable or disable control buttons safely based on processing state."""
        if state == "processing":
            self.btn_load.set_state(tk.DISABLED)
            self.btn_browse.set_state(tk.DISABLED)
            self.btn_voice_toggle.set_state(tk.DISABLED)
            self.btn_voice_sample.set_state(tk.DISABLED)
            self.btn_save.set_state(tk.DISABLED)
            self.btn_start.set_state(tk.DISABLED)
            self.btn_cancel.set_state(tk.NORMAL)
            self.btn_cancel.set_text("Stop Processing")
        else:
            self.btn_load.set_state(tk.NORMAL)
            self.btn_browse.set_state(tk.NORMAL)
            self.btn_voice_toggle.set_state(tk.NORMAL)
            self.btn_voice_sample.set_state(tk.NORMAL)
            self.btn_start.set_state(tk.NORMAL)
            self.btn_cancel.set_state(tk.DISABLED)
            self.btn_cancel.set_text("Stop Processing")
            has_preview = bool(self.last_dubbed_video and os.path.exists(self.last_dubbed_video))
            self.btn_save.set_state(tk.NORMAL if has_preview else tk.DISABLED)

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
        self.original_video_path = selected_file
        self.last_dubbed_video = None
        self.last_dubbed_srt = None
        self.last_dubbed_audio = None
        self.btn_save.set_state(tk.DISABLED)

        # Load video and extract first frame via VideoEngine
        self.player_view.load_video(selected_file)
        self.status_var.set("Ready")

    def save_video(self):
        """Action: Manually save the reviewed dubbed video to a chosen destination."""
        if not self.last_dubbed_video or not os.path.exists(self.last_dubbed_video):
            messagebox.showwarning(
                "Notice",
                "No dubbed video ready to save.\n\n"
                "Please click 'Start Dubbing' to generate a dubbed video preview first!"
            )
            return

        default_name = f"{self.last_video_basename}_dubbed_{self.last_voice_tag}.mp4"
        save_dest = filedialog.asksaveasfilename(
            title="Save Dubbed Video",
            initialdir=self.output_folder,
            initialfile=default_name,
            filetypes=[
                ("MP4 Video", "*.mp4"),
                ("MKV Video", "*.mkv"),
                ("All Files", "*.*")
            ],
            defaultextension=".mp4"
        )
        if not save_dest:
            return

        try:
            # 1. Copy dubbed video to chosen location
            shutil.copy2(self.last_dubbed_video, save_dest)
            dest_dir = os.path.dirname(os.path.abspath(save_dest))
            dest_base = os.path.splitext(os.path.basename(save_dest))[0]
            self.output_folder = dest_dir

            # 2. Also save Khmer subtitles alongside video if available
            saved_extra = []
            if self.last_dubbed_srt and os.path.exists(self.last_dubbed_srt):
                srt_dest = os.path.join(dest_dir, f"{dest_base}_khmer.srt")
                shutil.copy2(self.last_dubbed_srt, srt_dest)
                saved_extra.append(f"📝 Subtitles: {os.path.basename(srt_dest)}")

            # 3. Also save Khmer audio track alongside video if available
            if self.last_dubbed_audio and os.path.exists(self.last_dubbed_audio):
                ext = os.path.splitext(self.last_dubbed_audio)[1] or ".mp3"
                audio_dest = os.path.join(dest_dir, f"{dest_base}_khmer{ext}")
                shutil.copy2(self.last_dubbed_audio, audio_dest)
                saved_extra.append(f"🔊 Audio: {os.path.basename(audio_dest)}")

            self.status_var.set(f"Saved: {os.path.basename(save_dest)}")
            extra_msg = ("\n" + "\n".join(saved_extra)) if saved_extra else ""
            messagebox.showinfo(
                "Saved Successfully! 🎉",
                f"Dubbed video was successfully saved to:\n\n{save_dest}\n{extra_msg}"
            )
        except Exception as exc:
            messagebox.showerror(
                "Save Error",
                f"Failed to save video:\n{exc}"
            )

    def cancel_processing(self):
        """Action: Cancel or stop currently running dubbing processing."""
        if not self.is_processing:
            return

        self.status_var.set("Cancelling dubbing...")
        self._cancel_event.set()
        self.btn_cancel.set_text("Stopping...")
        self.btn_cancel.set_state(tk.DISABLED)

    def browse_output_folder(self):
        """Action 2 (Browse): Select destination folder where outputs will be stored."""
        selected_dir = filedialog.askdirectory(
            title="Select Output Folder",
            initialdir=self.output_folder
        )
        if selected_dir:
            self.output_folder = selected_dir
            self.status_var.set("Ready")

    def _update_voice_ui(self):
        """Synchronize voice selection buttons, indicators, and colors."""
        if self.voice_type == "Woman":
            self.btn_voice_toggle.set_text("Voice: Woman")
            self.btn_voice_toggle.set_colors("#db2777", "#be185d")
            self.btn_voice_sample.set_text("Sample: Edge TTS (F)")
            self.btn_voice_sample.set_colors("#94a3b8", "#64748b")
        elif self.voice_type == "Clone":
            self.btn_voice_toggle.set_text("Voice: Clone (VoxCPM 2)")
            self.btn_voice_toggle.set_colors("#7c3aed", "#6d28d9")
            sample_name = os.path.basename(self.custom_reference_audio) if self.custom_reference_audio else "Video Audio"
            if len(sample_name) > 16:
                sample_name = sample_name[:13] + "..."
            self.btn_voice_sample.set_text(f"Sample: {sample_name}")
            self.btn_voice_sample.set_colors("#0d9488", "#0f766e")
        else:
            self.voice_type = "Man"
            self.btn_voice_toggle.set_text("Voice: Man")
            self.btn_voice_toggle.set_colors("#ea580c", "#c2410c")
            self.btn_voice_sample.set_text("Sample: Edge TTS (M)")
            self.btn_voice_sample.set_colors("#94a3b8", "#64748b")

    def toggle_voice(self):
        """Action 4 (Voice): Cycle between Man, Woman, and Clone (VoxCPM 2)."""
        if self.voice_type == "Man":
            self.voice_type = "Woman"
        elif self.voice_type == "Woman":
            self.voice_type = "Clone"
        else:
            self.voice_type = "Man"
        self._update_voice_ui()

    def on_voice_sample_clicked(self):
        """Action 4b: Handle click on Voice Sample button (instant audio preview)."""
        if self.voice_type == "Clone":
            if self.custom_reference_audio and os.path.exists(self.custom_reference_audio):
                self.status_var.set(f"Playing Clone Sample: {os.path.basename(self.custom_reference_audio)} 🔊")
                self.sample_player.play(self.custom_reference_audio)
            elif self.video_path_var.get() and os.path.exists(self.video_path_var.get()):
                base_name = os.path.splitext(os.path.basename(self.video_path_var.get()))[0]
                preview_dir = os.path.join(self.engine.temp_dir, "dubbing_preview")
                ref_p = os.path.join(preview_dir, f"{base_name}_speaker_sample.wav")
                if not (os.path.exists(ref_p) and os.path.getsize(ref_p) > 1000):
                    self.status_var.set("Extracting speaker audio from video...")
                    self.voxcpm_engine.extract_reference_clip(self.video_path_var.get(), ref_p, start_sec=1.0, duration_sec=5.0)
                if os.path.exists(ref_p) and os.path.getsize(ref_p) > 1000:
                    self.status_var.set("Playing Video Speaker Sample 🔊")
                    self.sample_player.play(ref_p)
                else:
                    self.configure_clone_sample()
            else:
                self.configure_clone_sample()
        else:
            self.preview_current_voice_sample()

    def preview_current_voice_sample(self):
        """Play a fast, high-quality audio preview of the selected Khmer voice (Man / Woman)."""
        sample_path = os.path.join(self.engine.temp_dir, f"sample_{self.voice_type.lower()}.mp3")

        def _play():
            try:
                if not os.path.exists(sample_path) or os.path.getsize(sample_path) < 100:
                    self.status_var.set(f"Generating {self.voice_type} voice sample...")
                    sample_text = "សួស្តីបងប្អូន នេះជាសំឡេងនិយាយភាសាខ្មែរ"
                    self.dubbing_engine.synthesize_single_line(sample_text, self.voice_type, sample_path)

                if os.path.exists(sample_path) and os.path.getsize(sample_path) > 100:
                    self.status_var.set(f"Playing {self.voice_type} voice sample 🔊")
                    self.sample_player.play(sample_path)
            except Exception as e:
                self.status_var.set(f"Preview notice: {e}")

        threading.Thread(target=_play, daemon=True).start()

    def configure_clone_sample(self):
        """Configure reference voice sample for VoxCPM 2 cloning."""
        prev_voice = self.voice_type
        if self.voice_type != "Clone":
            self.voice_type = "Clone"
            self._update_voice_ui()

        choice = messagebox.askyesnocancel(
            "VoxCPM 2 Voice Clone Reference",
            "Configure Voice Sample for VoxCPM 2 Cloning:\n\n"
            "• Click YES: Select ANY reference audio or video file (.ogg, .opus, .mp3, .wav, .m4a, .mp4, etc.)\n"
            "  The AI will analyze the person's speech and clone their voice for the dubbing!\n\n"
            "• Click NO: Use speaker voice automatically extracted from the loaded video\n"
            "• Click CANCEL: Keep current setting"
        )
        if choice is True:
            filetypes = [
                ("Media Files (Audio & Video)", "*.ogg *.opus *.mp3 *.wav *.m4a *.aac *.flac *.mp4 *.mov *.mkv *.webm *.avi"),
                ("Audio Files", "*.ogg *.opus *.mp3 *.wav *.m4a *.aac *.flac"),
                ("Video Files", "*.mp4 *.mov *.mkv *.webm *.avi"),
                ("All Files", "*.*")
            ]
            selected = filedialog.askopenfilename(
                title="Select Reference Speaker Sample (.ogg, .mp3, .wav, .mp4)",
                filetypes=filetypes
            )
            if selected and os.path.exists(selected):
                self.custom_reference_audio = selected
                short_name = os.path.basename(selected)
                if len(short_name) > 16:
                    short_name = short_name[:13] + "..."
                self.btn_voice_sample.set_text(f"Sample: {short_name}")
                self.btn_voice_sample.set_colors("#0d9488", "#0f766e")
                self.status_var.set(f"Cloned Voice Reference: {os.path.basename(selected)}")
            elif not self.custom_reference_audio:
                if prev_voice != "Clone":
                    self.voice_type = prev_voice
                    self._update_voice_ui()
        elif choice is False:
            self.custom_reference_audio = None
            self.btn_voice_sample.set_text("Sample: Video Audio")
            self.btn_voice_sample.set_colors("#0d9488", "#0f766e")
            self.status_var.set("Voice Clone Reference: Loaded Video Audio")
        else:
            if prev_voice != "Clone":
                self.voice_type = prev_voice
                self._update_voice_ui()

    def start_dubbing(self):
        """Action 5 (Start): Start dubbing to preview. Does not auto-save to output folder."""
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
        self._cancel_event.clear()
        self._set_controls_state("processing")

        self.progress_bar.set_progress(0)
        self.percent_label.config(text="0%")
        self.status_var.set("Starting dubbing...")

        # Preview working directory in temp (NO auto-save to permanent folder)
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        voice_tag = "cloned" if "clone" in self.voice_type.lower() else self.voice_type.lower()
        preview_dir = os.path.join(self.engine.temp_dir, "dubbing_preview")
        os.makedirs(preview_dir, exist_ok=True)

        preview_video_path = os.path.join(preview_dir, f"{base_name}_preview_{voice_tag}.mp4")
        preview_srt_path = os.path.join(preview_dir, f"{base_name}_khmer.srt")
        preview_audio_path = os.path.join(preview_dir, f"{base_name}_khmer_{voice_tag}.mp3")
        preview_txt_path = os.path.join(preview_dir, f"{base_name}_khmer.txt")
        source_srt_path = os.path.join(preview_dir, f"{base_name}_subtitles.srt")

        thread = threading.Thread(
            target=self._dubbing_worker,
            args=(
                filepath,
                self.voice_type,
                preview_dir,
                preview_video_path,
                preview_srt_path,
                preview_audio_path,
                preview_txt_path,
                source_srt_path
            ),
            daemon=True
        )
        thread.start()

    def _dubbing_worker(
        self,
        filepath,
        voice,
        preview_dir,
        preview_video_path,
        preview_srt_path,
        preview_audio_path,
        preview_txt_path,
        source_srt_path
    ):
        """Worker thread executing end-to-end Khmer dubbing pipeline with cancellation and preview review."""
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        voice_tag = "cloned" if "clone" in voice.lower() else voice.lower()

        def cancel_check():
            return self._cancel_event.is_set()

        def on_progress(msg, pct):
            if cancel_check():
                raise InterruptedError("Dubbing cancelled by user.")
            self.update_progress_safe(msg, pct)

        try:
            if cancel_check():
                raise InterruptedError("Dubbing cancelled by user.")

            # Step 1: Ensure source script is extracted and contains valid content
            needs_extraction = True
            if os.path.exists(source_srt_path):
                try:
                    from src.core.dubbing_engine import parse_srt_file
                    parsed_test = parse_srt_file(source_srt_path)
                    if parsed_test and any(
                        p.text and len(p.text.strip()) > 1 and not (p.text.strip().startswith("[") and p.text.strip().endswith("]"))
                        for p in parsed_test
                    ):
                        # Detect if the existing SRT was created with coarse 5s/7s sliding windows from SpeechRecognition
                        is_coarse_chunked = len(parsed_test) >= 2 and all((s.end - s.start) in (5.0, 7.0) for s in parsed_test[:4])
                        if is_coarse_chunked and self.script_extractor.get_available_engine() in ("openai-whisper", "faster-whisper"):
                            needs_extraction = True
                        else:
                            needs_extraction = False
                except Exception:
                    needs_extraction = True

            if needs_extraction:
                if os.path.exists(preview_srt_path):
                    try:
                        os.remove(preview_srt_path)
                    except Exception:
                        pass
                if os.path.exists(preview_txt_path):
                    try:
                        os.remove(preview_txt_path)
                    except Exception:
                        pass
                self.update_progress_safe("Step 1/4: Extracting spoken script with high-precision Whisper...", 10)
                self.script_extractor.extract_script_to_srt(
                    video_path=filepath,
                    output_srt_path=source_srt_path,
                    on_progress=lambda m, p: on_progress(f"Step 1/4: {m}", min(25, int(p * 0.25))),
                    cancel_check=cancel_check
                )

            if cancel_check():
                raise InterruptedError("Dubbing cancelled by user.")

            # Step 2: Translate script to Khmer
            self.update_progress_safe("Step 2/4: Translating subtitles to Khmer...", 30)
            khmer_segments, full_khmer_script = self.dubbing_engine.translate_script(
                source_srt_path=source_srt_path,
                output_khmer_srt=preview_srt_path,
                output_khmer_txt=preview_txt_path,
                on_progress=on_progress,
                cancel_check=cancel_check
            )

            if cancel_check():
                raise InterruptedError("Dubbing cancelled by user.")

            # If existing SRT on disk was empty or stale, re-extract fresh script
            if not full_khmer_script or not full_khmer_script.strip():
                self.update_progress_safe("Re-extracting fresh subtitles...", 15)
                self.script_extractor.extract_script_to_srt(
                    video_path=filepath,
                    output_srt_path=source_srt_path,
                    on_progress=lambda m, p: on_progress(f"Step 1/4: {m}", min(25, int(p * 0.25))),
                    cancel_check=cancel_check
                )
                if cancel_check():
                    raise InterruptedError("Dubbing cancelled by user.")
                khmer_segments, full_khmer_script = self.dubbing_engine.translate_script(
                    source_srt_path=source_srt_path,
                    output_khmer_srt=preview_srt_path,
                    output_khmer_txt=preview_txt_path,
                    on_progress=on_progress,
                    cancel_check=cancel_check
                )

            if not full_khmer_script or not full_khmer_script.strip():
                raise RuntimeError("No dialogue or speech could be recognized from the video to dub! Please make sure the video has audible speech.")

            if cancel_check():
                raise InterruptedError("Dubbing cancelled by user.")

            # Probe exact video duration for precision timeline alignment
            meta = self.engine.probe_video_metadata(filepath)
            video_duration = meta.get("duration", 0.0)

            # If Voice Cloning is selected, ensure reference voice sample is ready
            ref_sample_path = None
            is_clone = "clone" in voice.lower()
            if is_clone:
                if self.custom_reference_audio and os.path.exists(self.custom_reference_audio):
                    ext = os.path.splitext(self.custom_reference_audio)[1].lower()
                    if ext in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac"):
                        ref_sample_path = os.path.join(preview_dir, f"{base_name}_custom_speaker_sample.wav")
                        if not (os.path.exists(ref_sample_path) and os.path.getsize(ref_sample_path) > 1000):
                            self.voxcpm_engine.extract_reference_clip(
                                video_or_audio_path=self.custom_reference_audio,
                                output_wav_path=ref_sample_path,
                                start_sec=0.0,
                                duration_sec=6.0,
                                cancel_check=cancel_check
                            )
                    else:
                        ref_sample_path = self.custom_reference_audio
                else:
                    ref_sample_path = os.path.join(preview_dir, f"{base_name}_speaker_sample.wav")
                    if not (os.path.exists(ref_sample_path) and os.path.getsize(ref_sample_path) > 1000):
                        self.update_progress_safe("Step 2.5/4: Extracting speaker sample from video for VoxCPM 2...", 45)
                        start_s = khmer_segments[0].start if khmer_segments else 1.0
                        self.voxcpm_engine.extract_reference_clip(
                            video_or_audio_path=filepath,
                            output_wav_path=ref_sample_path,
                            start_sec=start_s,
                            duration_sec=6.0,
                            cancel_check=cancel_check
                        )

                if cancel_check():
                    raise InterruptedError("Dubbing cancelled by user.")

                # Pre-initialize VoxCPM 2 model on GPU if not already loaded
                if self.voxcpm_engine._model is None and self.voxcpm_engine.is_available:
                    self.update_progress_safe("Step 2.8/4: Initializing VoxCPM 2 AI on RTX 5050 GPU...", 48)
                    self.voxcpm_engine.load_model()

            if cancel_check():
                raise InterruptedError("Dubbing cancelled by user.")

            # Step 3: Synthesize authentic Khmer voiceover SYNCHRONIZED IN REALTIME with video speech
            v_desc = "VoxCPM 2 Cloned" if is_clone else voice
            self.update_progress_safe(f"Step 3/4: Generating realtime Khmer {v_desc} voice synced to video speech...", 50)
            generated_audio = self.dubbing_engine.generate_timed_voice(
                khmer_segments=khmer_segments,
                voice_type=voice,
                total_video_duration=video_duration,
                output_audio_path=preview_audio_path,
                reference_audio_path=ref_sample_path,
                on_progress=on_progress,
                cancel_check=cancel_check
            )

            if cancel_check():
                raise InterruptedError("Dubbing cancelled by user.")

            # Step 4: Merge Khmer voice into video and REMOVE 100% of the original sound
            self.update_progress_safe("Step 4/4: Replacing original audio with pure Khmer voice...", 85)
            self.dubbing_engine.merge_video(
                video_path=filepath,
                audio_path=generated_audio,
                output_video_path=preview_video_path,
                remove_original_sound=True,
                background_volume=0.0,
                on_progress=on_progress,
                cancel_check=cancel_check
            )

            if cancel_check():
                raise InterruptedError("Dubbing cancelled by user.")

            # Save preview references (NOT auto-saved into user's output directory!)
            self.last_dubbed_video = preview_video_path
            self.last_dubbed_srt = preview_srt_path
            self.last_dubbed_audio = generated_audio
            self.last_video_basename = base_name
            self.last_voice_tag = voice_tag

            self.update_progress_safe("Dubbing Complete! Ready for review 🎉", 100)

            # Prompt success with details and auto-load dubbed video for instant preview review
            def _on_success():
                try:
                    self.player_view.load_video(preview_video_path)
                    self.video_path_var.set(preview_video_path)
                except Exception:
                    pass

                self.btn_save.set_state(tk.NORMAL)
                self.btn_save.set_colors("#059669", "#047857")
                self.status_var.set("Dubbing ready for review! Click Play to watch, then click 'Save Video' to save.")

                desc = "VoxCPM 2 Cloned Voice" if is_clone else f"{voice} voice"
                sample_info = f"\n🎙️ Speaker Reference Clip:\n{ref_sample_path}\n" if is_clone and ref_sample_path else ""
                messagebox.showinfo(
                    "Dubbing Ready for Review! 🎉",
                    f"Video successfully dubbed in Khmer ({desc})!\n\n"
                    f"🎬 The dubbed video is now loaded in the player.\n"
                    f"▶ Click Play to review the video and listen to the dubbed voice.\n"
                    f"{sample_info}\n"
                    f"💾 It is NOT auto-saved yet! When you are satisfied, click 'Save Video' to save it to your computer."
                )

            self.run_on_ui_thread(_on_success)
        except InterruptedError:
            self.update_progress_safe("Dubbing was cancelled.", 0)
            def _on_cancelled():
                self.status_var.set("Dubbing was cancelled by user.")
                # Clean up incomplete preview files
                for f in (preview_video_path, preview_audio_path):
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except Exception:
                            pass
            self.run_on_ui_thread(_on_cancelled)
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
