"""Thin database access helper — load any table as a filtered DataFrame."""

import sqlite3
import pandas as pd
from dashboard.config import DB_PATH


def load(table: str, start_date=None, end_date=None) -> pd.DataFrame:
    """Return *table* as a DataFrame with ``date`` parsed to datetime.

    Parameters
    ----------
    table : str
        Table name (e.g. ``'derived_monthly'``).
    start_date, end_date : str or datetime-like, optional
        Inclusive date boundaries applied after loading.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(f"SELECT * FROM [{table}]", conn)
    finally:
        conn.close()

    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])

    if start_date is not None:
        df = df[df['date'] >= pd.Timestamp(start_date)]
    if end_date is not None:
        df = df[df['date'] <= pd.Timestamp(end_date)]

    return df
