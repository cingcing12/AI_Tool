# 📖 User Manual & Testing Guide

This guide provides step-by-step instructions for installing, configuring, operating, and testing the **Video Translate & Subtitle Studio** desktop application.

---

## 💻 System Requirements

- **Operating System**: Windows 10 or Windows 11 (64-bit).
- **Python**: Python 3.10 – 3.14.
- **Hardware**: Dual-core CPU or higher, 4GB+ RAM, 500MB free disk space.
- **Network**: Internet connection required for Speech Recognition and Neural TTS synthesis.
- **FFmpeg**: Bundled automatically in `bin/ffmpeg.exe` (no manual system PATH installation required).

---

## 🚀 Quick Installation & Startup

### Option A: One-Click Launch (Recommended)
1. Clone the repository:
   ```bash
   git clone https://github.com/cingcing12/AI_Tool.git
   cd AI_Tool
   ```
2. Double-click `run.bat` or in PowerShell execute:
   ```powershell
   .\run.ps1
   ```
   *The launcher automatically initializes the virtual environment, verifies dependencies, links FFmpeg, and launches the application.*

### Option B: Manual Setup
```powershell
# 1. Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
python -m pip install -r requirements.txt

# 3. Launch application
python main.py
```

---

## 🖥️ How to Use the Studio

```
+--------------------------------------------------------------+
| Video Translate & Subtitle Studio                        [-] |
+------------------------------------+-------------------------+
|                                    | Controls                |
|                                    | [ Load Video          ] |
|                                    | [ Extract Script (SRT)] |
|         CINEMA VIDEO PLAYER        | [ Browse Output       ] |
|                                    | [ Voice: Man          ] |
|                                    |                         |
|                                    |                         |
|                                    | [ Start Dubbing       ] |
+------------------------------------+-------------------------+
| [▶]  [00:15 / 02:16] ============O============ [Progress: 100%]|
+--------------------------------------------------------------+
```

### 1. Load Source Video
- Click **"Load Video"** in the top-right control panel.
- Select any supported video file (`.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`).
- The video will immediately load into the Cinema Player with native aspect ratio.

### 2. Interactive Video Player Controls
- **Play / Pause**: Click `▶` / `||` or click directly on the video viewport.
- **YouTube Double-Click Skip**:
  - Double-click the **left half** of the video to skip backward **10 seconds** (`◀◀ 10s`).
  - Double-click the **right half** of the video to skip forward **10 seconds** (`10s ▶▶`).
- **Timeline Seeking**: Drag the timeline scrubber to jump to any frame instantly.

### 3. Extract English Subtitles Only (Optional)
- Click **"Extract Script (SRT)"**.
- The studio extracts speech audio, transcribes dialogue via sliding window, and produces an editable `.srt` subtitle file.

### 4. End-to-End Khmer Dubbing (1-Click)
- Choose **Voice Gender**: Click the **"Voice: Man"** toggle button to switch between:
  - **`Voice: Man`** (Uses authentic male voice `km-KH-PisethNeural`).
  - **`Voice: Woman`** (Uses authentic female voice `km-KH-SreymomNeural`).
- Click **"Start Dubbing"**:
  - **Step 1/4 (0%–25%)**: Extracts enhanced audio & transcribes dialogue into `.srt`.
  - **Step 2/4 (25%–40%)**: Translates English subtitles into natural Khmer.
  - **Step 3/4 (40%–80%)**: Synthesizes realtime-synchronized Khmer voiceover.
  - **Step 4/4 (80%–100%)**: Strips original video sound 100% and merges the pure Khmer voiceover.
- Upon completion, the newly dubbed video **auto-loads into the player for instant preview**!

---

## 🧪 Test Scenarios & Verification Checklist

| Test Case | Scenario Description | Expected Outcome | Pass/Fail |
| :---: | :--- | :--- | :---: |
| **TC-01** | Load 16:9 Landscape MP4 video. | Video displays with black letterboxing, maintaining 16:9 ratio. | `PASS` |
| **TC-02** | Load 9:16 Vertical TikTok/Reels video. | Video centers cleanly without stretching or distortion. | `PASS` |
| **TC-03** | Double-click left/right video canvas. | Seeks `-10s` or `+10s` with on-screen visual indicator. | `PASS` |
| **TC-04** | Extract script on dialogue with background noise. | Vocal enhancement filter isolates voice; accurate SRT produced. | `PASS` |
| **TC-05** | Dub with `Voice: Man`. | 100% pure male voice throughout; zero female voice leakage. | `PASS` |
| **TC-06** | Dub with `Voice: Woman`. | 100% female voice throughout. | `PASS` |
| **TC-07** | Audio-visual synchronization test. | Khmer speech begins and ends matching speaker's dialogue window. | `PASS` |
| **TC-08** | Verify original audio removal. | Original English speech is 100% silent; only Khmer voice plays. | `PASS` |
| **TC-09** | Unplug/replug headphones during playback. | Audio daemon migrates seamlessly to speakers without crash. | `PASS` |

---

## ❓ Troubleshooting & FAQs

### Q: Dubbing fails with "No speech recognition engine found"?
- Run: `python -m pip install SpeechRecognition` or use `.\run.ps1` which automatically installs all requirements.

### Q: Google Translate gives "429 Too Many Requests"?
- The studio automatically routes translations through `googletrans` with authenticated session headers, bypassing unauthenticated IP rate limits.

### Q: Audio doesn't switch when plugging in headphones?
- Ensure PowerShell execution policy permits local scripts:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
