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
from tkinter import filedialog, messagebox, scrolledtext
import re
import webbrowser
# Ensure src is in Python path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

BIN_DIR = os.path.join(APP_DIR, "bin")
if os.path.exists(BIN_DIR) and BIN_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")

from src.ui import (
    RoundedCard, RoundedButton, RoundedProgressBar, SectionHeader,
    YouTubePlayerView, draw_icon
)
from src.core import (
    VideoEngine, ScriptExtractor, DubbingEngine, VoxCPMEngine, WindowsAudioPlayer,
    VideoDownloader, clean_video_url, is_hongguo_url, extract_hongguo_ids
)
from src.core.dubbing_engine import (
    get_saved_gemini_api_key, save_gemini_api_key,
    format_gemini_drama_prompt, parse_gemini_translations, parse_srt_file
)


class VideoTranslateApp(tk.Tk):
    """Main Application Controller for Video Translate & Subtitle Studio."""

    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("AI Video Dubbing Studio - Khmer Edition")
        self.geometry("980x620")
        self.minsize(880, 540)
        self.aspect(14, 10, 18, 10)
        self.configure(bg="#0b0f19")

        # Core Engines
        self.engine = VideoEngine(base_dir=APP_DIR)
        self.downloader = VideoDownloader(download_dir=os.path.join(self.engine.temp_dir, "downloads"))
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
        self.blur_subtitles_var = tk.BooleanVar(value=True)
        self.anti_duplicate_var = tk.BooleanVar(value=True)
        self.bg_mode_var = tk.StringVar(value="clean_bg")  # "clean_bg" | "all_bg" | "muted"
        self.keep_bg_audio_var = tk.BooleanVar(value=True)
        self.funny_script_var = tk.BooleanVar(value=False)
        self.translator_mode_var = tk.StringVar(value="gemini_browser")  # "gemini_browser" | "google" | "gemini_api"
        self.gemini_api_key_var = tk.StringVar(value=get_saved_gemini_api_key())
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
        """Construct pro studio layout with top header bar, left video preview, and right grouped controls."""

        # ==========================================
        # TOP APP BAR: Logo, Title, Engine Badges, Output Path
        # ==========================================
        top_bar = tk.Frame(self, bg="#0b0f19", bd=0, highlightthickness=0)
        top_bar.pack(fill=tk.X, padx=16, pady=(10, 4))

        # Left branding
        brand_frame = tk.Frame(top_bar, bg="#0b0f19")
        brand_frame.pack(side=tk.LEFT)

        app_icon_canvas = tk.Canvas(brand_frame, width=22, height=22, bg="#0b0f19", highlightthickness=0, bd=0)
        app_icon_canvas.pack(side=tk.LEFT, padx=(0, 8))
        draw_icon(app_icon_canvas, "film", 11, 11, size=18, color="#38bdf8", width=2)

        lbl_app_name = tk.Label(
            brand_frame,
            text="AI VIDEO DUBBING STUDIO",
            bg="#0b0f19",
            fg="#f8fafc",
            font=("Segoe UI", 11, "bold")
        )
        lbl_app_name.pack(side=tk.LEFT, padx=(0, 10))

        badge_frame = tk.Frame(brand_frame, bg="#1e293b", padx=8, pady=2)
        badge_frame.pack(side=tk.LEFT)
        lbl_badge_text = tk.Label(
            badge_frame,
            text="KHMER AI DUBBING PRO",
            bg="#1e293b",
            fg="#10b981",
            font=("Segoe UI", 7, "bold")
        )
        lbl_badge_text.pack()

        # Right output folder indicator button
        folder_display_name = os.path.basename(self.output_folder) or self.output_folder
        if len(folder_display_name) > 22:
            folder_display_name = folder_display_name[:19] + "..."

        self.btn_folder_pill = RoundedButton(
            top_bar,
            text=f"Output: {folder_display_name}",
            icon="folder",
            icon_size=12,
            icon_color="#38bdf8",
            command=self.browse_output_folder,
            bg_color="#1e293b",
            hover_color="#334155",
            text_color="#cbd5e1",
            border_color="#334155",
            radius=8,
            height=26,
            font=("Segoe UI", 8)
        )
        self.btn_folder_pill.pack(side=tk.RIGHT)

        # ==========================================
        # MAIN CONTENT FRAME: 2 Columns
        # ==========================================
        content_frame = tk.Frame(self, bg="#0b0f19", bd=0, highlightthickness=0)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=6)

        # ==========================================
        # LEFT COLUMN: Rounded Card for Unified Video Player
        # ==========================================
        self.left_card = RoundedCard(
            content_frame,
            bg_color="#1e293b",
            border_color="#334155",
            radius=14
        )
        self.left_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        # Preview Header
        preview_header_frame = tk.Frame(self.left_card.container, bg="#1e293b")
        preview_header_frame.pack(fill=tk.X, pady=(0, 6))

        ph_icon_canvas = tk.Canvas(preview_header_frame, width=16, height=16, bg="#1e293b", highlightthickness=0)
        ph_icon_canvas.pack(side=tk.LEFT, padx=(0, 6))
        draw_icon(ph_icon_canvas, "video", 8, 8, size=14, color="#38bdf8", width=1.5)

        lbl_pv_title = tk.Label(
            preview_header_frame,
            text="Video Preview",
            bg="#1e293b",
            fg="#f8fafc",
            font=("Segoe UI", 10, "bold")
        )
        lbl_pv_title.pack(side=tk.LEFT)

        self.lbl_video_name = tk.Label(
            preview_header_frame,
            text="No Video Loaded",
            bg="#1e293b",
            fg="#64748b",
            font=("Segoe UI", 8)
        )
        self.lbl_video_name.pack(side=tk.RIGHT)

        # Unified YouTube Video Player Screen
        self.player_view = YouTubePlayerView(
            self.left_card.container,
            on_status_change=lambda msg: self.status_var.set(msg),
            radius=10,
            card_bg="#1e293b",
            border_color="#334155",
            screen_bg="#020617",
            controls_fg="#f8fafc"
        )
        self.player_view.pack(fill=tk.BOTH, expand=True)

        # ==========================================
        # RIGHT COLUMN: Rounded Card for Grouped Controls
        # ==========================================
        self.right_card = RoundedCard(
            content_frame,
            bg_color="#1e293b",
            border_color="#334155",
            radius=14,
            width=280
        )
        self.right_card.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_card.pack_propagate(False)

        ctrl_container = self.right_card.container

        # Group 1: Media Import
        SectionHeader(ctrl_container, title="Media Import", icon="upload", fg_color="#94a3b8", line_color="#334155").pack(fill=tk.X, pady=(0, 4))

        self.btn_load = RoundedButton(
            ctrl_container,
            text="Load Video File",
            icon="upload",
            command=self.load_video,
            bg_color="#2563eb",
            hover_color="#1d4ed8",
            text_color="#ffffff",
            radius=10,
            height=34,
            font=("Segoe UI", 9, "bold")
        )
        self.btn_load.pack(fill=tk.X, pady=(0, 6))

        self.btn_download = RoundedButton(
            ctrl_container,
            text="Download Video (Hongguo/URL)",
            icon="download",
            command=self.open_download_dialog,
            bg_color="#e11d48",
            hover_color="#be123c",
            text_color="#ffffff",
            radius=10,
            height=34,
            font=("Segoe UI", 8, "bold")
        )
        self.btn_download.pack(fill=tk.X, pady=(0, 10))

        # Group 2: AI Dubbing Configuration
        SectionHeader(ctrl_container, title="AI Dubbing Config", icon="settings", fg_color="#94a3b8", line_color="#334155").pack(fill=tk.X, pady=(0, 4))

        self.btn_voice_toggle = RoundedButton(
            ctrl_container,
            text="Voice: Man",
            icon="man",
            command=self.toggle_voice,
            bg_color="#ea580c",
            hover_color="#c2410c",
            text_color="#ffffff",
            radius=10,
            height=32,
            font=("Segoe UI", 9, "bold")
        )
        self.btn_voice_toggle.pack(fill=tk.X, pady=(0, 5))

        self.btn_funny_toggle = RoundedButton(
            ctrl_container,
            text="Script Style: Normal",
            icon="subtitles",
            command=self.toggle_script_style,
            bg_color="#0d9488",
            hover_color="#0f766e",
            text_color="#ffffff",
            radius=10,
            height=32,
            font=("Segoe UI", 9, "bold")
        )
        self.btn_funny_toggle.pack(fill=tk.X, pady=(0, 5))

        self.btn_translator_toggle = RoundedButton(
            ctrl_container,
            text="AI Translator: Gemini Web (Auto Browser)",
            icon="sparkles",
            command=self.toggle_translator_mode,
            bg_color="#059669",
            hover_color="#047857",
            text_color="#ffffff",
            radius=10,
            height=32,
            font=("Segoe UI", 8, "bold")
        )
        self.btn_translator_toggle.pack(fill=tk.X, pady=(0, 5))

        self.btn_bg_toggle = RoundedButton(
            ctrl_container,
            text="Original Audio: Clean BG (No Voice)",
            icon="volume",
            command=self.toggle_bg_audio,
            bg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            radius=10,
            height=32,
            font=("Segoe UI", 8, "bold")
        )
        self.btn_bg_toggle.pack(fill=tk.X, pady=(0, 5))

        self.btn_blur_toggle = RoundedButton(
            ctrl_container,
            text="Blur Subtitles: ON",
            icon="subtitles",
            command=self.toggle_blur_subtitles,
            bg_color="#7c3aed",
            hover_color="#6d28d9",
            text_color="#ffffff",
            radius=10,
            height=32,
            font=("Segoe UI", 9, "bold")
        )
        self.btn_blur_toggle.pack(fill=tk.X, pady=(0, 5))

        self.btn_anti_dup_toggle = RoundedButton(
            ctrl_container,
            text="TikTok FYP Bypass: ON",
            icon="sparkles",
            command=self.toggle_anti_duplicate,
            bg_color="#059669",
            hover_color="#047857",
            text_color="#ffffff",
            radius=10,
            height=32,
            font=("Segoe UI", 8, "bold")
        )
        self.btn_anti_dup_toggle.pack(fill=tk.X, pady=(0, 5))

        self.btn_voice_sample = RoundedButton(
            ctrl_container,
            text="Sample: Edge TTS (M)",
            icon="wave",
            command=self.on_voice_sample_clicked,
            bg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            border_color="#334155",
            radius=10,
            height=28,
            font=("Segoe UI", 8)
        )
        self.btn_voice_sample.pack(fill=tk.X, pady=(0, 8))
        self.btn_voice_sample.bind("<Button-3>", lambda e: self.configure_clone_sample())

        # Group 3: Output & Export
        SectionHeader(ctrl_container, title="Export & Output", icon="folder", fg_color="#94a3b8", line_color="#334155").pack(fill=tk.X, pady=(0, 4))

        self.btn_save = RoundedButton(
            ctrl_container,
            text="Save Dubbed Video",
            icon="save",
            command=self.save_video,
            bg_color="#059669",
            hover_color="#047857",
            text_color="#ffffff",
            radius=10,
            height=34,
            font=("Segoe UI", 9, "bold")
        )
        self.btn_save.pack(fill=tk.X, pady=(0, 6))
        self.btn_save.set_state(tk.DISABLED)

        self.btn_browse = RoundedButton(
            ctrl_container,
            text="Change Output Folder",
            icon="folder",
            command=self.browse_output_folder,
            bg_color="#1e293b",
            hover_color="#334155",
            text_color="#94a3b8",
            border_color="#334155",
            radius=10,
            height=30,
            font=("Segoe UI", 8)
        )
        self.btn_browse.pack(fill=tk.X, pady=(0, 10))

        # Bottom Actions Frame
        self.btn_cancel = RoundedButton(
            ctrl_container,
            text="Stop Processing",
            icon="stop",
            command=self.cancel_processing,
            bg_color="#dc2626",
            hover_color="#b91c1c",
            text_color="#ffffff",
            radius=10,
            height=34,
            font=("Segoe UI", 9, "bold")
        )
        self.btn_cancel.pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))
        self.btn_cancel.set_state(tk.DISABLED)

        self.btn_start = RoundedButton(
            ctrl_container,
            text="Start AI Dubbing",
            icon="sparkle_play",
            icon_size=18,
            command=self.start_dubbing,
            bg_color="#10b981",
            hover_color="#059669",
            text_color="#ffffff",
            radius=10,
            height=42,
            font=("Segoe UI", 10, "bold")
        )
        self.btn_start.pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 4))

        # ==========================================
        # BOTTOM: Unified Progress Bar & Status
        # ==========================================
        bottom_frame = tk.Frame(self, bg="#0b0f19", bd=0, highlightthickness=0)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 10))

        status_box = tk.Frame(bottom_frame, bg="#0b0f19", bd=0, highlightthickness=0)
        status_box.pack(fill=tk.X, pady=(0, 4))

        # Status pulse dot canvas
        self.status_dot_canvas = tk.Canvas(status_box, width=12, height=12, bg="#0b0f19", highlightthickness=0)
        self.status_dot_canvas.pack(side=tk.LEFT, padx=(0, 6))
        draw_icon(self.status_dot_canvas, "dot", 6, 6, size=8, color="#10b981")

        self.status_label = tk.Label(
            status_box,
            textvariable=self.status_var,
            bg="#0b0f19",
            fg="#cbd5e1",
            font=("Segoe UI", 9)
        )
        self.status_label.pack(side=tk.LEFT)

        self.percent_label = tk.Label(
            status_box,
            text="0%",
            bg="#0b0f19",
            fg="#38bdf8",
            font=("Consolas", 10, "bold")
        )
        self.percent_label.pack(side=tk.RIGHT)

        # Smooth Rounded Progress Bar
        self.progress_bar = RoundedProgressBar(
            bottom_frame,
            height=10,
            trough_color="#1e293b",
            fill_color="#10b981",
            radius=5
        )
        self.progress_bar.pack(fill=tk.X)

        # Pre-warm voice samples in a background thread for instant playback
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
        if hasattr(self, "status_dot_canvas"):
            self.status_dot_canvas.delete("all")
            dot_color = "#38bdf8" if state == "processing" else "#10b981"
            draw_icon(self.status_dot_canvas, "dot", 6, 6, size=8, color=dot_color)

        if state == "processing":
            self.btn_load.set_state(tk.DISABLED)
            self.btn_download.set_state(tk.DISABLED)
            self.btn_browse.set_state(tk.DISABLED)
            self.btn_voice_toggle.set_state(tk.DISABLED)
            self.btn_funny_toggle.set_state(tk.DISABLED)
            self.btn_translator_toggle.set_state(tk.DISABLED)
            self.btn_bg_toggle.set_state(tk.DISABLED)
            self.btn_voice_sample.set_state(tk.DISABLED)
            self.btn_blur_toggle.set_state(tk.DISABLED)
            self.btn_save.set_state(tk.DISABLED)
            self.btn_start.set_state(tk.DISABLED)
            self.btn_cancel.set_state(tk.NORMAL)
            self.btn_cancel.set_text("Stop Processing")
        else:
            self.btn_load.set_state(tk.NORMAL)
            self.btn_download.set_state(tk.NORMAL)
            self.btn_browse.set_state(tk.NORMAL)
            self.btn_voice_toggle.set_state(tk.NORMAL)
            self.btn_funny_toggle.set_state(tk.NORMAL)
            self.btn_translator_toggle.set_state(tk.NORMAL)
            self.btn_bg_toggle.set_state(tk.NORMAL)
            self.btn_voice_sample.set_state(tk.NORMAL)
            self.btn_blur_toggle.set_state(tk.NORMAL)
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
    def load_video_file(self, filepath: str):
        """Load video from a filepath directly into the player view."""
        if not filepath or not os.path.exists(filepath):
            return
        self.video_path_var.set(filepath)
        self.original_video_path = filepath
        self.last_dubbed_video = None
        self.last_dubbed_srt = None
        self.last_dubbed_audio = None
        self.btn_save.set_state(tk.DISABLED)
        if hasattr(self, "lbl_video_name"):
            name = os.path.basename(filepath)
            self.lbl_video_name.config(text=name if len(name) <= 24 else name[:21] + "...", fg="#38bdf8")
        self.player_view.load_video(filepath)
        self.status_var.set("Ready")

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

        self.load_video_file(selected_file)

    def open_download_dialog(self):
        """Open modern popup dialog to download video from Hongguo / Douyin / TikTok / Web without emojis."""
        dialog = tk.Toplevel(self)
        dialog.title("Download Video & Auto-Dub")
        dialog.geometry("640x480")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg="#0b0f19")

        x = self.winfo_x() + max(20, (self.winfo_width() // 2) - 320)
        y = self.winfo_y() + max(20, (self.winfo_height() // 2) - 240)
        dialog.geometry(f"+{x}+{y}")

        pad_frame = tk.Frame(dialog, bg="#0b0f19", padx=22, pady=16)
        pad_frame.pack(fill=tk.BOTH, expand=True)

        # Header with vector icon
        dlg_hdr = tk.Frame(pad_frame, bg="#0b0f19")
        dlg_hdr.pack(fill=tk.X, pady=(0, 4))

        hdr_icon_c = tk.Canvas(dlg_hdr, width=20, height=20, bg="#0b0f19", highlightthickness=0)
        hdr_icon_c.pack(side=tk.LEFT, padx=(0, 8))
        draw_icon(hdr_icon_c, "cloud_download", 10, 10, size=16, color="#38bdf8", width=2)

        lbl_title = tk.Label(
            dlg_hdr,
            text="Download Video (Hongguo 红果短剧 / Douyin 抖音 / Web)",
            font=("Segoe UI", 11, "bold"),
            bg="#0b0f19",
            fg="#f8fafc"
        )
        lbl_title.pack(side=tk.LEFT)

        lbl_sub = tk.Label(
            pad_frame,
            text="Paste link from Hongguo (红果), Douyin (抖音), TikTok, YouTube, or direct video address:",
            font=("Segoe UI", 8),
            bg="#0b0f19",
            fg="#94a3b8"
        )
        lbl_sub.pack(anchor="w", pady=(0, 6))

        # URL Input Entry
        url_var = tk.StringVar()
        try:
            cb = self.clipboard_get().strip()
            if cb and ("http://" in cb or "https://" in cb or "hongguo" in cb or "douyin" in cb):
                url_var.set(clean_video_url(cb))
        except Exception:
            pass

        entry_frame = tk.Frame(pad_frame, bg="#1e293b", highlightbackground="#334155", highlightthickness=1)
        entry_frame.pack(fill=tk.X, pady=(0, 8))
        entry = tk.Entry(
            entry_frame,
            textvariable=url_var,
            font=("Segoe UI", 10),
            relief="flat",
            bg="#1e293b",
            fg="#f8fafc",
            insertbackground="#38bdf8"
        )
        entry.pack(fill=tk.X, padx=10, pady=7)
        entry.focus_set()

        # Dynamic Hongguo Episode Selector Card (No emojis!)
        hg_card = tk.Frame(pad_frame, bg="#1e293b", highlightbackground="#d97706", highlightthickness=1, padx=12, pady=8)

        hg_header_row = tk.Frame(hg_card, bg="#1e293b")
        hg_header_row.pack(fill=tk.X)

        hg_ic_canvas = tk.Canvas(hg_header_row, width=16, height=16, bg="#1e293b", highlightthickness=0)
        hg_ic_canvas.pack(side=tk.LEFT, padx=(0, 6))
        draw_icon(hg_ic_canvas, "film", 8, 8, size=14, color="#f59e0b", width=2)

        lbl_hg_header = tk.Label(
            hg_header_row,
            text="HONGGUO SHORT DRAMA (红果短剧)",
            font=("Segoe UI", 8, "bold"),
            bg="#1e293b",
            fg="#fbbf24"
        )
        lbl_hg_header.pack(side=tk.LEFT)

        lbl_hg_info = tk.Label(
            hg_card,
            text="Detecting drama metadata...",
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#cbd5e1",
            wraplength=570,
            justify=tk.LEFT
        )
        lbl_hg_info.pack(anchor="w", pady=(2, 6))

        hg_ctrl_row = tk.Frame(hg_card, bg="#1e293b")
        hg_ctrl_row.pack(fill=tk.X)

        tk.Label(
            hg_ctrl_row,
            text="Episode Number:",
            font=("Segoe UI", 9, "bold"),
            bg="#1e293b",
            fg="#e2e8f0"
        ).pack(side=tk.LEFT, padx=(0, 8))

        episode_var = tk.IntVar(value=1)
        spn_ep = tk.Spinbox(
            hg_ctrl_row,
            from_=1,
            to=250,
            textvariable=episode_var,
            width=5,
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#f8fafc",
            buttonbackground="#334155",
            relief="flat",
            justify=tk.CENTER
        )
        spn_ep.pack(side=tk.LEFT, padx=(0, 8))

        # Vector badge canvas for free/locked state
        badge_canvas = tk.Canvas(hg_ctrl_row, width=190, height=24, bg="#1e293b", highlightthickness=0)
        badge_canvas.pack(side=tk.LEFT, padx=(0, 8))

        def _step_ep(delta: int):
            try:
                curr = episode_var.get()
                max_ep = int(spn_ep.cget("to"))
                new_v = max(1, min(max_ep, curr + delta))
                episode_var.set(new_v)
            except Exception:
                pass

        btn_prev = RoundedButton(
            hg_ctrl_row,
            text="Prev Ep",
            icon="chevron_left",
            icon_size=10,
            command=lambda: _step_ep(-1),
            bg_color="#334155",
            hover_color="#475569",
            text_color="#f8fafc",
            radius=6,
            height=26,
            width=76,
            font=("Segoe UI", 8, "bold")
        )
        btn_prev.pack(side=tk.LEFT, padx=(0, 4))

        btn_next = RoundedButton(
            hg_ctrl_row,
            text="Next Ep",
            icon="chevron_right",
            icon_size=10,
            command=lambda: _step_ep(1),
            bg_color="#334155",
            hover_color="#475569",
            text_color="#f8fafc",
            radius=6,
            height=26,
            width=76,
            font=("Segoe UI", 8, "bold")
        )
        btn_next.pack(side=tk.LEFT)

        # Douyin Tip Banner (No emojis!)
        tip_frame = tk.Frame(pad_frame, bg="#1e293b", highlightbackground="#3b82f6", highlightthickness=1, padx=10, pady=6)
        tip_row = tk.Frame(tip_frame, bg="#1e293b")
        tip_row.pack(fill=tk.X)
        tip_ic_c = tk.Canvas(tip_row, width=16, height=16, bg="#1e293b", highlightthickness=0)
        tip_ic_c.pack(side=tk.LEFT, padx=(0, 6))
        draw_icon(tip_ic_c, "info", 8, 8, size=14, color="#38bdf8", width=1.5)
        lbl_tip = tk.Label(
            tip_row,
            text="Tip: In Chrome, right-click the playing video -> 'Copy video address' and paste here for direct download.",
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#94a3b8",
            justify=tk.LEFT
        )
        lbl_tip.pack(side=tk.LEFT)

        # Cookies File Row
        cookie_var = tk.StringVar()
        default_cookie = self.downloader.find_cookie_file()
        if default_cookie:
            cookie_var.set(default_cookie)

        cookie_row = tk.Frame(pad_frame, bg="#0b0f19")
        cookie_row.pack(fill=tk.X, pady=(8, 4))

        lbl_cookie = tk.Label(
            cookie_row,
            text="Cookies File (Required for Hongguo Locked Episodes 6+ / VIP):",
            font=("Segoe UI", 8, "bold"),
            bg="#0b0f19",
            fg="#cbd5e1"
        )
        lbl_cookie.pack(anchor="w", pady=(0, 2))

        cookie_entry_box = tk.Frame(cookie_row, bg="#1e293b", highlightbackground="#334155", highlightthickness=1)
        cookie_entry_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        entry_cookie = tk.Entry(
            cookie_entry_box,
            textvariable=cookie_var,
            font=("Segoe UI", 8),
            relief="flat",
            bg="#1e293b",
            fg="#f8fafc",
            insertbackground="#38bdf8"
        )
        entry_cookie.pack(fill=tk.X, padx=8, pady=4)

        def _browse_cookie():
            fpath = filedialog.askopenfilename(
                title="Select Cookies File (cookies.txt)",
                parent=dialog,
                filetypes=[("Cookie Files", "*.txt"), ("All Files", "*.*")]
            )
            if fpath:
                cookie_var.set(fpath)

        btn_browse_cookie = RoundedButton(
            cookie_row,
            text="Browse...",
            icon="folder",
            icon_size=12,
            command=_browse_cookie,
            bg_color="#334155",
            hover_color="#475569",
            text_color="#f8fafc",
            radius=6,
            height=28,
            width=90,
            font=("Segoe UI", 8, "bold")
        )
        btn_browse_cookie.pack(side=tk.RIGHT)

        lbl_cookie_hint = tk.Label(
            pad_frame,
            text="Export cookies from Chrome using 'Get cookies.txt LOCALLY' extension to download locked episodes.",
            font=("Segoe UI", 7),
            bg="#0b0f19",
            fg="#64748b"
        )
        lbl_cookie_hint.pack(anchor="w", pady=(0, 8))

        # Checkbox: Auto-dub immediately after download
        auto_dub_var = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(
            pad_frame,
            text="Auto-start Khmer dubbing immediately after download (One-Click)",
            variable=auto_dub_var,
            font=("Segoe UI", 9, "bold"),
            bg="#0b0f19",
            fg="#10b981",
            activebackground="#0b0f19",
            selectcolor="#1e293b"
        )
        chk.pack(anchor="w", pady=(0, 10))

        # Series metadata state
        current_hg_info = {"accessible_cnt": 5, "total_cnt": 100}

        def _update_badge():
            try:
                badge_canvas.delete("all")
                ep = episode_var.get()
                acc = current_hg_info.get("accessible_cnt", 5)
                bw = badge_canvas.winfo_width() or 180
                if ep > acc:
                    draw_rounded_rect(badge_canvas, 1, 1, bw - 2, 22, 6, fill="#450a0a", outline="#dc2626", width=1)
                    draw_icon(badge_canvas, "lock", 14, 11, size=12, color="#f87171", width=1.5)
                    badge_canvas.create_text(26, 11, text="LOCKED (REQUIRES COOKIES)", fill="#f87171", font=("Segoe UI", 7, "bold"), anchor="w")
                else:
                    draw_rounded_rect(badge_canvas, 1, 1, bw - 2, 22, 6, fill="#064e3b", outline="#059669", width=1)
                    draw_icon(badge_canvas, "check", 14, 11, size=12, color="#34d399", width=2)
                    badge_canvas.create_text(26, 11, text=f"FREE EPISODE ({ep})", fill="#34d399", font=("Segoe UI", 7, "bold"), anchor="w")
            except Exception:
                pass

        episode_var.trace_add("write", lambda *a: _update_badge())

        # Async series inspector
        last_inspected_series = [None]
        def _inspect_hongguo_async(url_text: str):
            series_id, vid = extract_hongguo_ids(url_text)
            if not series_id or series_id == last_inspected_series[0]:
                return
            last_inspected_series[0] = series_id

            def _fetch():
                try:
                    c_file = cookie_var.get().strip() or None
                    info = self.downloader.get_hongguo_series_info(series_id, cookie_file=c_file)
                    s_name = info.get("series_name", "Hongguo Drama")
                    ep_cnt = info.get("episode_cnt", 1)
                    acc_cnt = info.get("accessible_episode_cnt", 5)
                    vid_list = info.get("vid_list", [])

                    def _apply():
                        current_hg_info["accessible_cnt"] = acc_cnt
                        current_hg_info["total_cnt"] = ep_cnt
                        lbl_hg_info.config(
                            text=f"Drama: 《{s_name}》  |  Episodes: {ep_cnt} Total (Free: 1–{acc_cnt})"
                        )
                        spn_ep.config(to=ep_cnt)
                        if vid and vid in vid_list:
                            match_ep = vid_list.index(vid) + 1
                            episode_var.set(match_ep)
                        _update_badge()

                    self.run_on_ui_thread(_apply)
                except Exception as ex:
                    print(f"[Hongguo Async Inspect Notice]: {ex}")

            threading.Thread(target=_fetch, daemon=True).start()

        def _sync_url_ui(*args):
            raw = url_var.get().strip()
            if is_hongguo_url(raw):
                tip_frame.pack_forget()
                hg_card.pack(fill=tk.X, pady=(0, 6), before=cookie_row)
                lbl_cookie.config(text="Cookies File (Required for Locked Episodes 6+):")
                _inspect_hongguo_async(raw)
            else:
                hg_card.pack_forget()
                tip_frame.pack(fill=tk.X, pady=(0, 6), before=cookie_row)
                lbl_cookie.config(text="Cookies File (Optional for Douyin / VIP):")

        url_var.trace_add("write", _sync_url_ui)
        # Initial sync
        _sync_url_ui()

        # Button row
        btn_row = tk.Frame(pad_frame, bg="#0b0f19")
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)

        def _do_action(auto_dub: bool):
            raw_val = url_var.get().strip()
            if not raw_val:
                messagebox.showwarning("Notice", "Please paste a video URL first!", parent=dialog)
                return
            cookie_val = cookie_var.get().strip() or None
            ep_val = episode_var.get() if is_hongguo_url(raw_val) else None
            dialog.destroy()
            self.start_download_and_dub(
                raw_val,
                auto_dub=auto_dub,
                cookie_file=cookie_val,
                episode_num=ep_val
            )

        btn_cancel = RoundedButton(
            btn_row,
            text="Cancel",
            command=dialog.destroy,
            bg_color="#334155",
            hover_color="#475569",
            text_color="#ffffff",
            radius=8,
            height=34,
            width=80,
            font=("Segoe UI", 9)
        )
        btn_cancel.pack(side=tk.RIGHT, padx=(8, 0))

        btn_download_only = RoundedButton(
            btn_row,
            text="Download Only",
            icon="download",
            icon_size=13,
            command=lambda: _do_action(auto_dub=False),
            bg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            radius=8,
            height=34,
            width=130,
            font=("Segoe UI", 9, "bold")
        )
        btn_download_only.pack(side=tk.RIGHT, padx=(8, 0))

        btn_download_dub = RoundedButton(
            btn_row,
            text="Download & Auto-Dub",
            icon="sparkle_play",
            icon_size=14,
            command=lambda: _do_action(auto_dub=auto_dub_var.get()),
            bg_color="#e11d48",
            hover_color="#be123c",
            text_color="#ffffff",
            radius=8,
            height=34,
            width=180,
            font=("Segoe UI", 9, "bold")
        )
        btn_download_dub.pack(side=tk.RIGHT)

    def start_download_and_dub(
        self,
        raw_url: str,
        auto_dub: bool = True,
        cookie_file: Optional[str] = None,
        episode_num: Optional[int] = None
    ):
        """Download video from URL in background, then automatically trigger dubbing."""
        self._cancel_event.clear()
        self._set_controls_state("processing")
        self.status_var.set("Connecting to video link...")
        self.progress_bar.set_progress(5)
        self.percent_label.config(text="5%")

        def cancel_check():
            return self._cancel_event.is_set()

        def on_dl_progress(msg, pct):
            if cancel_check():
                raise InterruptedError("Download cancelled by user.")
            self.update_progress_safe(msg, pct)

        def _worker():
            try:
                # 1. Download video (Hongguo or generic)
                if self.downloader.is_hongguo_url(raw_url):
                    downloaded_file = self.downloader.download_hongguo_video(
                        url=raw_url,
                        episode_num=episode_num or 1,
                        target_dir=os.path.join(self.engine.temp_dir, "downloads"),
                        cookie_file=cookie_file,
                        on_progress=on_dl_progress,
                        cancel_check=cancel_check
                    )
                else:
                    downloaded_file = self.downloader.download_video(
                        url_or_text=raw_url,
                        output_dir=os.path.join(self.engine.temp_dir, "downloads"),
                        cookie_file=cookie_file,
                        on_progress=on_dl_progress,
                        cancel_check=cancel_check
                    )

                if cancel_check():
                    raise InterruptedError("Download cancelled by user.")

                # 2. Load into player view and auto-dub if requested
                def _on_loaded():
                    self.load_video_file(downloaded_file)
                    if auto_dub:
                        self.start_dubbing()
                    else:
                        self._set_controls_state("ready")
                        self.update_progress_safe("Video downloaded successfully! Click 'Start Dubbing' to dub.", 100)
                        messagebox.showinfo("Success", f"Video downloaded successfully!\n\n{os.path.basename(downloaded_file)}")

                self.run_on_ui_thread(_on_loaded)
            except InterruptedError:
                self.update_progress_safe("Operation cancelled.", 0)
                def _on_cancel():
                    self._set_controls_state("ready")
                    self.status_var.set("Cancelled")
                self.run_on_ui_thread(_on_cancel)
            except Exception as e:
                err_msg = str(e)
                self.update_progress_safe("Download / Dubbing error", 0)
                def _on_err():
                    self._set_controls_state("ready")
                    self.status_var.set("Error occurred")
                    messagebox.showerror("Download Error", f"Failed to download or dub video:\n\n{err_msg}")
                self.run_on_ui_thread(_on_err)

        threading.Thread(target=_worker, daemon=True).start()

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
                saved_extra.append(f"[Subtitles] {os.path.basename(srt_dest)}")

            # 3. Also save Khmer audio track alongside video if available
            if self.last_dubbed_audio and os.path.exists(self.last_dubbed_audio):
                ext = os.path.splitext(self.last_dubbed_audio)[1] or ".mp3"
                audio_dest = os.path.join(dest_dir, f"{dest_base}_khmer{ext}")
                shutil.copy2(self.last_dubbed_audio, audio_dest)
                saved_extra.append(f"[Audio] {os.path.basename(audio_dest)}")

            self.status_var.set(f"Saved: {os.path.basename(save_dest)}")
            extra_msg = ("\n" + "\n".join(saved_extra)) if saved_extra else ""
            messagebox.showinfo(
                "Saved Successfully",
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
            self.btn_voice_toggle.set_icon("woman")
            self.btn_voice_toggle.set_colors("#db2777", "#be185d")
            self.btn_voice_sample.set_text("Sample: Edge TTS (F)")
            self.btn_voice_sample.set_colors("#94a3b8", "#64748b")
        elif self.voice_type == "Clone":
            self.btn_voice_toggle.set_text("Voice: Clone (VoxCPM 2)")
            self.btn_voice_toggle.set_icon("sparkles")
            self.btn_voice_toggle.set_colors("#7c3aed", "#6d28d9")
            sample_name = os.path.basename(self.custom_reference_audio) if self.custom_reference_audio else "Video Audio"
            if len(sample_name) > 16:
                sample_name = sample_name[:13] + "..."
            self.btn_voice_sample.set_text(f"Sample: {sample_name}")
            self.btn_voice_sample.set_colors("#0d9488", "#0f766e")
        else:
            self.voice_type = "Man"
            self.btn_voice_toggle.set_text("Voice: Man")
            self.btn_voice_toggle.set_icon("man")
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

    def toggle_blur_subtitles(self):
        """Action 4c (Blur Subtitle): Toggle original burned-in subtitle blurring ON/OFF."""
        new_val = not self.blur_subtitles_var.get()
        self.blur_subtitles_var.set(new_val)
        if new_val:
            self.btn_blur_toggle.set_text("Blur Subtitles: ON")
            self.btn_blur_toggle.set_colors("#7c3aed", "#6d28d9")
            self.status_var.set("Subtitle Blur: ON (Original foreign subtitles will be frosted blurred)")
        else:
            self.btn_blur_toggle.set_text("Blur Subtitles: OFF")
            self.btn_blur_toggle.set_colors("#64748b", "#475569")
            self.status_var.set("Subtitle Blur: OFF (Original video preserved without blur)")

    def toggle_anti_duplicate(self):
        """Action 4f (Anti-Duplicate): Toggle TikTok / Facebook algorithm duplicate bypass."""
        new_val = not self.anti_duplicate_var.get()
        self.anti_duplicate_var.set(new_val)
        if new_val:
            self.btn_anti_dup_toggle.set_text("TikTok FYP Bypass: ON")
            self.btn_anti_dup_toggle.set_colors("#059669", "#047857")
            self.status_var.set("TikTok FYP Bypass: ON (Strips metadata, zooms 104%, tunes color to bypass 0-view penalty)")
        else:
            self.btn_anti_dup_toggle.set_text("TikTok FYP Bypass: OFF")
            self.btn_anti_dup_toggle.set_colors("#64748b", "#475569")
            self.status_var.set("TikTok FYP Bypass: OFF (Standard video export)")

    def toggle_bg_audio(self):
        """Action 4d (Background Audio): Cycle between Clean BG (No Voice), Keep All (20%), and Muted (0%)."""
        current = self.bg_mode_var.get()
        if current == "clean_bg":
            next_mode = "all_bg"
            self.btn_bg_toggle.set_text("Original Audio: Keep All (20%)")
            self.btn_bg_toggle.set_icon("volume")
            self.btn_bg_toggle.set_colors("#4f46e5", "#4338ca")
            self.status_var.set("Original Audio: KEEP ALL (Original speech & music both preserved at 20%)")
            self.keep_bg_audio_var.set(True)
        elif current == "all_bg":
            next_mode = "muted"
            self.btn_bg_toggle.set_text("Original Audio: Muted (0%)")
            self.btn_bg_toggle.set_icon("volume_mute")
            self.btn_bg_toggle.set_colors("#475569", "#334155")
            self.status_var.set("Original Audio: MUTED (Original audio completely dropped, pure Khmer voice)")
            self.keep_bg_audio_var.set(False)
        else:
            next_mode = "clean_bg"
            self.btn_bg_toggle.set_text("Original Audio: Clean BG (No Voice)")
            self.btn_bg_toggle.set_icon("volume")
            self.btn_bg_toggle.set_colors("#0284c7", "#0369a1")
            self.status_var.set("Original Audio: CLEAN BG (Original voice REMOVED, background music & SFX kept!)")
            self.keep_bg_audio_var.set(True)
        self.bg_mode_var.set(next_mode)

    def toggle_script_style(self):
        """Action 4e (Script Style): Toggle between Normal translation and Funny Comedy narration."""
        new_val = not self.funny_script_var.get()
        self.funny_script_var.set(new_val)
        if new_val:
            self.btn_funny_toggle.set_text("Script Style: Funny Comedy")
            self.btn_funny_toggle.set_icon("sparkles")
            self.btn_funny_toggle.set_colors("#d97706", "#b45309")
            self.status_var.set("Script Style: FUNNY COMEDY (Entertaining, humorous Cambodian drama commentary)")
        else:
            self.btn_funny_toggle.set_text("Script Style: Normal")
            self.btn_funny_toggle.set_icon("subtitles")
            self.btn_funny_toggle.set_colors("#0d9488", "#0f766e")
            self.status_var.set("Script Style: NORMAL (Accurate, clear Cambodian subtitle translation)")

    def toggle_translator_mode(self):
        """Action: Cycle translation engine between Gemini Web (Auto Browser), Google Translate, and Gemini AI (API)."""
        current = self.translator_mode_var.get()
        if current == "gemini_browser":
            self.translator_mode_var.set("google")
            self.btn_translator_toggle.set_text("AI Translator: Google (Free)")
            self.btn_translator_toggle.set_icon("subtitles")
            self.btn_translator_toggle.set_colors("#0284c7", "#0369a1")
            self.status_var.set("Translator: GOOGLE TRANSLATE - Universal Drama Engine (Fast & free)")
        elif current == "google":
            self.translator_mode_var.set("gemini_api")
            self.btn_translator_toggle.set_text("AI Translator: Gemini AI (API)")
            self.btn_translator_toggle.set_icon("sparkles")
            self.btn_translator_toggle.set_colors("#7c3aed", "#6d28d9")
            self.status_var.set("Translator: GEMINI AI (API) - Background API translation")
            if not self.gemini_api_key_var.get().strip():
                self.show_gemini_api_key_dialog()
        else:
            self.translator_mode_var.set("gemini_browser")
            self.btn_translator_toggle.set_text("AI Translator: Gemini Web (Auto Browser)")
            self.btn_translator_toggle.set_icon("sparkles")
            self.btn_translator_toggle.set_colors("#059669", "#047857")
            self.status_var.set("Translator: GEMINI WEB (AUTO BROWSER) - Opens Chrome, pastes script, copies back, generates voice automatically!")

    def show_gemini_api_key_dialog(self):
        """Show clean modal to enter and save Google Gemini API key for 100% automated background dubbing."""
        top = tk.Toplevel(self)
        top.title("Google Gemini API Settings")
        top.geometry("540x350")
        top.configure(bg="#0f172a")
        top.transient(self)
        top.grab_set()
        top.attributes("-topmost", True)

        lbl_title = tk.Label(
            top,
            text="Google Gemini AI Translation Setup",
            font=("Segoe UI", 12, "bold"),
            bg="#0f172a",
            fg="#c084fc"
        )
        lbl_title.pack(anchor=tk.W, padx=20, pady=(15, 5))

        lbl_desc = tk.Label(
            top,
            text=(
                "Gemini AI translates short dramas with professional Cambodian studio quality,\n"
                "preserving villain hostility, CEO authority, and character lip sync in real time.\n"
                "Get a 100% FREE API key from Google AI Studio (thousands of free requests/day):"
            ),
            font=("Segoe UI", 8),
            bg="#0f172a",
            fg="#94a3b8",
            justify=tk.LEFT
        )
        lbl_desc.pack(anchor=tk.W, padx=20, pady=(0, 10))

        btn_get_key = RoundedButton(
            top,
            text="Get Free API Key (Google AI Studio)",
            icon="sparkles",
            command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"),
            bg_color="#4f46e5",
            hover_color="#4338ca",
            text_color="#ffffff",
            radius=8,
            height=30,
            font=("Segoe UI", 8, "bold")
        )
        btn_get_key.pack(anchor=tk.W, padx=20, pady=(0, 15))

        tk.Label(
            top,
            text="Paste your Gemini API Key here:",
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#e2e8f0"
        ).pack(anchor=tk.W, padx=20, pady=(0, 3))

        entry_key = tk.Entry(
            top,
            font=("Segoe UI", 10),
            bg="#1e293b",
            fg="#f8fafc",
            insertbackground="#ffffff",
            relief=tk.FLAT
        )
        entry_key.pack(fill=tk.X, padx=20, pady=(0, 15), ipady=4)
        current_k = self.gemini_api_key_var.get().strip()
        if current_k:
            entry_key.insert(0, current_k)

        btn_box = tk.Frame(top, bg="#0f172a")
        btn_box.pack(fill=tk.X, padx=20, pady=(5, 15))

        def _save():
            val = entry_key.get().strip()
            if val:
                save_gemini_api_key(val)
                self.gemini_api_key_var.set(val)
                self.translator_mode_var.set("gemini_api")
                self.btn_translator_toggle.set_text("AI Translator: Gemini AI (API)")
                self.btn_translator_toggle.set_colors("#7c3aed", "#6d28d9")
                self.status_var.set("Gemini API key saved! Ready for studio-quality auto-dubbing.")
            top.destroy()

        btn_save = RoundedButton(
            btn_box,
            text="Save & Enable Gemini API",
            icon="check",
            command=_save,
            bg_color="#7c3aed",
            hover_color="#6d28d9",
            text_color="#ffffff",
            radius=8,
            height=32,
            font=("Segoe UI", 9, "bold")
        )
        btn_save.pack(side=tk.RIGHT, padx=(5, 0))

        btn_cancel = RoundedButton(
            btn_box,
            text="Cancel",
            icon="stop",
            command=top.destroy,
            bg_color="#334155",
            hover_color="#475569",
            text_color="#cbd5e1",
            radius=8,
            height=32,
            font=("Segoe UI", 9)
        )
        btn_cancel.pack(side=tk.RIGHT)

    def open_gemini_browser_assistant(self, prompt: str, done_event: threading.Event, result_box: dict):
        """
        Open default browser to gemini.google.com, copy prompt to clipboard,
        and display assistant dialog that auto-detects copied translation from Gemini.
        """
        try:
            self.clipboard_clear()
            self.clipboard_append(prompt)
            self.update()
        except Exception:
            pass

        try:
            webbrowser.open("https://gemini.google.com")
        except Exception as e:
            print(f"[Webbrowser Open Notice]: {e}")

        top = tk.Toplevel(self)
        top.title("Gemini Web Browser Translation Assistant")
        top.geometry("640x520")
        top.configure(bg="#0f172a")
        top.transient(self)
        top.grab_set()
        top.attributes("-topmost", True)

        lbl_title = tk.Label(
            top,
            text="Gemini Web Translation Bridge",
            font=("Segoe UI", 13, "bold"),
            bg="#0f172a",
            fg="#38bdf8"
        )
        lbl_title.pack(anchor=tk.W, padx=20, pady=(15, 5))

        instructions = (
            "1. Chinese drama dialogue has been COPIED to your clipboard.\n"
            "2. Gemini has been opened in your browser (https://gemini.google.com).\n"
            "3. In Gemini, press Ctrl+V to paste the prompt and click Send.\n"
            "4. When Gemini finishes generating, click the Copy button on Gemini's answer.\n"
            "-> The app will automatically detect your copied translation and start dubbing!"
        )
        lbl_info = tk.Label(
            top,
            text=instructions,
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#e2e8f0",
            justify=tk.LEFT,
            padx=12,
            pady=10,
            relief=tk.FLAT
        )
        lbl_info.pack(fill=tk.X, padx=20, pady=5)

        status_lbl = tk.Label(
            top,
            text="Listening to clipboard for Gemini translation...",
            font=("Segoe UI", 9, "italic"),
            bg="#0f172a",
            fg="#f59e0b"
        )
        status_lbl.pack(anchor=tk.W, padx=20, pady=(8, 2))

        txt_area = scrolledtext.ScrolledText(
            top,
            wrap=tk.WORD,
            bg="#020617",
            fg="#f8fafc",
            insertbackground="#ffffff",
            font=("Segoe UI", 9),
            height=10
        )
        txt_area.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        btn_frame = tk.Frame(top, bg="#0f172a")
        btn_frame.pack(fill=tk.X, padx=20, pady=(10, 15))

        def _on_continue():
            text_val = txt_area.get("1.0", tk.END).strip()
            result_box["text"] = text_val
            done_event.set()
            try:
                top.destroy()
            except Exception:
                pass

        def _on_cancel():
            result_box["text"] = ""
            done_event.set()
            try:
                top.destroy()
            except Exception:
                pass

        btn_cont = RoundedButton(
            btn_frame,
            text="Continue Dubbing with This Translation",
            icon="sparkles",
            command=_on_continue,
            bg_color="#059669",
            hover_color="#047857",
            text_color="#ffffff",
            radius=8,
            height=34,
            font=("Segoe UI", 9, "bold")
        )
        btn_cont.pack(side=tk.RIGHT, padx=(5, 0))

        btn_close = RoundedButton(
            btn_frame,
            text="Cancel / Use Default",
            icon="stop",
            command=_on_cancel,
            bg_color="#334155",
            hover_color="#475569",
            text_color="#cbd5e1",
            radius=8,
            height=34,
            font=("Segoe UI", 9)
        )
        btn_close.pack(side=tk.RIGHT)

        top.protocol("WM_DELETE_WINDOW", _on_cancel)

        # Auto-clipboard detection loop
        sent_prompt_hash = hash(prompt.strip())
        auto_detected = {"done": False}

        def _poll_clipboard():
            if auto_detected["done"] or not top.winfo_exists():
                return
            try:
                clip = self.clipboard_get().strip()
                if clip and hash(clip) != sent_prompt_hash and len(clip) > 10:
                    khmer_count = len(re.findall(r"[\u1780-\u17ff]", clip))
                    if khmer_count > 10:
                        auto_detected["done"] = True
                        status_lbl.configure(text="Translation detected from Gemini! Starting voice generation...", fg="#10b981")
                        txt_area.delete("1.0", tk.END)
                        txt_area.insert("1.0", clip)
                        top.after(1000, _on_continue)
                        return
            except Exception:
                pass
            if top.winfo_exists():
                top.after(600, _poll_clipboard)

        top.after(1000, _poll_clipboard)

    def on_voice_sample_clicked(self):
        """Action 4b: Handle click on Voice Sample button (instant audio preview)."""
        if self.voice_type == "Clone":
            if self.custom_reference_audio and os.path.exists(self.custom_reference_audio):
                self.status_var.set(f"Playing Clone Sample: {os.path.basename(self.custom_reference_audio)}")
                self.sample_player.play(self.custom_reference_audio)
            elif self.video_path_var.get() and os.path.exists(self.video_path_var.get()):
                base_name = os.path.splitext(os.path.basename(self.video_path_var.get()))[0]
                preview_dir = os.path.join(self.engine.temp_dir, "dubbing_preview")
                ref_p = os.path.join(preview_dir, f"{base_name}_speaker_sample.wav")
                if not (os.path.exists(ref_p) and os.path.getsize(ref_p) > 1000):
                    self.status_var.set("Extracting speaker audio from video...")
                    self.voxcpm_engine.extract_reference_clip(self.video_path_var.get(), ref_p, start_sec=1.0, duration_sec=5.0)
                if os.path.exists(ref_p) and os.path.getsize(ref_p) > 1000:
                    self.status_var.set("Playing Video Speaker Sample")
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
                    self.status_var.set(f"Playing {self.voice_type} voice sample")
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
        style_tag = "funny" if self.funny_script_var.get() else "normal"
        bg_tag = self.bg_mode_var.get()
        preview_dir = os.path.join(self.engine.temp_dir, "dubbing_preview")
        os.makedirs(preview_dir, exist_ok=True)

        preview_video_path = os.path.join(preview_dir, f"{base_name}_preview_{voice_tag}_{style_tag}_{bg_tag}.mp4")
        preview_srt_path = os.path.join(preview_dir, f"{base_name}_khmer_{style_tag}.srt")
        preview_audio_path = os.path.join(preview_dir, f"{base_name}_khmer_{voice_tag}_{style_tag}.mp3")
        preview_txt_path = os.path.join(preview_dir, f"{base_name}_khmer_{style_tag}.txt")
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
            meta = self.engine.probe_video_metadata(filepath)
            video_duration = meta.get("duration", 0.0)

            needs_extraction = True
            if os.path.exists(source_srt_path) and os.path.getsize(source_srt_path) > 0:
                try:
                    from src.core.dubbing_engine import parse_srt_file
                    parsed_test = parse_srt_file(source_srt_path)
                    if parsed_test and any(
                        p.text and len(p.text.strip()) > 1 and not (p.text.strip().startswith("[") and p.text.strip().endswith("]"))
                        for p in parsed_test
                    ):
                        # Detect if existing SRT was created with old coarse integer sliding windows from SpeechRecognition
                        is_coarse_chunked = all(
                            abs(s.start - round(s.start)) < 0.001 and abs(s.end - round(s.end)) < 0.001
                            for s in parsed_test
                        )
                        has_oversized_chunk = any((s.end - s.start) >= 4.5 for s in parsed_test)
                        # Fix real-time voice sync: If cached SRT is truncated but video is full length
                        is_truncated_cache = False
                        if video_duration > 15.0 and parsed_test:
                            last_end = max(s.end for s in parsed_test)
                            if last_end < (video_duration * 0.85):
                                is_truncated_cache = True

                        if (is_coarse_chunked or has_oversized_chunk or is_truncated_cache) and self.script_extractor.get_available_engine() in ("openai-whisper", "faster-whisper"):
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

            # Step 2: Translate script to Khmer (Google Translate or Gemini AI / Browser)
            funny_mode = self.funny_script_var.get()
            translator_mode = self.translator_mode_var.get()
            gemini_key = self.gemini_api_key_var.get().strip()

            style_desc = "Funny Comedy (កំប្លែង)" if funny_mode else "Normal"
            trans_label = "Gemini AI (API)" if translator_mode == "gemini_api" else ("Gemini Web (Auto Browser)" if translator_mode == "gemini_browser" else "Google")
            self.update_progress_safe(f"Step 2/4: Translating subtitles ({trans_label} - {style_desc})...", 30)
            khmer_segments, full_khmer_script = self.dubbing_engine.translate_script(
                source_srt_path=source_srt_path,
                output_khmer_srt=preview_srt_path,
                output_khmer_txt=preview_txt_path,
                funny_mode=funny_mode,
                translator_mode=translator_mode,
                gemini_api_key=gemini_key,
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
                    funny_mode=funny_mode,
                    translator_mode=translator_mode,
                    gemini_api_key=gemini_key,
                    manual_translated_srt_content=manual_content,
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

            # Step 4: Merge Khmer voice into video (with clean background / voice removal / subtitle blur)
            blur_on = self.blur_subtitles_var.get()
            blur_note = " (with subtitle blur)" if blur_on else ""
            anti_dup_on = self.anti_duplicate_var.get()
            dup_note = " (with TikTok FYP bypass)" if anti_dup_on else ""
            bg_mode = self.bg_mode_var.get()
            if bg_mode == "clean_bg":
                bg_desc = "Clean BGM & SFX (Original Voice Removed)"
                remove_orig = False
                remove_voice = True
                bg_vol = 0.30
            elif bg_mode == "all_bg":
                bg_desc = "Original Audio Kept (20%)"
                remove_orig = False
                remove_voice = False
                bg_vol = 0.20
            else:
                bg_desc = "Original Audio Muted (0%)"
                remove_orig = True
                remove_voice = False
                bg_vol = 0.0

            self.update_progress_safe(f"Step 4/4: Merging Khmer voice ({bg_desc}{blur_note}{dup_note})...", 85)
            self.dubbing_engine.merge_video(
                video_path=filepath,
                audio_path=generated_audio,
                output_video_path=preview_video_path,
                remove_original_sound=remove_orig,
                background_volume=bg_vol,
                remove_voice_from_bg=remove_voice,
                speech_segments=khmer_segments if remove_voice else None,
                blur_subtitles=blur_on,
                anti_duplicate=anti_dup_on,
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

            self.update_progress_safe("Dubbing Complete! Ready for review.", 100)

            # Prompt success with details and auto-load dubbed video for instant preview review
            def _on_success():
                try:
                    self.player_view.load_video(preview_video_path)
                except Exception:
                    pass

                self.btn_save.set_state(tk.NORMAL)
                self.btn_save.set_colors("#059669", "#047857")
                self.status_var.set("Dubbing ready for review! Click Play to watch, then click 'Save Video' to save.")

                desc = "VoxCPM 2 Cloned Voice" if is_clone else f"{voice} voice"
                sample_info = f"\n• Speaker Reference Clip:\n{ref_sample_path}\n" if is_clone and ref_sample_path else ""
                messagebox.showinfo(
                    "Dubbing Ready for Review",
                    f"Video successfully dubbed in Khmer ({desc})!\n\n"
                    f"• The dubbed video is now loaded in the player.\n"
                    f"• Click Play to review the video and listen to the dubbed voice.\n"
                    f"{sample_info}\n"
                    f"• It is NOT auto-saved yet! When you are satisfied, click 'Save Video' to save it to your computer."
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
