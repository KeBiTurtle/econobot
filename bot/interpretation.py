# -*- coding: utf-8 -*-
"""
발표 결과 비교(상회/부합/하회) 및 연준 핵심지표 세부 해석 텍스트 생성.

주의: 여기서 생성하는 해석은 일반적인 시장 해석 프레임(예: "물가 상승 -> 매파적 압력")을
설명하는 참고용 콘텐츠이며, 특정 매매를 권유하는 투자 조언이 아니다.
"""
import re
from typing import Optional, Dict, Any

from . import fred_client
from .indicators import INDICATOR_BY_KEY

EPS = 1e-9


def parse_value(s: Optional[str]) -> Optional[float]:
    """'3.1%', '-0.2%', '150K', '1.44M' 같은 문자열을 숫자로 변환."""
    if not s:
        return None
    s = s.strip()
    if not s or s in ("-", "N/A"):
        return None
    neg = s.startswith("-")
    body = s.lstrip("+-")
    mult = 1.0
    if body.endswith("%"):
        body = body[:-1]
    elif body.upper().endswith("K"):
        mult = 1_000.0
        body = body[:-1]
    elif body.upper().endswith("M"):
        mult = 1_000_000.0
        body = body[:-1]
    elif body.upper().endswith("B"):
        mult = 1_000_000_000.0
        body = body[:-1]
    body = body.replace(",", "")
    try:
        val = float(body) * mult
    except ValueError:
        return None
    return -val if neg else val


def compare_label(actual: Optional[float], forecast: Optional[float]) -> str:
    if actual is None or forecast is None:
        return "비교불가"
    diff = actual - forecast
    if abs(diff) < max(abs(forecast) * 0.001, EPS):
        return "컨센서스 부합"
    return "예상치 상회" if diff > 0 else "예상치 하회"


def format_pre_announcement(events_today) -> str:
    if not events_today:
        return ""
    lines = ["\U0001F4C5 <b>오늘의 별3개(★★★)급 미국 경제지표 발표 예정</b>\n"]
    for e in sorted(events_today, key=lambda x: x["datetime_kst"]):
        t = e["datetime_kst"].strftime("%H:%M")
        fc = e["forecast"] or "N/A"
        prev = e["previous"] or "N/A"
        lines.append(
            f"• {t} (KST) — <b>{e['name_kr']}</b> ({e['ff_title']})\n"
            f"   예상치: {fc} / 이전치: {prev}"
        )
    lines.append("\n발표 즉시 실제 수치와 해석을 이어서 보내드립니다.")
    return "\n".join(lines)


def format_result_message(event: Dict[str, Any]) -> str:
    actual_v = parse_value(event["actual"])
    forecast_v = parse_value(event["forecast"])
    label = compare_label(actual_v, forecast_v)
    icon = {"예상치 상회": "\U0001F53A", "예상치 하회": "\U0001F53B",
            "컨센서스 부합": "➡️", "비교불가": "❓"}.get(label, "")
    lines = [
        f"\U0001F4E2 <b>[발표] {event['name_kr']}</b> ({event['ff_title']})",
        f"실제치: <b>{event['actual'] or 'N/A'}</b>  |  예상치: {event['forecast'] or 'N/A'}  |  이전치: {event['previous'] or 'N/A'}",
        f"{icon} {label}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 연준 핵심지표 세부 해석
# ---------------------------------------------------------------------------

def _trend_text(
    mom_trend,
    rising="최근 3개월간 상승 압력이 다시 확대되는 흐름입니다.",
    falling="최근 3개월간 둔화(디스인플레이션) 흐름이 이어지고 있습니다.",
    flat="최근 3개월간 큰 방향성 변화 없이 횡보하고 있습니다.",
):
    vals = [v for v in mom_trend if v is not None]
    if len(vals) < 3:
        return ""
    recent = vals[-3:]
    if recent[-1] > recent[0]:
        return rising
    elif recent[-1] < recent[0]:
        return falling
    return flat


def interpret_cpi_or_pce(event: Dict[str, Any], fred_api_key: str, label_kr: str) -> str:
    ind = INDICATOR_BY_KEY[event["indicator_key"]]
    headline_series = ind["fred"]["headline_index"]
    core_series = ind["fred"]["core_index"]

    headline = fred_client.mom_yoy(headline_series, fred_api_key) if fred_api_key else {}
    core = fred_client.mom_yoy(core_series, fred_api_key) if fred_api_key else {}

    lines = [f"\U0001F50D <b>{label_kr} 세부 해석</b>"]
    if not fred_api_key:
        lines.append("(FRED_API_KEY가 설정되지 않아 세부 해석 대신 발표치만 안내합니다.)")
        return "\n".join(lines)

    if headline:
        lines.append(
            f"• 헤드라인 {label_kr} — 전월비(MoM): {headline.get('mom_pct')}%,  전년동월비(YoY): {headline.get('yoy_pct')}%"
        )
    if core:
        lines.append(
            f"• 근원(Core, 식품·에너지 제외) — 전월비(MoM): {core.get('mom_pct')}%,  전년동월비(YoY): {core.get('yoy_pct')}%"
        )
        trend_txt = _trend_text(core.get("mom_trend_6m", []))
        if trend_txt:
            lines.append(f"  → {trend_txt}")
        yoy = core.get("yoy_pct")
        if yoy is not None:
            if yoy > 2.5:
                lines.append(
                    f"  → 근원 {label_kr} YoY {yoy}%는 연준의 2% 목표를 상회합니다. "
                    "물가 재가속 신호로 해석될 경우 금리인하 기대가 후퇴(매파적 재료)할 수 있습니다."
                )
            elif yoy <= 2.2:
                lines.append(
                    f"  → 근원 {label_kr} YoY {yoy}%는 연준 목표(2%)에 근접한 수준으로, "
                    "물가 안정 신호로 해석될 경우 금리인하 기대를 지지(비둘기적 재료)할 수 있습니다."
                )
    lines.append(
        "\nℹ️ 참고: 연준은 PCE(특히 근원 PCE)를 CPI보다 더 중요한 정책 판단 지표로 간주합니다."
        if label_kr == "CPI" else
        "ℹ️ 참고: PCE는 FOMC가 공식적으로 가장 중시하는 물가지표입니다."
    )
    return "\n".join(lines)


def interpret_nfp(event: Dict[str, Any], fred_api_key: str) -> str:
    ind = INDICATOR_BY_KEY["nfp"]
    lines = ["\U0001F50D <b>고용지표(NFP) 세부 해석</b>"]
    if not fred_api_key:
        lines.append("(FRED_API_KEY가 설정되지 않아 세부 해석 대신 발표치만 안내합니다.)")
        return "\n".join(lines)

    payrolls = fred_client.latest_level_change(ind["fred"]["payrolls_level"], fred_api_key)
    unrate = fred_client.latest_value(ind["fred"]["unemployment_rate"], fred_api_key)
    wages = fred_client.mom_yoy(ind["fred"]["avg_hourly_earnings"], fred_api_key)
    participation = fred_client.latest_value(ind["fred"]["participation_rate"], fred_api_key)

    if payrolls:
        lines.append(f"• 비농업 고용 증감: 전월대비 {payrolls.get('change'):+.0f}천 명")
    if unrate:
        lv, pv = unrate.get("latest_value"), unrate.get("prev_value")
        if lv is not None and pv is not None:
            direction = "상승(고용시장 둔화 신호)" if lv > pv else ("하락(고용시장 견조 신호)" if lv < pv else "보합")
            lines.append(f"• 실업률: {lv}% (전월 {pv}% → {direction})")
    if wages:
        lines.append(
            f"• 시간당 평균임금(임금 인플레이션): 전월비 {wages.get('mom_pct')}%, 전년비 {wages.get('yoy_pct')}%"
        )
        yoy = wages.get("yoy_pct")
        if yoy is not None:
            if yoy >= 4.0:
                lines.append("  → 임금 상승률이 여전히 높아 서비스물가·인플레 재가속 우려로 이어질 수 있습니다(매파적).")
            elif yoy <= 3.5:
                lines.append("  → 임금 상승률이 둔화되며 인플레 압력 완화 신호로 해석될 수 있습니다(비둘기적).")
    if participation:
        lv = participation.get("latest_value")
        if lv is not None:
            lines.append(f"• 경제활동참가율: {lv}%")
    lines.append(
        "\nℹ️ 참고: 연준은 '최대 고용' 목표 판단에서 실업률뿐 아니라 임금 상승률, 참가율을 함께 봅니다."
    )
    return "\n".join(lines)


def interpret_fomc(event: Dict[str, Any], fred_api_key: str) -> str:
    ind = INDICATOR_BY_KEY["fomc_rate_decision"]
    lines = ["\U0001F50D <b>FOMC 금리결정 세부 해석</b>"]
    if not fred_api_key:
        lines.append("(FRED_API_KEY가 설정되지 않아 세부 해석 대신 발표치만 안내합니다.)")
        return "\n".join(lines)
    upper = fred_client.latest_value(ind["fred"]["target_upper"], fred_api_key)
    lower = fred_client.latest_value(ind["fred"]["target_lower"], fred_api_key)
    if upper and lower:
        lu, pu = upper.get("latest_value"), upper.get("prev_value")
        ll, pl = lower.get("latest_value"), lower.get("prev_value")
        lines.append(f"• 새 기준금리 목표범위: {ll}% ~ {lu}%")
        if pu is not None and pl is not None:
            if lu > pu:
                lines.append(f"  → 이전({pl}%~{pu}%) 대비 <b>인상</b>")
            elif lu < pu:
                lines.append(f"  → 이전({pl}%~{pu}%) 대비 <b>인하</b>")
            else:
                lines.append(f"  → 이전({pl}%~{pu}%)과 <b>동결</b>")
    lines.append(
        "\nℹ️ 참고: 성명서 문구·점도표(dot plot)·파월 의장 기자회견 톤은 자동 분석 대상이 아닙니다. "
        "금리 자체의 방향 외 '매파/비둘기' 뉘앙스는 원문 확인을 권장합니다."
    )
    return "\n".join(lines)


def interpret_ppi(event: Dict[str, Any], fred_api_key: str) -> str:
    ind = INDICATOR_BY_KEY["ppi"]
    headline_series = ind["fred"]["headline_index"]
    core_series = ind["fred"]["core_index"]

    lines = ["\U0001F50D <b>PPI(생산자물가) 세부 해석</b>"]
    if not fred_api_key:
        lines.append("(FRED_API_KEY가 설정되지 않아 세부 해석 대신 발표치만 안내합니다.)")
        return "\n".join(lines)

    headline = fred_client.mom_yoy(headline_series, fred_api_key)
    core = fred_client.mom_yoy(core_series, fred_api_key)

    if headline:
        lines.append(
            f"• 헤드라인 PPI — 전월비(MoM): {headline.get('mom_pct')}%,  전년동월비(YoY): {headline.get('yoy_pct')}%"
        )
    if core:
        lines.append(
            f"• 근원(Core, 식품·에너지 제외) — 전월비(MoM): {core.get('mom_pct')}%,  전년동월비(YoY): {core.get('yoy_pct')}%"
        )
        trend_txt = _trend_text(core.get("mom_trend_6m", []))
        if trend_txt:
            lines.append(f"  → {trend_txt}")
    lines.append(
        "\nℹ️ 참고: PPI(생산자물가)는 기업이 원자재·중간재 구입에 지불하는 가격입니다. "
        "이 원가 압력은 보통 시차를 두고 소비자물가(CPI/PCE)에 전가되는 경향이 있어, "
        "시장은 PPI를 향후 CPI/PCE 흐름을 가늠하는 선행 신호 중 하나로 참고합니다."
    )
    return "\n".join(lines)


def interpret_gdp(event: Dict[str, Any], fred_api_key: str) -> str:
    ind = INDICATOR_BY_KEY["gdp"]
    series_id = ind["fred"]["growth_rate"]

    lines = ["\U0001F50D <b>GDP 성장률 세부 해석</b>"]
    if not fred_api_key:
        lines.append("(FRED_API_KEY가 설정되지 않아 세부 해석 대신 발표치만 안내합니다.)")
        return "\n".join(lines)

    # 주의: 이 시리즈(A191RL1Q225SBEA)는 FRED에 이미 '연율 성장률(%)'로 제공되는 값이라,
    # CPI/PCE처럼 지수 레벨에 mom_yoy()를 적용하면 '성장률의 성장률'이라는 의미 없는 값이 나온다.
    # 그래서 여기서는 latest_value(원값 그대로)를 쓰고, 직전 분기 대비는 직접 비교한다.
    obs = fred_client.get_observations(series_id, fred_api_key, limit=5)
    obs = [o for o in obs if o[1] is not None]
    if not obs:
        lines.append("(FRED에서 데이터를 가져오지 못했습니다.)")
        return "\n".join(lines)

    latest_date, latest_val = obs[0]
    lines.append(f"• 실질GDP 성장률(전분기 대비, 연율 환산): {latest_val:+.1f}%")

    if len(obs) >= 2:
        prev_val = obs[1][1]
        diff = latest_val - prev_val
        if abs(diff) < 0.2:
            trend_txt = f"직전 분기({prev_val:+.1f}%)와 비슷한 성장 속도를 유지하고 있습니다."
        elif diff > 0:
            trend_txt = f"직전 분기({prev_val:+.1f}%) 대비 성장세가 가속되고 있습니다."
        else:
            trend_txt = f"직전 분기({prev_val:+.1f}%) 대비 성장세가 둔화되고 있습니다."
        lines.append(f"  → {trend_txt}")

    if latest_val < 0:
        lines.append("  → 마이너스 성장은 경기 위축 국면을 시사할 수 있어 시장의 주목도가 특히 높습니다.")

    lines.append(
        "\nℹ️ 참고: 이 수치는 계절조정 후 연율 환산된 전분기 대비 실질GDP 성장률입니다. "
        "연준은 통화정책 결정에서 물가·고용지표를 더 직접적으로 활용하지만, "
        "GDP는 경기 사이클 전반을 판단하는 배경지표로 함께 참고됩니다."
    )
    return "\n".join(lines)


def interpret_jolts(event: Dict[str, Any], fred_api_key: str) -> str:
    ind = INDICATOR_BY_KEY["jolts"]
    series_id = ind["fred"]["job_openings"]

    lines = ["\U0001F50D <b>JOLTS(구인·이직보고서) 세부 해석</b>"]
    if not fred_api_key:
        lines.append("(FRED_API_KEY가 설정되지 않아 세부 해석 대신 발표치만 안내합니다.)")
        return "\n".join(lines)

    mv = fred_client.mom_yoy(series_id, fred_api_key)
    if mv and mv.get("latest_value") is not None:
        level_m = mv["latest_value"] / 1000.0  # FRED는 천 단위 -> 백만 단위로 환산
        lines.append(
            f"• 채용공고(Job Openings): {level_m:.2f}백만 건 "
            f"(전월비 {mv.get('mom_pct')}%, 전년비 {mv.get('yoy_pct')}%)"
        )
        trend_txt = _trend_text(
            mv.get("mom_trend_6m", []),
            rising="최근 3개월간 채용 수요가 다시 늘어나는 흐름입니다.",
            falling="최근 3개월간 채용 수요가 둔화되는 흐름입니다.",
            flat="최근 3개월간 채용공고 수준이 큰 변화 없이 유지되고 있습니다.",
        )
        if trend_txt:
            lines.append(f"  → {trend_txt}")
    lines.append(
        "\nℹ️ 참고: JOLTS 채용공고는 기업의 인력 수요(노동시장 수요 측면)를 보여주는 지표로, "
        "연준은 이를 통해 인플레이션 압력으로 이어질 수 있는 노동시장 과열/냉각 여부를 가늠합니다."
    )
    return "\n".join(lines)


def interpret_initial_claims(event: Dict[str, Any], fred_api_key: str) -> str:
    ind = INDICATOR_BY_KEY["initial_claims"]
    series_id = ind["fred"]["level"]

    lines = ["\U0001F50D <b>신규 실업수당 청구건수 세부 해석</b>"]
    if not fred_api_key:
        lines.append("(FRED_API_KEY가 설정되지 않아 세부 해석 대신 발표치만 안내합니다.)")
        return "\n".join(lines)

    obs = fred_client.get_observations(series_id, fred_api_key, limit=5)
    obs = [o for o in obs if o[1] is not None]
    if not obs:
        lines.append("(FRED에서 데이터를 가져오지 못했습니다.)")
        return "\n".join(lines)

    latest_date, latest_val = obs[0]
    lines.append(f"• 이번 주 신규 청구건수: {latest_val:,.0f}건")

    if len(obs) >= 4:
        avg4 = sum(v for _, v in obs[:4]) / 4
        lines.append(f"• 최근 4주 평균: {avg4:,.0f}건")
        diff = latest_val - avg4
        if abs(diff) < avg4 * 0.03:
            trend_txt = "4주 평균과 비슷한 수준으로, 뚜렷한 방향성 변화는 없습니다."
        elif diff > 0:
            trend_txt = "4주 평균을 웃돌아 노동시장이 다소 냉각되고 있다는 신호로 해석될 수 있습니다."
        else:
            trend_txt = "4주 평균을 밑돌아 노동시장이 여전히 견조하다는 신호로 해석될 수 있습니다."
        lines.append(f"  → {trend_txt}")

    lines.append(
        "\nℹ️ 참고: 매주 발표돼 변동성이 큰 지표라 단주(單週) 수치만으로 판단하기보다, "
        "4주 이동평균과 함께 보면 노동시장 방향성(둔화/견조)을 가장 빠르게 포착할 수 있는 지표 중 하나입니다."
    )
    return "\n".join(lines)


def build_interpretation_message(event: Dict[str, Any], fred_api_key: str) -> Optional[str]:
    """fed_critical 지표에 한해 세부 해석 메시지를 만든다. 아니면 None."""
    key = event["indicator_key"]
    ind = INDICATOR_BY_KEY[key]
    if not ind["fed_critical"]:
        return None

    if key == "cpi":
        return interpret_cpi_or_pce(event, fred_api_key, "CPI")
    if key == "pce":
        return interpret_cpi_or_pce(event, fred_api_key, "PCE")
    if key == "nfp":
        return interpret_nfp(event, fred_api_key)
    if key == "fomc_rate_decision":
        return interpret_fomc(event, fred_api_key)
    if key == "ppi":
        return interpret_ppi(event, fred_api_key)
    if key == "gdp":
        return interpret_gdp(event, fred_api_key)
    if key == "jolts":
        return interpret_jolts(event, fred_api_key)
    if key == "initial_claims":
        return interpret_initial_claims(event, fred_api_key)

    return None
