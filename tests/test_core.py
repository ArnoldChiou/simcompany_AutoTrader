import datetime
import logging
import unittest
from unittest.mock import Mock

from AutoBuyer import AutoBuyer
from market_utils import get_market_data
from production_monitor import PowerPlantProducer


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


class PowerPlantTests(unittest.TestCase):
    def test_finish_time_is_timezone_aware(self):
        parsed = PowerPlantProducer._parse_finish_time("2030-01-02 03:04:05")
        self.assertIsNotNone(parsed.tzinfo)

    def test_finish_time_keeps_same_instant(self):
        parsed = PowerPlantProducer._parse_finish_time("2030-01-02T03:04:05+00:00")
        expected = datetime.datetime(2030, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
        self.assertEqual(parsed.timestamp(), expected.timestamp())


if __name__ == "__main__":
    unittest.main()
