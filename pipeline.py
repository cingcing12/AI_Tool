from __future__ import annotations

import importlib.util
import asyncio
import json
import os
import shutil
import subprocess
import time
from collections import Counter
from difflib import SequenceMatcher
from glob import escape as glob_escape
import math
import re
import uuid
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import speech_recognition as sr
from deep_translator import GoogleTranslator
from gtts import gTTS
from PIL import Image, ImageOps

try:
    from moviepy.editor import (
        AudioClip,
        AudioFileClip,
        CompositeAudioClip,
        ImageClip,
        VideoFileClip,
        concatenate_audioclips,
        concatenate_videoclips,
    )
except ImportError:
    from moviepy import (
        AudioClip,
        AudioFileClip,
        CompositeAudioClip,
        ImageClip,
        VideoFileClip,
        concatenate_audioclips,
        concatenate_videoclips,
    )

from moviepy.video.fx.MultiplySpeed import MultiplySpeed


GENERATED_FINAL_OUTPUT_SUFFIX = "_final_output"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".webm")
TIMED_NARRATION_GAP_SECONDS = 0.05
MAX_TIMED_NARRATION_SPEEDUP = 1.35
DEFAULT_BACKGROUND_VOLUME = 0.35
DEFAULT_VOICE_GENDER = "female"

EDGE_TTS_LANGUAGE_KEYS = {
    "km": "km-KH",
    "km-kh": "km-KH",
    "en": "en-US",
    "en-us": "en-US",
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "ja": "ja-JP",
    "ja-jp": "ja-JP",
    "ko": "ko-KR",
    "ko-kr": "ko-KR",
}

EDGE_TTS_VOICE_NAMES = {
    "km-KH": {
        "female": "km-KH-SreymomNeural",
        "male": "km-KH-PisethNeural",
    },
    "en-US": {
        "female": "en-US-JennyNeural",
        "male": "en-US-GuyNeural",
    },
    "zh-CN": {
        "female": "zh-CN-XiaoxiaoNeural",
        "male": "zh-CN-YunxiNeural",
    },
    "zh-TW": {
        "female": "zh-TW-HsiaoChenNeural",
        "male": "zh-TW-YunJheNeural",
    },
    "ja-JP": {
        "female": "ja-JP-NanamiNeural",
        "male": "ja-JP-KeitaNeural",
    },
    "ko-KR": {
        "female": "ko-KR-SunHiNeural",
        "male": "ko-KR-InJoonNeural",
    },
}

VOICE_GENDER_ALIASES = {
    "auto": "auto",
    "default": "auto",
    "automatic": "auto",
    "female": "female",
    "woman": "female",
    "girl": "female",
    "ស្រី": "female",
    "male": "male",
    "man": "male",
    "boy": "male",
    "ប្រុស": "male",
}


@dataclass
class SubtitleSegment:
    start: float
    end: float
    text: str


@dataclass
class WorkflowConfig:
    video: str
    text: str | None = None
    text_file: str | None = None
    speech_lang: str = "auto"
    source_lang: str = "auto"
    target_lang: str = "km"
    voice_lang: str = "km"
    voice_gender: str = DEFAULT_VOICE_GENDER
    skip_translation: bool = False
    skip_voice: bool = False
    transcript_out: str = "transcript_original.txt"
    subtitle_out: str = "subtitles_original.srt"
    translated_subtitle_out: str = "subtitles_khmer.srt"
    translated_text_out: str = "translated_khmer.txt"
    audio_out: str = "narration.mp3"
    output: str = "final_output.mp4"
    keep_original_audio: bool = False
    preserve_background_audio: bool = True
    original_volume: float = DEFAULT_BACKGROUND_VOLUME
    slow_voice: bool = False
    chunk_seconds: int = 5
    overlap_seconds: float = 1.2
    transcription_engine: str = "auto"
    whisper_model: str = "medium"
    hf_token: str = ""
    repair_transcript_with_ollama: bool = False
    ollama_model: str = "llava:latest"


@dataclass
class AnalysisResult:
    transcript_path: str | None
    subtitle_path: str | None
    translated_subtitle_path: str | None
    translated_text_path: str
    source_text: str
    translated_text: str
    source_segments: list[SubtitleSegment]
    translated_segments: list[SubtitleSegment]


@dataclass
class WorkflowResult:
    analysis: AnalysisResult
    audio_path: str | None
    output_video_path: str | None
    video_extended: bool


@dataclass
class VoiceGenerationResult:
    audio_path: str
    timed_segments: list[SubtitleSegment]


LANGUAGE_ALIASES = {
    "auto detect": "auto",
    "automatic": "auto",
    "detect": "auto",
    "china": "zh-CN",
    "chinese": "zh-CN",
    "chinese china": "zh-CN",
    "chinese simplified": "zh-CN",
    "simplified chinese": "zh-CN",
    "mandarin": "zh-CN",
    "mandarin chinese": "zh-CN",
    "zh": "zh-CN",
    "zh cn": "zh-CN",
    "zhongwen": "zh-CN",
    "traditional chinese": "zh-TW",
    "chinese traditional": "zh-TW",
    "taiwan": "zh-TW",
    "taiwan chinese": "zh-TW",
    "zh tw": "zh-TW",
    "khmer": "km",
    "cambodian": "km",
    "cambodia": "km",
}


def normalize_language_code(language: str | None, default: str = "") -> str:
    value = (language or "").strip()
    if not value:
        return default

    if " - " in value:
        value = value.rsplit(" - ", 1)[1].strip()

    if value.lower() == "auto":
        return "auto"

    key = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return LANGUAGE_ALIASES.get(key, value)


def normalize_voice_gender(voice_gender: str | None, default: str = DEFAULT_VOICE_GENDER) -> str:
    value = (voice_gender or "").strip()
    if not value:
        return default

    if " - " in value:
        value = value.rsplit(" - ", 1)[1].strip()

    key = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    normalized = VOICE_GENDER_ALIASES.get(key)
    if normalized is None:
        raise ValueError("Voice gender must be auto, female, or male.")
    return normalized if normalized != "auto" else default if default != "auto" else "auto"


def edge_tts_language_key(language: str | None) -> str | None:
    normalized = normalize_language_code(language, default="km")
    return EDGE_TTS_LANGUAGE_KEYS.get(normalized.lower())


def edge_tts_voice_name(language: str | None, voice_gender: str | None = DEFAULT_VOICE_GENDER) -> str | None:
    gender = normalize_voice_gender(voice_gender, default=DEFAULT_VOICE_GENDER)
    if gender == "auto":
        gender = DEFAULT_VOICE_GENDER

    language_key = edge_tts_language_key(language)
    if language_key is None:
        return None

    return EDGE_TTS_VOICE_NAMES.get(language_key, {}).get(gender)


def edge_tts_rate(slow: bool) -> str:
    return "-18%" if slow else "+0%"


async def save_edge_tts_audio_async(
    text: str,
    output_file: str,
    voice_name: str,
    slow: bool = False,
) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice_name, rate=edge_tts_rate(slow))
    await communicate.save(output_file)


def save_edge_tts_audio(
    text: str,
    output_file: str,
    voice_name: str,
    slow: bool = False,
) -> str:
    asyncio.run(save_edge_tts_audio_async(text, output_file, voice_name, slow=slow))
    return output_file


def save_tts_audio(
    text: str,
    output_file: str,
    lang: str = "km",
    slow: bool = False,
    voice_gender: str | None = DEFAULT_VOICE_GENDER,
) -> str:
    gender = normalize_voice_gender(voice_gender, default=DEFAULT_VOICE_GENDER)
    voice_name = edge_tts_voice_name(lang, gender)

    if voice_name and importlib.util.find_spec("edge_tts") is not None:
        return save_edge_tts_audio(text, output_file, voice_name, slow=slow)

    if gender == "male":
        raise RuntimeError(
            "Male voice generation requires edge-tts. Install dependencies with: pip install -r requirements.txt"
        )

    gTTS(text=text, lang=lang, slow=slow).save(output_file)
    return output_file


def ensure_parent_dir(path: str) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def create_workspace_temp_dir(base_dir: Path, prefix: str) -> Path:
    root = base_dir.expanduser().resolve()
    for _attempt in range(12):
        candidate = root / f"{prefix}_{uuid.uuid4().hex[:8]}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"Could not create a temporary directory under: {root}")


def build_default_output_paths(video_file: str, output_dir: str | None = None) -> dict[str, str]:
    video_path = Path(video_file).expanduser()
    base_dir = Path(output_dir).expanduser() if output_dir else video_path.parent
    stem = video_path.stem or "output"

    return {
        "transcript_out": str(base_dir / f"{stem}_transcript_original.txt"),
        "subtitle_out": str(base_dir / f"{stem}_subtitles_original.srt"),
        "translated_subtitle_out": str(base_dir / f"{stem}_subtitles_khmer.srt"),
        "translated_text_out": str(base_dir / f"{stem}_translated_khmer.txt"),
        "audio_out": str(base_dir / f"{stem}_narration.mp3"),
        "output": str(base_dir / f"{stem}_final_output.mp4"),
    }


def find_original_video_for_generated_output(video_file: str | Path) -> Path | None:
    video_path = Path(video_file).expanduser()
    stem = video_path.stem
    if not stem.lower().endswith(GENERATED_FINAL_OUTPUT_SUFFIX):
        return None

    source_stem = stem[: -len(GENERATED_FINAL_OUTPUT_SUFFIX)]
    if not source_stem:
        return None

    candidate_suffixes = [video_path.suffix] if video_path.suffix else []
    candidate_suffixes.extend(suffix for suffix in VIDEO_EXTENSIONS if suffix.lower() != video_path.suffix.lower())
    for suffix in candidate_suffixes:
        candidate = video_path.with_name(f"{source_stem}{suffix}")
        if not candidate.is_file():
            continue
        try:
            if candidate.resolve() == video_path.resolve():
                continue
        except OSError:
            pass
        return candidate

    return None


def resolve_generated_output_config(
    config: WorkflowConfig,
    logger: Callable[[str], None] | None = None,
) -> WorkflowConfig:
    source_video = find_original_video_for_generated_output(config.video)
    if source_video is None:
        return config

    log = logger or (lambda _message: None)
    log(f"Selected video is an app-generated final output; using original source video instead: {source_video}")
    return replace(config, video=str(source_video))


def extract_video_url(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""

    match = re.search(r"https?://[^\s\"'<>]+", cleaned, flags=re.IGNORECASE)
    if not match:
        return ""

    return match.group(0).rstrip(".,;:!?)]}，。；：！？）】》")


def normalize_video_url(value: str) -> str:
    url = extract_video_url(value)
    if not url:
        return ""

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    query = parse_qs(parsed.query)
    modal_id = next((item for item in query.get("modal_id", []) if item.strip()), "")
    if modal_id and "douyin.com" in host:
        return f"https://www.douyin.com/video/{modal_id.strip()}"

    return url


def is_video_url(value: str) -> bool:
    return bool(normalize_video_url(value))


def parse_browser_cookie_source(value: str | None) -> tuple[str, str | None, str | None, str | None] | None:
    raw_value = (value or "").strip()
    if not raw_value:
        return None

    if " - " in raw_value:
        raw_value = raw_value.rsplit(" - ", 1)[1].strip()

    if raw_value.lower() in {"none", "no", "off", "false"}:
        return None

    match = re.fullmatch(
        r"(?P<name>[^+:]+)(?:\s*\+\s*(?P<keyring>[^:]+))?(?:\s*:\s*(?!:)(?P<profile>.+?))?(?:\s*::\s*(?P<container>.+))?",
        raw_value,
    )
    if not match:
        raise ValueError(f"Invalid cookie browser value: {value}")

    browser_name, keyring, profile, container = match.group("name", "keyring", "profile", "container")
    return (
        browser_name.strip().lower(),
        profile.strip() if profile else None,
        keyring.strip().upper() if keyring else None,
        container.strip() if container else None,
    )


def downloaded_video_candidates(info: dict[str, Any], download_dir: Path, started_at: float) -> list[Path]:
    candidates: list[Path] = []
    for key in ("filepath", "_filename", "filename"):
        value = info.get(key)
        if value:
            candidates.append(Path(str(value)).expanduser())

    for download in info.get("requested_downloads") or []:
        if not isinstance(download, dict):
            continue
        for key in ("filepath", "_filename", "filename"):
            value = download.get(key)
            if value:
                candidates.append(Path(str(value)).expanduser())

    video_suffixes = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
    for path in download_dir.glob("*"):
        if path.is_file() and path.suffix.lower() in video_suffixes and path.stat().st_mtime >= started_at - 2:
            candidates.append(path)

    existing = [path.resolve() for path in candidates if path.is_file()]
    return sorted(set(existing), key=lambda path: path.stat().st_mtime, reverse=True)


def download_video_from_url(
    video_url: str,
    output_dir: str | None = None,
    logger: Callable[[str], None] | None = None,
    ydl_class: Any | None = None,
    cookies_browser: str | None = None,
    cookies_file: str | None = None,
) -> str:
    log = logger or (lambda _message: None)
    url = normalize_video_url(video_url)
    if not url:
        raise ValueError("Paste a valid video link or copied share text containing http:// or https://.")

    base_dir = Path(output_dir).expanduser() if output_dir else Path.cwd() / "downloaded_videos"
    base_dir.mkdir(parents=True, exist_ok=True)

    if ydl_class is None:
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise RuntimeError("Install yt-dlp first: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt") from exc
        ydl_class = YoutubeDL

    progress_state = {"last_percent": -1}

    def progress_hook(status: dict[str, Any]) -> None:
        download_status = status.get("status")
        if download_status == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            downloaded = status.get("downloaded_bytes")
            if total and downloaded:
                percent = int((float(downloaded) / float(total)) * 100)
                if percent >= progress_state["last_percent"] + 20:
                    progress_state["last_percent"] = percent
                    log(f"Downloading linked video... {percent}%")
        elif download_status == "finished":
            log("Download finished. Preparing the video file...")

    options = {
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "outtmpl": str(base_dir / "%(extractor)s_%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "progress_hooks": [progress_hook],
    }
    browser_cookie_source = parse_browser_cookie_source(cookies_browser)
    if browser_cookie_source is not None:
        options["cookiesfrombrowser"] = browser_cookie_source
        log(f"Using cookies from browser: {browser_cookie_source[0]}")

    cookiefile = (cookies_file or "").strip()
    if cookiefile:
        options["cookiefile"] = str(Path(cookiefile).expanduser())
        log(f"Using cookies file: {options['cookiefile']}")

    started_at = time.time()
    log("Fetching video from link...")
    try:
        with ydl_class(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        message = str(exc)
        if "Fresh cookies" in message and browser_cookie_source is None and not cookiefile:
            raise RuntimeError(
                "Douyin needs fresh cookies. Open the video in Edge or Chrome once, "
                "then choose that browser in Cookie browser and click Fetch again. "
                f"Original error: {message}"
            ) from exc
        raise

    if not isinstance(info, dict):
        raise RuntimeError("The downloader did not return video information.")

    candidates = downloaded_video_candidates(info, base_dir, started_at)
    if not candidates:
        raise RuntimeError(f"Download finished, but no video file was found in: {base_dir}")

    video_path = str(candidates[0])
    log(f"Downloaded video to: {video_path}")
    return video_path


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def configure_hf_environment(hf_token: str | None = None) -> None:
    token = (hf_token or "").strip()
    if token:
        os.environ["HF_TOKEN"] = token
        os.environ["HUGGING_FACE_HUB_TOKEN"] = token


def subtitle_timestamp_to_seconds(value: str) -> float:
    cleaned = value.strip().replace(".", ",")
    hours, minutes, seconds_millis = cleaned.split(":")
    seconds, millis = seconds_millis.split(",", 1)
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + (int(millis.ljust(3, "0")[:3]) / 1000.0)
    )


def strip_subtitle_markup(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_subtitle_text(contents: str) -> list[SubtitleSegment]:
    segments: list[SubtitleSegment] = []
    lines = contents.replace("\r\n", "\n").split("\n")
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not line or line.upper() == "WEBVTT":
            index += 1
            continue
        if line.isdigit():
            index += 1
            continue

        if "-->" not in line:
            index += 1
            continue

        start_raw, end_raw = [part.strip() for part in line.split("-->", 1)]
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].strip())
            index += 1

        text = strip_subtitle_markup(" ".join(text_lines))
        if text:
            segments.append(
                SubtitleSegment(
                    start=subtitle_timestamp_to_seconds(start_raw.split(" ", 1)[0]),
                    end=subtitle_timestamp_to_seconds(end_raw.split(" ", 1)[0]),
                    text=text,
                )
            )

    return segments


def find_sidecar_subtitle_file(video_file: str) -> Path | None:
    video_path = Path(video_file).expanduser().resolve()
    stem = glob_escape(video_path.stem)
    patterns = [
        f"{stem}.srt",
        f"{stem}.vtt",
        f"{stem}.*.srt",
        f"{stem}.*.vtt",
    ]

    for pattern in patterns:
        matches = sorted(video_path.parent.glob(pattern))
        for path in matches:
            if path.is_file() and path.suffix.lower() in {".srt", ".vtt"}:
                return path

    return None


def load_sidecar_transcript(video_file: str) -> tuple[str, list[SubtitleSegment], Path] | None:
    subtitle_file = find_sidecar_subtitle_file(video_file)
    if subtitle_file is None:
        return None

    contents = subtitle_file.read_text(encoding="utf-8-sig", errors="ignore")
    segments = parse_subtitle_text(contents)
    if not segments:
        return None

    return join_segments_text(segments), segments, subtitle_file


def extract_embedded_subtitle_transcript(video_file: str) -> tuple[str, list[SubtitleSegment]] | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    video_path = Path(video_file).expanduser().resolve()

    temp_dir_path = create_workspace_temp_dir(video_path.parent, "embedded_subtitles")
    try:
        temp_path = temp_dir_path
        attempts = [
            (temp_path / "embedded_subtitles.srt", "srt"),
            (temp_path / "embedded_subtitles.vtt", "webvtt"),
        ]

        for output_path, subtitle_format in attempts:
            command = [
                ffmpeg_exe,
                "-y",
                "-i",
                str(video_path),
                "-map",
                "0:s:0",
                "-f",
                subtitle_format,
                str(output_path),
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size <= 0:
                continue

            contents = output_path.read_text(encoding="utf-8-sig", errors="ignore")
            segments = parse_subtitle_text(contents)
            if segments:
                return join_segments_text(segments), segments
    finally:
        shutil.rmtree(temp_dir_path, ignore_errors=True)

    return None


WINDOWS_OCR_SCRIPT = r"""
param([string]$JsonPath)
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$storageFileType = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$bitmapDecoderType = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$ocrEngineType = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$fileAccessType = [Windows.Storage.FileAccessMode,Windows.Storage,ContentType=WindowsRuntime]
$randomStreamType = [Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$softwareBitmapType = [Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$ocrResultType = [Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
$asTaskMethod = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1
})[0]

function Await-Op($Operation, $Type) {
    $task = $asTaskMethod.MakeGenericMethod($Type).Invoke($null, @($Operation))
    return $task.GetAwaiter().GetResult()
}

$paths = Get-Content -Raw -Path $JsonPath | ConvertFrom-Json
$ocr = $ocrEngineType::TryCreateFromUserProfileLanguages()
$results = New-Object System.Collections.Generic.List[string]

foreach ($path in $paths) {
    if (-not $path -or -not (Test-Path -LiteralPath $path)) {
        $results.Add("")
        continue
    }

    try {
        $resolvedPath = (Resolve-Path -LiteralPath $path).Path
        $file = Await-Op ($storageFileType::GetFileFromPathAsync($resolvedPath)) $storageFileType
        $stream = Await-Op ($file.OpenAsync($fileAccessType::Read)) $randomStreamType
        $decoder = Await-Op ($bitmapDecoderType::CreateAsync($stream)) $bitmapDecoderType
        $bitmap = Await-Op ($decoder.GetSoftwareBitmapAsync()) $softwareBitmapType
        $result = Await-Op ($ocr.RecognizeAsync($bitmap)) $ocrResultType
        $results.Add([string]$result.Text)
    } catch {
        $results.Add("")
    }
}

$results | ConvertTo-Json -Compress
"""


def windows_ocr_available() -> bool:
    return os.name == "nt" and shutil.which("powershell.exe") is not None


def run_windows_ocr(image_paths: list[Path], timeout: int = 180) -> list[str]:
    if not image_paths:
        return []
    if not windows_ocr_available():
        raise RuntimeError("Windows OCR is not available on this system.")

    temp_dir_path = create_workspace_temp_dir(image_paths[0].parent, "windows_ocr")
    try:
        json_path = temp_dir_path / "ocr_paths.json"
        script_path = temp_dir_path / "windows_ocr.ps1"
        json_path.write_text(
            json.dumps([str(path.expanduser().resolve()) for path in image_paths]),
            encoding="utf-8",
        )
        script_path.write_text(WINDOWS_OCR_SCRIPT, encoding="utf-8")

        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                str(json_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Windows OCR failed.")

        output = result.stdout.strip()
        if not output:
            return ["" for _path in image_paths]

        parsed = json.loads(output)
        if isinstance(parsed, list):
            return [str(item or "") for item in parsed]
        if isinstance(parsed, str):
            return [parsed]
        return ["" for _path in image_paths]
    finally:
        shutil.rmtree(temp_dir_path, ignore_errors=True)


def clean_subtitle_ocr_text(text: str) -> str:
    cleaned = strip_subtitle_markup(text.replace("\r", "\n"))
    cleaned = cleaned.replace("’", "'").replace("`", "'").replace("|", "I")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    if not re.search(r"[A-Za-z0-9\u1780-\u17FF]", cleaned):
        return ""
    return cleaned


def build_subtitle_ocr_image(frame: Any) -> Image.Image | None:
    image = Image.fromarray(frame)
    width, height = image.size
    left = int(width * 0.05)
    top = int(height * 0.60)
    right = int(width * 0.95)
    bottom = height
    crop = image.crop((left, top, right, bottom))

    grayscale = ImageOps.autocontrast(crop.convert("L"))
    threshold = grayscale.point(lambda pixel: 255 if pixel > 180 else 0)
    white_pixels = sum(1 for pixel in threshold.getdata() if pixel > 0)
    total_pixels = max(1, threshold.width * threshold.height)
    white_ratio = white_pixels / total_pixels
    if white_ratio < 0.001 or white_ratio > 0.35:
        return None

    return threshold.resize((threshold.width * 2, threshold.height * 2))


def sample_subtitle_ocr_timestamps(duration: float) -> tuple[float, list[float]]:
    if duration <= 0:
        return 1.0, []

    if duration <= 15:
        interval = 0.8
    elif duration <= 45:
        interval = 1.0
    elif duration <= 120:
        interval = 1.5
    else:
        interval = 2.0

    timestamps: list[float] = []
    timestamp = interval / 2.0
    max_time = max(0.0, duration - 0.05)
    while timestamp <= max_time:
        timestamps.append(timestamp)
        timestamp += interval

    if not timestamps:
        timestamps = [max(0.0, duration / 2.0)]

    max_samples = 90
    if len(timestamps) > max_samples:
        step = math.ceil(len(timestamps) / max_samples)
        timestamps = timestamps[::step]
        interval *= step

    return interval, timestamps


def subtitle_coverage_ratio(segments: list[SubtitleSegment], total_duration: float) -> float:
    if total_duration <= 0:
        return 0.0
    covered_duration = sum(max(0.0, segment.end - segment.start) for segment in segments)
    return min(1.0, covered_duration / total_duration)


def ocr_samples_to_segments(
    samples: list[tuple[float, str]],
    interval: float,
    total_duration: float,
) -> list[SubtitleSegment]:
    segments: list[SubtitleSegment] = []
    current_text = ""
    current_start = 0.0
    current_end = 0.0

    for timestamp, raw_text in samples:
        text = clean_subtitle_ocr_text(raw_text)
        sample_start = max(0.0, timestamp - (interval / 2.0))
        sample_end = min(total_duration, timestamp + (interval / 2.0))

        if not text:
            if current_text:
                segments.append(SubtitleSegment(start=current_start, end=current_end, text=current_text))
                current_text = ""
            continue

        if current_text and transcript_text_similarity(current_text, text) >= 0.9:
            current_end = max(current_end, sample_end)
            if len(text) > len(current_text):
                current_text = text
            continue

        if current_text:
            segments.append(SubtitleSegment(start=current_start, end=current_end, text=current_text))

        current_text = text
        current_start = sample_start
        current_end = sample_end

    if current_text:
        segments.append(SubtitleSegment(start=current_start, end=current_end, text=current_text))

    return cleanup_transcript_segments(segments)


def extract_burned_in_subtitle_transcript(
    video_file: str,
    logger: Callable[[str], None] | None = None,
) -> tuple[str, list[SubtitleSegment], float] | None:
    log = logger or (lambda _message: None)
    if not windows_ocr_available():
        return None

    video_path = Path(video_file).expanduser().resolve()
    clip = VideoFileClip(str(video_path))
    temp_dir_path = create_workspace_temp_dir(video_path.parent, "burned_in_ocr")

    try:
        total_duration = float(clip.duration or 0.0)
        if total_duration <= 0:
            return None

        interval, timestamps = sample_subtitle_ocr_timestamps(total_duration)
        image_paths: list[Path] = []
        sampled_timestamps: list[float] = []

        for index, timestamp in enumerate(timestamps):
            frame = clip.get_frame(min(max(0.0, timestamp), max(0.0, total_duration - 0.05)))
            processed_image = build_subtitle_ocr_image(frame)
            if processed_image is None:
                continue

            image_path = temp_dir_path / f"subtitle_ocr_{index:04}.png"
            processed_image.save(image_path)
            image_paths.append(image_path)
            sampled_timestamps.append(timestamp)

        if not image_paths:
            return None

        log(f"Transcript looked weak, trying burned-in subtitle OCR on {len(image_paths)} frames...")
        ocr_results = run_windows_ocr(image_paths, timeout=max(180, len(image_paths) * 5))
        samples = list(zip(sampled_timestamps, ocr_results))
        ocr_segments = ocr_samples_to_segments(samples, interval=interval, total_duration=total_duration)
        ocr_text = join_segments_text(ocr_segments)
        coverage = subtitle_coverage_ratio(ocr_segments, total_duration)

        if not ocr_segments or not ocr_text.strip():
            return None
        return ocr_text, ocr_segments, coverage
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        log(f"Burned-in subtitle OCR skipped: {exc}")
        return None
    finally:
        clip.close()
        shutil.rmtree(temp_dir_path, ignore_errors=True)


def build_transcript_repair_prompt(text: str, source_lang: str) -> str:
    language_note = source_lang if source_lang and source_lang != "auto" else "the original language"
    return (
        "You are repairing a rough speech-to-text transcript.\n"
        f"Language: {language_note}.\n"
        "Rules:\n"
        "- Keep the same language.\n"
        "- Do not translate.\n"
        "- Do not add new facts.\n"
        "- Restore missing words only when they are strongly implied by context.\n"
        "- Fix punctuation, casing, spacing, and line breaks.\n"
        "- Return only the corrected transcript.\n\n"
        "Transcript:\n"
        "<<<\n"
        f"{text.strip()}\n"
        ">>>"
    )


def clean_ollama_response(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:text)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def ollama_generate_text(model: str, prompt: str, system: str | None = None, timeout: int = 180) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    request = Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))

    if isinstance(data, dict):
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        result = str(data.get("response", "")).strip()
        if result:
            return result

    raise RuntimeError("Ollama returned no text.")


def repair_transcript_with_ollama(
    text: str,
    model: str,
    source_lang: str = "auto",
    logger: Callable[[str], None] | None = None,
) -> str:
    log = logger or (lambda _message: None)
    cleaned_text = text.strip()
    if not cleaned_text or not model.strip():
        return cleaned_text

    chunks = split_text_chunks(cleaned_text, max_chars=2800)
    if not chunks:
        return cleaned_text

    repaired_chunks: list[str] = []
    for chunk in chunks:
        prompt = build_transcript_repair_prompt(chunk, source_lang)
        try:
            response = ollama_generate_text(
                model=model,
                prompt=prompt,
                system="You repair speech transcripts and return plain text only.",
            )
        except (URLError, OSError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            log(f"Ollama transcript repair skipped: {exc}")
            return cleaned_text

        repaired_chunks.append(clean_ollama_response(response) or chunk.strip())

    repaired_text = "\n".join(part for part in repaired_chunks if part.strip()).strip()
    return repaired_text or cleaned_text


def read_source_text(inline_text: str | None, text_file: str | None) -> str:
    if inline_text and text_file:
        raise ValueError("Use either inline text or --text-file, not both.")

    if text_file:
        content = Path(text_file).expanduser().read_text(encoding="utf-8").strip()
    elif inline_text:
        content = inline_text.strip()
    else:
        raise ValueError("Provide text as the first argument or use --text-file.")

    if not content:
        raise ValueError("Source text is empty.")

    return content


def split_text_chunks(text: str, max_chars: int) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    chunks: list[str] = []
    current = ""

    for line in lines:
        sentences = re.split(r"(?<=[.!?\u17d4])\s+", line)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(sentence) > max_chars:
                words = sentence.split()
                partial = ""
                for word in words:
                    candidate = f"{partial} {word}".strip()
                    if partial and len(candidate) > max_chars:
                        chunks.append(partial)
                        partial = word
                    else:
                        partial = candidate
                if partial:
                    if current:
                        chunks.append(current)
                        current = ""
                    chunks.append(partial)
                continue

            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = sentence
            else:
                current = candidate

        if current and len(current) > max_chars:
            chunks.append(current)
            current = ""

    if current:
        chunks.append(current)

    return chunks


def translate_text(text: str, target_lang: str = "km", source_lang: str = "auto") -> str:
    cleaned_text = text.strip()
    if not cleaned_text:
        return ""

    source_lang = normalize_language_code(source_lang, default="auto")
    target_lang = normalize_language_code(target_lang, default="km")
    translator = GoogleTranslator(source=source_lang, target=target_lang)

    translated_chunks: list[str] = []

    for chunk in split_text_chunks(cleaned_text, max_chars=3000):
        translated = str(translator.translate(chunk) or "").strip()
        if translated:
            translated_chunks.append(translated)

    return "\n".join(part for part in translated_chunks if part.strip())


def translate_segments(
    segments: list[SubtitleSegment],
    target_lang: str = "km",
    source_lang: str = "auto",
) -> list[SubtitleSegment]:
    source_lang = normalize_language_code(source_lang, default="auto")
    target_lang = normalize_language_code(target_lang, default="km")
    translator = GoogleTranslator(source=source_lang, target=target_lang)
    translated_segments: list[SubtitleSegment] = []

    for segment in segments:
        cleaned_text = segment.text.strip()
        translated_text = str(translator.translate(cleaned_text) or "").strip() if cleaned_text else ""
        translated_segments.append(
            SubtitleSegment(start=segment.start, end=segment.end, text=translated_text)
        )

    return translated_segments


def join_segments_text(segments: list[SubtitleSegment]) -> str:
    return "\n".join(segment.text for segment in segments if segment.text.strip())


def normalize_transcript_match_text(text: str) -> str:
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def transcript_text_similarity(left: str, right: str) -> float:
    normalized_left = normalize_transcript_match_text(left)
    normalized_right = normalize_transcript_match_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def cleanup_transcript_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    cleaned_segments: list[SubtitleSegment] = []
    recent_normalized_texts: list[str] = []

    for segment in segments:
        text = re.sub(r"\s+", " ", segment.text).strip()
        if not text:
            continue

        if cleaned_segments:
            text = remove_duplicate_prefix(cleaned_segments[-1].text, text).strip()
            if not text:
                continue

        normalized_text = normalize_transcript_match_text(text)
        if not normalized_text:
            continue

        word_count = count_words(text)
        recent_window = recent_normalized_texts[-5:]
        if word_count >= 5:
            if normalized_text in recent_window:
                continue
            if any(
                len(previous.split()) >= 5 and transcript_text_similarity(normalized_text, previous) >= 0.96
                for previous in recent_window
            ):
                continue
            combined_recent = " ".join(recent_window)
            if len(normalized_text.split()) >= 6 and normalized_text in combined_recent:
                continue

        cleaned_segments.append(
            SubtitleSegment(
                start=segment.start,
                end=max(segment.end, segment.start),
                text=text,
            )
        )
        recent_normalized_texts.append(normalized_text)

    return cleaned_segments or segments


def build_translated_outputs(
    source_text: str,
    source_segments: list[SubtitleSegment],
    target_lang: str = "km",
    source_lang: str = "auto",
) -> tuple[str, list[SubtitleSegment]]:
    translated_text = translate_text(
        source_text,
        target_lang=target_lang,
        source_lang=source_lang,
    )
    translated_segments = translate_segments(
        source_segments,
        target_lang=target_lang,
        source_lang=source_lang,
    ) if source_segments else []
    return translated_text, translated_segments


def split_script_for_timed_segments(
    text: str,
    reference_segments: list[SubtitleSegment],
) -> list[str] | None:
    cleaned_text = text.strip()
    if not cleaned_text:
        return None

    reference_segments = [segment for segment in reference_segments if segment.end >= segment.start]
    if not reference_segments:
        return None

    lines = [line.strip() for line in cleaned_text.replace("\r\n", "\n").split("\n") if line.strip()]
    if len(lines) == len(reference_segments):
        return lines

    normalized_text = re.sub(r"\s+", " ", cleaned_text).strip()
    if not normalized_text:
        return None

    if len(reference_segments) == 1:
        return [normalized_text]

    durations = [max(segment.end - segment.start, 0.2) for segment in reference_segments]
    words = normalized_text.split()
    if len(words) >= len(reference_segments):
        chunks = split_units_by_segment_durations(words, durations, joiner=" ")
    else:
        units = split_text_into_timing_units(normalized_text)
        chunks = split_units_by_segment_durations(units, durations, joiner="")

    if chunks is None:
        return None

    if len(chunks) != len(reference_segments) or any(not chunk for chunk in chunks):
        return None

    return chunks


def split_text_into_timing_units(text: str) -> list[str]:
    units: list[str] = []
    for match in re.finditer(r"\S[\u0300-\u036f\u17b6-\u17d3\u17dd]*|\s+", text):
        unit = match.group(0)
        if not unit:
            continue
        if unit.isspace():
            if units:
                units[-1] += unit
            continue
        units.append(unit)
    return units


def split_units_by_segment_durations(
    units: list[str],
    durations: list[float],
    joiner: str,
) -> list[str] | None:
    if len(units) < len(durations):
        return None

    total_duration = sum(durations)
    if total_duration <= 0:
        return None

    chunks: list[str] = []
    previous_boundary = 0
    cumulative_duration = 0.0

    for index, duration in enumerate(durations[:-1], start=1):
        cumulative_duration += duration
        target_boundary = round(len(units) * cumulative_duration / total_duration)
        min_boundary = previous_boundary + 1
        max_boundary = len(units) - (len(durations) - index)
        boundary = max(min_boundary, min(target_boundary, max_boundary))
        chunks.append(joiner.join(units[previous_boundary:boundary]).strip())
        previous_boundary = boundary

    chunks.append(joiner.join(units[previous_boundary:]).strip())
    return chunks


def timed_narration_slot_duration(
    segment: SubtitleSegment,
    next_segment: SubtitleSegment | None = None,
) -> float:
    start = max(0.0, float(segment.start))
    segment_duration = max(0.3, float(segment.end) - start)
    if next_segment is None:
        return segment_duration

    next_start = max(start, float(next_segment.start))
    if next_start <= start:
        return segment_duration

    return max(0.3, next_start - start - TIMED_NARRATION_GAP_SECONDS)


def fit_narration_duration_to_timeline(
    natural_duration: float,
    segment: SubtitleSegment,
    next_segment: SubtitleSegment | None = None,
    max_speedup: float = MAX_TIMED_NARRATION_SPEEDUP,
    force_fit_to_slot: bool = False,
) -> float:
    natural_duration = max(0.0, float(natural_duration))
    if natural_duration <= 0:
        return timed_narration_slot_duration(segment, next_segment)

    available_duration = timed_narration_slot_duration(segment, next_segment)
    if natural_duration <= available_duration + 0.05:
        return natural_duration

    if force_fit_to_slot:
        return available_duration

    safe_speedup_duration = natural_duration / max(max_speedup, 1.0)
    return max(available_duration, safe_speedup_duration)


def build_timed_voice_segments(
    chunks: list[str],
    reference_segments: list[SubtitleSegment],
    natural_durations: list[float],
    max_speedup: float = MAX_TIMED_NARRATION_SPEEDUP,
    force_fit_to_timeline: bool = True,
) -> list[SubtitleSegment]:
    timed_segments: list[SubtitleSegment] = []
    previous_end: float | None = None

    for index, (chunk, segment, natural_duration) in enumerate(zip(chunks, reference_segments, natural_durations)):
        start_time = max(0.0, float(segment.start))
        if previous_end is not None:
            start_time = max(start_time, previous_end + TIMED_NARRATION_GAP_SECONDS)

        original_duration = max(0.3, float(segment.end) - max(0.0, float(segment.start)))
        effective_segment = SubtitleSegment(
            start=start_time,
            end=max(float(segment.end), start_time + original_duration),
            text=chunk,
        )
        next_segment = reference_segments[index + 1] if index + 1 < len(reference_segments) else None
        target_duration = fit_narration_duration_to_timeline(
            natural_duration,
            effective_segment,
            next_segment,
            max_speedup=max_speedup,
            force_fit_to_slot=force_fit_to_timeline,
        )
        end_time = start_time + target_duration
        timed_segments.append(
            SubtitleSegment(
                start=start_time,
                end=end_time,
                text=chunk,
            )
        )
        previous_end = end_time

    return timed_segments


def generate_timed_voice_with_timing(
    text: str,
    reference_segments: list[SubtitleSegment],
    lang: str = "km",
    output_file: str = "narration.mp3",
    slow: bool = False,
    voice_gender: str = DEFAULT_VOICE_GENDER,
    force_fit_to_timeline: bool = True,
) -> VoiceGenerationResult | None:
    reference_segments = sorted(
        (segment for segment in reference_segments if segment.end >= segment.start),
        key=lambda segment: segment.start,
    )
    chunks = split_script_for_timed_segments(text, reference_segments)
    if not chunks or len(chunks) != len(reference_segments):
        return None

    lang = normalize_language_code(lang, default="km")
    ensure_parent_dir(output_file)
    total_duration = max((segment.end for segment in reference_segments), default=0.0)
    audio_clips: list[AudioFileClip] = []
    combined_audio = None
    silent_audio = None
    natural_clips: list[AudioFileClip] = []
    temp_dir_path: Path | None = None

    try:
        output_root = Path(output_file).expanduser().resolve().parent
        temp_dir_path = create_workspace_temp_dir(output_root, "timed_tts_parts")
        for index, (chunk, segment) in enumerate(zip(chunks, reference_segments)):
            chunk_text = chunk.strip()
            if not chunk_text:
                continue

            part_path = temp_dir_path / f"timed_part_{index:03}.mp3"
            save_tts_audio(chunk_text, str(part_path), lang=lang, slow=slow, voice_gender=voice_gender)
            clip = AudioFileClip(str(part_path))
            natural_clips.append(clip)

        if not natural_clips:
            return None

        voiced_segments = build_timed_voice_segments(
            chunks,
            reference_segments,
            [float(clip.duration or 0.0) for clip in natural_clips],
            force_fit_to_timeline=force_fit_to_timeline,
        )

        for source_clip, natural_duration, voiced_segment in zip(
            natural_clips,
            [float(clip.duration or 0.0) for clip in natural_clips],
            voiced_segments,
        ):
            target_duration = max(0.0, voiced_segment.end - voiced_segment.start)
            clip = source_clip
            if natural_duration > 0 and abs(natural_duration - target_duration) > 0.05:
                clip = clip.with_effects([MultiplySpeed(final_duration=target_duration)])
            clip = clip.with_start(voiced_segment.start)
            audio_clips.append(clip)

        narration_duration = max(total_duration, max((segment.end for segment in voiced_segments), default=total_duration))
        silent_audio = create_silent_audio(narration_duration)
        combined_audio = CompositeAudioClip([silent_audio, *audio_clips])
        combined_audio = set_clip_duration(combined_audio, narration_duration)
        combined_audio.write_audiofile(
            output_file,
            codec=audio_codec_for_path(output_file),
            logger=None,
        )
    finally:
        if combined_audio is not None:
            combined_audio.close()
        if silent_audio is not None:
            silent_audio.close()
        for clip in audio_clips:
            clip.close()
        for clip in natural_clips:
            if clip not in audio_clips:
                clip.close()
        if temp_dir_path is not None:
            shutil.rmtree(temp_dir_path, ignore_errors=True)

    return VoiceGenerationResult(audio_path=output_file, timed_segments=voiced_segments)


def generate_timed_voice(
    text: str,
    reference_segments: list[SubtitleSegment],
    lang: str = "km",
    output_file: str = "narration.mp3",
    slow: bool = False,
    voice_gender: str = DEFAULT_VOICE_GENDER,
    force_fit_to_timeline: bool = True,
) -> str | None:
    result = generate_timed_voice_with_timing(
        text,
        reference_segments,
        lang=lang,
        output_file=output_file,
        slow=slow,
        voice_gender=voice_gender,
        force_fit_to_timeline=force_fit_to_timeline,
    )
    return result.audio_path if result is not None else None


def save_text(text: str, output_file: str) -> str:
    ensure_parent_dir(output_file)
    Path(output_file).expanduser().write_text(text, encoding="utf-8")
    return output_file


def format_srt_timestamp(seconds: float) -> str:
    total_milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def save_srt(segments: list[SubtitleSegment], output_file: str) -> str:
    ensure_parent_dir(output_file)

    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(
            f"{format_srt_timestamp(segment.start)} --> {format_srt_timestamp(segment.end)}"
        )
        lines.append(segment.text.strip() or "...")
        lines.append("")

    Path(output_file).expanduser().write_text("\n".join(lines), encoding="utf-8")
    return output_file


def audio_codec_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".wav":
        return "pcm_s16le"
    return "libmp3lame"


def generate_voice_with_timing(
    text: str,
    lang: str = "km",
    output_file: str = "narration.mp3",
    slow: bool = False,
    voice_gender: str = DEFAULT_VOICE_GENDER,
    timed_segments: list[SubtitleSegment] | None = None,
    force_fit_to_timeline: bool = True,
) -> VoiceGenerationResult:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("Khmer script is empty. Edit the script first.")

    lang = normalize_language_code(lang, default="km")
    ensure_parent_dir(output_file)
    if timed_segments:
        timed_audio = generate_timed_voice_with_timing(
            cleaned_text,
            timed_segments,
            lang=lang,
            output_file=output_file,
            slow=slow,
            voice_gender=voice_gender,
            force_fit_to_timeline=force_fit_to_timeline,
        )
        if timed_audio:
            return timed_audio

    chunks = split_text_chunks(cleaned_text, max_chars=900)

    if len(chunks) == 1:
        save_tts_audio(chunks[0], output_file, lang=lang, slow=slow, voice_gender=voice_gender)
        return VoiceGenerationResult(audio_path=output_file, timed_segments=[])

    combined_audio = None
    audio_clips: list[AudioFileClip] = []
    temp_dir_path: Path | None = None

    try:
        output_root = Path(output_file).expanduser().resolve().parent
        temp_dir_path = create_workspace_temp_dir(output_root, "tts_parts")
        for index, chunk in enumerate(chunks):
            part_path = temp_dir_path / f"part_{index:03}.mp3"
            save_tts_audio(chunk, str(part_path), lang=lang, slow=slow, voice_gender=voice_gender)
            audio_clips.append(AudioFileClip(str(part_path)))

        combined_audio = concatenate_audioclips(audio_clips)
        combined_audio.write_audiofile(
            output_file,
            codec=audio_codec_for_path(output_file),
            logger=None,
        )
    finally:
        if combined_audio is not None:
            combined_audio.close()
        for clip in audio_clips:
            clip.close()
        if temp_dir_path is not None:
            shutil.rmtree(temp_dir_path, ignore_errors=True)

    return VoiceGenerationResult(audio_path=output_file, timed_segments=[])


def generate_voice(
    text: str,
    lang: str = "km",
    output_file: str = "narration.mp3",
    slow: bool = False,
    voice_gender: str = DEFAULT_VOICE_GENDER,
    timed_segments: list[SubtitleSegment] | None = None,
    force_fit_to_timeline: bool = True,
) -> str:
    return generate_voice_with_timing(
        text,
        lang=lang,
        output_file=output_file,
        slow=slow,
        voice_gender=voice_gender,
        timed_segments=timed_segments,
        force_fit_to_timeline=force_fit_to_timeline,
    ).audio_path


def trim_audio_clip(audio_clip, end_time: float):
    if hasattr(audio_clip, "subclip"):
        return audio_clip.subclip(0, end_time)
    return audio_clip.subclipped(0, end_time)


def scale_audio_clip(audio_clip, volume_factor: float):
    if hasattr(audio_clip, "volumex"):
        return audio_clip.volumex(volume_factor)
    return audio_clip.with_volume_scaled(volume_factor)


def attach_audio_clip(video_clip, audio_clip):
    if hasattr(video_clip, "set_audio"):
        return video_clip.set_audio(audio_clip)
    return video_clip.with_audio(audio_clip)


def set_clip_duration(clip, duration: float):
    if hasattr(clip, "set_duration"):
        return clip.set_duration(duration)
    return clip.with_duration(duration)


def set_clip_fps(clip, fps: float | None):
    if fps is None:
        return clip
    if hasattr(clip, "set_fps"):
        return clip.set_fps(fps)
    if hasattr(clip, "with_fps"):
        return clip.with_fps(fps)
    return clip


def create_silent_audio(duration: float, fps: int = 44100):
    return AudioClip(lambda _t: 0, duration=duration, fps=fps)


def extend_video_clip(video_clip, target_duration: float):
    if target_duration <= video_clip.duration:
        return set_clip_duration(video_clip, target_duration), False

    frame_time = max(0.0, video_clip.duration - 0.05)
    last_frame = video_clip.get_frame(frame_time)
    extra_duration = target_duration - video_clip.duration
    freeze_clip = ImageClip(last_frame)
    freeze_clip = set_clip_duration(freeze_clip, extra_duration)
    freeze_clip = set_clip_fps(freeze_clip, getattr(video_clip, "fps", None))

    extended_video = concatenate_videoclips([video_clip, freeze_clip], method="compose")
    extended_video = set_clip_fps(extended_video, getattr(video_clip, "fps", None))
    return extended_video, True


def extract_audio_from_video(video_file: str, output_audio_file: str, fps: int = 16000) -> str:
    ensure_parent_dir(output_audio_file)
    video = VideoFileClip(str(Path(video_file).expanduser()))

    try:
        if video.audio is None:
            raise ValueError("The video has no audio track to transcribe.")

        video.audio.write_audiofile(
            str(Path(output_audio_file).expanduser()),
            fps=fps,
            nbytes=2,
            codec="pcm_s16le",
            ffmpeg_params=["-ac", "1"],
            logger=None,
        )
    finally:
        video.close()

    return output_audio_file


def normalize_word(word: str) -> str:
    return re.sub(r"[^\w]+", "", word.lower())


def count_words(text: str) -> int:
    return sum(1 for word in text.split() if normalize_word(word))


def normalized_words(text: str) -> list[str]:
    return [word for raw_word in text.split() if (word := normalize_word(raw_word))]


def repeated_ngram_ratio(text: str, n: int = 5) -> float:
    words = normalized_words(text)
    if len(words) < (n * 2):
        return 0.0

    ngrams = [tuple(words[index:index + n]) for index in range(len(words) - n + 1)]
    counts = Counter(ngrams)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / max(1, len(ngrams))


def similar_segment_ratio(segments: list[SubtitleSegment]) -> float:
    normalized_segments = [
        normalize_transcript_match_text(segment.text)
        for segment in segments
        if count_words(segment.text) >= 4
    ]
    if len(normalized_segments) < 3:
        return 0.0

    similar_count = 0
    for index, text in enumerate(normalized_segments):
        previous_window = normalized_segments[max(0, index - 6):index]
        if not previous_window:
            continue
        if text in previous_window or any(
            transcript_text_similarity(text, previous) >= 0.95
            for previous in previous_window
        ):
            similar_count += 1

    return similar_count / max(1, len(normalized_segments))


def timeline_duration(segments: list[SubtitleSegment]) -> float:
    return max((segment.end for segment in segments), default=0.0)


def transcript_quality_score(
    text: str,
    segments: list[SubtitleSegment],
    total_duration: float | None = None,
) -> float:
    duration = total_duration if total_duration is not None else timeline_duration(segments)
    words_per_second = count_words(text) / max(duration, 1.0)
    repetition_penalty = repeated_ngram_ratio(text) * 14.0
    segment_penalty = similar_segment_ratio(segments) * 8.0
    return min(words_per_second, 4.0) - repetition_penalty - segment_penalty


def transcript_looks_low_quality(
    text: str,
    segments: list[SubtitleSegment],
    total_duration: float | None = None,
) -> bool:
    duration = total_duration if total_duration is not None else timeline_duration(segments)
    if not text.strip():
        return True
    if duration >= 20 and count_words(text) < max(12, int(duration * 0.75)):
        return True
    if repeated_ngram_ratio(text) >= 0.08:
        return True
    if similar_segment_ratio(segments) >= 0.15:
        return True
    return transcript_quality_score(text, segments, duration) < 0.8


def should_use_ocr_transcript(
    current_text: str,
    current_segments: list[SubtitleSegment],
    ocr_text: str,
    ocr_segments: list[SubtitleSegment],
    ocr_coverage: float,
) -> bool:
    if not ocr_text.strip() or not ocr_segments:
        return False

    current_duration = max(timeline_duration(current_segments), 0.1)
    ocr_duration = max(timeline_duration(ocr_segments), 0.1)
    current_score = transcript_quality_score(current_text, current_segments, current_duration)
    ocr_score = transcript_quality_score(ocr_text, ocr_segments, ocr_duration)
    current_words = count_words(current_text)
    ocr_words = count_words(ocr_text)

    if ocr_coverage < 0.3 and ocr_words < max(6, current_words // 2):
        return False

    if transcript_looks_low_quality(current_text, current_segments, current_duration):
        return ocr_score >= (current_score - 0.4) or ocr_words >= max(6, current_words // 2)

    return ocr_score > (current_score + 0.6)


def remove_duplicate_prefix(previous_text: str, current_text: str) -> str:
    previous_words = [word for word in previous_text.split() if normalize_word(word)]
    current_words = [word for word in current_text.split() if normalize_word(word)]

    if not previous_words or not current_words:
        return current_text

    max_overlap = min(len(previous_words), len(current_words), 12)
    for overlap in range(max_overlap, 0, -1):
        previous_tail = [normalize_word(word) for word in previous_words[-overlap:]]
        current_head = [normalize_word(word) for word in current_words[:overlap]]
        if previous_tail == current_head:
            trimmed = " ".join(current_words[overlap:])
            return trimmed.strip()

    return current_text


def should_split_transcription_result(
    raw_text: str,
    deduped_text: str,
    duration: float,
    min_chunk_seconds: float,
) -> bool:
    if duration <= (min_chunk_seconds * 1.5):
        return False

    raw_words = count_words(raw_text)
    deduped_words = count_words(deduped_text)
    if raw_words == 0:
        return True
    if deduped_words == 0:
        return True
    if duration >= max(6.0, min_chunk_seconds * 2) and raw_words <= 4:
        return True
    if duration >= max(7.0, min_chunk_seconds * 2.5) and deduped_words <= 2:
        return True

    return False


def recognize_audio_chunk(
    recognizer: sr.Recognizer,
    audio_path: str,
    start: float,
    duration: float,
    speech_lang: str,
) -> str:
    with sr.AudioFile(audio_path) as source:
        audio_data = recognizer.record(source, offset=float(start), duration=float(duration))
    return google_recognize_best(recognizer, audio_data, speech_lang)


def audio_data_duration(audio_data: sr.AudioData) -> float:
    frame_count = len(audio_data.frame_data) / max(1, audio_data.sample_width)
    return frame_count / float(audio_data.sample_rate)


def google_recognize_best(
    recognizer: sr.Recognizer,
    audio_data: sr.AudioData,
    speech_lang: str,
) -> str:
    speech_lang = normalize_language_code(speech_lang, default="en-US")
    if speech_lang == "auto":
        speech_lang = "en-US"
    response = recognizer.recognize_google(audio_data, language=speech_lang, show_all=True)
    if isinstance(response, dict):
        alternatives = response.get("alternative", [])
        best_text = ""
        best_score = -1.0
        for alternative in alternatives:
            text = str(alternative.get("transcript", "")).strip()
            if not text:
                continue
            confidence = float(alternative.get("confidence", 0.0) or 0.0)
            score = (confidence * 1000.0) + count_words(text)
            if score > best_score:
                best_text = text
                best_score = score
        if best_text:
            return best_text

    if isinstance(response, str):
        return response.strip()

    return recognizer.recognize_google(audio_data, language=speech_lang).strip()


def transcribe_audio_window(
    audio_path: str,
    recognizer: sr.Recognizer,
    start: float,
    duration: float,
    total_duration: float,
    speech_lang: str,
    previous_text: str,
    min_chunk_seconds: float,
    recognize_chunk: Callable[[sr.Recognizer, str, float, float, str], str] | None = None,
) -> list[SubtitleSegment]:
    recognize = recognize_chunk or recognize_audio_chunk
    raw_text = ""

    try:
        raw_text = recognize(recognizer, audio_path, start, duration, speech_lang)
    except sr.UnknownValueError:
        raw_text = ""
    except sr.RequestError as exc:
        raise RuntimeError(f"Speech recognition failed: {exc}") from exc

    deduped_text = remove_duplicate_prefix(previous_text, raw_text).strip()
    if should_split_transcription_result(raw_text, deduped_text, duration, min_chunk_seconds):
        half_duration = duration / 2.0
        if half_duration < min_chunk_seconds:
            return []

        left_segments = transcribe_audio_window(
            audio_path=audio_path,
            recognizer=recognizer,
            start=start,
            duration=half_duration,
            total_duration=total_duration,
            speech_lang=speech_lang,
            previous_text=previous_text,
            min_chunk_seconds=min_chunk_seconds,
            recognize_chunk=recognize,
        )
        previous_for_right = left_segments[-1].text if left_segments else previous_text
        right_segments = transcribe_audio_window(
            audio_path=audio_path,
            recognizer=recognizer,
            start=start + half_duration,
            duration=duration - half_duration,
            total_duration=total_duration,
            speech_lang=speech_lang,
            previous_text=previous_for_right,
            min_chunk_seconds=min_chunk_seconds,
            recognize_chunk=recognize,
        )
        return left_segments + right_segments

    if not deduped_text:
        return []

    end = min(total_duration, start + duration)
    return [SubtitleSegment(start=start, end=end, text=deduped_text)]


def transcribe_audio_to_segments_windowed(
    audio_file: str,
    speech_lang: str = "en-US",
    chunk_seconds: int = 5,
    overlap_seconds: float = 1.2,
) -> list[SubtitleSegment]:
    recognizer = sr.Recognizer()
    audio_path = str(Path(audio_file).expanduser())

    audio_clip = AudioFileClip(audio_path)
    try:
        total_duration = audio_clip.duration
    finally:
        audio_clip.close()

    if total_duration <= 0:
        raise ValueError("The extracted audio is empty.")

    segments: list[SubtitleSegment] = []
    step_seconds = max(1.0, chunk_seconds - overlap_seconds)
    min_chunk_seconds = max(2.0, min(chunk_seconds / 2.0, 3.0))
    previous_text = ""
    start = 0.0

    while start < total_duration:
        duration = min(chunk_seconds, total_duration - start)
        if duration <= 0:
            break

        window_segments = transcribe_audio_window(
            audio_path=audio_path,
            recognizer=recognizer,
            start=start,
            duration=duration,
            total_duration=total_duration,
            speech_lang=speech_lang,
            previous_text=previous_text,
            min_chunk_seconds=min_chunk_seconds,
        )
        if window_segments:
            segments.extend(window_segments)
            previous_text = window_segments[-1].text

        start += step_seconds

    if not segments:
        raise ValueError(
            "No speech was detected. Check the video audio or try a different speech language value."
        )

    return segments


def transcribe_audio_to_segments_by_phrases(
    audio_file: str,
    speech_lang: str = "en-US",
    phrase_time_limit: int = 12,
) -> list[SubtitleSegment]:
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.5
    recognizer.non_speaking_duration = 0.25
    recognizer.phrase_threshold = 0.2
    audio_path = str(Path(audio_file).expanduser())

    segments: list[SubtitleSegment] = []
    previous_text = ""

    with sr.AudioFile(audio_path) as source:
        total_duration = float(source.DURATION or 0.0)
        while True:
            start_time = float(source.audio_reader.tell()) / float(source.SAMPLE_RATE)
            try:
                audio_data = recognizer.listen(source, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError:
                break

            duration = audio_data_duration(audio_data)
            if duration <= 0:
                break

            try:
                raw_text = google_recognize_best(recognizer, audio_data, speech_lang)
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                raise RuntimeError(f"Speech recognition failed: {exc}") from exc

            deduped_text = remove_duplicate_prefix(previous_text, raw_text).strip()
            if not deduped_text:
                continue

            end_time = min(total_duration, start_time + duration)
            segments.append(SubtitleSegment(start=start_time, end=end_time, text=deduped_text))
            previous_text = deduped_text

            if end_time >= total_duration:
                break

    return segments


def speech_lang_to_short_code(speech_lang: str) -> str | None:
    value = normalize_language_code(speech_lang).strip().lower()
    if not value or value == "auto":
        return None
    return value.split("-", 1)[0].split("_", 1)[0] or None


def build_faster_whisper_init_options() -> dict[str, Any]:
    return {
        "device": "cpu",
        "compute_type": "int8",
    }


def build_faster_whisper_transcribe_options(language_code: str | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "task": "transcribe",
        "beam_size": 5,
        "best_of": 5,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "no_repeat_ngram_size": 3,
        "vad_filter": True,
        "hallucination_silence_threshold": 2,
    }
    if language_code:
        options["language"] = language_code
    return options


def stronger_whisper_model(model: str) -> str | None:
    normalized = model.strip().lower() or "medium"
    upgrades = {
        "tiny": "base",
        "tiny.en": "base",
        "base": "small",
        "base.en": "small",
        "small": "medium",
        "small.en": "medium",
    }
    return upgrades.get(normalized)


def resolve_whisper_model_name(model: str, speech_lang: str) -> str:
    language_code = speech_lang_to_short_code(speech_lang)
    if language_code == "en" and model in {"tiny", "base", "small", "medium"}:
        return f"{model}.en"
    return model


def transcribe_audio_to_segments_with_whisper(
    audio_file: str,
    speech_lang: str = "en-US",
    engine: str = "faster-whisper",
    model: str = "base",
) -> list[SubtitleSegment]:
    recognizer = sr.Recognizer()
    audio_path = str(Path(audio_file).expanduser())
    language_code = speech_lang_to_short_code(speech_lang)
    resolved_model = resolve_whisper_model_name(model, speech_lang)

    with sr.AudioFile(audio_path) as source:
        audio_data = recognizer.record(source)

    if engine == "faster-whisper":
        result = recognizer.recognize_faster_whisper(
            audio_data,
            model=resolved_model,
            show_dict=True,
            init_options=build_faster_whisper_init_options(),
            **build_faster_whisper_transcribe_options(language_code),
        )
    else:
        options = {"task": "transcribe"}
        if language_code:
            options["language"] = language_code
        result = recognizer.recognize_whisper(
            audio_data,
            model=resolved_model,
            show_dict=True,
            **options,
        )

    segments: list[SubtitleSegment] = []
    for segment in result.get("segments", []):
        if hasattr(segment, "start"):
            start = float(getattr(segment, "start"))
            end = float(getattr(segment, "end"))
            text = str(getattr(segment, "text", "")).strip()
        else:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start))
            text = str(segment.get("text", "")).strip()
        if text:
            segments.append(SubtitleSegment(start=start, end=end, text=text))

    if segments:
        return cleanup_transcript_segments(segments)

    text = str(result.get("text", "")).strip()
    if not text:
        raise ValueError("The transcription engine returned no text.")
    return cleanup_transcript_segments(
        [SubtitleSegment(start=0.0, end=max(0.1, audio_data_duration(audio_data)), text=text)]
    )


def choose_transcription_engine(requested: str) -> str:
    value = requested.strip().lower() or "auto"
    if value != "auto":
        return value
    if module_available("faster_whisper"):
        return "faster-whisper"
    if module_available("whisper"):
        return "whisper"
    return "google"


def looks_like_low_coverage(segments: list[SubtitleSegment], total_duration: float) -> bool:
    if not segments:
        return True
    text = join_segments_text(segments)
    if transcript_looks_low_quality(text, segments, total_duration):
        return True
    if total_duration < 20:
        return False
    return count_words(text) < max(12, int(total_duration * 0.8))


def should_use_candidate_transcript(
    current_segments: list[SubtitleSegment],
    candidate_segments: list[SubtitleSegment],
) -> bool:
    if not candidate_segments:
        return False
    if not current_segments:
        return True

    current_text = join_segments_text(current_segments)
    candidate_text = join_segments_text(candidate_segments)
    if not candidate_text.strip():
        return False

    current_duration = timeline_duration(current_segments)
    candidate_duration = timeline_duration(candidate_segments)
    current_score = transcript_quality_score(current_text, current_segments, current_duration)
    candidate_score = transcript_quality_score(candidate_text, candidate_segments, candidate_duration)
    if candidate_score > current_score + 0.05:
        return True

    current_words = count_words(current_text)
    candidate_words = count_words(candidate_text)
    return (
        transcript_looks_low_quality(current_text, current_segments, current_duration)
        and candidate_words >= current_words + 2
    )


def should_try_google_speech_fallback(speech_lang: str, current_text: str) -> bool:
    normalized_lang = normalize_language_code(speech_lang, default="auto")
    if normalized_lang != "auto":
        return True

    has_latin_text = bool(re.search(r"[A-Za-z]", current_text))
    has_non_latin_asian_text = bool(re.search(r"[\u1780-\u17ff\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", current_text))
    return has_latin_text and not has_non_latin_asian_text


def transcribe_audio_to_segments(
    audio_file: str,
    speech_lang: str = "en-US",
    chunk_seconds: int = 5,
    overlap_seconds: float = 1.2,
    engine: str = "auto",
    whisper_model: str = "base",
) -> list[SubtitleSegment]:
    audio_path = str(Path(audio_file).expanduser())
    audio_clip = AudioFileClip(audio_path)
    try:
        total_duration = float(audio_clip.duration or 0.0)
    finally:
        audio_clip.close()

    if total_duration <= 0:
        raise ValueError("The extracted audio is empty.")

    chosen_engine = choose_transcription_engine(engine)
    if chosen_engine in {"whisper", "faster-whisper"}:
        return cleanup_transcript_segments(
            transcribe_audio_to_segments_with_whisper(
                audio_file,
                speech_lang=speech_lang,
                engine=chosen_engine,
                model=whisper_model,
            )
        )

    phrase_segments = cleanup_transcript_segments(
        transcribe_audio_to_segments_by_phrases(
            audio_file,
            speech_lang=speech_lang,
            phrase_time_limit=max(8, min(20, chunk_seconds * 2)),
        )
    )
    if phrase_segments and not looks_like_low_coverage(phrase_segments, total_duration):
        return phrase_segments

    windowed_segments = cleanup_transcript_segments(
        transcribe_audio_to_segments_windowed(
            audio_file,
            speech_lang=speech_lang,
            chunk_seconds=chunk_seconds,
            overlap_seconds=overlap_seconds,
        )
    )
    if count_words(join_segments_text(windowed_segments)) >= count_words(join_segments_text(phrase_segments)):
        return windowed_segments
    return phrase_segments


def transcribe_video_to_segments(
    video_file: str,
    speech_lang: str = "en-US",
    chunk_seconds: int = 5,
    overlap_seconds: float = 1.2,
    engine: str = "auto",
    whisper_model: str = "base",
) -> list[SubtitleSegment]:
    video_path = Path(video_file).expanduser().resolve()
    temp_dir_path = create_workspace_temp_dir(video_path.parent, "transcribe_audio")
    temp_audio_path = str(temp_dir_path / "source_audio.wav")

    try:
        extract_audio_from_video(video_file, temp_audio_path)
        return transcribe_audio_to_segments(
            temp_audio_path,
            speech_lang=speech_lang,
            chunk_seconds=chunk_seconds,
            overlap_seconds=overlap_seconds,
            engine=engine,
            whisper_model=whisper_model,
        )
    finally:
        shutil.rmtree(temp_dir_path, ignore_errors=True)


def retry_transcription_with_stronger_whisper(
    video_file: str,
    speech_lang: str,
    chunk_seconds: int,
    overlap_seconds: float,
    chosen_engine: str,
    whisper_model: str,
    current_segments: list[SubtitleSegment],
    logger: Callable[[str], None] | None = None,
) -> list[SubtitleSegment]:
    log = logger or (lambda _message: None)
    retry_model = stronger_whisper_model(whisper_model)
    if chosen_engine not in {"whisper", "faster-whisper"} or not retry_model:
        return current_segments

    current_resolved_model = resolve_whisper_model_name(whisper_model, speech_lang)
    retry_resolved_model = resolve_whisper_model_name(retry_model, speech_lang)
    if current_resolved_model == retry_resolved_model:
        return current_segments

    current_text = join_segments_text(current_segments)
    current_duration = timeline_duration(current_segments)
    if not transcript_looks_low_quality(current_text, current_segments, current_duration):
        return current_segments

    log(f"Transcript looked weak, retrying with stronger Whisper model: {retry_model}")
    try:
        retried_segments = transcribe_video_to_segments(
            video_file,
            speech_lang=speech_lang,
            chunk_seconds=chunk_seconds,
            overlap_seconds=overlap_seconds,
            engine=chosen_engine,
            whisper_model=retry_model,
        )
    except Exception as exc:
        log(f"Stronger Whisper retry failed: {exc}")
        return current_segments

    current_score = transcript_quality_score(current_text, current_segments, current_duration)
    retried_text = join_segments_text(retried_segments)
    retried_score = transcript_quality_score(
        retried_text,
        retried_segments,
        timeline_duration(retried_segments),
    )

    if retried_score > current_score:
        log(f"Using stronger Whisper transcript from {retry_model}.")
        return retried_segments

    log("Kept the original transcript after the stronger Whisper retry.")
    return current_segments


def audio_clip_channel_count(audio_clip) -> int | None:
    channels = getattr(audio_clip, "nchannels", None)
    if isinstance(channels, int) and channels > 0:
        return channels
    return None


def ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("imageio-ffmpeg is required for original voice removal.") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def remove_center_voice_from_video_audio(video_file: str, output_audio_file: str) -> str:
    ensure_parent_dir(output_audio_file)
    command = [
        ffmpeg_executable(),
        "-y",
        "-i",
        str(Path(video_file).expanduser()),
        "-vn",
        "-af",
        "pan=stereo|c0=c0-c1|c1=c1-c0,volume=0.5",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        str(Path(output_audio_file).expanduser()),
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip().splitlines()
        detail = stderr[-1] if stderr else "ffmpeg failed"
        raise RuntimeError(detail)
    return output_audio_file


def merge_audio_to_video(
    video_file: str,
    audio_file: str,
    output_file: str = "final_output.mp4",
    keep_original_audio: bool = False,
    preserve_background_audio: bool = True,
    original_volume: float = DEFAULT_BACKGROUND_VOLUME,
    extend_to_narration: bool = True,
    logger: Callable[[str], None] | None = None,
) -> tuple[str, bool]:
    ensure_parent_dir(output_file)
    log = logger or (lambda _message: None)

    video = VideoFileClip(str(Path(video_file).expanduser()))
    narration_source = AudioFileClip(str(Path(audio_file).expanduser()))
    narration = narration_source
    trimmed_narration = None
    extended_video = None
    mixed_audio = None
    final_video = None
    padding_audio = None
    background_audio = None
    quiet_background_audio = None
    quiet_original_audio = None
    background_temp_dir: Path | None = None
    video_extended = False

    try:
        base_video = video
        if extend_to_narration and narration.duration > video.duration:
            extended_video, video_extended = extend_video_clip(video, narration.duration)
            base_video = extended_video
        elif not extend_to_narration and narration.duration > video.duration:
            log("Narration is longer than the original video; trimming it to keep realtime video duration.")
            trimmed_narration = trim_audio_clip(narration_source, float(video.duration or 0.0))
            narration = trimmed_narration

        if keep_original_audio and video.audio is not None:
            quiet_original_audio = scale_audio_clip(video.audio, original_volume)
            mixed_audio = CompositeAudioClip([quiet_original_audio, narration])
        elif preserve_background_audio and video.audio is not None:
            channels = audio_clip_channel_count(video.audio)
            if channels is not None and channels < 2:
                log("Original audio is mono; removing all original audio because voice-only removal needs stereo.")
                padding_audio = create_silent_audio(base_video.duration)
                mixed_audio = CompositeAudioClip([padding_audio, narration])
            else:
                try:
                    output_root = Path(output_file).expanduser().resolve().parent
                    background_temp_dir = create_workspace_temp_dir(output_root, "voice_removed_audio")
                    background_path = str(background_temp_dir / "background_without_center_voice.wav")
                    remove_center_voice_from_video_audio(video_file, background_path)
                    background_audio = AudioFileClip(background_path)
                    quiet_background_audio = scale_audio_clip(background_audio, original_volume)
                    mixed_audio = CompositeAudioClip([quiet_background_audio, narration])
                except Exception as exc:
                    log(f"Could not remove only the original voice ({exc}); removing all original audio instead.")
                    padding_audio = create_silent_audio(base_video.duration)
                    mixed_audio = CompositeAudioClip([padding_audio, narration])
        else:
            padding_audio = create_silent_audio(base_video.duration)
            mixed_audio = CompositeAudioClip([padding_audio, narration])

        final_video = attach_audio_clip(base_video, mixed_audio)
        final_video = set_clip_duration(final_video, base_video.duration)
        final_video.write_videofile(
            str(Path(output_file).expanduser()),
            codec="libx264",
            audio_codec="aac",
        )
    finally:
        if final_video is not None:
            final_video.close()
        if mixed_audio is not None:
            mixed_audio.close()
        if quiet_background_audio is not None:
            quiet_background_audio.close()
        if background_audio is not None:
            background_audio.close()
        if quiet_original_audio is not None:
            quiet_original_audio.close()
        if padding_audio is not None:
            padding_audio.close()
        if extended_video is not None:
            extended_video.close()
        if trimmed_narration is not None:
            trimmed_narration.close()
        narration_source.close()
        video.close()
        if background_temp_dir is not None:
            shutil.rmtree(background_temp_dir, ignore_errors=True)

    return output_file, video_extended


def validate_config(config: WorkflowConfig) -> None:
    if not config.video:
        raise ValueError("Provide a video file.")

    video_path = Path(config.video).expanduser()
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if not 0 <= config.original_volume <= 1:
        raise ValueError("Original volume must be between 0 and 1.")

    if config.chunk_seconds <= 0:
        raise ValueError("Chunk seconds must be greater than 0.")


def analyze_video(
    config: WorkflowConfig,
    logger: Callable[[str], None] | None = None,
) -> AnalysisResult:
    log = logger or (lambda _message: None)
    config = resolve_generated_output_config(config, logger=log)
    validate_config(config)
    configure_hf_environment(config.hf_token)

    video_path = Path(config.video).expanduser()
    use_text_mode = bool(config.text or config.text_file)

    transcript_path: str | None = None
    subtitle_path: str | None = None
    translated_subtitle_path: str | None = None
    source_segments: list[SubtitleSegment] = []

    if use_text_mode:
        source_text = read_source_text(config.text, config.text_file)
        log(f"Loaded source text ({len(source_text)} characters).")
    else:
        sidecar = load_sidecar_transcript(str(video_path))
        if sidecar is not None:
            source_text, source_segments, sidecar_path = sidecar
            log(f"Step 1/4: loaded sidecar subtitles from: {sidecar_path}")
        else:
            embedded = extract_embedded_subtitle_transcript(str(video_path))
            if embedded is not None:
                source_text, source_segments = embedded
                log("Step 1/4: loaded embedded subtitle track from the video.")
            else:
                chosen_engine = choose_transcription_engine(config.transcription_engine)
                log(f"Step 1/4: transcribing speech using {chosen_engine}...")
                transcription_error: Exception | None = None
                try:
                    source_segments = transcribe_video_to_segments(
                        str(video_path),
                        speech_lang=config.speech_lang,
                        chunk_seconds=config.chunk_seconds,
                        overlap_seconds=config.overlap_seconds,
                        engine=config.transcription_engine,
                        whisper_model=config.whisper_model,
                    )
                    source_segments = retry_transcription_with_stronger_whisper(
                        str(video_path),
                        speech_lang=config.speech_lang,
                        chunk_seconds=config.chunk_seconds,
                        overlap_seconds=config.overlap_seconds,
                        chosen_engine=chosen_engine,
                        whisper_model=config.whisper_model,
                        current_segments=source_segments,
                        logger=log,
                    )
                    fallback_source_text = join_segments_text(source_segments)
                    if (
                        transcript_looks_low_quality(fallback_source_text, source_segments)
                        and should_try_google_speech_fallback(config.speech_lang, fallback_source_text)
                    ):
                        log("Transcript still looked weak, trying Google speech recognition fallback...")
                        try:
                            google_segments = transcribe_video_to_segments(
                                str(video_path),
                                speech_lang=config.speech_lang,
                                chunk_seconds=config.chunk_seconds,
                                overlap_seconds=config.overlap_seconds,
                                engine="google",
                                whisper_model=config.whisper_model,
                            )
                            if should_use_candidate_transcript(source_segments, google_segments):
                                source_segments = google_segments
                                log("Using Google speech recognition transcript because it has better coverage.")
                            else:
                                log("Kept the Whisper transcript after Google fallback.")
                        except Exception as google_exc:
                            log(f"Google speech fallback skipped: {google_exc}")
                except Exception as exc:
                    if chosen_engine in {"whisper", "faster-whisper"}:
                        log(f"Transcription engine failed, falling back to Google speech recognition: {exc}")
                        try:
                            source_segments = transcribe_video_to_segments(
                                str(video_path),
                                speech_lang=config.speech_lang,
                                chunk_seconds=config.chunk_seconds,
                                overlap_seconds=config.overlap_seconds,
                                engine="google",
                                whisper_model=config.whisper_model,
                            )
                        except Exception as google_exc:
                            transcription_error = google_exc
                    else:
                        transcription_error = exc

                if source_segments:
                    source_text = join_segments_text(source_segments)
                else:
                    burned_in_subtitles = extract_burned_in_subtitle_transcript(str(video_path), logger=log)
                    if burned_in_subtitles is not None:
                        ocr_text, ocr_segments, ocr_coverage = burned_in_subtitles
                        source_text = ocr_text
                        source_segments = ocr_segments
                        log("Using burned-in subtitle OCR because speech transcription was unavailable.")
                    elif transcription_error is not None:
                        raise transcription_error
                    else:
                        raise ValueError("No transcript could be created from speech or visible subtitles.")

                if transcript_looks_low_quality(source_text, source_segments):
                    burned_in_subtitles = extract_burned_in_subtitle_transcript(str(video_path), logger=log)
                    if burned_in_subtitles is not None:
                        ocr_text, ocr_segments, ocr_coverage = burned_in_subtitles
                        if should_use_ocr_transcript(
                            source_text,
                            source_segments,
                            ocr_text,
                            ocr_segments,
                            ocr_coverage,
                        ):
                            source_text = ocr_text
                            source_segments = ocr_segments
                            log("Using burned-in subtitle OCR instead of the weak speech transcript.")

        if config.repair_transcript_with_ollama:
            log(f"Repairing transcript with Ollama using model {config.ollama_model}...")
            repaired_text = repair_transcript_with_ollama(
                source_text,
                model=config.ollama_model,
                source_lang=config.speech_lang,
                logger=log,
            )
            if repaired_text != source_text:
                source_text = repaired_text
                repaired_lines = split_script_for_timed_segments(source_text, source_segments) if source_segments else None
                if repaired_lines and len(repaired_lines) == len(source_segments):
                    source_segments = [
                        SubtitleSegment(
                            start=segment.start,
                            end=segment.end,
                            text=line,
                        )
                        for segment, line in zip(source_segments, repaired_lines)
                    ]
                log("Applied Ollama transcript repair.")

        transcript_path = save_text(source_text, config.transcript_out)
        subtitle_path = save_srt(source_segments, config.subtitle_out)
        log(f"Saved original transcript to: {transcript_path}")
        log(f"Saved original subtitles to: {subtitle_path}")

    if config.skip_translation:
        translated_text = source_text
        translated_segments = source_segments
        log("Step 2/4: skipped translation.")
    else:
        log("Step 2/4: translating to Khmer script...")
        translated_text, translated_segments = build_translated_outputs(
            source_text,
            source_segments,
            target_lang=config.target_lang,
            source_lang=config.source_lang,
        ) if source_segments else (
            translate_text(
                source_text,
                target_lang=config.target_lang,
                source_lang=config.source_lang,
            ),
            [],
        )

    translated_text_path = save_text(translated_text, config.translated_text_out)
    log(f"Saved Khmer text to: {translated_text_path}")

    if translated_segments:
        translated_subtitle_path = save_srt(translated_segments, config.translated_subtitle_out)
        log(f"Saved Khmer subtitles to: {translated_subtitle_path}")

    return AnalysisResult(
        transcript_path=transcript_path,
        subtitle_path=subtitle_path,
        translated_subtitle_path=translated_subtitle_path,
        translated_text_path=translated_text_path,
        source_text=source_text,
        translated_text=translated_text,
        source_segments=source_segments,
        translated_segments=translated_segments,
    )


def save_voice_synced_subtitles(
    analysis: AnalysisResult,
    timed_segments: list[SubtitleSegment],
    output_file: str,
    logger: Callable[[str], None] | None = None,
) -> AnalysisResult:
    if not timed_segments:
        return analysis

    log = logger or (lambda _message: None)
    subtitle_path = save_srt(timed_segments, output_file)
    log(f"Saved Khmer subtitles synced to generated voice at: {subtitle_path}")
    return replace(
        analysis,
        translated_subtitle_path=subtitle_path,
        translated_segments=timed_segments,
    )


def build_voice_with_timing(
    khmer_text: str,
    output_file: str,
    voice_lang: str = "km",
    voice_gender: str = DEFAULT_VOICE_GENDER,
    slow_voice: bool = False,
    timed_segments: list[SubtitleSegment] | None = None,
    force_fit_to_timeline: bool = True,
    logger: Callable[[str], None] | None = None,
) -> VoiceGenerationResult:
    log = logger or (lambda _message: None)
    normalized_gender = normalize_voice_gender(voice_gender, default=DEFAULT_VOICE_GENDER)
    sync_ready = bool(timed_segments and split_script_for_timed_segments(khmer_text, timed_segments))
    if sync_ready:
        log(f"Step 3/4: generating {normalized_gender} voice in realtime with the subtitle timeline...")
    elif timed_segments:
        log(f"Step 3/4: subtitle timing did not match the edited script, so generating a continuous {normalized_gender} voice track...")
    else:
        log(f"Step 3/4: generating {normalized_gender} voice...")

    voice_result = generate_voice_with_timing(
        khmer_text,
        lang=voice_lang,
        output_file=output_file,
        slow=slow_voice,
        voice_gender=normalized_gender,
        timed_segments=timed_segments,
        force_fit_to_timeline=force_fit_to_timeline,
    )
    log(f"Saved narration to: {voice_result.audio_path}")
    return voice_result


def build_voice(
    khmer_text: str,
    output_file: str,
    voice_lang: str = "km",
    voice_gender: str = DEFAULT_VOICE_GENDER,
    slow_voice: bool = False,
    timed_segments: list[SubtitleSegment] | None = None,
    force_fit_to_timeline: bool = True,
    logger: Callable[[str], None] | None = None,
) -> str:
    return build_voice_with_timing(
        khmer_text,
        output_file=output_file,
        voice_lang=voice_lang,
        voice_gender=voice_gender,
        slow_voice=slow_voice,
        timed_segments=timed_segments,
        force_fit_to_timeline=force_fit_to_timeline,
        logger=logger,
    ).audio_path


def build_output_video(
    video_file: str,
    audio_file: str,
    output_file: str,
    keep_original_audio: bool = False,
    preserve_background_audio: bool = True,
    original_volume: float = DEFAULT_BACKGROUND_VOLUME,
    extend_to_narration: bool = True,
    logger: Callable[[str], None] | None = None,
) -> tuple[str, bool]:
    log = logger or (lambda _message: None)
    preserve_background_audio = preserve_background_audio and not keep_original_audio
    if keep_original_audio:
        log(f"Step 4/4: mixing narration with original audio at {original_volume:g} volume...")
    elif preserve_background_audio:
        log(f"Step 4/4: removing original voice and keeping background sound at {original_volume:g} volume...")
    else:
        log("Step 4/4: removing original video audio and adding narration...")
    merge_kwargs = {
        "output_file": output_file,
        "keep_original_audio": keep_original_audio,
        "preserve_background_audio": preserve_background_audio,
        "original_volume": original_volume,
        "logger": log,
    }
    if not extend_to_narration:
        merge_kwargs["extend_to_narration"] = False
    output_path, video_extended = merge_audio_to_video(
        video_file,
        audio_file,
        **merge_kwargs,
    )
    log(f"Created video at: {output_path}")
    if video_extended:
        log("Info: the video was extended so the full narration could finish.")
    return output_path, video_extended


def run_workflow(
    config: WorkflowConfig,
    logger: Callable[[str], None] | None = None,
) -> WorkflowResult:
    config = resolve_generated_output_config(config, logger=logger)
    analysis = analyze_video(config, logger=logger)

    if config.skip_voice:
        return WorkflowResult(
            analysis=analysis,
            audio_path=None,
            output_video_path=None,
            video_extended=False,
        )

    voice_result = build_voice_with_timing(
        analysis.translated_text,
        output_file=config.audio_out,
        voice_lang=config.voice_lang,
        voice_gender=config.voice_gender,
        slow_voice=config.slow_voice,
        timed_segments=analysis.translated_segments,
        logger=logger,
    )
    analysis = save_voice_synced_subtitles(
        analysis,
        voice_result.timed_segments,
        config.translated_subtitle_out,
        logger=logger,
    )
    output_path, video_extended = build_output_video(
        config.video,
        voice_result.audio_path,
        output_file=config.output,
        keep_original_audio=config.keep_original_audio,
        preserve_background_audio=config.preserve_background_audio,
        original_volume=config.original_volume,
        extend_to_narration=not bool(voice_result.timed_segments),
        logger=logger,
    )
    return WorkflowResult(
        analysis=analysis,
        audio_path=voice_result.audio_path,
        output_video_path=output_path,
        video_extended=video_extended,
    )
