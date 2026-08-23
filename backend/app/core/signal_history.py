"""Signal history read + flip annotation (written by scripts/signal_history.py).

Table name/DDL intentionally duplicated with the scripts-side writer — same
cross-process constant-copy precedent as MANIFEST_PATH in _pipeline/refresh.
"""

import sqlite3

from backend.app.core.db import DB_PATH, connect

TABLE = "signal_history"
FRAMEWORKS = ("merrill", "credit", "inventory", "debt")


def annotate_flips(rows):
    """rows 新→旧有序；为每行附 flips=[{framework,prev,curr}]（相对相邻更早一行）。
    prev != curr 即翻转（None 视为合法值参与比较）；窗口内最旧一行 flips=[]。"""
    out = []
    for i, r in enumerate(rows):
        flips = []
        if i + 1 < len(rows):
            prev = rows[i + 1]
            flips = [{"framework": f, "prev": prev[f], "curr": r[f]}
                     for f in FRAMEWORKS if r[f] != prev[f]]
        out.append({**r, "flips": flips})
    return out


def read_history(limit=60, db_path=DB_PATH):
    """倒序（rowid DESC，append-only 表 rowid 单调）取 limit+1 行——多取一行
    保证窗口内最旧一行的翻转也能对到前值；表缺失 → []（fresh install 不 500）。

    连接走 `core/db.connect()` 工厂（A-M1）：裸 `sqlite3.connect` 只继承到 WAL
    （DB 文件的持久属性），`busy_timeout` 是连接属性且默认 0，并发写入者一出现
    就抛 `database is locked` 而不是等待。"""
    conn = connect(db_path)
    try:
        cur = conn.execute(
            f"SELECT ts, data_as_of, composite, merrill, credit, inventory, debt "
            f"FROM {TABLE} ORDER BY rowid DESC LIMIT ?", (limit + 1,))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except sqlite3.OperationalError as e:
        # 唯一良性分支：全新安装尚无该表 → 空历史（fresh install 不 500）。
        # 其余（列缺失=schema 漂移、磁盘镜像损坏等）必须冒泡，
        # 避免把"读取失败"静默伪装成"暂无数据"。
        if "no such table" in str(e).lower():
            return []
        raise
    finally:
        conn.close()
    return annotate_flips(rows)[:limit]
