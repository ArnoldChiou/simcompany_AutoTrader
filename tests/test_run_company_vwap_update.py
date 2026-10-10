import unittest
from unittest.mock import Mock, patch

from run_company_vwap_update import run


class ScheduledVwapRunnerTests(unittest.TestCase):
    @patch("run_company_vwap_update.update_company_description")
    @patch("run_company_vwap_update.setup_logger")
    def test_runs_update_once_and_returns_success(self, setup_logger, update):
        logger = Mock()
        setup_logger.return_value = logger
        update.return_value = Mock(item_count=56, backup_path="backup.txt")

        status = run()

        self.assertEqual(status, 0)
        update.assert_called_once_with(apply=True, logger=logger)
        logger.info.assert_called()

    @patch("run_company_vwap_update.update_company_description", side_effect=RuntimeError("temporary API failure"))
    @patch("run_company_vwap_update.setup_logger")
    def test_returns_failure_and_logs_exception_when_update_fails(self, setup_logger, update):
        logger = Mock()
        setup_logger.return_value = logger

        status = run()

        self.assertEqual(status, 1)
        logger.exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
