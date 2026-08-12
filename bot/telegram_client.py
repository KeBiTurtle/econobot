# -*- coding: utf-8 -*-
"""텔레그램 메시지 발송."""
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 4000  # 텔레그램 제한(4096) 대비 여유


def send_message(bot_token: str, chat_id: str, text: str) -> None:
    if not text:
        return
    url = TELEGRAM_API.format(token=bot_token)
    # 너무 길면 분할 전송
    chunks = [text[i:i + MAX_LEN] for i in range(0, len(text), MAX_LEN)] or [text]
    for chunk in chunks:
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"텔레그램 전송 실패: {resp.status_code} {resp.text}")
