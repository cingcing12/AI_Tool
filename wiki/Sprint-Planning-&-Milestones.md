# 📅 Sprint Planning & Project Milestones

This document records the Sprint schedule, milestone objectives, deliverables, acceptance criteria, and progress tracking for the **Video Translate & Subtitle Studio** group project.

---

## 🏁 Milestones Roadmap

| Milestone | Target Dates | Focus Area | Status | Sign-off Lead |
| :---: | :---: | :--- | :---: | :---: |
| **M1** | Nov 01 – Nov 07 | Architecture, GUI Layout & Video Decoding | `Completed` | **Eang Panha** |
| **M2** | Nov 08 – Nov 13 | Speech-to-Text & Subtitle Extraction | `Completed` | **HIM Lihour** |
| **M3** | Nov 14 – Nov 17 | Khmer Translation & Neural Voiceover Engine | `Completed` | **Vong Sokpheak** |
| **M4** | Nov 18 – Nov 20 | Realtime Audio Sync & Clean Video Merging | `Completed` | **Vong Sokpheak** |
| **M5** | Nov 21 – Nov 26 | QA Testing, Benchmarking & Presentation Demo | `In Progress` | **VEASNA REAKSA** |

---

## 🏃 Sprint Breakdown & Deliverables

### Sprint 1: Architecture, UI Layout & Video Decoding (Nov 01 – Nov 07)
> **Goal**: Establish the repository, build the modern desktop UI with Tkinter, and implement smooth 25+ FPS FFmpeg video streaming.

- **Completed Deliverables**:
  - [x] Initialized Git repository with clean modular architecture (`src/core`, `src/ui`).
  - [x] Created custom Tkinter components (`RoundedCard`, `RoundedButton`, `RoundedProgressBar`) in `src/ui/widgets.py`.
  - [x] Implemented in-memory RGB24 frame streaming via FFmpeg pipe in `src/core/video_engine.py`.
  - [x] Built `player_view.py` with YouTube-style double-click skip (`-10s` / `+10s`) and cinema black viewport.
- **Acceptance Criteria Met**:
  - Application launches cleanly with zero UI freezing.
  - Video plays smoothly at native framerate with interactive scrubbing.

---

### Sprint 2: Audio Enhancement & Subtitle Extraction (Nov 08 – Nov 13)
> **Goal**: Extract spoken English dialogue from loaded videos and produce formatted `.srt` subtitle files.

- **Completed Deliverables**:
  - [x] Implemented 16kHz mono audio extraction with speech-vocal bandpass filtering in `src/core/video_engine.py`.
  - [x] Built overlapping sliding window ($7.0\text{s}$ window, $5.0\text{s}$ step) in `src/core/script_extractor.py`.
  - [x] Engineered prefix deduplication algorithm to prevent duplicated phrases across boundaries.
  - [x] Implemented two-pass sub-slice recovery to prevent dropped subtitle segments in quiet/music moments.
  - [x] Formatted transcripts into standard SubRip timestamp format (`HH:MM:SS,mmm`).
- **Acceptance Criteria Met**:
  - 100% of spoken words captured without missing phrases or sentence cutoffs.
  - Valid `.srt` file created and saved alongside input video.

---

### Sprint 3: Khmer Translation & Voice Synthesis (Nov 14 – Nov 17)
> **Goal**: Translate extracted English subtitles to natural Khmer and generate authentic neural speech.

- **Completed Deliverables**:
  - [x] Built multi-provider translation engine (`googletrans` + `deep_translator` fallback) with 429 rate limit immunity.
  - [x] Integrated Microsoft Azure Edge-TTS neural voices:
    - **Male**: `km-KH-PisethNeural`
    - **Female**: `km-KH-SreymomNeural`
  - [x] Implemented female-to-male acoustic pitch shifting (`asetrate=44100*0.82,atempo=1.22`) to guarantee 100% male voice adherence on any fallback.
  - [x] Added 3-attempt automated retry for network robustness.
- **Acceptance Criteria Met**:
  - Translations are grammatically natural in Khmer.
  - Voice selection (Man / Woman) strictly respected across all generated audio.

---

### Sprint 4: Realtime Sync & Audio-Video Merging (Nov 18 – Nov 20)
> **Goal**: Lock speech playback to video timestamps and merge pure Khmer audio into the output video.

- **Completed Deliverables**:
  - [x] Developed dynamic `atempo` chaining algorithm ($1.0\text{x} - 2.5\text{x}$) to fit speech within time slots without word clipping.
  - [x] Engineered silence gap padding to synchronize every line with video speech timestamps.
  - [x] Implemented audio concatenation manifest pipeline using `libmp3lame`.
  - [x] Implemented clean FFmpeg video-audio muxing (`-map 0:v:0 -map 1:a:0 -shortest`) that removes 100% of the original audio.
  - [x] Auto-load dubbed video for instant preview upon completion.
- **Acceptance Criteria Met**:
  - Dubbed video contains zero original audio.
  - Khmer voiceover plays in realtime sync with the speaker in the video.

---

### Sprint 5: QA Testing, Benchmarking & Presentation (Nov 21 – Nov 26)
> **Goal**: Final quality assurance, multi-format validation, documentation, and academic presentation delivery.

- **Deliverables**:
  - [x] Windows 1-click execution scripts (`run.bat` and `run.ps1`).
  - [x] Embedded Gyan FFmpeg 7.x portable binaries in `bin/ffmpeg.exe`.
  - [x] Complete GitHub Wiki documentation suite.
  - [ ] Cross-testing on diverse video aspect ratios (16:9 landscape, 9:16 vertical TikTok/Reels, 4:3).
  - [ ] Final team slide deck and live demonstration video.
- **Acceptance Criteria**:
  - Zero fatal crashes across all test datasets.
  - Ready for academic grading and presentation.
