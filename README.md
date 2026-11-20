# Video Translate & Subtitle Studio 🎬✨

> A high-performance, modern desktop application for Video Translation, AI Dubbing, and Speech-to-Text Subtitle (.srt) extraction with a sleek YouTube / VLC-style media player.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-Tkinter-brightgreen.svg)](https://docs.python.org/3/library/tkinter.html)
[![FFmpeg](https://img.shields.io/badge/Engine-FFmpeg-red.svg?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)
[![GitHub Wiki](https://img.shields.io/badge/Wiki-Documentation-purple.svg?logo=gitbook&logoColor=white)](wiki/Home.md)

---

## 👥 University Team Assignment Roster

| Member Name | Student ID | Core Project Role |
| :--- | :--- | :--- |
| **Eang Panha** | *Team Owner* | Project Lead & Lead System Architect |
| **Vong Sokpheak** | `DUC-PG-A-2024146` | Core AI & Audio Synthesis Engineer (Dubbing Lead) |
| **HIM Lihour** | `DUC-PG-A-...` | Speech Processing & NLP Engineer (STT Lead) |
| **NOK Sreylinh** | `DUC-PG-A-2024052` | Frontend UI/UX Designer & Media Player Engineer |
| **VEASNA REAKSA** | `DUC-PG-A-...` | DevOps, System Integration & QA Lead |

> 📚 **Complete Project Wiki Documentation**: Explore the full [Wiki Documentation](wiki/Home.md) including the [Team RACI Matrix & Task Assignments](wiki/Team-Roles-&-Task-Assignments.md), [System Architecture & Pipeline](wiki/System-Architecture-&-Pipeline.md), [Sprint Milestones](wiki/Sprint-Planning-&-Milestones.md), and [User Manual](wiki/User-Manual-&-Testing-Guide.md).

---

## 📖 Overview

**Video Translate & Subtitle Studio** is a lightweight, responsive desktop tool designed for content creators, translators, and video editors. It features a custom **Cinema Player** delivering smooth 25+ FPS playback, seamless automatic audio device switching, interactive YouTube-style seeking, and automated speech-to-text subtitle (`.srt`) extraction.

---

## ✨ Key Features

### 📺 1. YouTube & VLC-Style Unified Media Player
- **Cinema Black Viewport:** Solid, glare-free cinema background with smoothly masked rounded corners that fit cleanly within the card frame.
- **YouTube Double-Click Skip:** Double-click on the left side to skip **-10s** (`◀◀ 10s`), or on the right side to skip **+10s** (`10s ▶▶`).
- **Play / Pause Toggle (`▶` / `||`):** Pause at the exact current frame without resetting or replaying.
- **Timeline Scrubber:** Snug fit to the active video aspect ratio with instant seeking and live timestamp readout.

### 🎧 2. Automatic Audio Device Routing (Headphone & Speaker)
- Powered by Windows Media Foundation daemon (`audio_daemon.ps1`) using WASAPI.
- Automatically migrates audio between **Headphones** and **Speakers** when plugged or unplugged with zero latency and zero crashes.

### 🎙️ 3. Automatic Speech-to-Text & Subtitle (.srt) Extractor
- Powered by `ScriptExtractor`:
  - Automatically extracts a clean 16kHz mono WAV track via FFmpeg.
  - Generates standard SubRip (`.srt`) subtitle files with exact millisecond timestamps (`00:01:23,456 --> 00:01:26,789`).
  - Supports both **SpeechRecognition** and **faster-whisper**.

### ⚡ 4. Blazing Fast 25+ FPS In-Memory Streaming
- Video frames are decoded via a continuous FFmpeg stdout pipe directly into RAM as raw RGB24 buffers (`P6` PPM format).
- Zero disk wear and instant frame access.

### 📐 5. Dynamic Aspect Ratio Preservation
- Automatically probes video dimensions to preserve the original aspect ratio (16:9, 9:16 vertical, 4:3, 1:1 square).
- Maintains geometric proportions on resize without distortion.

---

## 📁 Project Architecture & Directory Structure

```
├── bin/                          # Local Binaries (Ignored by Git for size)
│   ├── .gitkeep
│   └── ffmpeg.exe                # FFmpeg 7.x Gyan build
│
├── src/                          # Modular Clean Architecture
│   ├── core/                     # Backend Processing Engine
│   │   ├── __init__.py           # Exports VideoEngine, AudioPlayer, ScriptExtractor
│   │   ├── audio_daemon.ps1      # Media Foundation background audio worker
│   │   ├── audio_player.py       # Auto-switching Windows audio player
│   │   ├── script_extractor.py   # Speech-to-Text & SRT subtitle generator
│   │   └── video_engine.py       # FFmpeg streaming, frame extraction, metadata probing
│   │
│   └── ui/                       # Frontend Presentation Layer
│       ├── __init__.py           # Exports custom widgets & YouTubePlayerView
│       ├── player_view.py        # Canvas video player with YouTube double-click & corner masks
│       └── widgets.py            # RoundedCard, RoundedButton, RoundedProgressBar
│
├── temp/                         # Temporary Processing Cache
│   └── .gitkeep
│
├── main.py                       # Main Application Entry Point
├── requirements.txt              # Production dependencies
├── run.bat                       # 1-Click Windows Batch Launcher
├── run.ps1                       # 1-Click PowerShell Launcher
├── .gitignore                    # Git rules (excludes venv, temp files, large exes)
└── README.md                     # Comprehensive project documentation
```

---

## 🛠️ Quick Start & Setup Guide

### Automatic 1-Click Launch (Windows)

1. **Clone Repository**:
   ```bash
   git clone https://github.com/cingcing12/AI_Tool.git
   cd AI_Tool
   ```

2. **Launch**:
   - Double-click `run.bat`, or in PowerShell run:
     ```powershell
     .\run.ps1
     ```
   *The launcher automatically configures `.venv`, installs requirements, links FFmpeg, and launches the app!*

### Manual Setup

1. **Create and activate virtual environment**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies**:
   ```powershell
   python -m pip install -r requirements.txt
   ```

3. **Run Application**:
   ```powershell
   python main.py
   ```
