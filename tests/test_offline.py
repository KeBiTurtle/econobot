# -*- coding: utf-8 -*-
"""
네트워크 없이 돌아가는 오프라인 스모크 테스트.
실행: python -m tests.test_offline  (프로젝트 루트에서)
"""
import datetime
import json
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import interpretation as interp
from bot import calendar_source as cal
from bot import fred_client


def test_parse_value():
    assert interp.parse_value("3.1%") == 3.1
    assert interp.parse_value("-0.2%") == -0.2
    assert interp.parse_value("150K") == 150000.0
    assert interp.parse_value("1.44M") == 1440000.0
    assert interp.parse_value("") is None
    assert interp.parse_value(None) is None
    assert interp.parse_value("N/A") is None
    print("test_parse_value OK")


def test_compare_label():
    assert interp.compare_label(3.5, 3.1) == "예상치 상회"
    assert interp.compare_label(2.9, 3.1) == "예상치 하회"
    assert interp.compare_label(3.1, 3.1) == "컨센서스 부합"
    assert interp.compare_label(None, 3.1) == "비교불가"
    print("test_compare_label OK")


FAKE_FF_PAYLOAD = [
    {
        "title": "CPI y/y",
        "country": "USD",
        "date": "2026-08-13T08:30:00-04:00",
        "impact": "High",
        "forecast": "3.1%",
        "previous": "3.0%",
        "actual": "",
    },
    {
        "title": "Core CPI m/m",
        "country": "USD",
        "date": "2026-08-13T08:30:00-04:00",
        "impact": "High",
        "forecast": "0.2%",
        "previous": "0.3%",
        "actual": "0.3%",
    },
    {
        "title": "German Ifo Business Climate",
        "country": "EUR",
        "date": "2026-08-13T04:00:00-04:00",
        "impact": "High",
        "forecast": "88.0",
        "previous": "87.5",
        "actual": "",
    },
    {
        "title": "Crude Oil Inventories",
        "country": "USD",
        "date": "2026-08-13T10:30:00-04:00",
        "impact": "Medium",
        "forecast": "-1.2M",
        "previous": "-0.8M",
        "actual": "",
    },
]


def test_calendar_source_filtering():
    with mock.patch.object(cal, "fetch_raw_events", return_value=FAKE_FF_PAYLOAD):
        events = cal.get_week_events(today_kst=datetime.date(2026, 8, 13))
    # USD + High + 레지스트리 매칭되는 것만: CPI y/y, Core CPI m/m 두 개만 남아야 함
    titles = sorted(e["ff_title"] for e in events)
    assert titles == ["CPI y/y", "Core CPI m/m"], titles
    for e in events:
        assert e["indicator_key"] == "cpi"
        assert e["date_kst"] == "2026-08-13"
    print("test_calendar_source_filtering OK ->", titles)


def test_message_formatting():
    with mock.patch.object(cal, "fetch_raw_events", return_value=FAKE_FF_PAYLOAD):
        events = cal.get_week_events(today_kst=datetime.date(2026, 8, 13))
    pre = interp.format_pre_announcement(events)
    assert "오늘의 별3개" in pre
    assert "CPI" in pre

    released = [e for e in events if e["ff_title"] == "Core CPI m/m"][0]
    result_msg = interp.format_result_message(released)
    assert "발표" in result_msg
    assert "예상치 상회" in result_msg  # actual 0.3 > forecast 0.2
    print("test_message_formatting OK")
    print("---- 샘플 사전공지 메시지 ----")
    print(pre)
    print("---- 샘플 결과 메시지 ----")
    print(result_msg)


def test_fred_mom_yoy_math():
    # 13개월치 가짜 관측치 (최신 -> 과거 순, get_observations와 동일한 정렬)
    base = datetime.date(2026, 8, 1)
    fake_obs = []
    for i in range(13):
        year = base.year - ((base.month - i - 1) < 0)
        month = ((base.month - i - 1) % 12) + 1
        fake_obs.append((f"{year}-{month:02d}-01", 100 + i * 0.1))
    with mock.patch.object(fred_client, "get_observations", return_value=fake_obs):
        result = fred_client.mom_yoy("FAKESERIES", "dummy_key")
    assert "mom_pct" in result and "yoy_pct" in result
    print("test_fred_mom_yoy_math OK ->", result)


def test_main_run_end_to_end():
    from bot import main as botmain

    tmp_dir = tempfile.mkdtemp()
    state_path = os.path.join(tmp_dir, "state.json")

    env = {
        "TELEGRAM_BOT_TOKEN": "fake-token",
        "TELEGRAM_CHAT_ID": "12345",
        "FRED_API_KEY": "",
        "STATE_PATH": state_path,
        "DAILY_DIGEST_TIME_KST": "07:00",
        "DAILY_DIGEST_WINDOW_MINUTES": "600",  # 테스트가 언제 돌든 창 안에 들어오게 넉넉히
    }

    sent_messages = []

    def fake_send(token, chat_id, text):
        sent_messages.append(text)

    fixed_now = datetime.datetime(2026, 8, 13, 7, 0, tzinfo=botmain.KST)

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    with mock.patch.dict(os.environ, env, clear=False), \
         mock.patch.object(cal, "fetch_raw_events", return_value=FAKE_FF_PAYLOAD), \
         mock.patch.object(botmain, "send_message", side_effect=fake_send), \
         mock.patch.object(botmain.datetime, "datetime", FixedDateTime):
        botmain.run()

    assert sent_messages, "메시지가 하나도 발송되지 않았습니다"
    joined = "\n".join(sent_messages)
    assert "오늘의 별3개" in joined
    assert "[발표]" in joined  # Core CPI m/m은 actual이 있어 결과 메시지도 함께 나가야 함

    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    assert state["last_daily_digest_date"] == "2026-08-13"
    # Core CPI m/m 이벤트는 result_sent=True 여야 함
    assert any(rec.get("result_sent") for rec in state["events"].values())

    print("test_main_run_end_to_end OK -> 발송된 메시지 수:", len(sent_messages))
    for m in sent_messages:
        print("=====")
        print(m)


if __name__ == "__main__":
    test_parse_value()
    test_compare_label()
    test_calendar_source_filtering()
    test_message_formatting()
    test_fred_mom_yoy_math()
    test_main_run_end_to_end()
    print("\nALL TESTS PASSED")
