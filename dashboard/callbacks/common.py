"""Shared callback helpers — date-range filtering used by every page."""

from datetime import datetime
from dateutil.relativedelta import relativedelta


def compute_preset_range(
    preset: str,
    max_date: datetime,
    min_date: datetime,
) -> tuple[str, str]:
    """Return ``(start_date, end_date)`` ISO strings for a preset button.

    Parameters
    ----------
    preset : str
        One of ``'5y'``, ``'10y'``, ``'20y'``, ``'all'``.
    max_date, min_date : datetime
        Data boundaries from the database.
    """
    end = max_date.strftime('%Y-%m-%d')
    if preset == '5y':
        start = (max_date - relativedelta(years=5)).strftime('%Y-%m-%d')
    elif preset == '10y':
        start = (max_date - relativedelta(years=10)).strftime('%Y-%m-%d')
    elif preset == '20y':
        start = (max_date - relativedelta(years=20)).strftime('%Y-%m-%d')
    else:  # 'all'
        start = min_date.strftime('%Y-%m-%d')
    return start, end
