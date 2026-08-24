"""国债收益率解析的两条 P-L 残留（TLS + 位置式取表）回归锁。

改前 `fetch_bond_yield._fetch_year` 有两处：

  1. `requests.get(..., verify=False)` —— 关闭 TLS 校验（MITM 风险）。实测中债
     站点用 certifi 默认 CA 即可 200，故根因修复是**删掉该参数**；本模块断言
     源码中不再出现 `verify=False`。
  2. `df = dfs[1]` —— 位置式取 `read_html` 的第二张表。该页第 0 张是查询表单，
     **表单同样带「曲线名称」列**，所以上游一旦多插一张表，位置式索引就取错表，
     再被裸 `except` 吞成「本年无数据」，表现为收益率永远不更新。

现由 `_specs.pick_curve_table` 按「曲线名称+日期+10年」三列同时存在认表，认不出
则抛 `LookupError`（让调用方记失败，而不是静默返回空表）。

Run:  .venv312/bin/python -m pytest backend/tests/test_bond_yield_parse.py -q
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _specs import CB_CURVE_COLS, pick_curve_table  # noqa: E402

FETCHER_SRC = (ROOT / "scripts" / "01_fetch_data.py").read_text(encoding="utf-8")


def _form_table():
    """第 0 张：查询表单——带「曲线名称」但没有「日期」/「10年」，是最容易误认的诱饵。"""
    return pd.DataFrame({"曲线名称": [], "开始时间:": [], "结束时间:": []})


def _data_table():
    """第 1 张：真数据表。"""
    return pd.DataFrame({
        "曲线名称": ["中债国债收益率曲线", "中债国债收益率曲线"],
        "日期": ["2026-01-05", "2026-01-06"],
        "3月": [1.2, 1.21],
        "10年": [2.55, 2.56],
    })


def test_picks_the_data_table_not_the_form():
    """真实页面结构（表单 + 数据）——必须选中数据表。"""
    got = pick_curve_table([_form_table(), _data_table()])
    assert list(got["10年"]) == [2.55, 2.56]


def test_form_table_alone_is_never_accepted():
    """表单带「曲线名称」但缺「日期」/「10年」，不能被误认为数据表。"""
    with pytest.raises(LookupError):
        pick_curve_table([_form_table()])


def test_survives_an_extra_table_inserted_upstream():
    """上游多插一张表 → 数据表不再位于索引 1；改前的 dfs[1] 会取错表。"""
    banner = pd.DataFrame({"公告": ["系统维护通知"]})
    dfs = [_form_table(), banner, _data_table()]
    assert dfs[1] is banner                      # 位置式索引会取到这张
    got = pick_curve_table(dfs)
    assert list(got["日期"]) == ["2026-01-05", "2026-01-06"]


def test_no_matching_table_raises_instead_of_returning_empty():
    """页面彻底改版 → 抛 LookupError，让调用方记为失败而非「本年无数据」。"""
    with pytest.raises(LookupError, match="未找到"):
        pick_curve_table([pd.DataFrame({"foo": [1]}), pd.DataFrame({"bar": [2]})])


def test_required_columns_are_all_three():
    """三列缺任意一列都不算数据表（只判「曲线名称」会重新引入表单误认）。"""
    assert set(CB_CURVE_COLS) == {"曲线名称", "日期", "10年"}
    full = _data_table()
    for col in CB_CURVE_COLS:
        with pytest.raises(LookupError):
            pick_curve_table([full.drop(columns=[col])])


def test_tls_verification_is_not_disabled_in_the_fetcher():
    """TLS 校验不得再被关闭（实测中债用默认 CA 即 200）。"""
    assert "verify=False" not in FETCHER_SRC


def test_fetcher_no_longer_indexes_the_table_positionally():
    """确保 fetcher 走 pick_curve_table，而非 dfs[1]。"""
    assert "pick_curve_table(dfs)" in FETCHER_SRC
    assert "dfs[1]" not in FETCHER_SRC


def test_year_failure_is_logged_not_swallowed_silently():
    """逐年失败必须留痕（⚠️），且不得含 ✅（refresh.py 用 ✅ 行数算进度）。"""
    marker = "国债收益率 {year} 年采集失败"
    assert marker in FETCHER_SRC
    line = next(ln for ln in FETCHER_SRC.splitlines() if marker in ln)
    assert "⚠️" in line and "✅" not in line
