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
"""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = PROJECT_ROOT / "data" / ".refresh.lock"


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
