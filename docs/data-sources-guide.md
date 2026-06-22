# 金融数据接入指南

> **用途**：本文档汇总 PanWatch 项目（股票监控）和 AKShare 项目（宏观经济分析）的数据源，供后续项目快速参考"哪些数据可从哪些接口获取"。
>
> **适用范围**：A 股/港股/美股实时行情、K 线、新闻资讯、资金流向、中国宏观经济指标。

---

## 一、PanWatch 数据源（股票监控）

PanWatch 项目直连 HTTP API 获取数据（**未使用 akshare 库**，虽然文件名含 `akshare_collector` 但实际已替换为腾讯接口）。

### 1.1 实时行情（股票报价）

**数据源：腾讯股票 HTTP API**

| 项目 | 详情 |
|---|---|
| **接口 URL** | `http://qt.gtimg.cn/q=` |
| **编码** | GBK |
| **请求方式** | HTTP GET（多代码拼接，`~` 分隔返回）|
| **支持市场** | A 股、港股、美股 |
| **返回字段** | 当前价、昨收、开盘、成交量、涨跌额、涨跌幅、最高、最低、成交额、换手率、市盈率、流通市值、总市值、量比 |
| **文件位置** | `src/collectors/akshare_collector.py`（类名 `AkshareCollector`，实际用腾讯接口）|
| **辅助模块** | `src/collectors/market_http.py`（通用 HTTP 请求封装，支持按 host 节流、退避重试、短 TTL 缓存）|

**示例请求**：
```
http://qt.gtimg.cn/q=sh600519,sz000001,hk00700
```
返回格式（`~` 分隔）：
```
v_sh600519="51~贵州茅台~600519~1800.50~1790.00~...";
v_sz000001="51~平安银行~000001~12.50~12.40~...";
```

**局限性**：
- 仅实时报价，无历史 K 线
- GBK 编码需特殊处理
- 无官方文档，接口可能变动

---

### 1.2 K 线数据（OHLC 蜡烛图）

**数据源：腾讯 + 东方财富 + Stooq（美股备用）**

#### 腾讯接口（主路径）

| 项目 | 详情 |
|---|---|
| **接口 URL** | `http://web.ifzq.gtimg.cn/appstock/app/fqkline/get` |
| **请求参数** | `param={标的代码},day,,,{天数},qfq`（前复权）；`_var=kline_dayqfq` |
| **返回格式** | JS 变量格式 JSON，解析 `data.{标的}.day` 或 `data.{标的}.qfqday` |
| **返回字段** | 数组，每条 `[日期, 开盘, 收盘, 最高, 最低, 成交量]` |
| **复权方式** | `qfq`（前复权）/ `hfq`（后复权）|
| **文件位置** | `src/collectors/kline_collector.py` |

**示例请求**：
```
http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,100,qfq&_var=kline_dayqfq
```

#### 东方财富接口（A 股/港股长历史 + 指数）

| 项目 | 详情 |
|---|---|
| **接口 URL** | `https://push2his.eastmoney.com/api/qt/stock/kline/get` |
| **请求参数** | `secid={市场}.{代码}`（如 `1.000001`）；`klt=101`（日K）；`fqt=1`（前复权）；`lmt={条数}`；`end=20500101`；`fields1/fields2`（字段集）；`ut={验证token}` |
| **返回格式** | JSON，提取 `data.klines` 数组 |
| **返回字段** | 逗号分隔字符串 `"YYYY-MM-DD,开盘,收盘,最高,最低,成交量,..."` |
| **适用场景** | A 股/港股长历史（>1000 条）+ 指数（如上证指数 `1.000001`）|

**示例请求**：
```
https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000001&klt=101&fqt=1&lmt=100&end=20500101&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&ut=b2884a393a59ad64002292a3e90d46a5
```

#### Stooq 接口（美股备用）

| 项目 | 详情 |
|---|---|
| **接口 URL** | `https://stooq.com/q/d/l/` |
| **请求参数** | `s={股票代码}.us`（如 `aapl.us`）；`i=d`（日线）|
| **返回格式** | CSV 文本，表头 `Date,Open,High,Low,Close,Volume` |
| **适用场景** | 美股历史数据（腾讯/东方财富无覆盖时）|

**示例请求**：
```
https://stooq.com/q/d/l/?s=aapl.us&i=d
```

**局限性**：
- 腾讯接口历史有限（通常 <1000 条），长历史需东方财富
- 东方财富接口需固定 token（`ut` 参数），可能过期
- Stooq 仅美股，且有请求频率限制

---

### 1.3 新闻资讯

**数据源：雪球 + 东方财富（2 个 API）**

#### 雪球（个股新闻聚合）

| 项目 | 详情 |
|---|---|
| **接口 URL** | `https://xueqiu.com/statuses/stock_timeline.json` |
| **认证** | 需登录 cookie（`xq_a_token`）|
| **请求参数** | `symbol={股票代码}`；`count={条数}` |
| **返回字段** | JSON，含 `user_id`、`id`、`text`（新闻内容）、`created_at` |
| **文章链接** | `https://xueqiu.com/{user_id}/{id}` |
| **适用场景** | 个股新闻（资讯 + 公告）|
| **启用条件** | 需配置 cookie，默认禁用 |

#### 东方财富搜索（按关键词/股票搜新闻）

| 项目 | 详情 |
|---|---|
| **接口 URL** | `https://search-api-web.eastmoney.com/search/jsonp` |
| **请求参数** | `keyword={股票名称/关键词}`；`type=0`（新闻）；`pi={页码}`；`ps={每页条数}` |
| **返回格式** | JSONP（需去除 callback 包裹）|
| **支持市场** | A 股、港股、美股 + 行业/主题关键词（如"新能源汽车"）|
| **文章链接** | `https://finance.eastmoney.com/a/{code}.html` |
| **启用条件** | 默认启用 |

**示例请求**：
```
https://search-api-web.eastmoney.com/search/jsonp?keyword=贵州茅台&type=0&pi=1&ps=10
```

#### 东方财富公告（上市公司公告批量查询）

| 项目 | 详情 |
|---|---|
| **接口 URL** | `https://np-anotice-stock.eastmoney.com/api/security/ann` |
| **请求参数** | `stock_code={6位A股代码}`；`page_index={页码}`；`page_size={每页条数}` |
| **返回格式** | JSON，含 `art_code`（公告ID）、`title`、`publish_date` |
| **公告链接** | `https://data.eastmoney.com/notices/detail/{symbol}/{art_code}.html` |
| **适用场景** | 仅 A 股（6 位数字代码）|
| **启用条件** | 默认启用 |

**示例请求**：
```
https://np-anotice-stock.eastmoney.com/api/security/ann?stock_code=600519&page_index=1&page_size=10
```

**局限性**：
- 雪球需登录 cookie，个人用需自配
- 东方财富 JSONP 需去除 callback 包裹
- 公告接口仅 A 股

---

### 1.4 资金流向（主力/北向资金）

**数据源：东方财富 API**

| 项目 | 详情 |
|---|---|
| **接口 URL** | `https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get` |
| **请求参数** | `secid={市场}.{代码}`；`klt=101`（日K）；`lmt=0`（全部）；`fields1=f1,f2,f3,f7`；`fields2=f51-f65`；`ut={验证token}`；`_={毫秒时间戳}` |
| **返回格式** | JSON，提取 `data.klines` 数组 |
| **返回字段** | 逗号分隔，索引含义：`0:日期, 1:主力净额, 2:小单净额, 3:中单净额, 4:大单净额, 5:超大单净额, 6:主力占比, 7:小单占比, 8:中单占比, 9:大单占比, 10:超大单占比, 11:收盘价, 12:涨跌幅, 13:成交量, 14:成交额` |
| **适用场景** | A 股/港股/美股资金流向历史 |
| **文件位置** | `src/collectors/capital_flow_collector.py` |

**示例请求**：
```
https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid=1.600519&klt=101&lmt=0&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&ut=b2884a393a59ad64002292a3e90d46a5&_=1234567890
```

**局限性**：
- 需固定 token（`ut` 参数），可能过期需更新
- 仅日 K 资金流（无分钟级）

---

## 二、AKShare 项目数据源（宏观经济指标）

本项目使用 **akshare 库**（开源 Python 金融数据接口）采集中国宏观经济指标，存储到 SQLite（`data/macro_data.db`）。

### 2.1 akshare 函数清单（17 个）

| akshare 函数 | 数据内容 | 频率 | 数据范围 | 存储表 |
|---|---|---|---|---|
| `ak.macro_china_supply_of_money()` | 货币供应 M0/M1/M2（含同比）| 月 | 1978–至今 | `money_supply` |
| `ak.macro_china_gdp()` | GDP 绝对值 + 同比增速 | 季 | 2000–至今 | `gdp` |
| `ak.macro_china_cpi_yearly()` | CPI 同比 | 月 | 1986–至今 | `cpi` |
| `ak.macro_china_cpi_monthly()` | CPI 环比 | 月 | 1996–至今 | `cpi` |
| `ak.macro_china_ppi_yearly()` | PPI 同比 | 月 | 1995–至今 | `ppi` |
| `ak.macro_china_pmi_yearly()` | PMI 官方制造业 | 月 | 2005–至今 | `pmi` |
| `ak.macro_china_cx_pmi_yearly()` | PMI 财新制造业 | 月 | 2012–至今 | `pmi` |
| `ak.macro_china_non_man_pmi()` | PMI 非制造业 | 月 | 2007–至今 | `pmi` |
| `ak.macro_china_cx_services_pmi_yearly()` | PMI 财新服务业 | 月 | 2012–至今 | `pmi` |
| `ak.macro_cnbs()` | 宏观杠杆率（CNBS 分部门）| 季 | 1992–至今 | `leverage` |
| `ak.macro_china_shrzgm()` | 社会融资规模增量 | 月 | 2015–至今 | `social_finance` |
| `ak.macro_china_lpr()` | LPR 利率（1Y/5Y）| 月 | 2013–至今 | `lpr` |
| `ak.macro_china_gyzjz()` | 工业增加值同比 + 累计 | 月 | 2008–至今 | `industrial` |
| `ak.macro_china_new_house_price()` | 70 城房价指数（新建/二手）| 月 | 2011–至今 | `house_price` |
| `ak.macro_china_new_financial_credit()` | 新增人民币贷款 | 月 | 2008–至今 | `new_credit` |
| `ak.macro_china_nbs_nation()` | NBS 通用接口（人口/收入/城镇化率）| 年 | 2000–至今 | `household_income` / `demographics` |
| `ak.bond_china_yield()` | 中债国债收益率曲线 | 日 | 2002–至今 | `bond_yield` |

**文件位置**：`scripts/01_fetch_data.py`（采集）+ `scripts/02_compute_derived.py`（衍生指标计算）

---

### 2.2 数据表结构

#### 原始表（13 张）

| 表名 | 行数（典型）| 关键字段 | 频率 |
|---|---|---|---|
| `money_supply` | 581 | date, m0, m1, m2, m0_yoy, m1_yoy, m2_yoy | 月 |
| `gdp` | 21 | date, gdp_abs, gdp_yoy | 季（实际年度）|
| `cpi` | 475 | date, cpi_yoy, cpi_mom | 月 |
| `ppi` | 361 | date, ppi_yoy | 月 |
| `pmi` | 321 | date, pmi_official, pmi_caixin, pmi_non_mfg, pmi_caixin_svc | 月 |
| `leverage` | 80 | date, household, non_fin_corp, gov_total, gov_central, gov_local | 季 |
| `social_finance` | 136 | date, total, rmb_loan, entrusted_loan, trust_loan, ... | 月 |
| `lpr` | 1534 | date, lpr_1y, lpr_5y | 月（实际日频，月频聚合）|
| `industrial` | 201 | date, ip_yoy, ip_cumulative | 月 |
| `house_price` | 1840 | date, city, new_yoy, new_mom, new_base, used_yoy, ... | 月 |
| `new_credit` | 221 | date, new_rmb_loan | 月 |
| `household_income` | 30 | date, income_per_capita, population_10k, income_abs | 年 |
| `bond_yield` | 5000+ | date, y_1y, y_3y, y_5y, y_7y, y_10y, y_30y | 日 |

#### 衍生表（2 张）

| 表名 | 来源 | 关键字段 |
|---|---|---|
| `derived_monthly` | 月度主表合并（581 行 × 30 列）| m2_m1_spread, real_rate, pmi_ma6, ip_trend, sf_stock_yoy, sf_impulse, loan_yoy, ... |
| `derived_quarterly` | 季度主表（GDP + 杠杆率）| gdp_yoy_smooth, household_change, gov_change, corp_change |

---

### 2.3 使用示例

#### Python 直接调用 akshare

```python
import akshare as ak
import pandas as pd

# 货币供应 M2
df = ak.macro_china_supply_of_money()
print(df[["统计时间", "货币和准货币（广义货币M2）", "货币和准货币（广义货币M2）同比增长"]].tail())

# CPI 同比
cpi = ak.macro_china_cpi_yearly()
print(cpi[["日期", "今值"]].tail())

# PMI 官方
pmi = ak.macro_china_pmi_yearly()
print(pmi[["日期", "今值"]].tail())

# LPR 利率
lpr = ak.macro_china_lpr()
print(lpr[["TRADE_DATE", "LPR1Y", "LPR5Y"]].tail())

# 70 城房价（需指定城市）
hp = ak.macro_china_new_house_price(city_first="北京", city_second="上海")
print(hp.head())
```

#### 从 SQLite 读取（项目已采集）

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("data/macro_data.db")

# 货币供应
df = pd.read_sql("SELECT date, m2, m2_yoy FROM money_supply ORDER BY date DESC LIMIT 10", conn)
print(df)

# 衍生月度（M2-M1 剪刀差）
derived = pd.read_sql("SELECT date, m2_m1_spread FROM derived_monthly WHERE m2_m1_spread IS NOT NULL ORDER BY date DESC LIMIT 10", conn)
print(derived)

# 杠杆率
lev = pd.read_sql("SELECT date, household, non_fin_corp, gov_total FROM leverage ORDER BY date DESC LIMIT 10", conn)
print(lev)

conn.close()
```

---

## 三、数据源对比表

| 数据类型 | PanWatch 接口 | AKShare 函数 | 适用场景 |
|---|---|---|---|
| **实时股票报价** | 腾讯 `qt.gtimg.cn` | `ak.stock_zh_a_spot_em()` 等 | A 股/港股/美股实时价格 |
| **K 线历史** | 腾讯 `web.ifzq.gtimg.cn` + 东方财富 `push2his.eastmoney.com` | `ak.stock_zh_a_hist()` | 日 K/周 K/月 K |
| **新闻资讯** | 雪球 + 东方财富搜索 + 东方财富公告 | `ak.stock_news_em()` | 个股新闻/公告 |
| **资金流向** | 东方财富 `push2his.eastmoney.com/fflow` | `ak.stock_individual_fund_flow()` | 主力/北向资金 |
| **宏观经济（中国）** | ❌ 无 | `ak.macro_china_*` 系列（17 个函数）| CPI/PPI/PMI/GDP/LPR 等 |
| **国债收益率** | ❌ 无 | `ak.bond_china_yield()` | 中债国债曲线 |
| **房价指数** | ❌ 无 | `ak.macro_china_new_house_price()` | 70 城房价 |
| **人口/城镇化** | ❌ 无 | `ak.macro_china_nbs_nation()` | NBS 年度数据 |

---

## 四、快速参考：接口 URL 汇总

### 腾讯接口

| 用途 | URL | 参数示例 |
|---|---|---|
| 实时行情 | `http://qt.gtimg.cn/q={代码列表}` | `sh600519,sz000001` |
| K 线（前复权）| `http://web.ifzq.gtimg.cn/appstock/app/fqkline/get` | `param=sh600519,day,,,100,qfq` |

### 东方财富接口

| 用途 | URL | 关键参数 |
|---|---|---|
| K 线（长历史）| `https://push2his.eastmoney.com/api/qt/stock/kline/get` | `secid=1.000001`, `klt=101`, `fqt=1` |
| 资金流向 | `https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get` | `secid=1.600519`, `klt=101` |
| 新闻搜索 | `https://search-api-web.eastmoney.com/search/jsonp` | `keyword=贵州茅台`, `type=0` |
| 公告查询 | `https://np-anotice-stock.eastmoney.com/api/security/ann` | `stock_code=600519` |

### 其他接口

| 用途 | URL | 备注 |
|---|---|---|
| 雪球新闻 | `https://xueqiu.com/statuses/stock_timeline.json` | 需 cookie |
| Stooq（美股）| `https://stooq.com/q/d/l/` | CSV 格式，备用 |
| 中债国债 | akshare `ak.bond_china_yield()` | 中债登数据 |

---

## 五、注意事项

1. **akshare 依赖外部数据源**——部分接口可能因上游变动失效（如 NBS 403、东方财富 token 过期）。采集失败时需检查上游接口状态。
2. **腾讯/东方财富接口无官方文档**——URL 和参数可能变动，需逆向工程或社区文档。
3. **雪球需登录**——个人用需自配 cookie（`xq_a_token`），企业用需遵守其 ToS。
4. **akshare NBS 接口在本沙箱被 WAF 拦截**（IP 140.205.85.146 被封）——需在 NBS 可达网络采集人口/城镇化率数据。
5. **数据频率差异**——akshare 宏观数据多为月频/季频/年频，PanWatch 行情为实时/日频。混用时注意频率对齐。

---

## 六、相关文档

- PanWatch 项目：https://github.com/TNT-Likely/PanWatch
- AKShare 文档：https://www.akshare.xyz/
- 本项目数据采集脚本：`scripts/01_fetch_data.py` + `scripts/02_compute_derived.py`
- 本项目数据表结构：`data/macro_data.db`（SQLite，13 张原始表 + 2 张衍生表）
