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


def test_enrich_actual_from_fred():
    """ForexFactory의 actual이 비어있어도 FRED_API_KEY가 있으면 채워지는지 확인.
    (실제 버그: PPI가 헤드라인/근원 구분 없이, 그리고 예전엔 잘못된 시리즈(PPIACO)로 매핑돼
    발표 후에도 actual이 계속 비어서 결과 메시지가 영원히 안 나갔던 문제)"""
    events = [
        {"ff_title": "PPI m/m", "actual": "", "forecast": "0.1%", "previous": "0.0%"},
        {"ff_title": "Core PPI m/m", "actual": "", "forecast": "0.2%", "previous": "0.1%"},
        {"ff_title": "CPI y/y", "actual": "", "forecast": "3.1%", "previous": "3.0%"},
        {"ff_title": "ISM Manufacturing PMI", "actual": "", "forecast": "49.0", "previous": "48.5"},
    ]

    def fake_mom_yoy(series_id, api_key):
        if series_id == "PPIFIS":
            return {"mom_pct": 0.4, "yoy_pct": 2.1}
        if series_id == "PPIFES":
            return {"mom_pct": 0.3, "yoy_pct": 2.8}
        if series_id == "CPIAUCSL":
            return {"mom_pct": 0.2, "yoy_pct": 3.6}
        return {}

    with mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy):
        fred_client.enrich_actual(events, "dummy_key")

    by_title = {e["ff_title"]: e for e in events}
    assert by_title["PPI m/m"]["actual"] == "+0.4%", by_title["PPI m/m"]["actual"]
    assert by_title["Core PPI m/m"]["actual"] == "+0.3%", by_title["Core PPI m/m"]["actual"]
    assert by_title["PPI m/m"]["actual"] != by_title["Core PPI m/m"]["actual"]  # 헤드라인/근원 구분됨
    assert by_title["CPI y/y"]["actual"] == "+3.6%"  # y/y 제목이라 yoy_pct 사용
    assert by_title["ISM Manufacturing PMI"]["actual"] == ""  # FRED에 없는 지표 -> 미채움(추측 안 함)
    print("test_enrich_actual_from_fred OK ->", {k: v["actual"] for k, v in by_title.items()})

    # 키가 없으면 아예 호출 안 하고 그대로 둠
    events2 = [{"ff_title": "PPI m/m", "actual": "", "forecast": "0.1%", "previous": "0.0%"}]
    fred_client.enrich_actual(events2, "")
    assert events2[0]["actual"] == ""
    print("test_enrich_actual_from_fred (no key) OK -> 변경 없음")


def test_calendar_source_includes_medium_impact_claims():
    """신규 실업수당 청구건수(Unemployment Claims)는 ForexFactory가 Medium으로 표기해도
    레지스트리의 min_impact 예외로 포함돼야 함. 매칭 안 되는 다른 Medium 지표(Continuing Claims)는
    여전히 제외돼야 함."""
    payload = [
        {
            "title": "Unemployment Claims",
            "country": "USD",
            "date": "2026-08-13T08:30:00-04:00",
            "impact": "Medium",
            "forecast": "202K",
            "previous": "199K",
            "actual": "",
        },
        {
            "title": "Continuing Claims",  # 레지스트리에 없는 지표 -> 계속 제외
            "country": "USD",
            "date": "2026-08-13T08:30:00-04:00",
            "impact": "Medium",
            "forecast": "1,950K",
            "previous": "1,940K",
            "actual": "",
        },
    ]
    with mock.patch.object(cal, "fetch_raw_events", return_value=payload):
        events = cal.get_week_events(today_kst=datetime.date(2026, 8, 13))
    titles = [e["ff_title"] for e in events]
    assert titles == ["Unemployment Claims"], titles
    assert events[0]["indicator_key"] == "initial_claims"
    print("test_calendar_source_includes_medium_impact_claims OK ->", titles)


def test_enrich_actual_unemployment_claims():
    events = [{"ff_title": "Unemployment Claims", "actual": "", "forecast": "202K", "previous": "199K"}]

    def fake_latest_value(series_id, api_key):
        if series_id == "ICSA":
            return {"latest_value": 199000.0, "prev_value": 198000.0}
        return {}

    with mock.patch.object(fred_client, "latest_value", side_effect=fake_latest_value):
        fred_client.enrich_actual(events, "dummy_key")
    assert events[0]["actual"] == "199K", events[0]["actual"]
    print("test_enrich_actual_unemployment_claims OK ->", events[0]["actual"])


def test_enrich_actual_baseline_prevents_stale_reuse():
    """실제로 보고된 버그 재현: 아직 발표 전(혹은 발표 시각이 지나지 않은) 지표에 대해
    FRED가 여전히 '직전 회차' 값만 갖고 있을 때, 그 값을 실측치로 잘못 채워버리면 안 된다.
    (1) 처음 확인할 때는 baseline만 기록하고 actual은 비워둬야 하고,
    (2) FRED 값이 그대로면(=아직 새 발표 없음) 몇 번을 다시 확인해도 계속 비워둬야 하며,
    (3) 실제로 새 관측치(다른 latest_date)가 나타나야만 그때 actual을 채워야 한다."""
    event_state = {}

    def make_event():
        return {"ff_title": "PPI m/m", "actual": "", "forecast": "0.1%", "previous": "0.0%", "event_id": "ppi_evt"}

    def fake_mom_yoy_old(series_id, api_key):
        # 아직 이번 회차가 발표되지 않아, FRED에는 여전히 직전(7월) 값만 있음
        return {"latest_date": "2026-07-14", "mom_pct": 0.2, "yoy_pct": 1.8}

    # 1차 확인(발표 전): baseline만 기록, actual은 비어 있어야 함
    e1 = make_event()
    with mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy_old):
        fred_client.enrich_actual([e1], "dummy_key", event_state=event_state)
    assert e1["actual"] == "", f"발표 전인데 실측치가 채워짐(직전 회차 값을 잘못 당겨씀) -> {e1['actual']}"
    assert event_state["ppi_evt"]["fred_baseline_obs_date"] == "2026-07-14"

    # 2차 확인: 아직도 발표 전, FRED 값 그대로(같은 latest_date) -> 몇 번을 다시 확인해도 비어 있어야 함
    e2 = make_event()
    with mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy_old):
        fred_client.enrich_actual([e2], "dummy_key", event_state=event_state)
    assert e2["actual"] == "", f"동일한 관측치인데 실측치가 채워짐 -> {e2['actual']}"

    # 3차 확인: 실제 발표가 나서 FRED에 새 관측치(다른 latest_date)가 등장 -> 그제서야 actual 채워야 함
    def fake_mom_yoy_new(series_id, api_key):
        return {"latest_date": "2026-08-14", "mom_pct": 0.4, "yoy_pct": 2.1}

    e3 = make_event()
    with mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy_new):
        fred_client.enrich_actual([e3], "dummy_key", event_state=event_state)
    assert e3["actual"] == "+0.4%", f"새 관측치가 나왔는데 실측치가 안 채워짐 -> {e3['actual']}"

    print("test_enrich_actual_baseline_prevents_stale_reuse OK")


def test_interpret_gdp_uses_raw_rate_not_mom_yoy():
    """GDP 시리즈(A191RL1Q225SBEA)는 FRED에 이미 '연율 성장률(%)'로 제공되는 값이라,
    CPI/PCE처럼 mom_yoy()로 이중 퍼센트 계산을 하면 안 된다(예전 버그).
    latest_value 기반으로 실제 성장률 값을 그대로 보여주고, 직전 분기 대비 가속/둔화만 비교해야 함."""
    event = {"indicator_key": "gdp"}
    fake_obs = [("2026-04-01", 2.6), ("2026-01-01", 2.3), ("2025-10-01", 2.0)]

    def fake_get_observations(series_id, api_key, limit=14):
        assert series_id == "A191RL1Q225SBEA"
        return fake_obs

    with mock.patch.object(fred_client, "get_observations", side_effect=fake_get_observations):
        msg = interp.interpret_gdp(event, "dummy_key")

    assert "+2.6%" in msg, msg
    assert "가속" in msg  # 2.3% -> 2.6%로 가속
    assert "13.0" not in msg and "13.04" not in msg  # 이중 퍼센트 버그였다면 나왔을 엉뚱한 숫자
    print("test_interpret_gdp_uses_raw_rate_not_mom_yoy OK ->", msg.splitlines()[1])


def test_interpret_ppi_jolts_claims_narrative():
    """PPI/JOLTS/신규실업수당청구 해석이 예전처럼 숫자만 나열하는 게 아니라
    맥락(선행지표, 노동시장 해석 등)을 담은 해설 형태인지 확인."""
    event = {}

    def fake_mom_yoy(series_id, api_key):
        if series_id == "PPIFIS":
            return {"mom_pct": 0.4, "yoy_pct": 2.1, "mom_trend_6m": [0.1, 0.1, 0.2, 0.2, 0.3, 0.3]}
        if series_id == "PPIFES":
            return {"mom_pct": 0.3, "yoy_pct": 2.8, "mom_trend_6m": [0.1, 0.1, 0.2, 0.2, 0.3, 0.3]}
        if series_id == "JTSJOL":
            return {"latest_value": 7450.0, "mom_pct": -1.2, "yoy_pct": -3.5,
                    "mom_trend_6m": [0.5, 0.2, 0.0, -0.3, -0.5, -0.8]}
        return {}

    def fake_get_observations(series_id, api_key, limit=14):
        if series_id == "ICSA":
            return [("2026-08-08", 235000.0), ("2026-08-01", 220000.0),
                    ("2026-07-25", 218000.0), ("2026-07-18", 215000.0)]
        return []

    with mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy), \
         mock.patch.object(fred_client, "get_observations", side_effect=fake_get_observations):
        ppi_msg = interp.interpret_ppi(event, "dummy_key")
        jolts_msg = interp.interpret_jolts(event, "dummy_key")
        claims_msg = interp.interpret_initial_claims(event, "dummy_key")

    assert "선행 신호" in ppi_msg  # PPI가 CPI/PCE에 선행한다는 해설
    assert "근원(Core" in ppi_msg
    assert "채용" in jolts_msg and "백만 건" in jolts_msg
    assert "4주 평균" in claims_msg and "235,000건" in claims_msg
    print("test_interpret_ppi_jolts_claims_narrative OK")


def test_interpret_fed_lens_hawkish_dovish_directions():
    """모든 fed_critical 지표 해석에 '연준(Fed) 관점' 문단이 붙고, 방향(매파적/비둘기적 여지)이
    실제 데이터 방향에 맞게 갈리는지 확인. (금리와의 연관성을 명시적으로 설명해달라는 요청 반영)"""

    # --- NFP: 강한 고용(매파적 여지) vs 약한 고용(비둘기적 여지) ---
    def fake_latest_level_change_strong(series_id, api_key):
        return {"change": 250.0}

    def fake_latest_value_strong(series_id, api_key):
        if series_id == "UNRATE":
            return {"latest_value": 4.0, "prev_value": 4.1}  # 하락 = 견조
        if series_id == "CIVPART":
            return {"latest_value": 62.5}
        return {}

    with mock.patch.object(fred_client, "latest_level_change", side_effect=fake_latest_level_change_strong), \
         mock.patch.object(fred_client, "latest_value", side_effect=fake_latest_value_strong), \
         mock.patch.object(fred_client, "mom_yoy", return_value={}):
        nfp_strong = interp.interpret_nfp({}, "dummy_key")
    assert "🏦" in nfp_strong and "매파적 여지" in nfp_strong, nfp_strong

    def fake_latest_level_change_weak(series_id, api_key):
        return {"change": 50.0}

    def fake_latest_value_weak(series_id, api_key):
        if series_id == "UNRATE":
            return {"latest_value": 4.3, "prev_value": 4.1}  # 상승 = 냉각
        return {}

    with mock.patch.object(fred_client, "latest_level_change", side_effect=fake_latest_level_change_weak), \
         mock.patch.object(fred_client, "latest_value", side_effect=fake_latest_value_weak), \
         mock.patch.object(fred_client, "mom_yoy", return_value={}):
        nfp_weak = interp.interpret_nfp({}, "dummy_key")
    assert "🏦" in nfp_weak and "비둘기적 여지" in nfp_weak, nfp_weak

    # --- FOMC: 인상/인하/동결에 따라 다른 연준 관점 문구 ---
    def fake_latest_value_hike(series_id, api_key):
        if series_id == "DFEDTARU":
            return {"latest_value": 5.5, "prev_value": 5.25}
        if series_id == "DFEDTARL":
            return {"latest_value": 5.25, "prev_value": 5.0}
        return {}

    with mock.patch.object(fred_client, "latest_value", side_effect=fake_latest_value_hike):
        fomc_hike = interp.interpret_fomc({}, "dummy_key")
    assert "인상" in fomc_hike and "물가 안정을" in fomc_hike, fomc_hike

    def fake_latest_value_cut(series_id, api_key):
        if series_id == "DFEDTARU":
            return {"latest_value": 5.0, "prev_value": 5.25}
        if series_id == "DFEDTARL":
            return {"latest_value": 4.75, "prev_value": 5.0}
        return {}

    with mock.patch.object(fred_client, "latest_value", side_effect=fake_latest_value_cut):
        fomc_cut = interp.interpret_fomc({}, "dummy_key")
    assert "인하" in fomc_cut and "고용·성장 둔화" in fomc_cut, fomc_cut

    # --- GDP: 마이너스 성장(비둘기적) vs 강한 성장(매파적) ---
    def fake_obs_negative(series_id, api_key, limit=14):
        return [("2026-04-01", -0.5), ("2026-01-01", 1.0)]

    with mock.patch.object(fred_client, "get_observations", side_effect=fake_obs_negative):
        gdp_neg = interp.interpret_gdp({"indicator_key": "gdp"}, "dummy_key")
    assert "🏦" in gdp_neg and "비둘기적 여지" in gdp_neg, gdp_neg

    def fake_obs_hot(series_id, api_key, limit=14):
        return [("2026-04-01", 3.5), ("2026-01-01", 2.0)]

    with mock.patch.object(fred_client, "get_observations", side_effect=fake_obs_hot):
        gdp_hot = interp.interpret_gdp({"indicator_key": "gdp"}, "dummy_key")
    assert "🏦" in gdp_hot and "매파적 여지" in gdp_hot, gdp_hot

    # --- PPI: 근원 PPI 상승 추세(매파적) vs 하락 추세(비둘기적) ---
    def fake_mom_yoy_ppi_rising(series_id, api_key):
        if series_id == "PPIFES":
            return {"mom_pct": 0.4, "yoy_pct": 3.0, "mom_trend_6m": [0.1, 0.1, 0.1, 0.2, 0.3, 0.4]}
        return {"mom_pct": 0.3, "yoy_pct": 2.0, "mom_trend_6m": []}

    with mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy_ppi_rising):
        ppi_rising = interp.interpret_ppi({}, "dummy_key")
    assert "🏦" in ppi_rising and "매파적 여지" in ppi_rising, ppi_rising

    def fake_mom_yoy_ppi_falling(series_id, api_key):
        if series_id == "PPIFES":
            return {"mom_pct": 0.1, "yoy_pct": 1.5, "mom_trend_6m": [0.4, 0.3, 0.3, 0.2, 0.1, 0.05]}
        return {"mom_pct": 0.1, "yoy_pct": 1.5, "mom_trend_6m": []}

    with mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy_ppi_falling):
        ppi_falling = interp.interpret_ppi({}, "dummy_key")
    assert "🏦" in ppi_falling and "비둘기적 여지" in ppi_falling, ppi_falling

    # --- JOLTS: 채용 수요 확대(매파적 여지) vs 둔화(비둘기적 여지) ---
    def fake_mom_yoy_jolts_rising(series_id, api_key):
        return {
            "latest_value": 8200.0,
            "mom_pct": 1.0,
            "yoy_pct": 2.0,
            "mom_trend_6m": [7800.0, 7900.0, 7950.0, 8000.0, 8100.0, 8200.0],
        }

    with mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy_jolts_rising):
        jolts_rising = interp.interpret_jolts({}, "dummy_key")
    assert "🏦" in jolts_rising and "매파적 여지" in jolts_rising, jolts_rising

    def fake_mom_yoy_jolts_falling(series_id, api_key):
        return {
            "latest_value": 7600.0,
            "mom_pct": -0.5,
            "yoy_pct": -3.0,
            "mom_trend_6m": [8200.0, 8000.0, 7900.0, 7800.0, 7700.0, 7600.0],
        }

    with mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy_jolts_falling):
        jolts_falling = interp.interpret_jolts({}, "dummy_key")
    assert "🏦" in jolts_falling and "비둘기적 여지" in jolts_falling, jolts_falling

    # --- 신규 실업수당 청구건수: 냉각(비둘기적) vs 견조(매파적) ---
    def fake_obs_claims_cooling(series_id, api_key, limit=5):
        # 최신치가 4주 평균 대비 3% 이상 높음 -> cooling
        return [("2026-08-08", 250000.0), ("2026-08-01", 220000.0), ("2026-07-25", 215000.0), ("2026-07-18", 210000.0)]

    with mock.patch.object(fred_client, "get_observations", side_effect=fake_obs_claims_cooling):
        claims_cooling = interp.interpret_initial_claims({}, "dummy_key")
    assert "🏦" in claims_cooling and "비둘기적 재료" in claims_cooling, claims_cooling

    def fake_obs_claims_tight(series_id, api_key, limit=5):
        # 최신치가 4주 평균 대비 3% 이상 낮음 -> tight
        return [("2026-08-08", 190000.0), ("2026-08-01", 220000.0), ("2026-07-25", 225000.0), ("2026-07-18", 215000.0)]

    with mock.patch.object(fred_client, "get_observations", side_effect=fake_obs_claims_tight):
        claims_tight = interp.interpret_initial_claims({}, "dummy_key")
    assert "🏦" in claims_tight and "매파적 재료" in claims_tight, claims_tight

    print("test_interpret_fed_lens_hawkish_dovish_directions OK")


def test_build_interpretation_message_routes_to_new_functions():
    for key, expected_snippet in [
        ("ppi", "PPI(생산자물가)"),
        ("gdp", "GDP 성장률"),
        ("jolts", "JOLTS"),
        ("initial_claims", "신규 실업수당"),
    ]:
        event = {"indicator_key": key}
        with mock.patch.object(fred_client, "mom_yoy", return_value={}), \
             mock.patch.object(fred_client, "get_observations", return_value=[]), \
             mock.patch.object(fred_client, "latest_value", return_value={}):
            msg = interp.build_interpretation_message(event, "dummy_key")
        assert msg is not None and expected_snippet in msg, (key, msg)
    print("test_build_interpretation_message_routes_to_new_functions OK")


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


def test_format_t15_alert():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    event = {
        "datetime_kst": datetime.datetime(2026, 8, 13, 21, 30, tzinfo=kst),
        "name_kr": "소비자물가지수(CPI)",
        "ff_title": "CPI y/y",
        "forecast": "3.1%",
        "previous": "3.0%",
    }
    msg = interp.format_t15_alert(event)
    assert "21:30" in msg
    assert "CPI y/y" in msg
    assert "3.1%" in msg
    assert "⏰" in msg
    print("test_format_t15_alert OK ->", msg.splitlines()[0])


def test_main_run_t15_alert():
    """발표 15분 이내로 남으면 T-15 알림이 딱 한 번만 나가는지 확인.
    (같은 상태 파일로 다시 실행해도 중복 발송되면 안 됨)"""
    from bot import main as botmain

    event_time_kst = datetime.datetime(2026, 8, 13, 21, 30, tzinfo=botmain.KST)
    payload = [
        {
            "title": "CPI y/y",
            "country": "USD",
            "date": "2026-08-13T08:30:00-04:00",  # == 21:30 KST
            "impact": "High",
            "forecast": "3.1%",
            "previous": "3.0%",
            "actual": "",
        },
    ]

    tmp_dir = tempfile.mkdtemp()
    state_path = os.path.join(tmp_dir, "state.json")
    env = {
        "TELEGRAM_BOT_TOKEN": "fake-token",
        "TELEGRAM_CHAT_ID": "12345",
        "FRED_API_KEY": "",
        "STATE_PATH": state_path,
        "DAILY_DIGEST_TIME_KST": "07:00",
        "DAILY_DIGEST_WINDOW_MINUTES": "10",
    }
    sent_messages = []

    def fake_send(token, chat_id, text):
        sent_messages.append(text)

    def run_at(fixed_now):
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(cal, "fetch_raw_events", return_value=payload), \
             mock.patch.object(botmain, "send_message", side_effect=fake_send), \
             mock.patch.object(botmain.datetime, "datetime", FixedDateTime):
            botmain.run()

    # 1차: 발표 10분 전 -> T-15 알림이 나가야 함
    run_at(event_time_kst - datetime.timedelta(minutes=10))
    assert any("⏰" in m for m in sent_messages), f"T-15 알림이 안 나감 -> {sent_messages}"
    assert any("곧 발표" in m for m in sent_messages), sent_messages

    # 2차: 같은 상태 파일로 5분 전에 다시 실행 -> 이미 보냈으니 중복 발송 안 돼야 함
    sent_messages.clear()
    run_at(event_time_kst - datetime.timedelta(minutes=5))
    assert not any("⏰" in m for m in sent_messages), f"T-15 알림이 중복 발송됨 -> {sent_messages}"

    print("test_main_run_t15_alert OK -> 1차 발송, 2차 중복 방지 확인")


def test_main_run_t15_alert_not_triggered_too_early():
    """발표까지 20분 넘게 남았으면 아직 T-15 알림을 보내면 안 됨."""
    from bot import main as botmain

    event_time_kst = datetime.datetime(2026, 8, 13, 21, 30, tzinfo=botmain.KST)
    payload = [
        {
            "title": "CPI y/y",
            "country": "USD",
            "date": "2026-08-13T08:30:00-04:00",
            "impact": "High",
            "forecast": "3.1%",
            "previous": "3.0%",
            "actual": "",
        },
    ]
    tmp_dir = tempfile.mkdtemp()
    state_path = os.path.join(tmp_dir, "state.json")
    env = {
        "TELEGRAM_BOT_TOKEN": "fake-token",
        "TELEGRAM_CHAT_ID": "12345",
        "FRED_API_KEY": "",
        "STATE_PATH": state_path,
        "DAILY_DIGEST_TIME_KST": "07:00",
        "DAILY_DIGEST_WINDOW_MINUTES": "10",
    }
    sent_messages = []

    def fake_send(token, chat_id, text):
        sent_messages.append(text)

    fixed_now = event_time_kst - datetime.timedelta(minutes=20)

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    with mock.patch.dict(os.environ, env, clear=False), \
         mock.patch.object(cal, "fetch_raw_events", return_value=payload), \
         mock.patch.object(botmain, "send_message", side_effect=fake_send), \
         mock.patch.object(botmain.datetime, "datetime", FixedDateTime):
        botmain.run()

    assert not any("⏰" in m for m in sent_messages), f"20분 전인데 T-15 알림이 나감 -> {sent_messages}"
    print("test_main_run_t15_alert_not_triggered_too_early OK")


def test_main_run_ppi_stuck_actual_bug_fixed():
    """실제로 보고된 버그 재현: ForexFactory가 PPI actual을 계속 비워두면(실측상 흔함)
    FRED_API_KEY가 있어도 보강 로직이 없으면 결과 메시지가 영원히 안 나간다.
    이제 main.run()이 FRED로 actual을 보강하므로 결과 메시지가 나가야 한다."""
    from bot import main as botmain

    ppi_payload = [
        {
            "title": "PPI m/m",
            "country": "USD",
            "date": "2026-08-13T08:30:00-04:00",
            "impact": "High",
            "forecast": "0.1%",
            "previous": "0.0%",
            "actual": "",  # ForexFactory가 발표 후에도 계속 비워두는 상황 재현
        },
    ]

    tmp_dir = tempfile.mkdtemp()
    state_path = os.path.join(tmp_dir, "state.json")
    env = {
        "TELEGRAM_BOT_TOKEN": "fake-token",
        "TELEGRAM_CHAT_ID": "12345",
        "FRED_API_KEY": "dummy_key",
        "STATE_PATH": state_path,
        "DAILY_DIGEST_TIME_KST": "07:00",
        "DAILY_DIGEST_WINDOW_MINUTES": "600",
    }

    sent_messages = []

    def fake_send(token, chat_id, text):
        sent_messages.append(text)

    def fake_mom_yoy(series_id, api_key):
        if series_id == "PPIFIS":
            return {"mom_pct": 0.4, "yoy_pct": 2.1, "mom_trend_6m": []}
        return {}

    fixed_now = datetime.datetime(2026, 8, 13, 9, 0, tzinfo=botmain.KST)  # 발표(08:30 ET) 이후 시점

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    with mock.patch.dict(os.environ, env, clear=False), \
         mock.patch.object(cal, "fetch_raw_events", return_value=ppi_payload), \
         mock.patch.object(botmain, "send_message", side_effect=fake_send), \
         mock.patch.object(botmain.datetime, "datetime", FixedDateTime), \
         mock.patch.object(fred_client, "mom_yoy", side_effect=fake_mom_yoy):
        botmain.run()

    joined = "\n".join(sent_messages)
    assert "[발표]" in joined, f"결과 메시지가 안 나감(버그 재현됨) -> {sent_messages}"
    assert "PPI" in joined
    print("test_main_run_ppi_stuck_actual_bug_fixed OK -> 결과 메시지 정상 발송")


def test_main_run_ppi_does_not_fire_early_and_fires_after_real_release():
    """실제로 보고된 버그 재현: (1) 아직 발표되지 않은 지표를 FRED의 직전 회차 값으로
    미리 '발표'해버리는 문제, (2) 그 여파로 진짜 발표가 나온 뒤에도 result_sent가 이미
    True라서 결과 메시지가 영원히 안 나가는 문제. 두 번의 폴링(발표 전 -> 발표 후)에 걸쳐
    baseline -> 새 관측치 흐름을 재현해 둘 다 고쳐졌는지 확인한다."""
    from bot import main as botmain

    ppi_payload = [
        {
            "title": "PPI m/m",
            "country": "USD",
            "date": "2026-08-13T08:30:00-04:00",  # == 21:30 KST
            "impact": "High",
            "forecast": "0.1%",
            "previous": "0.0%",
            "actual": "",
        },
    ]

    tmp_dir = tempfile.mkdtemp()
    state_path = os.path.join(tmp_dir, "state.json")
    env = {
        "TELEGRAM_BOT_TOKEN": "fake-token",
        "TELEGRAM_CHAT_ID": "12345",
        "FRED_API_KEY": "dummy_key",
        "STATE_PATH": state_path,
        "DAILY_DIGEST_TIME_KST": "07:00",
        "DAILY_DIGEST_WINDOW_MINUTES": "10",
    }

    sent_messages = []

    def fake_send(token, chat_id, text):
        sent_messages.append(text)

    def fake_mom_yoy_old(series_id, api_key):
        # 발표 전: FRED에는 아직 직전(7월) 값만 있음
        return {"latest_date": "2026-07-14", "mom_pct": 0.2, "yoy_pct": 1.8, "mom_trend_6m": []}

    def fake_mom_yoy_new(series_id, api_key):
        # 발표 후: FRED에 새 관측치가 등장
        return {"latest_date": "2026-08-14", "mom_pct": 0.4, "yoy_pct": 2.1, "mom_trend_6m": []}

    def run_at(fixed_now, mom_yoy_fn):
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(cal, "fetch_raw_events", return_value=ppi_payload), \
             mock.patch.object(botmain, "send_message", side_effect=fake_send), \
             mock.patch.object(botmain.datetime, "datetime", FixedDateTime), \
             mock.patch.object(fred_client, "mom_yoy", side_effect=mom_yoy_fn):
            botmain.run()

    # 1차 폴링: 발표 시각(21:30 KST)보다 한참 이른 아침 -> 아직 결과 메시지가 나가면 안 됨
    run_at(datetime.datetime(2026, 8, 13, 7, 0, tzinfo=botmain.KST), fake_mom_yoy_old)
    assert not any("[발표]" in m for m in sent_messages), \
        f"발표 전인데 결과 메시지가 미리 나감(버그 재현) -> {sent_messages}"

    # 2차 폴링: 발표 시각 이후, FRED에 새 관측치가 반영됨 -> 이제는 결과 메시지가 나가야 함
    sent_messages.clear()
    run_at(datetime.datetime(2026, 8, 13, 22, 0, tzinfo=botmain.KST), fake_mom_yoy_new)
    joined = "\n".join(sent_messages)
    assert "[발표]" in joined, f"진짜 발표 후에도 결과 메시지가 안 나감(버그 재현) -> {sent_messages}"
    assert "+0.4%" in joined, joined

    print("test_main_run_ppi_does_not_fire_early_and_fires_after_real_release OK")


if __name__ == "__main__":
    test_parse_value()
    test_compare_label()
    test_calendar_source_filtering()
    test_message_formatting()
    test_fred_mom_yoy_math()
    test_enrich_actual_from_fred()
    test_calendar_source_includes_medium_impact_claims()
    test_enrich_actual_unemployment_claims()
    test_enrich_actual_baseline_prevents_stale_reuse()
    test_interpret_gdp_uses_raw_rate_not_mom_yoy()
    test_interpret_ppi_jolts_claims_narrative()
    test_interpret_fed_lens_hawkish_dovish_directions()
    test_build_interpretation_message_routes_to_new_functions()
    test_format_t15_alert()
    test_main_run_t15_alert()
    test_main_run_t15_alert_not_triggered_too_early()
    test_main_run_end_to_end()
    test_main_run_ppi_stuck_actual_bug_fixed()
    test_main_run_ppi_does_not_fire_early_and_fires_after_real_release()
    print("\nALL TESTS PASSED")
