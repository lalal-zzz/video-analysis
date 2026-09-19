# video-analysis — Skill + MCP

通过对话处理 Bilibili、YouTube、抖音视频：搜索、多个作者更新、关注列表、
批量下载、转录、分析及本地订阅。Web 前端和项目 CLI 已移除。

## 安装服务

需要 Python 3.10+。在仓库目录创建独立环境并安装：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m playwright install chromium
```

macOS/Linux 将 `.venv/Scripts/python` 换成 `.venv/bin/python`。
Whisper 本地转录另需 `pip install -e ".[transcription]"` 和系统 ffmpeg。
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
   助手用 `read_artifact` 分页读取原文、形成结论，再通过 `save_analysis` 保存。
   这不需要额外 API Key。显式选择 `codex`/`claude` 才会调用另行安装的外部分析器。

`get_job` 的 `running` 不是成功；`partial` 表示部分失败。服务重启后的未完成任务
标记为 `interrupted`。可以重新提交失败项，已有媒体文件和转录缓存会复用。
任务不在 MCP 客户端退出后继续后台运行，也不会自动创建定时订阅任务。

其他工具：`manage_subscriptions`、`manage_domain`（创建/查询/更新/发现/监控/复盘）、
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
```

自动测试使用临时目录、模拟平台响应，包含真实 MCP STDIO 连接和 60 项批量测试，
不调用账号、浏览器登录或真实下载。真实下载验收单独执行：

```powershell
.venv/Scripts/python scripts/live_smoke.py bilibili "https://www.bilibili.com/video/你的BV号"
```

此脚本使用隔离的匿名会话；登录后验收请使用 MCP 工具。测试结论必须区分本地
逻辑通过与平台实际下载成功，不能以工具注册成功代替业务验收。

最近一次真实验收：Bilibili 登录、Cookie 验证和关注列表读取成功；抖音登录、Cookie
验证和关注页可见作者读取成功，但关键词搜索返回 `invalid_app`，因此未伪造搜索结果或
继续下载。YouTube 的公共视频下载仍受地区、验证和 yt-dlp 可用性影响；Google 登录的
Passkey 错误属于浏览器账号验证限制，不代表 Cookie 验证接口失败。
