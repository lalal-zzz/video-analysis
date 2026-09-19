"""Whisper 转录客户端 — 支持 YouTube、Bilibili、Douyin 音频下载。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir
from typing import Any

import httpx

from exceptions import TranscriberError
from models.transcript import TranscriptSegment, VideoTranscript
from models.video import VideoMetadata
from transcribers.base import BaseTranscriber

logger = logging.getLogger(__name__)


class WhisperClient(BaseTranscriber):
    def __init__(
        self,
        model_name: str = "base",
        device: str = "cpu",
        language: str | None = None,
        download_dir: str | None = None,
        load_cookies: bool = True,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._language = language
        self._download_dir = (
            Path(download_dir) if download_dir else Path(gettempdir()) / "video-analysis-audio"
        )
        self._download_dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.AsyncClient(timeout=300.0, follow_redirects=True)
        self._platform_cookies: dict[str, dict[str, str]] = {}
        if load_cookies:
            self._load_platform_cookies()
        self._model: Any = None
        # One model instance is shared by a batch. Downloads may run concurrently,
        # but Whisper inference is serialized to avoid model/GPU thread-safety issues.
        self._transcribe_lock = asyncio.Lock()

    def _load_platform_cookies(self) -> None:
        """Reuse web-login cookies for protected platform media requests."""
        for platform in ("bilibili", "douyin"):
            cookie_file = Path("data") / f"{platform}_cookies.json"
            if not cookie_file.exists():
                continue
            try:
                cookies = json.loads(cookie_file.read_text(encoding="utf-8")).get("cookies", {})
                self._platform_cookies[platform] = {
                    str(name): str(value) for name, value in cookies.items() if value
                }
                for name, value in cookies.items():
                    self._http.cookies.set(name, value, domain=f".{platform}.com", path="/")
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Could not load %s cookies for media download: %s", platform, exc)

    def _lazy_load_model(self) -> None:
        if self._model is not None:
            return
        try:
            import whisper
        except ImportError:
            raise TranscriberError(
                "openai-whisper is not installed. Run: pip install openai-whisper"
            )
        self._model = whisper.load_model(self._model_name, device=self._device)

    async def get_transcript(self, video: VideoMetadata) -> VideoTranscript:
        audio_path = await self._download_audio(video)
        if audio_path is None:
            raise TranscriberError(
                f"Failed to download audio for {video.video_id}"
            )

        try:
            async with self._transcribe_lock:
                await asyncio.to_thread(self._lazy_load_model)
                result = await self._transcribe(audio_path)
        except Exception as e:
            raise TranscriberError(
                f"Whisper transcription failed for {video.video_id}: {e}"
            ) from e
        finally:
            audio_path.unlink(missing_ok=True)

        segments = [
            TranscriptSegment(
                start=seg["start"], end=seg["end"], text=seg["text"].strip()
            )
            for seg in result.get("segments", [])
            if seg.get("text", "").strip()
        ]

        transcript = VideoTranscript(
            video=video,
            segments=segments,
            source="whisper",
        )
        transcript.build_full_text()
        return transcript

    async def transcribe_file(self, video: VideoMetadata, path: Path) -> VideoTranscript:
        """Transcribe managed media without re-downloading or deleting the source."""
        async with self._transcribe_lock:
            await asyncio.to_thread(self._lazy_load_model)
            result = await self._transcribe(path)
        transcript = VideoTranscript(video=video, source="whisper", segments=[
            TranscriptSegment(start=s["start"], end=s["end"], text=s["text"].strip())
            for s in result.get("segments", []) if s.get("text", "").strip()
        ])
        transcript.build_full_text()
        if not transcript.full_text:
            transcript.full_text = result.get("text", "").strip()
        return transcript

    async def supports(self, video: VideoMetadata) -> bool:
        return True

    async def _download_audio(self, video: VideoMetadata) -> Path | None:
        if video.platform == "youtube":
            return await self._download_youtube_audio(video.video_id)

        if video.platform == "bilibili":
            audio_url = await self._resolve_bilibili_audio(video.video_id)
            if audio_url:
                downloaded = await self._download_url(
                    audio_url, f"bilibili_{video.video_id}", headers=self._bilibili_headers()
                )
                if downloaded is not None:
                    return downloaded
            try:
                return await self._download_with_ytdlp(
                    video.url,
                    f"bilibili_{video.video_id}",
                    platform="bilibili",
                )
            except TranscriberError as exc:
                logger.warning("Bilibili download fallback failed for %s: %s", video.video_id, exc)
                return None

        if video.platform == "douyin":
            return await self._download_douyin_audio(video)

        return None

    async def _download_youtube_audio(self, video_id: str) -> Path | None:
        """Download the best available audio stream without requiring ffmpeg."""
        return await self._download_with_ytdlp(
            f"https://www.youtube.com/watch?v={video_id}", video_id, is_youtube=True
        )

    async def _download_with_ytdlp(
        self,
        url: str,
        output_stem: str,
        *,
        is_youtube: bool = False,
        platform: str = "",
    ) -> Path | None:
        """Download a media stream and return its actual file type.

        Whisper accepts WebM/M4A/MP4 directly, so forcing an MP3 conversion only
        adds an unnecessary ffmpeg dependency during download.
        """
        try:
            import yt_dlp
        except ImportError:
            raise TranscriberError("yt-dlp is required. Run: pip install yt-dlp")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(self._download_dir / f"{output_stem}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "overwrites": True,
        }
        generated_cookie_file: Path | None = None
        cookie_file = os.getenv("YTDLP_COOKIE_FILE", "")
        if not cookie_file:
            default_cookie_file = Path(__file__).resolve().parents[1] / "data" / "ytdlp_cookies.txt"
            if default_cookie_file.is_file():
                cookie_file = str(default_cookie_file)
        if not cookie_file and platform in self._platform_cookies:
            generated_cookie_file = self._create_cookie_file(
                platform, self._platform_cookies[platform]
            )
            cookie_file = str(generated_cookie_file)
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file
        browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "")
        if browser and not cookie_file:
            ydl_opts["cookiesfrombrowser"] = (browser,)
        if is_youtube:
            po_token = os.getenv("YTDLP_PO_TOKEN", "")
            if po_token:
                ydl_opts["extractor_args"] = {"youtube": {"po_token": [po_token]}}
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]),
            )
            files = [
                path for path in self._download_dir.glob(f"{output_stem}.*")
                if path.suffix not in {".part", ".ytdl"} and path.is_file()
            ]
            if files:
                return max(files, key=lambda path: path.stat().st_mtime)
        except Exception as e:
            cookie_hint = (
                " Import a Netscape cookie file at /download-cookies, or configure "
                "YTDLP_COOKIE_FILE."
                if is_youtube or platform == "douyin" else ""
            )
            raise TranscriberError(f"yt-dlp download failed: {e}.{cookie_hint}") from e
        finally:
            if generated_cookie_file is not None:
                generated_cookie_file.unlink(missing_ok=True)
        return None

    def _create_cookie_file(self, platform: str, cookies: dict[str, str]) -> Path:
        """Create a short-lived Netscape cookie file for yt-dlp."""
        domain = ".bilibili.com" if platform == "bilibili" else ".douyin.com"
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".cookies.txt",
            prefix=f"{platform}_",
            dir=self._download_dir,
            delete=False,
        ) as handle:
            handle.write("# Netscape HTTP Cookie File\n")
            for name, value in cookies.items():
                handle.write(f"{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")
            return Path(handle.name)

    async def _bootstrap_anonymous_cookies(self, platform: str) -> None:
        """Collect fresh anonymous cookies before falling back to account login."""
        if self._platform_cookies.get(platform):
            return
        home_urls = {
            "bilibili": "https://www.bilibili.com/",
            "douyin": "https://www.douyin.com/",
        }
        url = home_urls.get(platform)
        if not url:
            return
        headers = self._bilibili_headers() if platform == "bilibili" else {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/",
        }
        try:
            await self._http.get(url, headers=headers)
            cookies = {str(name): str(value) for name, value in self._http.cookies.items()}
            if cookies:
                self._platform_cookies[platform] = cookies
        except httpx.HTTPError as exc:
            logger.warning("Could not initialize anonymous %s cookies: %s", platform, exc)

    async def _resolve_bilibili_audio(self, video_id: str) -> str | None:
        info_url = f"https://api.bilibili.com/x/web-interface/view?bvid={video_id}"
        try:
            headers = self._bilibili_headers()
            resp = await self._http.get(info_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                return None

            cid = data["data"]["cid"]
            play_url = (
                f"https://api.bilibili.com/x/player/playurl?"
                f"bvid={video_id}&cid={cid}&qn=16&fnval=16&fourk=1"
            )
            play_resp = await self._http.get(play_url, headers=headers)
            play_resp.raise_for_status()
            play_data = play_resp.json()
            if play_data.get("code") != 0:
                return None

            audio_urls = play_data["data"].get("dash", {}).get("audio", [])
            if audio_urls:
                return audio_urls[0].get("baseUrl") or audio_urls[0].get("base_url")
            durl = play_data["data"].get("durl", [])
            if durl:
                return durl[0].get("url")
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Bilibili audio resolution failed for %s: %s", video_id, exc)
        return None

    @staticmethod
    def _bilibili_headers() -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }

    async def _download_douyin_audio(self, video: VideoMetadata) -> Path | None:
        """下载抖音视频音频。

        策略：dy-cli、yt-dlp，最后才尝试抖音 API。
        """
        # 策略 1: 尝试使用 dy-cli
        audio_path = await self._download_douyin_via_dycli(video)
        if audio_path is not None:
            return audio_path

        # 策略 2: yt-dlp supports Douyin URLs and handles many signature changes.
        try:
            await self._bootstrap_anonymous_cookies("douyin")
            audio_path = await self._download_with_ytdlp(
                video.url, f"douyin_{video.video_id}", platform="douyin"
            )
            if audio_path is not None:
                return audio_path
        except TranscriberError as exc:
            logger.warning("yt-dlp Douyin download failed for %s: %s", video.video_id, exc)

        # 策略 3: 尝试直接解析视频流
        audio_path = await self._download_douyin_via_api(video)
        if audio_path is not None:
            return audio_path

        return None

    async def _download_douyin_via_dycli(self, video: VideoMetadata) -> Path | None:
        """使用 dy-cli 下载抖音视频并提取音频。"""
        try:
            result = subprocess.run(
                ["dy-cli", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # 如果 dy-cli 不可用，静默回退
            if result.returncode != 0:
                return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

        output_path = self._download_dir / f"douyin_{video.video_id}.mp3"
        if output_path.exists():
            return output_path

        try:
            # dy-cli 下载视频
            dl_cmd = [
                "dy-cli",
                "download",
                "--url", video.url,
                "--output", str(self._download_dir),
            ]
            result = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                # 尝试替代语法
                dl_cmd = [
                    "dy-cli",
                    video.url,
                    "-o", str(self._download_dir),
                ]
                result = subprocess.run(
                    dl_cmd, capture_output=True, text=True, timeout=120
                )

            if result.returncode != 0:
                return None

            # 查找下载的视频文件
            video_files = list(self._download_dir.glob("douyin_*.mp4"))
            video_files.extend(self._download_dir.glob("*.mp4"))
            if video_files:
                # 使用 FFmpeg 提取音频
                video_path = video_files[0]
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", str(video_path),
                    "-vn",
                    "-acodec", "libmp3lame",
                    "-y",
                    str(output_path),
                ]
                subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)
                video_path.unlink(missing_ok=True)

                if output_path.exists():
                    return output_path

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    async def _download_douyin_via_api(self, video: VideoMetadata) -> Path | None:
        """通过 Douyin API 直接解析视频流 URL 并下载音频。"""
        try:
            # 使用 DouyinScraper 中的 API 逻辑获取视频详情
            video_id = video.video_id
            detail_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/"
            params = {
                "aweme_id": video_id,
                "version_code": "190400",
                "app_name": "aweme",
            }
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 13; SM-S9080) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/112.0.0.0 Mobile Safari/537.36"
                ),
                "Referer": "https://www.douyin.com/",
            }
            resp = await self._http.get(detail_url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            aweme_data = data.get("aweme_detail", {})
            # 优先使用无水印视频地址
            video_url = None
            video_info = aweme_data.get("video", {})

            # 尝试无水印地址
            play_addr = video_info.get("play_addr", {})
            if play_addr:
                urls = play_addr.get("url_list", [])
                if urls:
                    video_url = urls[0]

            # 尝试有水印地址
            if not video_url:
                urls = video_info.get("play_addr_265", {}).get("url_list", [])
                if urls:
                    video_url = urls[0]

            # 尝试下载链接
            if not video_url:
                urls = video_info.get("download_addr", {}).get("url_list", [])
                if urls:
                    video_url = urls[0]

            if not video_url:
                return None

            # 下载视频并保存
            output_video = self._download_dir / f"douyin_{video_id}.mp4"
            output_audio = self._download_dir / f"douyin_{video_id}.mp3"

            if output_audio.exists():
                return output_audio

            # 直接尝试下载音频流（如果视频 URL 包含音频）
            # 先下载整个视频
            video_resp = await self._http.get(video_url, follow_redirects=True)
            video_resp.raise_for_status()
            output_video.write_bytes(video_resp.content)

            # 使用 FFmpeg 提取音频
            try:
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", str(output_video),
                    "-vn",
                    "-acodec", "libmp3lame",
                    "-y",
                    str(output_audio),
                ]
                subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)
                output_video.unlink(missing_ok=True)

                if output_audio.exists():
                    return output_audio
            except (subprocess.TimeoutExpired, FileNotFoundError):
                output_video.unlink(missing_ok=True)
                return None

        except Exception:
            pass

        return None

    async def _download_url(
        self, url: str, video_id: str, headers: dict[str, str] | None = None
    ) -> Path | None:
        output_path = self._download_dir / f"{video_id}.m4s"
        if output_path.exists():
            return output_path

        try:
            resp = await self._http.get(url, headers=headers)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)
            return output_path
        except Exception:
            return None

    async def _transcribe(self, audio_path: Path) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        options = {"language": self._language, "task": "transcribe"}
        return await loop.run_in_executor(
            None, lambda: self._model.transcribe(str(audio_path), **options)
        )

    async def close(self) -> None:
        await self._http.aclose()
