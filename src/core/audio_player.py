"""
Windows Media Foundation Native Audio Player.
Supports AUTOMATIC hardware audio switching between Headphones and Speakers
on plug & unplug in real time!
"""

from __future__ import annotations

import os
import sys
import time
import ctypes
import threading
import subprocess
from pathlib import Path
from typing import Optional


class WindowsAudioPlayer:
    """
    High-Performance Windows Audio Player powered by Windows Media Foundation.
    Automatically handles audio endpoint migration (Headphone plug/unplug) in real time!
    """

    def __init__(self, ffmpeg_path=None, temp_dir=None):
        self.ffmpeg_path = ffmpeg_path
        self.temp_dir = temp_dir
        if not self.temp_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.temp_dir = os.path.join(base_dir, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

        self.current_video: Optional[str] = None
        self.has_audio = False
        self.is_playing = False
        self.current_volume = 0.8
        self.current_start_seconds = 0.0

        # Background Media Daemon
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_daemon.ps1")

        # Start background worker
        self._start_daemon()

    def _start_daemon(self):
        """Start the persistent Windows Media Foundation background daemon."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return

            if not os.path.exists(self._script_path):
                return

            cmd = [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", self._script_path
            ]
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    creationflags=0x08000000
                )
                # Wait for initial READY handshake
                ready = self._proc.stdout.readline()
                if "READY" in ready:
                    # Apply default volume
                    self._send_command_unlocked(f"VOL {self.current_volume:.2f}")
            except Exception:
                self._proc = None

    def _send_command_unlocked(self, cmd: str) -> bool:
        """Send command to daemon without acquiring lock."""
        if not self._proc or self._proc.poll() is not None:
            return False
        try:
            self._proc.stdin.write(f"{cmd}\n")
            self._proc.stdin.flush()
            # Read single response line
            self._proc.stdout.readline()
            return True
        except Exception:
            return False

    def _send_command(self, cmd: str) -> bool:
        """Thread-safe command dispatcher to Media Foundation daemon."""
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                self._start_daemon()
            return self._send_command_unlocked(cmd)

    def load(self, video_filepath: str, has_audio: bool = True):
        """Prepare audio player for video file."""
        self.stop()
        self.current_video = video_filepath
        self.has_audio = has_audio
        if has_audio and os.path.exists(video_filepath):
            uri = Path(video_filepath).resolve().as_uri()
            self._send_command(f"OPEN {uri}")
            self.set_volume(self.current_volume)

    def play(self, start_seconds: float = 0.0):
        """Start synchronized audio playback from timestamp."""
        if not self.has_audio or not self.current_video or not os.path.exists(self.current_video):
            return

        self.current_start_seconds = max(0.0, float(start_seconds))
        self.is_playing = True
        self._send_command(f"PLAY {self.current_start_seconds:.3f}")

    def stop(self):
        """Pause / stop audio playback."""
        self.is_playing = False
        self._send_command("PAUSE")

    def seek(self, seconds: float):
        """Instant audio seek."""
        self.current_start_seconds = max(0.0, float(seconds))
        self._send_command(f"SEEK {self.current_start_seconds:.3f}")

    def set_volume(self, volume_0_to_1: float):
        """Set playback volume (0.0 to 1.0)."""
        self.current_volume = max(0.0, min(1.0, float(volume_0_to_1)))
        self._send_command(f"VOL {self.current_volume:.2f}")

    def get_current_device_name(self) -> str:
        """Returns auto-switch indicator for UI."""
        return "Auto Audio"

    def toggle_device(self) -> str:
        """Auto audio mode indicator."""
        return "Auto Audio"

    def close(self):
        """Terminate background audio daemon on app shutdown."""
        self.stop()
        with self._lock:
            if self._proc:
                try:
                    self._proc.stdin.write("QUIT\n")
                    self._proc.stdin.flush()
                    self._proc.wait(timeout=1)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None
