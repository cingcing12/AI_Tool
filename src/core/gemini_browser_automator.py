"""
Automated Gemini Browser Translation Engine
Launches Chrome, navigates to gemini.google.com, enters the drama prompt,
waits for the translation, extracts the result, and returns it automatically.
"""

from __future__ import annotations

import os
import re
import time
from typing import Callable, List, Optional
from .dubbing_engine import (
    TimedSubtitle,
    clean_chinese_drama_text,
    format_gemini_drama_prompt,
    parse_gemini_translations
)


class GeminiBrowserAutomator:
    """Automates Google Gemini Web interface for zero-API-key subtitle translation."""

    def __init__(self, temp_dir: str, headless: bool = False):
        self.temp_dir = os.path.abspath(temp_dir)
        self.headless = headless
        self.profile_dir = os.path.abspath(os.path.join(self.temp_dir, "gemini_chrome_profile"))
        os.makedirs(self.profile_dir, exist_ok=True)

    def translate_subtitles_auto(
        self,
        segments: List[TimedSubtitle],
        funny_mode: bool = False,
        on_status: Optional[Callable[[str, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> List[str]:
        """
        Fully automated translation via Chrome browser to gemini.google.com.
        Opens Chrome, submits prompt, waits for response, extracts translated lines.
        """
        if not segments:
            return []

        if cancel_check and cancel_check():
            raise InterruptedError("Translation cancelled before start.")

        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        if on_status:
            on_status("Launching Chrome browser for Gemini translation...", 26)

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-data-dir={self.profile_dir}")
        options.add_argument("--remote-debugging-pipe")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        options.add_argument("--window-size=1280,850")

        # Exclude automation flags to prevent bot detection
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        driver = None
        results: List[str] = [""] * len(segments)

        # Batch size of 40 lines ensures high Gemini accuracy without truncation
        batch_size = 40

        try:
            driver = webdriver.Chrome(options=options)

            for start_idx in range(0, len(segments), batch_size):
                if cancel_check and cancel_check():
                    raise InterruptedError("Translation cancelled by user.")

                chunk = segments[start_idx:start_idx + batch_size]
                prompt = format_gemini_drama_prompt(chunk, funny_mode=funny_mode)

                if on_status:
                    pct = 28 + int((start_idx / max(1, len(segments))) * 12)
                    on_status(f"Navigating to Gemini Web ({start_idx + 1}-{min(len(segments), start_idx + len(chunk))}/{len(segments)})...", pct)

                driver.get("https://gemini.google.com/app")

                # Wait for input editor to load (up to 15 seconds)
                editor = None
                for _ in range(30):
                    if cancel_check and cancel_check():
                        raise InterruptedError("Translation cancelled by user.")
                    editors = driver.find_elements(By.CSS_SELECTOR, "div.ql-editor, rich-textarea div[contenteditable='true'], div[role='textbox']")
                    if editors:
                        editor = editors[0]
                        break
                    time.sleep(0.5)

                if not editor:
                    raise RuntimeError("Could not find Gemini text input area. Please check internet connection or sign in if prompted.")

                if on_status:
                    on_status("Submitting script to Gemini in browser...", 32)

                # Focus and enter prompt into Gemini's editor
                editor.click()
                time.sleep(0.3)

                # Fast injection via JavaScript execCommand for instant insertion
                try:
                    driver.execute_script("""
                        const el = arguments[0];
                        el.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('insertText', false, arguments[1]);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    """, editor, prompt)
                except Exception:
                    pass

                # If text wasn't inserted by execCommand, fall back to send_keys
                current_val = editor.text.strip()
                if len(current_val) < 10:
                    editor.send_keys(prompt)

                time.sleep(0.8)

                # Click Send button
                send_buttons = driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Send'], button[aria-label*='send'], button.send-button")
                if send_buttons:
                    driver.execute_script("arguments[0].click();", send_buttons[0])
                else:
                    editor.send_keys(Keys.ENTER)

                if on_status:
                    on_status("Gemini is translating in browser... Waiting for completion...", 34)

                # Wait for generation to complete (monitor stop button and content stabilization)
                time.sleep(2.0)
                last_text_len = 0
                stable_cycles = 0
                extracted_chunk_text = ""

                for _ in range(60):  # Maximum 60 seconds wait per batch
                    if cancel_check and cancel_check():
                        raise InterruptedError("Translation cancelled by user.")

                    time.sleep(1.0)
                    stop_btns = driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Stop'], button[aria-label*='stop']")
                    res_els = driver.find_elements(By.CSS_SELECTOR, "model-response, message-content, .markdown")

                    if res_els:
                        curr_txt = res_els[-1].text.strip()
                        curr_len = len(curr_txt)
                        if curr_len > 10:
                            if not stop_btns:
                                if curr_len == last_text_len:
                                    stable_cycles += 1
                                    if stable_cycles >= 2:
                                        extracted_chunk_text = curr_txt
                                        break
                                else:
                                    stable_cycles = 0
                            last_text_len = curr_len

                if not extracted_chunk_text:
                    # Final attempt to grab text
                    res_els = driver.find_elements(By.CSS_SELECTOR, "model-response, message-content, .markdown")
                    if res_els:
                        extracted_chunk_text = res_els[-1].text.strip()

                if on_status:
                    on_status("Extracting translated Khmer dialogue from browser...", 38)

                parsed_lines = parse_gemini_translations(extracted_chunk_text, len(chunk))
                for j, trans_line in enumerate(parsed_lines):
                    results[start_idx + j] = trans_line

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        return results
