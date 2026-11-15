# Video Translate 🎬✨

A sleek, lightweight desktop application for video dubbing and translation, designed with clean modern UI and YouTube-style playback controls.

## 📁 Project Structure

```
d:\DUC\SPD\
│
├── bin/                      # Binaries (FFmpeg & FFprobe)
│   ├── ffmpeg.exe
│   └── ffprobe.exe
│
├── src/                      # Clean Modular Source Code
│   ├── core/
│   │   ├── __init__.py
│   │   └── video_engine.py   # FFmpeg frame extraction & audio probing
│   └── ui/
│       ├── __init__.py
│       ├── widgets.py        # RoundedCard, RoundedButton, RoundedProgressBar
│       └── player_view.py    # Unified YouTube Video Player Canvas
│
├── temp/                     # Temporary cache for frame & audio extraction
│   └── .gitkeep
│
├── main.py                   # Application Entry Point
├── .gitignore                # Git ignore rules for venv, cache, and binaries
└── README.md                 # Project documentation
```

## 🚀 How to Run

Activate virtual environment (optional) and run:

```powershell
python main.py
```

## ⚙️ Features
- **Clean Modern Light UI:** 100% seamless rounded corners with no dark/gray clutter.
- **YouTube-Style Player:** Full-width red timeline scrubber, Play/Stop toggle (`▶` / `■`), Speaker/Mute control, volume slider, and live timestamp (`0:00 / 0:00`).
- **Real Video Preview:** Powered by local FFmpeg to extract and display actual video frames on the fly.
- **Dubbing Workflow:**
  1. `Load`: Select video file to load directly into the player.
  2. `Browse`: Select output directory (defaults to `Downloads`).
  3. `Voice`: Toggle between Man and Woman voice type.
  4. `Start`: Runs dubbing pipeline with animated progress bar and saves output.
