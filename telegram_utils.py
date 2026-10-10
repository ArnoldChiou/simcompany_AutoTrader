"""Telegram notification helpers.

The bot token and destination chat are kept in ``.env`` so they are never
committed to the repository.
"""

import os

import requests
from dotenv import load_dotenv


load_dotenv()


def _report(logger, level, message):
    if logger:
        getattr(logger, level)(message)
    else:
        print(message)


def send_telegram_notify(message, logger=None):
    """Send *message* to the configured Telegram chat.

    Returns ``True`` only when Telegram accepted the message.  Configuration
    and network failures are reported through *logger* when provided, or to
    the console otherwise, without stopping a monitor loop.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        _report(
            logger,
            "warning",
            "[Telegram] 未設定：請在 .env 加入 TELEGRAM_BOT_TOKEN 與 TELEGRAM_CHAT_ID。",
        )
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok", False):
            _report(
                logger,
                "error",
                f"[Telegram] 通知發送失敗：{payload.get('description', 'unknown error')}",
            )
            return False
        _report(logger, "info", "[Telegram] 通知已成功送達 Telegram API。")
        return True
    except requests.RequestException as error:
        _report(logger, "error", f"[Telegram] 通知發送失敗：{error}")
    except ValueError:
        _report(logger, "error", "[Telegram] 回傳了無法解析的內容。")
    return False
