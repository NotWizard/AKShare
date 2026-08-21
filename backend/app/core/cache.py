"""Cache reclaim — drop the data-backed lru_caches in one call.

NOTE: correctness no longer depends on this. Each cache is now keyed by a DB
*version* tag (``db._db_version()`` = mtime_ns+size), so an atomic swap
invalidates entries automatically regardless of who performed the swap (see
``core/db.py`` and ``analysis/signals.py``). ``clear_all_caches()`` remains a
harmless memory-reclaim helper — ``core/refresh.py`` still calls it on a
successful refresh, so it must stay importable and callable.

Targets are the *inner, cache-carrying* entry points (the public ``_load_full``
/ ``compute_signals`` are now thin version-injecting wrappers)."""

import analysis.cycle_merrill as _merrill
import analysis.cycle_credit as _credit
import analysis.cycle_inventory as _inventory
import analysis.cycle_debt as _debt
import analysis.signals as _signals
import analysis.real_estate as _real_estate

from backend.app.core.db import _load_full_versioned

# The lru_cache-carrying functions. _load_full_versioned / _compute_signals_versioned
# key on (…, db_version); the classify_* / real_estate caches still key on the
# db_path string (defined in analysis/cycle_* — out of scope to edit) and are
# invalidated on swap via signals' version gate, but clearing them here is a
# valid memory-reclaim too.
_CACHE_TARGETS = (
    _load_full_versioned,
    _merrill.classify_merrill,
    _credit.classify_credit,
    _inventory.classify_inventory,
    _debt.classify_debt,
    _signals._compute_signals_versioned,
    _real_estate._analyze_real_estate_cached,
)


def clear_all_caches() -> None:
    """Drop all data-backed lru_caches (memory reclaim; not correctness-critical)."""
    for fn in _CACHE_TARGETS:
        fn.cache_clear()
