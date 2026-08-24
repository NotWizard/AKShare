"""PBoC 社会融资规模增量 官方 XLSX 备用源 —— 单一真相源。

akshare ``macro_china_shrzgm`` 常滞后约 3-4 个月（实测封顶 2026-04），而中国人民银行
调查统计司按月发布「社会融资规模增量」XLSX，含人民币贷款/委托/信托/未贴现/企业债券/
股票等分项。本模块抓取并解析该 XLSX，作为 akshare 主源之外的补齐来源。

此前该抓取体只作为 ``01_fetch_data.fetch_social_finance`` 内的私有函数存在，无法在
主管线之外复用。主管线里它排在 leverage（``ak.macro_cnbs`` 走线程超时封装）之后，一旦
CNBS 超时的被弃线程损坏进程 fd（``[Errno 9] Bad file descriptor`` 级联），本抓取的
requests 也随之失败并被静默吞成空 → 社融永远补不进 05/06/07。抽到本模块后，
``04_supplement_social_finance`` 可脱离该级联、单独经闸门补齐（对照 nifd_leverage/03）。

解析失败一律返回空 DataFrame（列见 COLUMNS），由调用方决定「主源保留、补充跳过」。
"""

import io
import re
import datetime

import pandas as pd
import requests

from _specs import to_num

COLUMNS = ["date", "total", "rmb_loan", "entrusted_loan", "trust_loan",
           "acceptance_bill", "corp_bond", "equity"]

_UA = {"User-Agent": "Mozilla/5.0"}


def pbc_shrzgm_supplement_df() -> pd.DataFrame:
    """PBoC 调查统计司 社融增量 XLSX 备用源（akshare shrzgm 滞后时补齐）。解析失败返回空。"""
    try:
        yr = datetime.date.today().year
        hrefs = []
        for y in (yr, yr - 1):
            lu = f"http://www.pbc.gov.cn/diaochatongjisi/116219/116319/{y}ntjsj/shrzgm/index.html"
            try:
                r = requests.get(lu, headers=_UA, timeout=20)
                hrefs = re.findall(r'(attachDir/[^"\'\s]+\.xlsx)', r.text)
                if hrefs:
                    break
            except Exception:
                continue
        if not hrefs:
            return pd.DataFrame(columns=COLUMNS)
        xls = None
        hdr = None
        for h in hrefs[:4]:   # 选增量表(title 含"增量")且有列头行(含"人民币贷款")
            try:
                xr = requests.get("http://www.pbc.gov.cn/diaochatongjisi/" + h,
                                  headers=_UA, timeout=30)
                x = pd.read_excel(io.BytesIO(xr.content), header=None)
                if not any("增量" in str(v) for v in x.iloc[0]):
                    continue
                hd = next((i for i in range(min(20, len(x)))
                           if any("人民币贷款" in str(v) for v in x.iloc[i])), None)
                if hd is not None:
                    xls, hdr = x, hd
                    break
            except Exception:
                continue
        if xls is None or hdr is None:
            return pd.DataFrame(columns=COLUMNS)
        cols = [str(v) for v in xls.iloc[hdr]]

        def colidx(*names):
            for n in names:
                for j, c in enumerate(cols):
                    if n in c:
                        return j
            return None

        idx = {k: colidx(*ns) for k, ns in {
            "total": ("社会融资规模增量", "社会融资规模"), "rmb_loan": ("人民币贷款",),
            "entrusted_loan": ("委托贷款",), "trust_loan": ("信托贷款",),
            "acceptance_bill": ("未贴现",), "corp_bond": ("企业债券",),
            "equity": ("股票",)}.items()}
        rows = []
        for i in range(hdr + 1, len(xls)):
            mo = xls.iloc[i, 0]
            try:
                y = int(mo)
                month = round((float(mo) - y) * 100)   # 2026.05→5; 2026.1→10
            except Exception:
                continue
            if not (1 <= month <= 12):
                continue

            def gv(j):
                if j is None:
                    return None
                v = to_num(xls.iloc[i, j])
                return None if pd.isna(v) else float(v)

            rows.append({"date": f"{y}-{month:02d}-01", **{k: gv(j) for k, j in idx.items()}})
        return pd.DataFrame(rows, columns=COLUMNS)
    except Exception as e:
        print(f"  ⚠️ PBoC 社融补充失败, 保留主源: {type(e).__name__}")
        return pd.DataFrame(columns=COLUMNS)
