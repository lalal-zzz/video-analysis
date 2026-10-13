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
        # Exercise history navigation using temporary fixtures, never public report data.
        fixture_reports = []
        for day, revision, saved_at in (
            ("2024-03-01", "a" * 32, "2024-03-02T08:00:00+08:00"),
            ("2024-02-29", "b" * 32, "2024-03-01T08:00:00+08:00"),
            ("2024-02-29", "c" * 32, "2024-03-01T09:00:00+08:00"),
            ("2023-12-31", "d" * 32, "2024-01-01T08:00:00+08:00"),
        ):
            path = f"html/skills/daily/{day}/{revision}.md"
            fixture_reports.append({"trading_date": day, "revision": revision, "path": path,
                                    "saved_at": saved_at, "creators": 14, "transcripts": 20})
            fixture_report = output / path
            fixture_report.parent.mkdir(parents=True, exist_ok=True)
            fixture_report.write_text("Temporary calendar test report.\n", encoding="utf-8")
        fixture_reports.append({"trading_date": "2024-02-30", "revision": "e" * 32,
                                "path": "html/skills/daily/2024-02-30/" + "e" * 32 + ".md"})
        fixture_reports.append({"trading_date": "2024-03-02", "revision": "f" * 32,
                                "path": "https://example.com/untrusted.md"})
        fixture_html = re.sub(r'(<script id="daily-data" type="application/json">).*?(</script>)',
                              lambda match: match[1] + json.dumps(fixture_reports) + match[2], html, flags=re.S)
        fixture_path = output / "calendar-fixture.html"
        fixture_path.write_text(fixture_html, encoding="utf-8")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(fixture_path.as_uri())
        assert page.locator("#calendar-month").inner_text() == "2024年3月"
        assert page.locator("#daily-reports li").count() == 3
        assert page.locator(".calendar-day.has-report").count() == 1
        assert page.locator('[data-date="2024-03-02"]').is_disabled()
        page.locator("#calendar-prev").click()
        assert page.locator("#calendar-month").inner_text() == "2024年2月"
        assert page.locator(".calendar-day").count() == 29
        page.locator('[data-date="2024-02-29"]').click()
        assert page.locator('[data-date="2024-02-29"]').get_attribute("aria-pressed") == "true"
        assert page.locator("#daily-versions li").count() == 2
        assert page.locator("#daily-versions a").first.get_attribute("href").endswith("c" * 32 + ".md")
        assert "本月 1 天有分析 · 共 2 个版本" in page.locator("#calendar-summary").inner_text()
        page.locator("#daily").screenshot(path=str(output / "calendar-desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.locator("#daily").screenshot(path=str(output / "calendar-mobile.png"))
        # Full-text links point to an actual file, including older revisions.
        page.locator("#daily-versions a").last.click()
        assert "b" * 32 in page.url
        page.goto(fixture_path.as_uri())
        page.locator("#calendar-prev").click()
        page.locator("#calendar-prev").click()
        assert page.locator("#calendar-month").inner_text() == "2024年1月"
        assert page.locator("#daily-versions li").count() == 0
        page.locator("#calendar-prev").click()
        assert page.locator("#calendar-month").inner_text() == "2023年12月"
        assert page.locator('[data-date="2023-12-31"]').is_enabled()
        page.locator("#calendar-latest").click()
        assert page.locator("#calendar-month").inner_text() == "2024年3月"
        page.locator("#calendar-current").click()
        assert page.locator('[aria-current="date"]').count() == 1
        assert not errors, errors
        browser.close()
    print(json.dumps({"status": "ok", "catalog_count": len(embedded), "screenshots": str(output)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
