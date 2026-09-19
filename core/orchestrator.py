from datetime import datetime

from analyzers.base import BaseAnalyzer
from cache.base import BaseCache
from cache.manager import DiskCache
from config.settings import Settings
from core.scheduler import Scheduler
from data.manager import DataManager
from exceptions import TranscriberError
from models.analysis import AnalysisRequest, AnalysisResult
from models.rules import SelectorConfig
from models.search import SearchQuery, SearchResult
from models.video import VideoMetadata
from scrapers.base import BaseScraper
from transcribers.base import BaseTranscriber
import log


class Orchestrator:
    def __init__(
        self,
        scraper: BaseScraper,
        transcriber: BaseTranscriber,
        analyzer: BaseAnalyzer,
        cache: BaseCache | None = None,
        scheduler: Scheduler | None = None,
        settings: Settings | None = None,
        data_manager: DataManager | None = None,
    ) -> None:
        self._scraper = scraper
        self._transcriber = transcriber
        self._analyzer = analyzer
        self._cache = cache or DiskCache(settings)
        self._scheduler = scheduler or Scheduler()
        self._settings = settings or Settings()
        self._data = data_manager or DataManager(self._settings.data.data_dir)

    async def run(
        self,
        user_query: str,
        search_query: SearchQuery,
        selector: SelectorConfig | None = None,
        max_videos: int = 10,
        skill: str = "",
        session: str = "",
    ) -> AnalysisResult:
        log.log("INFO", "orchestrator", "pipeline_start",
                f"Pipeline: query='{search_query.keywords}' platform={search_query.platform}",
                detail={"query": search_query.keywords, "platform": search_query.platform, "max_videos": max_videos, "skill": skill})

        videos = await self._search_videos(search_query, selector)
        videos = videos[:max_videos]
        log.log("INFO", "orchestrator", "search_complete",
                f"Found {len(videos)} videos", detail={"count": len(videos), "query": search_query.keywords})

        transcripts = await self._transcribe_videos(videos)
        log.log("INFO", "orchestrator", "transcribe_complete",
                f"Transcribed {len(transcripts)} videos", detail={"count": len(transcripts)})

        transcript_files = self._data.save_transcripts(transcripts, session)
        rel_paths = [str(p.relative_to(self._data.root.parent)) for p in transcript_files]

        request = AnalysisRequest(
            transcripts=transcripts,
            transcript_files=rel_paths,
            user_query=user_query,
            model_type=self._analyzer.model_type,
        )

        result = await self._analyzer.analyze(request)
        log.log("INFO", "orchestrator", "analyze_complete",
                f"Analysis complete", detail={"user_query": user_query, "skill": skill})

        self._data.save_result(result, skill=skill, session=session)

        return result

    async def _search_videos(
        self,
        query: SearchQuery,
        selector: SelectorConfig | None,
    ) -> list[VideoMetadata]:
        cached = await self._cache.get_query(query)
        if cached is not None:
            log.log("DEBUG", "orchestrator", "cache_hit",
                    f"Cache hit for query '{query.keywords}'", detail={"query": query.keywords, "videos": len(cached.videos)})
            if selector:
                return selector.apply(cached.videos)
            return cached.videos

        log.log("DEBUG", "orchestrator", "cache_miss",
                f"Cache miss for query '{query.keywords}', fetching", detail={"query": query.keywords, "platform": query.platform})
        result = await self._scraper.fetch_videos(query)
        await self._cache.set_query(result)

        if selector:
            return await self._scraper.select(result, selector)

        return result.videos

    async def _transcribe_videos(
        self, videos: list[VideoMetadata]
    ) -> list:
        from models.transcript import VideoTranscript

        async def transcribe_one(video: VideoMetadata) -> VideoTranscript:
            cached = await self._cache.get_video(video.platform, video.video_id)
            if cached is not None:
                log.log("DEBUG", "orchestrator", "transcript_cache_hit",
                        f"Cache hit for {video.video_id}", detail={"video_id": video.video_id, "title": video.title})
                return cached

            if not await self._transcriber.supports(video):
                log.log("WARNING", "orchestrator", "unsupported_video",
                        f"Unsupported video: {video.title}", detail={"video_id": video.video_id, "platform": video.platform})
                return VideoTranscript(video=video, segments=[], full_text="", source="unsupported")

            try:
                transcript = await self._transcriber.get_transcript(video)
            except TranscriberError as e:
                log.log("ERROR", "orchestrator", "transcribe_failed",
                        f"Transcription error for {video.title}: {e}", detail={"video_id": video.video_id, "title": video.title}, error=str(e))
                return VideoTranscript(video=video, segments=[], full_text="", source="error")

            await self._cache.set_video(transcript)
            return transcript

        factories: list[tuple[object, tuple, dict]] = [
            (transcribe_one, (v,), {})
            for v in videos
        ]  # type: ignore[list-item]
        results = await self._scheduler.run_all(factories)

        valid = []
        for r in results:
            if isinstance(r, VideoTranscript):
                valid.append(r)

        return valid

    async def run_pipeline(
        self,
        user_query: str,
        search_query: SearchQuery,
        selector: SelectorConfig | None = None,
        max_videos: int = 10,
        skill: str = "",
        session: str = "",
    ) -> AnalysisResult:
        return await self.run(user_query, search_query, selector, max_videos, skill, session)