"""结果路由."""

from __future__ import annotations
from pathlib import Path
from litestar import get
from litestar.response import Template

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_manager import DataManager


@get("/results")
async def results_page() -> Template:
    dm = DataManager()
    domains = [d.name for d in Path("data").iterdir() if d.is_dir() and (d / "subscriptions.json").exists()]
    analyses = []
    for domain in domains:
        domain_analyses = dm.list_analyses(domain)
        analyses.extend(domain_analyses)
    analyses.sort(key=lambda x: x.get('analyzed_at', x.get('timestamp', '')), reverse=True)
    return Template(
        template_name="results.html",
        context={"title": "分析结果", "analyses": analyses[:50]},
    )
