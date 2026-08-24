#!/usr/bin/env python3
"""
补充社会融资规模增量（PBoC 官方 XLSX）—— 经暂存闸门原子提交。

``ak.macro_china_shrzgm()`` 常滞后 3-4 个月（实测封顶 2026-04），而 PBoC 调查统计司
按月发布社融增量 XLSX（含人民币贷款/委托/信托/未贴现/企业债券/股票分项）。

为何单列一个脚本（而非只靠 01_fetch_data.fetch_social_finance）：
  主管线里 social_finance 排在 leverage（``ak.macro_cnbs`` 走线程超时封装）之后，一旦
  CNBS 超时的被弃线程损坏进程 socket fd（``[Errno 9] Bad file descriptor`` 级联），紧随
  其后的 PBoC requests 也失败、被静默吞成空 → 社融的 05/06/07 永远补不进。本脚本脱离该
  级联，仅做「读现有 social_finance + PBoC 补充 → 闸门 → 原子交换」，故能稳定补齐。

与 03_supplement_leverage 同构：不直接写 live，而是 backup → open_staging(live→staging)
→ 合并 → validate() 闸门 → enforce_indexes + run_derived → commit_staging() 原子交换；
任何一步失败/拒收都丢弃暂存、live 逐字节不动。合并口径与 fetch_social_finance 完全一致：
仅追加「日期 > 现有最大月」且 total 非空（未发布月为 NaN，不追加）的 PBoC 行。

数据来源见 scripts/pbc_shrzgm.py。当 akshare shrzgm 追上后，fetch_social_finance 主源
会自然覆盖这些月份，本脚本可保留作手动补充参考。

Run:  .venv312/bin/python scripts/04_supplement_social_finance.py
"""
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd

# allow `import _pipeline` / `import pbc_shrzgm` whether run as a script or imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pipeline import (  # noqa: E402
    DB_PATH,
    STAGING_PATH,
    VINTAGE_DIR,
    BACKUP_DIR,
    backup_db,
    open_staging,
    commit_staging,
    discard_staging,
    validate,
    enforce_indexes,
    table_distinct_keys,
    run_derived,
)
from pbc_shrzgm import pbc_shrzgm_supplement_df  # noqa: E402 — 单一真相源


def supplement(db_path=DB_PATH, staging_path=STAGING_PATH,
               backup_dir=BACKUP_DIR, vintage_dir=VINTAGE_DIR):
    """Merge PBoC social-finance rows into social_finance THROUGH the staged pipeline.

    Copies the previously-good live DB into staging, appends only PBoC months
    newer than the current max with a non-null ``total`` (unpublished months are
    NaN and never appended — same rule as fetch_social_finance), runs the
    validation gate, rebuilds the UNIQUE index, recomputes derived tables on
    staging (raw+derived stay atomic), and only then atomically swaps staging →
    live with a vintage snapshot of the pre-commit live.

    Returns the number of rows supplemented (0 when there is nothing new).
    Raises FileNotFoundError when there is no live DB, ValueError when the merged
    frame fails the gate, and propagates any error from the staged run — in every
    failure case the staging file is discarded and the live DB is left byte-for-
    byte unchanged. All paths are injectable for testing.
    """
    db_path, staging_path = Path(db_path), Path(staging_path)
    if not db_path.exists():
        raise FileNotFoundError(
            f"live DB not found: {db_path}（请先运行 scripts/01_fetch_data.py）")

    backup_db(db_path, backup_dir)              # recoverable snapshot of live
    open_staging(db_path, staging_path)          # live → staging (old good data inside)
    conn = sqlite3.connect(staging_path)
    try:
        try:
            existing = pd.read_sql("SELECT * FROM social_finance", conn)
        except Exception:
            existing = pd.DataFrame(columns=["date"])

        base_max = existing["date"].max() if "date" in existing.columns and not existing.empty else None
        new_rows = pbc_shrzgm_supplement_df()
        if base_max is not None:
            new_rows = new_rows[new_rows["date"] > base_max]
        new_rows = new_rows.dropna(subset=["total"])   # 不追加未发布月份(NaN)

        if new_rows.empty:
            # nothing to add → never write an unchanged snapshot as if a run landed
            print("  ⏭️  无新增 PBoC 社融行（现有已最新或官方未发布更晚月份），live 保持不动")
            conn.close()
            discard_staging(staging_path)
            return 0

        merged = (pd.concat([existing, new_rows], ignore_index=True)
                    .sort_values("date").reset_index(drop=True))

        prev = table_distinct_keys(conn, "social_finance")   # grain-fair shrink basis
        ok, reason = validate(merged, "social_finance", prev)
        if not ok:
            raise ValueError(f"社融 PBoC 补充被验证闸门拒收，丢弃暂存、live 未改动：{reason}")

        merged.to_sql("social_finance", conn, if_exists="replace", index=False)
        enforce_indexes(conn, "social_finance")   # replace 会丢索引 → 重建唯一索引
        run_derived(conn)                          # raw+derived 原子：同批在暂存库重算派生表
        conn.commit()
    except BaseException:
        # 任何失败/拒收：关连接、丢弃暂存，live 保持上一份一致快照，异常上抛给调用方
        try:
            conn.close()
        except Exception:
            pass
        discard_staging(staging_path)
        raise
    conn.close()

    vintage = commit_staging(staging_path, db_path, vintage_dir)  # 原子交换 + vintage 快照
    for _, r in new_rows.iterrows():
        print(f"  ✅ {r['date']}: inserted (total={r['total']}, rmb_loan={r['rmb_loan']})")
    print(f"\n补充 {len(new_rows)} 行 PBoC 社融（经暂存闸门），live 已原子提交"
          + (f"（vintage {vintage.name}）" if vintage else ""))
    return len(new_rows)


if __name__ == "__main__":
    # 与 01_fetch_data.py / 03 / API 刷新共用同一把 flock：本脚本也写 staging，
    # 必须与其他刷新互斥，避免竞争共享的 data/macro_data.db.staging。
    from contextlib import nullcontext

    print("补充社会融资规模增量（PBoC 官方 XLSX，经暂存闸门原子提交）...")
    if os.getenv("REFRESH_LOCK_HELD") == "1":
        _guard = nullcontext()
    else:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from backend.app.core.locking import refresh_lock
        _guard = refresh_lock()

    try:
        with _guard:
            added = supplement()
        print(f"完成（新增 {added} 行）")
        sys.exit(0)
    except BlockingIOError:
        print("⛔ 已有刷新在进行中（另一进程持有刷新锁），本次退出")
        sys.exit(1)
    except (FileNotFoundError, ValueError) as e:
        print(f"⛔ 补充失败：{e}")
        sys.exit(1)
