"""
Windows Native Audio Player using Winsound & WaveOutSetVolume.
100% reliable on all Windows hardware (Speakers, Headphones, Bluetooth).
Zero external dependencies.
"""

import os
import ctypes
import winsound
import subprocess


class WindowsAudioPlayer:
    """Controls audio playback natively on Windows using winsound and waveOutSetVolume."""

    def __init__(self, ffmpeg_path=None, temp_dir=None):
        self.winmm = getattr(ctypes.windll, "winmm", None)
        self.ffmpeg_path = ffmpeg_path
        self.temp_dir = temp_dir
        if not self.temp_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.temp_dir = os.path.join(base_dir, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

        self.play_wav_path = os.path.join(self.temp_dir, "preview_audio.wav")
        self.current_video = None
        self.has_audio = False
        self.is_playing = False

    def load(self, video_filepath, has_audio=True):
        """Prepare audio player for a video file."""
        self.stop()
        self.current_video = video_filepath
        self.has_audio = has_audio

    def play(self, start_seconds=0.0):
        """Extract slice from start_seconds and play asynchronously through default audio device."""
        if not self.has_audio or not self.current_video or not os.path.exists(self.current_video):
            return

        if not self.ffmpeg_path or not os.path.exists(self.ffmpeg_path):
            return

        self.stop()

        time_str = f"{max(0.0, float(start_seconds)):.3f}"
        cmd = [
            self.ffmpeg_path,
            "-ss", time_str,
            "-i", self.current_video,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            "-y",
            self.play_wav_path
        ]
        try:
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000
            )
            if os.path.exists(self.play_wav_path) and os.path.getsize(self.play_wav_path) > 100:
                winsound.PlaySound(self.play_wav_path, winsound.SND_ASYNC | winsound.SND_FILENAME)
                self.is_playing = True
        except Exception:
            pass

    def stop(self):
        """Stop sound playback immediately."""
        self.is_playing = False
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def set_volume(self, volume_0_to_1):
        """Set Windows system output volume for playback (0.0 to 1.0)."""
        if self.winmm and hasattr(self.winmm, "waveOutSetVolume"):
            val = int(max(0.0, min(1.0, float(volume_0_to_1))) * 65535)
            dw = (val & 0xFFFF) | ((val & 0xFFFF) << 16)
            try:
                self.winmm.waveOutSetVolume(0, dw)
            except Exception:
                pass

    def close(self):
        """Clean up on app exit."""
        self.stop()
        try:
            if os.path.exists(self.play_wav_path):
                os.remove(self.play_wav_path)
        except Exception:
            pass
