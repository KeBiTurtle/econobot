# -*- coding: utf-8 -*-
"""
간단한 JSON 파일 기반 상태 저장소.

GitHub Actions는 실행마다 새 컨테이너를 쓰기 때문에, 이 파일을 리포지토리에
커밋해서 "이미 보낸 알림"을 다음 실행에서도 기억하게 만든다.
(워크플로우 yml에서 실행 후 git commit & push 하는 스텝을 둔다)
"""
import json
import os
from typing import Any, Dict


DEFAULT_STATE = {
    "last_daily_digest_date": None,   # "YYYY-MM-DD" (KST 기준, 오늘의 사전공지를 보낸 날짜)
    "events": {},
    # events[event_id] = {
    #   "pre_announced": bool,
    #   "result_sent": bool,
    #   "interpretation_sent": bool,
    #   "date": "YYYY-MM-DD",
    # }
}


def load_state(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return json.loads(json.dumps(DEFAULT_STATE))
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return json.loads(json.dumps(DEFAULT_STATE))
    # 누락된 키 보정
    for k, v in DEFAULT_STATE.items():
        if k not in data:
            data[k] = v
    return data


def save_state(path: str, state: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def prune_old_events(state: Dict[str, Any], keep_days: int = 14) -> None:
    """state.json이 무한정 커지지 않도록 오래된 이벤트 기록을 정리한다."""
    import datetime

    cutoff = (datetime.date.today() - datetime.timedelta(days=keep_days)).isoformat()
    state["events"] = {
        eid: rec for eid, rec in state["events"].items()
        if rec.get("date", "9999-99-99") >= cutoff
    }
