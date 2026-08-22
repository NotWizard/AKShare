"""WAL 与整库交换的相互作用（A-M1 修复的副作用收口）。

后端连接工厂启用 `journal_mode=WAL` 后，`scripts/_pipeline.py` 仍用
`shutil.copy2` + `os.replace` 搬整个库文件，而 **copy2 不会带走 `-wal` 边车**：

* `open_staging()` 不先 checkpoint → staging 丢掉仍留在 WAL 中的已提交事务；
* `commit_staging()` 交换后若留着旧 inode 的 `-wal` → SQLite 可能把它恢复到新文件上。

改前这两个用例都失败（staging 读不到写入的行 / 交换后残留边车），改后通过。
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import _pipeline  # noqa: E402


def _wal_db_with_uncheckpointed_row(path):
    """建一个 WAL 库并写一行，且**不做 checkpoint** —— 该行只在 -wal 里。"""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('committed-into-wal')")
    conn.commit()
    # 关闭会触发自动 checkpoint，所以保持连接打开，模拟"提交仍在 WAL 中"。
    return conn


def test_open_staging_keeps_wal_committed_rows(tmp_path):
    live = tmp_path / "live.db"
    staging = tmp_path / "live.db.staging"
    conn = _wal_db_with_uncheckpointed_row(live)
    try:
        assert Path(str(live) + "-wal").exists(), "前置条件：-wal 边车应存在"
        _pipeline.open_staging(db_path=live, staging_path=staging)
    finally:
        conn.close()

    got = sqlite3.connect(staging).execute("SELECT v FROM t").fetchall()
    assert got == [("committed-into-wal",)], (
        "staging 丢了仍在 -wal 中的已提交行（copy2 不带边车，需先 checkpoint）"
    )


def test_commit_staging_leaves_no_stale_sidecar(tmp_path):
    live = tmp_path / "live.db"
    staging = tmp_path / "live.db.staging"
    conn = _wal_db_with_uncheckpointed_row(live)
    try:
        _pipeline.open_staging(db_path=live, staging_path=staging)
    finally:
        conn.close()

    # staging 上再写一行并保持 WAL 未 checkpoint，然后提交交换。
    sconn = sqlite3.connect(staging)
    sconn.execute("PRAGMA journal_mode = WAL")
    sconn.execute("INSERT INTO t VALUES ('from-staging')")
    sconn.commit()
    sconn.close()

    _pipeline.commit_staging(
        staging_path=staging, db_path=live, vintage_dir=tmp_path / "vintages"
    )

    assert not Path(str(live) + "-wal").exists(), "交换后不应残留旧 inode 的 -wal"
    assert not Path(str(live) + "-shm").exists(), "交换后不应残留旧 inode 的 -shm"
    rows = {r[0] for r in sqlite3.connect(live).execute("SELECT v FROM t")}
    assert rows == {"committed-into-wal", "from-staging"}
