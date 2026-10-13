"""Public exports must not reveal a user's following relationships."""
from __future__ import annotations

import json

from scripts.export_creator_catalog import public_catalog, write_catalog


def private_snapshot():
    return {"checked_at": "2026-10-13T10:00:00+00:00", "following_count": 2,
            "account_id": "private-account", "creators": [
        {"name": "公开财经作者", "platform": "bilibili", "url": "https://space.bilibili.com/123",
         "author_id": "123", "category": "指数/ETF", "origins": ["account_following"],
         "email": "personal@example.com", "cookies": {"secret": "hidden"},
         "recent_videos": [{"title": "行情复盘", "publish_time": "2026-10-13T15:00:00",
                            "url": "https://www.bilibili.com/video/BVtest", "account_id": "hidden"}]},
        {"name": "个人美食偏好", "platform": "bilibili", "url": "https://space.bilibili.com/456",
         "category": "非财经或待核实", "origins": ["account_following"]}]}


def test_public_catalog_allowlists_profile_fields_and_excludes_relationships():
    public = public_catalog(private_snapshot())
    assert public["catalog_count"] == 1
    creator = public["creators"][0]
    assert creator["name"] == "公开财经作者"
    assert "origins" not in creator and "email" not in creator and "cookies" not in creator
    assert "following_count" not in public and "account_id" not in public
    assert "account_id" not in creator["recent_videos"][0]
    assert public_catalog(public) == public


def test_public_files_and_embedded_page_never_contain_private_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.export_creator_catalog.ROOT", tmp_path)
    page = tmp_path / "github.html"
    page.write_text('<b id="catalog-total">0</b><script id="creator-data" type="application/json">[]</script>', encoding="utf-8")
    write_catalog(private_snapshot())
    assert not (tmp_path / "docs").exists()
    folder = tmp_path / "html" / "skills"
    catalog = json.loads((folder / "creator-catalog.json").read_text(encoding="utf-8"))
    assert catalog["catalog_count"] == 1
    for path in [folder / "creator-catalog.json", folder / "creator-catalog.md", page]:
        text = path.read_text(encoding="utf-8")
        for secret in ("account_following", "private-account", "personal@example.com", "个人美食偏好", '"cookies"'):
            assert secret not in text
