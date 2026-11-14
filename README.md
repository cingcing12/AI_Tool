# Video Transcription & Khmer Voiceover Pipeline

An automated tool to transcribe videos, translate subtitles into Khmer, synthesize Khmer voiceover narrations, and merge them into the final video.

## Features

- **Speech Recognition**: Transcribe video speech using Whisper / faster-whisper or Google Speech Recognition.
- **Khmer Translation**: Automatic subtitle and transcript translation to Khmer.
- **Voiceover Generation**: High quality Khmer text-to-speech (gTTS / edge-tts) with adjustable voice gender and speech rate.
- **Audio Mixing**: Option to replace original audio, remove center voice while keeping background music, or mix narration with background audio.
- **Desktop GUI & CLI**: Interactive Tkinter graphical interface or terminal command-line interface.
- **Video Downloader**: Supports downloading videos directly from links (including Douyin/TikTok).

---

## Quick Start for Team Members (Windows)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/cingcing12/AI_Tool.git
   cd AI_Tool
   ```

2. **Run with one click**:
   - Double-click `run.bat`, or in PowerShell run:
     ```powershell
     .\run.ps1
     ```
   *The launcher script will automatically detect that `.venv` is missing, create it, install all dependencies from `requirements.txt`, and launch the desktop application!*

---

## Manual Setup (Any OS)

If you prefer to configure manually:

1. **Create and activate a virtual environment**:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch the application**:
   - Desktop GUI:
     ```bash
     python main.py
     ```
   - Command Line:
     ```bash
     python main.py --video path/to/video.mp4 --speech-lang zh-CN --target-lang km
     ```
   - View all CLI arguments:
     ```bash
     python main.py --help
     ```

---

## Running Tests

```bash
python test_pipeline.py
```
