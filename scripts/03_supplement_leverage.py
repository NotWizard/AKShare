#!/usr/bin/env python3
"""
补充宏观杠杆率数据（NIFD 季度报告）—— 经暂存闸门原子提交（G26 / P-M8）。

ak.macro_cnbs() (AKShare) 数据滞后；NIFD（国家金融与发展实验室）按季度发布宏观
杠杆率报告，含居民/非金融企业/政府（中央+地方）完整分项。本脚本把这些官方补充
值合并进 leverage 表，作为 fetch_leverage 之外的手动兜底。

改动要点（P-M8）：
  1. NIFD 数据不再在本文件内自存一份，改从 `scripts/nifd_leverage.py` 单一真相源
     引入（此前 01/03 各存一份、逐字重复、极易漂移）。
  2. 不再直接 `INSERT INTO data/macro_data.db`（live 库），而是走与主管线相同的
     暂存路径：backup → open_staging(live→staging) → 合并 → validate() 闸门 →
     在暂存库上 enforce_indexes + run_derived → commit_staging() 原子交换。任何一步
     失败/拒收都丢弃暂存、live 逐字节保持不动，维持「非经闸门，数据不入 live」这一
     核心不变量。（其“日期已存在则跳过”守卫意味着新的唯一索引不改变它的行为。）

数据来源见 scripts/nifd_leverage.py 头部（各季报告链接、交叉验证说明）。
当 ak.macro_cnbs() 更新至 2025+ 数据后，fetch_leverage 会自动覆盖，本脚本可保留
作为手动补充参考。
"""
import os
import sqlite3
import sys
from pathlib import Path

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


def supplement(db_path=DB_PATH, staging_path=STAGING_PATH,
               backup_dir=BACKUP_DIR, vintage_dir=VINTAGE_DIR):
    """Merge NIFD supplement rows into leverage THROUGH the staged pipeline.

    Copies the previously-good live DB into staging, appends only NIFD dates not
    already present (the same "skip existing dates" behaviour the old direct
    INSERT had), runs the validation gate, rebuilds the UNIQUE index, recomputes
    derived tables on staging (raw+derived stay atomic), and only then atomically
    swaps staging → live with a vintage snapshot of the pre-commit live.

    Returns the number of NIFD rows supplemented (0 when there is nothing new).
    Raises FileNotFoundError when there is no live DB to supplement, ValueError
    when the merged frame fails the gate, and propagates any error from the
    staged run — in every failure case the staging file is discarded and the live
    DB is left byte-for-byte unchanged. All paths are injectable for testing.
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
            existing = pd.read_sql("SELECT * FROM leverage", conn)
        except Exception:
            existing = pd.DataFrame(columns=["date"])

        existing_dates = set(existing["date"]) if "date" in existing.columns else set()
        new_rows = nifd_supplement_df()
        new_rows = new_rows[~new_rows["date"].isin(existing_dates)]

        if new_rows.empty:
            # nothing to add → never write an unchanged snapshot as if a run landed
            print("  ⏭️  无新增 NIFD 行（现有 leverage 已覆盖全部日期），live 保持不动")
            conn.close()
            discard_staging(staging_path)
            return 0

        merged = (pd.concat([existing, new_rows], ignore_index=True)
                    .sort_values("date").reset_index(drop=True))

        prev = table_distinct_keys(conn, "leverage")     # grain-fair shrink basis
        ok, reason = validate(merged, "leverage", prev)
        if not ok:
            raise ValueError(f"NIFD 杠杆率补充被验证闸门拒收，丢弃暂存、live 未改动：{reason}")

        merged.to_sql("leverage", conn, if_exists="replace", index=False)
        enforce_indexes(conn, "leverage")     # replace 会丢索引 → 重建唯一索引
        run_derived(conn)                      # raw+derived 原子：同批在暂存库重算派生表
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
        print(f"  ✅ {r['date']}: inserted (household={r['household']}, "
              f"non_fin={r['non_fin_corp']}, gov={r['gov_total']})")
    print(f"\n补充 {len(new_rows)} 行 NIFD（经暂存闸门），live 已原子提交"
          + (f"（vintage {vintage.name}）" if vintage else ""))
    return len(new_rows)


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
            added = supplement()
        print(f"完成（新增 {added} 行）")
        sys.exit(0)
    except BlockingIOError:
        print("⛔ 已有刷新在进行中（另一进程持有刷新锁），本次退出")
        sys.exit(1)
    except (FileNotFoundError, ValueError) as e:
        print(f"⛔ 补充失败：{e}")
        sys.exit(1)
