# -*- coding: utf-8 -*-
"""환경변수 기반 설정 로더."""
import os


class ConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise ConfigError(f"환경변수 {name} 가 설정되어 있지 않습니다. GitHub Secrets를 확인하세요.")
    return val


def _optional(name: str, default: str) -> str:
    """빈 문자열("")로 설정된 경우도 '미설정'으로 간주하고 기본값을 쓴다.
    (GitHub Actions에서 vars.X가 없으면 env에 빈 문자열이 채워지기 때문)"""
    val = os.environ.get(name, "").strip()
    return val if val else default


class Config:
    def __init__(self):
        self.telegram_bot_token = _require("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = _require("TELEGRAM_CHAT_ID")
        # FRED API 키는 없어도 동작은 하지만(캘린더 소스만으로 알림), 세부 해석 품질이 크게 떨어짐.
        self.fred_api_key = _optional("FRED_API_KEY", "")
        # 사전 공지를 보낼 한국시간(KST) 시각. "HH:MM" 형식.
        self.daily_digest_time_kst = _optional("DAILY_DIGEST_TIME_KST", "07:00")
        # 사전 공지가 너무 자주 중복되지 않도록 실행 주기 절반 정도의 허용 오차(분)를 둔다.
        self.daily_digest_window_minutes = int(_optional("DAILY_DIGEST_WINDOW_MINUTES", "10"))
        # 상태 저장 파일 경로 (GitHub Action이 커밋해서 다음 실행에도 유지)
        self.state_path = _optional("STATE_PATH", "state.json")
