"""
Dubbing Engine: Automated Khmer Translation, Realtime Timeline-Synchronized Voiceover,
and Clean Video-Audio Merging (Replacing original audio with pure Khmer narration).
"""

from __future__ import annotations

import os
import re
import time
import asyncio
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple


@dataclass
class TimedSubtitle:
    index: int
    start: float
    end: float
    text: str


def srt_timestamp_to_seconds(ts_str: str) -> float:
    """Convert HH:MM:SS,mmm or HH:MM:SS.mmm to seconds."""
    match = re.match(r"(\d+):(\d+):(\d+)[,\.](\d+)", ts_str.strip())
    if match:
        h, m, s, ms = match.groups()
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms[:3].ljust(3, "0")) / 1000.0
    return 0.0


def seconds_to_srt_timestamp(seconds: float) -> str:
    """Convert seconds to standard HH:MM:SS,mmm."""
    total_ms = max(0, int(round(seconds * 1000)))
    hours = total_ms // 3600000
    remainder = total_ms % 3600000
    minutes = remainder // 60000
    remainder = remainder % 60000
    secs = remainder // 1000
    millis = remainder % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_srt_file(srt_path: str) -> List[TimedSubtitle]:
    """Parse .srt file into structured TimedSubtitle list."""
    if not os.path.exists(srt_path):
        return []
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())
    results: List[TimedSubtitle] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue

        ts_line = None
        text_lines = []
        for line in lines:
            if "-->" in line:
                ts_line = line
            elif ts_line is not None:
                text_lines.append(line)

        if not ts_line:
            continue

        parts = ts_line.split("-->")
        if len(parts) != 2:
            continue

        start_sec = srt_timestamp_to_seconds(parts[0])
        end_sec = srt_timestamp_to_seconds(parts[1])
        text = " ".join(text_lines).strip()
        if text:
            results.append(TimedSubtitle(index=len(results) + 1, start=start_sec, end=end_sec, text=text))

    return results


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
    """High-Performance Khmer Video Dubbing & Realtime Audio Sync Engine."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", temp_dir: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path
        self.temp_dir = temp_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

    def probe_duration(self, audio_file: str) -> float:
        """Probe exact audio duration in seconds via FFmpeg."""
        try:
            cmd = [self.ffmpeg_path, "-i", audio_file]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr or "")
            if m:
                h, mm, s = m.groups()
                return int(h) * 3600 + int(mm) * 60 + float(s)
        except Exception:
            pass
        return 0.0

    def translate_script(
        self,
        source_srt_path: str,
        output_khmer_srt: str,
        output_khmer_txt: str,
        on_progress: Optional[Callable[[str, int], None]] = None
    ) -> Tuple[List[TimedSubtitle], str]:
        """
        Translate an English/source SRT subtitle file to Khmer.
        Returns (list of TimedSubtitle with Khmer text, full continuous text).
        """
        segments = parse_srt_file(source_srt_path)
        khmer_segments: List[TimedSubtitle] = []
        translated_entries = []
        full_text_parts = []
        total = len(segments)

        if not segments:
            # Fallback to plain text read
            with open(source_srt_path, "r", encoding="utf-8") as f:
                content = f.read()
            translated = translate_text_to_khmer(content)
            with open(output_khmer_txt, "w", encoding="utf-8") as f:
                f.write(translated)
            return [], translated

        for i, seg in enumerate(segments):
            if on_progress:
                pct = min(40, 20 + int(((i + 1) / total) * 20))
                on_progress(f"Translating to Khmer ({i + 1}/{total})...", pct)

            khmer_txt = translate_text_to_khmer(seg.text)
            khmer_seg = TimedSubtitle(index=seg.index, start=seg.start, end=seg.end, text=khmer_txt)
            khmer_segments.append(khmer_seg)

            start_str = seconds_to_srt_timestamp(seg.start)
            end_str = seconds_to_srt_timestamp(seg.end)
            translated_entries.append(f"{seg.index}\n{start_str} --> {end_str}\n{khmer_txt}\n")
            if khmer_txt:
                full_text_parts.append(khmer_txt)

        # Save translated SRT
        with open(output_khmer_srt, "w", encoding="utf-8") as f:
            f.write("\n".join(translated_entries))

        # Save continuous Khmer script
        full_khmer_script = " ".join(full_text_parts)
        with open(output_khmer_txt, "w", encoding="utf-8") as f:
            f.write(full_khmer_script)

        return khmer_segments, full_khmer_script

    def synthesize_single_line(self, text: str, voice_type: str, output_path: str) -> bool:
        """Synthesize a single line of Khmer speech using Edge TTS with gTTS fallback."""
        voice_gender = voice_type.lower()
        edge_voice = "km-KH-PisethNeural" if "man" in voice_gender or "male" in voice_gender else "km-KH-SreymomNeural"

        # 1. Edge TTS
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, edge_voice)
            asyncio.run(communicate.save(output_path))
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception:
            pass

        # 2. gTTS fallback
        try:
            from gtts import gTTS
            tts = gTTS(text, lang="km")
            tts.save(output_path)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception:
            pass

        return False

    def generate_timed_voice(
        self,
        khmer_segments: List[TimedSubtitle],
        voice_type: str = "Man",
        total_video_duration: float = 0.0,
        output_audio_path: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None
    ) -> str:
        """
        Synthesize Khmer speech synchronized in REALTIME with video speech timestamps.
        Each subtitle line is spoken at the exact second the person speaks in the video!
        """
        if not output_audio_path:
            output_audio_path = os.path.join(self.temp_dir, f"khmer_timed_narration_{int(time.time())}.wav")

        session_id = int(time.time())
        parts_dir = os.path.join(self.temp_dir, f"tts_session_{session_id}")
        os.makedirs(parts_dir, exist_ok=True)

        concat_list_file = os.path.join(parts_dir, "concat_manifest.txt")
        manifest_lines: List[str] = []

        current_time = 0.0
        total_segments = len(khmer_segments)

        for i, seg in enumerate(khmer_segments):
            if on_progress:
                pct = min(75, 45 + int(((i + 1) / max(1, total_segments)) * 30))
                on_progress(f"Synthesizing realtime voice ({i + 1}/{total_segments})...", pct)

            if not seg.text.strip():
                continue

            # 1. Add silence gap if there is a pause before this segment
            gap = seg.start - current_time
            if gap > 0.04:
                silence_file = os.path.join(parts_dir, f"silence_{i:04d}.wav")
                cmd = [
                    self.ffmpeg_path,
                    "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=mono",
                    "-t", f"{gap:.3f}",
                    "-c:a", "pcm_s16le",
                    "-y", silence_file
                ]
                subprocess.run(cmd, capture_output=True, creationflags=0x08000000)
                if os.path.exists(silence_file):
                    rel_name = os.path.basename(silence_file)
                    manifest_lines.append(f"file '{rel_name}'")
                    current_time += gap

            # 2. Synthesize Khmer speech for this segment
            raw_part = os.path.join(parts_dir, f"raw_part_{i:04d}.mp3")
            success = self.synthesize_single_line(seg.text, voice_type, raw_part)
            if not success or not os.path.exists(raw_part):
                continue

            # Probe synthesized speech duration
            actual_dur = self.probe_duration(raw_part)
            if actual_dur <= 0:
                actual_dur = max(0.5, seg.end - seg.start)

            # 3. Determine available time window until next subtitle starts
            if i + 1 < total_segments:
                max_window = max(0.4, khmer_segments[i + 1].start - seg.start)
            else:
                max_window = max(0.4, seg.end - seg.start)

            final_part = os.path.join(parts_dir, f"final_part_{i:04d}.wav")

            # If speech is slightly longer than the time window, gently adjust tempo
            if actual_dur > max_window + 0.15:
                speedup = min(1.35, max(0.9, actual_dur / max_window))
                cmd = [
                    self.ffmpeg_path,
                    "-i", raw_part,
                    "-af", f"atempo={speedup:.2f}",
                    "-ar", "44100",
                    "-ac", "1",
                    "-c:a", "pcm_s16le",
                    "-y", final_part
                ]
                subprocess.run(cmd, capture_output=True, creationflags=0x08000000)
                actual_dur = actual_dur / speedup
            else:
                cmd = [
                    self.ffmpeg_path,
                    "-i", raw_part,
                    "-ar", "44100",
                    "-ac", "1",
                    "-c:a", "pcm_s16le",
                    "-y", final_part
                ]
                subprocess.run(cmd, capture_output=True, creationflags=0x08000000)

            if os.path.exists(final_part):
                rel_name = os.path.basename(final_part)
                manifest_lines.append(f"file '{rel_name}'")
                current_time += actual_dur

        # 4. Trailing silence up to total video duration
        if total_video_duration > current_time + 0.1:
            trailing_gap = total_video_duration - current_time
            trailing_file = os.path.join(parts_dir, "trailing_silence.wav")
            cmd = [
                self.ffmpeg_path,
                "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=mono",
                "-t", f"{trailing_gap:.3f}",
                "-c:a", "pcm_s16le",
                "-y", trailing_file
            ]
            subprocess.run(cmd, capture_output=True, creationflags=0x08000000)
            if os.path.exists(trailing_file):
                manifest_lines.append(f"file '{os.path.basename(trailing_file)}'")

        # 5. Concatenate all timed segments into the master narration audio
        with open(concat_list_file, "w", encoding="utf-8") as f:
            f.write("\n".join(manifest_lines) + "\n")

        cmd = [
            self.ffmpeg_path,
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_file,
            "-c:a", "aac",
            "-b:a", "192k",
            "-y", output_audio_path
        ]
        subprocess.run(cmd, capture_output=True, creationflags=0x08000000)

        # Cleanup parts directory
        try:
            for f in os.listdir(parts_dir):
                os.remove(os.path.join(parts_dir, f))
            os.rmdir(parts_dir)
        except Exception:
            pass

        return output_audio_path

    def merge_video(
        self,
        video_path: str,
        audio_path: str,
        output_video_path: str,
        remove_original_sound: bool = True,
        background_volume: float = 0.0,
        on_progress: Optional[Callable[[str, int], None]] = None
    ) -> str:
        """
        Merge Khmer voiceover audio into the video.
        When remove_original_sound=True, COMPLETELY drops the original video audio track
        so that ONLY the crystal-clear Khmer voice plays in the final video!
        """
        if on_progress:
            on_progress("Merging pure Khmer voiceover into video (original audio removed)...", 85)

        os.makedirs(os.path.dirname(os.path.abspath(output_video_path)), exist_ok=True)

        if remove_original_sound or background_volume <= 0.0:
            # Map ONLY input 0 video + input 1 Khmer audio (Original video sound is 100% removed!)
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
        else:
            # Mix with ducked background sound if requested
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

        res = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
        if not os.path.exists(output_video_path) or os.path.getsize(output_video_path) == 0:
            err = res.stderr or "FFmpeg merge failed"
            raise RuntimeError(f"Failed to merge video: {err}")

        return output_video_path
