你正在创建一个领域 Skill。

用户意图: Test domain for verification
领域名称: test_domain

参考模板:
# 股票领域 Skill

## 目标
系统性地发现、监控和复盘股票投资领域的视频内容创作者，
追踪其分析质量，积累可信信息来源。

## 工作流

### 1. 发现 (discover)
- 搜索热门股票相关视频
- 使用 search_authors 工具获取作者列表
- 筛选出有潜力的创作者

### 2. 监控 (monitor)
- 定期拉取已订阅作者的最新视频
- 转录并分析内容
- 自动记录分析摘要

### 3. 复盘 (review)
- 评估作者近期分析质量
- 调整评分和订阅状态
- 识别领域趋势变化

## 评分标准
| 维度 | 权重 | 说明 |
|------|------|------|
| 数据引用 | 40% | 是否引用财务数据、行业数据 |
| 逻辑严谨 | 30% | 分析是否有逻辑链条 |
| 预测准确性 | 20% | 历史预测与实际走势对比 |
| 信息新颖 | 10% | 是否提供独特观点 |

## 黑名单条件
- 连续 3 次评分 < 0.3
- 推荐明显违反常识的标的
- 长期无更新

## 工具调用
可使用 [TOOL] 工具名(参数) [/TOOL] 格式调用:
- get_stock_data: 获取股票历史数据
- get_market_sentiment: 获取市场情绪
- search_videos: 搜索视频
- transcribe_video: 转录视频


请生成适配 test_domain 领域的 SKILL.md，使用 YAML frontmatter 格式：
---
name: test_domain-domain
description: Test domain for verification
---

保持与模板相同的工作流结构（发现/监控/复盘），但将内容调整为 test_domain 领域。