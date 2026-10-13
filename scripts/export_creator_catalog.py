"""Maintain a public financial creator catalog; private follows are opt-in.

Uses the supported MCP server for account access. Never exports session material.
Run manually when refreshing the repository's research catalog.
"""
from __future__ import annotations

import asyncio
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "html" / "skills" / "creator-catalog.json"
PRIVATE = ROOT / "data" / "private-research" / "creator-catalog.private.json"
# Discovery evidence from this conversation. A video is evidence, not a profile ID.
SEEDS = [
    ("海螺复盘", "BV1UJKb6CEPM", "指数/ETF/可转债"),
    ("股帮", "", "市场消息/收评"),
    ("作手峰途", "BV1eRPezEEug", "短线题材"),
    ("ETF基金波段王", "BV16YaAzgEhy", "指数/ETF"),
    ("跟着诸葛学交易", "BV14wT4zHEz2", "技术/收评"),
    ("比巴卜作手", "BV1NAiyBdEDM", "短线复盘"),
    ("小草论市", "BV11GuC6xEC6", "午评/收评"),
    ("沪深A神", "BV1nDTF69EPX", "午评/收评"),
    ("巴菲特的魔法师", "BV19FuR6PEMY", "盘前/午评/题材"),
    ("刘老师の炒股笔记", "BV1rGK3zvEiD", "午评/收评/实盘"),
    ("刺客论股", "BV1KfVB6sEZN", "每日股评；需核对是否与刘老师同源"),
    ("长空道可道", "BV1f1AtzKEkH", "复盘方法/盘前预案"),
    ("八零后中年打工人", "BV1tj6wBDECE", "持仓复盘；部分内容付费"),
    ("姜妮妮er", "BV1w8Q7B7EZm", "交易学习/复盘方法"),
    ("K线大叔", "BV1XtUaBPEx9", "技术/跨市场复盘"),
    ("每天解读一家上市公司", "BV16BLVzZEtd", "公司/基本面"),
    ("有信心BB", "", "财报研究；与每天解读一家上市公司分开核实"),
    ("九哥谈股论金", "BV1L3tA66Exd", "技术/收评"),
    ("筑基交易员", "BV1DA5M6VEfR", "短线题材/复盘"),
    ("憧憬船i", "BV13XqrYuEqr", "缠论/指数"),
    ("船长讲缠Z", "BV1oJ4m1g7NE", "缠论教学"),
    ("猫头理财说", "BV1js56zbEZW", "课程/基本面；核查原创与授权"),
    ("问君JLM", "BV1Xv9yB1EY3", "复盘回放；核查原创与转载"),
    ("一代作手", "", "深度题材复盘"),
    ("三步学交易-老雷", "", "A股/ETF/题材"),
    ("来自股市的猩猩", "", "早评/午评"),
    ("六哥说股", "", "午评/收评"),
    ("舵主老徐", "", "A股行情"),
    ("他山财经", "", "A股历史/研究"),
    ("趋势大龙", "BV1d9Yi6mEwk", "盘前；粉丝与日更待核实"),
    ("今日股评", "BV1Ufbq6bEvK", "收评；小号或转载待核实"),
    ("嘉嘉的第六感", "BV1tr421L7So", "解盘；旧样本待核实"),
    ("作手康红阳", "", "板块/技术"),
    ("少然说财经", "", "板块/技术"),
    ("交易员小郑", "", "交易/题材"),
]
EXTRA = [
    ("youtube", "A股作手", "https://www.youtube.com/channel/UC_gnvDt2_qUjN5BH3Met5WQ", "A股短线，日更未核实"),
    ("youtube", "A股财经【都业华-缠中说禅】", "https://www.youtube.com/channel/UC4psLoVnI8mD3L-HwIZe7EA", "A股缠论，官方身份与日更未核实"),
    ("youtube", "贝拉读书笔记", "https://www.youtube.com/channel/UC_vQCI0Dczas9QsmlYm_6Rw", "A股/港股补充，日更未核实"),
    ("youtube", "贝拉聊财金", "https://www.youtube.com/@bellafinance", "主要美股，外围补充"),
    ("youtube", "老王说财经", "https://www.youtube.com/@LaoWangFinance", "宏观，规模/日更未核实"),
    ("youtube", "老王愛說笑", "https://www.youtube.com/@oldwangstock", "主要台股，外围补充"),
    ("youtube", "阳光财经", "https://www.youtube.com/channel/UC2I5em6UyBpQiO-8ZW0nV3w", "主要美股，外围补充"),
    ("youtube", "双侧玩美股", "https://www.youtube.com/@DanielWu-d1q", "美股，非A股每日池"),
    ("youtube", "投机实验室", "https://www.youtube.com/channel/UCjQfmtuNPsHXVMhK74hFpog", "交易教学，日更A股未核实"),
    ("youtube", "美投君", "https://www.youtube.com/channel/UCBUH38E0ngqvmTqdchWunwQ", "美股，非A股每日池"),
    ("youtube", "Victor聊投资", "https://www.youtube.com/channel/UCK-Pz6nRnVugkusYllAz4IQ", "跨市场补充，日更未核实"),
    ("youtube", "股市咖啡屋 Stock Cafe", "", "美股，频道身份待核实"),
    ("youtube", "NaNa说美股", "", "美股，频道身份待核实"),
    ("youtube", "岚解美股大盘", "", "美股，频道身份待核实"),
    ("youtube", "Water Brother Investment 水哥股市小屋", "", "美股，频道身份待核实"),
    ("youtube", "私募一哥常士杉", "", "跨市场，频道身份待核实"),
]
TOPIC_TAGS = {
    "李大霄": "A股政策/市场短评", "擒龙先生": "A股盘后/科技题材",
    "量化技术分析": "指数/技术/期货", "知先财情": "宏观/跨市场/晨间收评",
    "梦想超过余额宝": "ETF份额/资金追踪", "主力行为学杨宁本人": "A股交易信号",
    "玄同波浪_极简交易": "近期以黄金为主", "周期研视角": "近期以恒生科技为主",
    "星话大白": "宏观/国际消息", "小Lin说": "财经科普，非每日A股复盘",
}


def escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def public_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    """An allowlist prevents account relationships and non-financial follows leaking."""
    allowed = ("name", "platform", "url", "author_id", "category", "evidence_url", "followers", "followers_checked_at", "identity_status", "verified_at")
    rows = []
    for source in payload["creators"]:
        if source.get("category") == "非财经或待核实":
            continue
        row = {key: source[key] for key in allowed if key in source}
        row.setdefault("identity_status", "public_profile_confirmed")
        if source.get("recent_videos"):
            unique = {video["url"]: {key: video[key] for key in ("title", "publish_time", "url") if key in video} for video in source["recent_videos"]}
            row["recent_videos"] = list(unique.values())
        rows.append(row)
    return {"checked_at": payload["checked_at"], "catalog_count": len(rows), "scope": "public_financial_creators", "creators": rows}


def sync_showcase(payload: dict[str, Any]) -> None:
    """Embed public rows so the static page also works when opened via file://."""
    html_path = ROOT / "github.html"
    if not html_path.exists():
        return
    html = html_path.read_text(encoding="utf-8")
    payload = public_catalog(payload)
    public_rows = [{k: row[k] for k in ("name", "platform", "url", "evidence_url", "category", "identity_status", "followers") if k in row} for row in payload["creators"]]
    embedded = json.dumps(public_rows, ensure_ascii=False).replace("<", "\\u003c")
    html = re.sub(r'(<script id="creator-data" type="application/json">).*?(</script>)', lambda m: m[1] + embedded + m[2], html, flags=re.DOTALL)
    html = re.sub(r'(<b id="catalog-total">).*?(</b>)', lambda m: m[1] + str(len(public_rows)) + m[2], html)
    html_path.write_text(html, encoding="utf-8")


async def main(reuse_following_snapshot: bool = False, include_following: bool = False) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    entries: dict[str, dict[str, Any]] = {}
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(ROOT))
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            status = (await session.call_tool("get_system_status", {})).structuredContent
            if not status or status.get("status") != "ok":
                raise RuntimeError("MCP status unavailable")
            if reuse_following_snapshot:
                previous = json.loads(PRIVATE.read_text(encoding="utf-8"))
                follows = {"status": "ok", "authors": [row for row in previous["creators"] if "account_following" in row["origins"]], "limit_reached": previous["following_limit_reached"]}
            elif include_following:
                follows = (await session.call_tool("list_followed_authors", {"platform": "bilibili", "limit": 500})).structuredContent
            else:
                follows = {"status": "ok", "authors": [], "limit_reached": False}
                if CATALOG.exists():
                    previous = json.loads(CATALOG.read_text(encoding="utf-8"))
                    for row in previous["creators"]:
                        entries[row["url"] or f"{row['platform']}:{row['name']}"] = row
            if not follows or follows.get("status") != "ok":
                raise RuntimeError("Following list unavailable; existing exports were preserved")
            for row in follows["authors"]:
                entries[row["url"]] = {**row, "origins": ["account_following"], "category": TOPIC_TAGS.get(row["name"], "非财经或待核实"), "verified_at": row.get("verified_at", stamp)}
            limiter = asyncio.Semaphore(3)
            async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}) as client:
                async def resolve(seed: tuple[str, str, str]) -> dict[str, Any]:
                    name, bvid, category = seed
                    row: dict[str, Any] = {"name": name, "platform": "bilibili", "url": "", "origins": ["conversation_search"], "category": category, "identity_status": "pending"}
                    if bvid:
                        row["evidence_url"] = f"https://www.bilibili.com/video/{bvid}"
                        async with limiter:
                            try:
                                data = (await client.get("https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid})).json()
                                owner = data.get("data", {}).get("owner", {})
                                if data.get("code") == 0 and owner.get("mid"):
                                    row.update(name=owner["name"], author_id=str(owner["mid"]), url=f"https://space.bilibili.com/{owner['mid']}", identity_status="api_verified", verified_at=stamp)
                                    if owner["name"] != name:
                                        row["discovery_name"] = name
                            except (httpx.HTTPError, ValueError, KeyError):
                                pass
                    return row
                for row in await asyncio.gather(*(resolve(seed) for seed in SEEDS)):
                    key = row["url"] or f"bilibili:{row['name']}"
                    if key in entries:
                        row["origins"] = list(dict.fromkeys(entries[key].get("origins", []) + row["origins"]))
                        row["category"] = entries[key]["category"] if "account_following" in entries[key].get("origins", []) else row["category"]
                        entries[key].update(row)
                    else:
                        entries[key] = row
                # Known profile identities already recorded by original Bilibili list URLs.
                known = {"海螺复盘": "471949556", "ETF基金波段王": "518495360"}
                for name, uid in known.items():
                    key = f"bilibili:{name}"
                    if key in entries:
                        row = entries.pop(key)
                        row.update(author_id=uid, url=f"https://space.bilibili.com/{uid}", identity_status="profile_link_evidence")
                        entries[row["url"]] = row
                async def resolve_search(key: str, row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
                    async with limiter:
                        result = (await session.call_tool("search_videos", {"platform": "bilibili", "keywords": row["name"], "max_results": 3, "refresh": True})).structuredContent
                        for video in (result or {}).get("videos", []):
                            profile = video.get("author_url", "")
                            if video.get("author") == row["name"] and profile.startswith("https://space.bilibili.com/"):
                                row.update(url=profile, author_id=profile.rstrip("/").split("/")[-1], identity_status="search_verified", verified_at=stamp)
                                break
                    return key, row
                pending = [(key, row) for key, row in entries.items() if row.get("identity_status") == "pending"]
                for old_key, row in await asyncio.gather(*(resolve_search(key, row) for key, row in pending)):
                    if row["url"]:
                        entries.pop(old_key, None)
                        if row["url"] in entries:
                            row["origins"] = list(dict.fromkeys(entries[row["url"]].get("origins", []) + row["origins"]))
                        entries[row["url"]] = row
                for platform, name, url, category in EXTRA:
                    entries[url or f"{platform}:{name}"] = {"name": name, "platform": platform, "url": url, "category": category, "origins": ["conversation_search"], "identity_status": "search_evidence_only"}
                async def fans(row: dict[str, Any]) -> None:
                    if row["platform"] != "bilibili" or not row.get("author_id"):
                        return
                    async with limiter:
                        try:
                            result = (await client.get("https://api.bilibili.com/x/relation/stat", params={"vmid": row["author_id"]})).json()
                            if result.get("code") == 0:
                                row.update(followers=result["data"]["follower"], followers_checked_at=stamp)
                        except (httpx.HTTPError, ValueError, KeyError):
                            pass
                # Non-financial follows remain in the catalog without unnecessary queries.
                await asyncio.gather(*(fans(row) for row in entries.values() if row["category"] != "非财经或待核实"))
            monitored = [row for row in entries.values() if row["platform"] == "bilibili" and row.get("author_id") and row["category"] != "非财经或待核实"]
            if monitored:
                batch = (await session.call_tool("get_latest_videos", {"platform": "bilibili", "authors": [row["url"] for row in monitored], "max_per_author": 6, "refresh": True})).structuredContent
                if batch and batch.get("job_id"):
                    while True:
                        batch = (await session.call_tool("get_job", {"job_id": batch["job_id"], "wait_seconds": 30})).structuredContent
                        if batch["status"] != "running":
                            break
                        print(json.dumps({"completed": batch.get("completed"), "total": batch.get("total")}), flush=True)
                for item in (batch or {}).get("results", []):
                    if isinstance(item.get("index"), int) and item["index"] < len(monitored):
                        monitored[item["index"]]["latest_status"] = item.get("status", "unknown")
                    videos = item.get("videos", [])
                    if not videos:
                        for nested in item.get("results", []):
                            videos.extend(nested.get("videos", []))
                    for video in videos:
                        row = entries.get(video.get("author_url", ""))
                        if row is not None:
                            row.setdefault("recent_videos", []).append({k: video[k] for k in ("title", "publish_time", "url")})
            # Preserve full/partial coverage explicitly rather than claiming unlimited follows.
            payload = {"checked_at": datetime.now(timezone.utc).isoformat(), "following_count": len(follows["authors"]), "following_limit_reached": follows.get("limit_reached", True), "creators": list(entries.values())}
            if include_following or reuse_following_snapshot:
                PRIVATE.parent.mkdir(parents=True, exist_ok=True)
                PRIVATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_catalog(payload)


def write_catalog(payload: dict[str, Any]) -> None:
    payload = public_catalog(payload)
    entries = {row["url"] or f"{row['platform']}:{row['name']}": row for row in payload["creators"]}
    for row in entries.values():
        if row.get("recent_videos"):
            row["recent_videos"] = list({video["url"]: video for video in row["recent_videos"]}.values())
    output = ROOT / "html" / "skills"
    output.mkdir(parents=True, exist_ok=True)
    (output / "creator-catalog.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 财经博主公开来源总表", "", f"核对时间：{payload['checked_at']}。共 {len(entries)} 个财经与研究条目。", "", "本表仅提供通用财经作者、公开主页和视频元数据，不提供任何用户的账号身份、关注关系、Cookie或登录资料。身份待核实、其他市场、课程或转载条目保留状态，不自动进入每日A股研究池。粉丝数不代表预测准确性。", "", "## 来源目录（按平台/UID合并）", "", "| 名称 | 平台 | 主页/发现证据 | 定位 | 粉丝数 | 身份核实 |", "|---|---|---|---|---:|---|"]
    for row in entries.values():
        link = row["url"] or row.get("evidence_url", "")
        lines.append(f"| {escape(row['name'])} | {row['platform']} | {'[来源](' + link + ')' if link else '待解析主页'} | {escape(row['category'])} | {row.get('followers', '待核实')} | {row['identity_status']} |")
    lines += ["", "## 最近视频证据", "", "以下只核实主题和更新日期；未转录的视频不支持观点结论。不能依据标题判断预测准确性。", ""]
    for row in entries.values():
        if row.get("recent_videos"):
            lines += [f"### {row['name']}", ""]
            for video in row["recent_videos"]:
                lines.append(f"- {video['publish_time']} · [{escape(video['title'])}]({video['url']})")
            lines.append("")
    lines += ["## 身份与证据限制", "", "- “每天解读一家上市公司”与“有信心BB”是两个独立候选，不能混用主页或粉丝数。", "- 同一讲者的大小号、课程号与转载号不能在共识计数中重复计票。刺客论股与刘老师的关系需要按主页/转录确认。", "- YouTube链接来自检索证据，尚未逐一验证近期更新，不写成实时日更名单。", "- 没有明确UID/频道URL的条目留在发现池，解析身份后才能加入固定监控。", "", "机器可读来源：[creator-catalog.json](creator-catalog.json)。每日流程：[a-share-daily-review Skill](../../skills/a-share-daily-review/SKILL.md)。", ""]
    (output / "creator-catalog.md").write_text("\n".join(lines), encoding="utf-8")
    sync_showcase(payload)
    print(json.dumps({"total": len(entries), "output": str(output)}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-following", action="store_true", help="Explicitly authorized import; full account snapshot stays in ignored local storage only")
    parser.add_argument("--reuse-following-snapshot", action="store_true", help="Use the existing authorized following snapshot when the live platform is restricted")
    parser.add_argument("--render-only", action="store_true", help="Embed existing public catalog in the showcase without account or network access")
    parser.add_argument("--input", type=Path, default=CATALOG, help="Existing catalog; publication always removes private relationships")
    arguments = parser.parse_args()
    if arguments.render_only:
        write_catalog(json.loads(arguments.input.read_text(encoding="utf-8")))
    else:
        asyncio.run(main(arguments.reuse_following_snapshot, arguments.include_following))
