# 开发计划

> 状态：Phase 1-7 **全部完成** ✅

---

## 核心原则

1. **Pydantic 驱动**：所有模块间数据交换均使用 Pydantic 模型，确保结构一致、类型安全
2. **抽象基类**：每个模块都有 `base.py` 定义抽象接口，具体实现可替换
3. **模块独立**：scrapers / transcribers / analyzers / cache 相互解耦，通过模型类通信
4. **规则可组合**：筛选、选择逻辑不硬编码，通过可组合的 Rule 系统表达
5. **CLI 优先**：所有功能通过 `python -m cli.main` 统一入口调用

---

## Phase 1: 共享数据模型 ✅

| 文件 | 内容 |
|------|------|
| `models/video.py` | `VideoMetadata`, `VideoStats` |
| `models/transcript.py` | `TranscriptSegment`, `VideoTranscript` |
| `models/search.py` | `SearchQuery`, `SearchResult` |
| `models/analysis.py` | `AnalysisRequest`, `AnalysisResult`, `AnalysisInsight` |
| `models/cache.py` | `CacheEntry`, `CacheStatus` |
| `models/rules.py` | `Rule` 筛选系统（FieldCompare/AuthorIn/KeywordInTitle/DateRange/Sort/And/Or + `SelectorConfig`） |
| `exceptions.py` | `ScraperError`, `TranscriberError`, `AnalyzerError`, `CacheMissError`, `ConfigError`, `RuleEvalError` |
| `config/settings.py` | Pydantic + YAML 配置加载 |

## Phase 2: 抽象基类 ✅

| 文件 | 类 | 方法 |
|------|-----|------|
| `scrapers/base.py` | `BaseScraper` | `fetch_videos`, `fetch_author_videos`, `select`, `search_and_select` |
| `transcribers/base.py` | `BaseTranscriber` | `get_transcript`, `supports` |
| `analyzers/base.py` | `BaseAnalyzer` | `analyze`, `chunk_transcripts` |
| `cache/base.py` | `BaseCache` | `get_video`, `set_video`, `get_query`, `set_query` |

## Phase 3: 具体实现 ✅

### 3.1 Scrapers

| 文件 | 类 | 实现 |
|------|-----|------|
| `scrapers/bilibili.py` | `BilibiliScraper` | B 站搜索 + UP 主视频，调用 B 站公开 API |
| `scrapers/youtube.py` | `YouTubeScraper` | YouTube Data API v3，支持搜索/作者/过滤 |
| `scrapers/douyin.py` | `DouyinScraper` | 抖音公开接口，搜索 + 用户作品 |

### 3.2 Transcribers

| 文件 | 类 | 实现 |
|------|-----|------|
| `transcribers/subtitle_parser.py` | `SubtitleParser` | 从 YouTube 页面提取并解析字幕 XML |
| `transcribers/whisper_client.py` | `WhisperClient` | 本地 OpenAI Whisper 模型（支持 yt-dlp 音频下载） |

### 3.3 Analyzers

| 文件 | 类 | 实现 |
|------|-----|------|
| `analyzers/claude_client.py` | `ClaudeAnalyzer` | **通过 subprocess 调用系统 `claude` CLI**，支持 `--skill` |
| `analyzers/codex_client.py` | `CodexAnalyzer` | **通过 subprocess 调用系统 `codex` CLI** |

### 3.4 Cache

| 文件 | 类 | 实现 |
|------|-----|------|
| `cache/manager.py` | `DiskCache` | JSON 文件缓存，支持 TTL 过期、视频/搜索双层缓存 |

## Phase 4: 调度编排 ✅

| 文件 | 内容 |
|------|------|
| `core/scheduler.py` | `Scheduler`：异步并发控制 + 请求限频 |
| `core/orchestrator.py` | `Orchestrator`：搜索→缓存检查→抓取→转录→分析全流程 |

## Phase 5: CLI + 配置 + Skills ✅

### CLI 入口

| 命令 | 用途 |
|------|------|
| `python -m cli.main search -q "关键词"` | 搜索视频 |
| `python -m cli.main analyze -q "关键词" -p "分析问题"` | 搜索+转录+分析 |
| `python -m cli.main claude -p "prompt" --skill stock-analyst` | 直接调 claude CLI |
| `python -m cli.main claude -i --skill stock-analyst` | claude 交互模式 |
| `python -m cli.main codex -p "prompt"` | 直接调 codex CLI |
| `python -m cli.main list-skills` | 列出内置 skills |

### Skills (`config/skills/`)

| Skill | 用途 |
|-------|------|
| `stock-analyst` | 股票/财经视频分析 |
| `video-analyzer` | 通用视频内容分析 |
| `research-assistant` | 研究助理 |

### Prompt 模板 (`config/prompts/`)

| 文件 | 用途 |
|------|------|
| `analysis.md` | 视频转录分析的 prompt 模板 |
| `summary.md` | 摘要生成的 prompt 模板 |

---

## Phase 6: Skill-Driven Domain Framework ✅

### 完成文件

| 文件 | 内容 |
|------|------|
| `models/domain.py` | DomainConfig, Subscription, BlacklistEntry, AnalysisSummary |
| `tools/__init__.py` | ToolRegistry 类 |
| `tools/general.py` | 通用工具 (subscription, history, scoring) |
| `tools/stock.py` | 股票工具 (get_stock_data, get_market_sentiment) |
| `tools/scraper.py` | 爬虫包装 (search_videos, transcribe_video) |
| `data_manager.py` | DataManager 数据持久化 |
| `engine/__init__.py` | Engine 包 |
| `engine/discover.py` | 发现引擎 |
| `engine/monitor.py` | 监控引擎 |
| `engine/review.py` | 复盘引擎 |
| `engine/domain_manager.py` | 领域管理器 (create/run/list) |
| `cli/main.py` | 扩展 domain 子命令 |
| `config/domains/stock/` | 股票领域模板 (SKILL.md + config.yaml + review.md) |

### 整体目标

从「一次性视频分析管道」演进为 **Skill 驱动的领域智能体框架**：

- **Skill = 领域智能体**（prompt + 工作流 + 工具声明），LLM 加载后自主运行
- **股票是唯一内置领域**，提供完整参考模板
- **其他领域**通过「CLI 向导 + LLM 生成」零代码创建
- **LLM 全自主运行**：加载 Skill 后自主判断何时搜索、监控、复盘
- **工具全局共享**：LLM 按需声明使用，运行时 CLI 从注册表调用执行
- **只存文本**：transcript 全文 + analysis 摘要，不存视频

### 核心架构

```
┌─────────────────────────────────────────────────────────┐
│                    CLI（触发入口）                        │
│  domain create | domain list | monitor | review          │
└──────────────────────┬──────────────────────────────────┘
                       │ 加载 Skill 目录
┌──────────────────────▼──────────────────────────────────┐
│              Domain Skill（领域智能体）                   │
│                                                          │
│  config/domains/{domain}/                                │
│  ├── SKILL.md            ← prompt + 工作流 + 工具声明     │
│  ├── config.yaml         ← 搜索/监控配置                  │
│  └── review.md           ← 复盘模板（可选）                │
│                                                          │
│  Skill 中声明工具名，LLM 自主决定是否调用                  │
│  LLM 输出标记 → CLI 从 registry 调用 → 结果注入继续       │
│  工具调用结果保存用于后续复盘                              │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│         tools/registry.py  ← 工具注册表                   │
│                                                          │
│  tools/                                                  │
│  ├── stock.py           ← 股票工具（注册到 registry）     │
│  ├── general.py         ← 通用工具（订阅/评分/历史）      │
│  └── scraper.py         ← 爬虫包装                       │
└──────────────────────────────────────────────────────────┘
```

### 新增模块

```
项目/
├── 现有（零修改）
│   ├── models / scrapers / transcribers / analyzers /
│   ├── cache / core / cli / config / utils /
│
├── 新增
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py     ← 全局工具注册表
│   │   ├── stock.py        ← 股票工具
│   │   ├── general.py      ← 通用工具（订阅/评分/历史）
│   │   └── scraper.py      ← 爬虫包装
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── domain_manager.py  ← 领域管理（create / run / skill 解析）
│   │   ├── discover.py        ← 发现（搜索 → 候选 → 订阅）
│   │   ├── monitor.py         ← 监控（拉取 → 转录 → 分析 → 保存）
│   │   └── review.py          ← 复盘（Skill + LLM → 决策 → 报告）
│   ├── models/
│   │   └── domain.py          ← DomainConfig / Subscription / BlacklistEntry
│   └── cli/
│       └── main.py            ← 扩展子命令

config/
└── domains/                    ← 领域 Skill 目录
    ├── stock/                  ← 唯一内置，完整参考模板
    │   ├── SKILL.md
    │   ├── config.yaml
    │   └── review.md
    ├── crypto/                 ← 由 LLM 生成
    │   ├── SKILL.md
    │   ├── config.yaml
    │   └── review.md
    └── ...                     ← 更多领域由 LLM 生成

data/
├── {domain}/
│   ├── subscriptions.json      # 订阅状态 + 评分
│   ├── blacklist.json          # 黑名单
│   ├── tools/                  # 工具调用结果
│   │   └── {tool_name}_YYYYMMDD.json
│   ├── transcripts/
│   │   └── {author_slug}/
│   │       └── {YYYY-MM-DD}_{video_id}.txt  # 全文
│   ├── analysis/
│   │   └── {author_slug}.json  # 分析摘要
│   └── review/
│       └── {YYYY-MM-DD}.md     # 复盘报告
```

### 领域 Skill 结构（以 stock 为例）

**SKILL.md**：

```markdown
---
name: stock-domain
description: 股票/财经领域智能体。自动发现、监控、复盘。
---

# 股票领域智能体

## 工作流

### 1. 发现（Discover）
- 按 config.yaml 中的 discovery 配置搜索
- 搜索视频文本（一次性分析）
- 搜索作者（进入订阅系统）
- 输出候选作者列表

### 2. 监控（Monitor）
- 遍历所有活跃订阅
- 获取每人最新视频
- 转录 + 分析 + 保存全文
- 更新 last_monitored_at

### 3. 复盘（Review）
- 加载订阅状态和历史分析
- 按需调用工具获取更多信息
- 评估作者质量
- 输出评分调整、黑名单建议、领域趋势

## 可用工具

- search_videos(platform, keywords)
- search_authors(platform, keywords)
- get_author_latest_videos(platform, author, since)
- transcribe_video(url, platform)
- analyze_content(text)
- get_author_history(author)
- get_author_score(author)
- get_stock_data(symbol, start, end)
- get_domain_trends(days)
- update_score(domain, author, score)
- blacklist_author(domain, author, reason)

## 评分规则
- 内容相关性强：+0.1~+0.2
- 分析深度足：+0.05~+0.1
- 错误预测：-0.1~-0.2
- 低质/广告：-0.2~-0.3
```

**config.yaml**：

```yaml
discovery:
  author_search:
    - platform: bilibili
      keywords: ["股票分析", "A股", "美股", "投资"]
      max_results: 20
    - platform: youtube
      keywords: ["stock analysis", "stock market", "investing"]
      max_results: 20
  video_search:
    - platform: bilibili
      keywords: ["股票", "基金", "财经"]
      max_results: 10

monitor:
  max_videos_per_author: 3
  transcription_method: whisper

review:
  interval_days: 7
  blacklist_threshold: -0.6
```

### 工具注册表

```python
class ToolRegistry:
    """全局工具注册表，所有 Skill 共享"""
    _registry = {}

    @classmethod
    def register(cls, name, func): ...
    @classmethod
    def call(cls, name, **kwargs): ...
    @classmethod
    def list_all(cls): ...

@ToolRegistry.register("get_stock_data")
def get_stock_data(symbol, start, end):
    """获取股票历史价格"""

@ToolRegistry.register("get_author_history")
def get_author_history(author):
    """获取作者历史分析摘要"""
```

### 工具调用流程

```
1. LLM 在执行 Skill 时自主判断需要调用工具
2. LLM 在输出中用特定格式标记工具调用，例如:
   [TOOL]get_stock_data(symbol="AAPL", start="2025-01-01", end="2025-06-01")[/TOOL]
3. CLI 捕获标记，从 registry 执行工具，获取结果
4. 结果保存到: data/{domain}/tools/{tool_name}_YYYYMMDD.json
5. 结果重新注入 prompt，LLM 继续执行
```

### Skill 创建流程（CLI 向导 + LLM 生成）

```
用户: python -m cli.main domain create crypto

CLI 交互式向导:
  [领域名称]: crypto
  [描述]: 加密货币领域监控
  [平台]: bilibili, youtube
  [关键词]: 比特币, crypto, blockchain, ETH
  [参考模板]: stock

→ CLI 将用户输入 + stock 模板传给 LLM
→ LLM 生成: SKILL.md + config.yaml + review.md
→ CLI 写入: config/domains/crypto/
→ 输出: "crypto 领域已创建，可以开始使用！"
```

### CLI 命令设计

```bash
# 领域管理
python -m cli.main domain create              # 交互式创建（向导 + LLM 生成 Skill）
python -m cli.main domain list                # 列出所有领域
python -m cli.main domain show stock          # 显示领域配置

# 发现
python -m cli.main discover stock             # 按配置搜索新作者
python -m cli.main discover stock -n "关键词"  # 自定义关键词

# 订阅
python -m cli.main sub list --domain stock    # 列出订阅
python -m cli.main sub add stock -n "老李" -u "URL" -p bilibili  # 添加
python -m cli.main sub blacklist stock "张三"  # 拉黑
python -m cli.main sub score stock "老李" 0.8  # 手动打分

# 监控（LLM 自主运行）
python -m cli.main monitor stock              # 拉取所有订阅作者最新视频并分析
python -m cli.main monitor stock --author "老李"  # 只监控指定作者

# 复盘（用户触发，LLM 自主决策）
python -m cli.main review stock               # 按 Skill 定义执行复盘
python -m cli.main review stock --force       # 强制复盘

# 查看
python -m cli.main history --domain stock     # 查看分析历史
python -m cli.main reports --domain stock     # 复盘报告列表
```

### 数据存储策略

- **只存文本**：transcript 全文（txt）+ analysis 摘要（json），不存视频
- **按领域隔离**：`data/{domain}/` 下一级目录
- **工具调用结果保存**：`data/{domain}/tools/{tool_name}_YYYYMMDD.json`
- **格式**：全部 JSON / Markdown，不引入 SQLite

### 实施阶段

```
Phase 6.1 — 模型 + 存储
  ├── models/domain.py          ← DomainConfig / Subscription / BlacklistEntry
  ├── tools/registry.py         ← 工具注册表
  ├── tools/general.py          ← 通用工具（订阅/评分/历史）
  └── utils/storage.py          ← JSON 读写

Phase 6.2 — 工具实现
  ├── tools/stock.py            ← 股票工具
  └── tools/scraper.py          ← 爬虫包装

Phase 6.3 — 领域管理 + Skill 解析
  ├── engine/domain_manager.py  ← 领域管理（create / run / skill 解析）
  └── engine/review.py          ← 复盘引擎（含工具调用解析）

Phase 6.4 — 核心引擎
  ├── engine/discover.py        ← 发现引擎
  └── engine/monitor.py         ← 监控引擎

Phase 6.5 — CLI 扩展
  ├── cli/main.py               ← 扩展 domain/sub/discover/monitor/review/history/reports
  └── config/domains/stock/     ← 股票领域完整参考模板

Phase 6.6 — 验证
  └── 手动跑通股票领域全流程：create → discover → sub → monitor → review
```

### 关键设计决策

| 取舍点 | 选择 | 原因 |
|---|---|---|
| 工具调用 | LLM 自主判断→输出标记→CLI 捕获执行→注入结果 | 无需 MCP，LLM 自主性强 |
| 工具结果 | 运行时保存，供后续复盘使用 | 减少重复调用 |
| Skill 创建 | CLI 向导收集意图 → LLM 生成 | 用户输入关键信息，LLM 补全 |
| 工具共享 | 全局 registry，Skill 按需声明 | 避免重复代码 |
| 股票领域 | 唯一内置参考模板 | 提供完整范式，其他领域参考生成 |
| 其他领域 | 全由 LLM 创建 | 零代码修改，灵活度高 |
| 存储 | JSON + Markdown 文件 | 无依赖，LLM 可直接读取 |
| 复盘触发 | 用户手动触发 → LLM 自主决策 | 用户掌握节奏 |

### 与现有代码的关系

| 现有模块 | 关系 |
|---|---|
| `scrapers/` | 不变，通过 `tools/scraper.py` 包装调用 |
| `transcribers/` | 不变，通过 `tools/` 中间层调用 |
| `analyzers/` | 不变，`engine/review.py` 复用 |
| `cache/` | 不变，继续使用 |
| `core/orchestrator.py` | 保留，一次性分析仍可用 |
| `cli/main.py` | 扩展，不改原有命令 |
| `models/` | 不变，新增 `domain.py` |
| `config/settings.py` | 不变 |
| `config/skills/` | 不变，review 使用独立 prompt |
| `config/prompts/` | 不变 |

---

## 执行顺序

```
✅ Phase 1 (模型 + Rule 系统)
→ ✅ Phase 2 (抽象基类)
→ ✅ Phase 3.4 (Cache)
→ ✅ Phase 3.1 (Scrapers)
→ ✅ Phase 3.2 (Transcribers)
→ ✅ Phase 3.3 (Analyzers)
→ ✅ Phase 4 (编排)
→ ✅ Phase 5 (CLI + Skills + 配置)
→ ✅ Phase 6.1 (模型 + 存储)
→ ✅ Phase 6.2 (工具实现)
→ ✅ Phase 6.3 (领域管理 + Skill 解析)
→ ✅ Phase 6.4 (核心引擎)
→ ✅ Phase 6.5 (CLI 扩展 + 股票模板)
→ ✅ Phase 7.1 (Litestar 基础架构)
→ ✅ Phase 7.2 (核心页面 dashboard + search)
→ ✅ Phase 7.3 (数据展示 results + transcripts)
→ ✅ Phase 7.4 (领域管理页面)
→ ✅ Phase 7.5 (图表可视化 ECharts)
→ ✅ Phase 7.6 (WebSocket 进度占位)
→ ✅ Phase 7.7 (数据层统一 + 架构修复)
```

---

### 修复记录

#### 2026-07: 数据层统一 + 架构修复

| 问题 | 修复 | 影响文件 |
|------|------|---------|
| Domain 和 Pipeline 数据使用两套不同读写方式 | 统一到 `data/manager.py`，`data_manager.py` 保持向后兼容 | `data/manager.py`, `data_manager.py`, `tools/general.py`, `engine/*` |
| log 模块使用 threading.local 导致异步上下文丢失 | 改用 `contextvars.ContextVar` | `log/__init__.py` |
| ReviewEngine 只生成 prompt.md 不执行 LLM | 直接调 `claude CLI` + 解析评分/黑名单输出 + 自动更新订阅 | `engine/review.py` |
| 同步工具函数中嵌套事件循环 | `_run_async()` 辅助函数检测并避免嵌套 | `tools/scraper.py` |
| DataManager 方法使用 `**kwargs` 缺乏类型保护 | 改为明确参数（`domain`, `author`, `video_id` 等） | `data/manager.py` |
| 外部脚本 `python -m cli.main` 报 ModuleNotFoundError | 统一用 `sys.path.insert(0, ...)` + 直接 import | `tests/run_external.py` |

## Phase 7: 前端界面 ✅

### 完成文件

| 文件 | 内容 |
|------|------|
| `web/__init__.py` | Web 包初始化 |
| `web/config.py` | Web 配置 (host, port) |
| `web/app.py` | Litestar 应用入口 |
| `web/routers/search.py` | 搜索路由 |
| `web/routers/domains.py` | 领域管理路由 |
| `web/routers/results.py` | 结果路由 |
| `web/routers/transcripts.py` | 转录路由 |
| `web/routers/charts.py` | 图表数据 API |
| `web/routers/ws.py` | WebSocket 进度占位 |
| `web/views/base.html` | 基础布局 (Tailwind + HTMX) |
| `web/views/dashboard.html` | 仪表盘 (ECharts 图表) |
| `web/views/search.html` | 搜索页 |
| `web/views/domains.html` | 领域管理页 |
| `web/static/css/style.css` | 自定义样式 |
| `web/static/js/charts.js` | 图表 JS |

### CLI 扩展

```bash
# 启动 Web 界面
python -m cli.main web            # 默认 localhost:8080
python -m cli.main web --port 9090

# 日志系统
python -m cli.main logs --tail 20
python -m cli.main logs --stats
```

### Phase 7.7 — 数据层统一 + 架构修复 ✅

| 文件 | 变更 |
|------|------|
| `data/manager.py` | 统一 DataManager（domain + pipeline 持久化） |
| `data_manager.py` | 保持向后兼容 → `from data.manager import DataManager` |
| `log/__init__.py` | threading.local → contextvars.ContextVar |
| `engine/review.py` | 自动调用 claude CLI + 解析评分/黑名单 + 更新订阅 |
| `tools/scraper.py` | `_run_async()` 避免嵌套事件循环 |
| `tests/run_external.py` | 统一测试脚本，无 Docker 依赖 |
