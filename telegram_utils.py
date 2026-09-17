"""Telegram notification helpers.

The bot token and destination chat are kept in ``.env`` so they are never
committed to the repository.
"""

import os

import requests
from dotenv import load_dotenv


load_dotenv()


def send_telegram_notify(message):
    """Send *message* to the configured Telegram chat.

    Returns ``True`` only when Telegram accepted the message.  Configuration
    and network failures are reported to the console instead of stopping a
    monitor loop.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[警告] Telegram 未設定：請在 .env 加入 TELEGRAM_BOT_TOKEN 與 TELEGRAM_CHAT_ID。")
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
            print(f"[錯誤] Telegram 通知發送失敗：{payload.get('description', 'unknown error')}")
            return False
        print("[通知] Telegram 通知已發送。")
        return True
    except requests.RequestException as error:
        print(f"[錯誤] Telegram 通知發送失敗：{error}")
    except ValueError:
        print("[錯誤] Telegram 回傳了無法解析的內容。")
    return False
