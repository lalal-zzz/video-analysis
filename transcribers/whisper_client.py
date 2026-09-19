"""Whisper 转录客户端 — 支持 YouTube、Bilibili、Douyin 音频下载。"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import httpx

from exceptions import TranscriberError
from models.transcript import TranscriptSegment, VideoTranscript
from models.video import VideoMetadata
from transcribers.base import BaseTranscriber


class WhisperClient(BaseTranscriber):
    def __init__(
        self,
        model_name: str = "whisper-large-v3",
        device: str = "cpu",
        language: str = "zh",
        download_dir: str | None = None,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._language = language
        self._download_dir = (
            Path(download_dir) if download_dir else Path("/tmp/whisper_downloads")
        )
        self._download_dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.AsyncClient(timeout=300.0, follow_redirects=True)
        self._model: Any = None

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
        self._lazy_load_model()

        audio_path = await self._download_audio(video)
        if audio_path is None:
            raise TranscriberError(
                f"Failed to download audio for {video.video_id}"
            )

        try:
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

    async def supports(self, video: VideoMetadata) -> bool:
        return True

    async def _download_audio(self, video: VideoMetadata) -> Path | None:
        if video.platform == "youtube":
            return await self._download_youtube_audio(video.video_id)

        if video.platform == "bilibili":
            audio_url = await self._resolve_bilibili_audio(video.video_id)
            if audio_url:
                return await self._download_url(audio_url, video.video_id)

        if video.platform == "douyin":
            return await self._download_douyin_audio(video)

        return None

    async def _download_youtube_audio(self, video_id: str) -> Path | None:
        try:
            import yt_dlp
        except ImportError:
            raise TranscriberError("yt-dlp is required. Run: pip install yt-dlp")

        output_path = self._download_dir / f"{video_id}.mp3"
        if output_path.exists():
            return output_path

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(output_path.with_suffix("")),
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
            ],
            "quiet": True,
            "no_warnings": True,
        }
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(ydl_opts).download(
                    [f"https://www.youtube.com/watch?v={video_id}"]
                ),
            )
            mp3_path = output_path.with_suffix(".mp3")
            if mp3_path.exists():
                return mp3_path
            if output_path.exists():
                return output_path
        except Exception as e:
            raise TranscriberError(f"yt-dlp download failed: {e}") from e
        return None

    async def _resolve_bilibili_audio(self, video_id: str) -> str | None:
        info_url = f"https://api.bilibili.com/x/web-interface/view?bvid={video_id}"
        try:
            resp = await self._http.get(
                info_url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.bilibili.com/",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                return None

            cid = data["data"]["cid"]
            play_url = (
                f"https://api.bilibili.com/x/player/playurl?"
                f"bvid={video_id}&cid={cid}&qn=16&type=mp4"
            )
            play_resp = await self._http.get(
                play_url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.bilibili.com/",
                },
            )
            play_resp.raise_for_status()
            play_data = play_resp.json()
            if play_data.get("code") != 0:
                return None

            audio_urls = play_data["data"].get("durl", [])
            if audio_urls:
                return audio_urls[0].get("url")
        except Exception:
            pass
        return None

    async def _download_douyin_audio(self, video: VideoMetadata) -> Path | None:
        """下载抖音视频音频。

        策略：
        1. 如果安装了 dy-cli，通过 subprocess 调用它下载
        2. 否则，尝试通过 Douyin API 直接解析视频流 URL 并下载
        """
        # 策略 1: 尝试使用 dy-cli
        audio_path = await self._download_douyin_via_dycli(video)
        if audio_path is not None:
            return audio_path

        # 策略 2: 尝试直接解析视频流
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

    async def _download_url(self, url: str, video_id: str) -> Path | None:
        output_path = self._download_dir / f"{video_id}.mp3"
        if output_path.exists():
            return output_path

        try:
            resp = await self._http.get(url)
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