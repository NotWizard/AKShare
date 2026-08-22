"""CRCL collector single-flight + enforceable third-party timeout — G09/F6.

Pre-fix, ``POST /crcl/refresh`` (and the SSE variant, and the startup hook) all
called ``crcl_collect.collect_all()`` with:
  * NO single-flight guard — N clicks started N concurrent full collections, all
    writing the same crcl_monitor.db (the macro refresh has had a flock for ages);
  * NO enforceable timeout — the httpx sources pass ``timeout=30`` correctly, but
    ``ak.stock_us_daily`` goes through akshare's internal BARE ``requests.get``
    and yfinance is equally uncontrolled, so a black-holed host pinned the
    calling thread (a threadpool token) forever;
  * a startup collection in a bare background thread that could race/duplicate a
    user-triggered one.

Hermetic: the lock file and the DB live under tmp_path, every network collector
is stubbed, and no test touches data/*.db or the real lock files.

Run: .venv312/bin/python -m pytest backend/tests/test_crcl_concurrency.py -q
"""

import logging
import sys
import threading
import time
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import crcl_alerts, crcl_collect, crcl_db, locking  # noqa: E402

_COLLECTORS = ("collect_usdc_circ", "collect_stablecoin_total", "collect_eurc_circ",
               "collect_treasury", "collect_crcl_stock")


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    """Tmp lock file + tmp CRCL DB (never data/*.db). Returns the lock path."""
    lock = tmp_path / ".crcl_collect.lock"
    monkeypatch.setattr(crcl_collect, "crcl_collect_lock",
                        lambda: locking.crcl_collect_lock(lock))
    monkeypatch.setattr(crcl_db, "CRCL_DB_PATH", tmp_path / "crcl.db")
    crcl_db.ensure_schema()
    return lock


@pytest.fixture
def hermetic(tmpdb, monkeypatch):
    """tmpdb + every network collector stubbed. Returns (lock_path, calls list)."""
    calls: list[str] = []
    for name in _COLLECTORS:
        monkeypatch.setattr(crcl_collect, name,
                            lambda run_id, _n=name: (calls.append(_n), 0)[1])
    monkeypatch.setattr(crcl_collect, "collect_valuation_snapshot", lambda run_id: True)
    monkeypatch.setattr(crcl_collect, "update_circ_snapshot", lambda run_id: None)
    monkeypatch.setattr(crcl_alerts, "evaluate", lambda run_id: [])
    return tmpdb, calls


# ── single-flight ────────────────────────────────────────────────────────────
def test_second_collect_is_busy_and_does_not_run(hermetic):
    """While the CRCL lock is held, collect_all returns busy WITHOUT collecting.
    (Pre-fix there was no lock at all: every caller ran a full collection.)"""
    lock, calls = hermetic
    with locking.crcl_collect_lock(lock):        # held by the "first" collect
        result = crcl_collect.collect_all()
    assert result["status"] == "busy"
    assert calls == [], f"a second collection ran anyway: {calls}"


def test_concurrent_collects_run_exactly_once(hermetic, monkeypatch):
    """Two overlapping collect_all calls → one runs, the other reports busy."""
    lock, calls = hermetic
    entered, release = threading.Event(), threading.Event()

    def _slow(run_id):
        calls.append("slow")
        entered.set()
        release.wait(5)
        return 0

    monkeypatch.setattr(crcl_collect, "collect_usdc_circ", _slow)
    box: dict = {}
    t = threading.Thread(target=lambda: box.update(first=crcl_collect.collect_all()))
    t.start()
    try:
        assert entered.wait(5), "first collection never started"
        second = crcl_collect.collect_all()      # overlaps the first
    finally:
        release.set()
        t.join(10)
    assert second["status"] == "busy"
    assert box["first"]["status"] == "ok"
    assert calls.count("slow") == 1, f"collector ran {calls.count('slow')}×"


def test_crcl_lock_is_a_different_file_from_the_refresh_lock(tmp_path, monkeypatch):
    """A running macro refresh must not make a CRCL collect report busy."""
    assert locking.CRCL_LOCK_PATH != locking.LOCK_PATH
    macro_lock = tmp_path / ".refresh.lock"
    crcl_lock = tmp_path / ".crcl_collect.lock"
    with locking.refresh_lock(macro_lock):
        assert locking.is_running(macro_lock) is True
        assert locking.is_running(crcl_lock) is False   # independent domain
        with locking.crcl_collect_lock(crcl_lock):      # acquirable regardless
            assert locking.is_running(crcl_lock) is True


# ── enforceable timeout for uncontrollable third-party calls ────────────────
def test_call_with_timeout_gives_up(monkeypatch):
    """A never-returning call raises TimeoutError instead of blocking forever."""
    monkeypatch.setattr(crcl_collect, "THIRD_PARTY_TIMEOUT_S", 1)
    t0 = time.time()
    with pytest.raises(TimeoutError):
        crcl_collect._call_with_timeout(lambda: time.sleep(30))
    assert time.time() - t0 < 5


def test_call_with_timeout_passes_values_and_errors_through(monkeypatch):
    monkeypatch.setattr(crcl_collect, "THIRD_PARTY_TIMEOUT_S", 5)
    assert crcl_collect._call_with_timeout(lambda: 42) == 42
    with pytest.raises(ValueError):
        crcl_collect._call_with_timeout(lambda: (_ for _ in ()).throw(ValueError("x")))


def test_hung_akshare_does_not_pin_the_thread(tmpdb, monkeypatch):
    """A black-holed akshare endpoint is abandoned after the ceiling, the source
    is logged as failed, and the collector returns — pre-fix this blocked for as
    long as the fake sleeps (i.e. forever, in production)."""
    monkeypatch.setattr(crcl_collect, "THIRD_PARTY_TIMEOUT_S", 1)
    monkeypatch.setitem(sys.modules, "akshare", types.SimpleNamespace(
        stock_us_daily=lambda symbol: time.sleep(6)))
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(
        Ticker=lambda s: (_ for _ in ()).throw(RuntimeError("offline"))))

    t0 = time.time()
    n = crcl_collect.collect_crcl_stock("run-test")
    elapsed = time.time() - t0

    assert n == 0
    assert elapsed < 4, f"hung third-party call was not bounded ({elapsed:.1f}s)"
    sources = {row["source"] for row in crcl_db.get_logs(limit=10)}
    assert "akshare_crcl" in sources


# ── startup collection cannot stampede a user-triggered one ─────────────────
def test_startup_collection_skips_when_a_collect_is_running(hermetic, caplog):
    """With the lock held, the startup hook's thread reports "skip" and collects
    nothing (pre-fix it fired an unguarded second full collection)."""
    lock, calls = hermetic
    with locking.crcl_collect_lock(lock), caplog.at_level(logging.INFO):
        crcl_collect.schedule_startup_collection()
        for _ in range(80):    # ≤2s, exits as soon as the skip is logged
            if any("启动采集跳过" in r.message for r in caplog.records):
                break
            time.sleep(0.025)
    assert any("启动采集跳过" in r.message for r in caplog.records), \
        "startup collection did not report a skip"
    assert calls == [], f"startup collection stampeded a running collect: {calls}"


def test_startup_collection_is_skippable(monkeypatch):
    """CRCL_STARTUP_COLLECT=0 still short-circuits before any thread is started."""
    monkeypatch.setenv("CRCL_STARTUP_COLLECT", "0")
    monkeypatch.setattr(crcl_collect, "collect_all",
                        lambda **k: pytest.fail("collect_all must not run"))
    crcl_collect.schedule_startup_collection()


# ── cooperative cancellation ────────────────────────────────────────────────
def test_stop_event_cancels_between_steps(hermetic):
    """A set stop_event (SSE client disconnected) aborts before any collector
    runs; the macro refresh has had this for ages, the CRCL worker had none."""
    lock, calls = hermetic
    stop = threading.Event()
    stop.set()
    result = crcl_collect.collect_all(stop_event=stop)
    assert result["status"] == "cancelled"
    assert calls == []
