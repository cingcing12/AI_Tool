"""
Dubbing Engine: Automated Khmer Translation, Neural Voiceover Generation, and Audio-Video Merging.
"""

from __future__ import annotations

import os
import re
import time
import asyncio
import subprocess
from typing import Callable, List, Optional, Tuple


def parse_srt(srt_path: str) -> List[Tuple[str, str, str]]:
    """Parse .srt file into list of (index, timestamp_line, text)."""
    if not os.path.exists(srt_path):
        return []
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())
    entries = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) >= 3:
            idx = lines[0]
            ts = lines[1]
            txt = " ".join(lines[2:])
            entries.append((idx, ts, txt))
        elif len(lines) == 2 and "-->" in lines[0]:
            ts = lines[0]
            txt = lines[1]
            entries.append((str(len(entries) + 1), ts, txt))
    return entries


def translate_text_to_khmer(text: str) -> str:
    """
    Robust multi-provider translation to Khmer.
    Tries GoogleTranslator first, falls back to MyMemoryTranslator.
    """
    cleaned = text.strip()
    if not cleaned:
        return ""

    # Provider 1: GoogleTranslator
    try:
        from deep_translator import GoogleTranslator
        res = GoogleTranslator(source="auto", target="km").translate(cleaned)
        if res and res.strip():
            return res.strip()
    except Exception:
        pass

    # Provider 2: MyMemoryTranslator
    try:
        from deep_translator import MyMemoryTranslator
        res = MyMemoryTranslator(source="en-US", target="km-KH").translate(cleaned)
        if res and res.strip():
            return res.strip()
    except Exception:
        pass

    return cleaned


class DubbingEngine:
    """High-Performance Khmer Video Dubbing & Audio Merge Engine."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", temp_dir: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path
        self.temp_dir = temp_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

    def translate_script(
        self,
        source_srt_path: str,
        output_khmer_srt: str,
        output_khmer_txt: str,
        on_progress: Optional[Callable[[str, int], None]] = None
    ) -> str:
        """
        Translate an English/source SRT subtitle file to Khmer.
        Saves both the translated .srt and continuous .txt script.
        """
        entries = parse_srt(source_srt_path)
        if not entries:
            # Fallback to plain text read
            with open(source_srt_path, "r", encoding="utf-8") as f:
                content = f.read()
            translated = translate_text_to_khmer(content)
            with open(output_khmer_txt, "w", encoding="utf-8") as f:
                f.write(translated)
            return translated

        translated_entries = []
        full_text_parts = []
        total = len(entries)

        for i, (idx, ts, txt) in enumerate(entries):
            if on_progress:
                pct = min(40, 20 + int(((i + 1) / total) * 20))
                on_progress(f"Translating to Khmer ({i + 1}/{total})...", pct)

            khmer_txt = translate_text_to_khmer(txt)
            translated_entries.append(f"{idx}\n{ts}\n{khmer_txt}\n")
            if khmer_txt:
                full_text_parts.append(khmer_txt)

        # Save translated SRT
        with open(output_khmer_srt, "w", encoding="utf-8") as f:
            f.write("\n".join(translated_entries))

        # Save continuous Khmer script
        full_khmer_script = " ".join(full_text_parts)
        with open(output_khmer_txt, "w", encoding="utf-8") as f:
            f.write(full_khmer_script)

        return full_khmer_script

    def generate_voice(
        self,
        khmer_text: str,
        voice_type: str = "Man",
        output_audio_path: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None
    ) -> str:
        """
        Generate authentic Khmer voiceover using Microsoft Edge Neural TTS
        with gTTS + pitch shift fallback.
        """
        if not output_audio_path:
            output_audio_path = os.path.join(self.temp_dir, f"khmer_voice_{int(time.time())}.mp3")

        voice_gender = voice_type.lower()
        # Edge TTS voices: Piseth (Male) and Sreymom (Female)
        edge_voice = "km-KH-PisethNeural" if "man" in voice_gender or "male" in voice_gender else "km-KH-SreymomNeural"

        if on_progress:
            on_progress(f"Generating Khmer {voice_type} voiceover...", 55)

        # 1. Try Microsoft Edge Neural Voice
        try:
            import edge_tts
            communicate = edge_tts.Communicate(khmer_text, edge_voice)
            asyncio.run(communicate.save(output_audio_path))
            if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 0:
                return output_audio_path
        except Exception as e:
            print(f"[Voice Gen] edge-tts error: {e}, falling back to gTTS...")

        # 2. Fallback to gTTS
        from gtts import gTTS
        temp_gtts = os.path.join(self.temp_dir, f"raw_gtts_{int(time.time())}.mp3")
        tts = gTTS(khmer_text, lang="km")
        tts.save(temp_gtts)

        # Apply pitch adjustment for Man/Woman persona if ffmpeg is available
        if os.path.exists(self.ffmpeg_path) and ("man" in voice_gender or "male" in voice_gender):
            pitch_filter = "asetrate=24000*0.87,atempo=1.15"
            cmd = [
                self.ffmpeg_path,
                "-i", temp_gtts,
                "-af", pitch_filter,
                "-y", output_audio_path
            ]
            subprocess.run(cmd, capture_output=True, creationflags=0x08000000)
            if os.path.exists(temp_gtts):
                try:
                    os.remove(temp_gtts)
                except Exception:
                    pass
            if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 0:
                return output_audio_path

        # Direct return if pitch shifting wasn't needed or failed
        if os.path.exists(temp_gtts):
            if os.path.exists(output_audio_path):
                os.remove(output_audio_path)
            os.rename(temp_gtts, output_audio_path)

        return output_audio_path

    def merge_video(
        self,
        video_path: str,
        audio_path: str,
        output_video_path: str,
        background_volume: float = 0.20,
        has_audio: bool = True,
        on_progress: Optional[Callable[[str, int], None]] = None
    ) -> str:
        """
        Merge Khmer voiceover audio into the video.
        Ducks original audio down to background_volume (default 20%) while keeping
        Khmer voice at 100% volume, and copies video stream directly without quality loss.
        """
        if on_progress:
            on_progress("Merging Khmer voiceover into video...", 80)

        os.makedirs(os.path.dirname(os.path.abspath(output_video_path)), exist_ok=True)

        if has_audio:
            # Mix background audio with new narration
            filter_str = f"[0:a]volume={background_volume:.2f}[bg];[1:a]volume=1.0[voice];[bg][voice]amix=inputs=2:duration=first[aout]"
            cmd = [
                self.ffmpeg_path,
                "-i", video_path,
                "-i", audio_path,
                "-filter_complex", filter_str,
                "-map", "0:v:0",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-y", output_video_path
            ]
        else:
            # Video had no audio, just add narration audio track
            cmd = [
                self.ffmpeg_path,
                "-i", video_path,
                "-i", audio_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-y", output_video_path
            ]

        res = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
        if not os.path.exists(output_video_path) or os.path.getsize(output_video_path) == 0:
            err = res.stderr or "FFmpeg merge failed"
            raise RuntimeError(f"Failed to merge video: {err}")

        return output_video_path
