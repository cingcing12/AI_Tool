"""
VoxCPM 2 Khmer Voice Cloning Engine.
High-fidelity zero-shot voice cloning for Khmer (and 30+ languages) using OpenBMB's VoxCPM 2.
Supports reference audio cloning, automatic video speaker extraction, and graceful fallback.
"""

from __future__ import annotations

import os
import re
import sys
import time
import subprocess
from typing import Callable, Optional, Tuple


class VoxCPMEngine:
    """
    VoxCPM 2 Voice Cloning Manager for Khmer Narration & Dubbing.
    Provides on-demand lazy loading, audio preprocessing, and zero-shot synthesis.
    """

    DEFAULT_MODEL_ID = "openbmb/VoxCPM2"
    KHMER_FINETUNED_ID = "ravuthz/VoxCPM2-khmer"

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        ffmpeg_path: str = "ffmpeg",
        temp_dir: Optional[str] = None,
        device: Optional[str] = None
    ):
        self.model_id = model_id
        self.ffmpeg_path = ffmpeg_path
        self.temp_dir = temp_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "temp"
        )
        os.makedirs(self.temp_dir, exist_ok=True)

        self._model = None
        self._is_loading = False
        self._load_error: Optional[str] = None
        self._device = device

    @property
    def is_available(self) -> bool:
        """Check if voxcpm and torch packages are installed in the environment."""
        try:
            import voxcpm  # noqa: F401
            import torch   # noqa: F401
            return True
        except ImportError:
            return False

    def get_preferred_device(self) -> str:
        """Auto-detect optimal device (CUDA vs CPU)."""
        if self._device:
            return self._device
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    def load_model(
        self,
        model_id: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None
    ) -> bool:
        """
        Lazily load the VoxCPM 2 model into memory.
        Returns True if successful, False otherwise.
        """
        if self._model is not None:
            return True

        if not self.is_available:
            self._load_error = "voxcpm package is not installed. Install via: pip install voxcpm soundfile"
            return False

        target_model = model_id or self.model_id
        self._is_loading = True
        self._load_error = None

        try:
            if on_progress:
                on_progress(f"Loading VoxCPM 2 weights ({target_model})...", 10)

            from voxcpm import VoxCPM
            # Load model (disabling standalone denoiser for lower VRAM overhead)
            self._model = VoxCPM.from_pretrained(target_model, load_denoiser=False)
            self.model_id = target_model

            if on_progress:
                on_progress("VoxCPM 2 model loaded successfully!", 100)

            return True
        except Exception as exc:
            self._model = None
            self._load_error = str(exc)
            if on_progress:
                on_progress(f"VoxCPM 2 Load Error: {exc}", 0)
            return False
        finally:
            self._is_loading = False

    def extract_reference_clip(
        self,
        video_or_audio_path: str,
        output_wav_path: str,
        start_sec: float = 2.0,
        duration_sec: float = 6.0
    ) -> bool:
        """
        Extract a clean, normalized 16kHz mono reference sample WAV from a video or audio file.
        A 5-8 second speech segment is optimal for VoxCPM 2 timbre cloning.
        """
        if not os.path.exists(video_or_audio_path):
            return False

        os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)

        cmd = [
            self.ffmpeg_path,
            "-ss", f"{start_sec:.2f}",
            "-t", f"{duration_sec:.2f}",
            "-i", video_or_audio_path,
            "-vn",
            "-af", "highpass=f=100,lowpass=f=7500,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            "-y", output_wav_path
        ]

        try:
            subprocess.run(cmd, capture_output=True, check=True, creationflags=0x08000000)
            return os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 1000
        except Exception:
            return False

    def auto_find_best_speech_segment(
        self,
        audio_path: str,
        min_speech_duration: float = 5.0
    ) -> Tuple[float, float]:
        """
        Detect the first clear continuous speech segment using FFmpeg silencedetect.
        Returns (start_second, duration_second).
        """
        try:
            cmd = [
                self.ffmpeg_path,
                "-i", audio_path,
                "-af", "silencedetect=noise=-30dB:d=0.5",
                "-f", "null",
                "-"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
            log = res.stderr or ""

            # Look for silence intervals
            silence_starts = [float(m) for m in re.findall(r"silence_start:\s*(\d+(?:\.\d+)?)", log)]
            silence_ends = [float(m) for m in re.findall(r"silence_end:\s*(\d+(?:\.\d+)?)", log)]

            if silence_ends and silence_starts:
                # Find first non-silent speech span
                first_speech_start = 0.5
                if silence_starts[0] > 1.0:
                    first_speech_start = 0.5
                    span = silence_starts[0] - first_speech_start
                    if span >= min_speech_duration:
                        return (first_speech_start, min(span, 8.0))

                for s_end, s_next in zip(silence_ends, silence_starts[1:]):
                    span = s_next - s_end
                    if span >= min_speech_duration:
                        return (s_end + 0.2, min(span - 0.4, 8.0))
        except Exception:
            pass

        # Fallback to standard offset
        return (2.0, min_speech_duration)

    def synthesize_khmer_cloned(
        self,
        text: str,
        reference_wav_path: str,
        output_path: str,
        prompt_text: Optional[str] = None,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10
    ) -> bool:
        """
        Synthesize Khmer speech using the cloned voice from reference_wav_path.
        - text: Khmer sentence to speak.
        - reference_wav_path: Path to target speaker voice clip (~5-8s).
        - prompt_text: Optional reference audio transcript for ultimate fidelity.
        - output_path: Where to save generated audio (.wav or .mp3).
        """
        cleaned_text = text.strip()
        if not cleaned_text:
            return False

        if not os.path.exists(reference_wav_path):
            return False

        # Ensure model is ready
        if self._model is None:
            if not self.load_model():
                return False

        try:
            import soundfile as sf

            kwargs = {
                "text": cleaned_text,
                "reference_wav_path": reference_wav_path,
                "cfg_value": cfg_value,
                "inference_timesteps": inference_timesteps
            }

            if prompt_text:
                kwargs["prompt_wav_path"] = reference_wav_path
                kwargs["prompt_text"] = prompt_text

            # VoxCPM 2 generates raw audio tensor/array at model.tts_model.sample_rate (typically 48kHz)
            wav_output = self._model.generate(**kwargs)

            sample_rate = getattr(getattr(self._model, "tts_model", None), "sample_rate", 48000)

            # Save temporary raw wav
            temp_wav = output_path if output_path.lower().endswith(".wav") else output_path + ".raw.wav"
            sf.write(temp_wav, wav_output, sample_rate)

            # If user wanted MP3 or specific format, convert cleanly via FFmpeg
            if output_path.lower().endswith(".mp3") and temp_wav != output_path:
                cmd = [
                    self.ffmpeg_path,
                    "-i", temp_wav,
                    "-c:a", "libmp3lame",
                    "-b:a", "192k",
                    "-y", output_path
                ]
                subprocess.run(cmd, capture_output=True, creationflags=0x08000000)
                if os.path.exists(temp_wav):
                    try:
                        os.remove(temp_wav)
                    except Exception:
                        pass
            elif temp_wav != output_path:
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
                os.rename(temp_wav, output_path)

            return os.path.exists(output_path) and os.path.getsize(output_path) > 100
        except Exception as exc:
            self._load_error = f"Synthesis error: {exc}"
            return False
