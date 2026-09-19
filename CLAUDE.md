# CLAUDE.md — 项目上下文与使用指南

## 项目概述

**analyze-stock** 是一个视频搜索、转录、LLM 分析框架，演进为 **Skill-Driven Domain Framework**：
- Phase 1-5: 视频搜索 + 转录 + Claude/Codex 分析管道
- Phase 6: Skill-Driven Domain Framework（领域智能体）
- Phase 7: Litestar + HTMX + Tailwind CSS Web 界面

## 核心架构

```
Phase 1-5: 视频分析管道
  SearchQuery → Scraper → Transcriber → Analyzer → AnalysisResult

Phase 6+: Domain Framework
  CLI (domain) → Skill.md + config.yaml → ToolRegistry → Engines (Discover/Monitor/Review)

Phase 7+: Web UI
  Browser ← HTMX → Litestar (routes) → Engines / DataManager / ToolRegistry
```

## CLI 使用

```bash
# ── Phase 1-5: 视频分析 ──
python -m cli.main search -q "特斯拉" -p bilibili -n 10
python -m cli.main analyze -q "白酒板块" -p "分析投资观点" --skill stock-analyst
python -m cli.main claude -i --skill stock-analyst
python -m cli.main codex -p "总结以下"
python -m cli.main list-skills

# ── Phase 6: 领域管理 ──
python -m cli.main domain discover -n stock      # 发现候选作者
python -m cli.main domain monitor -n stock       # 监控订阅作者（依赖网络）
python -m cli.main domain review -n stock        # 执行复盘（自动调 LLM + 更新评分/黑名单）

# ── Phase 7: Web 界面 ──
python -m cli.main web --port 8080

# ── 日志系统 ──
python -m cli.main logs --tail 20            # 查看最近日志
python -m cli.main logs --stats              # 查看统计摘要
python -m cli.main logs --level ERROR        # 筛选级别
python -m cli.main logs --pipeline discover  # 筛选管道
python -m cli.main logs --follow             # 自动跟随

# ── 外部测试（无 Docker） ──
python tests/run_external.py                  # 完整集成测试（数据层 + ToolRegistry + Web 路由）
python tests/run_external.py --no-web         # 跳过 Web 路由测试
python tests/run_external.py --fresh          # 从空数据开始测试
```

## Skills 使用

### 项目 Skills（一次性分析）
`config/skills/` — Claude CLI 可直接加载：
- `stock-analyst` — 股票/财经视频分析
- `video-analyzer` — 通用视频内容分析
- `research-assistant` — 研究助理

```bash
python -m cli.main claude -q "AI芯片" --skill stock-analyst
```

### 领域 Skills（自治智能体）
`config/domains/{name}/SKILL.md` — 每个领域有独立的 SKILL.md，LLM 加载后自主决定何时搜索/监控/复盘。
Stock 是唯一内置参考模板：`config/domains/stock/`

## 工具注册表 (ToolRegistry)

所有工具通过 `@ToolRegistry.register` 自动注册，Import `tools` 即触发：

```python
from tools import ToolRegistry
ToolRegistry.list_all()    # 14 tools
ToolRegistry.call("get_stock_data", symbol="600519")  # 调用工具
```

工具分类：
- **股票**: `get_stock_data`, `get_market_sentiment`
- **爬虫包装**: `search_videos`, `search_authors`, `get_author_latest_videos`, `transcribe_video`
- **通用**: `get_author_history`, `get_author_score`, `get_subscriptions`, `update_subscription_score`, `blacklist_author`, `get_domain_trends`, `get_domain_reports`, `get_volume_trends`

## 数据模型（Pydantic）

### 视频分析管道
| 模型 | 用途 |
|------|------|
| `VideoMetadata` | 视频元数据 |
| `TranscriptSegment` | 单段转录（start, end, text） |
| `VideoTranscript` | 完整转录 |
| `SearchQuery` / `SearchResult` | 搜索请求/结果 |
| `AnalysisRequest` / `AnalysisResult` | 分析请求/结果 |

### 领域框架
| 模型 | 文件 | 用途 |
|------|------|------|
| `DomainConfig` | `models/domain.py` | 领域配置 |
| `Subscription` | `models/domain.py` | 订阅作者 |
| `BlacklistEntry` | `models/domain.py` | 黑名单 |
| `AnalysisSummary` | `models/domain.py` | 分析摘要 |
| `LogEntry` | `models/log.py` | 结构化日志条目 |

## 数据存储（DataManager）

统一 `DataManager` 类位于 `data/manager.py`，向后兼容层位于 `data_manager.py`。

### 领域数据（domain）
```
data/{domain}/
├── subscriptions.json    ← 订阅状态 + 评分
├── blacklist.json        ← 黑名单
├── transcripts/          ← 转录全文 (.txt)
├── analysis/             ← 分析摘要 (.json)
└── review/               ← 复盘报告 (.md)
```

### 管道数据（pipeline）
```
data/
├── transcripts/          ← 转录文件 (.md)
├── results/              ← 分析结果 (.md)
└── logs/
    └── YYYY-MM-DD.jsonl  ← 按日期分割的结构化日志
```

```python
from data_manager import DataManager  # 向后兼容
# 或
from data.manager import DataManager  # 直接导入

dm = DataManager()
# 领域方法
subs = dm.load_subscriptions("stock")
dm.save_transcript_text("stock", "老李", "bv123", "转录全文...")
# 管道方法
from models.transcript import VideoTranscript
dm.save_transcript(transcript_obj)
from models.analysis import AnalysisResult
dm.save_result(result_obj)
```

## 模块结构

```
models/         — Pydantic 数据模型 + Rule 系统 + 领域模型 (domain.py)
scrapers/       — BaseScraper → BilibiliScraper, YouTubeScraper, DouyinScraper
transcribers/   — BaseTranscriber → SubtitleParser, WhisperClient
analyzers/      — BaseAnalyzer → ClaudeAnalyzer, CodexAnalyzer
cache/          — BaseCache → DiskCache
core/           — Scheduler + Orchestrator
cli/            — CLI 入口（search/analyze/claude/codex/domain/web/list-skills/logs）
engine/         — DiscoverEngine, MonitorEngine, ReviewEngine, DomainManager
tools/          — ToolRegistry + stock.py, scraper.py, general.py
web/            — Litestar app, routers, Jinja2 templates, static files
log/            — 结构化日志系统（LogEntry + JSONL 持久化 + contextvars pipeline_context）
data/manager.py — 统一数据管理器（domain + pipeline 持久化）
data_manager.py — 向后兼容层 → data/manager.py
config/
├── skills/     — 项目 skills
├── prompts/    — Prompt 模板
└── domains/    — 领域 Skills（stock/ 为参考模板）
data/
├── {domain}/   — 按领域隔离的数据
├── transcripts/— 管道转录文件 (.md)
├── results/    — 管道分析结果 (.md)
└── logs/       — 结构化日志 JSONL
```

## Rule 筛选系统

```python
from models.rules import FieldCompareRule, DateRangeRule, SortRule, SelectorConfig

selector = SelectorConfig(rules=[
    FieldCompareRule(field="views", operator="gte", value=10000),
    DateRangeRule(after=datetime(2025, 1, 1)),
    SortRule(sort_by="views", top_n=10),
])
```

## 缓存机制

- 视频缓存：key=`video:{platform}:{video_id}`，JSON 文件，TTL 默认 72h
- 搜索缓存：key=`query:{search_params}`，TTL 默认 24h
- 自动去重，重复搜索/转录直接命中缓存

## 关键修复记录

### 2026-07: 数据层统一 + 架构修复
1. **DataManager 统一**：`data/manager.py` 同时提供 domain 和 pipeline 持久化，`data_manager.py` 保持向后兼容
2. **Log contextvars 修复**：`pipeline_context` 使用 `ContextVar` 替代线程局部变量，支持异步嵌套上下文
3. **ReviewEngine 自动执行 LLM**：不再只生成 prompt.md，直接调用 `claude CLI` 执行复盘并解析结果 → 更新评分/黑名单
4. **异步安全**：同步工具函数通过 `_run_async()` 运行协程，避免嵌套事件循环
5. **DataManager 参数直接传递**：方法接收明确参数（如 `domain`, `author`），不再使用 `**kwargs`
6. **外部脚本导入修复**：`tests/run_external.py` 使用 `sys.path.insert(0, ...)` + `from cli.main import ...` 而非 `python -m`

## 开发规范

- Python 3.10+，所有函数需类型注解
- 异步优先（asyncio + httpx）
- 禁止原始异常，使用领域异常
- 所有模块通过 Pydantic 模型通信，不直接传递 dict
- Scrapers/Transcribers/Analyzers 通过抽象基类解耦
- 新增代码不修改现有模块（Phase 1-5 零修改）
- 外部脚本用 `sys.path.insert(0, PROJECT_ROOT)` + 直接 import，不用 `python -m`
