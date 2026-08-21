"""Health truthfulness (O-C1/B1 + P-H2) — the health signals must not lie.

Encodes the spec fix for two false-green bugs and the silent-failure bug:
  * an EMPTY sources list = no valid run recorded → ``unknown`` (gray), never
    ``green`` (old code short-circuited to green);
  * a STALE manifest (older than the monthly-cadence threshold) → downgraded,
    even when every source looks individually fine (old code had no staleness
    judgement at all);
  * the fetch pipeline must surface a real fetch/validate failure via a nonzero
    process exit code (old ``main()`` always fell through to exit 0).

The first two assertions FAIL on the original refresh.sources_health (returns
green); the exit-code helper does not exist on the original code.

Run:  .venv312/bin/python -m pytest backend/tests/test_health_truthfulness.py -q
"""

import importlib.util
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.refresh import sources_health  # noqa: E402


def _src(table, cf=0, ok=True):
    return {"table": table, "channel": "test", "ok": ok, "elapsed_s": 0.1,
            "error": None, "consecutive_failures": cf, "last_success": None}


def _ts(days_ago=0):
    """A parseable manifest timestamp ``days_ago`` days in the past (iso_ts fmt)."""
    return (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds")


# ── health must not lie ───────────────────────────────────────────────────────
def test_empty_sources_is_unknown_not_green():
    """Empty sources = no valid run recorded → unknown (gray), never green.
    (Original code returned green here — the core B1 false-green bug.)"""
    h = sources_health({"ts": _ts(), "sources": []})
    assert h["status"] == "unknown"
    assert h["status"] != "green"


def test_stale_manifest_not_green():
    """A 60-day-old manifest (monthly macro cadence → 40d threshold) is stale →
    not green, even when every source looks individually fine.
    (Original code: green, because there was no staleness rule.)"""
    m = {"ts": _ts(days_ago=60),
         "tables": {"cpi": {"status": "updated"}},
         "sources": [_src("cpi"), _src("ppi")]}
    h = sources_health(m)
    assert h["status"] != "green"
    assert h["status"] in ("yellow", "red")


def test_very_stale_manifest_is_red():
    """Way past threshold (>2×, ~90d) → red: badly stale data is a hard failure."""
    m = {"ts": _ts(days_ago=90),
         "tables": {"cpi": {"status": "updated"}},
         "sources": [_src("cpi")]}
    assert sources_health(m)["status"] == "red"


def test_fresh_all_ok_is_green():
    """Fresh manifest + all sources ok → green: the staleness rule must not
    false-positive on recent data."""
    m = {"ts": _ts(days_ago=1),
         "tables": {"cpi": {"status": "updated"}},
         "sources": [_src("cpi"), _src("ppi")]}
    assert sources_health(m)["status"] == "green"


def test_staleness_only_escalates_never_downgrades():
    """A per-source failure (red) stays red even if the manifest is fresh, and a
    fresh yellow stays yellow — staleness can only make things worse."""
    fresh_red = {"ts": _ts(days_ago=1), "tables": {},
                 "sources": [_src("gdp", cf=2, ok=False)]}
    assert sources_health(fresh_red)["status"] == "red"


# ── exit-code aggregation (fetch pipeline) ────────────────────────────────────
def _load_fetch_module():
    """Load scripts/01_fetch_data.py to test the pure compute_exit_code helper.

    akshare is its only heavy top-level import (and importing it into the pytest
    process is known to fail here without the expat DYLD path — see
    refresh._subprocess_env), so stub it. Every other transitive import
    (_pipeline, release_calendar, dual_sources, signal_history→analysis.signals)
    is akshare-free at module load."""
    sys.modules.setdefault("akshare", types.ModuleType("akshare"))
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(
        "_fetch_data_under_test", scripts_dir / "01_fetch_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exit_code_zero_when_all_updated():
    mod = _load_fetch_module()
    manifest = {"tables": {"cpi": {"status": "updated"},
                           "ppi": {"status": "updated"}}}
    assert mod.compute_exit_code(manifest) == 0


def test_exit_code_nonzero_on_kept_previous_failure():
    mod = _load_fetch_module()
    manifest = {"tables": {"cpi": {"status": "updated"},
                           "ppi": {"status": "kept_previous", "reason": "empty result"}}}
    assert mod.compute_exit_code(manifest) == 2


def test_exit_code_ignores_out_of_window_skips():
    """A table skipped outside its release window is carried in `sources` but is
    ABSENT from `tables` → it must NOT count as a failure. This is the
    real-failure-vs-in-window-skip distinction the exit code hinges on."""
    mod = _load_fetch_module()
    manifest = {
        "tables": {"cpi": {"status": "updated"}},          # attempted, clean
        "sources": [{"table": "cpi", "ok": True, "consecutive_failures": 0},
                    {"table": "gdp", "ok": True,           # carried over, not attempted
                     "consecutive_failures": 0}],
    }
    assert mod.compute_exit_code(manifest) == 0


def test_exit_code_zero_on_empty_window():
    """No tables attempted at all (all outside their windows) → clean no-op → 0."""
    mod = _load_fetch_module()
    assert mod.compute_exit_code({"tables": {}}) == 0
