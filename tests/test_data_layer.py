"""Integration tests for data layer and domain engine."""
import pytest
from pathlib import Path
from data_manager import DataManager
from engine.domain_manager import DomainManager
from tools import ToolRegistry


@pytest.fixture
def dm():
    return DataManager()


def test_data_manager_load_subscriptions(dm):
    subs = dm.load_subscriptions("stock")
    assert len(subs) > 0
    for s in subs:
        assert "author" in s
        assert isinstance(s["author"], dict)
        assert "platform" in s["author"]
        assert "url" in s["author"]


def test_data_manager_load_blacklist(dm):
    bl = dm.load_blacklist("stock")
    assert isinstance(bl, list)


def test_data_manager_list_analyses(dm):
    analyses = dm.list_analyses("stock")
    assert len(analyses) >= 10
    for a in analyses[:3]:
        assert "title" in a
        assert "author" in a
        assert "score_contribution" in a


def test_data_manager_list_transcripts(dm):
    transcripts = dm.list_transcripts("stock")
    assert len(transcripts) > 0
    for t in transcripts:
        assert "author" in t
        assert "video_id" in t


def test_data_manager_count_analyses_recent(dm):
    count = dm.count_analyses_recent(days=30, domain="stock")
    assert count >= 0


def test_data_manager_list_transcript_count(dm):
    count = dm.list_transcript_count(domain="stock")
    assert count > 0


def test_tool_registry_list(dm):
    tools = ToolRegistry.list_all()
    assert len(tools) >= 14


def test_tool_registry_get_stock_data(dm):
    result = ToolRegistry.call("get_stock_data", symbol="600519")
    assert result is not None


def test_tool_registry_get_market_sentiment(dm):
    result = ToolRegistry.call("get_market_sentiment")
    assert result is not None


def test_tool_registry_get_domain_trends(dm):
    result = ToolRegistry.call("get_domain_trends", domain="stock")
    assert result is not None
    assert "top_keywords" in result


def test_domain_manager_discover(dm):
    mgr = DomainManager()
    result = mgr.run("stock", "discover")
    assert result["status"] == "ok"
    assert result["action"] == "discover"


def test_domain_manager_monitor(dm):
    mgr = DomainManager()
    result = mgr.run("stock", "monitor")
    assert result["status"] == "ok"
    assert "monitored" in result


def test_domain_manager_review(dm):
    mgr = DomainManager()
    result = mgr.run("stock", "review")
    assert result["status"] == "ok"
    assert "prompt" in result
    assert len(result["prompt"]) > 100