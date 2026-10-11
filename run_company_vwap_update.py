"""Task Scheduler entry point for the daily company VWAP refresh."""
from __future__ import annotations
from datetime import datetime

from company_vwap_updater import update_company_description
from production_monitor import setup_logger
from telegram_utils import send_telegram_notify


def run() -> int:
    logger = setup_logger("company_vwap_updater", "company_vwap_updater.log")
    try:
        result = update_company_description(apply=True, logger=logger)
    except Exception:
        logger.exception("Scheduled company VWAP description update failed.")
        send_telegram_notify(
            "公司報價更新失敗，未能確認公司描述是否已儲存。請檢查程式日誌。", logger=logger,
        )
        return 1

    if result.backup_path:
        logger.info(
            "Scheduled company description update verified: company_id=%s, realm=%s, "
            "stocked_quality_pairs=%s, backup=%s",
            result.company_id,
            result.realm_id,
            result.item_count,
            result.backup_path,
        )
    else:
        logger.info(
            "Scheduled company description is already current: company_id=%s, realm=%s, "
            "stocked_quality_pairs=%s",
            result.company_id,
            result.realm_id,
            result.item_count,
        )
    status = "公司報價更新完成（已回讀驗證）" if result.backup_path else "公司報價檢查完成（價格未變）"
    message = (
        f"{status}\n"
        f"時間：{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %z}\n"
        f"共 {result.item_count} 筆產品／品質報價\n"
        "單價：每日 VWAP × 0.98（低於 $1 顯示三位小數，其餘兩位）\n\n"
        f"{result.listing_text}"
    )
    # 1800 Unicode code points are at most 3600 UTF-16 units, below TG's 4096 limit.
    # Prefer a newline boundary so a product's quality/name/price stay together.
    while message:
        boundary = len(message)
        if boundary > 1800:
            boundary = message.rfind("\n", 0, 1801)
            if boundary <= 0:
                boundary = 1800
        part, message = message[:boundary], message[boundary:]
        if message.startswith("\n"):
            message = message[1:]
        if not send_telegram_notify(part, logger=logger):
            logger.error("Company description checked, but Telegram report delivery failed.")
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
