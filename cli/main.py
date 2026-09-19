"""
analyze-video CLI — 视频搜索 + 转录 + LLM 分析管道

用法:
  analyze-video search --query "关键词" --platform bilibili --max-videos 5
  analyze-video analyze --query "人工智能" --prompt "总结这些视频的核心观点" --skill video-analyzer
  analyze-video claude --skill video-analyzer -p "分析"
  analyze-video claude -i --skill video-analyzer     # 交互模式
  analyze-video codex -p "总结以下视频"
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from analyzers.claude_client import ClaudeAnalyzer
from analyzers.codex_client import CodexAnalyzer
from config.settings import Settings
from core.orchestrator import Orchestrator
from data.manager import DataManager, _sanitize_filename
from models.rules import FieldCompareRule, SelectorConfig
from models.search import SearchQuery
from scrapers import BilibiliScraper, DouyinScraper, YouTubeScraper
from transcribers import SubtitleParser, WhisperClient
import log

# 项目根目录（cli 的 parent parent parent = 项目根）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def register_subparsers(subparsers):
    # ── search ──
    p_search = subparsers.add_parser("search", help="搜索视频并显示结果")
    p_search.add_argument("--query", "-q", required=True)
    p_search.add_argument("--platform", "-p", default="bilibili",
                          choices=["bilibili", "youtube", "douyin"])
    p_search.add_argument("--max-videos", "-n", type=int, default=10)
    p_search.add_argument("--author", "-a", default=None)
    p_search.add_argument("--date-from", default=None)
    p_search.add_argument("--date-to", default=None)
    p_search.add_argument("--sort", default="relevance",
                          choices=["relevance", "publish_time", "views"])
    p_search.add_argument("--min-views", type=int, default=0)
    p_search.add_argument("--transcribe", action="store_true")
    p_search.add_argument("--output", "-o", default=None)

    # ── analyze ──
    p_analyze = subparsers.add_parser("analyze",
                                      help="搜索 + 转录 + LLM 分析")
    p_analyze.add_argument("--query", "-q", required=True)
    p_analyze.add_argument("--prompt", required=True)
    p_analyze.add_argument("--platform", "-p", default="bilibili",
                           choices=["bilibili", "youtube", "douyin"])
    p_analyze.add_argument("--max-videos", "-n", type=int, default=10)
    p_analyze.add_argument("--author", "-a", default=None)
    p_analyze.add_argument("--date-from", default=None)
    p_analyze.add_argument("--date-to", default=None)
    p_analyze.add_argument("--min-views", type=int, default=0)
    p_analyze.add_argument("--model", default="claude",
                           choices=["claude", "codex"])
    p_analyze.add_argument("--skill", "-s", default=None,
                           help="项目内 skill 名称 (config/skills/<name>)")
    p_analyze.add_argument("--output", "-o", default=None)

    # ── claude (直调系统 claude CLI) ──
    p_claude = subparsers.add_parser("claude",
                                     help="直接调用系统 claude CLI，支持 skill")
    p_claude.add_argument("--prompt", "-p", default=None,
                          help="单次 prompt")
    p_claude.add_argument("--skill", "-s", default=None,
                          help="skill 名称或路径 (config/skills/<name>)")
    p_claude.add_argument("--model", "-m", default=None,
                          help="指定 claude 模型")
    p_claude.add_argument("--interactive", "-i", action="store_true",
                          help="交互模式")
    p_claude.add_argument("--query", "-q", default=None,
                          help="先搜索视频，将转录结果传入 claude")
    p_claude.add_argument("--platform", default="bilibili")
    p_claude.add_argument("--max-videos", type=int, default=5)

    # ── codex (直调系统 codex CLI) ──
    p_codex = subparsers.add_parser("codex",
                                    help="直接调用系统 codex CLI")
    p_codex.add_argument("--prompt", "-p", default=None)
    p_codex.add_argument("--interactive", "-i", action="store_true")
    p_codex.add_argument("--query", "-q", default=None,
                         help="先搜索视频，将转录结果传入 codex")
    p_codex.add_argument("--platform", default="bilibili")
    p_codex.add_argument("--max-videos", type=int, default=5)

    # ── domain ──
    p_domain = subparsers.add_parser("domain",
                                      help="领域管理 — create/discover/monitor/review")
    p_domain.add_argument("action",
                          choices=["create", "discover", "monitor", "review"],
                          help="操作类型")
    p_domain.add_argument("--name", "-n", required=True,
                          help="领域名称")
    p_domain.add_argument("--intent", "-i", default="",
                          help="领域描述（create 时必填）")
    p_domain.add_argument("--template", "-t", default="stock",
                          help="模板名称")
    p_domain.add_argument("--list", "-l", action="store_true",
                          help="列出所有领域")

    # ── list-skills ──
    p_list = subparsers.add_parser("list-skills",
                                    help="列出项目内置 skills")

    # ── web ──
    p_web = subparsers.add_parser("web",
                                   help="启动 Web 界面")
    p_web.add_argument("--port", "-p", type=int, default=8080,
                       help="端口号")
    p_web.add_argument("--host", default="127.0.0.1",
                       help="绑定地址")

    # ── logs ──
    p_logs = subparsers.add_parser("logs",
                                    help="查看管道日志")
    p_logs.add_argument("--tail", "-t", type=int, default=20,
                        help="显示最近 N 条日志")
    p_logs.add_argument("--level", "-l", default=None,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="按级别筛选")
    p_logs.add_argument("--pipeline", "-p", default=None,
                        help="按管道筛选 (search/analyze/monitor/discover/review)")
    p_logs.add_argument("--module", "-m", default=None,
                        help="按模块筛选 (如 engine.monitor)")
    p_logs.add_argument("--follow", "-f", action="store_true",
                        help="持续跟踪 (类似 tail -f)")
    p_logs.add_argument("--stats", action="store_true",
                        help="显示统计摘要")

    return {
        "search": p_search,
        "analyze": p_analyze,
        "claude": p_claude,
        "codex": p_codex,
        "domain": p_domain,
        "list-skills": p_list,
        "web": p_web,
        "logs": p_logs,
    }


# ──────────────────── 命令实现 ────────────────────

async def cmd_search(args):
    import json

    with log.pipeline_context("search"):
        settings = Settings()
        scraper = _make_scraper(args.platform)
        query = _make_query(args)
        selector = _make_selector(args)
        data = DataManager(settings.data.data_dir)

        orch = Orchestrator(
            scraper=scraper,
            transcriber=SubtitleParser(),
            analyzer=ClaudeAnalyzer(),
            settings=settings,
        )
        videos = await orch._search_videos(query, selector)

        if args.transcribe:
            transcripts = await orch._transcribe_videos(videos)
            session = datetime.now().strftime("%Y%m%d_%H%M%S")
            saved = data.save_transcripts(transcripts, session)
            print(f"转录文件已保存 ({len(saved)} 个):")
            for fp in saved:
                print(f"  {fp}")
            output = [
                {
                    "title": t.video.title,
                    "author": t.video.author,
                    "url": t.video.url,
                    "transcript": t.full_text,
                    "file": str(fp),
                }
                for t, fp in zip(transcripts, saved)
            ]
        else:
            output = [
                {
                    "title": v.title,
                    "author": v.author,
                    "url": v.url,
                    "views": v.stats.views,
                    "duration": v.duration,
                    "publish_time": str(v.publish_time or ""),
                }
                for v in videos
            ]

        text = json.dumps(output, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"结果已保存到: {args.output}")
        else:
            print(text)


async def cmd_analyze(args):
    with log.pipeline_context("analyze"):
        settings = Settings()
        session = datetime.now().strftime("%Y%m%d_%H%M%S")
        scraper = _make_scraper(args.platform)
        transcriber = _make_transcriber(args.platform)
        analyzer = ClaudeAnalyzer(skill=args.skill) if args.model == "claude" else CodexAnalyzer()

        orch = Orchestrator(
            scraper=scraper,
            transcriber=transcriber,
            analyzer=analyzer,
            settings=settings,
        )

        query = _make_query(args)
        selector = _make_selector(args)

        result = await orch.run(
            user_query=args.prompt,
            search_query=query,
            selector=selector,
            max_videos=args.max_videos,
            skill=args.skill or "",
            session=session,
        )

        text = result.raw_response or result.summary

        # 查找刚刚保存的结果文件
        data = DataManager(settings.data.data_dir)
        slug = _sanitize_filename(result.request.user_query or "analysis") or "analysis"
        result_dir = data.root / "results"
        if args.skill:
            result_dir = result_dir / args.skill
        if session:
            result_dir = result_dir / session
        result_file = result_dir / f"{session}_{slug}.md"

        print(text)
        print(f"\n--- 分析结果已保存: {result_file} ---")


async def cmd_claude(args):
    import os

    if args.interactive:
        return ClaudeAnalyzer.interactive(
            skill=args.skill,
            model=args.model,
        )

    if not args.prompt and not args.query:
        # 无 prompt 也无 query → 进入交互式
        return ClaudeAnalyzer.interactive(
            skill=args.skill,
            model=args.model,
        )

    if args.query:
        with log.pipeline_context("claude"):
            settings = Settings()
            session = datetime.now().strftime("%Y%m%d_%H%M%S")
            scraper = _make_scraper(args.platform)
            transcriber = _make_transcriber(args.platform)
            analyzer = ClaudeAnalyzer(skill=args.skill, model=args.model)
            orch = Orchestrator(
                scraper=scraper,
                transcriber=transcriber,
                analyzer=analyzer,
                settings=settings,
            )
            query = SearchQuery(
                keywords=args.query,
                platform=args.platform,
                max_results=args.max_videos,
            )
            result = await orch.run(
                user_query=args.prompt or "分析这些视频内容",
                search_query=query,
                max_videos=args.max_videos,
                skill=args.skill or "",
                session=session,
            )
            print(result.raw_response or result.summary)
            data = DataManager(settings.data.data_dir)
            slug = _sanitize_filename(result.request.user_query or "analysis") or "analysis"
            result_file = data.root / "results"
            if args.skill:
                result_file = result_file / args.skill
            if session:
                result_file = result_file / session
            result_file = result_file / f"{session}_{slug}.md"
            print(f"\n--- 分析结果已保存: {result_file} ---")

    elif args.prompt:
        analyzer = ClaudeAnalyzer(skill=args.skill, model=args.model)
        from models.analysis import AnalysisRequest
        result = await analyzer.analyze(
            AnalysisRequest(user_query=args.prompt)
        )
        print(result.raw_response or result.summary)


async def cmd_codex(args):
    if args.interactive:
        return __import__("subprocess").call(["codex"])

    if not args.prompt and not args.query:
        return __import__("subprocess").call(["codex"])

    if args.query:
        with log.pipeline_context("codex"):
            settings = Settings()
            session = datetime.now().strftime("%Y%m%d_%H%M%S")
            scraper = _make_scraper(args.platform)
            transcriber = _make_transcriber(args.platform)
            analyzer = CodexAnalyzer()
            orch = Orchestrator(
                scraper=scraper,
                transcriber=transcriber,
                analyzer=analyzer,
                settings=settings,
            )
            query = SearchQuery(
                keywords=args.query,
                platform=args.platform,
                max_results=args.max_videos,
            )
            result = await orch.run(
                user_query=args.prompt or "分析这些视频内容",
                search_query=query,
                max_videos=args.max_videos,
                session=session,
            )
            print(result.raw_response or result.summary)
            data = DataManager(settings.data.data_dir)
            slug = _sanitize_filename(result.request.user_query or "analysis") or "analysis"
            result_file = data.root / "results"
            if session:
                result_file = result_file / session
            result_file = result_file / f"{session}_{slug}.md"
            print(f"\n--- 分析结果已保存: {result_file} ---")

    elif args.prompt:
        analyzer = CodexAnalyzer()
        from models.analysis import AnalysisRequest
        result = await analyzer.analyze(
            AnalysisRequest(user_query=args.prompt)
        )
        print(result.raw_response or result.summary)


def cmd_list_skills(args):
    skills_dir = _PROJECT_ROOT / "config" / "skills"
    print(f"项目内置 skills ({skills_dir}):")
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir():
            continue
        skill_md = d / "SKILL.md"
        desc = ""
        if skill_md.exists():
            content = skill_md.read_text(encoding="utf-8")
            for line in content.splitlines()[:10]:
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break
        print(f"\n  📁 {d.name}")
        if desc:
            print(f"     {desc}")
        print(f"     用法: claude --skill {d.name}")


def cmd_domain(args):
    """领域管理命令."""
    from engine import DomainManager
    dm = DomainManager()

    if args.list:
        domains = dm.list_domains()
        if not domains:
            print("暂无领域")
            return
        for d in domains:
            print(f"  📁 {d['name']}: {d['description']}")
        return

    if args.action == "create":
        if not args.intent:
            print("错误: create 操作需要 --intent 参数")
            sys.exit(1)
        with log.pipeline_context("domain_create"):
            result = dm.create(args.name, args.intent, template_name=args.template)
            print(f"领域 '{args.name}' 创建成功:")
            for f in result["files"]:
                print(f"  {f}")
        return

    with log.pipeline_context(f"domain_{args.action}"):
        result = dm.run(args.name, args.action)
        if result.get("status") == "ok":
            if args.action == "discover":
                print(f"发现 {len(result['candidates'])} 位候选作者:")
                for c in result["candidates"]:
                    print(f"  - {c['name']} ({c['platform']}) — "
                          f"{c['video_count']} 个视频")
            elif args.action == "monitor":
                print(f"监控完成: {result.get('monitored', 0)} 个视频, "
                      f"{result.get('errors', 0)} 个错误")
            elif args.action == "review":
                print(f"复盘完成:")
                print(f"  评分调整: {result.get('score_changes', 0)} 个")
                print(f"  新拉黑: {result.get('new_blacklists', 0)} 个")
                report_content = result.get("llm_output") or result.get("prompt", "")
                review_file = _PROJECT_ROOT / "tmp_review.md"
                review_file.write_text(report_content, encoding="utf-8")
                print(f"  复盘报告已保存到: {review_file}")
        else:
            print(f"错误: {result.get('message', '未知错误')}")


def cmd_logs(args):
    """查看管道日志."""
    from log import database

    if args.stats:
        stats = database.stats()
        print(f"日志统计:")
        print(f"  总日志数: {stats['total']}")
        print(f"  日志文件数: {stats['log_files']}")
        print(f"  按级别:")
        for lvl, cnt in stats["by_level"].items():
            if cnt > 0:
                print(f"    {lvl}: {cnt}")
        print(f"  按管道:")
        for pl, cnt in stats["by_pipeline"].items():
            if cnt > 0:
                print(f"    {pl}: {cnt}")
        return

    kwargs: dict[str, object] = {"limit": args.tail}
    if args.level:
        kwargs["level"] = args.level
    if args.pipeline:
        kwargs["pipeline"] = args.pipeline
    if args.module:
        kwargs["module"] = args.module

    entries = database.query(**kwargs)

    if not entries:
        print("暂无日志记录")
        return

    for entry in entries:
        ts = entry.get("timestamp", "")[:19]
        level = entry.get("level", "INFO")
        module = entry.get("module", "")
        event = entry.get("event", "")
        msg = entry.get("message", "")
        error = entry.get("error", "")
        duration = entry.get("duration_ms")

        level_colors = {
            "DEBUG": "36",
            "INFO": "32",
            "WARNING": "33",
            "ERROR": "31",
        }
        color = level_colors.get(level, "37")
        dur_str = f" ({duration:.0f}ms)" if duration else ""
        err_str = f" — {error}" if error else ""
        print(f"\033[{color}m[{ts}] [{level:7s}] [{module}] {event}: {msg}{err_str}{dur_str}\033[0m")


def cmd_web(args):
    """启动 Web 界面."""
    try:
        import uvicorn  # type: ignore
    except ImportError:
        print("错误: uvicorn 未安装。pip install uvicorn")
        sys.exit(1)

    from web.app import app
    uvicorn.run(
        app,
        host=args.host or "127.0.0.1",
        port=args.port or 8080,
        log_level="info",
    )


COMMANDS = {
    "search": cmd_search,
    "analyze": cmd_analyze,
    "claude": cmd_claude,
    "codex": cmd_codex,
    "domain": cmd_domain,
    "list-skills": cmd_list_skills,
    "web": cmd_web,
    "logs": cmd_logs,
}


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="analyze-video — 视频搜索、转录、LLM 分析管道",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    register_subparsers(
        parser.add_subparsers(dest="command", required=True)
    )
    args = parser.parse_args()

    cmd = COMMANDS.get(args.command)
    if cmd is None:
        parser.print_help()
        sys.exit(1)

    if asyncio.iscoroutinefunction(cmd):
        asyncio.run(cmd(args))
    else:
        cmd(args)


if __name__ == "__main__":
    main()
