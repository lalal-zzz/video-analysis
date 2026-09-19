"""通用工具 — 订阅/评分/历史等，供所有 Skill 调用."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime

from models.domain import Subscription, BlacklistEntry
from data_manager import DataManager

logger = logging.getLogger(__name__)

# ─── 工具注册 ───────────────────────────────────────────────

from tools.registry import ToolRegistry


@ToolRegistry.register("get_author_history")
def get_author_history(author: str, domain: str) -> list[dict]:
    """获取作者历史分析摘要。author: 作者名, domain: 领域名."""
    base = Path("data") / domain / "analysis"
    results: list[dict] = []
    if not base.exists():
        return results
    for f in base.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("author") == author:
                        results.append(entry)
        except (json.JSONDecodeError, OSError):
            pass
    return results


@ToolRegistry.register("get_author_score")
def get_author_score(author: str, domain: str) -> dict:
    """获取作者评分和趋势."""
    subs_file = Path("data") / domain / "subscriptions.json"
    if subs_file.exists():
        subs: list[dict] = json.loads(subs_file.read_text(encoding="utf-8"))
        for sub in subs:
            if sub["author"]["name"] == author:
                return {
                    "name": author,
                    "score": sub["score"],
                    "total_analyses": sub["total_analyses"],
                    "subscribed_at": sub["subscribed_at"],
                    "last_monitored_at": sub.get("last_monitored_at"),
                    "tags": sub.get("tags", []),
                }
    return {"name": author, "score": 0.0}


@ToolRegistry.register("get_subscriptions")
def get_subscriptions(domain: str) -> list[dict]:
    """获取当前订阅列表."""
    subs_file = Path("data") / domain / "subscriptions.json"
    if subs_file.exists():
        return json.loads(subs_file.read_text(encoding="utf-8"))
    return []


@ToolRegistry.register("update_subscription_score")
def update_subscription_score(domain: str, author: str, score: float) -> bool:
    """更新作者评分."""
    subs_file = Path("data") / domain / "subscriptions.json"
    if not subs_file.exists():
        return False
    subs: list[dict] = json.loads(subs_file.read_text(encoding="utf-8"))
    updated = False
    for sub in subs:
        if sub["author"]["name"] == author:
            old_score = sub["score"]
            sub["score"] = round(max(-1.0, min(1.0, score)), 2)
            sub["score_history"] = sub.get("score_history", [])
            sub["score_history"].append({
                "value": sub["score"],
                "prev": old_score,
                "changed_at": datetime.now().isoformat(),
            })
            updated = True
            break
    if updated:
        subs_file.write_text(json.dumps(subs, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return updated


@ToolRegistry.register("blacklist_author")
def blacklist_author(domain: str, author: str, reason: str = "") -> bool:
    """拉黑作者."""
    subs_file = Path("data") / domain / "subscriptions.json"
    blacklist_file = Path("data") / domain / "blacklist.json"
    if not subs_file.exists():
        return False
    subs: list[dict] = json.loads(subs_file.read_text(encoding="utf-8"))
    updated = False
    for sub in subs:
        if sub["author"]["name"] == author:
            sub["is_blacklisted"] = True
            sub["blacklist_reason"] = reason
            sub["blacklisted_at"] = datetime.now().isoformat()
            updated = True
            break
    if updated:
        subs_file.write_text(json.dumps(subs, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        entry: dict = {
            "author": next((s["author"] for s in subs if s["author"]["name"] == author), {}),
            "domain": domain,
            "reason": reason,
            "blacklisted_at": datetime.now().isoformat(),
        }
        existing: list[dict] = []
        if blacklist_file.exists():
            existing = json.loads(blacklist_file.read_text(encoding="utf-8"))
        existing.append(entry)
        blacklist_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return updated


@ToolRegistry.register("get_domain_trends")
def get_domain_trends(domain: str, days: int = 30) -> dict:
    """获取领域趋势摘要."""
    dm = DataManager()
    analyses = dm.list_analyses(domain)
    word_counts: dict[str, float] = {}
    for a in analyses:
        title = a.get("title", a.get("query", ""))
        for word in title.split():
            if len(word) > 1:
                word_counts[word] = word_counts.get(word, 0) + 1
    top_keywords = sorted(word_counts.items(), key=lambda x: -x[1])[:10]
    return {
        "days": days,
        "domain": domain,
        "total_analyses": dm.count_analyses_recent(days, domain=domain),
        "total_videos": dm.list_transcript_count(days, domain=domain),
        "top_keywords": [{"keyword": k, "weight": min(v / 5.0, 1.0)} for k, v in top_keywords],
    }


@ToolRegistry.register("get_domain_reports")
def get_domain_reports(domain: str, limit: int = 10) -> list[dict]:
    """获取历史复盘报告."""
    review_dir = Path("data") / domain / "review"
    if not review_dir.exists():
        return []
    files = sorted(review_dir.glob("*.md"), reverse=True)[:limit]
    results = []
    for f in files:
        results.append({"file": f.name, "path": str(f), "content": f.read_text(encoding="utf-8")})
    return results


@ToolRegistry.register("unblacklist_author")
def unblacklist_author(domain: str, author: str) -> bool:
    """从黑名单移除作者."""
    subs_file = Path("data") / domain / "subscriptions.json"
    blacklist_file = Path("data") / domain / "blacklist.json"
    if not subs_file.exists():
        return False
    subs: list[dict] = json.loads(subs_file.read_text(encoding="utf-8"))
    updated = False
    for sub in subs:
        if sub["author"]["name"] == author:
            sub["is_blacklisted"] = False
            sub.pop("blacklist_reason", None)
            sub.pop("blacklisted_at", None)
            updated = True
            break
    if updated:
        subs_file.write_text(json.dumps(subs, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        if blacklist_file.exists():
            bl: list[dict] = json.loads(blacklist_file.read_text(encoding="utf-8"))
            bl = [b for b in bl if b.get("author", {}).get("name") != author]
            blacklist_file.write_text(json.dumps(bl, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return updated
