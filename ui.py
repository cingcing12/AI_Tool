from __future__ import annotations

import math
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

# ---------------------------------------------------------------------------
# Visual Theme & Professional Color Palette
# ---------------------------------------------------------------------------
COLOR_BG_ROOT = "#0B0F19"         # Ultra-dark cosmic canvas
COLOR_BG_CARD = "#121826"         # Elevated surface for panels & cards
COLOR_BG_CARD_ALT = "#161F33"     # Secondary elevated header/sub-deck
COLOR_BG_INNER = "#070A10"        # Viewport, editor, and console background
COLOR_BG_INPUT = "#0D1424"        # Input fields and combobox entry backgrounds
COLOR_BORDER_SUBTLE = "#1E293B"   # Resting borders
COLOR_BORDER_LIGHT = "#2A3854"    # Highlighted / input borders
COLOR_BORDER_FOCUS = "#00F2FE"    # Active cyan focus ring

COLOR_TEXT_WHITE = "#F8FAFC"      # High-contrast title and value text
COLOR_TEXT_LIGHT = "#E2E8F0"      # Readable body text
COLOR_TEXT_MUTED = "#8B9BB4"      # Secondary metadata / labels
COLOR_TEXT_DIM = "#52627A"        # Disabled / subtle captions

COLOR_CYAN = "#00F2FE"            # Electric Cyan
COLOR_CYAN_HOVER = "#38BDF8"      # Bright Sky Hover
COLOR_CYAN_DEEP = "#0284C7"       # Solid Cyan Button Base

COLOR_EMERALD = "#10B981"         # Vivid Emerald (Final Build / Ready)
COLOR_EMERALD_HOVER = "#34D399"   # Mint Hover
COLOR_EMERALD_DEEP = "#059669"    # Emerald Button Base

COLOR_PURPLE = "#8B5CF6"          # Studio Violet (Translation & Voice)
COLOR_PURPLE_HOVER = "#A855F7"    # Bright Purple Hover
COLOR_PURPLE_DEEP = "#6D28D9"     # Deep Purple Base

COLOR_AMBER = "#F59E0B"           # Energetic Amber (Processing/Alert)
COLOR_ROSE = "#F43F5E"            # Electric Rose (Error/Cancel)
COLOR_SLATE_BTN = "#1E293B"       # Dark Slate Tool Button
COLOR_SLATE_BTN_HOVER = "#2D3D58" # Slate Hover

PALETTE_CYBER = (
    "#00F2FE", "#38BDF8", "#60A5FA", "#818CF8", "#A855F7", "#C084FC", "#EC4899"
)
PALETTE_CYAN_PURPLE = (
    "#00F2FE", "#38BDF8", "#0284C7", "#6366F1", "#8B5CF6", "#A855F7"
)
PALETTE_BUSY = (
    "#00F2FE", "#34D399", "#10B981", "#059669", "#38BDF8", "#6EE7B7"
)


# ---------------------------------------------------------------------------
# High-Tech Custom Animated UI Widgets
# ---------------------------------------------------------------------------
class AnimatedBorderCard(tk.Frame):
    """A card framed by an orbiting glowing gradient laser beam along its perimeter."""

    def __init__(
        self,
        parent,
        title: str = "",
        badge: str = "",
        icon: str = "",
        bg: str = COLOR_BG_CARD,
        header_bg: str = COLOR_BG_CARD_ALT,
        border_color: str = COLOR_BORDER_SUBTLE,
        palette: tuple[str, ...] | None = None,
        busy_palette: tuple[str, ...] | None = None,
        border_width: int = 2,
        beam_len: int = 140,
        speed: int = 3,
        num_beams: int = 2,
        padding: int = 10,
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=bg, **kwargs)
        self.bg = bg
        self.base_border_color = border_color
        self.border_width = border_width
        self.beam_len = beam_len
        self.normal_speed = speed
        self.busy_speed = max(speed * 2, 6)
        self.speed = speed
        self.num_beams = num_beams
        self.palette = palette or PALETTE_CYBER
        self.busy_palette = busy_palette or PALETTE_BUSY
        self.current_palette = self.palette
        self.beam_pos = 0.0
        self.after_id: str | None = None
        self.w = 100
        self.h = 100
        self.is_busy = False

        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.container = tk.Frame(self.canvas, bg=bg)
        self.win_id = self.canvas.create_window(
            self.border_width, self.border_width, window=self.container, anchor="nw"
        )

        if title:
            h = tk.Frame(self.container, bg=header_bg, padx=padding, pady=8)
            h.pack(fill="x")
            lbl = tk.Label(
                h,
                text=f"{icon}  {title}" if icon else title,
                bg=header_bg,
                fg=COLOR_TEXT_WHITE,
                font=("Segoe UI", 9, "bold"),
            )
            lbl.pack(side="left")
            if badge:
                b = tk.Label(
                    h,
                    text=badge,
                    bg=COLOR_BORDER_SUBTLE,
                    fg=COLOR_CYAN,
                    font=("Segoe UI", 8, "bold"),
                    padx=7,
                    pady=2,
                )
                b.pack(side="right")
            div = tk.Frame(self.container, bg=border_color, height=1)
            div.pack(fill="x")

        self.body = tk.Frame(self.container, bg=bg, padx=padding, pady=padding)
        self.body.pack(fill="both", expand=True)

        self.canvas.bind("<Configure>", self._on_configure)
        self.bind("<Destroy>", self._on_destroy)
        self._start_animation()

    def _on_destroy(self, _event=None) -> None:
        self.stop()

    def stop(self) -> None:
        if self.after_id is not None:
            try:
                self.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _on_configure(self, event) -> None:
        self.w = max(10, event.width)
        self.h = max(10, event.height)
        bw = self.border_width
        self.canvas.coords(self.win_id, bw, bw)
        self.canvas.itemconfigure(
            self.win_id,
            width=max(1, self.w - 2 * bw),
            height=max(1, self.h - 2 * bw),
        )
        self._draw_base_border()

    def _draw_base_border(self) -> None:
        self.canvas.delete("base_border")
        bw = self.border_width
        half = bw / 2.0
        self.canvas.create_rectangle(
            half,
            half,
            self.w - half,
            self.h - half,
            outline=self.base_border_color,
            width=bw,
            tags="base_border",
        )

    def _get_perimeter_point(self, d: float, pw: float, ph: float) -> tuple[float, float]:
        p = 2.0 * (pw + ph)
        if p <= 0:
            return (0.0, 0.0)
        d = d % p
        if d <= pw:
            return (d, 0.0)
        d -= pw
        if d <= ph:
            return (pw, d)
        d -= ph
        if d <= pw:
            return (pw - d, ph)
        d -= pw
        return (0.0, ph - d)

    def _get_path_between(
        self, d1: float, d2: float, pw: float, ph: float, ox: float, oy: float
    ) -> list[tuple[float, float]]:
        p = 2.0 * (pw + ph)
        if p <= 0:
            return []
        d1 = d1 % p
        d2 = d2 % p
        corner_pts = {
            pw: (pw + ox, oy),
            pw + ph: (pw + ox, ph + oy),
            2.0 * pw + ph: (ox, ph + oy),
            0.0: (ox, oy),
            p: (ox, oy),
        }
        pt1 = self._get_perimeter_point(d1, pw, ph)
        pts = [(pt1[0] + ox, pt1[1] + oy)]
        dist = (d2 - d1) % p
        for c in [pw, pw + ph, 2.0 * pw + ph, p]:
            cdist = (c - d1) % p
            if 0.0 < cdist < dist:
                pts.append(corner_pts[c])
        pt2 = self._get_perimeter_point(d2, pw, ph)
        pts.append((pt2[0] + ox, pt2[1] + oy))
        return pts

    def _start_animation(self) -> None:
        if not self.winfo_exists():
            return
        self._step_animation()

    def _step_animation(self) -> None:
        self.after_id = None
        if not self.winfo_exists():
            return

        bw = self.border_width
        ox = bw / 2.0
        oy = bw / 2.0
        pw = max(1.0, float(self.w - 2 * ox))
        ph = max(1.0, float(self.h - 2 * oy))
        p = 2.0 * (pw + ph)

        if p > 30:
            self.canvas.delete("beam")
            palette = self.current_palette
            num_steps = len(palette)
            step_len = self.beam_len / float(num_steps)

            for b in range(self.num_beams):
                base_beam = (self.beam_pos + b * (p / float(self.num_beams))) % p
                for i, color in enumerate(palette):
                    d_tail = (base_beam - (i + 1) * step_len) % p
                    d_head = (base_beam - i * step_len) % p
                    path = self._get_path_between(d_tail, d_head, pw, ph, ox, oy)
                    if len(path) >= 2:
                        flat_coords = [coord for pt in path for coord in pt]
                        self.canvas.create_line(
                            *flat_coords,
                            tags="beam",
                            fill=color,
                            width=bw,
                            capstyle="round",
                            joinstyle="round",
                        )

            self.beam_pos = (self.beam_pos + self.speed) % p

        self.after_id = self.after(35, self._step_animation)

    def set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        if busy:
            self.current_palette = self.busy_palette
            self.speed = self.busy_speed
        else:
            self.current_palette = self.palette
            self.speed = self.normal_speed


class ModernCard(tk.Frame):
    """A sleek studio container with crisp outline and header bar."""

    def __init__(
        self,
        parent,
        title: str = "",
        badge: str = "",
        icon: str = "",
        bg: str = COLOR_BG_CARD,
        header_bg: str = COLOR_BG_CARD_ALT,
        border_color: str = COLOR_BORDER_SUBTLE,
        padding: int = 10,
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=border_color, padx=1, pady=1, **kwargs)
        self.inner = tk.Frame(self, bg=bg)
        self.inner.pack(fill="both", expand=True)

        if title:
            h = tk.Frame(self.inner, bg=header_bg, padx=padding, pady=7)
            h.pack(fill="x")
            lbl = tk.Label(
                h,
                text=f"{icon}  {title}" if icon else title,
                bg=header_bg,
                fg=COLOR_TEXT_WHITE,
                font=("Segoe UI", 9, "bold"),
            )
            lbl.pack(side="left")
            if badge:
                b = tk.Label(
                    h,
                    text=badge,
                    bg=COLOR_BORDER_SUBTLE,
                    fg=COLOR_CYAN_HOVER,
                    font=("Segoe UI", 8, "bold"),
                    padx=7,
                    pady=2,
                )
                b.pack(side="right")
            div = tk.Frame(self.inner, bg=border_color, height=1)
            div.pack(fill="x")

        self.body = tk.Frame(self.inner, bg=bg, padx=padding, pady=padding)
        self.body.pack(fill="both", expand=True)


class PulsingStatusDot(tk.Canvas):
    """An animated pulsing LED beacon representing system activity."""

    def __init__(self, parent, size: int = 16, bg: str = COLOR_BG_CARD, **kwargs) -> None:
        super().__init__(
            parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0, **kwargs
        )
        self.size = size
        self.state = "ready"
        self.phase = 0.0
        self.after_id: str | None = None
        self._animate()

    def set_state(self, state: str) -> None:
        self.state = state

    def stop(self) -> None:
        if self.after_id is not None:
            try:
                self.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _animate(self) -> None:
        self.after_id = None
        if not self.winfo_exists():
            return

        self.delete("all")
        c = self.size / 2.0
        self.phase = (self.phase + 0.16) % (2.0 * math.pi)
        glow_factor = (math.sin(self.phase) + 1.0) / 2.0

        if self.state == "busy":
            glow_r = 5.0 + 3.0 * glow_factor
            core_r = 3.5
            self.create_oval(
                c - glow_r, c - glow_r, c + glow_r, c + glow_r, fill="#0369A1", outline=""
            )
            self.create_oval(
                c - core_r, c - core_r, c + core_r, c + core_r, fill=COLOR_CYAN, outline=""
            )
        elif self.state == "error":
            glow_r = 4.5 + 2.0 * glow_factor
            core_r = 3.5
            self.create_oval(
                c - glow_r, c - glow_r, c + glow_r, c + glow_r, fill="#991B1B", outline=""
            )
            self.create_oval(
                c - core_r, c - core_r, c + core_r, c + core_r, fill=COLOR_ROSE, outline=""
            )
        else:  # ready
            glow_r = 4.0 + 2.5 * glow_factor
            core_r = 3.2
            self.create_oval(
                c - glow_r, c - glow_r, c + glow_r, c + glow_r, fill="#064E3B", outline=""
            )
            self.create_oval(
                c - core_r, c - core_r, c + core_r, c + core_r, fill=COLOR_EMERALD, outline=""
            )

        self.after_id = self.after(50, self._animate)


class AutoScrollbar(ttk.Scrollbar):
    """A ttk.Scrollbar that automatically hides itself when content fits without scrolling."""

    def set(self, lo, hi) -> None:
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.pack_forget()
        else:
            if self not in self.master.pack_slaves():
                self.pack(side="right", fill="y")
        super().set(lo, hi)


class ScrollableFrame(tk.Frame):
    """A smooth scrollable container with an auto-hiding scrollbar."""

    def __init__(self, parent, bg: str = COLOR_BG_CARD, **kwargs) -> None:
        super().__init__(parent, bg=bg, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = AutoScrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_content = tk.Frame(self.canvas, bg=bg)

        self.scrollable_content.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.win_id = self.canvas.create_window((0, 0), window=self.scrollable_content, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.win_id, width=event.width)

    def _bind_mousewheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# ---------------------------------------------------------------------------
# Main Application UI Class
# ---------------------------------------------------------------------------
class KhmerVideoUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AI Somray Khmer Studio — Neural Video Dubbing")
        self.root.geometry("1260x720")
        self.root.minsize(980, 620)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.animated_cards: list[AnimatedBorderCard] = []

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

        # Dedicated Progress Tracking
        self.progress_percent_var = tk.DoubleVar(value=0.0)
        self.progress_text_var = tk.StringVar(value="Ready to export")

        self._configure_styles()
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_events)

    def _configure_styles(self) -> None:
        self.root.configure(bg=COLOR_BG_ROOT)

        # Style Combobox dropdown listbox popups
        self.root.option_add("*TCombobox*Listbox.background", COLOR_BG_INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", COLOR_TEXT_WHITE)
        self.root.option_add("*TCombobox*Listbox.selectBackground", COLOR_CYAN_DEEP)
        self.root.option_add("*TCombobox*Listbox.selectForeground", COLOR_TEXT_WHITE)

        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background=COLOR_BG_ROOT)
        style.configure("Card.TFrame", background=COLOR_BG_CARD)
        style.configure("CardAlt.TFrame", background=COLOR_BG_CARD_ALT)
        style.configure("Header.TFrame", background=COLOR_BG_CARD_ALT)

        style.configure("App.TLabel", background=COLOR_BG_ROOT, foreground=COLOR_TEXT_WHITE)
        style.configure("Card.TLabel", background=COLOR_BG_CARD, foreground=COLOR_TEXT_LIGHT, font=("Segoe UI", 9))
        style.configure("CardBold.TLabel", background=COLOR_BG_CARD, foreground=COLOR_TEXT_WHITE, font=("Segoe UI", 9, "bold"))
        style.configure("Section.TLabel", background=COLOR_BG_CARD, foreground=COLOR_CYAN, font=("Segoe UI", 9, "bold"))
        style.configure("Muted.TLabel", background=COLOR_BG_CARD, foreground=COLOR_TEXT_MUTED, font=("Segoe UI", 8))
        style.configure("Badge.TLabel", background=COLOR_BORDER_SUBTLE, foreground=COLOR_CYAN, font=("Segoe UI", 8, "bold"))

        style.configure(
            "Path.TEntry",
            fieldbackground=COLOR_BG_INPUT,
            foreground=COLOR_TEXT_WHITE,
            insertcolor=COLOR_CYAN,
            bordercolor=COLOR_BORDER_LIGHT,
            lightcolor=COLOR_BORDER_LIGHT,
            darkcolor=COLOR_BORDER_LIGHT,
        )
        style.map(
            "Path.TEntry",
            bordercolor=[("focus", COLOR_BORDER_FOCUS)],
            lightcolor=[("focus", COLOR_BORDER_FOCUS)],
            darkcolor=[("focus", COLOR_BORDER_FOCUS)],
        )

        style.configure(
            "Dark.TCombobox",
            fieldbackground=COLOR_BG_INPUT,
            background=COLOR_BORDER_SUBTLE,
            foreground=COLOR_TEXT_WHITE,
            arrowcolor=COLOR_CYAN,
            bordercolor=COLOR_BORDER_LIGHT,
            lightcolor=COLOR_BORDER_LIGHT,
            darkcolor=COLOR_BORDER_LIGHT,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", COLOR_BG_INPUT), ("focus", COLOR_BG_INPUT)],
            foreground=[("readonly", COLOR_TEXT_WHITE), ("focus", COLOR_TEXT_WHITE)],
            bordercolor=[("focus", COLOR_BORDER_FOCUS)],
            lightcolor=[("focus", COLOR_BORDER_FOCUS)],
            darkcolor=[("focus", COLOR_BORDER_FOCUS)],
        )

        style.configure(
            "Dark.TCheckbutton",
            background=COLOR_BG_CARD,
            foreground=COLOR_TEXT_LIGHT,
            indicatorbackground=COLOR_BG_INPUT,
            indicatorforeground=COLOR_CYAN,
            font=("Segoe UI", 9),
        )

        style.configure(
            "Accent.TButton",
            padding=(10, 6),
            background=COLOR_CYAN_DEEP,
            foreground=COLOR_TEXT_WHITE,
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLOR_CYAN_HOVER), ("disabled", COLOR_BORDER_SUBTLE)],
            foreground=[("disabled", COLOR_TEXT_DIM)],
        )

        style.configure(
            "Build.TButton",
            padding=(12, 7),
            background=COLOR_EMERALD_DEEP,
            foreground=COLOR_TEXT_WHITE,
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "Build.TButton",
            background=[("active", COLOR_EMERALD_HOVER), ("disabled", COLOR_BORDER_SUBTLE)],
            foreground=[("disabled", COLOR_TEXT_DIM)],
        )

        style.configure(
            "Purple.TButton",
            padding=(10, 6),
            background=COLOR_PURPLE_DEEP,
            foreground=COLOR_TEXT_WHITE,
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
        )
        style.map(
            "Purple.TButton",
            background=[("active", COLOR_PURPLE_HOVER), ("disabled", COLOR_BORDER_SUBTLE)],
            foreground=[("disabled", COLOR_TEXT_DIM)],
        )

        style.configure(
            "Soft.TButton",
            padding=(8, 5),
            background=COLOR_SLATE_BTN,
            foreground=COLOR_TEXT_WHITE,
            font=("Segoe UI", 9),
            borderwidth=0,
        )
        style.map(
            "Soft.TButton",
            background=[("active", COLOR_SLATE_BTN_HOVER), ("disabled", COLOR_BG_INNER)],
            foreground=[("disabled", COLOR_TEXT_DIM)],
        )

        style.configure(
            "Small.TButton",
            padding=(6, 3),
            background=COLOR_SLATE_BTN,
            foreground=COLOR_TEXT_WHITE,
            font=("Segoe UI", 8),
            borderwidth=0,
        )
        style.map(
            "Small.TButton",
            background=[("active", COLOR_SLATE_BTN_HOVER)],
        )

        style.configure(
            "Preview.Horizontal.TScale",
            background=COLOR_BG_CARD,
            troughcolor=COLOR_BG_INPUT,
            slidercolor=COLOR_CYAN,
            bordercolor=COLOR_BORDER_SUBTLE,
        )
        style.configure(
            "Busy.Horizontal.TProgressbar",
            background=COLOR_EMERALD,
            troughcolor=COLOR_BG_INPUT,
            bordercolor=COLOR_BORDER_SUBTLE,
        )
        style.configure("TPanedwindow", background=COLOR_BG_ROOT)

    def _build_layout(self) -> None:
        root_frame = ttk.Frame(self.root, style="App.TFrame", padding=10)
        root_frame.pack(fill="both", expand=True)

        self.header_status_dot = None

        # -------------------------------------------------------------
        # Main 2-Column Split: Video on Left, Options on Right!
        # -------------------------------------------------------------
        main_split = ttk.Panedwindow(root_frame, orient="horizontal")
        main_split.pack(fill="both", expand=True)

        left_container = ttk.Frame(main_split, style="App.TFrame")
        right_container = ttk.Frame(main_split, style="App.TFrame")

        main_split.add(left_container, weight=1)
        main_split.add(right_container, weight=1)

        self._build_video_section(left_container)
        self._build_options_section(right_container)

    def _build_video_section(self, parent: ttk.Frame) -> None:
        """Left Column: Clean, compact video player with Start Video controls."""
        self.preview_card = AnimatedBorderCard(
            parent,
            title="VIDEO PREVIEW MONITOR",
            badge="LIVE PLAYER",
            icon="🎬",
            bg=COLOR_BG_CARD,
            header_bg=COLOR_BG_CARD_ALT,
            border_color=COLOR_BORDER_SUBTLE,
            palette=PALETTE_CYAN_PURPLE,
            busy_palette=PALETTE_BUSY,
            border_width=2,
            beam_len=140,
            speed=3,
            num_beams=2,
            padding=10,
        )
        self.preview_card.pack(fill="both", expand=True)
        self.animated_cards.append(self.preview_card)

        body = self.preview_card.body
        self.preview_card_body = body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        # 1. Video Canvas / Viewport - reduced, compact height
        self.preview_viewport = tk.Frame(body, bg=COLOR_BG_INNER, height=260)
        self.preview_viewport.grid(row=0, column=0, sticky="nsew")
        self.preview_viewport.grid_propagate(False)
        self.preview_viewport.bind("<Configure>", self._schedule_preview_resize)

        self.preview_surface = tk.Label(
            self.preview_viewport,
            text="🎬 NO VIDEO LOADED\n\nChoose a video file or fetch a link on the right to start previewing",
            bg=COLOR_BG_INNER,
            fg=COLOR_TEXT_MUTED,
            anchor="center",
            justify="center",
            font=("Segoe UI", 11, "bold"),
        )
        self.preview_surface.place(relx=0.5, rely=0.5, anchor="center")

        # 2. Active Video Info Chip
        info_row = ttk.Frame(body, style="Card.TFrame")
        info_row.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        ttk.Label(info_row, text="Active Video:", style="CardBold.TLabel").pack(side="left", padx=(0, 6))
        self.video_chip_label = ttk.Label(
            info_row,
            textvariable=self.current_video_label_var,
            style="Card.TLabel",
            wraplength=380,
        )
        self.video_chip_label.pack(side="left", fill="x", expand=True)

        # 3. Main Video Player Controls Deck
        controls_frame = ttk.Frame(body, style="Card.TFrame")
        controls_frame.grid(row=2, column=0, sticky="ew", pady=(4, 6))

        # "Start Video" Button
        self.play_button = ttk.Button(
            controls_frame,
            text="▶ Start Video",
            style="Build.TButton",
            command=self._toggle_preview_playback,
        )
        self.play_button.pack(side="left", padx=(0, 8))

        # Scrubber Scale
        self.preview_scale = ttk.Scale(
            controls_frame,
            from_=0.0,
            to=1.0,
            variable=self.preview_position_var,
            command=self._handle_seek,
            style="Preview.Horizontal.TScale",
        )
        self.preview_scale.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Digital Timer Readout
        self.preview_time_label = tk.Label(
            controls_frame,
            textvariable=self.preview_time_var,
            bg=COLOR_BG_CARD,
            fg=COLOR_CYAN,
            font=("Consolas", 10, "bold"),
        )
        self.preview_time_label.pack(side="left")

        # 4. Quick Switcher & Open Player Actions
        quick_row = ttk.Frame(body, style="Card.TFrame")
        quick_row.grid(row=3, column=0, sticky="ew", pady=(2, 4))

        ttk.Button(quick_row, text="🎬 Source Video", style="Soft.TButton", command=self._preview_input).pack(side="left")
        ttk.Button(quick_row, text="✨ Exported Video", style="Soft.TButton", command=self._preview_output).pack(side="left", padx=(6, 0))
        ttk.Button(quick_row, text="↗ Open in Player", style="Soft.TButton", command=self._open_current_video).pack(side="left", padx=(6, 0))

        audio_hint = ttk.Label(
            quick_row,
            text="🔊 In-app preview is silent",
            style="Muted.TLabel",
        )
        audio_hint.pack(side="right")

        # Hidden text widgets to maintain full transcript, script and log API
        self.transcript_text = tk.Text(self.root)
        self.khmer_text = tk.Text(self.root)
        self.log_text = tk.Text(self.root)

    def _build_options_section(self, parent: ttk.Frame) -> None:
        """Right Column: Redesigned Studio Control & Export Deck with elevated cards."""
        options_card = ModernCard(
            parent,
            title="STUDIO CONTROL & EXPORT DECK",
            badge="AI PIPELINE",
            icon="⚙️",
            bg=COLOR_BG_CARD,
            header_bg=COLOR_BG_CARD_ALT,
            border_color=COLOR_BORDER_SUBTLE,
            padding=10,
        )
        options_card.pack(fill="both", expand=True)

        scrollable = ScrollableFrame(options_card.body, bg=COLOR_BG_CARD)
        scrollable.pack(fill="both", expand=True)
        container = scrollable.scrollable_content
        self.options_container = container

        # -------------------------------------------------------------
        # 1. Video Source Card Tile
        # -------------------------------------------------------------
        source_tile = tk.Frame(
            container,
            bg=COLOR_BG_CARD_ALT,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SUBTLE,
        )
        source_tile.pack(fill="x", pady=(0, 10))

        tk.Label(
            source_tile,
            text="📁 VIDEO SOURCE & DESTINATION",
            bg=COLOR_BG_CARD_ALT,
            fg=COLOR_CYAN,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        s_grid = tk.Frame(source_tile, bg=COLOR_BG_CARD_ALT)
        s_grid.pack(fill="x")
        s_grid.columnconfigure(1, weight=1)

        ttk.Label(s_grid, text="Local File", style="CardBold.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(s_grid, textvariable=self.video_var, style="Path.TEntry").grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(s_grid, text="Browse", style="Soft.TButton", command=self._browse_video).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(s_grid, text="Link / URL", style="CardBold.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(s_grid, textvariable=self.video_url_var, style="Path.TEntry").grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(s_grid, text="⚡ Fetch", style="Accent.TButton", command=self._start_fetch_video_link).grid(row=1, column=2, padx=(8, 0), pady=4)

        ttk.Label(s_grid, text="Save Folder", style="CardBold.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(s_grid, textvariable=self.output_dir_var, style="Path.TEntry").grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(s_grid, text="Change", style="Soft.TButton", command=self._browse_output_dir).grid(row=2, column=2, padx=(8, 0), pady=4)

        # -------------------------------------------------------------
        # 2. Translation & Dubbing Card Tile
        # -------------------------------------------------------------
        dub_tile = tk.Frame(
            container,
            bg=COLOR_BG_CARD_ALT,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SUBTLE,
        )
        dub_tile.pack(fill="x", pady=(0, 10))

        tk.Label(
            dub_tile,
            text="🌐 TRANSLATION & DUBBING PARAMETERS",
            bg=COLOR_BG_CARD_ALT,
            fg=COLOR_CYAN,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        d_grid = tk.Frame(dub_tile, bg=COLOR_BG_CARD_ALT)
        d_grid.pack(fill="x")
        d_grid.columnconfigure(0, weight=1)
        d_grid.columnconfigure(1, weight=1)

        self._labeled_combo(d_grid, "Speech Language (Source)", self.speech_lang_var, 0, 0, SPEECH_LANGUAGE_OPTIONS)
        self._labeled_combo(d_grid, "Target Language (Translation)", self.target_lang_var, 0, 1, TRANSLATION_TARGET_OPTIONS)
        self._labeled_combo(d_grid, "Voiceover Persona", self.voice_gender_var, 2, 0, VOICE_GENDER_OPTIONS)

        ttk.Label(d_grid, text="Original Audio Track", style="Card.TLabel").grid(row=2, column=1, sticky="w")
        self.original_audio_mode_combo = ttk.Combobox(
            d_grid,
            textvariable=self.original_audio_mode_var,
            values=ORIGINAL_AUDIO_MODE_OPTIONS,
            state="readonly",
            style="Dark.TCombobox",
        )
        self.original_audio_mode_combo.grid(row=3, column=1, sticky="ew", padx=(0, 4), pady=(2, 6))

        # Background Volume Mixer Tile
        vol_tile = tk.Frame(
            dub_tile,
            bg=COLOR_BG_CARD,
            padx=8,
            pady=6,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SUBTLE,
        )
        vol_tile.pack(fill="x", pady=(6, 8))
        vol_tile.columnconfigure(1, weight=1)

        ttk.Label(vol_tile, text="🎵 Background Music Volume:", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.vol_scale = ttk.Scale(
            vol_tile,
            from_=0.0,
            to=1.0,
            value=float(self.original_volume_var.get()),
            command=self._on_volume_change,
            style="Preview.Horizontal.TScale",
        )
        self.vol_scale.grid(row=0, column=1, sticky="ew", padx=8)

        self.vol_label = tk.Label(
            vol_tile,
            text=f"{int(float(self.original_volume_var.get()) * 100)}%",
            bg=COLOR_BG_CARD,
            fg=COLOR_CYAN,
            font=("Segoe UI", 9, "bold"),
            width=5,
        )
        self.vol_label.grid(row=0, column=2, sticky="e")

        # Checkboxes
        check_row = tk.Frame(dub_tile, bg=COLOR_BG_CARD_ALT)
        check_row.pack(fill="x", pady=(2, 0))
        ttk.Checkbutton(check_row, text="Generate Voice", variable=self.generate_voice_var, style="Dark.TCheckbutton").pack(side="left")
        ttk.Checkbutton(check_row, text="Slow Voice", variable=self.slow_voice_var, style="Dark.TCheckbutton").pack(side="left", padx=(14, 0))
        ttk.Checkbutton(check_row, text="Skip Translation", variable=self.skip_translation_var, style="Dark.TCheckbutton").pack(side="left", padx=(14, 0))

        # -------------------------------------------------------------
        # 3. Advanced Engine Settings Card Tile (Accordion)
        # -------------------------------------------------------------
        adv_tile = tk.Frame(
            container,
            bg=COLOR_BG_CARD_ALT,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SUBTLE,
        )
        adv_tile.pack(fill="x", pady=(0, 10))

        adv_header = tk.Frame(adv_tile, bg=COLOR_BG_CARD_ALT, cursor="hand2")
        adv_header.pack(fill="x")
        adv_header.bind("<Button-1>", self._toggle_advanced_options)

        self.adv_toggle_lbl = tk.Label(
            adv_header,
            text="⚙️ Advanced AI & Model Settings ▸",
            bg=COLOR_BG_CARD_ALT,
            fg=COLOR_TEXT_MUTED,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        self.adv_toggle_lbl.pack(side="left")
        self.adv_toggle_lbl.bind("<Button-1>", self._toggle_advanced_options)

        self.adv_frame = ttk.Frame(adv_tile, style="Card.TFrame")
        self.adv_frame.columnconfigure(0, weight=1)
        self.adv_frame.columnconfigure(1, weight=1)

        ttk.Label(self.adv_frame, text="Transcription Engine", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.transcription_engine_combo = ttk.Combobox(
            self.adv_frame,
            textvariable=self.transcription_engine_var,
            values=("auto", "faster-whisper", "whisper", "google"),
            state="readonly",
            style="Dark.TCombobox",
        )
        self.transcription_engine_combo.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(2, 6))

        self._labeled_entry(self.adv_frame, "Whisper Model", self.whisper_model_var, 0, 1)
        self._labeled_entry(self.adv_frame, "Ollama Model", self.ollama_model_var, 2, 0)
        self._labeled_entry(self.adv_frame, "HF Token", self.hf_token_var, 2, 1)

        adv_check_row = ttk.Frame(self.adv_frame, style="Card.TFrame")
        adv_check_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        ttk.Checkbutton(adv_check_row, text="Repair with Ollama", variable=self.repair_transcript_var, style="Dark.TCheckbutton").pack(side="left")

        self._labeled_combo(self.adv_frame, "Cookie Browser", self.cookies_browser_var, 5, 0, COOKIE_BROWSER_OPTIONS)
        self._labeled_entry(self.adv_frame, "Chunk Seconds", self.chunk_seconds_var, 5, 1)

        # -------------------------------------------------------------
        # 4. EXPORT & RENDER STATION (The Master Station!)
        # -------------------------------------------------------------
        export_box = tk.Frame(
            container,
            bg=COLOR_BG_CARD_ALT,
            padx=14,
            pady=12,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_LIGHT,
        )
        export_box.pack(fill="x", pady=(0, 6))

        tk.Label(
            export_box,
            text="🚀 EXPORT & RENDER STATION",
            bg=COLOR_BG_CARD_ALT,
            fg=COLOR_EMERALD,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        # Big "Export Translated Video" button
        self.export_button = ttk.Button(
            export_box,
            text="🚀 Export Translated Video",
            style="Build.TButton",
            command=self._start_export,
        )
        self.export_button.pack(fill="x", pady=(0, 10))

        # Progress Status Line
        progress_info_frame = tk.Frame(export_box, bg=COLOR_BG_CARD_ALT)
        progress_info_frame.pack(fill="x", pady=(0, 4))

        self.status_dot = PulsingStatusDot(progress_info_frame, size=14, bg=COLOR_BG_CARD_ALT)
        self.status_dot.pack(side="left", padx=(0, 6))

        self.progress_label = tk.Label(
            progress_info_frame,
            textvariable=self.progress_text_var,
            bg=COLOR_BG_CARD_ALT,
            fg=COLOR_TEXT_WHITE,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.progress_label.pack(side="left", fill="x", expand=True)

        self.percent_label = tk.Label(
            progress_info_frame,
            text="0%",
            bg=COLOR_BG_CARD_ALT,
            fg=COLOR_CYAN,
            font=("Consolas", 9, "bold"),
        )
        self.percent_label.pack(side="right")

        # Visual Determinate Progress Bar
        self.export_progress_bar = ttk.Progressbar(
            export_box,
            variable=self.progress_percent_var,
            maximum=100.0,
            style="Busy.Horizontal.TProgressbar",
        )
        self.export_progress_bar.pack(fill="x", pady=(0, 8))
        self.busy_progress = self.export_progress_bar

        # Post-Export Actions
        self.post_export_frame = tk.Frame(export_box, bg=COLOR_BG_CARD_ALT)
        self.post_export_frame.pack(fill="x")
        self.post_export_frame.columnconfigure(0, weight=1)
        self.post_export_frame.columnconfigure(1, weight=1)

        self.play_export_btn = ttk.Button(
            self.post_export_frame,
            text="▶ Play Exported Video",
            style="Accent.TButton",
            command=self._preview_output,
            state="disabled",
        )
        self.play_export_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.open_folder_btn = ttk.Button(
            self.post_export_frame,
            text="📂 Open Output Folder",
            style="Soft.TButton",
            command=self._open_output_folder,
        )
        self.open_folder_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Secondary Actions (Transcribe only, etc.)
        sub_actions = tk.Frame(container, bg=COLOR_BG_CARD)
        sub_actions.pack(fill="x", pady=(2, 0))
        sub_actions.columnconfigure(0, weight=1)
        sub_actions.columnconfigure(1, weight=1)

        ttk.Button(sub_actions, text="⚡ Transcribe Only", style="Soft.TButton", command=self._start_analysis).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(sub_actions, text="🎙️ Generate Voice Only", style="Soft.TButton", command=self._start_voice_only).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _toggle_advanced_options(self, _event=None) -> None:
        """Toggles the advanced engine options accordion."""
        if self.adv_frame in self.adv_frame.master.pack_slaves():
            self.adv_frame.pack_forget()
            self.adv_toggle_lbl.config(text="⚙️ Advanced AI & Model Settings ▸")
        else:
            self.adv_frame.pack(fill="x", pady=(8, 4))
            self.adv_toggle_lbl.config(text="⚙️ Advanced AI & Model Settings ▾")

    def _on_volume_change(self, value: str) -> None:
        val = float(value)
        self.original_volume_var.set(f"{val:.2f}")
        if hasattr(self, "vol_label"):
            self.vol_label.config(text=f"{int(val * 100)}%")

    def _set_progress(self, percent: float, text: str) -> None:
        self.progress_percent_var.set(percent)
        self.progress_text_var.set(text)
        if hasattr(self, "percent_label"):
            self.percent_label.config(text=f"{int(percent)}%")

    def _labeled_entry(
        self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, column: int
    ) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=column, sticky="w")
        ttk.Entry(parent, textvariable=variable, style="Path.TEntry").grid(
            row=row + 1, column=column, sticky="ew", padx=(0, 8), pady=(2, 8)
        )

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
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="normal",
            style="Dark.TCombobox",
        ).grid(
            row=row + 1,
            column=column,
            sticky="ew",
            padx=(0, 8),
            pady=(2, 8),
        )

    def _language_code(self, variable: tk.StringVar, default: str) -> str:
        return normalize_language_code(variable.get(), default=default)

    def _voice_gender(self) -> str:
        return normalize_voice_gender(self.voice_gender_var.get(), default=DEFAULT_VOICE_GENDER)

    def _append_log(self, message: str) -> None:
        if hasattr(self, "log_text"):
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
        self._set_progress(0.0, "Ready to export")

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
        self._set_progress(10.0, "Downloading online video link...")
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
            raise ValueError("Choose a video file or fetch a link first.")

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

        dot_state = "busy" if busy else ("error" if ("fail" in status.lower() or "error" in status.lower()) else "ready")
        if getattr(self, "status_dot", None) is not None:
            self.status_dot.set_state(dot_state)
        if getattr(self, "header_status_dot", None) is not None:
            self.header_status_dot.set_state(dot_state)

        for card in getattr(self, "animated_cards", []):
            card.set_busy(busy)

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
        self._set_progress(20.0, "Transcribing speech & analyzing video...")
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
            messagebox.showerror("Transcript missing", "Transcribe the video first or paste transcript text in the editor.")
            return

        self.current_output_paths = output_paths
        self._set_progress(45.0, "Re-translating transcript to Khmer...")
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
        messagebox.showinfo("Saved", f"Khmer script saved to:\n{save_path}")

    def _start_voice_only(self) -> None:
        try:
            config, output_paths = self._build_config()
        except Exception as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        khmer_text = self._get_text(self.khmer_text)
        if not khmer_text:
            messagebox.showerror("Khmer script missing", "Transcribe the video first or type Khmer script before generating voice.")
            return

        self.current_output_paths = output_paths
        self._set_progress(60.0, "Generating Khmer narration voice...")
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

    def _start_export(self) -> None:
        """Main Export action: Starts end-to-end translation, voiceover, and video export."""
        self._start_build_final()

    def _start_build_final(self) -> None:
        try:
            config, output_paths = self._build_config()
        except Exception as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        self.current_output_paths = output_paths
        khmer_text = self._get_text(self.khmer_text)
        transcript_text = self._get_text(self.transcript_text)
        self._set_progress(10.0, "Step 1/3: Starting export pipeline...")
        self._run_worker(
            "Exporting translated video...",
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
                self.events.put(("progress", {"percent": 25.0, "text": "Step 1/3: Transcribing audio speech..."}))
                analysis = analyze_video(config, logger=self._queue_log)
                khmer_text = analysis.translated_text
                transcript_text = analysis.source_text
                self.events.put(("progress", {"percent": 55.0, "text": "Step 2/3: Translating script to Khmer..."}))
            else:
                save_text(khmer_text, output_paths["translated_text_out"])
                if transcript_text:
                    save_text(transcript_text, output_paths["transcript_out"])

            base_analysis = analysis if analysis is not None else self.current_analysis
            self.events.put(("progress", {"percent": 75.0, "text": "Step 3/3: Synthesizing Khmer narration voice..."}))

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

            self.events.put(("progress", {"percent": 88.0, "text": "Step 3/3: Mixing audio & rendering final MP4..."}))
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
        self._set_progress(0.0, f"Error: {message}")
        self._append_log(f"Error: {message}")
        messagebox.showerror("Workflow failed", message)

    def _handle_analysis_done(self, payload: object) -> None:
        self._set_busy(False, "Analysis complete")
        self._set_progress(60.0, "Transcription & translation ready. Click Export to build.")
        if not isinstance(payload, dict):
            return

        analysis = payload.get("analysis")
        if not isinstance(analysis, AnalysisResult):
            return

        self.current_analysis = analysis
        self._replace_text(self.transcript_text, analysis.source_text)
        self._replace_text(self.khmer_text, analysis.translated_text)
        self.khmer_path_var.set(analysis.translated_text_path)
        self._append_log("Transcription and Khmer translation complete.")

    def _handle_download_done(self, payload: object) -> None:
        self._set_busy(False, "Video ready")
        self._set_progress(0.0, "Video downloaded. Ready to export.")
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
        self._append_log("Linked video downloaded successfully.")
        self._load_preview(video_path)

    def _handle_retranslate_done(self, payload: object) -> None:
        self._set_busy(False, "Translation complete")
        self._set_progress(60.0, "Re-translation complete. Ready to export.")
        if not isinstance(payload, dict):
            return

        translated_text = str(payload.get("translated_text", ""))
        translated_text_path = str(payload.get("translated_text_path", ""))
        self._replace_text(self.khmer_text, translated_text)
        self.khmer_path_var.set(translated_text_path)
        self._append_log(f"Saved Khmer text to: {translated_text_path}")

    def _handle_voice_done(self, payload: object) -> None:
        self._set_busy(False, "Voice ready")
        self._set_progress(80.0, "Voice synthesis complete.")
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
        self._set_busy(False, "Export complete")
        self._set_progress(100.0, "✅ Export Complete! Ready to play.")
        if hasattr(self, "play_export_btn"):
            self.play_export_btn.config(state="normal")

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

        messagebox.showinfo("Export Done", f"Final translated video is ready!\n\nSaved to:\n{output_video_path}")

    def _poll_events(self) -> None:
        while True:
            try:
                event_type, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event_type == "log":
                self._append_log(str(payload))
            elif event_type == "progress":
                if isinstance(payload, dict):
                    pct = float(payload.get("percent", 0.0))
                    txt = str(payload.get("text", ""))
                    self._set_progress(pct, txt)
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
            self.current_video_label_var.set(f"{path.name}  ({self._format_time(self.preview_duration)})")
            self.ignore_seek = True
            self.preview_scale.configure(to=max(self.preview_duration, 1.0))
            self.preview_position_var.set(0.0)
            self.ignore_seek = False
            self._show_preview_frame(0.0)
            self._update_time_label()
            self.play_button.config(text="▶ Start Video")
        except Exception as exc:
            self._close_preview_clip()
            messagebox.showerror("Preview error", str(exc))

    def _show_preview_frame(self, timestamp: float) -> None:
        if self.preview_clip is None or self.preview_duration <= 0:
            self.preview_surface.configure(
                text="🎬 NO VIDEO LOADED\n\nChoose a video file or fetch a link on the right to start previewing",
                image="",
                fg=COLOR_TEXT_MUTED,
            )
            return

        safe_time = min(max(0.0, timestamp), max(0.0, self.preview_duration - 0.04))
        frame = self.preview_clip.get_frame(safe_time)
        image = Image.fromarray(frame)

        viewport = self.preview_viewport or self.preview_surface
        width = viewport.winfo_width()
        height = viewport.winfo_height()
        if width <= 2 or height <= 2:
            width, height = 480, 260

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
            self.play_button.config(text="▶ Start Video")
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
            self.play_button.config(text="▶ Start Video")
            if self.preview_after_id is not None:
                self.root.after_cancel(self.preview_after_id)
                self.preview_after_id = None
            return

        self.preview_playing = True
        self.play_button.config(text="⏸ Pause Video")
        self._advance_preview()

    def _handle_seek(self, _value: str) -> None:
        if self.ignore_seek or self.preview_clip is None:
            return

        if self.preview_after_id is not None:
            self.root.after_cancel(self.preview_after_id)
            self.preview_after_id = None

        self.preview_playing = False
        self.play_button.config(text="▶ Start Video")
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
            messagebox.showerror("No output video", "Export the translated video first.")
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
            messagebox.showerror("No video", "There is no video loaded to open.")
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
        for card in getattr(self, "animated_cards", []):
            card.stop()
        if getattr(self, "status_dot", None) is not None:
            self.status_dot.stop()
        if getattr(self, "header_status_dot", None) is not None:
            self.header_status_dot.stop()
        self._close_preview_clip()
        self.root.destroy()


def launch_gui() -> None:
    root = tk.Tk()
    KhmerVideoUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
