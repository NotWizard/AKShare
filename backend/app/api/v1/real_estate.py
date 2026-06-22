"""Real-estate analysis — wraps analysis.real_estate.analyze_real_estate (unchanged).

The analysis returns a dict containing pandas DataFrames (leverage/price/lpr),
which FastAPI can't JSON-encode — convert them to records here.
"""

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from analysis.real_estate import analyze_real_estate
from backend.app.core import db

router = APIRouter(prefix="/real-estate", tags=["real-estate"])

_DEFAULT_CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉", "重庆", "天津"]


def _jsonable(obj):
    if isinstance(obj, pd.DataFrame):
        from backend.app.core.serial import df_to_records
        return df_to_records(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    return obj


@router.get("")
def real_estate(cities: list[str] | None = Query(default=None)):
    """3D real-estate assessment (leverage space / rate / price momentum).

    Accepts repeated ``?cities=A&cities=B`` params (robust vs proxies that
    don't decode commas); defaults to the 10 default cities when omitted.
    """
    city_list = cities or _DEFAULT_CITIES
    # Validate city names against the known set
    invalid = [c for c in city_list if c not in _DEFAULT_CITIES]
    if invalid:
        raise HTTPException(400, f"unknown cities: {invalid}")
    result = analyze_real_estate(str(db.DB_PATH), city_list)
    return _jsonable(result)
