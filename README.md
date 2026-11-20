# Video Translate & Subtitle Studio 🎬✨

> A high-performance, modern desktop application for Video Translation, AI Dubbing, and Speech-to-Text Subtitle (.srt) extraction with a sleek YouTube / VLC-style media player.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-Tkinter-brightgreen.svg)](https://docs.python.org/3/library/tkinter.html)
[![FFmpeg](https://img.shields.io/badge/Engine-FFmpeg-red.svg?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)
[![GitHub Wiki](https://img.shields.io/badge/Wiki-Documentation-purple.svg?logo=gitbook&logoColor=white)](wiki/Home.md)

---

## 👥 ក្រុម 9 - Team Assignment Roster (Group 9)

| No. | Member Name | Student ID | Official Role | Core Responsibility |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **Vong Sokpheak** | `DUC-PG-A-2024146` | **Project Manager** | Project management, AI dubbing architecture & timeline sync lead |
| **2** | **Veasna Reaksa** | — | **Frontend Dev** | Desktop Tkinter UI/UX, Canvas video player & player controls |
| **3** | **Eang Panha** | — | **Backend Dev** | FFmpeg video pipeline, audio-video muxing & translation |
| **4** | **Nok Sreylinh** | `DUC-PG-A-20240199` | **QA & DevOps Specialist** | Audio daemon, testing, deployment & user documentation |
| **5** | **Him Lihour** | DUC-PG-A-20240776 | **Backend Dev** | Speech-to-Text extraction, audio enhancement & SRT generator |

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

### 🗣️ 4. Khmer Voice Cloning powered by VoxCPM 2
- **Zero-Shot Timbre Cloning:** Clones the speaker's vocal characteristics into authentic Khmer speech using OpenBMB's **VoxCPM 2** diffusion-autoregressive architecture.
- **Dual Sample Modes:**
  - **Auto Video Sample:** Automatically extracts a 5-6s clean speech sample from the loaded video.
  - **Custom Reference Upload:** Upload your own `.wav` or `.mp3` voice clip for personalized dubbing.
- **Realtime Timeline Synchronization:** Synchronized to video speech timestamps with automated silence padding and dynamic atempo alignment.
- **Pure Khmer Audio Replacement:** 100% cleanly strips original audio and merges the cloned Khmer narration track.

### ⚡ 5. Blazing Fast 25+ FPS In-Memory Streaming
- Video frames are decoded via a continuous FFmpeg stdout pipe directly into RAM as raw RGB24 buffers (`P6` PPM format).
- Zero disk wear and instant frame access.

### 📐 6. Dynamic Aspect Ratio Preservation
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
│   │   ├── __init__.py           # Exports VideoEngine, AudioPlayer, ScriptExtractor, DubbingEngine, VoxCPMEngine
│   │   ├── audio_daemon.ps1      # Media Foundation background audio worker
│   │   ├── audio_player.py       # Auto-switching Windows audio player
│   │   ├── dubbing_engine.py     # Timeline-synchronized dubbing & merging engine
│   │   ├── script_extractor.py   # Speech-to-Text & SRT subtitle generator
│   │   ├── video_engine.py       # FFmpeg streaming, frame extraction, metadata probing
│   │   └── voxcpm_engine.py      # VoxCPM 2 Khmer zero-shot voice cloning engine
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
├── requirements.txt              # Production dependencies (includes voxcpm)
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
