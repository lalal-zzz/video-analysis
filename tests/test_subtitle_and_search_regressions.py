import json

import httpx
import pytest

from exceptions import ScraperError
from models.search import SearchQuery
from scrapers.douyin import DouyinScraper
from transcribers.subtitle_parser import SubtitleParser
from mcp_server.storage import failure


def test_parse_webvtt_captions_supports_multiline_text():
    text = """WEBVTT

00:00:00.000 --> 00:00:02.500 align:start
第一行<br>第二行

00:00:02.500 --> 00:00:04.000
股票 &amp; 市场
"""

    segments = SubtitleParser._parse_vtt_caption(text)

    assert [(s.start, s.end, s.text) for s in segments] == [
        (0.0, 2.5, "第一行第二行"),
        (2.5, 4.0, "股票 & 市场"),
    ]


@pytest.mark.asyncio
async def test_subtitle_parser_reads_vtt_caption_response():
    player = {
        "captions": {
            "playerCaptionsTracklistRenderer": {
                "captionTracks": [{
                    "languageCode": "zh",
                    "name": {"simpleText": "Chinese"},
                    "baseUrl": "https://captions.example/track",
                }]
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.youtube.com":
            body = "var ytInitialPlayerResponse = " + json.dumps(player) + ";"
            return httpx.Response(200, text=body)
        return httpx.Response(
            200,
            headers={"content-type": "text/vtt"},
            text="WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n股票上涨\n",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    parser = SubtitleParser(client)
    try:
        segments = await parser._fetch_youtube_captions("abc123")
    finally:
        await parser.close()
    assert len(segments) == 1
    assert segments[0].text == "股票上涨"


@pytest.mark.asyncio
async def test_douyin_empty_search_is_not_success():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status_code": 0, "aweme_list": [], "extra": {}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scraper = DouyinScraper(client, load_cookies=False)
    with pytest.raises(ScraperError, match="no usable results"):
        await scraper.fetch_videos(SearchQuery(keywords="股票", max_results=5))
    await scraper.close()


def test_search_failure_contains_actionable_solution():
    result = failure(ScraperError("Douyin search returned no usable results; anonymous search may be restricted"), "douyin")
    assert result["code"] == "search_restricted"
    assert len(result["solutions"]) == 3
    assert "动态签名" in result["message"]
