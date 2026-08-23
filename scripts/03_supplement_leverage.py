#!/usr/bin/env python3
"""
补充宏观杠杆率数据（NIFD 季度报告）—— 经暂存闸门原子提交（G26 / P-M8）。

ak.macro_cnbs() (AKShare) 数据滞后；NIFD（国家金融与发展实验室）按季度发布宏观
杠杆率报告，含居民/非金融企业/政府（中央+地方）完整分项。本脚本把这些官方补充
值合并进 leverage 表，作为 fetch_leverage 之外的手动兜底。

改动要点（P-M8）：
  1. NIFD 数据不再在本文件内自存一份，改从 `scripts/nifd_leverage.py` 单一真相源
     引入（此前 01/03 各存一份、逐字重复、极易漂移）。
  2. 不再直接 `INSERT INTO data/macro_data.db`（live 库），而是走与所有写入者相同的
     暂存路径：open_staging(live→staging) → 合并 → validate() 闸门 → 在暂存库上
     重算派生表 → commit_staging() 原子交换。任何一步失败都丢弃暂存、live 保持不动，
     维持「非经闸门，数据不入 live」这一核心不变量。
     （其自带的“日期已存在则跳过”守卫意味着新的唯一索引不改变它的行为。）

数据来源见 scripts/nifd_leverage.py 头部（各季报告链接、交叉验证说明）。
当 ak.macro_cnbs() 更新至 2025+ 数据后，fetch_leverage 会自动覆盖，本脚本可保留
作为手动补充参考。
"""
import os
import sqlite3
import sys

import pandas as pd

# allow `import _pipeline` / `import nifd_leverage` whether run as a script or imported
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
from nifd_leverage import nifd_supplement_df  # noqa: E402 — 单一真相源


def supplement(db_path=DB_PATH, staging_path=STAGING_PATH, vintage_dir=VINTAGE_DIR):
    """Merge NIFD supplement rows into leverage THROUGH the staged pipeline.

    Reads the previously-good leverage from a staging COPY of the live DB, appends
    only NIFD dates not already present (the same "skip existing dates" behaviour
    the old direct-INSERT had), runs the validation gate, recomputes derived
    tables on staging, and only then atomically swaps staging → live. On any gate
    rejection / error the staging file is discarded and the live DB is untouched.

    Returns 0 on success (or when there is nothing new to add), 1 when the gate
    rejected the merged frame. All paths are injectable for testing.
    """
    backup_db(db_path)                      # recoverable snapshot of live
    open_staging(db_path, staging_path)      # live → staging (old good data inside)
    conn = sqlite3.connect(staging_path)
    try:
        try:
            existing = pd.read_sql("SELECT * FROM leverage", conn)
        except Exception:
            existing = pd.DataFrame(columns=["date"])

        existing_dates = set(existing["date"]) if "date" in existing.columns else set()
        nifd = nifd_supplement_df()
        new_rows = nifd[~nifd["date"].isin(existing_dates)]

        if new_rows.empty:
            print("  ⏭️  无新增 NIFD 行（现有 leverage 已覆盖全部日期），live 保持不动")
            conn.close()
            discard_staging(staging_path)    # nothing changed → keep last good snapshot
            return 0

        merged = (pd.concat([existing, new_rows], ignore_index=True)
                    .sort_values("date").reset_index(drop=True))

        prev = table_distinct_keys(conn, "leverage")     # grain-fair shrink basis
        ok, reason = validate(merged, "leverage", prev)
        if not ok:
            print(f"  ⛔ 闸门拒收，丢弃暂存、live 未改动：{reason}")
            conn.close()
            discard_staging(staging_path)
            return 1

        merged.to_sql("leverage", conn, if_exists="replace", index=False)
        enforce_indexes(conn, "leverage")     # replace 会丢索引 → 重建唯一索引
        run_derived(conn)                      # raw+derived 原子：同批重算派生表
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    vintage = commit_staging(staging_path, db_path, vintage_dir)  # 原子交换 + vintage 快照

    for _, r in new_rows.iterrows():
        print(f"  ✅ {r['date']}: inserted (household={r['household']}, "
              f"non_fin={r['non_fin_corp']}, gov={r['gov_total']})")
    print(f"\nInserted {len(new_rows)} NIFD row(s) via staged gate; "
          f"live promoted atomically" + (f" (vintage {vintage.name})" if vintage else ""))
    return 0


if __name__ == "__main__":
    # 与 01_fetch_data.py / API 刷新共用同一把 flock：本脚本现在也写 staging，
    # 必须与其他刷新互斥，避免竞争共享的 data/macro_data.db.staging。
    from contextlib import nullcontext

    print("补充宏观杠杆率数据（NIFD 季度报告，经暂存闸门原子提交）...")
    if os.getenv("REFRESH_LOCK_HELD") == "1":
        _guard = nullcontext()
    else:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from backend.app.core.locking import refresh_lock
        _guard = refresh_lock()

    try:
        with _guard:
            code = supplement()
        print("完成")
        sys.exit(code)
    except BlockingIOError:
        print("⛔ 已有刷新在进行中（另一进程持有刷新锁），本次退出")
        sys.exit(1)
