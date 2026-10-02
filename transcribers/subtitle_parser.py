import asyncio
import html
import re
import tempfile
from typing import Any
from pathlib import Path

import httpx

from exceptions import TranscriberError
from models.transcript import TranscriptSegment, VideoTranscript
from models.video import VideoMetadata
from transcribers.base import BaseTranscriber


class SubtitleParser(BaseTranscriber):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def get_transcript(self, video: VideoMetadata) -> VideoTranscript:
        if video.platform == "youtube":
            return await self._from_youtube(video)
        raise TranscriberError(f"Subtitle parsing not supported for platform: {video.platform}")

    async def supports(self, video: VideoMetadata) -> bool:
        return video.platform in ("youtube",)

    async def _from_youtube(self, video: VideoMetadata) -> VideoTranscript:
        try:
            segments = await self._fetch_youtube_captions(video.video_id)
        except Exception as e:
            raise TranscriberError(f"Failed to fetch YouTube captions for {video.video_id}: {e}") from e

        transcript = VideoTranscript(
            video=video,
            segments=segments,
            source="subtitle",
        )
        transcript.build_full_text()
        return transcript

    async def _fetch_youtube_captions(self, video_id: str) -> list[TranscriptSegment]:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        resp = await self._client.get(video_url, headers=self._youtube_headers())
        resp.raise_for_status()
        html = resp.text

        captions_data = self._extract_captions_data(html)
        if not captions_data:
            return []

        caption_url = self._pick_caption_url(captions_data)
        if not caption_url:
            return []

        caption_resp = await self._client.get(caption_url)
        caption_resp.raise_for_status()
        # YouTube currently serves auto captions as WebVTT for some player
        # clients and as srv3 XML for others.  Keep the XML fallback for older
        # responses, but prefer the format that is easiest to parse reliably.
        content_type = caption_resp.headers.get("content-type", "").lower()
        if "vtt" in content_type or caption_resp.text.lstrip().startswith("WEBVTT"):
            segments = self._parse_vtt_caption(caption_resp.text)
        else:
            segments = self._parse_xml_caption(caption_resp.text)
        if segments:
            return segments
        return await self._fetch_with_ytdlp(video_url)

    async def _fetch_with_ytdlp(self, video_url: str) -> list[TranscriptSegment]:
        """Use yt-dlp's subtitle downloader for HLS-backed caption tracks.

        YouTube sometimes exposes captions as an m3u8 playlist rather than a
        plain XML/VTT response. yt-dlp understands that playlist and, with
        skip_download enabled, fetches only subtitle fragments.
        """
        def download_and_parse() -> list[TranscriptSegment]:
            import yt_dlp

            with tempfile.TemporaryDirectory(prefix="video-analysis-subs-") as directory:
                options = {
                    "skip_download": True,
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    # Prefer native tracks.  Regex-like language selectors
                    # such as zh.* also request dozens of translated tracks,
                    # making anonymous requests much more likely to hit 429.
                    "subtitleslangs": ["zh", "en"],
                    "subtitlesformat": "vtt",
                    "outtmpl": str(Path(directory) / "%(id)s.%(language)s.%(ext)s"),
                    "noplaylist": True,
                    "quiet": True,
                    "no_warnings": True,
                }
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([video_url])
                files = sorted(Path(directory).glob("*.vtt"))
                for file in files:
                    segments = self._parse_vtt_caption(file.read_text(encoding="utf-8"))
                    if segments:
                        return segments
            return []

        return await asyncio.to_thread(download_and_parse)

    @staticmethod
    def _youtube_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        }

    def _extract_captions_data(self, html: str) -> list[dict[str, Any]]:
        import json

        pattern = r'var ytInitialPlayerResponse = ({.*?});'
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            return []

        try:
            player_data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        captions = (
            player_data.get("captions", {})
            .get("playerCaptionsTracklistRenderer", {})
            .get("captionTracks", [])
        )
        return captions

    def _pick_caption_url(self, captions: list[dict[str, Any]]) -> str | None:
        def lang_score(track: dict[str, Any]) -> int:
            lang = track.get("languageCode", "")
            name = track.get("name", {}).get("simpleText", "")
            if lang == "zh-Hans" or "中文" in name:
                return 10
            if lang.startswith("zh"):
                return 8
            if lang == "en":
                return 5
            return 1

        if not captions:
            return None
        best = max(captions, key=lang_score)
        base_url = best.get("baseUrl", "")
        if not base_url:
            return None
        separator = "&" if "?" in base_url else "?"
        return base_url + separator + "fmt=vtt"

    @staticmethod
    def _parse_vtt_caption(vtt_text: str) -> list[TranscriptSegment]:
        """Parse YouTube WebVTT cues, including multiline cue text."""
        segments: list[TranscriptSegment] = []
        lines = vtt_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if not line or line in {"WEBVTT", "STYLE", "REGION"} or line.startswith(("NOTE", "Kind:", "Language:")):
                index += 1
                continue
            if "-->" not in line:
                index += 1
                continue
            timing, *settings = line.split("-->", 1)
            end_part = settings[0].strip() if settings else ""
            end_token = end_part.split()[0] if end_part else ""
            start = SubtitleParser._parse_vtt_timestamp(timing.strip())
            end = SubtitleParser._parse_vtt_timestamp(end_token)
            if start is None or end is None:
                index += 1
                continue
            index += 1
            text_lines: list[str] = []
            while index < len(lines) and lines[index].strip():
                text_lines.append(lines[index].strip())
                index += 1
            text = html.unescape(re.sub(r"<[^>]+>", "", " ".join(text_lines))).strip()
            if text:
                segments.append(TranscriptSegment(start=start, end=end, text=text))
        return segments

    @staticmethod
    def _parse_vtt_timestamp(value: str) -> float | None:
        match = re.fullmatch(r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})", value)
        if not match:
            return None
        hours = int(match.group(1) or 0)
        minutes, seconds, millis = (int(part) for part in match.groups()[1:])
        return hours * 3600 + minutes * 60 + seconds + millis / 1000

    @staticmethod
    def _parse_xml_caption(xml_text: str) -> list[TranscriptSegment]:
        segments = []
        for match in re.finditer(
            r'<p t="([\d.]+)"[^>]* d="([\d.]+)"[^>]*>(.*?)</p>',
            xml_text,
        ):
            start = float(match.group(1)) / 1000.0
            duration = float(match.group(2)) / 1000.0
            text = re.sub(r"<[^>]+>", "", match.group(3))
            text = html.unescape(text)
            text = text.strip()
            if text:
                segments.append(
                    TranscriptSegment(start=start, end=start + duration, text=text)
                )
        return segments

    async def close(self) -> None:
        await self._client.aclose()
