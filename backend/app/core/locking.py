"""OS-level advisory lock for the data-refresh single-flight guard.

Root cure for the three broken-mutual-exclusion bugs (F1/F8):
    * F1 (TOCTOU): the old ``if is_running(): ... LOCK_PATH.touch()`` was a
      check-then-act race — ``Path.touch()`` never fails, so two concurrent
      callers both passed the check and both spawned a refresh that raced on the
      shared staging DB. ``fcntl.flock(LOCK_EX | LOCK_NB)`` acquires atomically:
      exactly one holder wins, every other caller gets ``BlockingIOError``.
    * F8 (destructive read): the old stale-lock heuristic let a read-only status
      probe ``unlink()`` a long-running refresh's lock. The kernel releases a
      flock automatically when the holding process dies, so there is NO stale
      heuristic here (no mtime check, no unlink) — a crashed holder's lock simply
      vanishes and ``is_running()`` never mutates anything.

Both the API refresh driver (``backend.app.core.refresh``) and the CLI fetch
script (``scripts/01_fetch_data.py``) acquire this SAME lock, so an API-triggered
refresh and a manual ``python scripts/01_fetch_data.py`` can never run
concurrently and corrupt the shared ``data/macro_data.db.staging``.

The primitive is parameterised by lock FILE, so it guards two independent
single-flight domains that must not block each other:
    * ``LOCK_PATH``      — the macro fetch pipeline (staging DB writer);
    * ``CRCL_LOCK_PATH`` — the CRCL collector (F6: N clicks used to start N
      concurrent full network collections, all writing crcl_monitor.db).

``submit_job`` adds the other half of the concurrency ceiling (F7): background
work is admitted to ONE small thread pool instead of a new unbounded
``threading.Thread`` per request.
"""

import fcntl
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = PROJECT_ROOT / "data" / ".refresh.lock"
CRCL_LOCK_PATH = PROJECT_ROOT / "data" / ".crcl_collect.lock"


@contextmanager
def refresh_lock(lock_path=LOCK_PATH):
    """Hold the exclusive refresh lock for the whole ``with`` body.

    Acquires ``fcntl.flock(LOCK_EX | LOCK_NB)`` — raises ``BlockingIOError``
    immediately if another process already holds it (single-flight). Writes the
    holder pid into the file for observability. On exit the lock is released and
    the fd closed; the lock FILE is intentionally left on disk — its mere
    presence never implies "locked" (only a live flock does), so nothing needs
    to clean it up and there is no stale-file window.
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # BlockingIOError if held
    except BlockingIOError:
        os.close(fd)
        raise
    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        yield fd
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def is_running(lock_path=LOCK_PATH) -> bool:
    """Side-effect-free probe: is a refresh currently holding the lock?

    Opens the lockfile read-write and tries a non-blocking exclusive flock:
    success → nobody holds it → release the probe lock and return ``False``;
    ``BlockingIOError`` → someone holds it → return ``True``. NEVER creates,
    unlinks, or leaves a lock behind (a missing file simply means "not running").
    """
    lock_path = Path(lock_path)
    try:
        fd = os.open(lock_path, os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


@contextmanager
def crcl_collect_lock(lock_path=CRCL_LOCK_PATH):
    """Single-flight for the CRCL collector — same primitive, DIFFERENT file.

    A separate lock file on purpose: a running macro refresh must not make a
    CRCL collect report "busy" (and vice versa); they touch different DBs.
    """
    with refresh_lock(lock_path) as fd:
        yield fd


# --- bounded background-job admission control (F7) --------------------------
# Before: every SSE request did ``threading.Thread(...).start()`` with no cap, so
# a few dozen tabs/mis-clicks spawned a few dozen concurrent full network
# collections on a single-worker uvicorn. Now ALL background work (macro refresh
# + CRCL collect) shares ONE small pool, and admission is refused rather than
# queued: an unbounded queue would only trade thread exhaustion for latency
# exhaustion (a click "accepted" then serviced 20 minutes later is a lie).
MAX_BACKGROUND_JOBS = int(os.getenv("MAX_BACKGROUND_JOBS", "2"))
_JOB_POOL = ThreadPoolExecutor(max_workers=MAX_BACKGROUND_JOBS,
                               thread_name_prefix="bgjob")
_JOB_SLOTS = threading.BoundedSemaphore(MAX_BACKGROUND_JOBS)


def submit_job(fn, *args, **kwargs):
    """Run ``fn`` on the shared bounded pool; return the Future, or None if full.

    The semaphore (not the executor's own unbounded queue) is what bounds
    concurrency: a caller that cannot get a slot gets ``None`` immediately and
    reports "busy" to the client. The slot is released in the worker's
    ``finally`` so a raising job can never leak it.
    """
    if not _JOB_SLOTS.acquire(blocking=False):
        return None

    def _run():
        try:
            return fn(*args, **kwargs)
        finally:
            _JOB_SLOTS.release()

    try:
        return _JOB_POOL.submit(_run)
    except RuntimeError:  # pool shut down (interpreter teardown)
        _JOB_SLOTS.release()
        return None
