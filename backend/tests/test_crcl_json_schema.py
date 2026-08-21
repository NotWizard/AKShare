"""G22 — schema validation for the hand-maintained CRCL JSON files.

Deterministic: every case writes a temporary JSON file and monkeypatches the
path the loader reads. The committed data/*.json files are only ever READ
(never mutated).

Pre-fix these discriminator assertions FAIL — the old endpoints did
`json.loads(...)` inside a broad `except` and passed semantic errors straight
through (a stringified number / bad date reached the frontend, and the alerts
engine compared the last two non-null quarters even across a gap). Post-fix
they PASS.

Run: .venv312/bin/python -m pytest backend/tests/test_crcl_json_schema.py -v
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.api.v1 import crcl
from backend.app.core import crcl_alerts, crcl_db

DATA_DIR = PROJECT_ROOT / "data"


VALID_EVENTS = {
    "updated_at": "2026-08-20",
    "events": [
        {"date": "2026-08-05", "category": "财报", "title": "Q2 财报",
         "detail": "x", "source": "IR", "status": "已发生"},
        {"date": "2026-09-16", "category": "里程碑", "title": "Arc 上线",
         "detail": "y", "source": "AMA", "status": "待验证"},
    ],
}

VALID_FUNDAMENTALS = {
    "updated_at": "2026-08-20",
    "flags": {"fed_cutting": True, "clarity_act_passed": False},
    "quarters": [
        {"period": "2026Q1", "nonreserve_share_pct": 6.1, "total_revenue_m": 694},
        {"period": "2026Q2", "nonreserve_share_pct": 4.7, "total_revenue_m": 701},
    ],
    "annual": [{"period": "2024", "distribution_cost_ratio_pct": None}],
    "presale": {"arc_presale_m": 222},
}


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def _point_events(monkeypatch, path: Path):
    monkeypatch.setattr(crcl, "EVENTS_PATH", path)


def _point_fundamentals(monkeypatch, path: Path):
    monkeypatch.setattr(crcl, "FUNDAMENTALS_PATH", path)
    monkeypatch.setattr(crcl_alerts, "FUNDAMENTALS_PATH", path)


def _deepcopy(payload: dict) -> dict:
    return json.loads(json.dumps(payload))


# --------------------------- valid data (contract preserved) ---------------
def test_valid_events_success_shape(tmp_path, monkeypatch):
    _point_events(monkeypatch, _write(tmp_path, "e.json", VALID_EVENTS))
    res = crcl.events()
    assert "error" not in res
    assert res["updated_at"] == "2026-08-20"
    assert [e["title"] for e in res["events"]] == ["Q2 财报", "Arc 上线"]
    for e in res["events"]:  # frontend contract keys survive untouched
        assert set(e) >= {"date", "category", "title", "detail", "source", "status"}


def test_valid_fundamentals_roundtrip(tmp_path, monkeypatch):
    _point_fundamentals(monkeypatch, _write(tmp_path, "f.json", VALID_FUNDAMENTALS))
    res = crcl.fundamentals()
    assert "error" not in res
    # success path returns the ORIGINAL object unchanged (no reserialization)
    assert res == VALID_FUNDAMENTALS


# --------------------------- number-as-string ------------------------------
def test_fundamentals_number_as_string_rejected(tmp_path, monkeypatch):
    bad = _deepcopy(VALID_FUNDAMENTALS)
    bad["quarters"][1]["nonreserve_share_pct"] = "4.7"   # string, not a number
    _point_fundamentals(monkeypatch, _write(tmp_path, "f.json", bad))
    res = crcl.fundamentals()
    # OLD code passed "4.7" straight through (no error); NEW rejects it loudly.
    assert "error" in res, "stringified number must be rejected, not passed through"
    assert "nonreserve_share_pct" in res["error"]      # field-located


# --------------------------- bad dates -------------------------------------
@pytest.mark.parametrize("bad_date", ["2026/08/05", "2026-13-01"])
def test_events_bad_date_rejected(tmp_path, monkeypatch, bad_date):
    bad = _deepcopy(VALID_EVENTS)
    bad["events"][0]["date"] = bad_date
    _point_events(monkeypatch, _write(tmp_path, "e.json", bad))
    res = crcl.events()
    assert "error" in res, f"bad date {bad_date} must be rejected"
    assert res["events"] == []
    assert "date" in res["error"]                       # field-located


def test_events_bad_enum_rejected(tmp_path, monkeypatch):
    bad = _deepcopy(VALID_EVENTS)
    bad["events"][0]["status"] = "不存在的状态"
    _point_events(monkeypatch, _write(tmp_path, "e.json", bad))
    res = crcl.events()
    assert "error" in res
    assert "status" in res["error"]


# --------------------------- alerts adjacency ------------------------------
def _run_stagnant():
    return crcl_alerts._EVALUATORS["y_nonreserve_stagnant"]()


def test_alerts_gap_not_treated_as_consecutive(tmp_path, monkeypatch):
    # Q2 missing → Q1 and Q3 are NOT adjacent; a <1pp delta between them must
    # NOT be reported as "two consecutive stagnant quarters".
    gapped = {
        "flags": {}, "annual": [],
        "quarters": [
            {"period": "2026Q1", "nonreserve_share_pct": 6.00},
            {"period": "2026Q3", "nonreserve_share_pct": 6.05},
        ],
    }
    _point_fundamentals(monkeypatch, _write(tmp_path, "f.json", gapped))
    status, msg = _run_stagnant()
    assert status == "insufficient_data", f"gap must not trigger; got {status}: {msg}"
    assert status != "triggered"


def test_alerts_adjacent_quarters_still_evaluated(tmp_path, monkeypatch):
    # Regression guard: genuinely adjacent quarters still evaluate as before.
    adjacent = {
        "flags": {}, "annual": [],
        "quarters": [
            {"period": "2026Q1", "nonreserve_share_pct": 4.70},
            {"period": "2026Q2", "nonreserve_share_pct": 4.80},
        ],
    }
    _point_fundamentals(monkeypatch, _write(tmp_path, "f.json", adjacent))
    status, msg = _run_stagnant()
    assert status == "triggered", f"adjacent <1pp must trigger; got {status}: {msg}"


# --------------------------- loader surfaces a clear error -----------------
def test_loader_raises_field_located_error(tmp_path, monkeypatch):
    bad = _deepcopy(VALID_FUNDAMENTALS)
    bad["quarters"][0]["nonreserve_share_pct"] = "6.1"
    _point_fundamentals(monkeypatch, _write(tmp_path, "f.json", bad))
    with pytest.raises(crcl_alerts.CrclDataError) as ei:
        crcl_alerts._load_fundamentals()
    assert "nonreserve_share_pct" in str(ei.value)


def test_alerts_stringified_number_surfaces_clear_message(tmp_path, monkeypatch):
    # Through the evaluate() path: a stringified number no longer degrades to a
    # swallowed TypeError → "评估异常"; it becomes a clear "数据校验失败" message.
    db = tmp_path / "crcl.db"
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", db)
    crcl_db.ensure_schema()

    bad = _deepcopy(VALID_FUNDAMENTALS)
    bad["quarters"][1]["nonreserve_share_pct"] = "4.7"
    _point_fundamentals(monkeypatch, _write(tmp_path, "f.json", bad))

    crcl_alerts.evaluate("run-test")
    row = crcl_db.get_rule_status().get("y_nonreserve_stagnant", {})
    assert row.get("status") == "insufficient_data"
    assert "数据校验失败" in row.get("message", "")
    assert "评估异常" not in row.get("message", "")
    assert "nonreserve_share_pct" in row.get("message", "")


# --------------------------- real data still validates ---------------------
def test_real_data_files_validate_under_schema():
    # Read-only sanity: the committed hand-maintained files must not be
    # over-constrained by the new schema.
    events = json.loads((DATA_DIR / "crcl_events.json").read_text(encoding="utf-8"))
    fundamentals = json.loads((DATA_DIR / "crcl_fundamentals.json").read_text(encoding="utf-8"))
    crcl.CrclEventsFile.model_validate(events)
    crcl_alerts.FundamentalsFile.model_validate(fundamentals)
