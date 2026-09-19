import re
from typing import Any

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
        return self._parse_xml_caption(caption_resp.text)

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
        return base_url + "&fmt=srv3"

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
            text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
            text = text.strip()
            if text:
                segments.append(
                    TranscriptSegment(start=start, end=start + duration, text=text)
                )
        return segments

    async def close(self) -> None:
        await self._client.aclose()