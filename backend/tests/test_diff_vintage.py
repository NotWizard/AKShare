"""diff_vintage — 两快照差异输出（build_report 结构 + CLI exit code）。

构造临时 live/vintage 库对：无差异 → identical/exit 0；新增行或同日期值修订
→ exit 1；无 vintage 基线 → 友好提示 exit 0。

Run:  .venv312/bin/python -m pytest backend/tests/test_diff_vintage.py -q
"""

import json
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import diff_vintage  # noqa: E402

ROWS = [("2026-05-01", 1.0), ("2026-06-01", 0.5)]


def _make_db(path, rows=ROWS):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cpi (date TEXT, cpi_yoy REAL)")
    conn.executemany("INSERT INTO cpi VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def test_identical_snapshots(tmp_path):
    live, vint = tmp_path / "live.db", tmp_path / "v.db"
    _make_db(live)
    shutil.copy2(live, vint)
    r = diff_vintage.build_report(live, vint)
    assert r["identical"] is True
    assert r["tables"]["cpi"] == {"live_rows": 2, "vintage_rows": 2, "delta": 0}
    assert r["series"]["cpi.cpi_yoy"]["diff"] == 0.0


def test_added_row(tmp_path):
    live, vint = tmp_path / "live.db", tmp_path / "v.db"
    _make_db(vint)
    _make_db(live, ROWS + [("2026-07-01", 2.0)])
    r = diff_vintage.build_report(live, vint)
    assert r["identical"] is False
    assert r["tables"]["cpi"]["delta"] == 1
    s = r["series"]["cpi.cpi_yoy"]
    # 新旧月交替：日期不同 → diff 为 None，但仍算有差异
    assert s["live_date"] == "2026-07-01" and s["diff"] is None


def test_same_date_revision(tmp_path):
    live, vint = tmp_path / "live.db", tmp_path / "v.db"
    _make_db(vint)
    _make_db(live, ROWS[:-1] + [("2026-06-01", 0.9)])
    r = diff_vintage.build_report(live, vint)
    assert r["identical"] is False
    assert r["tables"]["cpi"]["delta"] == 0           # 行数没变
    assert r["series"]["cpi.cpi_yoy"]["diff"] == 0.4  # 同日期值修订 live−vintage


def _main(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(diff_vintage, "DB_PATH", tmp_path / "live.db")
    monkeypatch.setattr(diff_vintage, "VINTAGE_DIR", tmp_path / "vintages")
    monkeypatch.setattr(sys, "argv", argv)
    return diff_vintage.main()


def test_cli_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    live, vdir = tmp_path / "live.db", tmp_path / "vintages"
    vdir.mkdir()
    _make_db(live)
    shutil.copy2(live, vdir / "macro_data_20260801_000000.db")
    monkeypatch.setattr(diff_vintage, "DB_PATH", live)
    monkeypatch.setattr(diff_vintage, "VINTAGE_DIR", vdir)

    monkeypatch.setattr(sys, "argv", ["diff_vintage.py", "--json"])
    assert diff_vintage.main() == 0                    # 无差异 → exit 0
    body = json.loads(capsys.readouterr().out)
    assert body["identical"] is True and "series" in body

    live.unlink()
    _make_db(live, ROWS + [("2026-07-01", 2.0)])       # live 新增一月
    assert diff_vintage.main() == 1                    # 有差异 → exit 1


def test_cli_no_vintage_friendly_exit0(tmp_path, monkeypatch):
    _make_db(tmp_path / "live.db")
    assert _main(monkeypatch, tmp_path, ["diff_vintage.py"]) == 0
