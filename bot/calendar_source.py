# -*- coding: utf-8 -*-
"""
경제지표 캘린더 소스.

기본 소스: ForexFactory의 공개 주간 캘린더 JSON 피드
  https://nfs.faireconomy.media/ff_calendar_thisweek.json
  - 무료/무인증, 위젯용으로 공개된 피드라 investing.com보다 차단 위험이 낮음.
  - impact: "High" 가 investing.com의 '별 3개(빨간불)'와 대체로 대응됨.
  - forecast/previous/actual(발표 후 채워짐) 필드를 제공.

보조 소스: investing.com 스크레이핑은 Cloudflare 등 봇 차단이 잦아 기본적으로는 사용하지 않음.
  필요하면 investing_fallback.py 를 직접 구현해 calendar_source.get_today_events() 안에서
  ForexFactory 실패 시 호출하도록 확장할 수 있다 (README 참고).
"""
import datetime
import hashlib
import json
from typing import List, Dict, Any, Optional

import requests

from .indicators import match_indicator

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
KST = datetime.timezone(datetime.timedelta(hours=9))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}


def _parse_ff_datetime(date_str: str) -> Optional[datetime.datetime]:
    """ForexFactory의 ISO8601(타임존 포함) 문자열을 파싱해 KST로 변환한다."""
    if not date_str:
        return None
    try:
        dt = datetime.datetime.fromisoformat(date_str)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(KST)


def make_event_id(title: str, dt_kst: datetime.datetime) -> str:
    raw = f"{title}|{dt_kst.date().isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def fetch_raw_events() -> List[Dict[str, Any]]:
    resp = requests.get(FF_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def get_week_events(today_kst: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
    """
    이번 주 캘린더에서 USD + High impact + 레지스트리에 매칭되는(=별3개급) 이벤트만 추려서 반환.

    반환 항목 예:
    {
      "event_id": "...",
      "indicator_key": "cpi",
      "name_kr": "소비자물가지수(CPI)",
      "ff_title": "CPI y/y",
      "datetime_kst": datetime(...),
      "date_kst": "2026-08-13",
      "forecast": "3.1%",
      "previous": "3.0%",
      "actual": "" or "3.2%",
    }
    """
    if today_kst is None:
        today_kst = datetime.datetime.now(KST).date()

    raw = fetch_raw_events()
    results = []
    for item in raw:
        if item.get("country") != "USD":
            continue
        if item.get("impact") != "High":
            continue
        title = item.get("title", "")
        ind = match_indicator(title)
        if ind is None:
            continue
        dt_kst = _parse_ff_datetime(item.get("date", ""))
        if dt_kst is None:
            continue
        results.append({
            "event_id": make_event_id(title, dt_kst),
            "indicator_key": ind["key"],
            "name_kr": ind["name_kr"],
            "ff_title": title,
            "datetime_kst": dt_kst,
            "date_kst": dt_kst.date().isoformat(),
            "forecast": (item.get("forecast") or "").strip(),
            "previous": (item.get("previous") or "").strip(),
            "actual": (item.get("actual") or "").strip(),
        })
    return results


def get_today_events(today_kst: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
    if today_kst is None:
        today_kst = datetime.datetime.now(KST).date()
    return [e for e in get_week_events(today_kst) if e["date_kst"] == today_kst.isoformat()]


if __name__ == "__main__":
    # 로컬 테스트용: python -m bot.calendar_source
    events = get_week_events()
    print(json.dumps(
        [{**e, "datetime_kst": e["datetime_kst"].isoformat()} for e in events],
        ensure_ascii=False, indent=2,
    ))
