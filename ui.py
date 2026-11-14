from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

from pipeline import (
    AnalysisResult,
    DEFAULT_BACKGROUND_VOLUME,
    DEFAULT_VOICE_GENDER,
    WorkflowConfig,
    analyze_video,
    build_default_output_paths,
    build_output_video,
    build_voice_with_timing,
    download_video_from_url,
    find_original_video_for_generated_output,
    normalize_language_code,
    normalize_voice_gender,
    save_voice_synced_subtitles,
    save_text,
    translate_text,
)


RESAMPLING = getattr(Image, "Resampling", Image).LANCZOS
SPEECH_LANGUAGE_OPTIONS = (
    "Auto detect - auto",
    "English (US) - en-US",
    "Chinese (China) - zh-CN",
    "Chinese (Taiwan) - zh-TW",
    "Khmer (Cambodia) - km-KH",
    "Japanese - ja-JP",
    "Korean - ko-KR",
)
TRANSLATION_SOURCE_OPTIONS = (
    "Auto - auto",
    "English - en",
    "Chinese (China) - zh-CN",
    "Chinese (Taiwan) - zh-TW",
    "Khmer - km",
    "Japanese - ja",
    "Korean - ko",
)
TRANSLATION_TARGET_OPTIONS = (
    "Khmer - km",
    "Chinese (China) - zh-CN",
    "Chinese (Taiwan) - zh-TW",
    "English - en",
    "Japanese - ja",
    "Korean - ko",
)
VOICE_LANGUAGE_OPTIONS = (
    "Khmer - km",
    "Chinese (China) - zh-CN",
    "Chinese (Taiwan) - zh-TW",
    "English - en",
    "Japanese - ja",
    "Korean - ko",
)
VOICE_GENDER_OPTIONS = (
    "Female - female",
    "Male - male",
    "Auto/default - auto",
)
COOKIE_BROWSER_OPTIONS = (
    "None",
    "Edge - edge",
    "Chrome - chrome",
    "Firefox - firefox",
    "Brave - brave",
)
ORIGINAL_AUDIO_MODE_OPTIONS = (
    "Remove voice only - keep background",
    "Remove all original audio",
    "Keep full original audio",
)


class KhmerVideoUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AI Somray Khmer Studio")
        self.root.geometry("1380x920")
        self.root.minsize(1180, 780)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False

        self.preview_clip = None
        self.preview_path: str | None = None
        self.preview_duration = 0.0
        self.preview_current_time = 0.0
        self.preview_fps = 24.0
        self.preview_playing = False
        self.preview_after_id: str | None = None
        self.preview_resize_after_id: str | None = None
        self.preview_image = None
        self.preview_viewport: tk.Frame | None = None
        self.ignore_seek = False

        self.current_output_paths: dict[str, str] = {}
        self.current_analysis: AnalysisResult | None = None
        self.current_audio_path: str | None = None
        self.current_output_video_path: str | None = None

        self.video_var = tk.StringVar()
        self.video_url_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.cookies_browser_var = tk.StringVar(value=COOKIE_BROWSER_OPTIONS[0])
        self.cookies_file_var = tk.StringVar()
        self.speech_lang_var = tk.StringVar(value=SPEECH_LANGUAGE_OPTIONS[0])
        self.source_lang_var = tk.StringVar(value=TRANSLATION_SOURCE_OPTIONS[0])
        self.target_lang_var = tk.StringVar(value=TRANSLATION_TARGET_OPTIONS[0])
        self.voice_lang_var = tk.StringVar(value=VOICE_LANGUAGE_OPTIONS[0])
        self.voice_gender_var = tk.StringVar(value=VOICE_GENDER_OPTIONS[0])
        self.transcription_engine_var = tk.StringVar(value="auto")
        self.whisper_model_var = tk.StringVar(value="medium")
        self.hf_token_var = tk.StringVar(value="")
        self.ollama_model_var = tk.StringVar(value="llava:latest")
        self.chunk_seconds_var = tk.StringVar(value="5")
        self.original_volume_var = tk.StringVar(value=f"{DEFAULT_BACKGROUND_VOLUME:g}")
        self.generate_voice_var = tk.BooleanVar(value=True)
        self.original_audio_mode_var = tk.StringVar(value=ORIGINAL_AUDIO_MODE_OPTIONS[0])
        self.slow_voice_var = tk.BooleanVar(value=False)
        self.skip_translation_var = tk.BooleanVar(value=False)
        self.repair_transcript_var = tk.BooleanVar(value=False)
        self.preview_position_var = tk.DoubleVar(value=0.0)
        self.preview_time_var = tk.StringVar(value="00:00 / 00:00")
        self.status_var = tk.StringVar(value="Ready")
        self.current_video_label_var = tk.StringVar(value="No preview loaded")
        self.output_video_var = tk.StringVar(value="")
        self.audio_path_var = tk.StringVar(value="")
        self.khmer_path_var = tk.StringVar(value="")

        self._configure_styles()
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_events)

    def _configure_styles(self) -> None:
        self.root.configure(bg="#eef2f6")
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background="#eef2f6")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Header.TFrame", background="#172033")
        style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#172033", font=("Segoe UI", 10, "bold"))
        style.configure("App.TLabel", background="#eef2f6", foreground="#172033")
        style.configure("Card.TLabel", background="#ffffff", foreground="#172033")
        style.configure("Muted.TLabel", background="#ffffff", foreground="#5e6b7a")
        style.configure("HeaderTitle.TLabel", background="#172033", foreground="#ffffff", font=("Segoe UI", 20, "bold"))
        style.configure("HeaderMeta.TLabel", background="#172033", foreground="#cbd5e1")
        style.configure("Section.TLabel", background="#ffffff", foreground="#172033", font=("Segoe UI", 10, "bold"))
        style.configure("Accent.TButton", padding=8, background="#116a5b", foreground="white")
        style.map(
            "Accent.TButton",
            background=[("active", "#15806e"), ("disabled", "#91aaa3")],
            foreground=[("disabled", "#f2f2f2")],
        )
        style.configure("Soft.TButton", padding=8, background="#dbe4ef", foreground="#172033")
        style.map("Soft.TButton", background=[("active", "#cbd8e7")])
        style.configure("Path.TEntry", fieldbackground="#ffffff")
        style.configure("Preview.Horizontal.TScale", background="#ffffff")
        style.configure("Busy.Horizontal.TProgressbar", background="#116a5b", troughcolor="#dbe4ef")

    def _build_layout(self) -> None:
        root_frame = ttk.Frame(self.root, style="App.TFrame", padding=18)
        root_frame.pack(fill="both", expand=True)

        hero = ttk.Frame(root_frame, style="Header.TFrame", padding=(18, 14))
        hero.pack(fill="x")
        ttk.Label(
            hero,
            text="AI Somray Khmer Studio",
            style="HeaderTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            hero,
            text="Khmer video voiceover workspace",
            style="HeaderMeta.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        main_split = ttk.Panedwindow(root_frame, orient="vertical")
        main_split.pack(fill="both", expand=True, pady=(16, 0))

        top_split = ttk.Panedwindow(main_split, orient="horizontal")
        main_split.add(top_split, weight=4)

        preview_card = ttk.LabelFrame(top_split, text="Preview", style="Card.TLabelframe", padding=12)
        controls_card = ttk.LabelFrame(top_split, text="Workflow", style="Card.TLabelframe", padding=12)
        top_split.add(preview_card, weight=5)
        top_split.add(controls_card, weight=4)

        lower_split = ttk.Panedwindow(main_split, orient="vertical")
        main_split.add(lower_split, weight=5)

        editor_split = ttk.Panedwindow(lower_split, orient="horizontal")
        lower_split.add(editor_split, weight=4)

        transcript_card = ttk.LabelFrame(editor_split, text="Original Transcript", style="Card.TLabelframe", padding=12)
        khmer_card = ttk.LabelFrame(editor_split, text="Editable Khmer Script", style="Card.TLabelframe", padding=12)
        editor_split.add(transcript_card, weight=1)
        editor_split.add(khmer_card, weight=1)

        log_card = ttk.LabelFrame(lower_split, text="Log", style="Card.TLabelframe", padding=12)
        lower_split.add(log_card, weight=2)

        self._build_preview_card(preview_card)
        self._build_controls_card(controls_card)
        self._build_editors(transcript_card, khmer_card)
        self._build_log(log_card)

    def _build_preview_card(self, parent: ttk.LabelFrame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.preview_viewport = tk.Frame(parent, bg="#0f1114", height=220)
        self.preview_viewport.grid(row=0, column=0, sticky="nsew")
        self.preview_viewport.grid_propagate(False)
        self.preview_viewport.bind("<Configure>", self._schedule_preview_resize)

        self.preview_surface = tk.Label(
            self.preview_viewport,
            text="Choose a video to preview",
            bg="#0f1114",
            fg="#f7efe4",
            anchor="center",
            justify="center",
            font=("Segoe UI", 11),
        )
        self.preview_surface.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(parent, textvariable=self.current_video_label_var, style="Card.TLabel", wraplength=520).grid(row=1, column=0, sticky="ew", pady=(10, 2))
        ttk.Label(
            parent,
            text="In-app preview is silent. Use Open Current Video for full audio/video playback.",
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(0, 10))

        button_row = ttk.Frame(parent, style="Card.TFrame")
        button_row.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(button_row, text="Preview Input", style="Soft.TButton", command=self._preview_input).pack(side="left")
        ttk.Button(button_row, text="Preview Output", style="Soft.TButton", command=self._preview_output).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Open Current Video", style="Soft.TButton", command=self._open_current_video).pack(side="left", padx=(8, 0))

        playback_row = ttk.Frame(parent, style="Card.TFrame")
        playback_row.grid(row=4, column=0, sticky="ew")
        self.play_button = ttk.Button(playback_row, text="Play", style="Accent.TButton", command=self._toggle_preview_playback)
        self.play_button.pack(side="left")

        self.preview_scale = ttk.Scale(
            playback_row,
            from_=0.0,
            to=1.0,
            variable=self.preview_position_var,
            command=self._handle_seek,
            style="Preview.Horizontal.TScale",
        )
        self.preview_scale.pack(side="left", fill="x", expand=True, padx=(12, 12))
        ttk.Label(playback_row, textvariable=self.preview_time_var, style="Card.TLabel").pack(side="left")

    def _build_controls_card(self, parent: ttk.LabelFrame) -> None:
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Video file", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(parent, textvariable=self.video_var, style="Path.TEntry").grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="Browse", style="Soft.TButton", command=self._browse_video).grid(row=0, column=2, padx=(8, 0), pady=6)

        ttk.Label(parent, text="Video link/share", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(parent, textvariable=self.video_url_var, style="Path.TEntry").grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="Fetch", style="Soft.TButton", command=self._start_fetch_video_link).grid(row=1, column=2, padx=(8, 0), pady=6)

        ttk.Label(parent, text="Output folder", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(parent, textvariable=self.output_dir_var, style="Path.TEntry").grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="Browse", style="Soft.TButton", command=self._browse_output_dir).grid(row=2, column=2, padx=(8, 0), pady=6)

        settings = ttk.Frame(parent, style="Card.TFrame")
        settings.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for column in range(4):
            settings.columnconfigure(column, weight=1)

        self._labeled_combo(settings, "Speech language", self.speech_lang_var, 0, 0, SPEECH_LANGUAGE_OPTIONS)
        self._labeled_combo(settings, "Source lang", self.source_lang_var, 0, 1, TRANSLATION_SOURCE_OPTIONS)
        self._labeled_combo(settings, "Target lang", self.target_lang_var, 0, 2, TRANSLATION_TARGET_OPTIONS)
        self._labeled_combo(settings, "Voice lang", self.voice_lang_var, 0, 3, VOICE_LANGUAGE_OPTIONS)

        self._labeled_combo(settings, "Voice gender", self.voice_gender_var, 2, 0, VOICE_GENDER_OPTIONS)
        ttk.Label(settings, text="Transcription engine", style="Card.TLabel").grid(row=2, column=1, sticky="w")
        self.transcription_engine_combo = ttk.Combobox(
            settings,
            textvariable=self.transcription_engine_var,
            values=("auto", "faster-whisper", "whisper", "google"),
            state="readonly",
        )
        self.transcription_engine_combo.grid(row=3, column=1, sticky="ew", padx=(0, 8), pady=(0, 8))

        self._labeled_entry(settings, "Whisper model", self.whisper_model_var, 2, 2)
        self._labeled_entry(settings, "HF token", self.hf_token_var, 2, 3)

        self._labeled_entry(settings, "Ollama model", self.ollama_model_var, 4, 0)
        ttk.Label(settings, text="Repair with Ollama", style="Card.TLabel").grid(row=4, column=1, sticky="w")
        ttk.Checkbutton(settings, text="Use", variable=self.repair_transcript_var).grid(row=5, column=1, sticky="w", pady=(0, 8))

        self._labeled_entry(settings, "Chunk seconds", self.chunk_seconds_var, 4, 2)
        self._labeled_entry(settings, "Background volume", self.original_volume_var, 4, 3)

        self._labeled_combo(settings, "Cookie browser", self.cookies_browser_var, 6, 0, COOKIE_BROWSER_OPTIONS)
        ttk.Label(settings, text="Cookies file", style="Card.TLabel").grid(row=6, column=1, sticky="w")
        ttk.Entry(settings, textvariable=self.cookies_file_var, style="Path.TEntry").grid(row=7, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=(0, 8))
        ttk.Button(settings, text="Browse", style="Soft.TButton", command=self._browse_cookies_file).grid(row=7, column=3, sticky="ew", padx=(0, 8), pady=(0, 8))

        ttk.Checkbutton(settings, text="Generate Khmer voice", variable=self.generate_voice_var).grid(row=8, column=0, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Original audio", style="Card.TLabel").grid(row=8, column=1, sticky="w", pady=(8, 0))
        self.original_audio_mode_combo = ttk.Combobox(
            settings,
            textvariable=self.original_audio_mode_var,
            values=ORIGINAL_AUDIO_MODE_OPTIONS,
            state="readonly",
        )
        self.original_audio_mode_combo.grid(row=9, column=1, sticky="ew", padx=(0, 8), pady=(2, 0))
        ttk.Checkbutton(settings, text="Slow voice", variable=self.slow_voice_var).grid(row=8, column=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(settings, text="Skip translation", variable=self.skip_translation_var).grid(row=8, column=3, sticky="w", pady=(8, 0))

        ttk.Label(parent, text="Actions", style="Section.TLabel").grid(row=8, column=0, columnspan=3, sticky="w", pady=(16, 4))
        action_frame = ttk.Frame(parent, style="Card.TFrame")
        action_frame.grid(row=9, column=0, columnspan=3, sticky="ew")
        for column in range(2):
            action_frame.columnconfigure(column, weight=1)

        ttk.Button(action_frame, text="Analyze Video", style="Accent.TButton", command=self._start_analysis).grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=6)
        ttk.Button(action_frame, text="Re-translate Transcript", style="Soft.TButton", command=self._start_retranslate).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Button(action_frame, text="Generate Voice", style="Soft.TButton", command=self._start_voice_only).grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=6)
        ttk.Button(action_frame, text="Build Final Video", style="Accent.TButton", command=self._start_build_final).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(action_frame, text="Save Khmer Script", style="Soft.TButton", command=self._save_current_khmer_script).grid(row=2, column=0, sticky="ew", padx=(0, 8), pady=6)
        ttk.Button(action_frame, text="Open Output Folder", style="Soft.TButton", command=self._open_output_folder).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(parent, text="Current Outputs", style="Section.TLabel").grid(row=10, column=0, columnspan=3, sticky="w", pady=(16, 4))
        outputs_frame = ttk.Frame(parent, style="Card.TFrame")
        outputs_frame.grid(row=11, column=0, columnspan=3, sticky="ew")
        outputs_frame.columnconfigure(1, weight=1)

        ttk.Label(outputs_frame, text="Khmer text", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(outputs_frame, textvariable=self.khmer_path_var, style="Path.TEntry").grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(outputs_frame, text="Narration audio", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(outputs_frame, textvariable=self.audio_path_var, style="Path.TEntry").grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(outputs_frame, text="Output video", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(outputs_frame, textvariable=self.output_video_var, style="Path.TEntry").grid(row=2, column=1, sticky="ew", pady=4)

        status_row = ttk.Frame(parent, style="Card.TFrame")
        status_row.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Label(status_row, text="Status:", style="Card.TLabel").pack(side="left")
        ttk.Label(status_row, textvariable=self.status_var, style="Card.TLabel").pack(side="left", padx=(8, 0))
        self.busy_progress = ttk.Progressbar(status_row, mode="indeterminate", length=150, style="Busy.Horizontal.TProgressbar")
        self.busy_progress.pack(side="right")

    def _build_editors(self, transcript_card: ttk.LabelFrame, khmer_card: ttk.LabelFrame) -> None:
        ttk.Label(
            transcript_card,
            text="You can correct missing transcript lines here before re-translating.",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        self.transcript_text = scrolledtext.ScrolledText(transcript_card, wrap="word", height=18, font=("Consolas", 10))
        self.transcript_text.pack(fill="both", expand=True)

        ttk.Label(
            khmer_card,
            text="Edit this Khmer script before generating voice. The final voice uses exactly this text.",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        self.khmer_text = scrolledtext.ScrolledText(khmer_card, wrap="word", height=18, font=("Leelawadee UI", 11))
        self.khmer_text.pack(fill="both", expand=True)

    def _build_log(self, parent: ttk.LabelFrame) -> None:
        self.log_text = scrolledtext.ScrolledText(parent, wrap="word", height=10, font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)

    def _labeled_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, column: int) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=column, sticky="w")
        ttk.Entry(parent, textvariable=variable, style="Path.TEntry").grid(row=row + 1, column=column, sticky="ew", padx=(0, 8), pady=(0, 8))

    def _labeled_combo(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        row: int,
        column: int,
        values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=column, sticky="w")
        ttk.Combobox(parent, textvariable=variable, values=values, state="normal").grid(
            row=row + 1,
            column=column,
            sticky="ew",
            padx=(0, 8),
            pady=(0, 8),
        )

    def _language_code(self, variable: tk.StringVar, default: str) -> str:
        return normalize_language_code(variable.get(), default=default)

    def _voice_gender(self) -> str:
        return normalize_voice_gender(self.voice_gender_var.get(), default=DEFAULT_VOICE_GENDER)

    def _append_log(self, message: str) -> None:
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")

    def _replace_text(self, widget: scrolledtext.ScrolledText, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _get_text(self, widget: scrolledtext.ScrolledText) -> str:
        return widget.get("1.0", "end").strip()

    def _browse_video(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose a video file",
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return

        selected_source = find_original_video_for_generated_output(selected)
        if selected_source is not None:
            self._append_log(f"Selected generated output: {selected}")
            selected = str(selected_source)
            self._append_log(f"Using original source video instead: {selected}")

        self.video_var.set(selected)
        if not self.output_dir_var.get().strip():
            self.output_dir_var.set(str(Path(selected).expanduser().resolve().parent))

        self.current_analysis = None
        self.current_audio_path = None
        self.current_output_video_path = None
        self.output_video_var.set("")
        self.audio_path_var.set("")
        self.khmer_path_var.set("")
        self._replace_text(self.transcript_text, "")
        self._replace_text(self.khmer_text, "")
        self._append_log(f"Selected video: {selected}")
        self._load_preview(selected)

    def _browse_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="Choose an output folder")
        if selected:
            self.output_dir_var.set(selected)

    def _browse_cookies_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose a cookies.txt file",
            filetypes=[
                ("Cookie files", "*.txt *.cookies"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.cookies_file_var.set(selected)

    def _start_fetch_video_link(self) -> None:
        video_url = self.video_url_var.get().strip()
        if not video_url:
            messagebox.showerror("No video link", "Paste a Douyin link or copied share text first.")
            return

        output_dir = self.output_dir_var.get().strip() or None
        cookies_browser = self.cookies_browser_var.get().strip()
        cookies_file = self.cookies_file_var.get().strip() or None
        self._run_worker(
            "Fetching linked video...",
            lambda: self._worker_fetch_video_link(video_url, output_dir, cookies_browser, cookies_file),
        )

    def _worker_fetch_video_link(
        self,
        video_url: str,
        output_dir: str | None,
        cookies_browser: str | None,
        cookies_file: str | None,
    ) -> None:
        try:
            video_path = download_video_from_url(
                video_url,
                output_dir=output_dir,
                logger=self._queue_log,
                cookies_browser=cookies_browser,
                cookies_file=cookies_file,
            )
        except Exception as exc:
            self.events.put(("error", str(exc)))
            return

        self.events.put(("download_done", {"video_path": video_path}))

    def _build_config(self) -> tuple[WorkflowConfig, dict[str, str]]:
        video = self.video_var.get().strip()
        if not video:
            raise ValueError("Choose a video file first.")

        video_path = Path(video).expanduser()
        if not video_path.is_file():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        selected_source = find_original_video_for_generated_output(video_path)
        if selected_source is not None:
            video_path = selected_source
            video = str(video_path)
            self.video_var.set(video)
            self._append_log(f"Using original source video instead of generated output: {video}")

        output_dir = self.output_dir_var.get().strip() or None
        output_paths = build_default_output_paths(video, output_dir)

        chunk_seconds = int(self.chunk_seconds_var.get().strip())
        original_volume = float(self.original_volume_var.get().strip())
        if chunk_seconds <= 0:
            raise ValueError("Chunk seconds must be greater than 0.")
        if not 0 <= original_volume <= 1:
            raise ValueError("Background volume must be between 0 and 1.")

        keep_original_audio, preserve_background_audio = self._selected_original_audio_flags()
        config = WorkflowConfig(
            video=str(video_path),
            speech_lang=self._language_code(self.speech_lang_var, "en-US"),
            source_lang=self._language_code(self.source_lang_var, "auto"),
            target_lang=self._language_code(self.target_lang_var, "km"),
            voice_lang=self._language_code(self.voice_lang_var, "km"),
            voice_gender=self._voice_gender(),
            transcription_engine=self.transcription_engine_var.get().strip() or "auto",
            whisper_model=self.whisper_model_var.get().strip() or "medium",
            hf_token=self.hf_token_var.get().strip(),
            repair_transcript_with_ollama=self.repair_transcript_var.get(),
            ollama_model=self.ollama_model_var.get().strip() or "llava:latest",
            skip_translation=self.skip_translation_var.get(),
            skip_voice=not self.generate_voice_var.get(),
            transcript_out=output_paths["transcript_out"],
            subtitle_out=output_paths["subtitle_out"],
            translated_subtitle_out=output_paths["translated_subtitle_out"],
            translated_text_out=output_paths["translated_text_out"],
            audio_out=output_paths["audio_out"],
            output=output_paths["output"],
            keep_original_audio=keep_original_audio,
            preserve_background_audio=preserve_background_audio,
            original_volume=original_volume,
            slow_voice=self.slow_voice_var.get(),
            chunk_seconds=chunk_seconds,
        )
        return config, output_paths

    def _queue_log(self, message: str) -> None:
        self.events.put(("log", message))

    def _selected_original_audio_flags(self) -> tuple[bool, bool]:
        mode = self.original_audio_mode_var.get()
        if mode == "Keep full original audio":
            return True, False
        if mode == "Remove all original audio":
            return False, False
        return False, True

    def _set_busy(self, busy: bool, status: str) -> None:
        self.busy = busy
        self.status_var.set(status)
        progress = getattr(self, "busy_progress", None)
        if progress is not None:
            if busy:
                progress.start(12)
            else:
                progress.stop()

    def _run_worker(self, status: str, worker) -> None:
        if self.busy:
            return

        self._set_busy(True, status)
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _start_analysis(self) -> None:
        try:
            config, output_paths = self._build_config()
        except Exception as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        self.current_output_paths = output_paths
        self.khmer_path_var.set(output_paths["translated_text_out"])
        self.audio_path_var.set(output_paths["audio_out"])
        self.output_video_var.set(output_paths["output"])
        self._run_worker("Analyzing video...", lambda: self._worker_analysis(config, output_paths))

    def _worker_analysis(self, config: WorkflowConfig, output_paths: dict[str, str]) -> None:
        try:
            analysis = analyze_video(config, logger=self._queue_log)
        except Exception as exc:
            self.events.put(("error", str(exc)))
            return

        self.events.put(("analysis_done", {"analysis": analysis, "paths": output_paths}))

    def _start_retranslate(self) -> None:
        try:
            config, output_paths = self._build_config()
        except Exception as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        transcript_text = self._get_text(self.transcript_text)
        if not transcript_text:
            messagebox.showerror("Transcript missing", "Analyze the video first or paste transcript text here.")
            return

        self.current_output_paths = output_paths
        self._run_worker(
            "Translating transcript...",
            lambda: self._worker_retranslate(config, output_paths, transcript_text),
        )

    def _worker_retranslate(
        self,
        config: WorkflowConfig,
        output_paths: dict[str, str],
        transcript_text: str,
    ) -> None:
        try:
            self._queue_log("Re-translating the transcript to Khmer...")
            translated_text = transcript_text if config.skip_translation else translate_text(
                transcript_text,
                target_lang=config.target_lang,
                source_lang=config.source_lang,
            )
            save_text(transcript_text, output_paths["transcript_out"])
            translated_text_path = save_text(translated_text, output_paths["translated_text_out"])
        except Exception as exc:
            self.events.put(("error", str(exc)))
            return

        self.events.put(
            (
                "retranslate_done",
                {
                    "transcript_text": transcript_text,
                    "translated_text": translated_text,
                    "translated_text_path": translated_text_path,
                },
            )
        )

    def _save_current_khmer_script(self) -> None:
        if not self.current_output_paths:
            try:
                _, output_paths = self._build_config()
                self.current_output_paths = output_paths
            except Exception as exc:
                messagebox.showerror("Cannot save", str(exc))
                return

        khmer_text = self._get_text(self.khmer_text)
        if not khmer_text:
            messagebox.showerror("Khmer script missing", "There is no Khmer script to save.")
            return

        save_path = save_text(khmer_text, self.current_output_paths["translated_text_out"])
        self.khmer_path_var.set(save_path)
        self._append_log(f"Saved Khmer script to: {save_path}")

    def _start_voice_only(self) -> None:
        try:
            config, output_paths = self._build_config()
        except Exception as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        khmer_text = self._get_text(self.khmer_text)
        if not khmer_text:
            messagebox.showerror("Khmer script missing", "Analyze the video first or type Khmer script before generating voice.")
            return

        self.current_output_paths = output_paths
        self._run_worker(
            "Generating Khmer voice...",
            lambda: self._worker_voice_only(config, output_paths, khmer_text),
        )

    def _worker_voice_only(
        self,
        config: WorkflowConfig,
        output_paths: dict[str, str],
        khmer_text: str,
    ) -> None:
        try:
            save_text(khmer_text, output_paths["translated_text_out"])
            analysis = self.current_analysis
            voice_result = build_voice_with_timing(
                khmer_text,
                output_file=output_paths["audio_out"],
                voice_lang=config.voice_lang,
                voice_gender=config.voice_gender,
                slow_voice=config.slow_voice,
                timed_segments=analysis.translated_segments if analysis else None,
                logger=self._queue_log,
            )
            if analysis is not None and voice_result.timed_segments:
                analysis = replace(
                    analysis,
                    translated_text=khmer_text,
                    translated_text_path=output_paths["translated_text_out"],
                )
                analysis = save_voice_synced_subtitles(
                    analysis,
                    voice_result.timed_segments,
                    output_paths["translated_subtitle_out"],
                    logger=self._queue_log,
                )
        except Exception as exc:
            self.events.put(("error", str(exc)))
            return

        self.events.put(("voice_done", {"audio_path": voice_result.audio_path, "analysis": analysis}))

    def _start_build_final(self) -> None:
        try:
            config, output_paths = self._build_config()
        except Exception as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        self.current_output_paths = output_paths
        khmer_text = self._get_text(self.khmer_text)
        transcript_text = self._get_text(self.transcript_text)
        self._run_worker(
            "Building final video...",
            lambda: self._worker_build_final(config, output_paths, transcript_text, khmer_text),
        )

    def _worker_build_final(
        self,
        config: WorkflowConfig,
        output_paths: dict[str, str],
        transcript_text: str,
        khmer_text: str,
    ) -> None:
        analysis: AnalysisResult | None = None
        base_analysis: AnalysisResult | None = None

        try:
            if not khmer_text:
                analysis = analyze_video(config, logger=self._queue_log)
                khmer_text = analysis.translated_text
                transcript_text = analysis.source_text
            else:
                save_text(khmer_text, output_paths["translated_text_out"])
                if transcript_text:
                    save_text(transcript_text, output_paths["transcript_out"])

            base_analysis = analysis if analysis is not None else self.current_analysis
            voice_result = build_voice_with_timing(
                khmer_text,
                output_file=output_paths["audio_out"],
                voice_lang=config.voice_lang,
                voice_gender=config.voice_gender,
                slow_voice=config.slow_voice,
                timed_segments=base_analysis.translated_segments if base_analysis else None,
                logger=self._queue_log,
            )
            if base_analysis is not None and voice_result.timed_segments:
                base_analysis = replace(
                    base_analysis,
                    translated_text=khmer_text,
                    translated_text_path=output_paths["translated_text_out"],
                )
                base_analysis = save_voice_synced_subtitles(
                    base_analysis,
                    voice_result.timed_segments,
                    output_paths["translated_subtitle_out"],
                    logger=self._queue_log,
                )
            output_video_path, video_extended = build_output_video(
                config.video,
                voice_result.audio_path,
                output_file=output_paths["output"],
                keep_original_audio=config.keep_original_audio,
                preserve_background_audio=config.preserve_background_audio,
                original_volume=config.original_volume,
                extend_to_narration=not bool(voice_result.timed_segments),
                logger=self._queue_log,
            )
        except Exception as exc:
            self.events.put(("error", str(exc)))
            return

        self.events.put(
            (
                "final_done",
                {
                    "analysis": base_analysis if base_analysis is not None else analysis,
                    "transcript_text": transcript_text,
                    "khmer_text": khmer_text,
                    "audio_path": voice_result.audio_path,
                    "output_video_path": output_video_path,
                    "video_extended": video_extended,
                },
            )
        )

    def _handle_event_error(self, message: str) -> None:
        self._set_busy(False, "Failed")
        self._append_log(f"Error: {message}")
        messagebox.showerror("Workflow failed", message)

    def _handle_analysis_done(self, payload: object) -> None:
        self._set_busy(False, "Analysis complete")
        if not isinstance(payload, dict):
            return

        analysis = payload.get("analysis")
        if not isinstance(analysis, AnalysisResult):
            return

        self.current_analysis = analysis
        self._replace_text(self.transcript_text, analysis.source_text)
        self._replace_text(self.khmer_text, analysis.translated_text)
        self.khmer_path_var.set(analysis.translated_text_path)
        self._append_log("You can edit the Khmer script now, then click Build Final Video.")

    def _handle_download_done(self, payload: object) -> None:
        self._set_busy(False, "Video ready")
        if not isinstance(payload, dict):
            return

        video_path = str(payload.get("video_path", ""))
        if not video_path:
            return

        self.video_var.set(video_path)
        if not self.output_dir_var.get().strip():
            self.output_dir_var.set(str(Path(video_path).expanduser().parent))

        self.current_analysis = None
        self.current_audio_path = None
        self.current_output_video_path = None
        self.output_video_var.set("")
        self.audio_path_var.set("")
        self.khmer_path_var.set("")
        self._replace_text(self.transcript_text, "")
        self._replace_text(self.khmer_text, "")
        self._append_log("Linked video is ready. Click Analyze Video to generate the script.")
        self._load_preview(video_path)

    def _handle_retranslate_done(self, payload: object) -> None:
        self._set_busy(False, "Translation complete")
        if not isinstance(payload, dict):
            return

        translated_text = str(payload.get("translated_text", ""))
        translated_text_path = str(payload.get("translated_text_path", ""))
        self._replace_text(self.khmer_text, translated_text)
        self.khmer_path_var.set(translated_text_path)
        self._append_log(f"Saved Khmer text to: {translated_text_path}")

    def _handle_voice_done(self, payload: object) -> None:
        self._set_busy(False, "Voice ready")
        if not isinstance(payload, dict):
            return

        audio_path = str(payload.get("audio_path", ""))
        analysis = payload.get("analysis")
        if isinstance(analysis, AnalysisResult):
            self.current_analysis = analysis
        self.current_audio_path = audio_path
        self.audio_path_var.set(audio_path)
        self._append_log("Voice generation finished.")

    def _handle_final_done(self, payload: object) -> None:
        self._set_busy(False, "Final video ready")
        if not isinstance(payload, dict):
            return

        analysis = payload.get("analysis")
        if isinstance(analysis, AnalysisResult):
            self.current_analysis = analysis
            self._replace_text(self.transcript_text, analysis.source_text)
            self._replace_text(self.khmer_text, analysis.translated_text)
            self.khmer_path_var.set(analysis.translated_text_path)
        else:
            self._replace_text(self.transcript_text, str(payload.get("transcript_text", "")))
            self._replace_text(self.khmer_text, str(payload.get("khmer_text", "")))

        audio_path = str(payload.get("audio_path", ""))
        output_video_path = str(payload.get("output_video_path", ""))
        video_extended = bool(payload.get("video_extended", False))

        self.current_audio_path = audio_path
        self.current_output_video_path = output_video_path
        self.audio_path_var.set(audio_path)
        self.output_video_var.set(output_video_path)
        self._append_log(f"Final video created: {output_video_path}")
        if video_extended:
            self._append_log("The video was extended to keep the full Khmer voice.")

        if output_video_path and Path(output_video_path).is_file():
            self._load_preview(output_video_path)

        messagebox.showinfo("Done", "Final video is ready.")

    def _poll_events(self) -> None:
        while True:
            try:
                event_type, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event_type == "log":
                self._append_log(str(payload))
            elif event_type == "error":
                self._handle_event_error(str(payload))
            elif event_type == "download_done":
                self._handle_download_done(payload)
            elif event_type == "analysis_done":
                self._handle_analysis_done(payload)
            elif event_type == "retranslate_done":
                self._handle_retranslate_done(payload)
            elif event_type == "voice_done":
                self._handle_voice_done(payload)
            elif event_type == "final_done":
                self._handle_final_done(payload)

        self.root.after(100, self._poll_events)

    def _format_time(self, seconds: float) -> str:
        seconds = max(0, int(seconds))
        minutes, secs = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02}:{minutes:02}:{secs:02}"
        return f"{minutes:02}:{secs:02}"

    def _update_time_label(self) -> None:
        self.preview_time_var.set(
            f"{self._format_time(self.preview_current_time)} / {self._format_time(self.preview_duration)}"
        )

    def _close_preview_clip(self) -> None:
        if self.preview_after_id is not None:
            self.root.after_cancel(self.preview_after_id)
            self.preview_after_id = None

        if self.preview_resize_after_id is not None:
            self.root.after_cancel(self.preview_resize_after_id)
            self.preview_resize_after_id = None

        self.preview_playing = False
        if self.preview_clip is not None:
            self.preview_clip.close()
            self.preview_clip = None

    def _schedule_preview_resize(self, _event: object | None = None) -> None:
        if self.preview_clip is None:
            return

        if self.preview_resize_after_id is not None:
            self.root.after_cancel(self.preview_resize_after_id)

        self.preview_resize_after_id = self.root.after(120, self._redraw_preview_frame)

    def _redraw_preview_frame(self) -> None:
        self.preview_resize_after_id = None
        if self.preview_clip is None:
            return

        self._show_preview_frame(self.preview_current_time)

    def _load_preview(self, video_path: str) -> None:
        path = Path(video_path).expanduser()
        if not path.is_file():
            messagebox.showerror("Preview error", f"Video file not found: {path}")
            return

        self._close_preview_clip()

        try:
            try:
                from moviepy.editor import VideoFileClip
            except ImportError:
                from moviepy import VideoFileClip

            self.preview_clip = VideoFileClip(str(path))
            self.preview_duration = float(self.preview_clip.duration or 0.0)
            self.preview_fps = float(getattr(self.preview_clip, "fps", 24.0) or 24.0)
            self.preview_path = str(path)
            self.preview_current_time = 0.0
            self.current_video_label_var.set(str(path))
            self.ignore_seek = True
            self.preview_scale.configure(to=max(self.preview_duration, 1.0))
            self.preview_position_var.set(0.0)
            self.ignore_seek = False
            self._show_preview_frame(0.0)
            self._update_time_label()
            self.play_button.config(text="Play")
        except Exception as exc:
            self._close_preview_clip()
            messagebox.showerror("Preview error", str(exc))

    def _show_preview_frame(self, timestamp: float) -> None:
        if self.preview_clip is None or self.preview_duration <= 0:
            self.preview_surface.configure(text="Choose a video to preview", image="")
            return

        safe_time = min(max(0.0, timestamp), max(0.0, self.preview_duration - 0.04))
        frame = self.preview_clip.get_frame(safe_time)
        image = Image.fromarray(frame)

        viewport = self.preview_viewport or self.preview_surface
        width = viewport.winfo_width()
        height = viewport.winfo_height()
        if width <= 2 or height <= 2:
            width, height = 520, 220

        image.thumbnail((max(1, width - 8), max(1, height - 8)), RESAMPLING)

        photo = ImageTk.PhotoImage(image)
        self.preview_image = photo
        self.preview_surface.configure(image=photo, text="")
        self.preview_current_time = safe_time
        self.ignore_seek = True
        self.preview_position_var.set(safe_time)
        self.ignore_seek = False
        self._update_time_label()

    def _advance_preview(self) -> None:
        if not self.preview_playing or self.preview_clip is None:
            return

        next_time = self.preview_current_time + (1.0 / max(self.preview_fps, 12.0))
        if next_time >= self.preview_duration:
            self.preview_playing = False
            self.play_button.config(text="Play")
            self._show_preview_frame(max(0.0, self.preview_duration - 0.04))
            return

        self._show_preview_frame(next_time)
        delay = int(1000 / max(self.preview_fps, 12.0))
        self.preview_after_id = self.root.after(delay, self._advance_preview)

    def _toggle_preview_playback(self) -> None:
        if self.preview_clip is None:
            return

        if self.preview_playing:
            self.preview_playing = False
            self.play_button.config(text="Play")
            if self.preview_after_id is not None:
                self.root.after_cancel(self.preview_after_id)
                self.preview_after_id = None
            return

        self.preview_playing = True
        self.play_button.config(text="Pause")
        self._advance_preview()

    def _handle_seek(self, _value: str) -> None:
        if self.ignore_seek or self.preview_clip is None:
            return

        if self.preview_after_id is not None:
            self.root.after_cancel(self.preview_after_id)
            self.preview_after_id = None

        self.preview_playing = False
        self.play_button.config(text="Play")
        self._show_preview_frame(float(self.preview_position_var.get()))

    def _preview_input(self) -> None:
        video = self.video_var.get().strip()
        if not video:
            messagebox.showerror("No video", "Choose an input video first.")
            return
        self._load_preview(video)

    def _preview_output(self) -> None:
        output_video = self.output_video_var.get().strip() or self.current_output_video_path
        if not output_video or not Path(output_video).is_file():
            messagebox.showerror("No output video", "Build the final video first.")
            return
        self._load_preview(output_video)

    def _open_path(self, path: str) -> None:
        if not path:
            return

        target = str(Path(path).expanduser())
        if sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
            return

        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
            return

        subprocess.Popen(["xdg-open", target])

    def _open_current_video(self) -> None:
        path = self.preview_path or self.output_video_var.get().strip() or self.video_var.get().strip()
        if not path or not Path(path).is_file():
            messagebox.showerror("No video", "There is no video to open.")
            return
        self._open_path(path)

    def _open_output_folder(self) -> None:
        if self.current_output_paths:
            folder = Path(next(iter(self.current_output_paths.values()))).expanduser().parent
        else:
            video = self.video_var.get().strip()
            folder = Path(video).expanduser().parent if video else Path.cwd()

        self._open_path(str(folder))

    def _on_close(self) -> None:
        self._close_preview_clip()
        self.root.destroy()


def launch_gui() -> None:
    root = tk.Tk()
    KhmerVideoUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
