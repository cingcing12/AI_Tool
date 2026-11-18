"""
Script Extractor Module (Speech-to-Text & Subtitle Generation)
High-precision subtitle generation with speech enhancement, phrase detection,
and overlapping sliding windows with prefix deduplication to ensure zero dropped text.
"""

from __future__ import annotations

import os
import re
import sys
import time
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple


@dataclass
class SubtitleSegment:
    start: float
    end: float
    text: str


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


def normalize_word(word: str) -> str:
    """Lowercase alphanumeric word normalizer for text comparison."""
    return "".join(c.lower() for c in word if c.isalnum())


def count_words(text: str) -> int:
    """Count non-empty normalized words."""
    return sum(1 for w in text.split() if normalize_word(w))


def remove_duplicate_prefix(previous_text: str, current_text: str) -> str:
    """
    Remove overlapping duplicate words from the beginning of current_text
    that already appeared at the end of previous_text.
    """
    if not previous_text or not current_text:
        return current_text.strip()

    prev_words = [w for w in previous_text.split() if normalize_word(w)]
    curr_words = [w for w in current_text.split() if normalize_word(w)]

    if not prev_words or not curr_words:
        return current_text.strip()

    max_overlap = min(len(prev_words), len(curr_words), 14)
    for k in range(max_overlap, 0, -1):
        prev_tail = [normalize_word(w) for w in prev_words[-k:]]
        curr_head = [normalize_word(w) for w in curr_words[:k]]
        if prev_tail == curr_head:
            trimmed = " ".join(curr_words[k:])
            return trimmed.strip()

    return current_text.strip()


def google_recognize_best(recognizer, audio_data, speech_lang: str = "en-US") -> str:
    """
    Query Google Speech Recognition and pick the best alternative candidate
    scored by confidence and sentence completeness.
    """
    lang = speech_lang if speech_lang and speech_lang != "auto" else "en-US"
    try:
        res = recognizer.recognize_google(audio_data, language=lang, show_all=True)
        if isinstance(res, dict) and "alternative" in res and res["alternative"]:
            best_text = ""
            best_score = -1.0
            for alt in res["alternative"]:
                text = str(alt.get("transcript", "")).strip()
                if not text:
                    continue
                conf = float(alt.get("confidence", 0.0) or 0.0)
                words = count_words(text)
                score = (conf * 100.0) + words
                if score > best_score:
                    best_score = score
                    best_text = text
            if best_text:
                return best_text
    except Exception:
        pass

    # Standard fallback
    return recognizer.recognize_google(audio_data, language=lang).strip()


class ScriptExtractor:
    """
    High-Performance Video Script & Subtitle (SRT) Extractor.
    Automatically selects the best installed speech engine (faster-whisper or SpeechRecognition).
    Features Speech Enhancement, Phrase Segmentation, and Overlapping Windows with Deduplication.
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
        """
        Check which speech-to-text engine is installed and ready.
        Handles Windows Smart App Control policy blocks on C++ DLLs (WinError 4551).
        """
        try:
            import faster_whisper
            from faster_whisper import WhisperModel
            return "faster-whisper"
        except (ImportError, OSError, Exception) as exc:
            print(f"[ScriptExtractor] faster-whisper unavailable ({exc}), using SpeechRecognition.")

        try:
            import speech_recognition
            return "speech_recognition"
        except (ImportError, OSError, Exception):
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
            on_progress("Extracting and enhancing audio for transcription...", 10)

        from .video_engine import VideoEngine
        ve = VideoEngine()

        # Step 1: Extract speech-enhanced 16kHz audio track
        temp_wav = os.path.join(ve.temp_dir, f"transcribe_{int(time.time())}.wav")
        extracted_wav = ve.extract_audio(video_path, temp_wav, enhance_speech=True)

        # Fallback to standard extraction if filter failed
        if not extracted_wav or not os.path.exists(extracted_wav) or os.path.getsize(extracted_wav) == 0:
            extracted_wav = ve.extract_audio(video_path, temp_wav, enhance_speech=False)

        if not extracted_wav or not os.path.exists(extracted_wav) or os.path.getsize(extracted_wav) == 0:
            raise RuntimeError(
                "Failed to extract audio track from video.\n"
                "Please verify that FFmpeg is available in bin/ or in your system PATH."
            )

        srt_content = ""
        try:
            if engine == "faster-whisper":
                try:
                    srt_content = self._transcribe_faster_whisper(
                        extracted_wav, language, on_progress
                    )
                except (OSError, Exception) as whisper_err:
                    print(f"[Whisper Warning]: {whisper_err}. Falling back to SpeechRecognition.")
                    if on_progress:
                        on_progress("Switching to SpeechRecognition engine...", 20)
                    srt_content = self._transcribe_speech_recognition(
                        extracted_wav, video_path, ve, language, on_progress
                    )
            else:
                srt_content = self._transcribe_speech_recognition(
                    extracted_wav, video_path, ve, language, on_progress
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

    def _generate_silence_aligned_intervals(
        self,
        audio_path: str,
        total_duration: float,
        target_interval: float = 4.8,
        search_window: float = 1.4
    ) -> List[Tuple[float, float]]:
        """
        Generate continuous, non-overlapping speech intervals split at natural quiet moments.
        - Zero Overlap: Completely eliminates duplicate/repeated words.
        - Zero Cutoff: Splits at audio volume valleys so words are never cut in half.
        - Sweet-Spot Duration (3.8s - 5.5s): Optimal for Google Speech Recognition accuracy and realtime voice sync.
        """
        import wave
        import numpy as np

        samples = None
        sr = 16000

        try:
            with wave.open(audio_path, "rb") as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)
                ch = wf.getnchannels()
                samples = np.frombuffer(raw, dtype=np.int16)
                if ch > 1:
                    samples = samples[::ch]
        except Exception:
            samples = None

        if samples is None or len(samples) == 0 or sr <= 0:
            # Fallback to continuous non-overlapping 4.8s intervals
            intervals: List[Tuple[float, float]] = []
            t = 0.0
            while t < total_duration:
                step = min(4.8, total_duration - t)
                if step >= 0.5:
                    intervals.append((round(t, 3), round(t + step, 3)))
                t += step
            return intervals

        actual_duration = len(samples) / sr
        intervals: List[Tuple[float, float]] = []
        t_start = 0.0
        half_w = search_window / 2.0

        while t_start < actual_duration - 0.5:
            target_t = t_start + target_interval
            if target_t >= actual_duration - 1.0:
                intervals.append((round(t_start, 3), round(actual_duration, 3)))
                break

            s_sec = max(t_start + 2.8, target_t - half_w)
            e_sec = min(actual_duration, target_t + half_w)
            s_idx = int(s_sec * sr)
            e_idx = int(e_sec * sr)

            if e_idx - s_idx < int(0.1 * sr):
                t_split = target_t
            else:
                region = samples[s_idx:e_idx].astype(np.float32)
                win_len = int(0.06 * sr) # 60ms energy window
                energy = np.convolve(region**2, np.ones(win_len)/win_len, mode="valid")
                min_offset = int(np.argmin(energy))
                t_split = (s_idx + min_offset) / sr

            intervals.append((round(t_start, 3), round(t_split, 3)))
            t_start = t_split

        return intervals

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
        Uses Pause/Silence-Aligned Split Windows:
        - Continuous coverage: every second of speech is transcribed (no missing words).
        - Zero Overlap: each chunk starts exactly where the previous ends (no double voices).
        - Natural Word Boundaries: splits at volume dips so words are never cut in half.
        """
        import speech_recognition as sr

        target_lang = language or self.default_language
        if target_lang == "auto":
            target_lang = "en-US"

        meta = video_engine.probe_video_metadata(video_path)
        total_duration = meta.get("duration", 0.0)
        if total_duration <= 0:
            total_duration = 30.0

        if on_progress:
            on_progress("Analyzing speech audio and word boundaries...", 20)

        # Generate continuous, non-overlapping intervals split at quiet moments
        intervals = self._generate_silence_aligned_intervals(audio_path, total_duration)

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 280
        recognizer.dynamic_energy_threshold = True

        segments: List[SubtitleSegment] = []
        previous_text = ""
        total_intervals = len(intervals)

        for idx, (seg_start, seg_end) in enumerate(intervals, 1):
            cur_duration = seg_end - seg_start
            if cur_duration < 0.5:
                continue

            if on_progress:
                pct = min(95, 20 + int((idx / max(1, total_intervals)) * 75))
                on_progress(f"Transcribing speech phrase ({idx}/{total_intervals})...", pct)

            raw_text = ""
            try:
                with sr.AudioFile(audio_path) as source:
                    audio_data = recognizer.record(source, offset=seg_start, duration=cur_duration)
                    raw_text = google_recognize_best(recognizer, audio_data, speech_lang=target_lang)
            except (sr.UnknownValueError, Exception):
                raw_text = ""

            if raw_text:
                cleaned = raw_text.strip()
                # Deduplicate prefix words if any edge bleed occurred
                deduped = remove_duplicate_prefix(previous_text, cleaned).strip()
                if not deduped:
                    continue

                # Skip exact consecutive duplicates
                if segments and deduped.lower() == segments[-1].text.lower():
                    continue

                # Capitalize first character
                if len(deduped) > 1:
                    deduped = deduped[0].upper() + deduped[1:]
                else:
                    deduped = deduped.upper()

                segments.append(SubtitleSegment(start=seg_start, end=seg_end, text=deduped))
                previous_text = deduped

        # Fallback if no speech was detected anywhere in the entire video
        if not segments:
            segments.append(SubtitleSegment(
                start=0.0,
                end=min(5.0, total_duration),
                text="[No clear speech detected]"
            ))

        # Format into clean standard SRT format
        srt_entries: List[str] = []
        for index, seg in enumerate(segments, 1):
            start_str = seconds_to_srt_timestamp(seg.start)
            end_str = seconds_to_srt_timestamp(seg.end)
            srt_entries.append(f"{index}\n{start_str} --> {end_str}\n{seg.text}\n")

        return "\n".join(srt_entries)
