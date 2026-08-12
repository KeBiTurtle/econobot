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

def _trend_text(mom_trend):
    vals = [v for v in mom_trend if v is not None]
    if len(vals) < 3:
        return ""
    recent = vals[-3:]
    if recent[-1] > recent[0]:
        return "최근 3개월간 상승 압력이 다시 확대되는 흐름입니다."
    elif recent[-1] < recent[0]:
        return "최근 3개월간 둔화(디스인플레이션) 흐름이 이어지고 있습니다."
    return "최근 3개월간 큰 방향성 변화 없이 횡보하고 있습니다."


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
    if key in ("ppi", "gdp", "jolts"):
        # 일반적인 FRED 최신치/추세 안내 (레벨 or MoM/YoY)
        sub = ind["fred"]
        lines = [f"\U0001F50D <b>{ind['name_kr']} 세부 해석</b>"]
        if not fred_api_key:
            lines.append("(FRED_API_KEY가 설정되지 않아 세부 해석 대신 발표치만 안내합니다.)")
            return "\n".join(lines)
        for sub_name, series_id in sub.items():
            mv = fred_client.mom_yoy(series_id, fred_api_key)
            if mv:
                lines.append(f"• {sub_name}: MoM {mv.get('mom_pct')}%, YoY {mv.get('yoy_pct')}%")
            else:
                lv = fred_client.latest_value(series_id, fred_api_key)
                if lv:
                    lines.append(f"• {sub_name}: 최신값 {lv.get('latest_value')} (이전 {lv.get('prev_value')})")
        return "\n".join(lines)

    return None
