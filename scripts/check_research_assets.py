"""Validate local research assets and render the static showcase in an isolated browser."""
from __future__ import annotations

import json
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from models.creator_research import CreatorWatchlist

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "href" and value and not urlparse(value).scheme and not value.startswith("#"):
                assert (ROOT / unquote(value.split("#")[0])).is_file(), value


def main():
    html = (ROOT / "github.html").read_text(encoding="utf-8")
    Links().feed(html)
    catalog = json.loads((ROOT / "html/skills/creator-catalog.json").read_text(encoding="utf-8"))
    embedded = json.loads(re.search(r'<script id="creator-data" type="application/json">(.*?)</script>', html, re.S)[1])
    assert len(embedded) == len(catalog["creators"])
    assert "following_count" not in catalog
    assert all("origins" not in row and row["category"] != "非财经或待核实" for row in embedded)
    reports = json.loads((ROOT / "html/skills/daily/index.json").read_text(encoding="utf-8"))["reports"]
    daily_embedded = json.loads(re.search(r'<script id="daily-data" type="application/json">(.*?)</script>', html, re.S)[1])
    assert daily_embedded == reports
    assert all((ROOT / report["path"]).is_file() for report in reports)
    watchlist = json.loads((ROOT / "skills/a-share-daily-review/references/default-watchlist.json").read_text(encoding="utf-8"))
    CreatorWatchlist.model_validate({"name": "a-share-daily", **watchlist})
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((ROOT / "github.html").as_uri())
        assert page.locator("#creator-rows tr").count() == len(embedded)
        page.locator("#creator-search").fill("巴菲特")
        assert page.locator("#creator-rows tr").count() == 1
        page.locator("#creator-search").fill("")
        page.locator("#creator-filter").select_option("bilibili")
        assert page.locator("#creator-rows tr").count() == sum(row["platform"] == "bilibili" for row in embedded)
        page.locator("#creator-filter").select_option("all")
        assert not errors, errors
        assert page.locator("#daily-reports li").count() == len({report["trading_date"] for report in reports})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        output = Path(tempfile.mkdtemp(prefix="video-analysis-showcase-"))
        page.screenshot(path=str(output / "desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        browser.close()
    print(json.dumps({"status": "ok", "catalog_count": len(embedded), "screenshots": str(output)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
