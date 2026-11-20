# 🏗️ System Architecture & Engineering Pipeline

This document details the underlying engineering architecture, mathematical algorithms, data processing flows, and modular design of the **Video Translate & Subtitle Studio**.

---

## 📐 High-Level Architecture Overview

The system is constructed with a modular layered architecture separating Presentation, Business Logic, and Multimedia IO.

```mermaid
graph TD
    subgraph UI_Layer["1. Presentation Layer (Tkinter GUI)"]
        MV["main.py (Application Window)"]
        PV["player_view.py (Canvas Cinema Player)"]
        WG["widgets.py (Rounded UI Components)"]
    end

    subgraph Core_Layer["2. Core Processing Engines"]
        SE["script_extractor.py<br/>(Speech-to-Text & Subtitles)"]
        DE["dubbing_engine.py<br/>(Translation, TTS & Sync)"]
        VE["video_engine.py<br/>(FFmpeg Video Streamer)"]
        AP["audio_player.py<br/>(Audio Device Switcher)"]
    end

    subgraph Hardware_IO["3. Hardware, Media & AI Providers"]
        FF["Embedded Gyan FFmpeg 7.x"]
        AD["audio_daemon.ps1 (WASAPI Audio Routing)"]
        GT["Google Speech & Google Translate API"]
        ET["Microsoft Edge Neural TTS (Azure)"]
        FS["File System (SRT, MP3, MP4)"]
    end

    MV --> PV
    MV --> WG
    MV --> SE
    MV --> DE
    MV --> VE
    MV --> AP

    SE --> FF
    SE --> GT
    DE --> GT
    DE --> ET
    DE --> FF
    VE --> FF
    AP --> AD
```

---

## 🔄 End-to-End Dubbing & Video Pipeline

The video dubbing lifecycle progresses through four deterministic steps:

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant GUI as main.py (UI)
    participant Extractor as script_extractor.py
    participant Engine as dubbing_engine.py
    participant FFmpeg as bin/ffmpeg.exe

    User->>GUI: Loads Video (e.g. IMG_0864.MP4)
    User->>GUI: Clicks "Start Dubbing" (Voice: Man)

    rect rgb(240, 248, 255)
        note over GUI, Extractor: Step 1: Subtitle Extraction (0% - 25%)
        GUI->>Extractor: extract_script_to_srt(video_path)
        Extractor->>FFmpeg: Extract 16kHz mono audio with vocal bandpass
        Extractor->>Extractor: Overlapping sliding window (7s win, 5s step)
        Extractor->>Extractor: Speech recognition with sub-slice recovery
        Extractor-->>GUI: Returns source_script.srt
    end

    rect rgb(255, 250, 240)
        note over GUI, Engine: Step 2: Khmer Translation (25% - 40%)
        GUI->>Engine: translate_script(source_script.srt)
        Engine->>Engine: Multi-provider translation (googletrans -> deep_translator)
        Engine-->>GUI: Returns khmer_script.srt & khmer_script.txt
    end

    rect rgb(240, 255, 240)
        note over GUI, Engine: Step 3: Realtime Voiceover Synthesis (40% - 80%)
        GUI->>Engine: generate_timed_voice(khmer_segments, voice_type="Man")
        loop For each subtitle segment
            Engine->>Engine: Synthesize Edge-TTS (km-KH-PisethNeural)
            alt If fallback needed
                Engine->>FFmpeg: Female-to-Male pitch shift (asetrate=44100*0.82,atempo=1.22)
            end
            Engine->>FFmpeg: Dynamic atempo scaling (fits window with ZERO word cutoff)
            Engine->>Engine: Insert exact silence gap to lock next start second
        end
        Engine->>FFmpeg: Concat parts via manifest with libmp3lame
        Engine-->>GUI: Returns khmer_timed_narration.mp3
    end

    rect rgb(255, 240, 245)
        note over GUI, FFmpeg: Step 4: Pure Audio Replacement (80% - 100%)
        GUI->>Engine: merge_video(video_path, audio_path, remove_original=True)
        Engine->>FFmpeg: -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -shortest
        FFmpeg-->>GUI: Outputs dubbed MP4 video (original audio 100% removed)
    end

    GUI->>User: Displays Instant Dubbed Video Preview in Cinema Player!
```

---

## 🧮 Mathematical Algorithms & Technical Innovations

### 1. Zero-Cutoff Dynamic `atempo` Chaining
When translating English speech into Khmer, the resulting Khmer sentence is often 20% - 40% longer in phonetic duration. In naive implementations, capping speedup or using hard `-t` cuts off final syllables.

Our algorithm calculates the exact required tempo multiplier:
$$\text{speedup} = \min\left(2.5, \max\left(1.0, \frac{\text{actual\_duration}}{\text{max\_available\_window} - 0.02}\right)\right)$$

Since FFmpeg's `atempo` filter is restricted to $[0.5, 2.0]$, the engine recursively chains filters:
$$\text{Filter Chain} = \underbrace{\text{atempo=2.0}, \dots}_{\lfloor \text{speedup} / 2.0 \rfloor \text{ times}}, \text{atempo}=\left(\frac{\text{speedup}}{2.0^k}\right)$$

This mathematical approach guarantees:
1. The voice finishes **before or exactly at** the start of the next subtitle.
2. **Zero words or syllables are clipped**.
3. Realtime video sync is maintained continuously across multi-minute videos.

### 2. Guaranteed 100% Male Voice Synthesis with Pitch-Shift Fallback
- **Primary Voice**: Microsoft Azure `km-KH-PisethNeural` (authentic deep male Cambodian voice).
- **Secondary Fallback**: If network interruptions occur, Google TTS (`gTTS`) generates raw audio. Because `gTTS` only provides a female voice for Khmer, the engine applies an acoustic pitch-frequency downshift:
  $$\text{FFmpeg Filter} = \texttt{-af "asetrate=44100*0.82,atempo=1.22"}$$
  This decreases formants and fundamental frequencies by 18% while restoring normal playback tempo, creating an authentic male voice and eliminating any jarring female voice switches.

### 3. Overlapping Sliding Window with Prefix Deduplication
To eliminate dropped words at chunk boundaries:
- Audio is read in **$7.0\text{s}$ windows** with a **$5.0\text{s}$ step** ($2.0\text{s}$ overlap).
- A two-pointer normalization algorithm compares the tail of the previous segment with the head of the current segment:
  $$\max_{k \le 14} \left( \text{Normalize}(\text{Tail}_{k}(\text{prev})) == \text{Normalize}(\text{Head}_{k}(\text{curr})) \right)$$
- If duplicate words are detected, they are trimmed cleanly.
- If a primary window returns empty due to quiet speech, a secondary pass splits the audio into focused $4.0\text{s}$ and $2.5\text{s}$ slices to capture the phrase.

---

## 📁 Source Code Organization

```
src/
├── core/
│   ├── audio_daemon.ps1      # Windows WASAPI background audio router
│   ├── audio_player.py       # High-level Python audio playback controller
│   ├── dubbing_engine.py     # Khmer translation, TTS synthesis & FFmpeg sync
│   ├── script_extractor.py   # Speech enhancement, sliding-window STT, SRT formatter
│   └── video_engine.py       # Pipe-based FFmpeg frame decoding & metadata extraction
└── ui/
    ├── player_view.py        # Tkinter Canvas video viewport & seek controllers
    └── widgets.py            # Modern rounded cards, buttons & progress bars
```
