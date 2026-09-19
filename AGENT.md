# AGENT.md - AI Agent & Developer Guidelines

This document provides guidelines, constraints, and instructions for any AI Agent or developer working on or interacting with the **Video Scraping, Transcription, LLM Analysis Framework with Skill-Driven Domain Management**.

---

## 🛠️ Development & Coding Standards

1. **Language & Environment**: Python 3.10+.
2. **Type Hints**: All new functions and methods must have type annotations.
3. **Asynchronous Execution**:
   - Scraping tasks (especially when requesting multiple videos) should leverage asynchronous programming (`asyncio` and `httpx`) to improve performance.
   - Limit concurrency per platform to prevent rate-limiting or IP blocks.
4. **Error Handling**:
   - Never raise raw exceptions. Use domain-specific exceptions (e.g., `ScraperError`, `TranscriberError`, `AnalyzerError`).
   - If a whisper transcription fails, fall back gracefully to cache or skip, and log the failure. Do not crash the entire batch pipeline.
5. **Model-Driven**: All module-to-module communication must use Pydantic models. Never pass raw `dict` objects between modules.
6. **Abstract First**: All extensible modules (scrapers, transcribers, analyzers, cache) must implement their abstract base class defined in `base.py`.

---

## 🧠 Domain Framework (Phase 6+)

The project now supports **Skill-Driven Domain Agents** that autonomously discover, monitor, and review content creators.

### Architecture

```
CLI (domain create/list/discover/monitor/review)
  ↓
Domain Skill (SKILL.md + config.yaml + review.md)
  ↓
Tools Registry (14 tools, auto-registered)
  ↓
Engines: Discover | Monitor | Review
```

### Tools Registry

All tools are auto-registered via `@ToolRegistry.register` decorator. Import `tools` to trigger registration:

```python
from tools import ToolRegistry

# List all tools
ToolRegistry.list_all()  # ['get_stock_data', 'search_videos', 'search_authors', ...]

# Call a tool
result = ToolRegistry.call("get_stock_data", symbol="600519", start="2025-01-01")
```

Available tools (14 total):
| 工具 | 用途 |
|------|------|
| `get_stock_data` | 获取股票历史价格数据 |
| `get_market_sentiment` | 获取市场情绪（涨停跌停数） |
| `search_videos` | 搜索视频（包装现有 scraper） |
| `search_authors` | 搜索作者（从视频结果中提取） |
| `get_author_latest_videos` | 获取作者最新视频 |
| `transcribe_video` | 转录视频（YouTube/B站） |
| `get_author_history` | 获取作者历史分析摘要 |
| `get_author_score` | 获取作者评分 |
| `get_subscriptions` | 列出订阅 |
| `update_subscription_score` | 更新订阅评分 |
| `blacklist_author` | 拉黑作者 |
| `get_domain_trends` | 获取领域趋势 |
| `get_domain_reports` | 获取复盘报告 |
| `get_volume_trends` | 获取领域内视频播放量趋势 |

### Engines

| 引擎 | 文件 | 用途 |
|------|------|------|
| `DiscoverEngine` | `engine/discover.py` | 通过搜索发现候选作者 |
| `MonitorEngine` | `engine/monitor.py` | 拉取订阅作者最新视频，转录并分析 |
| `ReviewEngine` | `engine/review.py` | 加载数据，构建复盘 prompt，解析 LLM 输出 |
| `DomainManager` | `engine/domain_manager.py` | 领域创建/运行/LLM 生成 Skill 文件 |

### Domain Structure

```
config/domains/{name}/
├── SKILL.md          ← prompt + 工作流 + 工具声明
├── config.yaml       ← 搜索/监控配置
└── review.md         ← 复盘模板（可选）

data/{name}/
├── subscriptions.json   ← 订阅状态 + 评分
├── blacklist.json       ← 黑名单
```

Stock domain is the reference template at `config/domains/stock/`.

---

## 💾 Caching Rules

Every scraping and transcribing action **must** check the cache first.
- **Cache Hit Check**: Query the `cache.manager` using `{platform}_{video_id}` before invoking scrapers or whisper.
- **Data Integrity**: Ensure cached transcripts have metadata attached (source platform, timestamp, video title, author, duration).
- **Cache Update**: Write back to cache immediately after successful Whisper transcription or metadata retrieval.

---

## 🗄️ Data Persistence (DataManager)

统一 `DataManager` 类位于 `data/manager.py`，向后兼容层在 `data_manager.py`。

### 领域数据 (domain)
```
data/{domain}/
├── subscriptions.json   ← 订阅作者列表（含评分、标签、最后监控时间）
├── blacklist.json       ← 黑名单作者
├── transcripts/{author}/{video_id}.txt ← 转录全文
├── analysis/{author}.json ← 分析摘要
└── review/{date}.md     ← 复盘报告
```

### 管道数据 (pipeline)
```
data/
├── transcripts/{platform}/{video_id}_title.md ← 转录文件
├── results/{skill}/{timestamp}_query.md ← 分析结果
└── logs/YYYY-MM-DD.jsonl ← 按日期分割的结构化日志
```

Use `DataManager` class for all data access:
```python
from data_manager import DataManager  # 向后兼容层
# 或 from data.manager import DataManager

dm = DataManager()
# 领域方法
subs = dm.load_subscriptions("stock")
dm.save_transcript_text("stock", "老李", "bv123", "转录全文...")

# 管道方法 (VideoTranscript / AnalysisResult 对象)
from models.transcript import VideoTranscript
from models.analysis import AnalysisResult
dm.save_transcript(transcript_obj)
dm.save_result(result_obj)
```

---

## 🧪 Testing Constraints

- **Mocking**: When writing tests for scrapers or LLM analyzers, do not make live API requests or scrape real URLs. Use mocks/fixtures.
- **Whisper Testing**: Use a small test audio file (under 2 seconds) or mock the Whisper model response for unit/integration tests to avoid long execution times.
- **Analyzer Testing**: LLM analyzers call system `claude`/`codex` CLI via subprocess. Tests should mock `asyncio.create_subprocess_exec` and `subprocess.call`.

---

## 🔧 Skills

### Project Skills (config/skills/)
Built-in Claude-compatible skills for one-off analysis:
- `stock-analyst` — 股票/财经视频分析
- `video-analyzer` — 通用视频内容分析
- `research-assistant` — 研究助理

```bash
# Use with Claude CLI
claude --skill config/skills/stock-analyst/SKILL.md -p "prompt"

# Or via project CLI
python -m cli.main claude --skill stock-analyst -p "prompt"
```

### Domain Skills (config/domains/)
Each domain has its own SKILL.md for autonomous agent behavior:
```bash
# List domains
python -m cli.main domain --list

# Discover new authors
python -m cli.main domain discover -n stock

# Monitor subscribed authors
python -m cli.main domain monitor -n stock

# Run review (LLM evaluates author quality)
python -m cli.main domain review -n stock
```

---

## 🌐 Web Interface (Phase 7+)

A Litestar + HTMX + Tailwind CSS web UI is available:

```bash
# Start web server
python -m cli.main web            # localhost:8080
python -m cli.main web --port 9090
```

Pages:
- `/` — Dashboard (statistics, ECharts charts, recent activity)
- `/search` — Video search with platform selection
- `/results` — Analysis results listing
- `/transcripts` — Transcript browsing
- `/domains` — Domain management (create, monitor, review)

---

## 📁 Project Structure

```
models/             — Pydantic data models + Rule system
scrapers/           — BaseScraper → BilibiliScraper, YouTubeScraper, DouyinScraper
transcribers/       — BaseTranscriber → SubtitleParser, WhisperClient
analyzers/          — BaseAnalyzer → ClaudeAnalyzer, CodexAnalyzer
cache/              — BaseCache → DiskCache (JSON file, TTL)
core/               — Scheduler (concurrency/rate-limit) + Orchestrator (pipeline)
cli/                — Main entry: search / analyze / claude / codex / domain / web / list-skills
engine/             — Domain framework: DiscoverEngine, MonitorEngine, ReviewEngine, DomainManager
tools/              — ToolRegistry + stock/scraper/general tools
data_manager.py     — JSON file-based persistence for domains
web/                — Litestar + HTMX + Tailwind web UI
config/
├── skills/         — Project skills (stock-analyst, video-analyzer, ...)
├── prompts/        — Prompt templates
└── domains/        — Domain skills (stock/ is the reference template)
data/
└── {domain}/       — Per-domain: subscriptions, blacklist, transcripts, analysis, review
```
