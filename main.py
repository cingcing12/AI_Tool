from __future__ import annotations

import argparse
import sys

from pipeline import (
    DEFAULT_BACKGROUND_VOLUME,
    DEFAULT_VOICE_GENDER,
    WorkflowConfig,
    download_video_from_url,
    normalize_language_code,
    normalize_voice_gender,
    run_workflow,
)


def prompt_text(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or (default or "")


def prompt_bool(label: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    value = input(f"{label}{suffix}").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "true"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transcribe a video, translate subtitles to Khmer, and optionally create Khmer voiceover."
    )
    parser.add_argument("text", nargs="?", help="Optional source text if you want text-first mode")
    parser.add_argument("--text-file", help="Path to a UTF-8 text file with source text")
    parser.add_argument("--video", help="Path to the input video file")
    parser.add_argument("--video-url", help="Download a video from a link or copied share text, for example a Douyin URL")
    parser.add_argument(
        "--cookies-from-browser",
        default="",
        help="Browser to load fresh cookies from for video links, for example edge, chrome, or firefox",
    )
    parser.add_argument("--cookies", default="", help="Netscape cookies.txt file for video link downloads")
    parser.add_argument("--gui", action="store_true", help="Launch the desktop UI")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for missing inputs in the terminal",
    )
    parser.add_argument(
        "--speech-lang",
        default="auto",
        help="Speech recognition language code for the video audio, for example auto, en-US, or zh-CN",
    )
    parser.add_argument("--source-lang", default="auto", help="Source language code for translation, for example auto or zh-CN")
    parser.add_argument("--target-lang", default="km", help="Target language code for translation, for example km or zh-CN")
    parser.add_argument("--voice-lang", default="km", help="Language code for text-to-speech, for example km or zh-CN")
    parser.add_argument(
        "--voice-gender",
        default=DEFAULT_VOICE_GENDER,
        choices=("female", "male", "auto"),
        help="Generated voice gender: female, male, or auto",
    )
    parser.add_argument(
        "--transcription-engine",
        default="auto",
        help="Transcription engine: auto, google, whisper, or faster-whisper",
    )
    parser.add_argument(
        "--whisper-model",
        default="medium",
        help="Whisper model size, for example small, medium, or large-v3",
    )
    parser.add_argument(
        "--hf-token",
        default="",
        help="Optional Hugging Face access token for faster-whisper downloads",
    )
    parser.add_argument(
        "--repair-transcript-with-ollama",
        action="store_true",
        help="Use Ollama to polish the transcript after speech recognition",
    )
    parser.add_argument(
        "--ollama-model",
        default="llava:latest",
        help="Ollama model name used for transcript repair",
    )
    parser.add_argument(
        "--skip-translation",
        action="store_true",
        help="Use the source text directly instead of translating it first",
    )
    parser.add_argument(
        "--skip-voice",
        action="store_true",
        help="Create subtitles and Khmer text only, without voice generation or video audio merge",
    )
    parser.add_argument(
        "--transcript-out",
        default="transcript_original.txt",
        help="File path to save the original transcript text",
    )
    parser.add_argument(
        "--subtitle-out",
        default="subtitles_original.srt",
        help="File path to save the original subtitles",
    )
    parser.add_argument(
        "--translated-subtitle-out",
        default="subtitles_khmer.srt",
        help="File path to save the translated Khmer subtitles",
    )
    parser.add_argument(
        "--translated-text-out",
        default="translated_khmer.txt",
        help="File path to save the translated Khmer script",
    )
    parser.add_argument("--audio-out", default="narration.mp3", help="Output MP3 narration path")
    parser.add_argument("--output", default="final_output.mp4", help="Output MP4 path")
    audio_group = parser.add_mutually_exclusive_group()
    audio_group.add_argument(
        "--remove-original-voice",
        dest="preserve_background_audio",
        action="store_true",
        help="Remove the centered original voice while keeping background sound where possible (default)",
    )
    audio_group.add_argument(
        "--remove-original-audio",
        dest="preserve_background_audio",
        action="store_false",
        help="Remove all original video audio and use only the generated narration in the final video",
    )
    audio_group.add_argument(
        "--keep-original-audio",
        dest="keep_original_audio",
        action="store_true",
        help="Mix the narration with the original video audio instead of replacing it",
    )
    parser.set_defaults(keep_original_audio=False, preserve_background_audio=True)
    parser.add_argument(
        "--original-volume",
        type=float,
        default=DEFAULT_BACKGROUND_VOLUME,
        help="Volume multiplier for the original video audio when mixing",
    )
    parser.add_argument(
        "--slow-voice",
        action="store_true",
        help="Generate slower narration for easier listening",
    )
    parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=5,
        help="Subtitle chunk length for speech recognition in seconds",
    )
    return parser


def launch_gui() -> None:
    from ui import launch_gui as launch_gui_app

    launch_gui_app()


def fill_missing_inputs(args: argparse.Namespace) -> None:
    if not args.video and not args.video_url:
        args.video = prompt_text("Video path")

    if not args.text and not args.text_file:
        print("No text was provided, so the tool will transcribe the video audio into subtitles.")
        args.speech_lang = prompt_text("Speech language code", args.speech_lang)
        args.skip_voice = not prompt_bool("Generate Khmer voiceover", default=True)
        if not args.skip_voice:
            args.voice_gender = normalize_voice_gender(
                prompt_text("Voice gender (female, male, or auto)", args.voice_gender),
                default=DEFAULT_VOICE_GENDER,
            )
            args.keep_original_audio = prompt_bool(
                "Keep full original video audio in the background",
                default=False,
            )
            if not args.keep_original_audio:
                args.preserve_background_audio = prompt_bool(
                    "Keep background sound while removing original voice",
                    default=True,
                )
            if args.keep_original_audio or args.preserve_background_audio:
                volume_text = prompt_text("Original audio volume between 0 and 1", str(args.original_volume))
                args.original_volume = float(volume_text)


def build_config(args: argparse.Namespace) -> WorkflowConfig:
    return WorkflowConfig(
        video=args.video or "",
        text=args.text,
        text_file=args.text_file,
        speech_lang=normalize_language_code(args.speech_lang, default="auto"),
        source_lang=normalize_language_code(args.source_lang, default="auto"),
        target_lang=normalize_language_code(args.target_lang, default="km"),
        voice_lang=normalize_language_code(args.voice_lang, default="km"),
        voice_gender=normalize_voice_gender(args.voice_gender, default=DEFAULT_VOICE_GENDER),
        transcription_engine=args.transcription_engine,
        whisper_model=args.whisper_model,
        hf_token=args.hf_token,
        repair_transcript_with_ollama=args.repair_transcript_with_ollama,
        ollama_model=args.ollama_model,
        skip_translation=args.skip_translation,
        skip_voice=args.skip_voice,
        transcript_out=args.transcript_out,
        subtitle_out=args.subtitle_out,
        translated_subtitle_out=args.translated_subtitle_out,
        translated_text_out=args.translated_text_out,
        audio_out=args.audio_out,
        output=args.output,
        keep_original_audio=args.keep_original_audio,
        preserve_background_audio=args.preserve_background_audio and not args.keep_original_audio,
        original_volume=args.original_volume,
        slow_voice=args.slow_voice,
        chunk_seconds=args.chunk_seconds,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if len(sys.argv) == 1 or args.gui:
        launch_gui()
        return

    try:
        if args.interactive:
            fill_missing_inputs(args)

        if args.video_url and not args.video:
            args.video = download_video_from_url(
                args.video_url,
                logger=print,
                cookies_browser=args.cookies_from_browser,
                cookies_file=args.cookies,
            )

        run_workflow(build_config(args), logger=print)
    except Exception as exc:
        parser.exit(
            status=1,
            message=(
                f"Error: {exc}\n"
                "Hint: subtitle transcription, translation, and gTTS all require internet access.\n"
            ),
        )


if __name__ == "__main__":
    main()
