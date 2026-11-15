"""
Windows Native Audio Player using WinMM MCI API.
Enables instant seeking, playback, volume control, and zero external dependencies.
"""

import ctypes
import os


class WindowsAudioPlayer:
    """Controls audio playback natively on Windows using mciSendString."""

    def __init__(self):
        self.winmm = getattr(ctypes.windll, "winmm", None)
        self.alias = "dubber_audio_player"
        self.is_opened = False
        self.current_file = None

    def load(self, wav_path):
        """Open a WAV file for playback."""
        self.close()
        if not self.winmm or not wav_path or not os.path.exists(wav_path):
            return False

        # Use short path or 8.3 filename if possible to avoid quote parsing issues in MCI
        normalized_path = os.path.abspath(wav_path).replace("/", "\\")
        cmd = f'open "{normalized_path}" type waveaudio alias {self.alias}'
        res = self.winmm.mciSendStringW(cmd, None, 0, 0)
        self.is_opened = (res == 0)
        if self.is_opened:
            self.current_file = normalized_path
        return self.is_opened

    def play(self, start_ms=0):
        """Play from specific millisecond position."""
        if not self.is_opened or not self.winmm:
            return
        cmd = f"play {self.alias} from {int(start_ms)}"
        self.winmm.mciSendStringW(cmd, None, 0, 0)

    def pause(self):
        """Pause playback."""
        if self.is_opened and self.winmm:
            self.winmm.mciSendStringW(f"pause {self.alias}", None, 0, 0)

    def stop(self):
        """Stop playback and rewind."""
        if self.is_opened and self.winmm:
            self.winmm.mciSendStringW(f"stop {self.alias}", None, 0, 0)

    def set_volume(self, volume_0_to_1):
        """Set volume (0.0 to 1.0). MCI volume range is 0 to 1000."""
        if self.is_opened and self.winmm:
            val = max(0, min(1000, int(volume_0_to_1 * 1000)))
            self.winmm.mciSendStringW(f"setaudio {self.alias} volume to {val}", None, 0, 0)

    def close(self):
        """Release MCI device."""
        if self.is_opened and self.winmm:
            self.winmm.mciSendStringW(f"close {self.alias}", None, 0, 0)
            self.is_opened = False
            self.current_file = None
