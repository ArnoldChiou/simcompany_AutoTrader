"""Task Scheduler entry point for the daily company VWAP refresh."""
from __future__ import annotations

from company_vwap_updater import update_company_description
from production_monitor import setup_logger


def run() -> int:
    logger = setup_logger("company_vwap_updater", "company_vwap_updater.log")
    try:
        result = update_company_description(apply=True, logger=logger)
    except Exception:
        logger.exception("Scheduled company VWAP description update failed.")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
