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

``create_job``/``get_job`` (F4) add a thin *registry* over that same pool so a
mutation and its progress stream can be split across two requests: the POST
starts the job and gets back an id, and the SSE GET only looks the job up and
replays its progress. No second executor, no second lock — a Job is just the
progress buffer + cancellation handle for one ``submit_job`` submission.
"""

import asyncio
import fcntl
import os
import threading
import time
import uuid
from collections import OrderedDict, deque
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


# --- job registry: POST starts the work, a later GET subscribes (F4) --------
# Both refresh streams used to START their mutation from a GET, so
# ``<img src="…/crcl/refresh/stream">`` — or a browser prefetch/prerender, or a
# link scanner — ran a full network collection. The mutation now lives on the
# POST alone; the POST registers a Job here and returns its id, and the SSE GET
# only looks the id up. A Job therefore has to survive between two requests and
# be readable by a subscriber that attaches AFTER work began, hence the replay
# buffer below.
JOB_TTL_S = int(os.getenv("JOB_TTL_S", "600"))   # a finished job stays subscribable
MAX_JOBS = 32                                    # registry ceiling
PROGRESS_BUFFER = 4096                           # replayable ticks per job


class Job:
    """One ``submit_job`` submission plus everything its stream needs.

    * ``emit`` (worker thread) appends the tick to the replay buffer AND pushes
      it to every attached listener via ``loop.call_soon_threadsafe``, i.e. the
      same zero-threadpool-token hand-off the inline SSE worker used to do.
    * ``subscribe`` (event loop) replays the buffer into a fresh
      ``asyncio.Queue`` and registers as a listener *under the same lock*, so no
      tick can be lost or duplicated in the gap between the two.
    """

    __slots__ = ("id", "stop_event", "result", "done", "finished_at",
                 "_items", "_listeners", "_lock")

    def __init__(self, job_id: str):
        self.id = job_id
        self.stop_event = threading.Event()
        self.result = None
        self.done = False
        self.finished_at: float | None = None
        self._items: deque = deque(maxlen=PROGRESS_BUFFER)
        self._listeners: list = []
        self._lock = threading.Lock()

    # -- worker side (background thread) ------------------------------------
    def progress(self, frac: float) -> None:
        """``progress_cb`` handed to the runner; dropped once cancelled."""
        if not self.stop_event.is_set():
            self.emit(frac)

    def emit(self, item) -> None:
        """Publish a progress fraction, or ``None`` as the terminal sentinel."""
        with self._lock:
            if item is None:
                self.done = True
                self.finished_at = time.monotonic()
            else:
                self._items.append(item)
            listeners = list(self._listeners)
        for loop, q in listeners:
            try:
                loop.call_soon_threadsafe(q.put_nowait, item)
            except RuntimeError:
                pass  # that subscriber's event loop is gone (client left)

    # -- subscriber side (event loop) --------------------------------------
    def subscribe(self, loop) -> asyncio.Queue:
        """Queue pre-filled with everything already emitted, then live ticks."""
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            for item in self._items:
                q.put_nowait(item)
            if self.done:
                q.put_nowait(None)          # nothing more will ever be emitted
            else:
                self._listeners.append((loop, q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._listeners = [entry for entry in self._listeners if entry[1] is not q]


_JOBS: "OrderedDict[str, Job]" = OrderedDict()
_JOBS_LOCK = threading.Lock()


def _prune_jobs() -> None:
    """Drop expired jobs, then evict oldest FINISHED ones over the ceiling.

    Caller holds ``_JOBS_LOCK``. A running job is never the preferred victim, so
    the registry cannot forget a job someone is still streaming.
    """
    now = time.monotonic()
    for jid, job in list(_JOBS.items()):
        if job.finished_at is not None and now - job.finished_at > JOB_TTL_S:
            del _JOBS[jid]
    while len(_JOBS) > MAX_JOBS:
        victim = next((jid for jid, job in _JOBS.items() if job.done),
                      next(iter(_JOBS)))
        del _JOBS[victim]


def create_job(runner) -> Job | None:
    """Start ``runner(progress_cb, stop_event)`` on the shared bounded pool.

    Returns the registered Job — whose ``id`` is the handle the SSE subscriber
    passes back — or ``None`` when the pool is saturated, i.e. exactly the
    ``submit_job`` admission rule: refused, never queued.
    """
    job = Job(uuid.uuid4().hex)     # unguessable id; buffers from birth

    def _work():
        try:
            job.result = runner(job.progress, job.stop_event)
        finally:
            job.emit(None)          # sentinel: finished, even if runner raised

    if submit_job(_work) is None:
        return None
    with _JOBS_LOCK:
        _JOBS[job.id] = job
        _prune_jobs()
    return job


def get_job(job_id: str) -> Job | None:
    """Look a job up by id — pure read, never creates or starts anything."""
    with _JOBS_LOCK:
        return _JOBS.get(job_id)
