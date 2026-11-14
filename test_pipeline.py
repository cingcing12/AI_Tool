from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from main import build_config, build_parser
from pipeline import (
    WorkflowConfig,
    DEFAULT_BACKGROUND_VOLUME,
    DEFAULT_VOICE_GENDER,
    build_timed_voice_segments,
    build_output_video,
    build_transcript_repair_prompt,
    build_translated_outputs,
    build_faster_whisper_init_options,
    build_faster_whisper_transcribe_options,
    clean_subtitle_ocr_text,
    cleanup_transcript_segments,
    clean_ollama_response,
    configure_hf_environment,
    download_video_from_url,
    extract_video_url,
    find_original_video_for_generated_output,
    fit_narration_duration_to_timeline,
    edge_tts_voice_name,
    google_recognize_best,
    is_video_url,
    load_sidecar_transcript,
    looks_like_low_coverage,
    normalize_language_code,
    normalize_voice_gender,
    normalize_video_url,
    ocr_samples_to_segments,
    parse_subtitle_text,
    parse_browser_cookie_source,
    repeated_ngram_ratio,
    resolve_generated_output_config,
    retry_transcription_with_stronger_whisper,
    should_use_ocr_transcript,
    speech_lang_to_short_code,
    split_script_for_timed_segments,
    remove_center_voice_from_video_audio,
    remove_duplicate_prefix,
    stronger_whisper_model,
    should_split_transcription_result,
    should_try_google_speech_fallback,
    should_use_candidate_transcript,
    SubtitleSegment,
    translate_text,
    transcript_looks_low_quality,
    transcribe_audio_window,
)
from ui import (
    COOKIE_BROWSER_OPTIONS,
    SPEECH_LANGUAGE_OPTIONS,
    TRANSLATION_SOURCE_OPTIONS,
    TRANSLATION_TARGET_OPTIONS,
    VOICE_GENDER_OPTIONS,
    VOICE_LANGUAGE_OPTIONS,
)


class PipelineTests(unittest.TestCase):
    def test_cli_removes_original_voice_by_default(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["--video", "clip.mp4"])
        config = build_config(args)

        self.assertFalse(args.keep_original_audio)
        self.assertTrue(args.preserve_background_audio)
        self.assertFalse(config.keep_original_audio)
        self.assertTrue(config.preserve_background_audio)

    def test_cli_can_choose_original_audio_mode_explicitly(self) -> None:
        parser = build_parser()

        keep_args = parser.parse_args(["--video", "clip.mp4", "--keep-original-audio"])
        remove_voice_args = parser.parse_args(["--video", "clip.mp4", "--remove-original-voice"])
        remove_audio_args = parser.parse_args(["--video", "clip.mp4", "--remove-original-audio"])
        keep_config = build_config(keep_args)

        self.assertTrue(keep_args.keep_original_audio)
        self.assertFalse(keep_config.preserve_background_audio)
        self.assertFalse(remove_voice_args.keep_original_audio)
        self.assertTrue(remove_voice_args.preserve_background_audio)
        self.assertFalse(remove_audio_args.keep_original_audio)
        self.assertFalse(remove_audio_args.preserve_background_audio)

    def test_cli_can_choose_voice_gender(self) -> None:
        parser = build_parser()

        default_args = parser.parse_args(["--video", "clip.mp4"])
        male_args = parser.parse_args(["--video", "clip.mp4", "--voice-gender", "male"])

        self.assertEqual(build_config(default_args).voice_gender, DEFAULT_VOICE_GENDER)
        self.assertEqual(build_config(male_args).voice_gender, "male")

    def test_voice_gender_normalizes_ui_labels(self) -> None:
        self.assertEqual(normalize_voice_gender("Female - female"), "female")
        self.assertEqual(normalize_voice_gender("Male - male"), "male")
        self.assertEqual(normalize_voice_gender("Auto/default - auto"), DEFAULT_VOICE_GENDER)

    def test_khmer_edge_tts_voice_names_support_gender(self) -> None:
        self.assertEqual(edge_tts_voice_name("km", "female"), "km-KH-SreymomNeural")
        self.assertEqual(edge_tts_voice_name("Khmer - km", "male"), "km-KH-PisethNeural")

    def test_language_aliases_support_chinese(self) -> None:
        self.assertEqual(normalize_language_code("Auto detect - auto"), "auto")
        self.assertEqual(normalize_language_code("china"), "zh-CN")
        self.assertEqual(normalize_language_code("Chinese (China) - zh-CN"), "zh-CN")
        self.assertEqual(normalize_language_code("traditional chinese"), "zh-TW")
        self.assertEqual(normalize_language_code("khmer"), "km")
        self.assertEqual(speech_lang_to_short_code("china"), "zh")

    def test_cli_defaults_to_auto_speech_language(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--video", "clip.mp4"])

        config = build_config(args)

        self.assertEqual(config.speech_lang, "auto")

    def test_cli_normalizes_chinese_language_aliases(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--video",
                "clip.mp4",
                "--speech-lang",
                "china",
                "--source-lang",
                "china",
                "--target-lang",
                "china",
                "--voice-lang",
                "china",
            ]
        )

        config = build_config(args)

        self.assertEqual(config.speech_lang, "zh-CN")
        self.assertEqual(config.source_lang, "zh-CN")
        self.assertEqual(config.target_lang, "zh-CN")
        self.assertEqual(config.voice_lang, "zh-CN")

    def test_translate_text_normalizes_chinese_target(self) -> None:
        with patch("pipeline.GoogleTranslator") as translator_class:
            translator_class.return_value.translate.return_value = "ni hao"

            translated = translate_text("hello", target_lang="china", source_lang="auto")

        self.assertEqual(translated, "ni hao")
        translator_class.assert_called_once_with(source="auto", target="zh-CN")

    def test_translate_text_uses_full_context_for_multiline_scripts(self) -> None:
        with patch("pipeline.GoogleTranslator") as translator_class:
            translator = translator_class.return_value
            translator.translate.return_value = "full translated script"

            translated = translate_text("line one\nline two", target_lang="km", source_lang="auto")

        self.assertEqual(translated, "full translated script")
        translator.translate.assert_called_once_with("line one line two")

    def test_google_recognize_best_uses_english_when_speech_language_is_auto(self) -> None:
        calls: list[tuple[str, bool | None]] = []

        class FakeRecognizer:
            def recognize_google(self, _audio_data, language, show_all=False):
                calls.append((language, show_all))
                return {"alternative": [{"transcript": "hello world", "confidence": 0.8}]}

        text = google_recognize_best(FakeRecognizer(), object(), "auto")  # type: ignore[arg-type]

        self.assertEqual(text, "hello world")
        self.assertEqual(calls, [("en-US", True)])

    def test_thai_is_not_shown_in_language_options(self) -> None:
        all_options = (
            *SPEECH_LANGUAGE_OPTIONS,
            *TRANSLATION_SOURCE_OPTIONS,
            *TRANSLATION_TARGET_OPTIONS,
            *VOICE_LANGUAGE_OPTIONS,
            *VOICE_GENDER_OPTIONS,
        )

        self.assertFalse(any("Thai" in option or "th-" in option or option.endswith(" - th") for option in all_options))
        self.assertEqual(SPEECH_LANGUAGE_OPTIONS[0], "Auto detect - auto")
        self.assertEqual(VOICE_GENDER_OPTIONS[0], "Female - female")
        self.assertIn("Edge - edge", COOKIE_BROWSER_OPTIONS)

    def test_download_video_from_url_uses_downloader(self) -> None:
        temp_path = Path("test_download_workspace").resolve()
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True, exist_ok=True)
        logs: list[str] = []
        requested_urls: list[str] = []

        class FakeYDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                return False

            def extract_info(self, url, download):
                requested_urls.append(url)
                self.options["progress_hooks"][0]({"status": "finished"})
                path = Path(str(self.options["outtmpl"]).replace("%(extractor)s", "Douyin").replace("%(id)s", "123").replace("%(ext)s", "mp4"))
                path.write_bytes(b"video")
                return {"filepath": str(path), "webpage_url": url, "download": download}

        try:
            video_path = download_video_from_url(
                "https://www.douyin.com/video/123",
                output_dir=str(temp_path),
                logger=logs.append,
                ydl_class=FakeYDL,
            )
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)

        self.assertTrue(video_path.endswith("Douyin_123.mp4"))
        self.assertEqual(requested_urls, ["https://www.douyin.com/video/123"])
        self.assertTrue(any("Downloaded video to:" in message for message in logs))
        self.assertTrue(is_video_url("https://www.douyin.com/video/123"))
        self.assertFalse(is_video_url("not a url"))

    def test_douyin_share_text_and_modal_urls_are_normalized(self) -> None:
        share_text = (
            "5.82 X@m.QX 05/15 TLw:/ 一口气五十分钟 "
            "https://v.douyin.com/sqjNilrim6o/ 复制此链接，打开Dou音搜索"
        )
        modal_url = "https://www.douyin.com/jingxuan?modal_id=7613274429069511955"

        self.assertEqual(extract_video_url(share_text), "https://v.douyin.com/sqjNilrim6o/")
        self.assertEqual(normalize_video_url(share_text), "https://v.douyin.com/sqjNilrim6o/")
        self.assertEqual(
            normalize_video_url(modal_url),
            "https://www.douyin.com/video/7613274429069511955",
        )
        self.assertTrue(is_video_url(share_text))

    def test_parse_browser_cookie_source_accepts_ui_and_cli_values(self) -> None:
        self.assertIsNone(parse_browser_cookie_source("None"))
        self.assertEqual(parse_browser_cookie_source("Edge - edge"), ("edge", None, None, None))
        self.assertEqual(parse_browser_cookie_source("chrome:Default"), ("chrome", "Default", None, None))

    def test_download_video_from_url_passes_cookie_options(self) -> None:
        temp_path = Path("test_download_workspace").resolve()
        cookie_path = temp_path / "cookies.txt"
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True, exist_ok=True)
        cookie_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        captured_options: list[dict] = []

        class FakeYDL:
            def __init__(self, options):
                self.options = options
                captured_options.append(options)

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                return False

            def extract_info(self, _url, download):
                path = Path(str(self.options["outtmpl"]).replace("%(extractor)s", "Douyin").replace("%(id)s", "456").replace("%(ext)s", "mp4"))
                path.write_bytes(b"video")
                return {"filepath": str(path)}

        try:
            download_video_from_url(
                "https://www.douyin.com/video/456",
                output_dir=str(temp_path),
                ydl_class=FakeYDL,
                cookies_browser="Edge - edge",
                cookies_file=str(cookie_path),
            )
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)

        self.assertEqual(captured_options[0]["cookiesfrombrowser"], ("edge", None, None, None))
        self.assertEqual(captured_options[0]["cookiefile"], str(cookie_path))

    def test_download_video_from_url_explains_fresh_cookie_error(self) -> None:
        class FakeYDL:
            def __init__(self, _options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                return False

            def extract_info(self, _url, download):
                raise RuntimeError("Fresh cookies (not necessarily logged in) are needed")

        with self.assertRaisesRegex(RuntimeError, "choose that browser"):
            download_video_from_url("https://www.douyin.com/video/456", ydl_class=FakeYDL)

    def test_build_output_video_logs_original_voice_removal(self) -> None:
        logs: list[str] = []

        with patch("pipeline.merge_audio_to_video", return_value=("out.mp4", False)) as merge_mock:
            output_path, video_extended = build_output_video(
                "clip.mp4",
                "voice.mp3",
                output_file="out.mp4",
                logger=logs.append,
            )

        self.assertEqual(output_path, "out.mp4")
        self.assertFalse(video_extended)
        self.assertIn("removing original voice", logs[0].lower())
        merge_mock.assert_called_once_with(
            "clip.mp4",
            "voice.mp3",
            output_file="out.mp4",
            keep_original_audio=False,
            preserve_background_audio=True,
            original_volume=DEFAULT_BACKGROUND_VOLUME,
            logger=logs.append,
        )

    def test_build_output_video_can_remove_all_original_audio(self) -> None:
        logs: list[str] = []

        with patch("pipeline.merge_audio_to_video", return_value=("out.mp4", False)) as merge_mock:
            build_output_video(
                "clip.mp4",
                "voice.mp3",
                output_file="out.mp4",
                preserve_background_audio=False,
                logger=logs.append,
            )

        self.assertIn("removing original video audio", logs[0].lower())
        merge_mock.assert_called_once_with(
            "clip.mp4",
            "voice.mp3",
            output_file="out.mp4",
            keep_original_audio=False,
            preserve_background_audio=False,
            original_volume=DEFAULT_BACKGROUND_VOLUME,
            logger=logs.append,
        )

    def test_build_output_video_logs_original_audio_mix(self) -> None:
        logs: list[str] = []

        with patch("pipeline.merge_audio_to_video", return_value=("out.mp4", False)) as merge_mock:
            build_output_video(
                "clip.mp4",
                "voice.mp3",
                output_file="out.mp4",
                keep_original_audio=True,
            original_volume=0.25,
            logger=logs.append,
        )

        self.assertIn("mixing narration with original audio", logs[0].lower())
        merge_mock.assert_called_once_with(
            "clip.mp4",
            "voice.mp3",
            output_file="out.mp4",
            keep_original_audio=True,
            preserve_background_audio=False,
            original_volume=0.25,
            logger=logs.append,
        )

    def test_build_output_video_can_disable_video_extension(self) -> None:
        logs: list[str] = []

        with patch("pipeline.merge_audio_to_video", return_value=("out.mp4", False)) as merge_mock:
            build_output_video(
                "clip.mp4",
                "voice.mp3",
                output_file="out.mp4",
                extend_to_narration=False,
                logger=logs.append,
            )

        merge_mock.assert_called_once_with(
            "clip.mp4",
            "voice.mp3",
            output_file="out.mp4",
            keep_original_audio=False,
            preserve_background_audio=True,
            original_volume=DEFAULT_BACKGROUND_VOLUME,
            logger=logs.append,
            extend_to_narration=False,
        )

    def test_remove_center_voice_uses_stereo_phase_cancellation_filter(self) -> None:
        class Completed:
            returncode = 0
            stderr = ""

        with (
            patch("pipeline.ffmpeg_executable", return_value="ffmpeg"),
            patch("pipeline.subprocess.run", return_value=Completed()) as run_mock,
        ):
            result = remove_center_voice_from_video_audio("clip.mp4", "voice_removed.wav")

        self.assertEqual(result, "voice_removed.wav")
        command = run_mock.call_args.args[0]
        self.assertIn("-vn", command)
        self.assertIn("pan=stereo|c0=c0-c1|c1=c1-c0,volume=0.5", command)

    def test_build_faster_whisper_init_options_uses_cpu(self) -> None:
        options = build_faster_whisper_init_options()
        self.assertEqual(options["device"], "cpu")
        self.assertEqual(options["compute_type"], "int8")

    def test_build_faster_whisper_transcribe_options_reduce_repetition(self) -> None:
        options = build_faster_whisper_transcribe_options("en")
        self.assertEqual(options["task"], "transcribe")
        self.assertEqual(options["language"], "en")
        self.assertEqual(options["beam_size"], 5)
        self.assertEqual(options["no_repeat_ngram_size"], 3)
        self.assertFalse(options["condition_on_previous_text"])
        self.assertTrue(options["vad_filter"])

    def test_configure_hf_environment_sets_token(self) -> None:
        original_hf_token = os.environ.get("HF_TOKEN")
        original_hf_hub_token = os.environ.get("HUGGING_FACE_HUB_TOKEN")
        try:
            configure_hf_environment("test-token")
            self.assertEqual(os.environ.get("HF_TOKEN"), "test-token")
            self.assertEqual(os.environ.get("HUGGING_FACE_HUB_TOKEN"), "test-token")
        finally:
            if original_hf_token is None:
                os.environ.pop("HF_TOKEN", None)
            else:
                os.environ["HF_TOKEN"] = original_hf_token
            if original_hf_hub_token is None:
                os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
            else:
                os.environ["HUGGING_FACE_HUB_TOKEN"] = original_hf_hub_token

    def test_build_transcript_repair_prompt_mentions_rules(self) -> None:
        prompt = build_transcript_repair_prompt("hello world", "en-US")
        self.assertIn("Do not translate", prompt)
        self.assertIn("en-US", prompt)
        self.assertIn("hello world", prompt)

    def test_clean_ollama_response_strips_code_fence(self) -> None:
        self.assertEqual(clean_ollama_response("```text\nhello\n```"), "hello")

    def test_parse_subtitle_text_handles_webvtt(self) -> None:
        contents = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello there\n\n00:00:02.000 --> 00:00:04.500\nGeneral Kenobi\n"
        segments = parse_subtitle_text(contents)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].text, "Hello there")
        self.assertEqual(segments[1].text, "General Kenobi")

    def test_clean_subtitle_ocr_text_normalizes_spacing(self) -> None:
        self.assertEqual(clean_subtitle_ocr_text("  with   a cow’s  "), "with a cow's")
        self.assertEqual(clean_subtitle_ocr_text("..."), "")

    def test_load_sidecar_transcript_prefers_matching_file(self) -> None:
        temp_path = Path("test_sidecar_workspace").resolve()
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            video_path = temp_path / "clip.mp4"
            subtitle_path = temp_path / "clip.en.srt"
            video_path.write_bytes(b"video")
            subtitle_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nFirst line\n\n2\n00:00:01,000 --> 00:00:02,000\nSecond line\n",
                encoding="utf-8",
            )

            loaded = load_sidecar_transcript(str(video_path))
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        text, segments, found_path = loaded
        self.assertEqual(text, "First line\nSecond line")
        self.assertEqual(len(segments), 2)
        self.assertEqual(found_path.name, "clip.en.srt")

    def test_cleanup_transcript_segments_drops_repeated_lines(self) -> None:
        segments = [
            SubtitleSegment(start=0.0, end=1.0, text="If you take out your stomach and replace it with a house"),
            SubtitleSegment(start=1.0, end=2.0, text="Just like a cow or a hen, it would swell the size of a water heap"),
            SubtitleSegment(start=2.0, end=3.0, text="If you take out your stomach and replace it with a house"),
        ]

        cleaned = cleanup_transcript_segments(segments)

        self.assertEqual(len(cleaned), 2)
        self.assertEqual(cleaned[0].text, segments[0].text)
        self.assertEqual(cleaned[1].text, segments[1].text)

    def test_repeated_ngram_ratio_detects_looping_text(self) -> None:
        text = (
            "if you take out your stomach and replace it with a cow's "
            "if you take out your stomach and replace it with a cow's"
        )
        self.assertGreater(repeated_ngram_ratio(text, n=5), 0.2)

    def test_transcript_looks_low_quality_flags_repetition(self) -> None:
        segments = [
            SubtitleSegment(start=0.0, end=5.0, text="If you take out your stomach and replace it with a house"),
            SubtitleSegment(start=5.0, end=10.0, text="Do you think you can digest grass just like a cow or a hen"),
            SubtitleSegment(start=10.0, end=15.0, text="If you take out your stomach and replace it with a house"),
        ]
        text = "\n".join(segment.text for segment in segments)
        self.assertTrue(transcript_looks_low_quality(text, segments, total_duration=15.0))

    def test_looks_like_low_coverage_flags_short_dropped_transcript(self) -> None:
        segments = [
            SubtitleSegment(start=0.0, end=5.3, text="subtitles in Khmer voice"),
        ]

        self.assertTrue(looks_like_low_coverage(segments, total_duration=5.3))

    def test_should_use_candidate_transcript_prefers_better_coverage(self) -> None:
        current = [
            SubtitleSegment(start=0.0, end=5.3, text="subtitles in Khmer voice"),
        ]
        candidate = [
            SubtitleSegment(
                start=0.0,
                end=5.3,
                text="Welcome to Cambodia this tool creates subtitles in Khmer voice",
            ),
        ]

        self.assertTrue(should_use_candidate_transcript(current, candidate))

    def test_google_fallback_guard_handles_auto_language_safely(self) -> None:
        self.assertTrue(should_try_google_speech_fallback("auto", "subtitles in Khmer voice"))
        self.assertFalse(should_try_google_speech_fallback("auto", "你好世界"))
        self.assertTrue(should_try_google_speech_fallback("zh-CN", "你好世界"))

    def test_ocr_samples_to_segments_merges_repeated_samples(self) -> None:
        samples = [
            (0.5, "with a cow's"),
            (1.5, "with a cow's"),
            (2.5, "digest grass?"),
            (3.5, "digest grass?"),
        ]

        segments = ocr_samples_to_segments(samples, interval=1.0, total_duration=4.0)

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].text, "with a cow's")
        self.assertEqual(segments[0].start, 0.0)
        self.assertEqual(segments[0].end, 2.0)
        self.assertEqual(segments[1].text, "digest grass?")
        self.assertEqual(segments[1].start, 2.0)
        self.assertEqual(segments[1].end, 4.0)

    def test_should_use_ocr_transcript_prefers_cleaner_subtitles(self) -> None:
        current_segments = [
            SubtitleSegment(start=0.0, end=5.0, text="If you take out your stomach and replace it with house"),
            SubtitleSegment(start=5.0, end=10.0, text="If you take out your stomach and replace it with house"),
        ]
        current_text = "\n".join(segment.text for segment in current_segments)
        ocr_segments = [
            SubtitleSegment(start=0.0, end=5.0, text="If you take out your stomach and replace it with a cow's"),
            SubtitleSegment(start=5.0, end=10.0, text="Do you think you can digest grass?"),
        ]
        ocr_text = "\n".join(segment.text for segment in ocr_segments)

        self.assertTrue(
            should_use_ocr_transcript(
                current_text,
                current_segments,
                ocr_text,
                ocr_segments,
                ocr_coverage=0.8,
            )
        )

    def test_load_sidecar_transcript_ignores_generated_outputs(self) -> None:
        temp_path = Path("test_sidecar_workspace").resolve()
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            video_path = temp_path / "clip.mp4"
            generated_path = temp_path / "clip_subtitles_original.srt"
            video_path.write_bytes(b"video")
            generated_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nWrong script\n",
                encoding="utf-8",
            )

            loaded = load_sidecar_transcript(str(video_path))
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)

        self.assertIsNone(loaded)

    def test_find_original_video_for_generated_output_uses_sibling_source(self) -> None:
        temp_path = Path("test_generated_output_workspace").resolve()
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            source_path = temp_path / "clip.mp4"
            generated_path = temp_path / "clip_final_output.mp4"
            source_path.write_bytes(b"source")
            generated_path.write_bytes(b"generated")

            found = find_original_video_for_generated_output(generated_path)
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)

        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.name, "clip.mp4")

    def test_resolve_generated_output_config_switches_to_source_video(self) -> None:
        temp_path = Path("test_generated_output_workspace").resolve()
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            source_path = temp_path / "clip.mp4"
            generated_path = temp_path / "clip_final_output.mp4"
            source_path.write_bytes(b"source")
            generated_path.write_bytes(b"generated")
            messages: list[str] = []

            resolved = resolve_generated_output_config(
                WorkflowConfig(video=str(generated_path)),
                logger=messages.append,
            )
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)

        self.assertEqual(Path(resolved.video).name, "clip.mp4")
        self.assertTrue(any("using original source video" in message for message in messages))

    def test_split_script_for_timed_segments_uses_existing_lines(self) -> None:
        reference_segments = [
            SubtitleSegment(start=0.0, end=1.5, text="first"),
            SubtitleSegment(start=1.5, end=3.0, text="second"),
        ]

        chunks = split_script_for_timed_segments("Khmer line one\nKhmer line two", reference_segments)

        self.assertEqual(chunks, ["Khmer line one", "Khmer line two"])

    def test_split_script_for_timed_segments_proportionally_splits_paragraph(self) -> None:
        reference_segments = [
            SubtitleSegment(start=0.0, end=1.0, text="first"),
            SubtitleSegment(start=1.0, end=4.0, text="second"),
        ]

        text = "one two three four five six seven eight"
        chunks = split_script_for_timed_segments(text, reference_segments)

        self.assertIsNotNone(chunks)
        assert chunks is not None
        self.assertEqual(len(chunks), 2)
        self.assertEqual(" ".join(chunks).split(), text.split())
        self.assertGreater(len(chunks[1].split()), len(chunks[0].split()))

    def test_split_script_for_timed_segments_splits_text_without_spaces(self) -> None:
        reference_segments = [
            SubtitleSegment(start=0.0, end=1.0, text="first"),
            SubtitleSegment(start=1.0, end=3.0, text="second"),
            SubtitleSegment(start=3.0, end=4.0, text="third"),
        ]

        chunks = split_script_for_timed_segments("abcdefghij", reference_segments)

        self.assertIsNotNone(chunks)
        assert chunks is not None
        self.assertEqual(len(chunks), 3)
        self.assertEqual("".join(chunks), "abcdefghij")
        self.assertGreater(len(chunks[1]), len(chunks[0]))

    def test_build_timed_voice_segments_force_fits_long_voice_to_original_slots(self) -> None:
        reference_segments = [
            SubtitleSegment(start=0.0, end=1.0, text="first"),
            SubtitleSegment(start=1.0, end=2.0, text="second"),
        ]

        timed_segments = build_timed_voice_segments(
            ["first", "second"],
            reference_segments,
            natural_durations=[4.0, 1.0],
            max_speedup=2.0,
        )

        self.assertEqual(len(timed_segments), 2)
        self.assertAlmostEqual(timed_segments[0].start, 0.0)
        self.assertAlmostEqual(timed_segments[0].end, 0.95)
        self.assertAlmostEqual(timed_segments[1].start, 1.0)
        self.assertAlmostEqual(timed_segments[1].end, 2.0)

    def test_build_timed_voice_segments_can_preserve_natural_limit_when_requested(self) -> None:
        reference_segments = [
            SubtitleSegment(start=0.0, end=1.0, text="first"),
            SubtitleSegment(start=1.0, end=2.0, text="second"),
        ]

        timed_segments = build_timed_voice_segments(
            ["first", "second"],
            reference_segments,
            natural_durations=[4.0, 1.0],
            max_speedup=2.0,
            force_fit_to_timeline=False,
        )

        self.assertAlmostEqual(timed_segments[0].end, 2.0)
        self.assertGreaterEqual(timed_segments[1].start, timed_segments[0].end + 0.05)

    def test_fit_narration_duration_keeps_short_voice_natural(self) -> None:
        segment = SubtitleSegment(start=10.0, end=12.0, text="first")
        next_segment = SubtitleSegment(start=13.0, end=15.0, text="second")

        fitted = fit_narration_duration_to_timeline(1.4, segment, next_segment)

        self.assertEqual(fitted, 1.4)

    def test_fit_narration_duration_limits_speedup_for_long_voice(self) -> None:
        segment = SubtitleSegment(start=10.0, end=12.0, text="first")
        next_segment = SubtitleSegment(start=12.1, end=14.0, text="second")

        fitted = fit_narration_duration_to_timeline(
            6.0,
            segment,
            next_segment,
            max_speedup=1.5,
        )

        self.assertEqual(fitted, 4.0)

    def test_remove_duplicate_prefix_keeps_new_words(self) -> None:
        previous = "could you eat and digest grass just like a cow but"
        current = "like a cow but fart 50 gallons of methane gas every day"
        self.assertEqual(
            remove_duplicate_prefix(previous, current),
            "fart 50 gallons of methane gas every day",
        )

    def test_should_split_duplicate_only_long_result(self) -> None:
        self.assertTrue(
            should_split_transcription_result(
                raw_text="fart 50 gallons of methane gas every day",
                deduped_text="",
                duration=8.0,
                min_chunk_seconds=3.0,
            )
        )

    def test_transcribe_audio_window_splits_duplicate_chunk(self) -> None:
        responses = {
            (0.0, 8.0): "fart 50 gallons of methane gas every day",
            (0.0, 4.0): "fart 50 gallons of methane gas every day",
            (4.0, 4.0): "every day so if everyone on the planet",
        }

        def fake_recognize(_recognizer, _audio_path: str, start: float, duration: float, _speech_lang: str) -> str:
            key = (round(start, 1), round(duration, 1))
            return responses[key]

        segments = transcribe_audio_window(
            audio_path="fake.wav",
            recognizer=object(),  # type: ignore[arg-type]
            start=0.0,
            duration=8.0,
            total_duration=20.0,
            speech_lang="en-US",
            previous_text="could you eat and digest grass just like a cow but fart 50 gallons of methane gas every day",
            min_chunk_seconds=3.0,
            recognize_chunk=fake_recognize,
        )

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].start, 4.0)
        self.assertEqual(segments[0].end, 8.0)
        self.assertEqual(segments[0].text, "so if everyone on the planet")

    def test_build_translated_outputs_uses_full_transcript_for_script(self) -> None:
        source_text = "line one\nline two"
        source_segments = [
            SubtitleSegment(start=0.0, end=1.0, text="line one"),
            SubtitleSegment(start=1.0, end=2.0, text="line two"),
        ]
        translated_segments = [
            SubtitleSegment(start=0.0, end=1.0, text="seg one"),
            SubtitleSegment(start=1.0, end=2.0, text="seg two"),
        ]

        with (
            patch("pipeline.translate_text", return_value="full script") as translate_text_mock,
            patch("pipeline.translate_segments", return_value=translated_segments) as translate_segments_mock,
        ):
            translated_text, timed_segments = build_translated_outputs(source_text, source_segments)

        self.assertEqual(translated_text, "full script")
        self.assertEqual(timed_segments, translated_segments)
        translate_text_mock.assert_called_once_with(
            source_text,
            target_lang="km",
            source_lang="auto",
        )
        translate_segments_mock.assert_called_once_with(
            source_segments,
            target_lang="km",
            source_lang="auto",
        )

    def test_stronger_whisper_model_steps_up_without_jumping_to_large(self) -> None:
        self.assertEqual(stronger_whisper_model("tiny"), "base")
        self.assertEqual(stronger_whisper_model("base"), "small")
        self.assertEqual(stronger_whisper_model("small"), "medium")
        self.assertIsNone(stronger_whisper_model("medium"))
        self.assertIsNone(stronger_whisper_model("large-v3"))

    def test_retry_transcription_with_stronger_whisper_uses_better_result(self) -> None:
        current_segments = [
            SubtitleSegment(start=0.0, end=5.0, text="If you take out your stomach and replace it with a house"),
            SubtitleSegment(start=5.0, end=10.0, text="Do you think you can digest grass just like a cow or a hen"),
            SubtitleSegment(start=10.0, end=15.0, text="If you take out your stomach and replace it with a house"),
        ]
        retried_segments = [
            SubtitleSegment(start=0.0, end=7.5, text="If you take out your stomach and replace it with a cow's"),
            SubtitleSegment(start=7.5, end=15.0, text="Do you think you can digest grass just like a cow or a hen"),
        ]

        with patch("pipeline.transcribe_video_to_segments", return_value=retried_segments) as retry_mock:
            result = retry_transcription_with_stronger_whisper(
                video_file="clip.mp4",
                speech_lang="en-US",
                chunk_seconds=5,
                overlap_seconds=1.2,
                chosen_engine="faster-whisper",
                whisper_model="small",
                current_segments=current_segments,
            )

        self.assertEqual(result, retried_segments)
        retry_mock.assert_called_once()

    def test_retry_transcription_with_stronger_whisper_does_not_upgrade_medium(self) -> None:
        current_segments = [
            SubtitleSegment(start=0.0, end=5.0, text="same repeated words same repeated words"),
            SubtitleSegment(start=5.0, end=10.0, text="same repeated words same repeated words"),
        ]

        with patch("pipeline.transcribe_video_to_segments") as retry_mock:
            result = retry_transcription_with_stronger_whisper(
                video_file="clip.mp4",
                speech_lang="en-US",
                chunk_seconds=5,
                overlap_seconds=1.2,
                chosen_engine="faster-whisper",
                whisper_model="medium",
                current_segments=current_segments,
            )

        self.assertEqual(result, current_segments)
        retry_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
