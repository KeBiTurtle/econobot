# -*- coding: utf-8 -*-
"""
경제지표 텔레그램 봇 - 실행 진입점.

매 실행(poll)마다 하는 일:
1) 오늘자 별3개(★★★)급 미국 지표 목록을 가져온다.
2) 아직 사전공지를 안 보냈고, 설정된 KST 시각(±허용오차)이면 "오늘 발표 있음" 공지를 보낸다.
3) 발표까지 15분 이내로 남았고 아직 T-15 알림을 안 보냈다면 "곧 발표됩니다" 알림을 보낸다.
4) 각 지표에 대해 실제치(actual)가 새로 채워졌는데 아직 결과를 안 보냈다면 결과(상회/부합/하회) 메시지를 보낸다.
5) 결과를 보낸 지 일정 시간(기본 2분) 이상 지났고 아직 해석을 안 보냈다면(연준 핵심지표만) 세부 해석을 보낸다.
   -> 이렇게 하면 발표 15분 전엔 예고를, 발표 직후엔 수치를, 몇 분 뒤엔 해석을 받아볼 수 있다
      (FRED 반영 시차 고려).

이 스크립트는 GitHub Actions 등 외부 스케줄러가 반복 호출하는 것을 전제로 한다.
자세한 배포 방법은 README.md 참고.
"""
import datetime
import sys
import traceback

from .config import Config, ConfigError
from . import calendar_source
from . import fred_client
from . import interpretation
from . import state as state_mod
from .telegram_client import send_message

KST = datetime.timezone(datetime.timedelta(hours=9))
INTERPRETATION_DELAY_MINUTES = 2  # 결과 발송 후 해석 발송까지 최소 대기 시간
T15_ALERT_MINUTES = 15  # 발표 이 시간(분) 이내로 남으면 사전 알림을 보낸다


def _within_digest_window(now_kst: datetime.datetime, target_hhmm: str, window_min: int) -> bool:
    try:
        hh, mm = [int(x) for x in target_hhmm.split(":")]
    except ValueError:
        hh, mm = 7, 0
    target = now_kst.replace(hour=hh, minute=mm, second=0, microsecond=0)
    delta = abs((now_kst - target).total_seconds()) / 60.0
    return delta <= window_min


def run() -> None:
    cfg = Config()
    state = state_mod.load_state(cfg.state_path)
    now_kst = datetime.datetime.now(KST)
    today_str = now_kst.date().isoformat()

    try:
        today_events = calendar_source.get_today_events(now_kst.date())
    except Exception as exc:  # 네트워크/파싱 오류 시 이번 실행은 건너뛰고 다음 폴링을 기다림
        print(f"[WARN] 캘린더 조회 실패: {exc}", file=sys.stderr)
        traceback.print_exc()
        today_events = []

    # ForexFactory의 actual 필드는 발표 후 한참 지나도 안 채워지는 경우가 있어(실측 확인됨),
    # FRED_API_KEY가 있으면 공식 데이터로 actual을 보강한다. 안 그러면 아래 2)/3) 단계가
    # has_actual=False에 계속 막혀서 결과/해석 메시지가 영원히 안 나가는 문제가 생긴다.
    if cfg.fred_api_key and today_events:
        try:
            fred_client.enrich_actual(today_events, cfg.fred_api_key, event_state=state["events"])
        except Exception as exc:
            print(f"[WARN] FRED actual 보강 실패: {exc}", file=sys.stderr)
            traceback.print_exc()

    # --- 1) 사전 공지 ---------------------------------------------------
    if state.get("last_daily_digest_date") != today_str and _within_digest_window(
        now_kst, cfg.daily_digest_time_kst, cfg.daily_digest_window_minutes
    ):
        if today_events:
            msg = interpretation.format_pre_announcement(today_events)
            send_message(cfg.telegram_bot_token, cfg.telegram_chat_id, msg)
        state["last_daily_digest_date"] = today_str
        for e in today_events:
            rec = state["events"].setdefault(e["event_id"], {"date": e["date_kst"]})
            rec["pre_announced"] = True
            rec["date"] = e["date_kst"]

    # --- 3) T-15분 사전 알림 ----------------------------------------------
    # 폴링 주기(1~5분)마다 확인하다가, "발표까지 15분 이내로 남았다"를 처음 감지한
    # 시점에 딱 한 번만 보낸다(그 뒤로 몇 분 남았든 다시 안 보냄 -> t15_sent로 방지).
    for e in today_events:
        rec = state["events"].setdefault(e["event_id"], {"date": e["date_kst"]})
        if not rec.get("t15_sent"):
            minutes_until = (e["datetime_kst"] - now_kst).total_seconds() / 60.0
            if 0 <= minutes_until <= T15_ALERT_MINUTES:
                msg = interpretation.format_t15_alert(e)
                send_message(cfg.telegram_bot_token, cfg.telegram_chat_id, msg)
                rec["t15_sent"] = True
                rec["date"] = e["date_kst"]

    # --- 4) 발표 결과 + 5) 세부 해석 -------------------------------------
    for e in today_events:
        rec = state["events"].setdefault(
            e["event_id"],
            {"date": e["date_kst"], "pre_announced": False, "result_sent": False, "interpretation_sent": False},
        )

        # 자가치유: ForexFactory 캘린더 피드가 (실측 확인된 버그로) 예정 발표 시각이 되기도 전에
        # actual 필드를 일시적으로 채워 내보내는 경우가 있다. 그 순간에 폴링이 걸리면
        # has_actual=True로 오판해서 진짜 발표 전에 "결과" 메시지를 보내버리고 result_sent가
        # True로 고정돼, 정작 진짜 발표가 나온 뒤에는 아무 메시지도 안 나가는 문제가 있었다
        # (실제 발생 확인됨: result_sent_at이 예정 시각보다 훨씬 이른 자정 직후로 찍힘).
        # -> 발송 기록 시각이 이 이벤트의 예정 발표 시각보다 이르면 무효로 보고 재발송 대기로
        #    되돌린다.
        sent_at_str = rec.get("result_sent_at")
        if rec.get("result_sent") and sent_at_str:
            try:
                sent_at = datetime.datetime.fromisoformat(sent_at_str)
            except ValueError:
                sent_at = None
            if sent_at is not None and sent_at < e["datetime_kst"]:
                print(
                    f"[INFO] {e['event_id']}: 예정 발표 시각({e['datetime_kst'].isoformat()}) 이전에 "
                    f"잘못 발송된 결과 감지({sent_at.isoformat()}) -> 재발송 대기로 초기화"
                )
                rec["result_sent"] = False
                rec["interpretation_sent"] = False
                rec.pop("result_sent_at", None)

        # actual 값이 있어도 아직 예정 발표 시각 전이면(캘린더 소스가 위와 같은 이유로 너무 이르게
        # 채운 경우) 진짜 발표로 인정하지 않는다. 발표 시각이 지나야만 실측치로 취급한다.
        has_actual = bool(e["actual"]) and now_kst >= e["datetime_kst"]

        if has_actual and not rec.get("result_sent"):
            msg = interpretation.format_result_message(e)
            send_message(cfg.telegram_bot_token, cfg.telegram_chat_id, msg)
            rec["result_sent"] = True
            rec["result_sent_at"] = now_kst.isoformat()
            rec["interpretation_sent"] = False

        if rec.get("result_sent") and not rec.get("interpretation_sent"):
            sent_at_str = rec.get("result_sent_at")
            ready = True
            if sent_at_str:
                sent_at = datetime.datetime.fromisoformat(sent_at_str)
                ready = (now_kst - sent_at).total_seconds() >= INTERPRETATION_DELAY_MINUTES * 60
            if ready:
                interp_msg = interpretation.build_interpretation_message(e, cfg.fred_api_key)
                if interp_msg:
                    send_message(cfg.telegram_bot_token, cfg.telegram_chat_id, interp_msg)
                rec["interpretation_sent"] = True  # 해석 대상이 아니어도(None) 완료 처리

    state_mod.prune_old_events(state)
    state_mod.save_state(cfg.state_path, state)


if __name__ == "__main__":
    try:
        run()
    except ConfigError as ce:
        print(f"[CONFIG ERROR] {ce}", file=sys.stderr)
        sys.exit(1)
