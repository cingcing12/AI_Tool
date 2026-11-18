"""
Script Extractor Module (Speech-to-Text & Subtitle Generation)
Standard Professional Engine supporting SpeechRecognition (Pure Python & Safe)
and faster-whisper with automatic fallback.
"""

from __future__ import annotations

import os
import re
import sys
import time
import subprocess
from typing import Callable, List, Optional, Tuple


def seconds_to_srt_timestamp(seconds: float) -> str:
    """
    Convert a duration in seconds to standard SRT timestamp format:
    HH:MM:SS,mmm (e.g. 00:01:23,456)
    """
    total_ms = max(0, int(round(seconds * 1000)))
    hours = total_ms // 3600000
    remainder = total_ms % 3600000
    minutes = remainder // 60000
    remainder = remainder % 60000
    secs = remainder // 1000
    millis = remainder % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class ScriptExtractor:
    """
    High-Performance Video Script & Subtitle (SRT) Extractor.
    Automatically selects the best installed speech engine (faster-whisper or SpeechRecognition).
    """

    def __init__(
        self,
        model_size: str = "base",
        default_language: str = "en-US",
        device: str = "auto"
    ):
        self.model_size = model_size
        self.default_language = default_language
        self.device = device
        self._whisper_model = None

    def get_available_engine(self) -> str:
        """Check which speech-to-text engine is installed and ready."""
        try:
            import faster_whisper
            return "faster-whisper"
        except ImportError:
            pass

        try:
            import speech_recognition
            return "speech_recognition"
        except ImportError:
            pass

        return "none"

    def _get_whisper_model(self):
        """Lazy-load WhisperModel on demand."""
        if self._whisper_model is not None:
            return self._whisper_model

        from faster_whisper import WhisperModel
        compute = "int8" if self.device == "cpu" else "default"
        self._whisper_model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=compute
        )
        return self._whisper_model

    def _detect_speech_segments(
        self,
        audio_path: str,
        total_duration: float,
        ffmpeg_bin: str
    ) -> List[Tuple[float, float]]:
        """
        Use FFmpeg silence detection to divide audio into speech intervals.
        Falls back to 5-second uniform chunks if silence detection returns empty.
        """
        if total_duration <= 0:
            total_duration = 10.0

        segments: List[Tuple[float, float]] = []

        try:
            cmd = [
                ffmpeg_bin,
                "-i", audio_path,
                "-af", "silencedetect=noise=-30dB:d=0.35",
                "-f", "null", "-"
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
            output = proc.stderr or ""

            starts = [float(s) for s in re.findall(r"silence_start:\s*([0-9.]+)", output)]
            ends = [float(e) for e in re.findall(r"silence_end:\s*([0-9.]+)", output)]

            if starts and ends:
                cur = 0.0
                for s_start, s_end in zip(starts, ends):
                    if s_start > cur + 0.5:
                        segments.append((cur, s_start))
                    cur = s_end
                if cur < total_duration - 0.5:
                    segments.append((cur, total_duration))
        except Exception:
            pass

        # Split long segments (>7s) or use uniform 5s chunks if no silences detected
        refined_segments: List[Tuple[float, float]] = []

        if not segments:
            # Fallback: uniform 5-second windows
            step = 5.0
            t = 0.0
            while t < total_duration:
                refined_segments.append((t, min(total_duration, t + step)))
                t += step
        else:
            for start, end in segments:
                dur = end - start
                if dur > 8.0:
                    step = 5.0
                    sub_t = start
                    while sub_t < end:
                        refined_segments.append((sub_t, min(end, sub_t + step)))
                        sub_t += step
                elif dur >= 0.6:
                    refined_segments.append((start, end))

        return refined_segments if refined_segments else [(0.0, total_duration)]

    def extract_script_to_srt(
        self,
        video_path: str,
        output_srt_path: Optional[str] = None,
        language: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None
    ) -> str:
        """
        Extract spoken script from video and format into a standard SubRip (.srt) subtitle file.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        engine = self.get_available_engine()
        if engine == "none":
            raise RuntimeError(
                "No speech recognition engine found!\n"
                "Please run: python -m pip install SpeechRecognition"
            )

        if on_progress:
            on_progress("Extracting audio track for transcription...", 15)

        from .video_engine import VideoEngine
        ve = VideoEngine()
        temp_wav = os.path.join(ve.temp_dir, f"transcribe_{int(time.time())}.wav")
        extracted_wav = ve.extract_audio(video_path, temp_wav)
        audio_file = extracted_wav if (extracted_wav and os.path.exists(extracted_wav)) else video_path

        srt_content = ""
        try:
            if engine == "faster-whisper":
                srt_content = self._transcribe_faster_whisper(
                    audio_file, language, on_progress
                )
            else:
                srt_content = self._transcribe_speech_recognition(
                    audio_file, video_path, ve, language, on_progress
                )
        finally:
            if temp_wav and os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass

        # Save to destination file if specified
        if output_srt_path:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(output_srt_path)), exist_ok=True)
                with open(output_srt_path, "w", encoding="utf-8") as f:
                    f.write(srt_content)
            except Exception:
                # Fallback to saving in the same directory as the video if Downloads is not writeable
                alt_dir = os.path.dirname(os.path.abspath(video_path))
                alt_path = os.path.join(alt_dir, os.path.basename(output_srt_path))
                try:
                    with open(alt_path, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                except Exception:
                    pass

        if on_progress:
            on_progress("Script extraction complete! 🎉", 100)

        return srt_content

    def _transcribe_faster_whisper(
        self,
        audio_path: str,
        language: Optional[str],
        on_progress: Optional[Callable[[str, int], None]]
    ) -> str:
        """Transcription via faster-whisper offline engine."""
        if on_progress:
            on_progress("Loading faster-whisper AI model...", 25)

        model = self._get_whisper_model()

        if on_progress:
            on_progress("Transcribing audio into subtitles (.srt)...", 35)

        segments, info = model.transcribe(
            audio_path,
            language=language,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            beam_size=5
        )

        duration = info.duration or 1.0
        srt_entries: List[str] = []
        index = 1

        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            start_str = seconds_to_srt_timestamp(segment.start)
            end_str = seconds_to_srt_timestamp(segment.end)
            srt_entries.append(f"{index}\n{start_str} --> {end_str}\n{text}\n")
            index += 1

            if on_progress and duration > 0:
                pct = min(95, 35 + int((segment.end / duration) * 60))
                on_progress(f"Transcribing: {segment.end:.1f}s / {duration:.1f}s", pct)

        return "\n".join(srt_entries)

    def _transcribe_speech_recognition(
        self,
        audio_path: str,
        video_path: str,
        video_engine,
        language: Optional[str],
        on_progress: Optional[Callable[[str, int], None]]
    ) -> str:
        """
        Pure-Python Speech Recognition using SpeechRecognition library.
        Zero C++ compilation, 100% safe from Windows Smart App Control blocks.
        """
        import speech_recognition as sr

        if on_progress:
            on_progress("Analyzing speech segments...", 25)

        meta = video_engine.probe_video_metadata(video_path)
        total_dur = meta.get("duration", 0.0)
        if total_dur <= 0:
            total_dur = 10.0

        segments = self._detect_speech_segments(
            audio_path, total_dur, getattr(video_engine, "ffmpeg_path", "ffmpeg")
        )

        recognizer = sr.Recognizer()
        target_lang = language or self.default_language

        srt_entries: List[str] = []
        index = 1
        num_segments = len(segments)

        for i, (seg_start, seg_end) in enumerate(segments):
            dur = seg_end - seg_start
            if dur <= 0.3:
                continue

            try:
                with sr.AudioFile(audio_path) as source:
                    audio_data = recognizer.record(source, offset=seg_start, duration=dur)
                    text = recognizer.recognize_google(audio_data, language=target_lang)
                    text = text.strip() if text else ""
            except (sr.UnknownValueError, Exception):
                text = ""

            if text:
                start_str = seconds_to_srt_timestamp(seg_start)
                end_str = seconds_to_srt_timestamp(seg_end)
                srt_entries.append(f"{index}\n{start_str} --> {end_str}\n{text}\n")
                index += 1

            if on_progress:
                pct = min(95, 25 + int(((i + 1) / num_segments) * 70))
                on_progress(f"Transcribing segment {i + 1}/{num_segments}...", pct)

        if not srt_entries:
            # Fallback if no speech was detected
            srt_entries.append(f"1\n00:00:00,000 --> {seconds_to_srt_timestamp(min(5.0, total_dur))}\n[No clear speech detected]\n")

        return "\n".join(srt_entries)
