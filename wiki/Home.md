# Welcome to Video Translate & Subtitle Studio Wiki 🎬✨

> **Department of Computer Science / University Team Project**  
> **Course Assignment**: AI-Powered Multimedia Processing & Video Localization Desktop Application  
> **Repository**: [cingcing12/AI_Tool](https://github.com/cingcing12/AI_Tool)

---

## 📌 Project Overview

**Video Translate & Subtitle Studio** is an advanced desktop multimedia studio engineered in Python. It seamlessly bridges speech recognition, neural machine translation, synchronized voiceover synthesis, and video streaming into a single, highly intuitive application.

```mermaid
flowchart LR
    A["🎬 Source Video (MP4)"] --> B["🎙️ 1. Audio & Speech Extraction"]
    B --> C["📝 English Subtitles (.SRT)"]
    C --> D["🇰🇭 2. Natural Khmer Translation"]
    D --> E["🗣️ 3. Neural Voiceover Synthesis"]
    E --> F["🎞️ 4. Clean Audio-Video Merging"]
    F --> G["✨ Dubbed Video (Pure Khmer Audio)"]
```

### Core Capabilities
- **High-FPS Video Player**: In-memory FFmpeg video decoding with smooth 25+ FPS playback, YouTube-style double-click seeking (`-10s` / `+10s`), and interactive scrubbers.
- **Precision Subtitle Extraction**: Automated speech-to-text generation using 16kHz mono audio enhancement, overlapping sliding windows, and prefix deduplication.
- **Accurate Khmer Translation**: Multi-provider translation engine (`googletrans` session-authenticated API + `deep_translator` fallback) with 429 rate limit immunity.
- **Realtime Synchronized Khmer Voiceover**: Timeline-locked neural voice generation (Male: `km-KH-PisethNeural`, Female: `km-KH-SreymomNeural`) with dynamic tempo adjustments and pitch-shifted fallbacks.
- **Pure Video Audio Replacement**: 100% removal of original speech/noise, replacing it with pristine studio-quality Khmer narration.
- **Hardware-Aware Audio Routing**: Background Windows Media Foundation daemon (`audio_daemon.ps1`) for seamless hot-swapping between headphones and speakers.

---

## 📑 Wiki Documentation Navigation

| Wiki Page | Description | Lead Owner |
| :--- | :--- | :--- |
| 👥 [Team Roles & Task Assignments](Team-Roles-&-Task-Assignments) | RACI matrix, member duties, Student IDs, and task progress | **Eang Panha** |
| 🏗️ [System Architecture & Pipeline](System-Architecture-&-Pipeline) | Deep dive into technical design, data flows, and algorithms | **Vong Sokpheak** |
| 📅 [Sprint Planning & Milestones](Sprint-Planning-&-Milestones) | Sprint schedule, deliverables, progress tracking, and dates | **Eang Panha** |
| 🔀 [Git Workflow & Contribution Guide](Git-Workflow-&-Contribution-Guide) | Branching strategy, commit conventions, and PR review workflow | **VEASNA REAKSA** |
| 📖 [User Manual & Testing Guide](User-Manual-&-Testing-Guide) | Installation, usage instructions, test scenarios, and FAQs | **HIM Lihour** & **NOK Sreylinh** |

---

## 👥 Project Team Roster

| Member Name | Student ID | Core Project Role | Git Handle |
| :--- | :--- | :--- | :--- |
| **Eang Panha** | *Team Owner* | Project Lead & Lead System Architect | `@panha` |
| **Vong Sokpheak** | `DUC-PG-A-2024146` | Core AI & Audio Synthesis Engineer | `@vongsokpheak` |
| **HIM Lihour** | `DUC-PG-A-...` | Speech Processing & NLP Engineer | `@lihour` |
| **NOK Sreylinh** | `DUC-PG-A-2024052` | Frontend UI/UX & Player Designer | `@sreylinh` |
| **VEASNA REAKSA** | `DUC-PG-A-...` | DevOps, System Integration & QA Lead | `@reaksa` |

---

## 🚀 Quick Links
- 💻 **Application Entry Point**: [`main.py`](https://github.com/cingcing12/AI_Tool/blob/main/main.py)
- ⚙️ **One-Click Windows Launcher**: [`run.bat`](https://github.com/cingcing12/AI_Tool/blob/main/run.bat) | [`run.ps1`](https://github.com/cingcing12/AI_Tool/blob/main/run.ps1)
- 📦 **Dependencies**: [`requirements.txt`](https://github.com/cingcing12/AI_Tool/blob/main/requirements.txt)
