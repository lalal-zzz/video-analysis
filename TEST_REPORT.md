# 修正与验收记录（2026-09-19）

## 本地验收

- 独立 `.venv` 安装 `.[dev]` 成功，`pip check` 无依赖冲突。
- `python -m pytest -q`：**35 passed**。包括恢复后的核心 Mock 流水线、
  真实 MCP STDIO 连接、60 项任务并发/部分失败、登录校验、Cookie 域隔离、
  登录后缓存隔离、退出清理、空字幕回退、转录/分析文件通路及路径边界。
- 官方本机 Skill/Plugin 校验脚本：通过（不是仅 JSON 语法检查）。
- Wheel 构建成功；`scripts/check_wheel.py` 在临时目录安装该 wheel，
  通过隔离解释器确认 `cache/config/log/exceptions/data_manager` 等来自安装包，
  并真实启动 STDIO、发现 20 个工具、调用系统状态成功。
- Playwright 使用本机浏览器程序、独立临时 profile，以 headless 模式实际启动成功。
  未使用用户日常浏览器 profile；该项不等同于扫码登录成功。
- Playwright Chromium 下载停在 0 字节，已停止该次安装任务；程序已提供
  Chrome/Edge 独立 profile 回退。可在网络恢复后重试标准浏览器安装。

## 匿名真实平台检查

使用 `scripts/live_smoke.py`，与用户登录会话隔离。

| 平台 | 测试链接/操作 | 本次结果 |
| --- | --- | --- |
| Bilibili | BV1xx411c7mD、BV1GJ411x7h7 | yt-dlp 未完成下载；对 BV1GJ411x7h7 的直连接口检查返回 HTTP 412 |
| YouTube | BaW_jenozKc、jNQXAC9IVRw | 提取器返回 This video is unavailable，没有生成可验证媒体文件 |
| 抖音 | 6961737553342991651（yt-dlp 内置测试链接） | 提取器要求 Cookie，返回 auth_required |

这次没有证明三个平台的真实下载均已成功。程序会如实返回失败类别，不把
失败或空文件记作成功，也不把所有错误都归因于没有登录。
账号登录后的关注列表、下载可用性仍需用户扫码后用可播放视频链接验收。
尤其 Google 可能拒绝自动化浏览器登录；抖音会话检测及关注动态抓取仍为实验功能。

## 本次修正要点

- 校正 Plugin manifest 类型及展示字段，补齐 Python 包模块和资源。
- 登录、搜索、媒体下载和转录共用域隔离的 Cookie store，退出不留托管 Cookie。
- 登录按平台验证；Bilibili 用户 ID Cookie 单独存在不再算登录成功。
- 批量任务持久化进度，支持部分成功、进程中断状态、已下载文件/转录缓存复用。
- 多作者查询保留逐作者错误；YouTube 使用频道上传页而不是 from:显示名搜索。
- Bilibili 关注分页固定页大小，防止尾页重复/遗漏。
- 字幕为空时进入 Whisper；转录产生可读取 artifact，当前助手可分析并保存结果。
- 补回核心测试，去掉依赖真实账号/仓库样例数据的默认测试方式。
- 清理旧 Web 辅助脚本和过时使用说明；保留核心库与已有用户数据。

运行方式见 README；本报告不是全平台或全部账号可用性的保证。
