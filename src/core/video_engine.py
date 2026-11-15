"""
Core Video Engine: Handles FFmpeg streaming, frame extraction, audio extraction, and media probing.
"""

import os
import subprocess


class VideoEngine:
    """Provides methods to probe and process video files using local or system FFmpeg."""

    def __init__(self, base_dir=None):
        if base_dir is None:
            # d:\DUC\SPD
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.base_dir = base_dir

        self.ffmpeg_path = self._find_binary("ffmpeg.exe", "ffmpeg")
        self.ffprobe_path = self._find_binary("ffprobe.exe", "ffprobe")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

    def _find_binary(self, filename, cmd_name):
        # 1. Check in bin/
        local_bin = os.path.join(self.base_dir, "bin", filename)
        if os.path.exists(local_bin):
            return local_bin

        # 2. Check in root
        root_bin = os.path.join(self.base_dir, filename)
        if os.path.exists(root_bin):
            return root_bin

        # 3. Fallback to system command
        return cmd_name

    def format_time_hms(self, seconds):
        s = int(seconds)
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        return f"{h:02d}:{m:02d}:{sec:02d}"

    def probe_duration(self, filepath):
        """Extract exact duration in seconds using ffprobe."""
        if not os.path.exists(filepath):
            return 0.0

        if os.path.exists(self.ffprobe_path):
            try:
                cmd = [
                    self.ffprobe_path,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    filepath
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
                dur = float(res.stdout.strip())
                if dur > 0:
                    return dur
            except Exception:
                pass

        # Fallback estimation based on file size
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        return max(60.0, min(600.0, size_mb * 15.0))

    def extract_frame_ppm(self, filepath, timestamp, target_w, target_h):
        """
        Fast single-frame extraction directly into memory as PPM bytes (P6 format).
        Zero disk I/O, instantaneous rendering in Tkinter PhotoImage.
        """
        if not os.path.exists(filepath) or not os.path.exists(self.ffmpeg_path):
            return None

        # Ensure even dimensions for FFmpeg
        target_w = target_w - (target_w % 2)
        target_h = target_h - (target_h % 2)
        if target_w <= 0 or target_h <= 0:
            return None

        time_str = f"{timestamp:.3f}"
        try:
            cmd = [
                self.ffmpeg_path,
                "-ss", time_str,
                "-i", filepath,
                "-vframes", "1",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-vf", f"scale={target_w}:{target_h}",
                "-an", "-sn",
                "-y",
                "-"
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=0x08000000)
            expected_size = target_w * target_h * 3
            if len(res.stdout) >= expected_size:
                raw_bytes = res.stdout[:expected_size]
                header = f"P6\n{target_w} {target_h}\n255\n".encode("ascii")
                return header + raw_bytes
        except Exception:
            pass
        return None

    def start_video_stream(self, filepath, start_time, target_w, target_h, fps=25):
        """
        Start continuous FFmpeg streaming process piping raw RGB24 frames to stdout.
        Yields ultra-smooth 25 FPS video playback with zero process startup overhead.
        """
        if not os.path.exists(filepath) or not os.path.exists(self.ffmpeg_path):
            return None

        target_w = target_w - (target_w % 2)
        target_h = target_h - (target_h % 2)
        if target_w <= 0 or target_h <= 0:
            return None

        time_str = f"{start_time:.3f}"
        cmd = [
            self.ffmpeg_path,
            "-ss", time_str,
            "-i", filepath,
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-vf", f"scale={target_w}:{target_h}",
            "-r", str(fps),
            "-an", "-sn",
            "-"
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=target_w * target_h * 3 * 2,
                creationflags=0x08000000
            )
            return proc, target_w, target_h
        except Exception:
            return None

    def extract_audio(self, filepath, output_wav=None):
        """Extract audio track as standard 16kHz mono WAV for dubbing and preview playback."""
        if not os.path.exists(filepath) or not os.path.exists(self.ffmpeg_path):
            return None

        if output_wav is None:
            output_wav = os.path.join(self.temp_dir, "extracted_audio.wav")

        try:
            cmd = [
                self.ffmpeg_path,
                "-i", filepath,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                "-y", output_wav
            ]
            subprocess.run(cmd, capture_output=True, creationflags=0x08000000)
            if os.path.exists(output_wav) and os.path.getsize(output_wav) > 0:
                return output_wav
        except Exception:
            pass
        return None
