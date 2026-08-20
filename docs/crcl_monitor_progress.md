# CRCL 监控体系 — 进度跟踪

> Goal 状态文件。规范见 docs/CRCL监控体系.md。
> 更新：2026-08-20

## 完成项

- [x] git pull origin main（远端有新增：scripts/schedule/*, scripts/signal_history.py 等）
- [x] 监控规范文档复制到 docs/CRCL监控体系.md
- [x] 数据源可达性验证（见下表，全部通过，免费无 key）
- [x] 后端：crcl_db / crcl_collect / crcl_alerts / api/v1/crcl.py + 启动自动采集钩子（main.py lifespan）
- [x] 前端：CrclMonitor.vue 五区页面 + 路由 + Sidebar 菜单；vue-tsc + vite build 通过
- [x] 告警 fixture 测试：黄×2/红/确认 全部通过（backend/tests/test_crcl_alerts.py）
- [x] 端到端验证：SSE 手动刷新全链路、启动自动采集（07:51 日志）、页面截图五区齐全
- [x] 无回归：pytest golden 6 passed；/derived/monthly、/signals 正常

## 数据源状态表（2026-08-20 实测）

| 指标域 | 渠道 | 端点/接口 | 状态 | 备注 |
|---|---|---|---|---|
| 稳定币总盘 + USDC 流通量 | DefiLlama | GET https://stablecoins.llama.fi/stablecoins?includePrices=false | ✅ | peggedAssets 数组含 circulating.peggedUSD；历史曲线用 /stablecoincharts/all 或单币历史端点（待实现时确认） |
| 短端美债收益率 | Treasury.gov CSV | https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv | ✅ | 列含 "3 Mo"/"6 Mo"/"1 Yr" 等；注意 api.fiscal.treasury.gov JSON 端点实测不可用，弃用 |
| CRCL 日线 OHLCV | akshare | ak.stock_us_daily(symbol='CRCL') | ✅ | 实测返回至 8/19 收盘 78.59 |
| CRCL 市值/估值 | yfinance | Ticker('CRCL').info | ✅ | marketCap/trailingPE/forwardPE/priceToSales 等字段齐全 |
| FOMC/监管/CPN/Arc 里程碑 | 手工维护 JSON | 待建 data/crcl_events.json | ⏳ | 文本卡片，标注来源与日期 |
| 季报拆解（收入结构/EPS/分发成本） | 手工维护 JSON | 待建 data/crcl_fundamentals.json | ⏳ | 每季度财报后人工更新 |

## 已知问题 / 决策记录

1. **P/E 口径分歧**：yfinance trailingPE=14.4（trailingEps 5.47 含一次性项目），WSJ 口径 ~44.9。页面展示时标注数据源为 Yahoo Finance，并在图表说明中提示口径差异；前瞻 P/E(49.4) > TTM P/E(14.4) 的方向性结论不受影响。
2. **利率 API 选型**：fiscaldata JSON API 实测返回空，改用 home.treasury.gov 年度 CSV（按年取数，跨年需拼接 2025/2026 两个文件）。
3. 告警规则引擎的 fixture 测试放在 backend/tests/，与现有 test_golden.py 并列。

## 实施记录（2026-08-20 完成）

1. 数据层 ✅ — crcl_monitor.db 独立库；metric_points/snapshot/alerts/collect_log 四表
2. API ✅ — /crcl/{overview,metrics,events,alerts,logs,fundamentals,refresh,refresh/stream}
3. 前端 ✅ — 五区：KPI 瓦 / 四图表 / 事件时间线 / 告警面板+手工数据 / 日志表
4. 告警 ✅ — 5 规则；真实数据触发 y_usdc_growth（同比 7.4% < 15%）
5. 自动采集 ✅ — lifespan 后台线程；CRCL_STARTUP_COLLECT=0 可关（测试用）

## 遗留 / 维护事项

- 每季度财报后更新 data/crcl_fundamentals.json（quarters + flags）
- 事件日历维护 data/crcl_events.json（FOMC 日期标注待核实的需以 Fed 官方日历核实）
- annual.distribution_cost_ratio_pct 待对照 2024 年报核实后填入（当前 y_distribution_cost 规则为 insufficient_data）
- akshare 新浪端点偶发不可达，已实现 yfinance 备用源自动切换
