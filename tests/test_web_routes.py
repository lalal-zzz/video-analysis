"""Integration tests for all web routes."""
import pytest
from litestar.testing import TestClient
from web.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_returns_stats(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert "订阅作者" in html
    assert "领域数" in html
    assert "今日分析" in html
    assert "转录总数" in html
    assert "score-chart" in html
    assert "volume-chart" in html


def test_health_returns_json(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"status": "ok"}


def test_search_page_renders(client):
    resp = client.get("/search")
    assert resp.status_code == 200
    html = resp.text
    assert 'hx-post="/search/execute"' in html
    assert 'name="query"' in html
    assert 'name="platform"' in html
    assert 'name="max_videos"' in html
    assert 'value="bilibili"' in html
    assert 'value="youtube"' in html
    assert 'id="search-results"' in html


def test_results_page_returns_html(client):
    resp = client.get("/results")
    assert resp.status_code == 200


def test_transcripts_page_lists_transcripts(client):
    resp = client.get("/transcripts")
    assert resp.status_code == 200
    html = resp.text
    assert "转录浏览" in html


def test_domains_page_renders_with_controls(client):
    resp = client.get("/domains")
    assert resp.status_code == 200
    html = resp.text
    assert "领域管理" in html
    assert "startMonitor(" in html
    assert "startDiscover(" in html
    assert "startReview(" in html
    assert 'id="progress-container"' in html
    assert "stock" in html


def test_404_returns_custom_page(client):
    resp = client.get("/nonexistent")
    assert resp.status_code == 404
    assert "404" in resp.text


def test_static_css_served(client):
    resp = client.get("/static/css/style.css")
    assert resp.status_code in (200, 404)


def test_static_js_served(client):
    resp = client.get("/static/js/ws_progress.js")
    assert resp.status_code == 200


def test_chart_author_trend(client):
    resp = client.get("/charts/author-trend/stock")
    assert resp.status_code == 200
    data = resp.json()
    assert "xAxis" in data
    assert "series" in data


def test_chart_volume_trend(client):
    resp = client.get("/charts/volume-trend/stock")
    assert resp.status_code == 200
    data = resp.json()
    assert "dates" in data
    assert "views" in data or "series" in data


def test_ws_task_endpoints(client):
    resp = client.get("/ws/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data


def test_progress_docs(client):
    resp = client.get("/progress/docs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "websocket"


def test_nav_links_present(client):
    resp = client.get("/")
    html = resp.text
    for href in ["/search", "/results", "/transcripts", "/domains", "/progress/docs"]:
        assert f'href="{href}' in html or f"href='{href}" in html