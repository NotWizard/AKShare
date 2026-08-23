"""Pytest session setup shared by the whole backend suite.

Seeding seam (G16)
------------------
Several tests read the real ``data/macro_data.db`` / ``data/crcl_monitor.db``
(they ``shutil.copy2`` a temp copy, ``assert`` the file exists, or ``pytest.skip``
when it is absent). On CI / a fresh clone those files do not exist, so the tests
either failed or skipped. This autouse session fixture seeds them from the
committed fixtures under ``backend/tests/fixtures/`` **only when the real file is
absent**, and removes exactly what it created on teardown.

Critical property: when the real DBs ARE present (a normal developer machine),
this is a strict no-op — nothing is copied, nothing is deleted — so it cannot
perturb the existing green baseline. It never overwrites a real DB.
"""

import shutil
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parents[1]          # backend/tests → backend → repo root
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))     # so `import analysis` / `import backend` resolve

_FIXTURES = _TESTS_DIR / "fixtures"
_DATA_DIR = _PROJECT_ROOT / "data"
# real filename → committed fixture (must match backend.app.core.db.DB_PATH /
# crcl_db.CRCL_DB_PATH, which both resolve to <repo>/data/<name>).
_SEEDS = {
    "macro_data.db": _FIXTURES / "macro_data.db",
    "crcl_monitor.db": _FIXTURES / "crcl_monitor.db",
}


@pytest.fixture(scope="session", autouse=True)
def _seed_missing_dbs():
    created = []
    for name, fixture in _SEEDS.items():
        target = _DATA_DIR / name
        if not target.exists() and fixture.exists():
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixture, target)
            created.append(target)
    yield
    # Remove ONLY the files this fixture seeded (plus any WAL sidecars the app
    # spawned when it opened them). A real developer DB is never touched.
    for target in created:
        for p in (target, Path(f"{target}-wal"), Path(f"{target}-shm")):
            p.unlink(missing_ok=True)
