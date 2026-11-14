# Video Transcription & Khmer Voiceover Pipeline

An automated tool to transcribe videos, translate subtitles into Khmer, synthesize Khmer voiceover narrations, and merge them into the final video.

## Features

- **Speech Recognition**: Transcribe video speech using Whisper / faster-whisper or Google Speech Recognition.
- **Khmer Translation**: Automatic subtitle and transcript translation to Khmer.
- **Voiceover Generation**: High quality Khmer text-to-speech (gTTS / edge-tts) with adjustable voice gender and speech rate.
- **Audio Mixing**: Option to replace original audio, remove center voice while keeping background music, or mix narration with background audio.
- **Desktop GUI & CLI**: Interactive Tkinter graphical interface or terminal command-line interface.
- **Video Downloader**: Supports downloading videos directly from links (including Douyin/TikTok).

## Installation

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd "New folder (3)"
   ```

2. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Desktop GUI
Run the GUI launcher:
```powershell
.\run.ps1
```
or:
```powershell
.\.venv\Scripts\python.exe main.py --gui
```

### Command Line
```powershell
.\run.ps1 --video path/to/video.mp4 --speech-lang zh-CN --target-lang km
```

See all available options:
```powershell
.\run.ps1 --help
```

## Running Tests

```powershell
.\.venv\Scripts\python.exe test_pipeline.py
```
