# 金融数据源接入参考手册

> 按数据类型分类的数据源参考文档。每类数据说明：数据源、请求方式、返回字段、使用示例。

---

## 一、实时行情数据

### 数据源：腾讯财经 API

**官方文档**：无官方文档（非公开 API，逆向工程整理）

**接口地址**：`http://qt.gtimg.cn/q={股票代码列表}`

**请求方式**：HTTP GET

**股票代码格式**：
- A 股：`sh600519`（上海）、`sz000001`（深圳）
- 港股：`hk00700`
- 美股：`usAAPL`

**请求示例**：
```python
import requests

url = "http://qt.gtimg.cn/q=sh600519,sz000001,hk00700"
response = requests.get(url)
response.encoding = 'gbk'
print(response.text)
```

**返回字段**（以 `~` 分隔）：
```
索引 | 字段
0    | 未知
1    | 股票名称
2    | 股票代码
3    | 当前价格
4    | 昨收价
5    | 今开价
6    | 成交量（手）
7    | 外盘
8    | 内盘
9    | 买一价
10   | 买一量
11   | 买二价
12   | 买二量
...  | ...
30   | 最新价
31   | 涨跌额
32   | 涨跌幅（%）
33   | 最高价
34   | 最低价
35   | 价格/成交量/成交额
36   | 成交量（手）
37   | 成交额（万元）
38   | 换手率（%）
...  | ...
```

**使用示例**：
```python
import requests

def get_realtime_quote(symbol):
    """获取实时行情"""
    url = f"http://qt.gtimg.cn/q={symbol}"
    response = requests.get(url)
    response.encoding = 'gbk'
    
    data = response.text.split('~')
    if len(data) > 35:
        return {
            'name': data[1],
            'code': data[2],
            'price': float(data[3]),
            'yesterday_close': float(data[4]),
            'open': float(data[5]),
            'volume': int(data[6]),
            'change': float(data[31]),
            'change_pct': float(data[32]),
            'high': float(data[33]),
            'low': float(data[34]),
            'turnover': float(data[37]),
            'turnover_rate': float(data[38]) if data[38] else 0
        }
    return None

# 示例
quote = get_realtime_quote('sh600519')
print(f"{quote['name']}: {quote['price']} 元 ({quote['change_pct']}%)")
```

---

## 二、历史 K 线数据

### 数据源 1：腾讯财经 K 线 API

**官方文档**：无官方文档（非公开 API，逆向工程整理）

**接口地址**：`http://web.ifzq.gtimg.cn/appstock/app/fqkline/get`

**请求参数**：
- `param`: `{股票代码},day,,,{天数},{复权方式}`
  - 股票代码：`sh600519`、`sz000001`
  - 周期：`day`（日K）、`week`（周K）、`month`（月K）
  - 天数：获取多少条数据
  - 复权：`qfq`（前复权）、`hfq`（后复权）、空（不复权）
- `_var`: `kline_dayqfq`（固定值）

**请求示例**：
```python
import requests
import json

url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
params = {
    'param': 'sh600519,day,,,100,qfq',
    '_var': 'kline_dayqfq'
}

response = requests.get(url, params=params)
text = response.text

# 解析响应（移除 var 声明）
if 'kline_dayqfq=' in text:
    text = text.split('kline_dayqfq=')[1]
    data = json.loads(text)
    
    if 'data' in data and 'sh600519' in data['data']:
        kline_data = data['data']['sh600519']
        klines = kline_data.get('day') or kline_data.get('qfqday')
        
        if klines:
            print(f"获取到 {len(klines)} 条 K 线数据")
            print(f"示例: {klines[0]}")
```

**返回字段**（每条 K 线）：
```
[日期, 开盘价, 收盘价, 最高价, 最低价, 成交量]
示例: ['2023-01-03', '10.50', '10.80', '10.85', '10.45', '1000000']
```

---

### 数据源 2：东方财富 K 线 API

**官方文档**：无官方文档（非公开 API，逆向工程整理）

**接口地址**：`https://push2his.eastmoney.com/api/qt/stock/kline/get`

**请求参数**：
- `secid`: `{市场代码}.{股票代码}`
  - A 股上海：`1.600519`
  - A 股深圳：`0.000001`
  - 港股：`116.00700`
- `klt`: K 线类型（`101`=日K、`102`=周K、`103`=月K）
- `fqt`: 复权方式（`0`=不复权、`1`=前复权、`2`=后复权）
- `beg`: 开始日期（`YYYYMMDD`）
- `end`: 结束日期（`YYYYMMDD`）
- `lmt`: 获取条数
- `fields1`: `f1,f2,f3,f4,f5,f6`
- `fields2`: `f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63`
- `ut`: `fa5fd1943c7b386f172d6893dbbd1d0c`（固定公共 token，无需替换）

**请求示例**：
```python
import requests
import pandas as pd

url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
params = {
    'secid': '1.600519',  # 贵州茅台
    'klt': '101',  # 日K
    'fqt': '1',    # 前复权
    'beg': '20230101',
    'end': '20261231',
    'lmt': '100',
    'fields1': 'f1,f2,f3,f4,f5,f6',
    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63',
    'ut': 'fa5fd1943c7b386f172d6893dbbd1d0c'
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/'
}

response = requests.get(url, params=params, headers=headers, timeout=15)
data = response.json()

if 'data' in data and data['data'] and 'klines' in data['data']:
    klines = data['data']['klines']
    
    # 解析 K 线数据
    df = pd.DataFrame([item.split(',') for item in klines],
                     columns=['date', 'open', 'close', 'high', 'low', 'volume', 'amount',
                             'amplitude', 'change_pct', 'change', 'turnover'])
    
    df['date'] = pd.to_datetime(df['date'])
    df[['open', 'close', 'high', 'low']] = df[['open', 'close', 'high', 'low']].astype(float)
    df['volume'] = df['volume'].astype(int)
    
    print(f"获取到 {len(df)} 条 K 线数据")
    print(df.head())
```

**返回字段**：
```
date         | 日期
open         | 开盘价
close        | 收盘价
high         | 最高价
low          | 最低价
volume       | 成交量
amount       | 成交额
amplitude    | 振幅（%）
change_pct   | 涨跌幅（%）
change       | 涨跌额
turnover     | 换手率（%）
```

---

### 数据源 3：Yahoo Finance（yfinance）

**官方文档**：https://ranaroussi.github.io/yfinance/

**API 参考**：https://ranaroussi.github.io/yfinance/reference/api.html

**GitHub 仓库**：https://github.com/ranaroussi/yfinance

> 注：yfinance 非 Yahoo 官方产品，数据来源于 Yahoo Finance，可能存在延迟或不准确。

**安装**：`pip install yfinance`

**使用示例**：
```python
import yfinance as yf

# A 股：代码.SS（上海）、.SZ（深圳）
ticker = yf.Ticker("600519.SS")

# 获取历史数据
df = ticker.history(period="max")  # 全部历史
# 或
df = ticker.history(start="2023-01-01", end="2026-12-31")

print(df.head())
```

**返回字段**：
```
Date, Open, High, Low, Close, Volume, Dividends, Stock Splits
```

---

## 三、新闻资讯数据

### 数据源 1：新浪财经滚动新闻 API

**官方文档**：无官方文档（非公开 API，逆向工程整理）

> ⚠️ 注意：该接口为非公开 API，可能需要添加 `Referer: https://finance.sina.com.cn/` 请求头，且随时可能变更。

**接口地址**：`https://feed.mix.sina.com.cn/api/roll/get`

**请求参数**：
- `pageid`: 页面 ID（`153`=财经频道）
- `lid`: 栏目 ID（`2509`=全部、`2511`=A 股、`2516`=个股）
- `k`: 搜索关键词（可选，如股票名称/代码）
- `num`: 每页条数
- `page`: 页码

**请求示例**：
```python
import requests

url = "https://feed.mix.sina.com.cn/api/roll/get"
params = {
    'pageid': '153',
    'lid': '2516',
    'k': '贵州茅台',
    'num': '10',
    'page': '1'
}

headers = {
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://finance.sina.com.cn/'
}

response = requests.get(url, params=params, headers=headers, timeout=15)
data = response.json()

if 'result' in data and 'data' in data['result']:
    news_list = data['result']['data']
    for item in news_list[:5]:
        print(f"- [{item.get('ctime', '')}] {item.get('title', 'N/A')}")
        print(f"  {item.get('url', '')}")
```

**返回字段**：
```
字段      | 说明
title     | 新闻标题
ctime     | 发布时间（Unix 时间戳）
url       | 新闻链接
media_name| 媒体来源
summary   | 摘要
keywords  | 关键词
```

> 备选方案：如该接口不可用，可使用 **Tushare 旧版** 的 `ts.get_latest_news()` 获取即时财经新闻，或使用下方的东方财富新闻 API。

---

### 数据源 2：东方财富新闻搜索 API

**官方文档**：无官方文档（非公开 API，逆向工程整理）

**接口地址**：`https://search-api-web.eastmoney.com/search/jsonp`

**请求参数**（通过 JSONP `param` 传递）：
- `keyword`: 搜索关键词（股票名称/代码）
- `type`: 搜索类型（`cmsArticleWebOld`=新闻文章）
- `pageIndex`: 页码
- `pageSize`: 每页条数
- `sort`: 排序方式（`default`=默认）

**请求示例**：
```python
import requests
import json
import re

url = "https://search-api-web.eastmoney.com/search/jsonp"
params = {
    'cb': 'jQuery',
    'param': json.dumps({
        "uid": "",
        "keyword": "贵州茅台",
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": 10,
                "preTag": "",
                "postTag": ""
            }
        }
    })
}

headers = {
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://so.eastmoney.com/'
}

response = requests.get(url, params=params, headers=headers, timeout=15)

# 解析 JSONP 响应：jQuery({...})
text = response.text
match = re.search(r'jQuery\((.*)\)', text, re.DOTALL)
if match:
    data = json.loads(match.group(1))
    result = data.get('result', {})
    articles = result.get('cmsArticleWebOld', [])
    print(f"共 {result.get('hitsTotal', 0)} 条结果")
    for article in articles[:5]:
        print(f"- [{article.get('date', '')}] {article.get('title', '')}")
        print(f"  来源: {article.get('mediaName', '')}")
        print(f"  链接: {article.get('url', '')}")
```

**返回字段**：
```
字段        | 说明
title       | 新闻标题
date        | 发布时间
content     | 摘要
mediaName   | 媒体来源
url         | 新闻链接
code        | 文章 ID
image       | 缩略图 URL
```

---

## 四、ETF 数据

**说明**：ETF 数据复用历史 K 线 API（东方财富/Yahoo Finance），接口地址和参数与历史 K 线相同，仅股票代码格式不同。

### 数据源 1：东方财富 ETF K 线 API

**官方文档**：无官方文档（复用历史 K 线 API，逆向工程整理）

**ETF 代码格式**：
- 上海 ETF：`1.563020`
- 深圳 ETF：`0.159915`

**使用示例**：
```python
import requests
import pandas as pd

url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
params = {
    'secid': '1.563020',  # 红利低波 ETF
    'klt': '101',
    'fqt': '1',
    'beg': '20230101',
    'end': '20261231',
    'fields1': 'f1,f2,f3,f4,f5,f6',
    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63',
    'ut': 'fa5fd1943c7b386f172d6893dbbd1d0c'
}

response = requests.get(url, params=params, timeout=15)
data = response.json()

if 'data' in data and data['data'] and 'klines' in data['data']:
    klines = data['data']['klines']
    df = pd.DataFrame([item.split(',') for item in klines],
                     columns=['date', 'open', 'close', 'high', 'low', 'volume', 'amount',
                             'amplitude', 'change_pct', 'change', 'turnover'])
    print(f"获取到 {len(df)} 条 ETF K 线数据")
```

---

### 数据源 2：Yahoo Finance ETF 数据

**ETF 代码格式**：`代码.SS`（上海）、`.SZ`（深圳）

**使用示例**：
```python
import yfinance as yf

ticker = yf.Ticker("563020.SS")  # 红利低波 ETF
df = ticker.history(period="max")

print(df.head())
```

---

## 五、宏观经济数据（AKShare）

### 官方文档

**AKShare 官方文档**：https://akshare.akfamily.xyz/

**AKShare 数据字典（API 全量索引）**：https://akshare.akfamily.xyz/data/macro/macro.html

**AKShare GitHub**：https://github.com/akfamily/akshare

### 安装

```bash
pip install akshare
```

### 货币供应量（M2）

```python
import akshare as ak

# M2 货币供应年率（年度数据）
df = ak.macro_china_m2_yearly()
print(df.head())

# 字段：日期, M2 货币和准货币（亿元）, M2 同比（%）
```

> 注：AKShare 当前版本未提供独立的 M0/M1 月度供应函数。如需 M0/M1 数据，可通过
> `ak.macro_china_money_supply()` 获取完整货币供应量统计表（含 M0、M1、M2 月度数据），
> 或参考东方财富宏观数据页面手动导出。

### GDP

```python
import akshare as ak

df = ak.macro_china_gdp()
print(df.head())

# 字段：季度, 国内生产总值-绝对值, 国内生产总值-同比
```

### CPI

```python
import akshare as ak

# 同比
df_yoy = ak.macro_china_cpi_yearly()

# 环比
df_mom = ak.macro_china_cpi_monthly()
```

### PPI

```python
import akshare as ak

df = ak.macro_china_ppi_yearly()
```

### PMI

```python
import akshare as ak

# 官方制造业 PMI
df_official = ak.macro_china_pmi_yearly()

# 财新制造业 PMI
df_caixin = ak.macro_china_cx_pmi_yearly()

# 非制造业 PMI
df_non_man = ak.macro_china_non_man_pmi()
```

### LPR 利率

```python
import akshare as ak

df = ak.macro_china_lpr()

# 字段：TRADE_DATE, LPR1Y, LPR5Y
```

### 社会融资规模

```python
import akshare as ak

df = ak.macro_china_shrzgm()
```

### 工业增加值

```python
import akshare as ak

df = ak.macro_china_gyzjz()
```

### 70 城房价指数

```python
import akshare as ak

df = ak.macro_china_new_house_price(city_first="北京", city_second="上海")
```

### 宏观杠杆率（CNBS）

```python
import akshare as ak

df = ak.macro_cnbs()

# 字段：年份, 居民部门, 非金融企业部门, 政府部门, 实体经济部门
```

---

## 六、指数估值数据（Tushare）

### 官方文档

**Tushare 官方文档**：https://tushare.pro/document/1

**index_dailybasic 接口文档**：https://tushare.pro/document/2?doc_id=128

**积分权限说明**：https://tushare.pro/document/1?doc_id=108（index_dailybasic 需要 4000+ 积分）

### 安装

```bash
pip install tushare
```

### 注册

https://tushare.pro/register（免费，需要积分）

### 指数估值（股息率、PE、PB）

```python
import tushare as ts

ts.set_token('YOUR_TOKEN_HERE')
pro = ts.pro_api()

# 获取指数估值数据（支持：上证综指/深证成指/上证50/沪深300/中证500/中小板指/创业板指）
df = pro.index_dailybasic(
    ts_code='000300.SH',  # 沪深300指数
    start_date='20140101',
    end_date='20261231',
    fields='ts_code,trade_date,pe,pe_ttm,pb,dv_ratio,dv_ttm,turnover_rate,total_mv,float_mv'
)

print(df.head())

# 字段：
# trade_date    | 交易日期
# total_mv      | 当日总市值（元）
# float_mv      | 当日流通市值（元）
# total_share   | 当日总股本（股）
# float_share   | 当日流通股本（股）
# free_share    | 当日自由流通股本（股）
# turnover_rate | 换手率（%）
# pe            | 市盈率
# pe_ttm        | 市盈率 TTM
# pb            | 市净率
# dv_ratio      | 股息率（%）
# dv_ttm        | 股息率 TTM
```

---

## 七、常见问题

### Q: 腾讯 API 返回空数据？

A: 检查股票代码格式是否正确（`sh`/`sz`/`hk` 前缀），以及是否在交易时间。

### Q: 新浪新闻 API 返回 403？

A: 新浪 `feed.mix.sina.com.cn` 接口可能需要：
- 添加 `Referer: https://finance.sina.com.cn/` 请求头
- 在本地网络运行（非云服务器）
- 接口随时可能变更，建议优先使用东方财富新闻 API

### Q: 东方财富 API 返回 ConnectionError？

A: 可能是 IP 被限制，尝试：
- 使用代理
- 在本地网络运行（非云服务器）
- 使用其他数据源（Yahoo Finance、新浪财经）

### Q: AKShare 函数报错？

A: AKShare 依赖上游数据源，上游接口可能变动。检查 AKShare 版本是否最新：
```bash
pip install --upgrade akshare
```

### Q: AKShare 找不到 `macro_china_supply_of_money`？

A: 该函数已被移除或从未存在。M2 年度数据请使用 `macro_china_m2_yearly()`，
完整货币供应量统计表（含 M0/M1/M2 月度）请使用 `macro_china_money_supply()`。

### Q: Tushare 接口无权限？

A: 部分接口需要积分，详见：https://tushare.pro/document/1?doc_id=108

---

## 八、数据源对比

| 数据类型 | 腾讯 | 东方财富 | Yahoo | AKShare | Tushare |
|---------|------|---------|-------|---------|---------|
| 实时行情 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 历史 K 线 | ✅（短） | ✅（长） | ✅ | ✅ | ✅ |
| ETF 数据 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 新闻资讯 | ❌ | ✅ | ❌ | ✅ | ❌ |
| 宏观经济 | ❌ | ❌ | ❌ | ✅ | ✅ |
| 指数估值 | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## 九、使用建议

1. **实时行情**：腾讯 API（简单快速）
2. **历史 K 线**：东方财富（数据全）或 Yahoo Finance（海外股票）
3. **宏观经济**：AKShare（覆盖广）
4. **指数估值**：Tushare（需积分）
5. **新闻资讯**：东方财富新闻 API

---

## 十、官方文档快速索引

| 数据源 | 类型 | 官方文档 | 备注 |
|--------|------|---------|------|
| **腾讯财经 API** | 实时行情 / K 线 | 无官方文档 | 非公开 API，逆向工程整理 |
| **东方财富 API** | K 线 / 新闻 | 无官方文档 | 非公开 API，逆向工程整理 |
| **新浪财经 API** | 新闻 / K 线 | 无官方文档 | 非公开 API，逆向工程整理；新闻接口可能需 Referer 头 |
| **Yahoo Finance** | 行情 / K 线 | https://ranaroussi.github.io/yfinance | yfinance 库官方文档；[API 参考](https://ranaroussi.github.io/yfinance/reference/api.html) |
| **AKShare** | 宏观经济数据 | https://akshare.akfamily.xyz/ | [数据字典](https://akshare.akfamily.xyz/data/macro/macro.html)；[GitHub](https://github.com/akfamily/akshare) |
| **Tushare** | 指数估值 | https://tushare.pro/document/1 | [index_dailybasic](https://tushare.pro/document/2?doc_id=128)；[积分权限](https://tushare.pro/document/1?doc_id=108)；需注册 + 4000 积分 |

---

*文档版本：1.2 | 更新时间：2026-06-23*
