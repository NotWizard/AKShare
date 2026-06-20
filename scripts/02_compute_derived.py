#!/usr/bin/env python3
"""
衍生指标计算脚本
从 SQLite 读取原始数据，计算衍生指标，写回 SQLite
"""

import sqlite3
import os
import sys

import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "macro_data.db")


def log(msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_table(conn, table):
    """从 SQLite 加载表

    若表含 date 列，按 date 去重（保留最后写入的一行）。
    源表（如 pmi 多次采集、lpr 月内多行）可能存在重复日期，
    不去重会导致后续 on="date" 的 left merge 产生笛卡尔积、行数膨胀。
    本脚本加载的所有表均为「日期单粒度」时序，去重安全。
    """
    try:
        df = pd.read_sql(f"SELECT * FROM {table}", conn)
    except Exception:
        return pd.DataFrame()
    if "date" in df.columns:
        df = df.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    return df


def compute_derived(conn):
    """计算所有衍生指标"""
    log("计算衍生指标 ...")

    money = load_table(conn, "money_supply")
    gdp = load_table(conn, "gdp")
    cpi = load_table(conn, "cpi")
    ppi = load_table(conn, "ppi")
    pmi = load_table(conn, "pmi")
    leverage = load_table(conn, "leverage")
    social_fin = load_table(conn, "social_finance")
    new_credit = load_table(conn, "new_credit")
    lpr = load_table(conn, "lpr")
    industrial = load_table(conn, "industrial")
    hh_income = load_table(conn, "household_income")
    bond = load_table(conn, "bond_yield")

    # ─── 构建月度主表 ───
    # 以 money_supply 的日期为锚（月度，最长序列）
    monthly = money[["date", "m1", "m1_yoy", "m2", "m2_yoy", "m0", "m0_yoy"]].copy()
    monthly["date"] = pd.to_datetime(monthly["date"])

    # M2-M1 剪刀差
    monthly["m2_m1_spread"] = monthly["m2_yoy"] - monthly["m1_yoy"]

    # 合并 CPI
    if not cpi.empty:
        cpi_m = cpi.copy()
        cpi_m["date"] = pd.to_datetime(cpi_m["date"])
        monthly = monthly.merge(cpi_m[["date", "cpi_yoy", "cpi_mom"]], on="date", how="left")

    # 合并 PPI
    if not ppi.empty:
        ppi_m = ppi.copy()
        ppi_m["date"] = pd.to_datetime(ppi_m["date"])
        monthly = monthly.merge(ppi_m[["date", "ppi_yoy"]], on="date", how="left")

    # 合并 PMI
    if not pmi.empty:
        pmi_m = pmi.copy()
        pmi_m["date"] = pd.to_datetime(pmi_m["date"])
        monthly = monthly.merge(
            pmi_m[["date", "pmi_official", "pmi_caixin", "pmi_non_mfg", "pmi_caixin_svc"]],
            on="date", how="left"
        )

    # 合并工业增加值
    if not industrial.empty:
        ind_m = industrial.copy()
        ind_m["date"] = pd.to_datetime(ind_m["date"])
        monthly = monthly.merge(ind_m[["date", "ip_yoy", "ip_cumulative"]], on="date", how="left")

    # 合并 LPR
    if not lpr.empty:
        lpr_m = lpr.copy()
        lpr_m["date"] = pd.to_datetime(lpr_m["date"])
        monthly = monthly.merge(lpr_m[["date", "lpr_1y", "lpr_5y"]], on="date", how="left")

    # 实际利率 = LPR 1Y - CPI
    if "lpr_1y" in monthly.columns and "cpi_yoy" in monthly.columns:
        monthly["real_rate"] = monthly["lpr_1y"] - monthly["cpi_yoy"]

    # ─── 10 年期国债收益率（日频 → 月频：取每月最后一个交易日的值）───
    if not bond.empty:
        b = bond.copy()
        b["date"] = pd.to_datetime(b["date"])
        b = b.sort_values("date").dropna(subset=["y_10y"])
        # resample 到月末，取当月最后值；再对齐到 monthly 的月初锚点
        b_m = (
            b.set_index("date")["y_10y"]
            .resample("ME")
            .last()
            .reset_index()
            .rename(columns={"y_10y": "bond_10y"})
        )
        # monthly 锚点是每月 1 号；国债月末值 forward-fill 对齐到该月
        b_m["date"] = b_m["date"].values.astype("datetime64[M]")  # 月初归一
        monthly = monthly.merge(b_m[["date", "bond_10y"]], on="date", how="left")
    else:
        # 采集失败时仍预创建列（全 NaN），保证 derived_monthly 列结构稳定，
        # 前端始终能请求到 bond_10y（值全空 → 图表无线，优雅降级而非缺列报错）
        monthly["bond_10y"] = pd.NA

    # ─── 社融存量增速 ───
    if not social_fin.empty:
        sf = social_fin.copy()
        sf["date"] = pd.to_datetime(sf["date"])
        sf = sf.sort_values("date")
        # 累计社融 → 滚动12月存量估算
        sf["total_12m"] = sf["total"].rolling(12, min_periods=1).sum()
        sf["sf_stock_yoy"] = sf["total_12m"].pct_change(12) * 100  # 同比增速
        sf["sf_impulse"] = (sf["total"] - sf["total"].shift(12))  # 信贷脉冲（简化）

        monthly = monthly.merge(
            sf[["date", "total", "rmb_loan", "sf_stock_yoy", "sf_impulse"]],
            on="date", how="left"
        )

    # ─── 新增人民币贷款（社融的补充信用指标）───
    if not new_credit.empty:
        nc = new_credit.copy()
        nc["date"] = pd.to_datetime(nc["date"])
        nc = nc.sort_values("date")
        # 新增贷款同比增速（作为信用脉冲的替代）
        nc["loan_yoy"] = nc["new_rmb_loan"].pct_change(12) * 100
        # 新增贷款 12 月滚动累计
        nc["loan_12m"] = nc["new_rmb_loan"].rolling(12, min_periods=1).sum()
        nc["loan_stock_yoy"] = nc["loan_12m"].pct_change(12) * 100
        monthly = monthly.merge(
            nc[["date", "new_rmb_loan", "loan_yoy", "loan_stock_yoy"]],
            on="date", how="left"
        )

    # ─── PMI 均线 ───
    if "pmi_official" in monthly.columns:
        monthly["pmi_ma6"] = monthly["pmi_official"].rolling(6, min_periods=1).mean()

    # ─── 工业增加值趋势 ───
    if "ip_yoy" in monthly.columns:
        monthly["ip_trend"] = monthly["ip_yoy"].rolling(6, min_periods=1).mean()

    # ─── M1 领先 PPI 标记 ───
    if "m1_yoy" in monthly.columns and "ppi_yoy" in monthly.columns:
        monthly["m1_lead_6m"] = monthly["m1_yoy"].shift(-6)  # M1 领先 6 个月

    # ─── 排序并保存 ───
    monthly = monthly.sort_values("date").reset_index(drop=True)
    monthly["date"] = monthly["date"].dt.strftime("%Y-%m-%d")

    monthly.to_sql("derived_monthly", conn, if_exists="replace", index=False)
    log(f"  ✅ derived_monthly: {len(monthly)} rows, {len(monthly.columns)} columns")

    # ─── 构建季度衍生表 ───
    quarterly = pd.DataFrame()
    if not gdp.empty:
        quarterly = gdp[["date", "gdp_abs", "gdp_yoy"]].copy()
        quarterly["date"] = pd.to_datetime(quarterly["date"])
        quarterly["gdp_yoy_smooth"] = quarterly["gdp_yoy"].rolling(4, min_periods=1).mean()

    if not leverage.empty:
        lev = leverage.copy()
        lev["date"] = pd.to_datetime(lev["date"])
        quarterly = quarterly.merge(
            lev[["date", "household", "non_fin_corp", "gov_total",
                 "gov_central", "gov_local", "real_economy"]],
            on="date", how="left"
        )
        # 杠杆率变化速度 (年度变化 = 当前 - 4 季度前)
        if "household" in quarterly.columns:
            quarterly["household_change"] = quarterly["household"] - quarterly["household"].shift(4)
            quarterly["gov_change"] = quarterly["gov_total"] - quarterly["gov_total"].shift(4)
            quarterly["corp_change"] = quarterly["non_fin_corp"] - quarterly["non_fin_corp"].shift(4)

    # ─── 居民真实杠杆率（债务 / 可支配收入）───
    if not hh_income.empty and not quarterly.empty and "gdp_abs" in quarterly.columns:
        hi = hh_income.copy()
        hi["date"] = pd.to_datetime(hi["date"])
        # 年度 income_abs 前向填充到季度
        quarterly = quarterly.merge(hi[["date", "income_abs"]], on="date", how="left")
        quarterly["income_abs"] = quarterly["income_abs"].ffill()
        if "household" in quarterly.columns:
            # household leverage is % of GDP; debt_abs = household/100 * gdp_abs
            quarterly["hh_debt_abs"] = quarterly["household"] / 100.0 * quarterly["gdp_abs"]
            quarterly["hh_income_share"] = quarterly["income_abs"] / quarterly["gdp_abs"] * 100.0
            quarterly["hh_debt_to_income"] = quarterly["hh_debt_abs"] / quarterly["income_abs"] * 100.0
            log(f"  ✅ hh_debt_to_income: {quarterly['hh_debt_to_income'].notna().sum()} / {len(quarterly)} quarters")

    if not quarterly.empty:
        quarterly = quarterly.sort_values("date").reset_index(drop=True)
        quarterly["date"] = quarterly["date"].dt.strftime("%Y-%m-%d")
        quarterly.to_sql("derived_quarterly", conn, if_exists="replace", index=False)
        log(f"  ✅ derived_quarterly: {len(quarterly)} rows")

    return monthly, quarterly


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}")
        print("   请先运行: python scripts/01_fetch_data.py")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    monthly, quarterly = compute_derived(conn)
    conn.close()

    log("=" * 50)
    log("衍生指标计算完成！")
    log(f"月度表列: {monthly.columns.tolist()}")
    if not quarterly.empty:
        log(f"季度表列: {quarterly.columns.tolist()}")
    log("=" * 50)


if __name__ == "__main__":
    main()
