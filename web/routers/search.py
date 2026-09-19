"""搜索路由 — 支持 HTMX 表单提交。未登录时自动跳转扫码登录。"""

from __future__ import annotations

import json
from datetime import datetime

import uuid
from typing import Any

from litestar import get, post, MediaType, Request
from litestar.response import Template

from models.search import SearchQuery
from scrapers import BilibiliScraper, YouTubeScraper, DouyinScraper
import log

SCRAPERS: dict[str, Any] = {
    "bilibili": BilibiliScraper,
    "youtube": YouTubeScraper,
    "douyin": DouyinScraper,
}

# 需要登录才能搜索的平台
AUTH_REQUIRED_PLATFORMS = {"bilibili", "douyin"}


@get("/search", name="search_page")
async def search_page(
    request: Request,
) -> Template:
    """搜索页面 — 不强制检查登录状态，登录检查推迟到执行搜索时。"""
    query = request.query_params.get("query", "")
    platform = request.query_params.get("platform", "bilibili")

    return Template(
        template_name="search.html",
        context={
            "title": "视频搜索",
            "query": query,
            "platform": platform,
            "videos": [],
        },
    )


@post("/search/execute", media_type=MediaType.TEXT)
async def execute_search(request: Request) -> str:
    """处理 HTMX 搜索表单提交。支持多平台搜索，未登录时返回登录链接。"""
    data = await request.form()
    platforms = data.getall("platform") or ["bilibili"]
    keywords = data.get("query", "")
    max_videos = int(data.get("max_videos", 10))
    sort = data.get("sort", "relevance")
    min_views = data.get("min_views", "")
    date_from = data.get("date_from", "")
    date_to = data.get("date_to", "")

    if not keywords:
        return '<div class="text-red-500 text-center py-4">请输入搜索关键词</div>'

    if len(platforms) == 1:
        # 单平台搜索（原有逻辑）
        return await _execute_single_search(platforms[0], keywords, max_videos, sort, min_views, date_from, date_to)
    else:
        # 多平台搜索
        return await _execute_multi_search(platforms, keywords, max_videos, sort, min_views, date_from, date_to)


async def _execute_single_search(platform: str, keywords: str, max_videos: int, sort: str = "", min_views: str = "", date_from: str = "", date_to: str = "") -> str:
    """单平台搜索逻辑。"""
    # 检查需要登录的平台
    if platform in AUTH_REQUIRED_PLATFORMS:
        scraper = SCRAPERS[platform]()
        try:
            logged_in = await scraper.is_logged_in()
        except Exception:
            logged_in = False
        
        if not logged_in:
            login_url = "/bilibili-login" if platform == "bilibili" else "/douyin-login"
            platform_name = "Bilibili" if platform == "bilibili" else "抖音"
            return f'''
            <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center" data-slide>
                <div class="text-5xl mb-4 opacity-40">🔒</div>
                <p class="text-lg font-semibold text-gray-700 mb-2">需要先登录 {platform_name}</p>
                <p class="text-sm text-gray-400 mb-5">登录后即可搜索 {platform_name} 视频</p>
                <div class="flex justify-center gap-3">
                    <a href="{login_url}" 
                       class="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg hover:from-blue-700 hover:to-blue-800 font-medium transition-all shadow-md text-sm">
                        扫码登录 →
                    </a>
                </div>
            </div>
            '''

    scraper_cls = SCRAPERS.get(platform)
    if scraper_cls is None:
        return f'<div class="text-red-500">不支持的平台: {platform}</div>'

    scraper = scraper_cls()
    query = SearchQuery(keywords=keywords, platform=platform, max_results=max_videos, sort=sort)
    if date_from:
        query.date_from = datetime.fromisoformat(date_from)
    if date_to:
        query.date_to = datetime.fromisoformat(date_to)

    try:
        log.log("INFO", "web.search", "search_execute",
                f"Search: keywords='{keywords}' platform={platform}",
                detail={"keywords": keywords, "platform": platform})

        result = await scraper.fetch_videos(query)

        log.log("INFO", "web.search", "search_result",
                f"Found {len(result.videos)} videos",
                detail={"count": len(result.videos), "query": keywords})

        videos = [
            {
                "title": v.title,
                "author": v.author,
                "url": v.url,
                "views": v.stats.views,
                "publish_time": str(v.publish_time or ""),
                "video_id": v.video_id,
            }
            for v in result.videos
        ]
        return _render_video_cards(videos, platform)

    except Exception as e:
        err_str = str(e)
        log.log("ERROR", "web.search", "search_error",
                f"Search error: {err_str}",
                detail={"query": keywords, "platform": platform},
                error=err_str)
        if "Name or service not known" in err_str or "Connection refused" in err_str or "timeout" in err_str.lower():
            hint = f'<p class="text-xs text-gray-400 mt-2">请检查网络连接是否正常，或尝试使用其他平台搜索</p>'
        else:
            hint = ""
        return f'<div class="text-red-500 p-4 text-center">搜索失败: {err_str}{hint}</div>'


async def _execute_multi_search(platforms: list[str], keywords: str, max_videos: int, sort: str = "", min_views: str = "", date_from: str = "", date_to: str = "") -> str:
    """多平台搜索逻辑，按平台分组返回结果。"""
    from litestar.contrib.htmx.response import TemplateResponse
    
    all_results = {}  # {platform: [videos]}
    login_errors = {}  # {platform: error_html}
    
    # 检查需要登录的平台
    for platform in platforms:
        if platform in AUTH_REQUIRED_PLATFORMS:
            scraper = SCRAPERS[platform]()
            try:
                logged_in = await scraper.is_logged_in()
            except Exception:
                logged_in = False
            
            if not logged_in:
                login_url = "/bilibili-login" if platform == "bilibili" else "/douyin-login"
                platform_name = "Bilibili" if platform == "bilibili" else "抖音"
                login_errors[platform] = f'''
                <div class="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
                    <div class="text-3xl mb-2 opacity-60">🔒</div>
                    <p class="text-sm font-semibold text-red-700 mb-1">需要先登录 {platform_name}</p>
                    <a href="{login_url}" class="text-xs text-red-600 hover:text-red-800 underline">去扫码登录 →</a>
                </div>
                '''
                continue
        
        scraper_cls = SCRAPERS.get(platform)
        if not scraper_cls:
            login_errors[platform] = f'<div class="text-red-500 text-sm">不支持的平台: {platform}</div>'
            continue
        
        try:
            scraper = scraper_cls()
            q = SearchQuery(keywords=keywords, platform=platform, max_results=max_videos, sort=sort)
            if date_from:
                q.date_from = datetime.fromisoformat(date_from)
            if date_to:
                q.date_to = datetime.fromisoformat(date_to)
            result = await scraper.fetch_videos(q)
            
            videos = [
                {
                    "title": v.title,
                    "author": v.author,
                    "url": v.url,
                    "views": v.stats.views,
                    "publish_time": str(v.publish_time or ""),
                    "video_id": v.video_id,
                }
                for v in result.videos
            ]
            all_results[platform] = videos
        except Exception as e:
            log.log("ERROR", "web.search", "search_error",
                    f"Search error for {platform}: {e}",
                    detail={"query": keywords, "platform": platform},
                    error=str(e))
            login_errors[platform] = f'<div class="text-red-500 text-sm">搜索失败: {e}</div>'
    
    return _render_multi_platform_results(platforms, all_results, login_errors)


@post("/search/analyze", media_type=MediaType.TEXT)
async def analyze_videos(request: Request) -> str:
    """分析选定视频 — 支持单平台和多平台分析。异步执行，返回进度 HTML。"""
    data = await request.form()
    platform_param = data.get("platform", "bilibili")
    selected_ids_str = data.get("selected_video_ids", "")
    selected_ids = [x.strip() for x in selected_ids_str.split(",") if x.strip()]
    model_type = data.get("model_type", "claude")
    whisper_model = data.get("whisper_model", "tiny")
    analysis_type = data.get("analysis_type", "full")
    user_query = data.get("user_query", "")
    skip_analysis = analysis_type == "skip"

    if not selected_ids:
        return '<div class="text-red-500 p-4 text-center">未选择任何视频</div>'

    # 判断是单平台还是多平台
    platforms = [p.strip() for p in platform_param.split(",") if p.strip()]
    is_multi_platform = len(platforms) > 1

    # Create a task for async processing
    task_id = f"analyze_{uuid.uuid4().hex[:8]}"

    # Start async work
    import asyncio
    asyncio.create_task(_run_analysis(task_id, platforms, selected_ids, model_type, whisper_model, skip_analysis, user_query))

    # Return progress HTML for HTMX polling
    platform_display = "、".join(platforms) if is_multi_platform else platforms[0]
    return f'''
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-8" data-slide>
        <div class="flex items-center gap-4">
            <div class="animate-spin w-8 h-8 border-4 border-violet-500 border-t-transparent rounded-full"></div>
            <div>
                <h3 class="font-semibold text-gray-800">分析任务已启动</h3>
                <p class="text-sm text-gray-500 mt-0.5">
                    平台: {platform_display}
                    · {skip_analysis and '仅下载视频' or ('正在分析 ' + str(len(selected_ids)) + ' 个视频')}
                    · 使用 {model_type or '默认'} 模型
                    {not skip_analysis and whisper_model and whisper_model != 'none' and ' · Whisper: ' + whisper_model or ''}
                </p>
            </div>
        </div>
        <div class="mt-4">
            <div class="w-full bg-gray-200 rounded-full h-2">
                <div class="bg-gradient-to-r from-blue-500 to-violet-500 h-2 rounded-full animate-pulse" style="width: 30%"></div>
            </div>
        </div>
        <div class="mt-4 text-sm text-gray-500">
            <p>分析完成后，请前往 <a href="/results" class="text-blue-600 hover:text-blue-800 underline">分析结果</a> 页面查看。</p>
        </div>
    </div>
    '''


async def _run_analysis(task_id, platforms, video_ids, model_type, whisper_model, skip_analysis, user_query):
    """异步执行分析任务。支持多平台分析。"""
    from models.video import VideoMetadata
    from models.transcript import VideoTranscript
    from models.search import SearchQuery

    all_selected_videos = []
    
    try:
        log.log("INFO", "web.analyze", "analyze_start", f"Task {task_id} starting", detail={"platforms": platforms, "video_ids": video_ids})

        # 1. 搜索（支持多平台）— 直接用已知的 video_id 搜索
        for platform in platforms:
            scraper_cls = SCRAPERS.get(platform)
            if not scraper_cls:
                log.log("WARNING", "web.analyze", "unsupported_platform", f"Platform {platform} not supported")
                continue
            
            scraper = scraper_cls()
            # 搜索足够多的视频以覆盖选中的 video_id
            query = SearchQuery(keywords="", platform=platform, max_results=max(len(video_ids) * 3, 50))
            search_result = await scraper.fetch_videos(query)

            # Filter to selected videos from this platform
            selected_videos = [v for v in search_result.videos if v.video_id in video_ids]
            all_selected_videos.extend(selected_videos)
            log.log("INFO", "web.analyze", "platform_search_done", 
                    f"Platform {platform}: found {len(selected_videos)} selected videos out of {len(search_result.videos)}")

        if not all_selected_videos:
            log.log("WARNING", "web.analyze", "no_selected_videos_found",
                    f"Could not find any of the {len(video_ids)} selected video IDs in search results")
            log.log("INFO", "web.analyze", "analyze_task_complete",
                    f"Task {task_id} completed with no videos", 
                    detail={"platforms": platforms, "video_count": 0})
            return

        log.log("INFO", "web.analyze", "search_done", 
                f"Found {len(all_selected_videos)} selected videos from {len(platforms)} platforms")

        # 2. Transcribe (if needed)
        if not skip_analysis:
            from transcribers.whisper_client import WhisperClient
            from transcribers.subtitle_parser import SubtitleParser

            if whisper_model and whisper_model != "none":
                transcriber = WhisperClient(model_name=f"whisper-{whisper_model}")
            else:
                transcriber = SubtitleParser()

            transcripts = []
            for i, v in enumerate(all_selected_videos):
                try:
                    log.log("INFO", "web.analyze", "transcribing", 
                            f"Transcribing ({i+1}/{len(all_selected_videos)}): {v.title[:30]}...",
                            detail={"video_id": v.video_id})
                    transcript = await transcriber.get_transcript(v)
                    transcripts.append(transcript)
                except Exception as e:
                    log.log("WARNING", "web.analyze", "transcribe_error", str(e), 
                            detail={"video_id": v.video_id})
                    transcripts.append(VideoTranscript(video=v, segments=[], full_text="", source="error"))

            log.log("INFO", "web.analyze", "transcribe_done", f"Transcribed {len(transcripts)} videos")

            # 3. Analyze (if needed)
            log.log("INFO", "web.analyze", "analyze_start_llm", "Starting LLM analysis")
            if model_type == "codex":
                from analyzers.codex_client import CodexAnalyzer
                analyzer = CodexAnalyzer()
            else:
                from analyzers.claude_client import ClaudeAnalyzer
                analyzer = ClaudeAnalyzer()

            # Build analysis request - include platform info for cross-platform analysis
            platform_names = {"bilibili": "Bilibili", "youtube": "YouTube", "douyin": "抖音"}
            platforms_display = "、".join([platform_names.get(p, p) for p in platforms])
            
            if len(platforms) > 1:
                default_query = f"请跨平台对比分析以下来自{platforms_display}的视频内容，找出各平台的观点异同"
            else:
                default_query = "请分析这些视频中的关键观点和内容"
            
            from models.analysis import AnalysisRequest
            analysis_query = user_query or default_query
            
            request = AnalysisRequest(
                transcripts=transcripts,
                user_query=analysis_query,
                model_type=model_type,
            )

            log.log("INFO", "web.analyze", "llm_call_start", 
                    f"User query: {analysis_query[:100]}")
            result = await analyzer.analyze(request)

            # Save result
            from data.manager import DataManager
            dm = DataManager()
            dm.save_result(result)

            # Save model/whisper info to analysis JSON for results page display
            try:
                domain = platforms[0] if len(platforms) == 1 else "cross"
                analysis_file = dm.root / domain / "analysis" / f"{uuid.uuid4().hex[:12]}.json"
                analysis_file.parent.mkdir(parents=True, exist_ok=True)
                analysis_entry = {
                    "user_query": analysis_query,
                    "model_type": model_type,
                    "whisper_model": whisper_model if whisper_model and whisper_model != "none" else "",
                    "analyzed_at": result.analyzed_at.isoformat(),
                    "summary": result.summary[:200] if result.summary else "",
                    "conclusion": result.conclusion[:200] if result.conclusion else "",
                    "videos_analyzed": len(all_selected_videos),
                    "video_ids": [v.video_id for v in all_selected_videos],
                }
                analysis_file.write_text(json.dumps([analysis_entry], ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                log.log("WARNING", "web.analyze", "save_analysis_json_error", str(e))

            log.log("INFO", "web.analyze", "analyze_done", "Analysis complete")

        log.log("INFO", "web.analyze", "analyze_task_complete", 
                f"Task {task_id} completed", 
                detail={"platforms": platforms, "video_count": len(all_selected_videos)})

    except Exception as e:
        import traceback
        log.log("ERROR", "web.analyze", "analyze_error", str(e), exc_info=True)


def _render_video_cards(videos: list[dict], platform: str = "bilibili") -> str:
    """渲染视频卡片 HTML（带 checkbox 选择 + 分析按钮）。"""
    if not videos:
        platform_name = {"bilibili": "Bilibili", "youtube": "YouTube", "douyin": "抖音"}.get(platform, platform)
        return f'<div class="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center"><div class="text-5xl mb-4 opacity-30">📭</div><p class="text-gray-400 text-lg">{platform_name} 未找到相关视频</p><p class="text-gray-300 text-sm mt-1">请尝试其他关键词</p></div>'

    # Generate a unique session id for this search
    search_id = uuid.uuid4().hex[:12]

    cards = []
    for v in videos:
        publish_date = str(v.get("publish_time", ""))[:10] or "未知"
        views = v.get('views', 0)
        views_str = f"{views:,}" if isinstance(views, (int, float)) else str(views)
        title = v.get('title', '无标题')
        author = v.get('author', '未知')
        url = v.get('url', '#')
        video_id = v.get('video_id', '')
        cards.append(f"""
        <div class="result-card p-4 bg-white rounded-xl border border-gray-100 shadow-sm">
            <div class="flex items-start gap-3">
                <div class="pt-1">
                    <input type="checkbox" name="selected_videos" value="{video_id}"
                           class="video-checkbox w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                           data-video-title="{title}" data-video-url="{url}" data-video-author="{author}" data-video-platform="{platform}"
                           checked>
                </div>
                <div class="flex-1 min-w-0">
                    <h3 class="font-medium text-gray-800 truncate text-sm">
                        {title}
                    </h3>
                    <div class="flex items-center gap-2 mt-1.5 text-xs text-gray-500">
                        <span class="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 rounded text-gray-600 font-medium">
                            👤 {author}
                        </span>
                        <button type="button" onclick="toggleSubscribeAuthor(this, '{author}', '{platform}')"
                                class="subscribe-btn ml-1 px-2 py-0.5 text-xs rounded border font-medium transition-all border-blue-300 text-blue-600 bg-blue-50 hover:bg-blue-100"
                                data-author="{author}" data-platform="{platform}" data-subscribed="false">
                            +关注
                        </button>
                        <span class="text-gray-300">|</span>
                        <span>👁 {views_str}</span>
                        <span class="text-gray-300">|</span>
                        <span>📅 {publish_date}</span>
                    </div>
                </div>
                <a href="{url}" target="_blank" rel="noopener"
                   class="shrink-0 px-2.5 py-1 text-xs bg-gray-50 text-gray-500 rounded-lg hover:bg-blue-50 hover:text-blue-600 border border-gray-200 hover:border-blue-200 transition-all">
                    观看 ▸
                </a>
            </div>
        </div>
        """)

    video_ids = ",".join(v.get("video_id", "") for v in videos)

    return f'''
    <div data-fade>
        <div class="flex items-center justify-between mb-3 px-1">
            <div class="flex items-center gap-2">
                <label class="text-sm text-gray-600">已选 <span id="selected-count">{len(videos)}</span>/{len(videos)}</label>
                <button type="button" onclick="toggleAll(true)" class="text-xs text-blue-600 hover:text-blue-800">全选</button>
                <button type="button" onclick="toggleAll(false)" class="text-xs text-blue-600 hover:text-blue-800">全不选</button>
            </div>
            <button type="button" onclick="submitAnalysis('{search_id}')"
                    class="px-5 py-2 bg-gradient-to-r from-violet-600 to-violet-700 text-white rounded-lg hover:from-violet-700 hover:to-violet-800 font-medium transition-all shadow-md text-sm">
                分析所选视频 →
            </button>
        </div>
        <div class="space-y-2" id="search-id-{search_id}">{"".join(cards)}</div>
        <input type="hidden" id="search-ids-{search_id}" value="{video_ids}">
        <input type="hidden" id="search-platform-{search_id}" value="{platform}">
    </div>
    '''


def _render_multi_platform_results(platforms: list[str], all_results: dict, login_errors: dict) -> str:
    """多平台搜索结果，按平台分组显示。"""
    search_id = uuid.uuid4().hex[:12]
    platform_names = {"bilibili": "Bilibili", "youtube": "YouTube", "douyin": "抖音"}
    
    total_videos = sum(len(videos) for videos in all_results.values())
    
    html_parts = []
    
    # 汇总信息
    html_parts.append(f'''
    <div class="bg-gradient-to-r from-blue-50 to-violet-50 rounded-xl border border-blue-200 p-4 mb-4">
        <div class="flex items-center gap-3">
            <span class="text-2xl">🔍</span>
            <div>
                <p class="font-semibold text-gray-800">搜索结果汇总</p>
                <p class="text-sm text-gray-600">
                    搜索平台: {", ".join(platform_names.get(p, p) for p in platforms)}
                    · 共找到 <span class="font-semibold text-blue-700">{total_videos}</span> 个视频
                </p>
            </div>
        </div>
    </div>
    ''')
    
    # 登录错误提示
    for platform, error_html in login_errors.items():
        html_parts.append(f'<div class="mb-4"><div class="border-l-4 border-red-400 pl-4">{error_html}</div></div>')
    
    # 按平台分组显示结果
    for platform in platforms:
        if platform in login_errors:
            continue  # 已显示错误信息，跳过
        
        videos = all_results.get(platform, [])
        if not videos:
            html_parts.append(f'''
            <div class="mb-6">
                <div class="flex items-center gap-2 mb-3">
                    <span class="px-3 py-1 bg-gray-100 text-gray-600 rounded-full text-sm font-medium">{platform_names.get(platform, platform)}</span>
                    <span class="text-sm text-gray-400">未找到相关视频</span>
                </div>
            </div>
            ''')
            continue
        
        # 平台标签
        html_parts.append(f'''
        <div class="mb-6">
            <div class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2">
                    <span class="px-3 py-1 bg-gradient-to-r from-blue-500 to-violet-500 text-white rounded-full text-sm font-medium">{platform_names.get(platform, platform)}</span>
                    <span class="text-sm text-gray-500">{len(videos)} 个视频</span>
                </div>
            </div>
        </div>
        ''')
        
        # 该平台的所有视频卡片
        for v in videos:
            publish_date = str(v.get("publish_time", ""))[:10] or "未知"
            views = v.get('views', 0)
            views_str = f"{views:,}" if isinstance(views, (int, float)) else str(views)
            title = v.get('title', '无标题')
            author = v.get('author', '未知')
            url = v.get('url', '#')
            video_id = v.get('video_id', '')
            
            html_parts.append(f"""
            <div class="result-card p-4 bg-white rounded-xl border border-gray-100 shadow-sm mb-2">
                <div class="flex items-start gap-3">
                    <div class="pt-1">
                        <input type="checkbox" name="selected_videos" value="{video_id}"
                               class="video-checkbox w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                               data-video-title="{title}" data-video-url="{url}" data-video-author="{author}" data-video-platform="{platform}"
                               checked>
                    </div>
                    <div class="flex-1 min-w-0">
                        <h3 class="font-medium text-gray-800 truncate text-sm">
                            {title}
                        </h3>
                        <div class="flex items-center gap-2 mt-1.5 text-xs text-gray-500">
                            <span class="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 rounded text-gray-600 font-medium">
                                👤 {author}
                            </span>
                            <span class="text-gray-300">|</span>
                            <span>👁 {views_str} 次播放</span>
                            <span class="text-gray-300">|</span>
                            <span>📅 {publish_date}</span>
                        </div>
                    </div>
                    <a href="{url}" target="_blank" rel="noopener"
                       class="shrink-0 px-2.5 py-1 text-xs bg-gray-50 text-gray-500 rounded-lg hover:bg-blue-50 hover:text-blue-600 border border-gray-200 hover:border-blue-200 transition-all">
                        观看 ▸
                    </a>
                </div>
            </div>
            """)
    
    # 收集所有视频 ID 和平台信息
    all_video_ids = []
    all_platforms = []
    for platform, videos in all_results.items():
        if platform not in all_platforms:
            all_platforms.append(platform)
        for v in videos:
            all_video_ids.append(v.get("video_id", ""))
    
    platforms_str = ",".join(all_platforms)
    html_parts.append(f'''
    <div class="mt-6 pt-4 border-t border-gray-200">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
                <label class="text-sm text-gray-600">
                    已选 <span id="selected-count">{total_videos}</span>/{total_videos} 个视频
                </label>
                <button type="button" onclick="toggleAll(true)" class="text-xs text-blue-600 hover:text-blue-800">全选</button>
                <button type="button" onclick="toggleAll(false)" class="text-xs text-blue-600 hover:text-blue-800">全不选</button>
            </div>
            <button type="button" onclick="submitAnalysisMulti('{search_id}')"
                    class="px-5 py-2 bg-gradient-to-r from-violet-600 to-violet-700 text-white rounded-lg hover:from-violet-700 hover:to-violet-800 font-medium transition-all shadow-md text-sm">
                跨平台分析 ({len(all_platforms)} 个平台) →
            </button>
        </div>
    </div>
    <input type="hidden" id="search-ids-{search_id}" value="{''.join(all_video_ids)}">
    <input type="hidden" id="search-platforms-{search_id}" value="{platforms_str}">
    ''')
    
    return '\n'.join(html_parts)


# ── 作者模式搜索 ─────────────────────────────────────────


async def _fetch_author_videos_single(author: str, platform: str, max_videos: int) -> list[dict]:
    """Fetch videos for a single author. Returns list of video dicts."""
    scraper_cls = SCRAPERS.get(platform)
    if not scraper_cls:
        raise ValueError(f"不支持的平台: {platform}")
    scraper = scraper_cls()
    videos = await scraper.fetch_author_videos(author, max_results=max_videos)
    return [
        {
            "title": v.title,
            "author": v.author,
            "url": v.url,
            "views": v.stats.views,
            "publish_time": str(v.publish_time or ""),
            "video_id": v.video_id,
        }
        for v in videos
    ]


@post("/search/author_execute", media_type=MediaType.TEXT)
async def execute_author_search(request: Request) -> str:
    """按作者搜索视频。支持批量（逗号分隔多个作者）。"""
    data = await request.form()
    platform = data.get("platform", "bilibili")
    author_str = data.get("author", "").strip()
    domain = data.get("domain", "").strip()
    max_videos = int(data.get("max_videos", 10))

    if not author_str:
        return '<div class="text-red-500 text-center py-4">请输入作者名称</div>'

    authors = [a.strip() for a in author_str.replace("，", ",").split(",") if a.strip()]

    if not authors:
        return '<div class="text-red-500 text-center py-4">请输入作者名称</div>'

    # 登录检查
    if platform in AUTH_REQUIRED_PLATFORMS:
        scraper = SCRAPERS[platform]()
        try:
            logged_in = await scraper.is_logged_in()
        except Exception:
            logged_in = False
        if not logged_in:
            login_url = "/bilibili-login" if platform == "bilibili" else "/douyin-login"
            plat_name = "Bilibili" if platform == "bilibili" else "抖音"
            return f'''
            <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center" data-slide>
                <div class="text-5xl mb-4 opacity-40">🔒</div>
                <p class="text-lg font-semibold text-gray-700 mb-2">需要先登录 {plat_name}</p>
                <a href="{login_url}" class="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg hover:from-blue-700 hover:to-blue-800 font-medium inline-block text-sm">扫码登录 →</a>
            </div>
            '''

    scraper_cls = SCRAPERS.get(platform)
    if not scraper_cls:
        return f'<div class="text-red-500">不支持的平台: {platform}</div>'

    # Check subscription status for all authors
    from data.manager import DataManager
    dm = DataManager()
    subscribed_authors = set()
    try:
        subs = dm.load_subscriptions(domain or "general")
        for s in subs:
            sa = s.get("author", {})
            if sa.get("platform") == platform:
                subscribed_authors.add(sa.get("name", ""))
    except Exception:
        pass

    try:
        if len(authors) == 1:
            # Single author (original flow)
            author = authors[0]
            log.log("INFO", "web.search", "author_search",
                    f"Author search: author='{author}' platform={platform}")
            video_list = await _fetch_author_videos_single(author, platform, max_videos)
            return _render_author_video_cards(video_list, platform, author, domain, subscribed_authors)
        else:
            # Batch search: search each author, merge results
            log.log("INFO", "web.search", "batch_author_search",
                    f"Batch search: authors={authors} platform={platform}")
            all_html = []
            total_videos = 0
            for i, author in enumerate(authors):
                try:
                    videos = await _fetch_author_videos_single(author, platform, max_videos)
                    if videos:
                        total_videos += len(videos)
                        all_html.append(_render_author_video_cards(videos, platform, author, domain, subscribed_authors, batch_index=i))
                    else:
                        all_html.append(f'<div class="mb-4"><div class="bg-gray-50 rounded-lg p-4 text-center"><p class="text-gray-500">作者 "{author}" 暂无视频</p></div></div>')
                except Exception as e:
                    log.log("ERROR", "web.search", "batch_author_search_error", f"Error searching author '{author}': {e}")
                    all_html.append(f'<div class="mb-4"><div class="bg-red-50 border border-red-200 rounded-lg p-4 text-center"><p class="text-red-600 text-sm">作者 "{author}" 搜索失败: {e}</p></div></div>')

            search_id = uuid.uuid4().hex[:12]
            html = f'''
            <div data-fade>
                <div class="bg-gradient-to-r from-emerald-50 to-teal-50 rounded-xl border border-emerald-200 p-4 mb-4">
                    <div class="flex items-center gap-3">
                        <span class="text-2xl">👥</span>
                        <div>
                            <p class="font-semibold text-gray-800">批量作者搜索结果</p>
                            <p class="text-sm text-gray-600">
                                搜索作者: {", ".join(authors)} · 共找到 <span class="font-semibold text-emerald-700">{total_videos}</span> 个视频
                            </p>
                        </div>
                    </div>
                </div>
                {"".join(all_html)}
            </div>
            '''
            return html

    except Exception as e:
        log.log("ERROR", "web.search", "author_search_error", str(e))
        return f'<div class="text-red-500 p-4 text-center">搜索失败: {e}</div>'


# ── 订阅/取消订阅 API ─────────────────────────────────────


@post("/api/subscribe", media_type=MediaType.JSON)
async def api_subscribe(request: Request) -> dict:
    """订阅作者 (form-encoded: author, platform, domain)."""
    data = await request.form()
    author_name = data.get("author", "").strip()
    platform = data.get("platform", "bilibili").strip()
    domain = data.get("domain", "").strip() or "general"

    if not author_name or not platform:
        return {"success": False, "error": "作者名和平台不能为空"}

    from data.manager import DataManager
    dm = DataManager()
    existing = dm.load_subscriptions(domain)
    for sub in existing:
        sa = sub.get("author", {})
        if sa.get("name") == author_name and sa.get("platform") == platform:
            return {"success": True, "status": "existed", "message": "已关注该作者"}

    new_sub = {
        "id": f"sub_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "author": {"name": author_name, "platform": platform, "url": "", "author_id": None},
        "subscribed_at": datetime.now().isoformat(),
        "score": 0.5,
        "total_analyses": 0,
        "last_monitored_at": None,
        "is_blacklisted": False,
        "tags": [],
        "notes": "",
    }
    existing.append(new_sub)
    dm.save_subscriptions(domain, existing)
    log.log("INFO", "web.search", "subscribe", f"Subscribed '{author_name}' ({platform}) to '{domain}'")
    return {"success": True, "message": f"已关注 {author_name}"}


@post("/api/unsubscribe", media_type=MediaType.JSON)
async def api_unsubscribe(request: Request) -> dict:
    """取消订阅作者 (form-encoded: author, platform, domain)."""
    data = await request.form()
    author_name = data.get("author", "").strip()
    platform = data.get("platform", "bilibili").strip()
    domain = data.get("domain", "").strip() or "general"

    if not author_name or not platform:
        return {"success": False, "error": "作者名和平台不能为空"}

    from data.manager import DataManager
    dm = DataManager()
    existing = dm.load_subscriptions(domain)
    new_list = [sub for sub in existing
                if not (sub.get("author", {}).get("name") == author_name
                        and sub.get("author", {}).get("platform") == platform)]
    if len(new_list) < len(existing):
        dm.save_subscriptions(domain, new_list)
        log.log("INFO", "web.search", "unsubscribe", f"Unsubscribed '{author_name}' ({platform}) from '{domain}'")
        return {"success": True, "message": f"已取消关注 {author_name}"}
    return {"success": False, "error": "未找到该作者"}


def _render_author_video_cards(videos: list[dict], platform: str, author: str, domain: str = "",
                               subscribed_authors: set | None = None, batch_index: int = 0) -> str:
    """渲染作者搜索结果（带关注按钮的卡片）. """
    if not videos:
        return f'<div class="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center"><div class="text-5xl mb-4 opacity-30">📭</div><p class="text-gray-400 text-lg">作者 "{author}" 暂无视频</p></div>'

    search_id = uuid.uuid4().hex[:12]
    is_subscribed = subscribed_authors and author in subscribed_authors

    if is_subscribed:
        subscribe_button = f'''
        <button type="button" onclick="toggleSubscribeAuthor(this, '{author}', '{platform}')"
                class="subscribe-btn px-3 py-1.5 text-xs rounded-lg border font-medium transition-all border-gray-300 text-gray-500 bg-gray-100 hover:bg-gray-200"
                data-author="{author}" data-platform="{platform}" data-subscribed="true">
            ✓ 已关注
        </button>
        '''
    else:
        subscribe_button = f'''
        <button type="button" onclick="toggleSubscribeAuthor(this, '{author}', '{platform}')"
                class="subscribe-btn px-3 py-1.5 text-xs rounded-lg border font-medium transition-all border-blue-300 text-blue-600 bg-blue-50 hover:bg-blue-100"
                data-author="{author}" data-platform="{platform}" data-subscribed="false">
            + 关注
        </button>
        '''

    cards = []
    for v in videos:
        publish_date = str(v.get("publish_time", ""))[:10] or "未知"
        views = v.get('views', 0)
        views_str = f"{views:,}" if isinstance(views, (int, float)) else str(views)
        title = v.get('title', '无标题')
        url = v.get('url', '#')
        video_id = v.get('video_id', '')

        cards.append(f"""
        <div class="result-card p-4 bg-white rounded-xl border border-gray-100 shadow-sm">
            <div class="flex items-start gap-3">
                <div class="pt-1">
                    <input type="checkbox" name="selected_videos" value="{video_id}"
                           class="video-checkbox w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                           data-video-title="{title}" data-video-url="{url}" data-video-author="{author}" data-video-platform="{platform}"
                           checked>
                </div>
                <div class="flex-1 min-w-0">
                    <h3 class="font-medium text-gray-800 truncate text-sm">{title}</h3>
                    <div class="flex items-center gap-2 mt-1.5 text-xs text-gray-500">
                        <span>👁 {views_str}</span>
                        <span class="text-gray-300">|</span>
                        <span>📅 {publish_date}</span>
                    </div>
                </div>
                <a href="{url}" target="_blank" rel="noopener"
                   class="shrink-0 px-2.5 py-1 text-xs bg-gray-50 text-gray-500 rounded-lg hover:bg-blue-50 hover:text-blue-600 border border-gray-200 hover:border-blue-200 transition-all">观看 ▸</a>
            </div>
        </div>
        """)

    video_ids = ",".join(v.get("video_id", "") for v in videos)

    return f'''
    <div data-fade>
        <div class="flex items-center justify-between mb-3 px-1">
            <div class="flex items-center gap-2">
                <label class="text-sm text-gray-600">作者: <strong>{author}</strong></label>
                {subscribe_button}
                <input type="hidden" id="author-domain-{search_id}" value="{domain}">
            </div>
            <div class="flex items-center gap-2">
                <label class="text-sm text-gray-600">已选 <span id="selected-count">{len(videos)}</span>/{len(videos)}</label>
                <button type="button" onclick="toggleAll(true)" class="text-xs text-blue-600 hover:text-blue-800">全选</button>
                <button type="button" onclick="toggleAll(false)" class="text-xs text-blue-600 hover:text-blue-800">全不选</button>
            </div>
            <button type="button" onclick="submitAnalysis('{search_id}')"
                    class="px-5 py-2 bg-gradient-to-r from-violet-600 to-violet-700 text-white rounded-lg hover:from-violet-700 hover:to-violet-800 font-medium transition-all shadow-md text-sm">分析所选 →</button>
        </div>
        <div class="space-y-2" id="search-id-{search_id}">{"".join(cards)}</div>
        <input type="hidden" id="search-ids-{search_id}" value="{video_ids}">
        <input type="hidden" id="search-platform-{search_id}" value="{platform}">
    </div>
    '''
