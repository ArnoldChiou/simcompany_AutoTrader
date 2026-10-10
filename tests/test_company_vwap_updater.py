import unittest
from contextlib import redirect_stdout
from io import StringIO
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from company_vwap_updater import (
    aggregate_inventory,
    company_settings_url,
    format_listing_rows,
    fetch_resource_constants,
    map_warehouse_categories,
    replace_listing,
    resolve_profile,
)


class InventoryTests(unittest.TestCase):
    def test_sums_positive_unblocked_stock_by_resource_and_quality(self):
        records = [
            {"kind": 22, "quality": 4, "amount": 5, "blocked": False},
            {"kind": 22, "quality": 4, "amount": 7, "blocked": False},
            {"kind": 22, "quality": 3, "amount": 9, "blocked": True},
            {"kind": 2, "quality": 0, "amount": 0, "blocked": False},
        ]
        self.assertEqual(aggregate_inventory(records), {(22, 4): 12})

    def test_formats_batteries_q4_at_two_percent_below_market_vwap(self):
        market = {22: {"resource": {"resourceId": 22, "resourceName": "Batteries", "summariesByQuality": [
            {"quality": 4, "lastDayCandlestick": {"vwap": 85.38966}},
        ]}}}
        self.assertEqual(
            format_listing_rows({(22, 4): 9186}, market, {22: "Electronics"}, ["Electronics"]),
            ["Q | Product | Price", "[Electronics]", "Q4 | :re-22: | $83.68"],
        )

    def test_formats_sub_dollar_prices_to_three_decimal_places(self):
        market = {5: {"resource": {"resourceId": 5, "resourceName": "Product", "summariesByQuality": [
            {"quality": 0, "lastDayCandlestick": {"vwap": "0.12345"}},
        ]}}}
        self.assertEqual(
            format_listing_rows({(5, 0): 1}, market, {5: "Food"}, ["Food"]),
            ["Q | Product | Price", "[Food]", "Q0 | :re-5: | $0.121"],
        )

    def test_groups_rows_by_warehouse_category_in_table_format(self):
        market = {
            5: {"resource": {"resourceId": 5, "resourceName": "Product", "summariesByQuality": [
                {"quality": 0, "lastDayCandlestick": {"vwap": "0.12345"}},
            ]}},
            22: {"resource": {"resourceId": 22, "resourceName": "Batteries", "summariesByQuality": [
                {"quality": 4, "lastDayCandlestick": {"vwap": 85.38966}},
            ]}},
        }
        categories = {5: "Food", 22: "Electronics"}
        category_order = ["Food", "Electronics"]
        self.assertEqual(
            format_listing_rows({(22, 4): 9186, (5, 0): 1}, market, categories, category_order),
            [
                "Q | Product | Price",
                "[Food]",
                "Q0 | :re-5: | $0.121",
                "[Electronics]",
                "Q4 | :re-22: | $83.68",
            ],
        )

    def test_fetches_official_resource_constants(self):
        constants = {"119": {"image": "images/resources/coffee-ground.png"}}
        session = Mock()
        response = Mock()
        response.json.return_value = constants
        session.get.return_value = response

        fetched = fetch_resource_constants(session)

        self.assertEqual(fetched, constants)
        session.get.assert_called_once_with(
            "https://www.simcompanies.com/api/v2/constants/resources/", timeout=20
        )

    def test_maps_resource_images_to_live_warehouse_groups(self):
        constants = {
            "119": {"image": "images/resources/coffee-ground.png"},
            "1": {"image": "images/resources/power.png"},
        }
        groups = [
            {
                "category": "Food",
                "images": ["https://www.simcompanies.com/static/images/resources/coffee-ground.bcae51dc2976.png"],
            },
            {
                "category": "Energy",
                "images": ["https://www.simcompanies.com/static/images/resources/power.123abc.png"],
            },
        ]

        order, categories = map_warehouse_categories(groups, constants)

        self.assertEqual(order, ["Food", "Energy"])
        self.assertEqual(categories, {119: "Food", 1: "Energy"})

    def test_fails_closed_when_any_stocked_quality_has_no_vwap(self):
        with self.assertRaisesRegex(ValueError, "商品.*ID 22.*Q4"):
            format_listing_rows({(22, 4): 1}, {22: {"resource": {"resourceId": 22, "summariesByQuality": []}}}, {22: "Electronics"}, ["Electronics"])


class DescriptionTests(unittest.TestCase):
    def test_updates_rows_but_preserves_header_divider_and_footer(self):
        original = "Selling @VWAP mp-3%\nold listing\n---------------------------------------------------------------------\nfooter\n\n"
        updated = replace_listing(original, ["Q4 :re-22:  @$85.39"])
        self.assertEqual(updated, "Selling @VWAP mp-3%\nQ4 :re-22:  @$85.39\n---------------------------------------------------------------------\nfooter\n\n")

    def test_refuses_unknown_description_format(self):
        with self.assertRaisesRegex(ValueError, "找不到 Selling @VWAP"):
            replace_listing("unrelated text", ["Q4 :re-22:  @$85.39"])

    def test_realm_url_is_company_settings_page(self):
        self.assertEqual(company_settings_url(0), "https://www.simcompanies.com/account-settings/settings/0/")


class ProfileTests(unittest.TestCase):
    def test_resolves_the_existing_construction_monitor_profile(self):
        with TemporaryDirectory() as profile, patch.dict("os.environ", {"USER_DATA_DIR_construction_monitor": profile}, clear=True):
            self.assertEqual(resolve_profile(), profile)

    def test_requires_a_configured_signed_in_profile(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "USER_DATA_DIR_construction_monitor"):
                resolve_profile()


class MainMenuIntegrationTests(unittest.TestCase):
    @patch("main.update_company_description")
    @patch("main.setup_logger")
    def test_menu_action_updates_the_company_description(self, setup_logger, update):
        from main import run_company_vwap_update

        logger = Mock()
        setup_logger.return_value = logger
        update.return_value = SimpleNamespace(
            item_count=56,
            backup_path=Path("record/backup.txt"),
            updated_description="Q4 :re-22:  @$85.39",
        )
        output = StringIO()
        with redirect_stdout(output):
            result = run_company_vwap_update()

        update.assert_called_once_with(apply=True, logger=logger)
        self.assertEqual(result.item_count, 56)
        self.assertIn("56", output.getvalue())


if __name__ == "__main__":
    unittest.main()
