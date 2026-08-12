# -*- coding: utf-8 -*-
"""
'별 3개(★★★)'급 경제지표 레지스트리.

각 지표는:
- key: 내부 식별자
- name_kr / name_en: 표시 이름
- ff_keywords: ForexFactory 캘린더 title 필드와 매칭할 키워드(소문자, 부분일치)
- fred: {서브지표명: FRED series_id} - 공식 실측치/과거 추세 계산용. 없으면 None(FRED에 없는 지표)
- fed_critical: 연준이 특히 중요하게 보는 지표인가 (True면 세부 해석 로직 적용)
- category: 분류(물가/고용/성장/제조업&서비스/통화정책/소비)
- unit_hint: 값 표시 시 참고용 단위 힌트

주의: ForexFactory의 'impact: High'가 investing.com의 '별 3개(빨간 폭탄)'와 대체로 대응됩니다.
      국가는 USD(미국)만 다룹니다 - '연준이 중요하게 여기는 지표' 요청에 맞춤.
"""

INDICATORS = [
    {
        "key": "cpi",
        "name_kr": "소비자물가지수(CPI)",
        "name_en": "CPI",
        "ff_keywords": ["cpi"],
        "fred": {
            "headline_index": "CPIAUCSL",   # CPI 전체(계절조정)
            "core_index": "CPILFESL",       # Core CPI(식품·에너지 제외)
        },
        "fed_critical": True,
        "category": "물가",
    },
    {
        "key": "pce",
        "name_kr": "개인소비지출물가지수(PCE)",
        "name_en": "PCE Price Index",
        "ff_keywords": ["pce price", "core pce", "personal consumption expenditures"],
        "fred": {
            "headline_index": "PCEPI",
            "core_index": "PCEPILFE",
        },
        "fed_critical": True,   # 연준이 공식적으로 가장 선호하는 물가지표
        "category": "물가",
    },
    {
        "key": "nfp",
        "name_kr": "비농업고용지수(NFP) / 실업률",
        "name_en": "Nonfarm Payrolls / Unemployment Rate",
        "ff_keywords": ["nonfarm payrolls", "non-farm employment change", "unemployment rate"],
        "fred": {
            "payrolls_level": "PAYEMS",         # 비농업 고용자 수(천명)
            "unemployment_rate": "UNRATE",
            "avg_hourly_earnings": "CES0500000003",  # 시간당 평균 임금
            "participation_rate": "CIVPART",
        },
        "fed_critical": True,
        "category": "고용",
    },
    {
        "key": "ppi",
        "name_kr": "생산자물가지수(PPI)",
        "name_en": "PPI",
        "ff_keywords": ["ppi", "producer price index"],
        "fred": {
            "headline_index": "PPIACO",
        },
        "fed_critical": True,
        "category": "물가",
    },
    {
        "key": "retail_sales",
        "name_kr": "소매판매",
        "name_en": "Retail Sales",
        "ff_keywords": ["retail sales"],
        "fred": {
            "level": "RSAFS",
        },
        "fed_critical": False,
        "category": "소비",
    },
    {
        "key": "ism_manufacturing",
        "name_kr": "ISM 제조업 구매관리자지수(PMI)",
        "name_en": "ISM Manufacturing PMI",
        "ff_keywords": ["ism manufacturing"],
        "fred": None,  # ISM 데이터는 라이선스 문제로 FRED 무료 제공 안 함 -> 캘린더 소스의 actual 값 사용
        "fed_critical": False,
        "category": "제조업",
    },
    {
        "key": "ism_services",
        "name_kr": "ISM 서비스업 구매관리자지수(PMI)",
        "name_en": "ISM Services / Non-Manufacturing PMI",
        "ff_keywords": ["ism services", "ism non-manufacturing"],
        "fred": None,
        "fed_critical": False,
        "category": "서비스업",
    },
    {
        "key": "gdp",
        "name_kr": "국내총생산(GDP) 성장률",
        "name_en": "GDP Growth Rate",
        "ff_keywords": ["gdp"],
        "fred": {
            "growth_rate": "A191RL1Q225SBEA",  # 실질GDP 성장률(연율)
        },
        "fed_critical": True,
        "category": "성장",
    },
    {
        "key": "fomc_rate_decision",
        "name_kr": "FOMC 기준금리 결정",
        "name_en": "FOMC Interest Rate Decision",
        "ff_keywords": ["fomc statement", "federal funds rate", "fed interest rate decision"],
        "fred": {
            "target_upper": "DFEDTARU",
            "target_lower": "DFEDTARL",
        },
        "fed_critical": True,
        "category": "통화정책",
    },
    {
        "key": "jolts",
        "name_kr": "구인이직보고서(JOLTS) 채용공고",
        "name_en": "JOLTS Job Openings",
        "ff_keywords": ["jolts"],
        "fred": {
            "job_openings": "JTSJOL",
        },
        "fed_critical": True,
        "category": "고용",
    },
    {
        "key": "consumer_confidence",
        "name_kr": "컨퍼런스보드 소비자신뢰지수",
        "name_en": "CB Consumer Confidence",
        "ff_keywords": ["cb consumer confidence"],
        "fred": None,
        "fed_critical": False,
        "category": "소비",
    },
    {
        "key": "michigan_sentiment",
        "name_kr": "미시간대 소비자심리지수",
        "name_en": "Michigan Consumer Sentiment",
        "ff_keywords": ["prelim umcsi", "revised umcsi", "michigan consumer sentiment"],
        "fred": {
            "index": "UMCSENT",
        },
        "fed_critical": False,
        "category": "소비",
    },
    {
        "key": "durable_goods",
        "name_kr": "내구재주문",
        "name_en": "Durable Goods Orders",
        "ff_keywords": ["durable goods orders"],
        "fred": {
            "level": "DGORDER",
        },
        "fed_critical": False,
        "category": "제조업",
    },
]

INDICATOR_BY_KEY = {i["key"]: i for i in INDICATORS}


def match_indicator(ff_title: str):
    """ForexFactory 이벤트 title 문자열을 지표 레지스트리와 매칭한다."""
    title_lower = ff_title.lower()
    for ind in INDICATORS:
        for kw in ind["ff_keywords"]:
            if kw in title_lower:
                return ind
    return None
