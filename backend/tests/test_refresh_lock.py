"""Refresh single-flight lock (flock) + wall-clock timeout — G02.

These are the regression tests for three mutual-exclusion bugs that could corrupt
the production DB:

* F1 (TOCTOU): the old check-then-touch let two concurrent refreshes both spawn a
  fetcher that raced on the shared staging DB. flock acquires atomically, so a
  second attempt is refused with BlockingIOError.
* F8 (destructive read): the old is_running() unlinked the lock when it looked
  "stale", so a read-only status probe could delete a live refresh's lock. The
  probe here has NO side effect.
* F2 (unenforceable timeout): the old `for line in proc.stdout` blocked in
  readline(), so the deadline never fired while the child hung silently with no
  output. run_refresh now enforces the deadline independently and kills the child.

Run:  .venv312/bin/python -m pytest backend/tests/test_refresh_lock.py -q
"""

import fcntl
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core import locking, refresh  # noqa: E402


# ── F1: atomic single-flight ─────────────────────────────────────────────────
def test_flock_mutual_exclusion_and_probe(tmp_path):
    """While the lock is held, is_running() is True and any independent
    non-blocking flock on the same file is refused; after release it is free."""
    lock = tmp_path / ".refresh.lock"
    with locking.refresh_lock(lock):
        assert locking.is_running(lock) is True
        # a second, independent open + non-blocking flock must be refused
        fd = os.open(lock, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
    # lock released → free again, and a fresh acquisition now succeeds
    assert locking.is_running(lock) is False
    with locking.refresh_lock(lock):
        assert locking.is_running(lock) is True


# ── F8: probe has no destructive side effect ─────────────────────────────────
def test_is_running_has_no_side_effect(tmp_path):
    """Probing is_running() while a refresh holds the lock must NEVER unlink the
    lock file (the old stale-heuristic did, enabling a concurrent second run)."""
    lock = tmp_path / ".refresh.lock"
    with locking.refresh_lock(lock):
        for _ in range(3):
            assert locking.is_running(lock) is True
            assert lock.exists()          # probe did not delete the held lock
    assert lock.exists()                  # file survives release (only flock drops)
    assert locking.is_running(lock) is False


def test_is_running_missing_file_is_false(tmp_path):
    """A missing lock file simply means 'not running' — no creation, no error."""
    lock = tmp_path / "nope.lock"
    assert locking.is_running(lock) is False
    assert not lock.exists()              # probe did not create it


# ── F2: wall-clock deadline is enforced against a silent child ───────────────
def test_run_refresh_kills_silent_hang(tmp_path, monkeypatch):
    """With a tiny REFRESH_TIMEOUT_S and a child that sleeps with NO output
    (mimics a bare no-timeout requests.get), run_refresh must return a timeout
    error within a few seconds and the child must be killed, not left running.

    On the pre-fix code `for line in proc.stdout` blocks in readline(), so the
    deadline check never runs until a line arrives — this would hang ~30s."""
    lock = tmp_path / ".refresh.lock"
    monkeypatch.setattr(refresh, "REFRESH_TIMEOUT_S", 2)
    # hermetic lock (don't touch the real data/.refresh.lock)
    monkeypatch.setattr(refresh, "refresh_lock", lambda: locking.refresh_lock(lock))
    # fake child: sleeps 30s, prints nothing
    monkeypatch.setattr(
        refresh, "_build_cmd",
        lambda full: [sys.executable, "-c", "import time; time.sleep(30)"],
    )

    captured = {}
    real_popen = refresh.subprocess.Popen

    def _spy_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        captured["proc"] = proc
        return proc

    monkeypatch.setattr(refresh.subprocess, "Popen", _spy_popen)

    t0 = time.time()
    result = refresh.run_refresh()
    elapsed = time.time() - t0

    assert elapsed < 15, f"deadline not enforced: run_refresh took {elapsed:.1f}s"
    assert result["status"] == "error"
    assert "超时" in result["msg"]
    # the child process was killed and reaped, not orphaned
    proc = captured["proc"]
    assert proc.poll() is not None


def test_run_refresh_reports_busy_when_locked(tmp_path, monkeypatch):
    """If the lock is already held, run_refresh returns 'busy' atomically without
    spawning any subprocess (the loser of the flock race)."""
    lock = tmp_path / ".refresh.lock"
    monkeypatch.setattr(refresh, "refresh_lock", lambda: locking.refresh_lock(lock))

    def _boom(*a, **k):  # must never be reached while the lock is held
        raise AssertionError("run_refresh spawned a subprocess despite busy lock")

    monkeypatch.setattr(refresh.subprocess, "Popen", _boom)

    with locking.refresh_lock(lock):        # hold it from the test process
        result = refresh.run_refresh()
    assert result["status"] == "busy"
