"""国债收益率 **全链路重放**：21 年抓取 → 月频重采样 → 闸门 → 落库（G30 / P-L 收尾）。

`test_bond_yield_parse.py` 只覆盖「认表」这一步；本模块把 `fetch_bond_yield`
整条链路跑完，唯一被替换的是 socket（`mod.requests`），其余全是真代码：真的
`ThreadPoolExecutor` 并发、真的 `pd.read_html`、真的 `resample("ME").last()`、
真的 `save_to_db` → `validate()` 闸门 → `to_sql` → UNIQUE 索引。

HTML 夹具按**断网前实测到的真实页面结构**构造（见 test_bond_yield_parse 头注）：
第 0 张是查询表单且**同样带「曲线名称」列**，第 1 张才是数据，且数据表混有
「中债商业银行普通债收益率曲线」等其它曲线行需要被筛掉。

为何用夹具而非真网络：本仓库的沙箱出口策略禁止外连（DNS 正常但 TCP 被拒），
真实联网重放请在有网机器上执行 `scripts/verify_bond_yield_e2e.py`。TLS 段的
证据是断网前实测的 HTTP 200（正文 150214 字节），已记入 CHANGELOG/账本。

Run:  .venv312/bin/python -m pytest backend/tests/test_bond_yield_e2e.py -q
"""

import importlib.util
import sqlite3
import sys
import types
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

# 数据表里真实存在的其它曲线（必须被筛掉，只留国债）
_OTHER_CURVE = "中债商业银行普通债收益率曲线(AAA)"
_GZ_CURVE = "中债国债收益率曲线"


def _load_fetcher():
    """加载 `scripts/01_fetch_data.py`（文件名以数字开头，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location(
        "fetch_data_mod", SCRIPTS / "01_fetch_data.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fetch_data_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def _year_html(year, last_month, yield_base=2.5):
    """造一年的页面：表单表 + 数据表（含需筛掉的其它曲线行）。

    每月给两个交易日，月末那天的值刻意与月中不同，这样 resample last 取错就会露馅。
    """
    rows = []
    for m in range(1, last_month + 1):
        mid_val = yield_base + m * 0.01
        eom_val = mid_val + 0.005          # 月末值 ≠ 月中值
        rows.append((_GZ_CURVE, f"{year}-{m:02d}-15", mid_val))
        rows.append((_GZ_CURVE, f"{year}-{m:02d}-28", eom_val))
        # 同日混入另一条曲线，值明显越界（若未筛掉会把闸门 ranges 打爆）
        rows.append((_OTHER_CURVE, f"{year}-{m:02d}-28", 99.0))

    body = "".join(
        f"<tr><td>{c}</td><td>{d}</td><td>1.1</td><td>{v}</td></tr>" for c, d, v in rows)
    return f"""
    <html><body>
      <table>
        <tr><th>曲线名称</th><th>开始时间:</th><th>结束时间:</th></tr>
        <tr><td>全部</td><td>{year}-01-01</td><td>{year}-12-31</td></tr>
      </table>
      <table>
        <tr><th>曲线名称</th><th>日期</th><th>3月</th><th>10年</th></tr>
        {body}
      </table>
    </body></html>
    """


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200


def _install_fake_network(monkeypatch, mod, last_month_of_current):
    """把 `mod.requests` 换成假模块；断言调用方**没有**再传 verify=False。"""
    seen = {"verify_kwargs": [], "years": []}
    today_year = date.today().year

    def fake_get(url, params=None, headers=None, timeout=None, **kw):
        seen["verify_kwargs"].append(kw.get("verify", "<absent>"))
        year = int(params["startDate"][:4])
        seen["years"].append(year)
        last = last_month_of_current if year == today_year else 12
        return _FakeResp(_year_html(year, last))

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))
    return seen


@pytest.fixture
def fetcher():
    return _load_fetcher()


def test_full_replay_lands_monthly_series_through_the_gate(tmp_path, monkeypatch, fetcher):
    """21 年全量重放：并发抓取 → 月频 → 闸门 → 落库，逐项校验。"""
    mod = fetcher
    # 当年只到上个月（模拟"年份未过完"），保证最新月份在 max_date_lag=200 天内
    today = date.today()
    last_month = max(1, today.month - 1)
    seen = _install_fake_network(monkeypatch, mod, last_month)

    db = tmp_path / "macro.db"
    conn = sqlite3.connect(db)
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"tables": {}})

    result = mod.fetch_bond_yield(conn)

    # —— 抓取覆盖面：2006 起到今年，逐年各一次请求
    assert min(seen["years"]) == 2006
    assert max(seen["years"]) == today.year
    assert len(seen["years"]) == today.year - 2006 + 1

    # —— TLS：调用方不得再传 verify（=不得关校验）
    assert set(seen["verify_kwargs"]) == {"<absent>"}, \
        f"fetcher 又开始传 verify=…: {set(seen['verify_kwargs'])}"

    # —— 月频重采样：每年 12 个月（当年到 last_month），且取的是月末值
    expected_months = (today.year - 2006) * 12 + last_month
    assert len(result) == expected_months, f"月份数 {len(result)} != {expected_months}"
    assert list(result.columns) == ["date", "y_10y"]
    assert result["date"].is_monotonic_increasing
    assert all(d.endswith("-01") for d in result["date"]), "月频锚点必须是月初 YYYY-MM-01"

    # 2006-03 月末值 = base + 3*0.01 + 0.005（证明 resample 取 last 而非 first/mean）
    v = result.loc[result["date"] == "2006-03-01", "y_10y"].iloc[0]
    assert v == pytest.approx(2.5 + 0.03 + 0.005), f"取到的不是月末值: {v}"

    # —— 其它曲线（99.0）必须已被筛掉，否则闸门 ranges(0,10) 会炸
    assert result["y_10y"].max() < 10

    # —— 闸门：真的通过 validate 并落库，manifest 记 updated
    assert mod._MANIFEST["tables"]["bond_yield"]["status"] == "updated", \
        mod._MANIFEST["tables"]["bond_yield"]
    stored = pd.read_sql("SELECT * FROM bond_yield ORDER BY date", conn)
    assert len(stored) == len(result)
    assert stored["y_10y"].iloc[-1] == pytest.approx(result["y_10y"].iloc[-1])

    # —— UNIQUE 索引已重建（to_sql replace 会把索引删掉）
    idx = pd.read_sql(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='bond_yield'", conn)
    assert not idx.empty, "落库后未重建 UNIQUE 索引"
    conn.close()


def test_stale_series_is_rejected_by_the_freshness_gate(tmp_path, monkeypatch, fetcher):
    """若上游整体冻结在多年前，闸门必须拒收（max_date_lag=200），不得覆盖好数据。"""
    mod = fetcher

    def fake_get(url, params=None, headers=None, timeout=None, **kw):
        year = int(params["startDate"][:4])
        # 只有 2006..2015 有数据，最新值距今 >200 天
        return _FakeResp(_year_html(year, 12) if year <= 2015
                         else _year_html(year, 0))

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    conn = sqlite3.connect(tmp_path / "macro.db")
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"tables": {}})
    mod.fetch_bond_yield(conn)

    entry = mod._MANIFEST["tables"]["bond_yield"]
    assert entry["status"] == "kept_previous", entry
    assert "max_date_lag" in entry["reason"] or "behind" in entry["reason"].lower(), entry
    conn.close()


def test_a_broken_page_is_logged_per_year_not_silently_empty(tmp_path, monkeypatch, fetcher, capsys):
    """页面改版（认不出表）→ 逐年 ⚠️ 留痕；改前是裸 except 静默返回空表。"""
    mod = fetcher

    def fake_get(url, params=None, headers=None, timeout=None, **kw):
        return _FakeResp("<html><body><table><tr><th>foo</th></tr>"
                         "<tr><td>1</td></tr></table></body></html>")

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))
    conn = sqlite3.connect(tmp_path / "macro.db")
    mod._MANIFEST.clear()
    mod._MANIFEST.update({"tables": {}})
    mod.fetch_bond_yield(conn)

    out = capsys.readouterr().out
    assert "国债收益率" in out and "采集失败" in out, out[-500:]
    assert "LookupError" in out, "未记录认表失败的异常类型"
    conn.close()
