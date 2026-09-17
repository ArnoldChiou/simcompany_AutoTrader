import datetime
import logging
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from selenium.common.exceptions import TimeoutException

from AutoBuyer import AutoBuyer
from market_utils import get_market_data
from production_monitor import BaseMonitor, BuildingConstructionMonitor, PowerPlantProducer
from retail_profit_advisor import (
    RetailProfitAdvisor,
    RetailRecommendation,
    parse_labeled_number,
    weighted_market_price,
)
from service_runner import run_service
from telegram_utils import send_telegram_notify


class MarketDataTests(unittest.TestCase):
    def test_returns_lowest_order_and_next_distinct_price(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [
            {"id": 1, "quality": 0, "price": 10, "quantity": 5},
            {"id": 2, "quality": 0, "price": 10, "quantity": 7},
            {"id": 3, "quality": 0, "price": 12, "quantity": 9},
        ]
        session = Mock()
        session.get.return_value = response

        result = get_market_data(session, "https://example.test", 0, return_order_detail=True)

        self.assertEqual(result["lowest_order"]["id"], 1)
        self.assertEqual(result["second_lowest_price"], 12)


class AutoBuyerTests(unittest.TestCase):
    def test_extract_resource_id(self):
        buyer = AutoBuyer({}, {}, {}, None, None, None)
        self.assertEqual(
            buyer._extract_resource_id("https://www.simcompanies.com/api/v3/market/0/113/"),
            113,
        )

    def test_invalid_resource_url_returns_none(self):
        buyer = AutoBuyer({}, {}, {}, None, None, None)
        self.assertIsNone(buyer._extract_resource_id("https://example.test/not-market"))

    def test_parse_price_with_thousands_separator(self):
        self.assertEqual(AutoBuyer._parse_price_text("$2,200.000"), 2200.0)

    def test_historical_average_uses_product_samples(self):
        buyer = AutoBuyer({}, {}, {}, None, None, None)
        buyer._price_history = {
            "Power": [
                {"timestamp": "2030-01-01T00:00:00", "price": 10.0},
                {"timestamp": "2030-01-01T01:00:00", "price": 14.0},
            ]
        }
        average, sample_count = buyer._get_historical_average("Power")
        self.assertEqual(average, 12.0)
        self.assertEqual(sample_count, 2)


class PowerPlantTests(unittest.TestCase):
    def test_finish_time_is_timezone_aware(self):
        parsed = PowerPlantProducer._parse_finish_time("2030-01-02 03:04:05")
        self.assertIsNotNone(parsed.tzinfo)

    def test_finish_time_keeps_same_instant(self):
        parsed = PowerPlantProducer._parse_finish_time("2030-01-02T03:04:05+00:00")
        expected = datetime.datetime(2030, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
        self.assertEqual(parsed.timestamp(), expected.timestamp())

    def test_finds_nested_finish_time_used_by_upgrade_and_robot_installation(self):
        monitor = PowerPlantProducer([], logger=Mock())
        parent = Mock()
        parent.is_displayed.return_value = True
        parent.text = "UPGRADING BUILDING Finishes at 01/02/30 3:04 AM"
        timer = Mock()
        timer.is_displayed.return_value = True
        timer.text = "Finishes at\n01/02/30 3:04 AM"
        monitor.driver = Mock()
        monitor.driver.find_elements.return_value = [parent, timer]

        element, text, finish_dt = monitor._find_visible_finish_time()

        self.assertIs(element, timer)
        self.assertEqual(text, "Finishes at 01/02/30 3:04 AM")
        self.assertEqual(finish_dt.year, 2030)


class MonitorLoginTests(unittest.TestCase):
    def test_public_home_price_ticker_is_not_treated_as_authenticated(self):
        monitor = BaseMonitor("TestMonitor", logger=Mock())
        monitor.driver = Mock()
        sign_in = Mock()
        sign_in.is_displayed.return_value = True
        public_ticker = Mock()
        public_ticker.is_displayed.return_value = True
        monitor.driver.find_elements.side_effect = [[sign_in], [public_ticker]]

        self.assertEqual(monitor._login_state(), "login_required")
        self.assertEqual(monitor.driver.find_elements.call_count, 1)

    @patch("production_monitor.initialize_driver")
    def test_background_login_failure_does_not_read_stdin(self, initialize_driver):
        driver = Mock()
        driver.current_url = "https://www.simcompanies.com/signin/"
        initialize_driver.return_value = driver
        monitor = BaseMonitor("TestMonitor", logger=Mock())

        with patch.object(monitor, "_wait_for_login_state", return_value="login_required"), \
                patch("production_monitor.send_telegram_notify", return_value=True) as notify, \
                patch("builtins.input", side_effect=AssertionError("stdin must not be read")):
            self.assertFalse(monitor._initialize_driver())
            self.assertFalse(monitor._initialize_driver())

        notify.assert_called_once()
        self.assertEqual(driver.quit.call_count, 2)

    @patch("production_monitor.initialize_driver")
    def test_successful_login_clears_alert_suppression(self, initialize_driver):
        initialize_driver.return_value = Mock()
        monitor = BaseMonitor("TestMonitor", logger=Mock())
        monitor._login_alert_sent = True

        with patch.object(monitor, "_wait_for_login_state", return_value="authenticated"):
            self.assertTrue(monitor._initialize_driver())

        self.assertFalse(monitor._login_alert_sent)


class ServiceRunnerTests(unittest.TestCase):
    @patch("service_runner.run_building_construction_monitor")
    @patch("service_runner.setup_logger")
    def test_construction_service_uses_activity_logger(self, setup_logger, run_monitor):
        logger = Mock()
        setup_logger.return_value = logger

        run_service("construction")

        setup_logger.assert_called_once_with("production_monitor.activity", "monitor_activity.log")
        run_monitor.assert_called_once_with(logger)


class ConstructionNotificationTests(unittest.TestCase):
    def test_removes_stale_timer_for_building_absent_from_loaded_landscape(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = BuildingConstructionMonitor(
                logger=Mock(), state_file_path=os.path.join(directory, "activity_state.json")
            )
            monitor.state = {
                "initialized": True,
                "constructions": {},
                "productions": {
                    "/b/old/": {
                        "name": "Removed building",
                        "url": "https://www.simcompanies.com/b/old/",
                        "products": {"Old#1": {"name": "Old", "finish_at": "2020-01-01 00:00:00"}},
                    }
                },
            }

            monitor._update_state_and_notify({}, active_paths=[])

            self.assertEqual(monitor.state["productions"], {})

    def test_empty_landscape_timeout_preserves_previous_state(self):
        monitor = BuildingConstructionMonitor(logger=Mock())
        monitor.driver = Mock()
        monitor.driver.find_elements.return_value = []

        with patch.object(monitor, "_check_login_required", return_value=False), \
             patch("production_monitor.WebDriverWait") as wait:
            wait.return_value.until.side_effect = [Mock(), TimeoutException()]
            self.assertIsNone(monitor._get_landscape_building_paths())

    def test_notifies_after_a_tracked_construction_becomes_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "activity_state.json")
            monitor = BuildingConstructionMonitor(
                logger=Mock(), state_file_path=state_path, poll_seconds=300
            )
            construction = {
                "/b/123/": {
                    "name": "Test Factory",
                    "url": "https://www.simcompanies.com/b/123/",
                    "construction": {
                        "name": "Test Factory",
                        "url": "https://www.simcompanies.com/b/123/",
                        "finish_at": "2020-01-01 00:00:00",
                    },
                    "products": {},
                }
            }

            # The first scan must only establish state, not announce a stale build.
            with patch("production_monitor.send_telegram_notify") as notify:
                monitor._update_state_and_notify(construction)
                notify.assert_not_called()

            completed = {
                "/b/123/": {
                    "name": "Test Factory",
                    "url": "https://www.simcompanies.com/b/123/",
                    "construction": None,
                    "products": {},
                }
            }
            with patch("production_monitor.send_telegram_notify", return_value=True) as notify:
                monitor._update_state_and_notify(completed)
                notify.assert_not_called()
                monitor._update_state_and_notify(completed)
                notify.assert_called_once()
            self.assertEqual(monitor.state["constructions"], {})

    def test_notifies_after_a_tracked_product_timer_disappears(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = BuildingConstructionMonitor(
                logger=Mock(), state_file_path=os.path.join(directory, "activity_state.json")
            )
            producing = {
                "/b/123/": {
                    "name": "Test Factory", "url": "https://www.simcompanies.com/b/123/",
                    "construction": None,
                    "products": {"Widgets#1": {"name": "Widgets", "finish_at": "2020-01-01 00:00:00"}},
                }
            }
            monitor._update_state_and_notify(producing)
            with patch("production_monitor.send_telegram_notify", return_value=True) as notify:
                completed = {
                    "/b/123/": {
                        "name": "Test Factory", "url": "https://www.simcompanies.com/b/123/",
                        "construction": None, "products": {},
                    }
                }
                monitor._update_state_and_notify(completed)
                notify.assert_not_called()
                self.assertEqual(
                    monitor.state["productions"]["/b/123/"]["products"]["Widgets#1"]["_missing_confirmations"],
                    1,
                )
                monitor._update_state_and_notify(completed)
                notify.assert_called_once()

    def test_preserves_a_missing_product_timer_until_its_finish_time(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = BuildingConstructionMonitor(
                logger=Mock(), state_file_path=os.path.join(directory, "activity_state.json")
            )
            monitor.state = {
                "initialized": True,
                "constructions": {},
                "productions": {
                    "/b/123/": {
                        "name": "Test Store",
                        "url": "https://www.simcompanies.com/b/123/",
                        "products": {
                            "Tablets#1": {"name": "Tablets", "finish_at": "2030-01-01 00:00:00"}
                        },
                    }
                },
            }
            idle = {
                "/b/123/": {
                    "name": "Test Store",
                    "url": "https://www.simcompanies.com/b/123/",
                    "construction": None,
                    "products": {},
                }
            }

            with patch("production_monitor.send_telegram_notify") as notify:
                monitor._update_state_and_notify(idle)

            notify.assert_not_called()
            self.assertIn("Tablets#1", monitor.state["productions"]["/b/123/"]["products"])

    def test_power_products_are_ignored_by_default(self):
        monitor = BuildingConstructionMonitor(logger=Mock())
        self.assertTrue(monitor._is_ignored_product("POWER Q7"))
        self.assertFalse(monitor._is_ignored_product("BATTERIES Q3"))

    def test_dedupes_alternate_labels_for_the_same_product_timer(self):
        products = {
            "PRODUCTION\nProcessors#1": {
                "name": "PRODUCTION\nProcessors", "finish_at": "2030-01-01 12:00:00"
            },
            "PROCESSORS Q2#1": {
                "name": "PROCESSORS Q2", "finish_at": "2030-01-01 12:00:00"
            },
        }

        deduped = BuildingConstructionMonitor._dedupe_products(products)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(next(iter(deduped.values()))["name"], "PROCESSORS Q2")

    def test_duplicate_old_labels_send_only_one_completion_notification(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = BuildingConstructionMonitor(
                logger=Mock(), state_file_path=os.path.join(directory, "activity_state.json")
            )
            monitor.state = {
                "initialized": True,
                "constructions": {},
                "productions": {
                    "/b/123/": {
                        "name": "Test Factory",
                        "url": "https://www.simcompanies.com/b/123/",
                        "products": {
                            "PRODUCTION\nProcessors#1": {
                                "name": "PRODUCTION\nProcessors", "finish_at": "2020-01-01 00:00:00"
                            },
                            "PROCESSORS Q2#1": {
                                "name": "PROCESSORS Q2", "finish_at": "2020-01-01 00:00:00"
                            },
                        },
                    }
                },
            }
            idle = {
                "/b/123/": {
                    "name": "Test Factory",
                    "url": "https://www.simcompanies.com/b/123/",
                    "construction": None,
                    "products": {},
                }
            }

            with patch("production_monitor.send_telegram_notify", return_value=True) as notify:
                monitor._update_state_and_notify(idle)
                notify.assert_not_called()
                monitor._update_state_and_notify(idle)

            notify.assert_called_once()
            self.assertIn("PROCESSORS Q2", notify.call_args.args[0])

    def test_heading_change_with_same_timer_is_not_a_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = BuildingConstructionMonitor(
                logger=Mock(), state_file_path=os.path.join(directory, "activity_state.json")
            )
            monitor.state = {
                "initialized": True,
                "constructions": {},
                "productions": {
                    "/b/123/": {
                        "name": "Test Factory",
                        "url": "https://www.simcompanies.com/b/123/",
                        "products": {
                            "PROCESSORS Q2#1": {
                                "name": "PROCESSORS Q2", "finish_at": "2030-01-01 00:00:00"
                            }
                        },
                    }
                },
            }
            renamed = {
                "/b/123/": {
                    "name": "Test Factory",
                    "url": "https://www.simcompanies.com/b/123/",
                    "construction": None,
                    "products": {
                        "Processors#1": {
                            "name": "Processors", "finish_at": "2030-01-01 00:00:00"
                        }
                    },
                }
            }

            with patch("production_monitor.send_telegram_notify") as notify:
                monitor._update_state_and_notify(renamed)

            notify.assert_not_called()
            saved_products = monitor.state["productions"]["/b/123/"]["products"]
            self.assertEqual(len(saved_products), 1)
            self.assertEqual(next(iter(saved_products.values()))["name"], "PROCESSORS Q2")

    def test_combined_construction_heading_is_classified_as_construction(self):
        activity_type, name = BuildingConstructionMonitor._normalize_activity_heading(
            "CONSTRUCTION\nUpgrading to level 15"
        )
        self.assertEqual(activity_type, "construction")
        self.assertEqual(name, "Upgrading to level 15")


class TelegramTests(unittest.TestCase):
    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"})
    @patch("telegram_utils.requests.post")
    def test_send_telegram_notify_posts_message(self, post):
        response = Mock()
        response.json.return_value = {"ok": True}
        post.return_value = response

        self.assertTrue(send_telegram_notify("hello"))
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["json"]["chat_id"], "chat")
        self.assertEqual(post.call_args.kwargs["json"]["text"], "hello")


class RetailProfitAdvisorTests(unittest.TestCase):
    def test_inventory_book_cost_is_replaced_not_deducted_twice(self):
        result = RetailRecommendation('Quadcopter', 543, 4, 124.819, 870, 865)
        self.assertAlmostEqual(result.net_profit_per_unit, 119.819)
        self.assertAlmostEqual(result.net_profit_total, 65061.717)

    def test_literal_duration_is_not_misread_as_unit_count(self):
        quantity = Mock()
        quantity.get_attribute.return_value = '48hr'
        self.assertIsNone(RetailProfitAdvisor._resolved_quantity(quantity, 'Quantity 48hr'))

    def test_resource_id_comes_from_actual_encyclopedia_product_link(self):
        link = Mock()
        link.get_attribute.return_value = 'https://www.simcompanies.com/encyclopedia/0/resource/24/'
        card = Mock()
        card.find_elements.return_value = [link]
        self.assertEqual(RetailProfitAdvisor._resource_id_from_card(card), 24)

    def test_weighted_market_price_uses_the_full_required_quantity(self):
        orders = [
            {"quality": 0, "price": 10, "quantity": 5},
            {"quality": 0, "price": 14, "quantity": 5},
        ]
        self.assertEqual(weighted_market_price(orders, 8), 11.5)

    def test_weighted_market_price_requires_enough_matching_quality(self):
        orders = [{"quality": 1, "price": 10, "quantity": 100}]
        self.assertIsNone(weighted_market_price(orders, 10, quality=2))

    def test_parse_labeled_number_supports_negative_game_currency(self):
        self.assertEqual(
            parse_labeled_number("Profit per unit: -$1,234.50", ("Profit per unit",)),
            -1234.5,
        )

    def test_telegram_text_ranks_by_total_net_profit(self):
        advisor = RetailProfitAdvisor(hours=48)
        high = RetailRecommendation("Bread", 100, 0, 12, 10)
        low = RetailRecommendation("Cheese", 100, 0, 8, 7)
        report = advisor.telegram_text([high, low], 48)
        self.assertIn("1. Bread", report)
        self.assertIn("淨利 $200", report)


if __name__ == "__main__":
    unittest.main()
