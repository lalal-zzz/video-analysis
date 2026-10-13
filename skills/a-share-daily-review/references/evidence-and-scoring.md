# 日报数据与事前判断核验

## 运行工具

现有采集工具：`manage_creator_watchlist`、`research_creator_watchlist`、`batch_transcribe`、`get_job`、`analyze_videos`、`read_artifact`。大盘行情需要由助手的网页/行情工具提供；本MCP不内置实时交易所行情接口。`save_daily_research`不会自动补齐指标。

新增归档接口：

- `save_daily_research(record)`：保存新版本，返回revision、saved_at与report_path。
- `get_daily_research(trading_date="", revision="latest", limit=30)`：空日期列出已记录日期，传日期读取，传revision读取冻结版本。
- `evaluate_daily_forecasts(previous_trading_date, market)`：读取上一交易日，在今日09:15集合竞价前已保存的最后一个版本，比较目标日期为今日的规则。

日期均ISO格式。所有时间要带时区；A股默认 `+08:00`。必须使用真实来源链接和真实时间，不复制示例数值当作行情。

## record

| 字段 | 内容 |
|---|---|
| trading_date | 本日报日期，例如 YYYY-MM-DD |
| cutoff_at | 报告证据截止时间，带时区，不能晚于保存时刻 |
| market | 下述独立行情证据 |
| report | 完整Markdown正文 |
| transcript_artifacts | 已存在且非空的 transcripts/*.json ID列表 |
| forecasts | 下一交易日或明确未来目标日的原始判断 |
| coverage | 名称/UID → ok、no_update、auth_required、platform_restricted、failed、sampled 等说明 |
| gaps | 未核实的事实、未成功转录、抽样缺口与来源冲突 |

字段拼写必须与MCP模型一致，未定义字段会拒绝。验证的数值有限，不能为NaN/Infinity。报告日期与market日期必须一致。forecast对应的转录必须列在transcript_artifacts中；内容证据在转录中保留而非由作者标题猜测。

## market

| 字段 | 内容 |
|---|---|
| trading_date | 与record相同的目标日期 |
| is_trading_day | 已查过交易日历的boolean |
| stage | preopen / intraday / close / holiday |
| previous_trading_date / next_trading_date | 核实后的相邻交易日，可缺失；评估必须给previous |
| calendar_source_url | 核实休市安排的来源URL |
| metrics | 指标名 → {value, unit, source_url, observed_at, note} |
| gaps | 未能取得的市场数据 |

推荐保持固定指标名，不要每日报告改键：

| 指标 | 建议单位 | 口径 |
|---|---|---|
| sh_close / sz_close / chinext_close / csi300_close | points | 对应指数收盘点位 |
| sh_change_pct / sz_change_pct / chinext_change_pct / csi300_change_pct | pct | 1.2表示1.2%，不使用0.012 |
| turnover_cny_100m | CNY_100m | 两市成交金额，万元/亿元/万亿元先统一 |
| advancers / decliners / unchanged | count | 写清沪深或沪深北、是否剔除ST |
| limit_up / limit_down | count | 写清收盘封板或触板、是否含ST/新股 |

盘中与收盘数据不混用。自动收盘评估要求指标observed_at为目标日上海时间15:00后；这是最小时间校验，助手仍要核实数据确为收盘值。收盘点位和当日涨跌幅不能互相代替。行业/个股目标必须给对应指标，不能拿沪指结果验证科技板块涨跌。

## forecasts

每条判断保留：id、creator、creator_url、source_url、source_published_at、transcript_artifact、timestamp_seconds、statement、target_trading_date。最后一项须晚于日报日期，不能将今日已发生的事实保存成下一交易日预测。

source_url必须对应转录中的同一个视频，timestamp_seconds必须落在非空segment内；转录已有publish_time时，source_published_at必须与它一致。平台元数据的无时区时间按服务所返回的上海本地时间解释为+08:00，不能为绕过截止限制改日期。外部摘要只能成为待核实线索，不能替代这一引用链。

可自动判定的额外字段：

- scorable=true；metric、unit、operator、threshold必填。
- operator可为gt/gte/lt/lte/between。between包含上下边界，并要求upper。
- condition留空；有条件的自然语言原话设置scorable=false。
- scorable=false时not_scorable_reason必填，例如“没有量化涨幅阈值”“预测期限不明确”“尚需独立核对触发条件”。

“沪指下一个交易日收涨”可以事前映射到 `sh_change_pct`、`pct`、`gt`、0，前提是转录确有明确方向/期限。不能把“科技值得关注”翻译成“创业板明天涨超过1%”。用中性语言观察场景，不为提高计分覆盖而改写预测。

## 防止事后改写

每次save产生新revision，旧文件保留。评估冻结前一交易日、今日09:15前已保存的最后一版。所有昨日内容若都在今日开盘后才导入，baseline_status=late_record，不计作事前记录；有原始视频发布时间仍可做人工历史回顾，但应披露它未提前归档。

返回missing表示没有昨日记录；frozen表示有可用基线。日历必须明确市场previous_trading_date等于请求的基线日期；国庆后不能按自然日前一天比较。

自动结果：hit / miss / pending / not_scorable / missing_data / incompatible_unit。pending覆盖未收盘、休市；缺数据和单位冲突不计为错误。条件触发、因果解释正确与否另写人工核查列，并给实际触发证据。未到目标日的判断在历史中保留，不丢弃。

数值命中只能说明定义的结果条件成立，不能证明其理由成立或能产生投资收益。不从多条判断中挑选最有利规则，也不让同一讲者多个转载重复增加样本。

## 持续发现

按盘前、午评、盘后、周评、指数ETF、公司研究等关键词扩展。优先解析唯一主页/UID；核实最近若干交易日的视频主题、发布时间与原创关系。新作者先进入候选池，保留来源链接、核对日、更新频率证据和排除原因；使用人数和粉丝数不代表可靠度。

全量池与每日预算分开维护。报告声明本日抽样规则，轮换补充较小或不同观点的来源，避免固定只看一个方向。公开展示不得声称所有候选已完成转录或所有平台验证成功，不提供用户关注关系或非财经个人偏好。
