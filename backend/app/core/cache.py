"""Cache invalidation — the lru_caches keyed by table/db_path must be cleared
after an atomic DB swap, else the API keeps serving pre-refresh DataFrames.

Targets mirror the analysis engine's cached entry points (migrated from the
analysis modules — themselves UNCHANGED)."""

import analysis.cycle_merrill as _merrill
import analysis.cycle_credit as _credit
import analysis.cycle_inventory as _inventory
import analysis.cycle_debt as _debt
import analysis.signals as _signals
import analysis.real_estate as _real_estate

from backend.app.core.db import _load_full

# Every lru_cache keyed by the (unchanging) db_path string.
_CACHE_TARGETS = (
    _load_full,
    _merrill.classify_merrill,
    _credit.classify_credit,
    _inventory.classify_inventory,
    _debt.classify_debt,
    _signals.compute_signals,
    _real_estate._analyze_real_estate_cached,
)


def clear_all_caches() -> None:
    """Invalidate all data-backed lru_caches so the next read hits the new DB."""
    for fn in _CACHE_TARGETS:
        fn.cache_clear()
