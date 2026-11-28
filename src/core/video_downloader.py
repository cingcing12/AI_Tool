"""
Video Downloader Module
High-Performance Downloader for Douyin (抖音), TikTok, YouTube, and Web Video URLs,
with watermark-free direct stream extraction and cancellation support.
"""

from __future__ import annotations

import os
import re
import sys
import time
import json
import urllib.request
import urllib.parse
from typing import Callable, Optional

# Ensure bin directory containing ffmpeg.exe is in PATH
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BIN_DIR = os.path.join(_BASE_DIR, "bin")
if os.path.exists(_BIN_DIR) and _BIN_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _BIN_DIR + os.pathsep + os.environ.get("PATH", "")


def clean_video_url(raw_input: str) -> str:
    """Extract clean URL from raw user input or app share text, with Douyin/Hongguo canonicalization."""
    if not raw_input:
        return ""
    text = raw_input.strip()
    match = re.search(r"https?://[^\s<>\"']+", text)
    if match:
        url = match.group(0)
        # Strip trailing punctuation if present
        url = re.sub(r"[,\;।\s\)]+$", "", url)
    else:
        url = text

    # Canonicalize Douyin desktop URLs with modal_id parameter:
    # e.g. https://www.douyin.com/jingxuan?modal_id=7705786150463622454
    # or https://www.douyin.com/recommend?modal_id=...
    modal_match = re.search(r"[?&]modal_id=(\d{15,25})", url)
    if modal_match:
        vid = modal_match.group(1)
        url = f"https://www.douyin.com/video/{vid}"

    return url


def is_hongguo_url(url: str) -> bool:
    """Check if URL points to Hongguo Short Drama (红果短剧)."""
    low = (url or "").lower()
    return "hongguo" in low or "qznovelvod" in low or "fqnovel" in low


def extract_hongguo_ids(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract (series_id, vid) from Hongguo detail or player URLs.
    Example detail: https://www.hongguoduanju.com/detail?series_id=7709114780467858456
    Example player: https://www.hongguoduanju.com/player/7709114780467858456/7709114791150767128
    """
    if not url:
        return None, None
    # Check player route: /player/{series_id}/{vid}
    m_player = re.search(r"/player/(\d{15,25})/(\d{15,25})", url)
    if m_player:
        return m_player.group(1), m_player.group(2)

    # Check detail route: series_id={id}
    m_series = re.search(r"[?&]series_id=(\d{15,25})", url)
    series_id = m_series.group(1) if m_series else None

    # Check if vid or item_id is present in query parameters
    m_vid = re.search(r"[?&](?:vid|item_id)=(\d{15,25})", url)
    vid = m_vid.group(1) if m_vid else None

    # Check generic /detail/{series_id}
    if not series_id:
        m_detail_path = re.search(r"/detail/(\d{15,25})", url)
        if m_detail_path:
            series_id = m_detail_path.group(1)

    return series_id, vid


def load_cookies_as_header(cookie_path: Optional[str], domain_filter: str = "") -> str:
    """
    Parse cookies file into standard HTTP 'Cookie:' header string.
    Supports:
    - Netscape format (tab or space separated)
    - JSON array format from Cookie-Editor extension
    - HTTP 'Cookie: name=value; name2=value2' format
    - Raw key=value lines
    """
    if not cookie_path or not os.path.exists(cookie_path):
        return ""
    pairs = []
    seen_keys = set()
    try:
        with open(cookie_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()

        # 1. Check for JSON array (Cookie-Editor extension format)
        if content.startswith("[") and content.endswith("]"):
            try:
                cookies_json = json.loads(content)
                if isinstance(cookies_json, list):
                    for item in cookies_json:
                        if isinstance(item, dict):
                            name = item.get("name")
                            val = item.get("value")
                            dom = item.get("domain", "")
                            if name and val is not None:
                                if not domain_filter or any(d in dom.lower() for d in ["hongguo", "fqnovel", "snssdk", "bytedance", "douyin"]) or domain_filter.lower() in dom.lower():
                                    if name not in seen_keys:
                                        pairs.append(f"{name}={val}")
                                        seen_keys.add(name)
                    if pairs:
                        return "; ".join(pairs)
            except Exception:
                pass

        # 2. Check for single line with semicolons (e.g. pasted Cookie: header)
        if ";" in content and "\n" not in content:
            raw_c = re.sub(r"^[Cc]ookie:\s*", "", content).strip()
            for part in raw_c.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    k = k.strip()
                    if k and k not in seen_keys:
                        pairs.append(f"{k}={v.strip()}")
                        seen_keys.add(k)
            if pairs:
                return "; ".join(pairs)

        # 3. Netscape or multi-line format
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Check if line contains a full cookie string with semicolons
            if ";" in line:
                raw_c = re.sub(r"^[Cc]ookie:\s*", "", line).strip()
                for part in raw_c.split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k = k.strip()
                        if k and k not in seen_keys:
                            pairs.append(f"{k}={v.strip()}")
                            seen_keys.add(k)
                continue

            # Check tab or multi-space separated (standard Netscape format)
            parts = re.split(r"\t+|\s{2,}", line)
            if len(parts) >= 7:
                dom = parts[0]
                name = parts[5].strip()
                val = parts[6].strip()
                if not domain_filter or any(d in dom.lower() for d in ["hongguo", "fqnovel", "snssdk", "bytedance", "douyin"]) or domain_filter.lower() in dom.lower():
                    if name and name not in seen_keys:
                        pairs.append(f"{name}={val}")
                        seen_keys.add(name)
            elif "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                if k and k not in seen_keys:
                    pairs.append(f"{k}={v.strip()}")
                    seen_keys.add(k)

    except Exception as e:
        print(f"[Cookie Parse Warning]: {e}")

    return "; ".join(pairs)


def check_cookie_file_domain(cookie_path: Optional[str], target_url: str) -> tuple[bool, str]:
    """
    Check if the user-selected cookie file matches the platform of target_url.
    Returns (is_match, detected_domain_name).
    """
    if not cookie_path or not os.path.exists(cookie_path):
        return True, ""
    try:
        with open(cookie_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().lower()
        has_douyin = any(k in content for k in ["douyin.com", "snssdk", "bytedance"])
        has_hongguo = any(k in content for k in ["hongguo", "fqnovel", "qznovel"])

        url_low = target_url.lower()
        if "douyin" in url_low:
            if not has_douyin:
                if has_hongguo:
                    return False, "Hongguo Short Drama (hongguoduanju.com)"
                return False, "Another Website"
        elif "hongguo" in url_low or "fqnovel" in url_low:
            if not has_hongguo:
                if has_douyin:
                    return False, "Douyin (douyin.com)"
                return False, "Another Website"
    except Exception:
        pass
    return True, ""


class VideoDownloader:
    """High-speed video downloader supporting Douyin, TikTok, and web video platforms."""

    def __init__(self, download_dir: Optional[str] = None):
        self.download_dir = download_dir or os.path.join(_BASE_DIR, "temp", "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
        self.ffmpeg_path = os.path.join(_BIN_DIR, "ffmpeg.exe") if os.path.exists(os.path.join(_BIN_DIR, "ffmpeg.exe")) else "ffmpeg"

    def find_cookie_file(self, explicit_path: Optional[str] = None) -> Optional[str]:
        """Find an existing cookies.txt file for yt-dlp or direct stream extractors."""
        if explicit_path and os.path.exists(explicit_path) and os.path.getsize(explicit_path) > 10:
            return os.path.abspath(explicit_path)

        candidates = [
            os.path.join(_BASE_DIR, "hongguo_cookies.txt"),
            os.path.join(_BASE_DIR, "cookies.txt"),
            os.path.join(_BASE_DIR, "temp", "cookies.txt"),
            os.path.join(os.path.expanduser("~"), "Downloads", "hongguo_cookies.txt"),
            os.path.join(os.path.expanduser("~"), "Downloads", "cookies.txt")
        ]
        # Inspect recent .txt files in Downloads folder for Netscape cookies (Hongguo or Douyin)
        try:
            dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            if os.path.exists(dl_dir):
                txt_files = sorted(
                    [os.path.join(dl_dir, f) for f in os.listdir(dl_dir) if f.lower().endswith(".txt")],
                    key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
                    reverse=True
                )
                for fpath in txt_files[:25]:
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            snippet = f.read(1024)
                            if "Netscape" in snippet:
                                candidates.insert(0, fpath)
                                break
                    except Exception:
                        pass
        except Exception:
            pass

        for c in candidates:
            if os.path.exists(c) and os.path.getsize(c) > 10:
                return os.path.abspath(c)
        return None

    def is_hongguo_url(self, url: str) -> bool:
        """Check if URL points to Hongguo Short Drama (红果短剧)."""
        return is_hongguo_url(url)

    def is_direct_stream_url(self, url: str) -> bool:
        """Check if URL points directly to a video stream or CDN media file."""
        low = url.lower()
        if any(ext in low for ext in [".mp4", ".m4v", ".webm", ".mov", ".flv", ".ts"]):
            return True
        cdn_keywords = [
            "douyinvod.com", "bytevcloudcdn.com", "snssdk.com", "zijieapi.com",
            "tiktokcdn.com", "googlevideo.com", "fbcdn.net", "akamaihd.net",
            "qznovelvod.com"
        ]
        if any(kw in low for kw in cdn_keywords):
            return True
        return False

    def get_hongguo_series_info(self, series_id: str, cookie_file: Optional[str] = None) -> dict:
        """
        Fetch Hongguo drama series detail metadata from Modern.js SSR payload.
        Returns series title, episode counts, and complete vid_list.
        """
        url = f"https://www.hongguoduanju.com/detail?series_id={series_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Referer": "https://www.hongguoduanju.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        resolved_cookie = self.find_cookie_file(cookie_file)
        if resolved_cookie:
            ck = load_cookies_as_header(resolved_cookie, "hongguo")
            if ck:
                headers["Cookie"] = ck

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        idx = html.find("_ROUTER_DATA")
        if idx == -1:
            raise RuntimeError(f"Could not parse Hongguo series page: _ROUTER_DATA missing for series {series_id}")

        start = html.find("{", idx)
        data, _ = json.JSONDecoder().raw_decode(html[start:])
        loader_data = data.get("loaderData", {})
        detail_data = loader_data.get("detail_page", {}) or loader_data.get("detail_layout", {})
        series_detail = detail_data.get("seriesDetail", {})
        if not series_detail:
            for v in loader_data.values():
                if isinstance(v, dict) and "seriesDetail" in v:
                    series_detail = v["seriesDetail"]
                    break

        series_name = series_detail.get("series_name") or f"Hongguo_Series_{series_id}"
        episode_cnt = int(series_detail.get("episode_cnt") or len(series_detail.get("vid_list") or []))
        accessible_cnt = int(series_detail.get("accessible_episode_cnt") or 5)
        vid_list = series_detail.get("vid_list") or []

        return {
            "series_id": str(series_id),
            "series_name": series_name,
            "episode_cnt": episode_cnt,
            "accessible_episode_cnt": accessible_cnt,
            "vid_list": vid_list,
            "series_cover": series_detail.get("series_cover") or "",
            "series_intro": series_detail.get("series_intro") or ""
        }

    def download_hongguo_episode(
        self,
        series_id: str,
        episode_num: int = 1,
        vid: Optional[str] = None,
        output_dir: Optional[str] = None,
        cookie_file: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        """
        Download a specific episode from Hongguo Short Drama (supports free 1-5 & locked 6+ with cookies).
        """
        if cancel_check and cancel_check():
            raise InterruptedError("Download cancelled before execution.")

        target_dir = output_dir or self.download_dir
        os.makedirs(target_dir, exist_ok=True)

        if on_progress:
            on_progress(f"Fetching Hongguo series info (Series: {series_id})...", 10)

        series_info = self.get_hongguo_series_info(series_id, cookie_file=cookie_file)
        series_name = series_info.get("series_name", "Hongguo_Drama")
        clean_name = re.sub(r'[\\/*?:"<>|]', "", series_name).strip() or f"Hongguo_{series_id}"
        vid_list = series_info.get("vid_list", [])

        # Validate or resolve vid
        if not vid:
            if episode_num < 1:
                episode_num = 1
            if vid_list and episode_num > len(vid_list):
                episode_num = len(vid_list)
            if vid_list and 0 <= episode_num - 1 < len(vid_list):
                vid = vid_list[episode_num - 1]
            else:
                raise ValueError(f"Could not locate episode {episode_num} in Hongguo series {series_id}.")
        else:
            if vid in vid_list:
                episode_num = vid_list.index(vid) + 1

        resolved_cookie_file = self.find_cookie_file(cookie_file)
        player_url = f"https://www.hongguoduanju.com/player/{series_id}/{vid}"

        if on_progress:
            on_progress(f"Resolving Episode {episode_num} of '{clean_name}'...", 20)

        # Check if episode is beyond public limit
        accessible_limit = series_info.get("accessible_episode_cnt", 5)
        is_locked = episode_num > accessible_limit

        if is_locked and not resolved_cookie_file:
            raise RuntimeError(
                f"Hongguo Episode {episode_num} is LOCKED (App / VIP Exclusive).\n\n"
                f"[Guide] How to download locked episodes:\n"
                f"1. Open https://www.hongguoduanju.com in Chrome and log in to your account.\n"
                f"2. Export 'cookies.txt' (using the Chrome extension 'Get cookies.txt LOCALLY').\n"
                f"3. Select your 'cookies.txt' in the 'Cookies File' box and click Download!"
            )

        # 1. Fetch full-length episode stream via official fallback play info API
        # (Delivers the 100% complete full episode duration, unlike the 10s public SEO teaser)
        fallback_api_url = "https://hongguoduanju.com/api/video/protected/fallback-play-info"
        try:
            req_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": f"https://hongguoduanju.com/player/{series_id}/{vid}",
                "Origin": "https://hongguoduanju.com",
                "Content-Type": "application/json"
            }
            if resolved_cookie_file:
                cookie_hdr = load_cookies_as_header(resolved_cookie_file, "hongguo")
                if cookie_hdr:
                    req_headers["Cookie"] = cookie_hdr

            fb_payload = json.dumps({"item_id": str(vid)}).encode("utf-8")
            fb_req = urllib.request.Request(fallback_api_url, data=fb_payload, headers=req_headers, method="POST")

            with urllib.request.urlopen(fb_req, timeout=12) as fb_resp:
                if fb_resp.status == 200:
                    fb_data = json.loads(fb_resp.read().decode("utf-8", errors="ignore"))
                    main_stream = fb_data.get("main_url") or fb_data.get("backup_url")
                    if main_stream:
                        out_filename = f"{clean_name}_EP{episode_num:02d}_{vid}.mp4"
                        if on_progress:
                            on_progress(f"Downloading full episode {episode_num} stream...", 30)
                        downloaded = self._download_direct_stream(
                            main_stream,
                            target_dir,
                            on_progress,
                            cancel_check,
                            custom_filename=out_filename
                        )
                        if downloaded and os.path.exists(downloaded) and os.path.getsize(downloaded) > 100000:
                            return downloaded
        except InterruptedError:
            raise
        except urllib.error.HTTPError as http_err:
            if http_err.code == 403 and is_locked and not resolved_cookie_file:
                raise RuntimeError(
                    f"Hongguo Episode {episode_num} is LOCKED (App / VIP Exclusive).\n\n"
                    f"[Guide] How to download locked episodes:\n"
                    f"1. Open https://www.hongguoduanju.com in Chrome and log in to your account.\n"
                    f"2. Export 'cookies.txt' (using the Chrome extension 'Get cookies.txt LOCALLY').\n"
                    f"3. Select your 'cookies.txt' in the 'Cookies File' box and click Download!"
                )
            print(f"[Hongguo Fallback API Notice]: Episode {episode_num}: HTTP {http_err.code}")
        except Exception as fb_err:
            print(f"[Hongguo Fallback API Notice]: Episode {episode_num}: {fb_err}")

        # 2. Check Modern.js player page with user cookies (required for locked episodes 6+)
        if resolved_cookie_file:
            if on_progress:
                on_progress(f"Authenticating episode {episode_num} with cookies...", 35)
            try:
                cookie_hdr = load_cookies_as_header(resolved_cookie_file, "hongguo")
                player_req = urllib.request.Request(player_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                    "Referer": f"https://www.hongguoduanju.com/detail?series_id={series_id}",
                    "Cookie": cookie_hdr
                })
                with urllib.request.urlopen(player_req, timeout=12) as p_resp:
                    p_html = p_resp.read().decode("utf-8", errors="ignore")

                p_idx = p_html.find("_ROUTER_DATA")
                if p_idx != -1:
                    p_start = p_html.find("{", p_idx)
                    p_data, _ = json.JSONDecoder().raw_decode(p_html[p_start:])
                    p_loader = p_data.get("loaderData", {})
                    p_page = p_loader.get("player_(series_id)/(vid)/page", {})
                    ret_vid = str(p_page.get("vid", ""))
                    # If server fell back to guest vid (episode 1) instead of requested vid, cookies are invalid
                    if ret_vid and ret_vid != str(vid) and is_locked:
                        raise PermissionError("Server returned guest episode. Hongguo cookies are not logged in or expired.")

                    player_info = p_page.get("video_player_info") or {}
                    main_stream = player_info.get("main_url") or player_info.get("backup_url")
                    if main_stream:
                        out_filename = f"{clean_name}_EP{episode_num:02d}_{vid}.mp4"
                        if on_progress:
                            on_progress(f"Downloading unlocked episode {episode_num} stream...", 45)
                        downloaded = self._download_direct_stream(
                            main_stream,
                            target_dir,
                            on_progress,
                            cancel_check,
                            custom_filename=out_filename
                        )
                        if downloaded and os.path.exists(downloaded) and os.path.getsize(downloaded) > 10000:
                            return downloaded
            except InterruptedError:
                raise
            except Exception as auth_err:
                print(f"[Hongguo Auth Notice]: {auth_err}")
                if "cookies are not logged in" in str(auth_err).lower():
                    raise RuntimeError(
                        f"Hongguo Episode {episode_num} could not be unlocked.\n\n"
                        f"The provided cookie file does not have an active login session.\n"
                        f"Please open https://www.hongguoduanju.com in Chrome, sign in, re-export 'cookies.txt', and try again."
                    )

        # 3. Try yt-dlp on player page with cookies (only if not locked or if valid cookies are present)
        if not is_locked or resolved_cookie_file:
            if on_progress:
                on_progress(f"Extracting episode {episode_num} stream via media engine...", 45)
            try:
                downloaded = self._download_with_ytdlp(
                    player_url,
                    target_dir,
                    cookie_file=resolved_cookie_file,
                    on_progress=on_progress,
                    cancel_check=cancel_check
                )
                if downloaded and os.path.exists(downloaded) and os.path.getsize(downloaded) > 10000:
                    desired_name = os.path.join(target_dir, f"{clean_name}_EP{episode_num:02d}_{vid}.mp4")
                    if downloaded != desired_name:
                        try:
                            if os.path.exists(desired_name):
                                os.remove(desired_name)
                            os.rename(downloaded, desired_name)
                            return os.path.abspath(desired_name)
                        except Exception:
                            pass
                    return downloaded
            except InterruptedError:
                raise
            except Exception as yt_err:
                print(f"[Hongguo yt-dlp Notice]: {yt_err}")

        # 4. If failed, determine if episode is locked
        if is_locked and not resolved_cookie_file:
            raise RuntimeError(
                f"Hongguo Episode {episode_num} is LOCKED (App/VIP Exclusive).\n\n"
                f"[Guide] How to download locked episodes:\n"
                f"1. Open https://www.hongguoduanju.com in Chrome and log in to your account.\n"
                f"2. Export 'cookies.txt' (using the free Chrome extension 'Get cookies.txt LOCALLY').\n"
                f"3. Select your 'cookies.txt' file in the Cookies box and click Download!"
            )
        elif is_locked and resolved_cookie_file:
            raise RuntimeError(
                f"Hongguo Episode {episode_num} could not be unlocked with the provided cookie file.\n\n"
                f"Please make sure you are logged in to Hongguo in Chrome when exporting cookies, and that your cookies.txt is fresh."
            )
        else:
            raise RuntimeError(
                f"Could not download Hongguo Episode {episode_num} from '{player_url}'.\n"
                f"Please verify your internet connection and try again."
            )

    def download_hongguo_video(
        self,
        url: str,
        episode_num: Optional[int] = None,
        target_dir: Optional[str] = None,
        cookie_file: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        """Entry point for downloading from Hongguo URL with automatic ID extraction."""
        series_id, vid = extract_hongguo_ids(url)
        if not series_id:
            raise ValueError(f"Could not extract Hongguo series ID from URL: {url}")

        ep = episode_num or 1
        return self.download_hongguo_episode(
            series_id=series_id,
            episode_num=ep,
            vid=vid,
            output_dir=target_dir,
            cookie_file=cookie_file,
            on_progress=on_progress,
            cancel_check=cancel_check
        )

    def download_video(
        self,
        url_or_text: str,
        output_dir: Optional[str] = None,
        cookie_file: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        """
        Download video from Douyin, TikTok, or video URL.
        Returns the absolute filepath of the downloaded MP4 video.
        """
        if cancel_check and cancel_check():
            raise InterruptedError("Download cancelled before execution.")

        target_dir = output_dir or self.download_dir
        os.makedirs(target_dir, exist_ok=True)

        clean_url = clean_video_url(url_or_text)
        if not clean_url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid video URL: '{clean_url}'. Please provide a valid http/https link.")

        if on_progress:
            on_progress("Connecting to video source...", 5)

        # 1. Direct stream check (fastest path: direct MP4 or CDN video stream)
        if self.is_direct_stream_url(clean_url):
            try:
                downloaded = self._download_direct_stream(clean_url, target_dir, on_progress, cancel_check)
                if downloaded and os.path.exists(downloaded) and os.path.getsize(downloaded) > 10000:
                    return downloaded
            except InterruptedError:
                raise
            except Exception as stream_err:
                print(f"[Direct Stream Notice]: {stream_err}. Trying standard extractors...")

        # 2. Hongguo Short Drama (红果短剧)
        if self.is_hongguo_url(clean_url):
            if on_progress:
                on_progress("Connecting to Hongguo Short Drama...", 12)
            return self.download_hongguo_video(
                clean_url,
                target_dir=target_dir,
                cookie_file=cookie_file,
                on_progress=on_progress,
                cancel_check=cancel_check
            )

        # 3. Douyin direct resolver (watermark-free HD stream via dedicated parser)
        if "douyin" in clean_url.lower():
            if on_progress:
                on_progress("Resolving watermark-free Douyin stream...", 15)
            try:
                downloaded = self._download_douyin_direct(clean_url, target_dir, on_progress, cancel_check)
                if downloaded and os.path.exists(downloaded) and os.path.getsize(downloaded) > 10000:
                    return downloaded
            except InterruptedError:
                raise
            except Exception as d_err:
                print(f"[Douyin Direct Notice]: {d_err}")

        # Find available cookies file if any
        resolved_cookie_file = self.find_cookie_file(cookie_file)
        cookie_is_match = True
        cookie_wrong_site = ""
        if resolved_cookie_file:
            cookie_is_match, cookie_wrong_site = check_cookie_file_domain(resolved_cookie_file, clean_url)
            print(f"[Downloader]: Using cookie file '{resolved_cookie_file}' (Platform match: {cookie_is_match})")

        # 4. Try yt-dlp (handles TikTok, YouTube, Bilibili, and 1000+ sites)
        ytdlp_error = None
        try:
            downloaded = self._download_with_ytdlp(
                clean_url,
                target_dir,
                cookie_file=resolved_cookie_file if cookie_is_match else None,
                on_progress=on_progress,
                cancel_check=cancel_check
            )
            if downloaded and os.path.exists(downloaded) and os.path.getsize(downloaded) > 10000:
                return downloaded
        except InterruptedError:
            raise
        except Exception as yt_err:
            ytdlp_error = str(yt_err)
            print(f"[yt-dlp Notice]: {yt_err}")

        # If blocked specifically by Douyin's anti-bot requirement
        if "douyin" in clean_url.lower() and (
            ytdlp_error and ("cookies" in ytdlp_error.lower() or "403" in ytdlp_error)
        ):
            if resolved_cookie_file and not cookie_is_match:
                raise RuntimeError(
                    f"Cookie File Platform Mismatch!\n\n"
                    f"You have selected a cookie file for {cookie_wrong_site}, but the video link you pasted is from Douyin (douyin.com).\n\n"
                    f"Because this cookie file was exported from a different website, Douyin cannot recognize it.\n\n"
                    f"[Solutions for Douyin]:\n"
                    f"1. [Fastest - No cookies required]: In Chrome, play the video on Douyin, right-click the video, and click 'Copy video address' (复制视频地址), then paste that direct link here!\n\n"
                    f"2. [Or]: Open https://www.douyin.com in Chrome, export 'cookies.txt' from Douyin, and select that file in the download dialog."
                )
            else:
                raise RuntimeError(
                    f"Douyin anti-bot protection blocked the automated web page download.\n\n"
                    f"[Solutions]:\n"
                    f"1. [Fastest]: In Chrome, right-click the playing video and click 'Copy video address', then paste that direct link here!\n\n"
                    f"2. [Or]: Export 'cookies.txt' from Chrome while on www.douyin.com (using the free 'Get cookies.txt LOCALLY' extension) and select it in the download dialog."
                )

        raise RuntimeError(
            f"Could not download video from '{clean_url}'.\n"
            "Please make sure the link is public and accessible."
        )

    def _download_direct_stream(
        self,
        url: str,
        target_dir: str,
        on_progress: Optional[Callable[[str, int], None]],
        cancel_check: Optional[Callable[[], bool]],
        custom_filename: Optional[str] = None
    ) -> Optional[str]:
        """Download directly from a media stream or CDN URL."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }
        if "douyin" in url.lower() or "byte" in url.lower() or "snssdk" in url.lower():
            headers["Referer"] = "https://www.douyin.com/"
        elif "hongguo" in url.lower() or "qznovel" in url.lower():
            headers["Referer"] = "https://www.hongguoduanju.com/"

        req = urllib.request.Request(url, headers=headers)
        os.makedirs(target_dir, exist_ok=True)
        ts = int(time.time())
        filename = custom_filename or f"stream_{ts}.mp4"
        out_path = os.path.join(target_dir, filename)

        with urllib.request.urlopen(req, timeout=25) as resp, open(out_path, "wb") as f_out:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 128 * 1024
            while True:
                if cancel_check and cancel_check():
                    raise InterruptedError("Download cancelled by user.")
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f_out.write(chunk)
                downloaded += len(chunk)
                if total > 0 and on_progress:
                    pct = min(98, max(5, int((downloaded / total) * 92)))
                    on_progress(f"Downloading stream: {pct}%", pct)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            return os.path.abspath(out_path)
        return None

    def _download_with_ytdlp(
        self,
        url: str,
        target_dir: str,
        cookie_file: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> Optional[str]:
        """Download using yt-dlp with progress reporting and cancellation."""
        import yt_dlp

        downloaded_filepath = None

        def hook(d):
            nonlocal downloaded_filepath
            if cancel_check and cancel_check():
                raise InterruptedError("Download cancelled by user.")

            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                speed_mb = speed / (1024 * 1024) if speed else 0

                pct = 0
                if total > 0:
                    pct = min(98, max(5, int((downloaded / total) * 90) + 5))

                speed_str = f"{speed_mb:.1f} MB/s" if speed_mb > 0 else "downloading..."
                if on_progress:
                    on_progress(f"Downloading video: {pct}% ({speed_str})", pct)

            elif status == "finished":
                downloaded_filepath = d.get("filename")
                if on_progress:
                    on_progress("Finalizing downloaded video...", 98)

        ydl_opts = {
            "outtmpl": os.path.join(target_dir, "%(title).45s [%(id)s].%(ext)s"),
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": _BIN_DIR if os.path.exists(os.path.join(_BIN_DIR, "ffmpeg.exe")) else None,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Referer": "https://www.douyin.com/"
            }
        }

        if cookie_file and os.path.exists(cookie_file):
            ydl_opts["cookiefile"] = cookie_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                # Resolve final output filename
                expected = ydl.prepare_filename(info)
                # If merged into mp4
                base = os.path.splitext(expected)[0]
                mp4_candidate = base + ".mp4"
                if os.path.exists(mp4_candidate):
                    return os.path.abspath(mp4_candidate)
                if os.path.exists(expected):
                    return os.path.abspath(expected)
                if downloaded_filepath and os.path.exists(downloaded_filepath):
                    return os.path.abspath(downloaded_filepath)

        return None

    def _download_douyin_direct(
        self,
        url: str,
        target_dir: str,
        on_progress: Optional[Callable[[str, int], None]],
        cancel_check: Optional[Callable[[], bool]]
    ) -> Optional[str]:
        """Dedicated watermark-free HD stream resolver for Douyin videos."""
        import requests
        from bs4 import BeautifulSoup

        canonical_url = clean_video_url(url)
        # Follow 302 redirect for mobile short links (e.g. v.douyin.com/xxx)
        if "v.douyin.com" in canonical_url:
            try:
                sess = requests.Session()
                r = sess.get(
                    canonical_url,
                    headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"},
                    allow_redirects=True,
                    timeout=10
                )
                if r.url and "douyin.com" in r.url:
                    canonical_url = r.url
            except Exception as e:
                print(f"[Douyin Short URL Redirect Notice]: {e}")

        item_id = ""
        m = re.search(r"/video/(\d+)", canonical_url) or re.search(r"modal_id=(\d+)", canonical_url)
        if m:
            item_id = m.group(1)
            target_resolve_url = f"https://www.douyin.com/video/{item_id}"
        else:
            target_resolve_url = canonical_url

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        }

        # 1. Resolve direct watermark-free HD MP4 using dedicated Douyin API (SaveTik)
        try:
            if on_progress:
                on_progress("Resolving Douyin video stream...", 15)

            res = requests.post(
                "https://savetik.co/api/ajaxSearch",
                data={"q": target_resolve_url, "lang": "en"},
                headers=headers,
                timeout=12
            )
            if res.status_code == 200:
                html_data = res.json().get("data", "")
                soup = BeautifulSoup(html_data, "html.parser")
                dl_link = None
                for a in soup.find_all("a"):
                    text = a.get_text()
                    if "Download MP4" in text and a.get("href"):
                        dl_link = a["href"]
                        if "HD" in text:
                            break

                if dl_link:
                    ts = int(time.time())
                    out_filename = f"douyin_{item_id or ts}.mp4"
                    out_path = os.path.join(target_dir, out_filename)

                    with requests.get(dl_link, headers=headers, stream=True, timeout=25) as resp:
                        resp.raise_for_status()
                        total = int(resp.headers.get("content-length", 0))
                        downloaded = 0
                        chunk_size = 128 * 1024
                        with open(out_path, "wb") as f_out:
                            for chunk in resp.iter_content(chunk_size):
                                if cancel_check and cancel_check():
                                    raise InterruptedError("Download cancelled by user.")
                                if chunk:
                                    f_out.write(chunk)
                                    downloaded += len(chunk)
                                    if total > 0 and on_progress:
                                        pct = min(98, 15 + int((downloaded / total) * 80))
                                        on_progress(f"Downloading Douyin video: {pct}%", pct)

                    if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
                        return os.path.abspath(out_path)
        except InterruptedError:
            raise
        except Exception as e:
            print(f"[Douyin Direct SaveTik Notice]: {e}")

        # 2. Try TikWM resolver
        try:
            res_tw = requests.post(
                "https://www.tikwm.com/api/",
                data={"url": target_resolve_url, "hd": 1},
                headers=headers,
                timeout=12
            )
            if res_tw.status_code == 200:
                tw_data = res_tw.json()
                if tw_data.get("code") == 0 and "data" in tw_data:
                    dl_link = tw_data["data"].get("play") or tw_data["data"].get("wmplay")
                    if dl_link:
                        if dl_link.startswith("/"):
                            dl_link = "https://www.tikwm.com" + dl_link
                        ts = int(time.time())
                        out_filename = f"douyin_{item_id or ts}.mp4"
                        out_path = os.path.join(target_dir, out_filename)
                        with requests.get(dl_link, headers=headers, stream=True, timeout=25) as resp:
                            resp.raise_for_status()
                            total = int(resp.headers.get("content-length", 0))
                            downloaded = 0
                            with open(out_path, "wb") as f_out:
                                for chunk in resp.iter_content(128 * 1024):
                                    if cancel_check and cancel_check():
                                        raise InterruptedError("Download cancelled by user.")
                                    if chunk:
                                        f_out.write(chunk)
                                        downloaded += len(chunk)
                                        if total > 0 and on_progress:
                                            pct = min(98, 15 + int((downloaded / total) * 80))
                                            on_progress(f"Downloading Douyin video: {pct}%", pct)
                        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
                            return os.path.abspath(out_path)
        except InterruptedError:
            raise
        except Exception as tw_err:
            print(f"[Douyin TikWM Notice]: {tw_err}")

        return None
