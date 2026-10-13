# video-analysis — 视频下载、语音转文字与博主观点分析 | Skill + MCP

**video-analysis 是面向 AI 助手的多平台视频分析工具，提供 Agent Skill 和 MCP（Model Context Protocol）STDIO 服务。**
支持 Bilibili（哔哩哔哩 / B站）、YouTube 和抖音的视频搜索、批量下载、字幕提取、
Whisper 本地语音识别与视频转文字，再由当前助手总结内容、比较博主观点，并保存带来源和时间戳的分析报告。
还支持关注列表、UP主最新视频、固定博主研究清单和本地订阅。支持的使用入口是 Skill 与 MCP，Web 前端和项目交互式 CLI 已移除。

Video Analysis is a Python MCP server and Agent Skill for Bilibili, YouTube and Douyin
video search, batch downloading, subtitle extraction, local Whisper speech-to-text,
creator tracking, transcript summarization and evidence-based opinion comparison.

## 使用场景与对话示例

- **B站关注博主分析**：读取关注列表，筛选股票、财经或其他领域的 UP主，获取最近视频并比较观点。
- **视频批量下载与转录**：提供视频链接或作者主页，批量下载媒体，将字幕或语音转换为可读取的文本。
- **固定博主研究**：维护作者清单，按需获取更新，比较各期观点变化、共识、分歧及其依据。
- **学习与内容整理**：总结课程、访谈和行业解读，保留原视频链接、发布时间与转录时间戳。

连接服务并加载 Skill 后，可以向助手提出：

> 分析我在 Bilibili 关注的股票类博主最近的视频，比较他们的行情观点和风险条件。
>
> 下载这几个视频并转成文字，按主题整理要点，给出原视频链接和对应时间戳。
>
> 获取这个博主清单每位作者最近两条视频，比较前后观点是否发生变化。

视频内容和机构转述属于待分析的证据；研究报告会标注转录错误、采集缺口和未独立核验的说法。
股票财经分析用于理解视频观点，不会把博主预测直接当作投资建议。

## A股每日研究与项目展示

新增 [`a-share-daily-review` Skill](skills/a-share-daily-review/SKILL.md)：采集财经博主视频、读取转录、独立核对当日大盘，并对照上一交易日保存的原始判断，形成“昨日判断 → 今日结果 → 观点变化 → 下一交易日观察条件”的日报。

- [公开财经博主来源总表](html/skills/creator-catalog.md)：提供通用作者主页、视频证据和核实状态，不提供个人关注关系；目录不等于全部已转录或验证。
- [静态项目介绍 github.html](github.html)：对外说明研究流程和日报样式，不是旧Web UI，也不提供登录、交易或服务器控制。
- [日报模板](skills/a-share-daily-review/assets/daily-report.md)与[数据/判定口径](skills/a-share-daily-review/references/evidence-and-scoring.md)。

调用示例：`使用 $a-share-daily-review 做今天的A股复盘，核对大盘，验证上一交易日的判断，保存日报和下一交易日观察条件。`

晨间定时示例：每天北京时间08:00调用Skill，复盘前一个已收盘交易日D，获取作者最近6期并筛选相关视频，用D的大盘验证再前一个交易日P的原始判断。周末和节假日沿用最近交易日；已处理记录不重复计分。执行日凌晨的新视频作为盘前补充单列，不混进昨日行情或昨日证据截止窗口。

日报对研究清单中的每位作者分别给出本次观点、此前3—5个已归档交易日观点、变化原因、判断验证和证据状态；再汇总共识、分歧与基准/走强/走弱三种情景下的操作参考，写明触发条件、风险、失效条件与时效。首次历史不足时明确缺口，不补造。

在用户授权每日公开发布后，使用`scripts/publish_daily_report.py --record <归档revision.json> --push`导出原创摘要，追加保存至`html/skills/daily/`，更新`github.html`日报索引，只提交日报、索引与页面并推送GitHub `origin/main`。个人资料、内部转录引用和全文转录不发布；已有用户暂存/页面改动或推送失败时停止并报告，不强推、不推送旧分支。没有新报告不创建空提交。

`save_daily_research` 按日期追加保存JSON与Markdown版本，`get_daily_research` 读取历史记录，`evaluate_daily_forecasts` 冻结今日09:15集合竞价前已保存的上一交易日版本。只有明确定义、单位一致、期限匹配的判断进入自动判定；条件句、模糊判断和缺数据分别标记，不计为预测失败。历史记录晚于今日开盘才导入时不能当成事前成绩。工具不自动获取实时行情，也不自动创建定时任务。

日报存放在 `Paths.root/daily-research/`，与state中的登录资料隔离。公开名单直接提供在`github.html`和`html/skills/`，不需要独立文档目录。维护脚本`scripts/export_creator_catalog.py`默认只刷新公开目录；显式授权读取关注列表后，完整快照仅保存在被Git忽略的`data/private-research/`，发布时过滤非财经账号、个人关注标记和登录资料。

## 核心能力

| 能力 | Bilibili | YouTube | 抖音 |
| --- | --- | --- | --- |
| 视频下载 | 支持 | 支持 | 支持，受签名/验证影响 |
| 字幕或语音转文本 | 支持 | 支持，字幕优先 | 支持，字幕不可用时使用 Whisper |
| 文本分析 | 支持 | 支持 | 支持 |
| 关键片段抽帧复核 | 支持 | 支持 | 支持，前提是视频已成功下载 |

默认工作流程是 **视频采集 → 下载/字幕提取 → 语音转文字 → 文字分析 → 保存报告**。
当前助手读取转录并完成分析，默认路径无需另配分析模型 API Key；Whisper 在本机运行。
抽帧是可选的证据核对步骤，仅在需要检查图表、字幕或演示画面时按转录时间戳执行，依赖 ffmpeg。

## 安装服务

需要 Python 3.10+。在仓库目录创建独立环境并安装：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m playwright install chromium
```

macOS/Linux 将 `.venv/Scripts/python` 换成 `.venv/bin/python`。
Whisper 本地转录另需 `pip install -e ".[transcription]"` 和系统 ffmpeg。
YouTube 的最新 yt-dlp 提取器还需要 Deno 等 JavaScript runtime；Windows 可安装
`winget install DenoLand.Deno`。视频合并需要 ffmpeg，YouTube 字幕优先路径不需要下载完整视频。
默认模型为 `base`，首次转录会下载模型。没有 ffmpeg 时可下载平台提供的
完整单文件格式，部分高画质视频需要 ffmpeg 合并。

## 连接 MCP 与 Skill

仓库包含 `.codex-plugin/plugin.json`、`.mcp.json` 和 `skills/video-analysis/`。
插件清单已按本机 Codex 的插件校验器验证。`.mcp.json` 使用
`video-analysis-mcp` 命令，因此插件模式需要该入口在 Codex 的 PATH 中。
可通过 `pipx install .` 安装独立入口，再在 Codex 本地插件流程中添加本仓库。
仓库没有发布到公共市场；安装 Python 包本身不会自动注册 Codex 插件。

直接连接本地开发环境时，在 Codex MCP 配置中使用绝对 Python 路径：

```toml
[mcp_servers.video_analysis]
command = "C:/path/to/video_analysis/.venv/Scripts/python.exe"
args = ["-m", "mcp_server.server"]
```

然后将 `skills/video-analysis` 目录放入客户端支持的 Skill 目录，或通过
本仓库插件加载它。[官方 MCP 配置说明](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。
配置命令路径需替换成你的实际位置；不依赖 Codex 的当前工作目录。

## 登录与各平台限制

公开视频先尝试匿名访问，**不是所有视频都必须登录**。
收到 `auth_required` 后调用 `start_platform_login`，在专用 Chromium
窗口扫码/密码登录，再调用 `wait_for_platform_login`（每次最多 45 秒）。
无需复制 Cookie。Bilibili 会查询接口确认登录；YouTube 检查登录后的账号按钮；
如果 Playwright Chromium 尚未安装，服务会尝试使用本机 Chrome/Edge 程序，
但仍创建独立配置目录，不读取日常浏览器的登录状态。
抖音仅能检测会话 Cookie，明确标记 `session_detected`，仍需通过实际操作验证。
Google 可能拒绝自动化浏览器登录；平台限流、验证或区域限制也可能在登录后继续存在。
可调用 `validate_platform_cookies` 做本地和平台接口双重检查，不会返回 Cookie 值。

YouTube 登录如果弹出 Windows Hello/通行密钥错误，选择“取消”后使用“试试其他方式”、
密码或手机验证。独立浏览器不能读取日常 Edge/Chrome 配置中的 Passkey；个人浏览器里的
登录状态也不会自动共享给 MCP。若必须复用现有会话，应显式导出受支持的 Cookie 文件并
通过受控导入流程验证，不要把 Cookie 粘贴到聊天或提交到仓库。

| 功能 | Bilibili | YouTube | 抖音 |
| --- | --- | --- | --- |
| 搜索、下载 | API/yt-dlp，完整 MP4 直连回退 | yt-dlp，受地区/验证及运行时影响 | Cookie 实验支持，受签名/验证影响 |
| 作者最新视频 | UID/主页链接 | 频道链接、@handle 或 UC ID；频道 videos 页 | sec_uid/主页链接 |
| 登录后关注 | 关注 API，分页 | 订阅页面可见频道，实验性 | 关注动态中可见作者，实验性 |

实验结果返回 `best_effort=true`、`complete=false`；不能当作完整关注名单。
YouTube 作者显示名可能重名，因此不再用 `from:名字` 猜测频道。

Bilibili 作者视频采集使用 `/x/space/wbi/arc/search`，自动获取 WBI 公共密钥并添加
`wts` / `w_rid` 签名，保留分页及作者、发布时间和原视频链接。旧的未签名作者接口可能
返回 `-799`，即使登录有效也无法采集；服务将请求频率限制归为 `platform_restricted`。
WBI 签名解决本次接口兼容问题，但不能保证所有平台风控都能解除。

抖音关注页目前是页面可见内容的滚动抓取，不是完整的游标分页接口。抖音关键词搜索的
网页接口还可能返回 `invalid_app`/`params_check`（动态设备参数和签名缺失），即使 Cookie
已验证也可能没有结果。遇到这种情况不能把空列表当作“搜索成功”；请改用浏览器内搜索
回退，或直接提供视频 URL 进行下载。

## 批量与分析流程

1. `search_videos` / `get_latest_videos` 获取元数据。每位作者 1–50 条、最多 100 位作者；超过三位作者返回后台任务 ID。
   查询缓存有效期为一小时，要求即时更新时传 `refresh=true`；登录状态变化会隔离缓存。
2. `batch_download` 接受 1–500 个 `{platform,url}`，立即返回 `job_id`。
   `get_job(wait_seconds=30)` 查询进度。默认每批并发 3，每个平台也最多 3。
   每个条目独立记录结果；只有实际生成非空媒体文件才算成功。
3. `batch_transcribe` 接受完整视频元数据，优先字幕，空字幕/失败时使用 Whisper。
   任务结果返回可重复使用的转录 artifact ID。
4. `analyze_videos(artifacts, user_query)` 默认准备当前助手分析。
   转录段落保留 `start`/`end` 时间戳；发现需要视觉验证的时间点后，使用
   `extract_video_frames(media_file, timestamps)` 抽取 1–20 张 JPG 帧。
   助手用 `read_artifact` 分页读取原文、形成结论，再通过 `save_analysis` 保存。
   这不需要额外 API Key。显式选择 `codex`/`claude` 才会调用另行安装的外部分析器。

### 固定博主研究

固定博主不再混入领域配置，单独保存在数据目录的 `watchlists/` 下。调用
`manage_creator_watchlist` 创建或更新清单，每个条目应提供平台和博主主页/频道 URL；
再调用 `research_creator_watchlist` 获取更新。它返回 `videos` 和
`transcription_items`，后者可直接提交给 `batch_transcribe`，然后按
`skills/creator-research/SKILL.md` 的证据规则调用 `analyze_videos` 和 `save_analysis`。
采集、转录、分析是三个明确阶段，部分抓取不会被报告为完整研究。

`get_job` 的 `running` 不是成功；`partial` 表示部分失败。服务重启后的未完成任务
标记为 `interrupted`。可以重新提交失败项，已有媒体文件和转录缓存会复用。
任务不在 MCP 客户端退出后继续后台运行，也不会自动创建定时订阅任务。

其他工具：`manage_subscriptions`、`manage_domain`（创建/查询/更新/发现/监控/复盘）、
`manage_creator_watchlist`、`research_creator_watchlist`、
`extract_video_frames`、
`list_artifacts`、`read_artifact`、`get_overview`、`query_logs`、`get_system_status`。
领域 monitor 返回视频，后续下载/转录由批量工具执行；review 返回本地证据供助手分析。

## 本地数据

默认使用操作系统用户数据目录下的 `video-analysis`。可通过 MCP 的环境变量
`VIDEO_ANALYSIS_DATA_DIR`、`VIDEO_ANALYSIS_STATE_DIR` 指定路径。
`.env.example` 是变量说明，服务不会自动读取仓库 `.env`。

登录资料存放在 state 目录，与可读取的 artifacts 隔离；不要共享 state 目录。
每次下载使用独立 Cookie 文件，避免并发覆盖或跨平台发送 Cookie。
`logout_platform` 会删除该平台专用浏览器配置和所有托管 Cookie，需要先等待活动任务结束。

旧数据可通过 `migrate_legacy_data(directory="旧 data 的绝对路径")` 复制 Cookie、
管道转录和结果；原文件不删除，不覆盖新文件。旧的领域配置/订阅可以通过
`manage_domain`、`manage_subscriptions` 明确导入，避免覆盖当前列表。

## 验证

```powershell
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m pip check
.venv/Scripts/python -m pip wheel . --no-deps -w dist
.venv/Scripts/python scripts/check_wheel.py dist/video_analysis-0.1.0-py3-none-any.whl
```

自动测试使用临时目录、模拟平台响应，包含真实 MCP STDIO 连接和 60 项批量测试，
不调用账号、浏览器登录或真实下载。真实下载验收单独执行：

```powershell
.venv/Scripts/python scripts/live_smoke.py bilibili "https://www.bilibili.com/video/你的BV号"
```

此脚本使用隔离的匿名会话；登录后验收请使用 MCP 工具。测试结论必须区分本地
逻辑通过与平台实际下载成功，不能以工具注册成功代替业务验收。

### 最近验收记录（2026-10-02）

| 验收项目 | 结果与范围 |
| --- | --- |
| 本地自动测试 | 55 项通过，包含 WBI 签名、作者分页、下载缓存、字幕解析、研究清单及 MCP 协议回归 |
| 依赖与安装包 | `pip check`、wheel 构建及隔离目录安装包 STDIO 检查通过，发现 24 个 MCP 工具 |
| Bilibili 登录与关注 | 平台接口确认登录有效，关注列表读取成功 |
| 作者视频采集修复 | 原先失败的 7 位作者通过真实 MCP 全部采集成功，每位 2 条，共 14 条视频元数据；查询缓存通过 |
| 下载与转录 | 前一批 5 条视频均实际下载并完成转录；修复后另验证 1 条新采集视频下载成功；下载和转录缓存均已验证 |
| 内容分析 | 已完成前一批 5 条视频的文字观点分析与报告保存；新增 14 条元数据不等于已经完成转录或分析 |

本轮真实验收集中在 Bilibili，使用完整 MP4 低清直连路径，不代表高画质提取或所有平台均已通过。
此前抖音登录与关注页可见作者读取成功，但关键词搜索返回 `invalid_app`；YouTube 公共下载
仍受地区、验证和 yt-dlp 运行环境影响。这些限制不能由本地测试通过或 Bilibili 验收结果替代。

## 相关关键词 / Keywords

中文：视频分析、视频下载、批量视频下载、视频转文字、语音转文字、字幕提取、视频总结、
博主观点分析、UP主追踪、关注列表、股票财经视频分析、哔哩哔哩、B站、抖音、MCP服务器、Agent Skill。

English: video analysis, video downloader, batch download, video transcription, speech-to-text,
subtitle extraction, video summarization, creator research, creator tracking, Bilibili, YouTube,
Douyin, Whisper, yt-dlp, Python, MCP server, Model Context Protocol, Agent Skills.
