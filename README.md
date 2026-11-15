# Video Translate 🎬✨
> A high-performance, modern desktop application for Video Translation & AI Dubbing with a sleek YouTube / VLC-style media player.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Tkinter](https://img.shields.io/badge/GUI-Tkinter-brightgreen.svg)](https://docs.python.org/3/library/tkinter.html)
[![FFmpeg](https://img.shields.io/badge/Engine-FFmpeg-red.svg?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)

---

## 📖 Overview

**Video Translate** is a lightweight, responsive desktop tool designed for content creators, translators, and video editors. It features a custom **Cinema Player** that delivers silky-smooth 25+ FPS video playback, synchronized native Windows audio, and a streamlined 4-button dubbing workflow.

---

## ✨ Key Features

### 📺 1. YouTube & VLC-Style Unified Media Player
- **Cinema Black Viewport (`#000000`):** Solid, glare-free cinema background inspired by VLC Media Player and YouTube Desktop.
- **Play / Pause Toggle (`▶` / `||`):** Click to pause at the current exact timestamp without resetting or replaying from the beginning.
- **Red Timeline Scrubber:** Draggable circular knob with instant single-frame seek preview.
- **Synchronized Audio & Controls:** Speaker mute toggle, interactive volume slider (0% to 100%), and live timestamp readout (`0:00 / 0:00`).

### ⚡ 2. Blazing Fast 25+ FPS In-Memory Streaming
- **Zero Disk I/O Overhead:** Video frames are decoded via a continuous FFmpeg stdout pipe directly into RAM as raw RGB24 buffers (`P6` PPM format).
- **Over 2,000 FPS Decoding Throughput:** Eliminates process startup lag and disk wear completely.

### 🧵 3. Thread-Safe Queue Architecture (Python 3.15+ Ready)
- Background decoding threads communicate with Tkinter UI through a dedicated `queue.Queue`.
- Prevents GUI freezes, race conditions, and Tcl `main thread is not in main loop` exceptions.

### 📐 4. Dynamic Aspect Ratio Preservation (Flush Fit)
- Automatically probes video dimensions with `ffprobe` to preserve the original aspect ratio:
  - 📱 **9:16 Portrait:** TikTok, Instagram Reels, YouTube Shorts (Pillarboxed cleanly).
  - 📺 **4:3 Classic TV / Retro Video:** Displayed with correct geometric proportions.
  - 🎬 **16:9 & 21:9 Widescreen / Cinema:** Full panoramic presentation.
  - 🔲 **1:1 Square Videos:** Symmetrically centered.
- **Zero Space Top & Bottom:** Video sits flush against the controls with 0px wasted gap.

### 🔊 5. 100% Reliable Windows Audio
- Powered by native Windows Multimedia API (`winsound` + `waveOutSetVolume`).
- Compatible with all audio output devices (Headphones, Realtek Speakers, Bluetooth headsets) with zero latency.

### ⚡ 6. Real-Time Responsive Resizing
- Throttled 30+ FPS scaling engine dynamically resizes the video and controls in real time as the window border is dragged.

### 🎙️ 7. 4-Step Dubbing Workflow
1. **Load:** Select and preview any video format (`.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.flv`).
2. **Browse:** Choose destination directory (defaults to user's `Downloads` folder).
3. **Voice:** Toggle between **Man** and **Woman** voice persona with a single click.
4. **Start:** Executes automated audio extraction, speech synthesis, and video remuxing with a single progress bar.

---

## 📁 Project Architecture & Directory Structure

```
d:\DUC\SPD\
│
├── bin/                          # Local Binaries (Ignored by Git for size)
│   ├── .gitkeep
│   ├── ffmpeg.exe                # FFmpeg 7.x / 8.x / Gyan build
│   └── ffprobe.exe               # Media analysis tool
│
├── src/                          # Modular Clean Architecture
│   ├── core/                     # Backend Processing Engine
│   │   ├── __init__.py           # Exports VideoEngine & WindowsAudioPlayer
│   │   ├── video_engine.py       # FFmpeg streaming, frame extraction, metadata probing
│   │   └── audio_player.py       # Windows native audio playback & volume controller
│   │
│   └── ui/                       # Frontend Presentation Layer
│       ├── __init__.py           # Exports custom widgets & YouTubePlayerView
│       ├── widgets.py            # RoundedCard, RoundedButton, RoundedProgressBar
│       └── player_view.py        # High-performance Tkinter Canvas video player
│
├── temp/                         # Temporary Processing Cache (Ignored by Git)
│   └── .gitkeep
│
├── main.py                       # Main Application Entry Point
├── .gitignore                    # Git rules (excludes venv, temp files, large exes)
└── README.md                     # Comprehensive project documentation
```

---

## 🛠️ Quick Start & Setup Guide

### 1. Prerequisites
- **Operating System:** Windows 10 or Windows 11 (64-bit).
- **Python:** Python 3.10 to 3.15+ installed.
- **FFmpeg Binaries:** Ensure `ffmpeg.exe` and `ffprobe.exe` are placed inside `bin/` or available in your system `PATH`.

### 2. Clone Repository
```powershell
git clone <repository-url>
cd SPD
```

### 3. Setup Virtual Environment (Recommended)
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

### 4. Run Application
```powershell
python main.py
```

---

## 💻 Technical Component Breakdown

| Module | Component | Responsibility |
| :--- | :--- | :--- |
| `main.py` | `VideoTranslateApp` | Main window controller, layout orchestration, dubbing thread management. |
| `src.ui.player_view` | `YouTubePlayerView` | Unified Canvas player handling frame queues, cinema viewport, scrubber, and YouTube controls. |
| `src.ui.widgets` | `RoundedCard` | Clean white card container with mathematical continuous rounded corners (zero inner lines). |
| `src.ui.widgets` | `RoundedButton` | Hover-animated rounded action buttons with active state coloring. |
| `src.ui.widgets` | `RoundedProgressBar` | Smooth single progress bar with customizable fill color and radius. |
| `src.core.video_engine` | `VideoEngine` | Spawns persistent FFmpeg pipes, probes JSON metadata, extracts audio. |
| `src.core.audio_player` | `WindowsAudioPlayer` | Handles instant seeking, asynchronous playback, and `waveOutSetVolume`. |

---

## 🤝 Team Git Workflow & Contribution Guidelines

To keep the repository clean and avoid conflicts:

1. **Branching Strategy:**
   - Always branch off `main` or the latest integration branch:
     ```powershell
     git checkout -b feature/your-feature-name
     # or
     git checkout -b fix/your-bug-fix
     ```
2. **Commit Convention:**
   - Use clear conventional commit messages:
     - `feat: add AI voice synthesis integration`
     - `fix: resolve aspect ratio calculation on ultrawide monitors`
     - `docs: update setup instructions in README`
3. **Files Ignored by Git:**
   - `bin/*.exe` (FFmpeg executables exceed GitHub's 100MB limit).
   - `.venv/` (Virtual environment folder).
   - `temp/*` (Temporary audio slices and preview frames).

---

## 🔒 Security & Sandbox Best Practices

- **Zero Arbitrary Execution:** All media files are inspected and parsed safely through documented FFmpeg/ffprobe arguments.
- **Hidden Subprocess Windows:** Subprocess invocations use Windows `creationflags=0x08000000` (`CREATE_NO_WINDOW`) to prevent annoying command prompt popups.
- **Clean Disposal Protocol:** Closing the main window automatically triggers `player_view.destroy()`, terminating active stream subprocesses and releasing audio devices immediately.

---

## 👤 Credits & Author

- **Project Lead:** បង **LIHOUR**
- **Architecture & Development:** ប្អូន **ហនុមាន (Hanuman)**
- **Organization:** DUC / SPD Team

---

*Happy Dubbing & Translating! 🚀🎥*
