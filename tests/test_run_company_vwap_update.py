import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from run_company_vwap_update import run


class ScheduledVwapRunnerTests(unittest.TestCase):
    @patch("run_company_vwap_update.send_telegram_notify", create=True, return_value=True)
    @patch("run_company_vwap_update.update_company_description")
    @patch("run_company_vwap_update.setup_logger")
    def test_verified_update_sends_named_prices_to_telegram(self, setup_logger, update, send):
        logger = Mock()
        setup_logger.return_value = logger
        update.return_value = SimpleNamespace(
            company_id=123, realm_id=0, item_count=2, backup_path=Path("backup.txt"),
            listing_text="Q | Product | Price\n[Energy]\nQ0 | Water | $0.121\n[Electronics]\nQ4 | Batteries | $83.68",
        )
        status = run()
        self.assertEqual(status, 0)
        update.assert_called_once_with(apply=True, logger=logger)
        send.assert_called_once()
        message = send.call_args.args[0]
        self.assertIn("公司報價更新完成", message)
        self.assertIn("2", message)
        self.assertIn("VWAP × 0.98", message)
        self.assertIn("Q0 | Water | $0.121", message)
        self.assertIn("Q4 | Batteries | $83.68", message)
        self.assertNotIn(":re-", message)
        self.assertEqual(send.call_args.kwargs, {"logger": logger})

    @patch("run_company_vwap_update.send_telegram_notify", return_value=True)
    @patch("run_company_vwap_update.update_company_description")
    @patch("run_company_vwap_update.setup_logger")
    def test_long_report_is_split_without_losing_any_prices(self, setup_logger, update, send):
        listing = "\n".join(f"Q4 | Product {i} 電池 | ${i}.00" for i in range(250))
        update.return_value = SimpleNamespace(
            company_id=123, realm_id=0, item_count=250, backup_path=None, listing_text=listing,
        )
        self.assertEqual(run(), 0)
        self.assertGreater(send.call_count, 1)
        messages = [call.args[0] for call in send.call_args_list]
        self.assertTrue(all(len(message.encode("utf-16-le")) // 2 <= 4096 for message in messages))
        self.assertIn(listing, "\n".join(messages))
        self.assertIn("價格未變", messages[0])

    @patch("run_company_vwap_update.send_telegram_notify", return_value=False)
    @patch("run_company_vwap_update.update_company_description")
    @patch("run_company_vwap_update.setup_logger")
    def test_notification_failure_marks_task_failed_without_repeating_update(self, setup_logger, update, send):
        update.return_value = SimpleNamespace(
            company_id=123, realm_id=0, item_count=1, backup_path=None,
            listing_text="Q4 | Batteries | $83.68",
        )
        self.assertEqual(run(), 2)
        update.assert_called_once()
        send.assert_called_once()
        setup_logger.return_value.error.assert_called_once()

    @patch("run_company_vwap_update.send_telegram_notify", create=True, return_value=True)
    @patch("run_company_vwap_update.update_company_description", side_effect=RuntimeError("temporary API failure"))
    @patch("run_company_vwap_update.setup_logger")
    def test_update_failure_notifies_without_claiming_success(self, setup_logger, update, send):
        logger = Mock()
        setup_logger.return_value = logger
        status = run()
        self.assertEqual(status, 1)
        logger.exception.assert_called_once()
        send.assert_called_once()
        self.assertIn("失敗", send.call_args.args[0])
        self.assertNotIn("更新完成", send.call_args.args[0])
        self.assertNotIn("temporary API failure", send.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
