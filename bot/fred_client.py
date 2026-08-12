# -*- coding: utf-8 -*-
"""
FRED(세인트루이스 연은) API 클라이언트.

무료 API 키 발급: https://fredaccount.stlouisfed.org/apikeys
공식 실측치와 과거 시계열(추세 판단용)을 가져오는 데 사용한다.
FRED에 없는 지표(ISM PMI, 컨퍼런스보드 소비자신뢰지수 등)는 None을 반환하므로
호출부에서 캘린더 소스의 actual 값으로 대체해야 한다.
"""
import datetime
from typing import List, Optional, Tuple

import requests

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


def get_observations(series_id: str, api_key: str, limit: int = 14) -> List[Tuple[str, Optional[float]]]:
    """최근 관측치를 (date, value) 리스트로 반환한다. 최신순 정렬."""
    if not api_key:
        return []
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    resp = requests.get(BASE_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for obs in data.get("observations", []):
        val = obs.get("value")
        try:
            fval = float(val)
        except (TypeError, ValueError):
            fval = None
        out.append((obs["date"], fval))
    return out


def pct_change(curr: float, prev: float) -> Optional[float]:
    if prev in (None, 0):
        return None
    return (curr - prev) / prev * 100.0


def mom_yoy(series_id: str, api_key: str) -> dict:
    """
    월간 지수 시리즈(CPI, PCE 등)에 대해 최신 MoM(전월비)/YoY(전년동월비) 변화율과
    최근 6개월 MoM 추세를 계산해 반환한다.
    """
    obs = get_observations(series_id, api_key, limit=14)
    obs = [o for o in obs if o[1] is not None]
    if len(obs) < 13:
        return {}
    latest_date, latest_val = obs[0]
    prev_month_val = obs[1][1]
    yoy_val = obs[12][1]  # 12개월 전
    mom = pct_change(latest_val, prev_month_val)
    yoy = pct_change(latest_val, yoy_val)
    # 최근 6개월 MoM 추세 (오래된 -> 최신 순)
    trend = []
    for i in range(5, -1, -1):
        if i + 1 < len(obs):
            c = obs[i][1]
            p = obs[i + 1][1]
            trend.append(round(pct_change(c, p), 2) if pct_change(c, p) is not None else None)
    return {
        "latest_date": latest_date,
        "latest_value": latest_val,
        "mom_pct": round(mom, 2) if mom is not None else None,
        "yoy_pct": round(yoy, 2) if yoy is not None else None,
        "mom_trend_6m": trend,
    }


def latest_level_change(series_id: str, api_key: str) -> dict:
    """PAYEMS처럼 '수준(레벨)' 시리즈에서 전월대비 증감(예: 비농업고용 증가폭)을 계산."""
    obs = get_observations(series_id, api_key, limit=3)
    obs = [o for o in obs if o[1] is not None]
    if len(obs) < 2:
        return {}
    latest_date, latest_val = obs[0]
    prev_val = obs[1][1]
    return {
        "latest_date": latest_date,
        "latest_value": latest_val,
        "change": round(latest_val - prev_val, 1),
    }


def latest_value(series_id: str, api_key: str) -> dict:
    obs = get_observations(series_id, api_key, limit=2)
    obs = [o for o in obs if o[1] is not None]
    if not obs:
        return {}
    latest_date, latest_val = obs[0]
    prev_val = obs[1][1] if len(obs) > 1 else None
    return {
        "latest_date": latest_date,
        "latest_value": latest_val,
        "prev_value": prev_val,
    }
