# analyze-stock — 视频搜索、转录、LLM 分析框架

从 Bilibili、YouTube、抖音等平台搜索视频、转录字幕，通过系统已安装的 Claude/Codex CLI 进行深度分析。

---

## 🚀 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 列出内置 skills
python -m cli.main list-skills

# 搜索视频
python -m cli.main search -q "特斯拉股票" -p bilibili -n 10

# 搜索 + 转录 + 分析（全自动）
python -m cli.main analyze -q "白酒板块" -p "分析这些视频的投资观点" --skill stock-analyst

# 直接用 claude CLI + skill
python -m cli.main claude -i --skill stock-analyst

# 用 codex 分析视频转录
python -m cli.main codex -q "AI芯片" -p "总结对AI芯片市场的判断"
```

## ✨ 功能

- **多平台搜索**：Bilibili、YouTube、抖音
- **自动缓存**：搜索和视频转录本地缓存，避免重复
- **视频转录**：YouTube 字幕解析 + 本地 Whisper 模型
- **Rule 筛选系统**：按播放量、作者、日期、关键词组合筛选
- **Claude / Codex CLI 集成**：直接调用系统已安装的 Claude/Codex CLI，支持 `--skill`
- **项目内置 Skills**：`config/skills/` 下的 skill 可被 Claude CLI 直接识别

## 📁 项目结构

```
analyze_stock_-master/
├── cli/                          # CLI 入口
│   ├── main.py                   # 命令: search / analyze / claude / codex / list-skills
│   └── __init__.py
├── models/                       # Pydantic 数据模型
│   ├── video.py                  # VideoMetadata, VideoStats
│   ├── transcript.py             # TranscriptSegment, VideoTranscript
│   ├── search.py                 # SearchQuery, SearchResult
│   ├── analysis.py               # AnalysisRequest, AnalysisResult
│   ├── cache.py                  # CacheEntry, CacheStatus
│   ├── rules.py                  # Rule 筛选系统 (FieldCompare/AuthorIn/KeywordInTitle/DateRange/Sort/And/Or)
│   └── __init__.py
├── scrapers/                     # 视频爬虫
│   ├── base.py                   # BaseScraper (抽象基类)
│   ├── bilibili.py               # BilibiliScraper
│   ├── youtube.py                # YouTubeScraper (Data API v3)
│   ├── douyin.py                 # DouyinScraper
│   └── __init__.py
├── transcribers/                 # 视频转录
│   ├── base.py                   # BaseTranscriber (抽象基类)
│   ├── subtitle_parser.py        # SubtitleParser (YouTube 字幕)
│   ├── whisper_client.py         # WhisperClient (本地 Whisper 模型)
│   └── __init__.py
├── analyzers/                    # LLM 分析 (调用系统 CLI)
│   ├── base.py                   # BaseAnalyzer (抽象基类)
│   ├── claude_client.py          # ClaudeAnalyzer (调用 claude CLI)
│   ├── codex_client.py           # CodexAnalyzer (调用 codex CLI)
│   └── __init__.py
├── cache/                        # 缓存管理
│   ├── base.py                   # BaseCache (抽象基类)
│   ├── manager.py                # DiskCache (JSON 文件缓存)
│   └── __init__.py
├── core/                         # 调度编排
│   ├── scheduler.py              # 并发控制 + 限频
│   ├── orchestrator.py           # 搜索→缓存→转录→分析全流程
│   └── __init__.py
├── config/                       # 配置与技能
│   ├── settings.py               # Pydantic 配置加载
│   ├── settings.yaml             # 全局配置 (需自行创建)
│   ├── prompts/                  # LLM 提示词模板
│   │   ├── analysis.md           # 视频分析 prompt 模板
│   │   └── summary.md            # 摘要 prompt 模板
│   └── skills/                   # Claude 兼容 Skills
│       ├── stock-analyst/        # 股票/财经视频分析
│       │   └── SKILL.md
│       ├── video-analyzer/       # 通用视频内容分析
│       │   └── SKILL.md
│       └── research-assistant/   # 研究助理
│           └── SKILL.md
├── exceptions.py                 # 领域异常定义
├── pyproject.toml                # 项目依赖与配置
├── README.md                     # 本文件
├── DEV_PLAN.md                   # 开发计划
└── CLAUDE.md                     # Claude 分析指导
```

## 💻 命令参考

### `search` — 搜索视频

```bash
python -m cli.main search -q "关键词" \
  -p bilibili \           # bilibili | youtube | douyin
  -n 10 \                 # 最大结果数
  -a "作者名" \           # 限定作者
  --min-views 1000 \      # 最低播放量
  --sort views \          # relevance | publish_time | views
  --date-from 2025-01-01 \
  --date-to 2025-06-01 \
  --transcribe \          # 同时转录
  -o result.json          # 输出到文件
```

### `analyze` — 搜索 + 转录 + 分析

```bash
python -m cli.main analyze \
  -q "AI 芯片" \
  -p "这些视频对 AI 芯片市场前景怎么看？" \
  -p bilibili \
  -n 5 \
  --skill stock-analyst \    # 使用内置 skill
  -o analysis.md
```

### `claude` — 直接调用系统 Claude CLI

```bash
# 单次 prompt
python -m cli.main claude -p "帮我总结以下视频观点..."

# 搜索视频 + 自动转录 + 传给 claude
python -m cli.main claude \
  -q "特斯拉股票" \
  -p "分析这些视频的投资观点" \
  --skill stock-analyst

# 交互模式
python -m cli.main claude -i --skill stock-analyst
```

### `codex` — 直接调用系统 Codex CLI

```bash
# 单次 prompt
python -m cli.main codex -p "总结一下..."

# 搜索视频 + 自动转录 + 传给 codex
python -m cli.main codex \
  -q "市场分析" \
  -p "总结观点"
```

### `list-skills` — 列出内置 Skills

```bash
python -m cli.main list-skills
```

## 🧩 Skills

项目内置 Claude 兼容 Skills，位于 `config/skills/`：

| Skill | 用途 |
|-------|------|
| `stock-analyst` | 股票/财经视频分析，提取市场观点和投资洞察 |
| `video-analyzer` | 通用视频内容分析，提取洞察、对比观点 |
| `research-assistant` | 研究助理，多角度信息梳理和分析 |

Claude CLI 使用时自动从项目内加载：
```bash
claude --skill config/skills/stock-analyst/SKILL.md
```

## 📋 依赖

| 依赖 | 用途 |
|------|------|
| `pydantic>=2.0` | 数据模型 |
| `pyyaml>=6.0` | 配置解析 |
| `httpx>=0.27` | 网络请求 |
| **可选**: `openai-whisper` | 本地语音转录 |
| **可选**: `yt-dlp` | YouTube 音频下载 |
| **必须**: `claude` CLI | 系统已安装的 Claude CLI |
| **可选**: `codex` CLI | 系统已安装的 Codex CLI |

## 🔧 配置

复制 `settings.yaml` 模板后修改：

```bash
cp config/settings.yaml.template config/settings.yaml
```

```yaml
cache:
  storage_dir: cache/storage
  video_ttl_hours: 72
  query_ttl_hours: 24

scraper:
  max_concurrency: 3
  request_delay_seconds: 1.0

transcriber:
  whisper_model: whisper-large-v3
  device: cpu
  language: zh

analyzer:
  claude_api_key: ""
  codex_api_key: ""
  default_model: claude
```

## 📝 Prompt 模板

项目内 `config/prompts/` 提供分析提示词模板，可在 `settings.yaml` 中配置路径：

```yaml
prompt_templates:
  analysis: config/prompts/analysis.md
  summary: config/prompts/summary.md
```

## 🧪 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/

# 外部集成测试（无 Docker，自动填充/清理数据）
python tests/run_external.py              # 完整集成（数据层 + ToolRegistry + Web 路由）
python tests/run_external.py --no-web     # 跳过 Web 路由测试
python tests/run_external.py --fresh      # 从空数据开始

# 类型检查
mypy .
```
