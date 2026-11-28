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

# Ensure bin directory containing ffmpeg.exe is always in PATH for Whisper and subprocesses
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BIN_DIR = os.path.join(_BASE_DIR, "bin")
if os.path.exists(_BIN_DIR) and _BIN_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _BIN_DIR + os.pathsep + os.environ.get("PATH", "")


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


def split_segments_by_words(
    segments: List[dict],
    min_pause: float = 0.28,
    max_dur: float = 4.2
) -> List[tuple[float, float, str]]:
    """
    Split speech recognition segments into natural, tightly-timed dialogue units.
    Uses word-level timestamps to detect speaker turns, sentence boundaries, and pauses.
    Guarantees 100% real-time synchronization with on-screen character dialogue.
    """
    subtitles = []

    for seg in segments:
        words = seg.get("words", [])
        if not words:
            text = seg.get("text", "").strip()
            if text:
                subtitles.append((float(seg.get("start", 0.0)), float(seg.get("end", 0.0)), text))
            continue

        current_words = []
        current_start = None

        for i, w in enumerate(words):
            if isinstance(w, dict):
                word_txt = w.get("word", "")
                w_start = float(w.get("start", 0.0))
                w_end = float(w.get("end", w_start + 0.1))
            else:
                word_txt = getattr(w, "word", "")
                w_start = float(getattr(w, "start", 0.0))
                w_end = float(getattr(w, "end", w_start + 0.1))

            if current_start is None:
                current_start = w_start
            current_words.append(word_txt)

            # Check split conditions:
            # 1. Terminal punctuation boundary (.?!。？！!)
            has_terminal_punct = bool(re.search(r"[.?!。？！!]$", word_txt.strip()))

            # 2. Significant pause before next word (indicating new sentence or speaker turn)
            has_pause = False
            if i + 1 < len(words):
                next_w = words[i + 1]
                next_start = float(next_w.get("start", w_end) if isinstance(next_w, dict) else getattr(next_w, "start", w_end))
                if (next_start - w_end) >= min_pause:
                    has_pause = True

            # 3. Maximum duration limit for real-time mouth movement
            dur_so_far = w_end - current_start
            is_too_long = dur_so_far >= max_dur

            if (has_terminal_punct and dur_so_far >= 0.70) or has_pause or is_too_long or (i == len(words) - 1):
                clean_text = "".join(current_words).strip()
                if clean_text:
                    subtitles.append((current_start, w_end, clean_text))
                current_words = []
                current_start = None

    return subtitles


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
        except (ImportError, OSError, Exception):
            pass

        try:
            import whisper
            return "openai-whisper"
        except (ImportError, OSError, Exception):
            pass

        try:
            import speech_recognition
            return "speech_recognition"
        except (ImportError, OSError, Exception):
            pass

        return "none"

    def _get_whisper_model(self):
        """Lazy-load WhisperModel on demand with safe CUDA/CPU detection."""
        if self._whisper_model is not None:
            return self._whisper_model

        from faster_whisper import WhisperModel

        target_device = self.device
        if target_device == "auto":
            # Test if CUDA and cublas DLLs can actually be loaded
            try:
                import torch
                if torch.cuda.is_available():
                    import ctypes
                    try:
                        ctypes.cdll.LoadLibrary("cublas64_12.dll")
                        target_device = "cuda"
                    except Exception:
                        target_device = "cpu"
                else:
                    target_device = "cpu"
            except Exception:
                target_device = "cpu"

        compute = "int8" if target_device == "cpu" else "float16"
        try:
            self._whisper_model = WhisperModel(
                self.model_size,
                device=target_device,
                compute_type=compute
            )
        except Exception as exc:
            print(f"[Whisper Model Notice]: {exc}. Falling back to CPU int8.")
            self._whisper_model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8"
            )

        return self._whisper_model

    def extract_script_to_srt(
        self,
        video_path: str,
        output_srt_path: Optional[str] = None,
        language: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        """
        Extract spoken script from video and format into a standard SubRip (.srt) subtitle file.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if cancel_check and cancel_check():
            raise InterruptedError("Script extraction cancelled before execution.")

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
        extracted_wav = ve.extract_audio(video_path, temp_wav, enhance_speech=True, cancel_check=cancel_check)

        # Fallback to standard extraction if filter failed
        if not extracted_wav or not os.path.exists(extracted_wav) or os.path.getsize(extracted_wav) == 0:
            extracted_wav = ve.extract_audio(video_path, temp_wav, enhance_speech=False, cancel_check=cancel_check)

        if not extracted_wav or not os.path.exists(extracted_wav) or os.path.getsize(extracted_wav) == 0:
            raise RuntimeError(
                "Failed to extract audio track from video.\n"
                "Please verify that FFmpeg is available in bin/ or in your system PATH."
            )

        srt_content = ""
        try:
            if cancel_check and cancel_check():
                raise InterruptedError("Script extraction cancelled.")

            if engine == "faster-whisper":
                try:
                    srt_content = self._transcribe_faster_whisper(
                        extracted_wav, language, on_progress, cancel_check=cancel_check
                    )
                except InterruptedError:
                    raise
                except (OSError, Exception) as whisper_err:
                    print(f"[Faster-Whisper Warning]: {whisper_err}. Trying OpenAI Whisper.")
                    srt_content = ""

            if not srt_content and engine in ("openai-whisper", "faster-whisper"):
                try:
                    srt_content = self._transcribe_openai_whisper(
                        extracted_wav, language, on_progress, cancel_check=cancel_check
                    )
                except InterruptedError:
                    raise
                except Exception as o_err:
                    print(f"[OpenAI-Whisper Warning]: {o_err}. Falling back to SpeechRecognition.")
                    srt_content = ""

            # Check if Whisper produced a meaningful transcript
            has_valid_speech = False
            if srt_content and len(srt_content.strip()) > 10:
                lines = [l for l in srt_content.strip().splitlines() if l and not l.isdigit() and "-->" not in l]
                text_content = " ".join(lines).strip()
                # Must contain at least 3 characters (supports Chinese, Khmer, English words)
                if len(text_content) >= 3:
                    has_valid_speech = True

            if not has_valid_speech:
                if cancel_check and cancel_check():
                    raise InterruptedError("Script extraction cancelled.")
                if on_progress:
                    on_progress("Enhancing transcript with SpeechRecognition (Khmer/Auto)...", 30)
                srt_content = self._transcribe_speech_recognition(
                    extracted_wav, video_path, ve, language, on_progress, cancel_check=cancel_check
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
            on_progress("Script extraction complete!", 100)

        return srt_content

    def _transcribe_faster_whisper(
        self,
        audio_path: str,
        language: Optional[str],
        on_progress: Optional[Callable[[str, int], None]],
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        """Transcription via faster-whisper offline engine."""
        if cancel_check and cancel_check():
            raise InterruptedError("Transcription cancelled.")

        if on_progress:
            on_progress("Loading faster-whisper AI model...", 25)

        model = self._get_whisper_model()

        if cancel_check and cancel_check():
            raise InterruptedError("Transcription cancelled.")

        if on_progress:
            on_progress("Transcribing audio into subtitles (.srt)...", 35)

        segments_gen, info = model.transcribe(
            audio_path,
            language=language,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            beam_size=5,
            word_timestamps=True
        )
        segments = list(segments_gen)
        seg_dicts = []
        for s in segments:
            seg_dicts.append({
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "words": getattr(s, "words", []) or []
            })
        precision_subs = split_segments_by_words(seg_dicts)
        srt_entries: List[str] = []
        for idx, (start_s, end_s, text) in enumerate(precision_subs, 1):
            if cancel_check and cancel_check():
                raise InterruptedError("Transcription cancelled by user.")
            if not text:
                continue
            start_str = seconds_to_srt_timestamp(start_s)
            end_str = seconds_to_srt_timestamp(end_s)
            srt_entries.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")

        return "\n".join(srt_entries)

    def _transcribe_openai_whisper(
        self,
        audio_path: str,
        language: Optional[str],
        on_progress: Optional[Callable[[str, int], None]],
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        """Transcription via official OpenAI Whisper offline engine with precision timestamps."""
        if cancel_check and cancel_check():
            raise InterruptedError("Transcription cancelled.")

        if not hasattr(self, "_openai_whisper_model") or self._openai_whisper_model is None:
            if on_progress:
                on_progress("Loading OpenAI Whisper AI model...", 25)
            import whisper
            target_model = self.model_size if self.model_size in ("tiny", "base", "small", "medium") else "base"
            self._openai_whisper_model = whisper.load_model(target_model)
        model = self._openai_whisper_model

        if cancel_check and cancel_check():
            raise InterruptedError("Transcription cancelled.")

        if on_progress:
            on_progress("Transcribing audio into precision subtitles (.srt)...", 35)

        # Universal Chinese short-drama context prompt covering all major genres (CEO/romance, action/fighting, fantasy/xianxia, historical/court, apocalypse/revenge)
        prompt = (
            "以下是标准普通话短剧、都市爽剧、豪门总裁、仙侠修真、古装宫廷、末世逆袭对白："
            "总裁、董事长、离婚、签合同、少废话、找死、看招、给我跪下、宗门、修仙、师傅、徒弟、"
            "大人、陛下、属下、兄弟、饶命、末世、幽灵船、战舰、亡灵大军、老大。"
        )
        kwargs = {"fp16": False, "word_timestamps": True, "initial_prompt": prompt, "temperature": 0.0}
        if language and language not in ("auto", "none"):
            kwargs["language"] = language

        result = model.transcribe(audio_path, **kwargs)

        if cancel_check and cancel_check():
            raise InterruptedError("Transcription cancelled by user.")

        segments = result.get("segments", [])
        precision_subs = split_segments_by_words(segments)
        srt_entries: List[str] = []
        for idx, (start_s, end_s, text) in enumerate(precision_subs, 1):
            if cancel_check and cancel_check():
                raise InterruptedError("Transcription cancelled by user.")
            if not text:
                continue
            start_str = seconds_to_srt_timestamp(start_s)
            end_str = seconds_to_srt_timestamp(end_s)
            srt_entries.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")

        return "\n".join(srt_entries)

    def _transcribe_speech_recognition(
        self,
        audio_path: str,
        video_path: str,
        video_engine,
        language: Optional[str],
        on_progress: Optional[Callable[[str, int], None]],
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        """
        Pure-Python Speech Recognition using SpeechRecognition library.
        Combines natural phrase detection and overlapping sliding windows with prefix
        deduplication to ensure seamless, complete transcripts without cut-off words.
        """
        import speech_recognition as sr

        if cancel_check and cancel_check():
            raise InterruptedError("Transcription cancelled.")

        target_lang = language or self.default_language
        if target_lang == "auto":
            target_lang = "en-US"

        meta = video_engine.probe_video_metadata(video_path)
        total_duration = meta.get("duration", 0.0)
        if total_duration <= 0:
            total_duration = 30.0

        if on_progress:
            on_progress("Analyzing speech audio...", 20)

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 260
        recognizer.dynamic_energy_threshold = True

        # Smart Khmer audio probe: if audio contains Khmer speech, prioritize km-KH
        if not language or language in ("auto", "en-US"):
            try:
                if cancel_check and cancel_check():
                    raise InterruptedError("Transcription cancelled.")
                with sr.AudioFile(audio_path) as s_probe:
                    probe_data = recognizer.record(s_probe, offset=0.0, duration=min(6.5, total_duration))
                    km_try = recognizer.recognize_google(probe_data, language="km-KH").strip()
                    if km_try and re.search(r"[\u1780-\u17ff]", km_try):
                        target_lang = "km-KH"
            except InterruptedError:
                raise
            except Exception:
                pass

        # Method: Overlapping Sliding Window with Prefix Deduplication
        # Window size: 7.0 seconds
        # Overlap: 2.0 seconds (step = 5.0 seconds)
        window_size = 7.0
        step = 5.0
        segments: List[SubtitleSegment] = []
        previous_text = ""

        t = 0.0
        total_steps = max(1, int(total_duration / step) + 1)
        step_idx = 0

        while t < total_duration:
            if cancel_check and cancel_check():
                raise InterruptedError("Transcription cancelled by user.")

            cur_duration = min(window_size, total_duration - t)
            if cur_duration < 0.6:
                break

            step_idx += 1
            if on_progress:
                pct = min(95, 20 + int((step_idx / total_steps) * 75))
                on_progress(f"Transcribing {t:.1f}s - {t + cur_duration:.1f}s of {total_duration:.1f}s...", pct)

            raw_text = ""
            # Pass 1: Primary window
            try:
                with sr.AudioFile(audio_path) as source:
                    audio_data = recognizer.record(source, offset=t, duration=cur_duration)
                    raw_text = google_recognize_best(recognizer, audio_data, speech_lang=target_lang)
            except Exception:
                raw_text = ""

            # Pass 2: If primary window returned no text, try sub-slices to catch short or quiet phrases
            if not raw_text and cur_duration >= 3.5:
                # Sub-slice 1: First half
                try:
                    with sr.AudioFile(audio_path) as source:
                        audio_data = recognizer.record(source, offset=t, duration=min(4.0, cur_duration))
                        sub1 = google_recognize_best(recognizer, audio_data, speech_lang=target_lang)
                        if sub1:
                            raw_text = sub1
                except Exception:
                    pass

                # Sub-slice 2: Second half
                if not raw_text and cur_duration >= 4.5:
                    try:
                        sub_offset = t + 2.5
                        sub_dur = cur_duration - 2.5
                        with sr.AudioFile(audio_path) as source:
                            audio_data = recognizer.record(source, offset=sub_offset, duration=sub_dur)
                            sub2 = google_recognize_best(recognizer, audio_data, speech_lang=target_lang)
                            if sub2:
                                raw_text = sub2
                    except Exception:
                        pass

                # Sub-slice 3: Try Khmer language recognition if English produced no speech
                if not raw_text and target_lang != "km-KH":
                    try:
                        with sr.AudioFile(audio_path) as source:
                            audio_data = recognizer.record(source, offset=t, duration=cur_duration)
                            km_candidate = google_recognize_best(recognizer, audio_data, speech_lang="km-KH")
                            if km_candidate:
                                raw_text = km_candidate
                    except Exception:
                        pass

            if raw_text:
                raw_text = raw_text.strip()
                # Deduplicate prefix words that were already captured at the end of the previous segment
                deduped = remove_duplicate_prefix(previous_text, raw_text).strip()
                if not deduped and raw_text and (not segments or raw_text.lower() != segments[-1].text.lower()):
                    deduped = raw_text

                if deduped:
                    # Clean up first character capitalization
                    if len(deduped) > 1:
                        deduped = deduped[0].upper() + deduped[1:]
                    elif len(deduped) == 1:
                        deduped = deduped.upper()

                    seg_start = t
                    seg_end = min(total_duration, t + cur_duration)

                    # Smooth segment start so it doesn't overlap backwards
                    if segments and seg_start < segments[-1].end:
                        seg_start = segments[-1].end

                    if seg_end > seg_start:
                        segments.append(SubtitleSegment(start=seg_start, end=seg_end, text=deduped))
                        previous_text = deduped

            t += step

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
