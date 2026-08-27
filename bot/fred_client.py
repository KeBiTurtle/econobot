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


# ---------------------------------------------------------------------------
# actual(실측치) 보강: ForexFactory의 actual 필드는 실제 발표 후 몇 시간이 지나도
# 비어있는 경우가 흔하다(실측 확인됨). 그 상태로는 main.py의 "발표 결과" 단계가
# has_actual=False로 영원히 막혀서 결과/해석 메시지가 아예 안 나가는 문제가 생긴다.
# 여기서 FRED 공식 데이터로 캘린더의 actual을 직접 채워 그 문제를 우회한다.
# ---------------------------------------------------------------------------
_ACTUAL_MATCH_TABLE = [
    # (ff_title에 포함된 키워드(소문자), FRED series_id, kind, 제외 키워드)
    ("core cpi", "CPILFESL", "mom_yoy", []),
    ("cpi", "CPIAUCSL", "mom_yoy", []),
    ("core pce", "PCEPILFE", "mom_yoy", []),
    ("pce price", "PCEPI", "mom_yoy", []),
    ("core ppi", "PPIFES", "mom_yoy", []),
    ("ppi", "PPIFIS", "mom_yoy", ["core"]),
    ("unemployment rate", "UNRATE", "value", []),
    ("non-farm employment change", "PAYEMS", "level_change", []),
    ("nonfarm payrolls", "PAYEMS", "level_change", []),
    ("jolts", "JTSJOL", "level_million", []),
    ("gdp", "A191RL1Q225SBEA", "value", ["price index"]),  # GDP 가격지수는 다른 지표라 제외
    ("unemployment claims", "ICSA", "level_thousand", []),
]


def _match_actual_series(ff_title_lower: str):
    for kw, series_id, kind, exclude in _ACTUAL_MATCH_TABLE:
        if kw in ff_title_lower and not any(x in ff_title_lower for x in exclude):
            return series_id, kind
    return None, None


def _fetch_latest_for_kind(series_id: str, kind: str, api_key: str, title_l: str):
    """(관측일자, 포맷된 문자열) 튜플을 반환한다. 값이 없으면 (None, None)."""
    if kind == "value":
        lv = latest_value(series_id, api_key)
        v = lv.get("latest_value")
        return (lv.get("latest_date"), f"{v:.1f}%") if v is not None else (None, None)
    if kind == "level_million":
        lv = latest_value(series_id, api_key)
        v = lv.get("latest_value")
        return (lv.get("latest_date"), f"{v / 1000:.2f}M") if v is not None else (None, None)
    if kind == "level_change":
        lc = latest_level_change(series_id, api_key)
        v = lc.get("change")
        return (lc.get("latest_date"), f"{v:+.0f}K") if v is not None else (None, None)
    if kind == "level_thousand":
        lv = latest_value(series_id, api_key)
        v = lv.get("latest_value")
        return (lv.get("latest_date"), f"{v / 1000:.0f}K") if v is not None else (None, None)
    # mom_yoy: 제목에 y/y가 있으면 YoY, 아니면 MoM
    mv = mom_yoy(series_id, api_key)
    if not mv:
        return None, None
    use_yoy = "y/y" in title_l or "yoy" in title_l
    val = mv.get("yoy_pct") if use_yoy else mv.get("mom_pct")
    return (mv.get("latest_date"), f"{val:+.1f}%") if val is not None else (None, None)


def enrich_actual(events, api_key: str, event_state=None):
    """캘린더 이벤트 리스트(dict, in-place로 수정)에서 actual이 비어있는데
    FRED로 확인 가능한 지표면 공식 실측치로 채운다. 값을 지어내지 않고, 매칭되는
    시리즈가 없거나 FRED 호출이 실패하면 조용히 건너뛴다(actual은 빈 채로 유지).

    event_state: main.py의 state["events"](event_id -> 기록 dict)를 넘겨주면,
    "이 이벤트를 처음 확인했을 때 FRED에 있던 값(baseline)"을 기록해두고, 그 이후
    baseline과 다른(=새로 반영된) 관측치가 나타날 때만 actual을 채운다.

    이렇게 하는 이유: FRED는 발표 전에도 '직전 회차'의 값을 계속 갖고 있어서,
    바로 최신값을 그대로 가져다 쓰면 (a) 아직 발표 전인(심지어 내일 발표할) 지표에
    직전 발표치를 실측치로 잘못 채워 미리 "발표" 메시지를 보내버리고, 그 바람에
    (b) result_sent가 이미 True로 찍혀서 정작 진짜 발표가 나온 뒤에는 아무 메시지도
    안 나가는 문제가 있었다(실제 보고된 버그). event_state가 없으면(하위 호환) 예전처럼
    즉시 최신값을 사용한다."""
    if not api_key:
        return events
    for e in events:
        if e.get("actual"):
            continue
        title_l = e.get("ff_title", "").lower()
        series_id, kind = _match_actual_series(title_l)
        if not series_id:
            continue
        try:
            obs_date, formatted = _fetch_latest_for_kind(series_id, kind, api_key, title_l)
        except Exception:
            continue  # 이 지표 하나 실패해도 나머지는 계속 처리
        if formatted is None:
            continue

        if event_state is None or obs_date is None:
            # event_state가 없으면(하위 호환) 예전처럼 즉시 최신값을 사용한다.
            # obs_date를 못 구했으면(관측일자 없는 응답 등) baseline 비교가 불가능하니
            # 안전하게 예전 방식대로 채운다(못 채우고 영원히 비는 것보다는 낫다).
            e["actual"] = formatted
            continue

        rec = event_state.setdefault(e.get("event_id"), {})
        baseline = rec.get("fred_baseline_obs_date")
        if baseline is None:
            # 이 이벤트를 처음 확인하는 것이면, 지금 FRED 값이 "새로 나온" 것인지 판단할
            # 기준이 없다(직전 회차 값일 수도 있음). baseline으로만 기록해두고 이번 실행에서는
            # 아직 actual을 채우지 않는다 -> 다음 폴링부터 새 값이 나오는지 비교 가능.
            rec["fred_baseline_obs_date"] = obs_date
            continue
        if obs_date == baseline:
            continue  # baseline과 동일 -> 아직 새 관측치 없음(발표 전이거나 FRED 반영 지연)
        e["actual"] = formatted  # baseline과 다른 새 관측치 등장 -> 진짜 실측치로 채택
    return events
