from decimal import Decimal
import unittest
from unittest.mock import patch

from building_profit_advisor import (
    Building,
    MarketQuote,
    Product,
    calculate_unit_gross_profit,
    deduplicate_buildings,
    _production_building_codes,
    products_for_building,
    render_report,
)


class BuildingProfitAdvisorTests(unittest.TestCase):
    def test_duplicate_landscape_tiles_are_collapsed_by_building_id(self):
        buildings = [
            Building("/b/101/", "Factory", "F"),
            Building("/b/101/", "Factory", "F"),
            Building("/b/202/", "Factory", "F"),
        ]
        self.assertEqual([b.path for b in deduplicate_buildings(buildings)], ["/b/101/", "/b/202/"])

    def test_resources_are_assigned_by_producing_building_code(self):
        constants = {
            "1": {"producedAt": "F", "isExchangeTradable": True},
            "2": {"producedAt": "G", "isExchangeTradable": True},
            "3": {"producedAt": "F", "isExchangeTradable": False},
        }
        self.assertEqual(products_for_building("F", constants), {1, 3})

    def test_gross_profit_subtracts_recipe_inputs_at_their_exchange_prices(self):
        product = Product(
            resource_id=10,
            name="Widget",
            input_quantities={1: Decimal("2"), 2: Decimal("0.5")},
        )
        self.assertEqual(
            calculate_unit_gross_profit(
                product,
                output_price=Decimal("20"),
                input_prices={1: Decimal("3"), 2: Decimal("4")},
            ),
            Decimal("12.0"),
        )

    def test_missing_input_price_does_not_guess_profit(self):
        product = Product(10, "Widget", {1: Decimal("2")})
        self.assertIsNone(
            calculate_unit_gross_profit(product, Decimal("20"), input_prices={})
        )

    def test_non_tradable_product_is_never_ranked_as_best(self):
        building = Building("/b/101/", "Factory", "F")
        row = (Product(10, "Internal good", {}, market_tradable=False), MarketQuote("Internal good", Decimal("100"), None), Decimal("100"))
        report = render_report([building], {"F": [row]}, [], "now")
        self.assertIn("不可交易，無交易所價格", report)
        self.assertIn("無足夠報價可判定毛利最高產品", report)
        self.assertNotIn("毛利最高：Internal good", report)

    def test_same_named_buildings_with_different_codes_keep_both_product_sets(self):
        buildings = [Building("/b/101/", "Factory", "F"), Building("/b/202/", "Factory", "G")]
        rows = {
            "F": [(Product(10, "Steel", {}, True), MarketQuote("Steel", Decimal("10"), None), Decimal("10"))],
            "G": [(Product(11, "Glass", {}, True), MarketQuote("Glass", Decimal("12"), None), Decimal("12"))],
        }
        report = render_report(buildings, rows, [], "now")
        self.assertIn("Steel", report)
        self.assertIn("Glass", report)
        self.assertIn("Factory（生產類型 F）", report)
        self.assertIn("Factory（生產類型 G）", report)

    def test_building_page_failure_remains_in_landscape_total(self):
        class BrokenDriver:
            def get(self, _url):
                pass

        class ImmediateTimeout:
            def __init__(self, *_args, **_kwargs):
                pass

            def until(self, _condition):
                raise TimeoutError("page did not load")

        building = Building("/b/404/", "Factory", None)
        with patch("building_profit_advisor.WebDriverWait", ImmediateTimeout):
            resolved, issues = _production_building_codes(BrokenDriver(), [building], {})
        self.assertEqual(resolved, [building])
        report = render_report(resolved, {}, issues, "now")
        self.assertIn("Landscape 建築數：1", report)
        self.assertIn("Factory", report)


if __name__ == "__main__":
    unittest.main()
