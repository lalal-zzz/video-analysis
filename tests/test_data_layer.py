"""Data regressions use temporary storage, never real accounts or tracked fixtures."""
from data.manager import DataManager
from models import VideoMetadata, VideoTranscript
from tools import ToolRegistry


def test_subscriptions_round_trip(tmp_path):
    dm = DataManager(tmp_path)
    rows = [{"author": {"name": "creator", "platform": "bilibili", "url": "https://space.bilibili.com/1"}}]
    dm.save_subscriptions("test", rows)
    assert dm.load_subscriptions("test") == rows
    assert dm.load_subscriptions("absent") == []


def test_blacklist_round_trip_and_remove(tmp_path):
    dm = DataManager(tmp_path)
    rows = [{"author": {"name": "creator"}}]
    dm.save_blacklist("test", rows)
    assert dm.load_blacklist("test") == rows
    assert dm.unblacklist_author("test", "creator")
    assert dm.load_blacklist("test") == []


def test_domain_transcripts_and_analysis(tmp_path):
    dm = DataManager(tmp_path)
    dm.save_transcript_text("test", "creator", "v1", "transcript")
    assert dm.load_transcript_text("test", "creator", "v1") == "transcript"
    assert dm.list_transcript_count(domain="test") == 1
    dm.save_analysis_summary("test", "creator", {"title": "sample", "score_contribution": 0.1})
    assert dm.list_analyses("test")[0]["title"] == "sample"


def test_pipeline_transcript_preserves_metadata(tmp_path):
    dm = DataManager(tmp_path)
    video = VideoMetadata(platform="youtube", video_id="v1", title="sample", author="creator", url="https://www.youtube.com/watch?v=v1")
    path = dm.save_transcript(VideoTranscript(video=video, full_text="words", source="subtitle"))
    assert "words" in path.read_text(encoding="utf-8")
    assert path in dm.list_pipeline_transcripts(platform="youtube")


def test_tool_registry_has_core_tools():
    assert {"search_videos", "get_author_latest_videos", "transcribe_video"} <= set(ToolRegistry.list_all())
