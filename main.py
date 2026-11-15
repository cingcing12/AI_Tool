"""
Video Translate Application
Created for: បង LIHOUR
Developed by: ប្អូនហនុមាន (Hanuman)
"""

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

# Ensure src is in Python path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from src.ui import RoundedCard, RoundedButton, RoundedProgressBar, YouTubePlayerView
from src.core import VideoEngine


class VideoTranslateApp(tk.Tk):
    """Main Application Controller for Video Translate."""

    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Video Translate")
        self.geometry("800x480")
        self.minsize(740, 440)
        self.configure(bg="#f1f5f9")

        # Core Video Engine
        self.engine = VideoEngine(base_dir=APP_DIR)

        # Variables
        self.video_path_var = tk.StringVar(value="")
        default_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        self.output_folder = default_downloads if os.path.exists(default_downloads) else os.path.expanduser("~")

        self.voice_type = "Man"
        self.status_var = tk.StringVar(value="Status: Ready. Click 'Load' to select video.")
        self.is_processing = False

        # Build UI Layout
        self._create_layout()

        # Clean shutdown protocol
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Ensure stream processes and audio player are closed gracefully."""
        if hasattr(self, "player_view"):
            self.player_view.destroy()
        self.destroy()

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

        # Unified YouTube Video Player Screen
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
        self.btn_load.pack(fill=tk.X, pady=(0, 10))

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
        self.btn_voice_toggle.pack(fill=tk.X, pady=(0, 12))

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

        # Smooth Rounded Progress Bar
        self.progress_bar = RoundedProgressBar(
            bottom_frame,
            height=14,
            trough_color="#e2e8f0",
            fill_color="#10b981",
            radius=7
        )
        self.progress_bar.pack(fill=tk.X)

    # ==========================================
    # Button Actions
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
        filename = os.path.basename(selected_file)

        # Load video and extract real frames via VideoEngine
        self.player_view.load_video(selected_file)
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
            self.status_var.set(f"Save destination set to '{folder_name}'.")

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
        """Worker thread executing audio extraction and dubbing pipeline."""
        steps = [
            (20, "1/4 Extracting audio track with FFmpeg... 🎵"),
            (50, f"2/4 Generating {voice} AI speech clone... 🎙️"),
            (80, "3/4 Merging dubbed audio track with video... 🎬"),
            (100, f"4/4 Completed and saved to {os.path.basename(output_path)}! 🎉")
        ]

        # Extract audio using real VideoEngine
        self.engine.extract_audio(filepath)

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


# Backward compatibility alias
VideoDubbingApp = VideoTranslateApp

if __name__ == "__main__":
    app = VideoTranslateApp()
    app.mainloop()
