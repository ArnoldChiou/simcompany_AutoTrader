from decimal import Decimal
import unittest
from unittest.mock import patch

from building_profit_advisor import (
    Building,
    MarketQuote,
    Product,
    build_product_rows,
    calculate_unit_gross_profit,
    deduplicate_buildings,
    _quote_from_payload,
    _production_building_codes,
    recommend_best_product,
    products_for_building,
    render_report,
)


class BuildingProfitAdvisorTests(unittest.TestCase):
    def test_market_quote_uses_q0_daily_vwap_instead_of_latest_trade(self):
        quote = _quote_from_payload({
            "resource": {
                "resourceName": "Widget",
                "summariesByQuality": [{
                    "quality": 0,
                    "price": 999,
                    "timestamp": "2026-10-12T01:00:00Z",
                    "lastDayCandlestick": {"vwap": "12.34", "date": "2026-10-11T00:00:00Z"},
                }],
            }
        })
        self.assertEqual(quote.quality_zero_price, Decimal("12.34"))
        self.assertEqual(quote.timestamp, "2026-10-11T00:00:00Z")
        self.assertEqual(quote.price_source, "daily VWAP")

    def test_market_quote_falls_back_to_latest_trade_when_vwap_is_missing(self):
        quote = _quote_from_payload({
            "resource": {
                "resourceName": "Widget",
                "summariesByQuality": [{
                    "quality": 0,
                    "price": 999,
                    "timestamp": "2026-10-12T01:00:00Z",
                }],
            }
        })
        self.assertEqual(quote.quality_zero_price, Decimal("999"))
        self.assertEqual(quote.timestamp, "2026-10-12T01:00:00Z")
        self.assertEqual(quote.price_source, "latest trade")

    def test_market_quote_without_vwap_or_latest_trade_is_unavailable(self):
        quote = _quote_from_payload({
            "resource": {
                "resourceName": "Widget",
                "summariesByQuality": [{"quality": 0}],
            }
        })
        self.assertIsNone(quote.quality_zero_price)

    def test_product_output_and_recipe_cost_both_use_parsed_q0_daily_vwap(self):
        def quote(resource_id, name, last_trade, vwap):
            return _quote_from_payload({
                "resource": {
                    "resourceId": resource_id,
                    "resourceName": name,
                    "summariesByQuality": [{
                        "quality": 0,
                        "price": last_trade,
                        "lastDayCandlestick": {"vwap": vwap, "date": "2026-10-11T00:00:00Z"},
                    }],
                }
            })

        constants = {
            "10": {"producedAt": "F", "isExchangeTradable": True, "image": "images/resources/widget.png", "producedFrom": {"20": 2}},
            "20": {"producedAt": "I", "isExchangeTradable": True, "image": "images/resources/input.png", "producedFrom": {}},
        }
        rows = build_product_rows(
            "F",
            constants,
            {10: quote(10, "Widget", 999, "5.5"), 20: quote(20, "Input", 999, "1.25")},
        )
        self.assertEqual(rows[0][1].quality_zero_price, Decimal("5.5"))
        self.assertEqual(rows[0][2], Decimal("3.00"))

    def test_product_recipe_cost_uses_latest_trade_when_input_vwap_is_missing(self):
        output = _quote_from_payload({"resource": {"resourceName": "Widget", "summariesByQuality": [{"quality": 0, "price": 999, "lastDayCandlestick": {"vwap": 5.5}}]}})
        input_quote = _quote_from_payload({"resource": {"resourceName": "Input", "summariesByQuality": [{"quality": 0, "price": 1.25}]}})
        constants = {
            "10": {"producedAt": "F", "isExchangeTradable": True, "image": "images/resources/widget.png", "producedFrom": {"20": 2}},
            "20": {"producedAt": "I", "isExchangeTradable": True, "image": "images/resources/input.png", "producedFrom": {}},
        }
        rows = build_product_rows("F", constants, {10: output, 20: input_quote})
        self.assertEqual(input_quote.price_source, "latest trade")
        self.assertEqual(rows[0][2], Decimal("3.00"))

    def test_best_product_for_building_ranks_each_recipe_using_daily_vwap(self):
        class Driver:
            def __init__(self):
                self.visited = []

            def get(self, url):
                self.visited.append(url)

        driver = Driver()
        constants = {
            "10": {"producedAt": "F", "isExchangeTradable": True, "image": "images/resources/plain.png", "producedFrom": {}},
            "11": {"producedAt": "F", "isExchangeTradable": True, "image": "images/resources/processed.png", "producedFrom": {"20": 2}},
            "20": {"producedAt": "X", "isExchangeTradable": True, "image": "images/resources/input.png", "producedFrom": {}},
        }
        quotes = {
            10: MarketQuote("Plain", Decimal("8"), None),
            11: MarketQuote("Processed", Decimal("20"), None),
            20: MarketQuote("Input", Decimal("3"), None),
        }
        with patch("building_profit_advisor._get_json", side_effect=[{"authCompany": {"realmId": 0}}, constants]), \
             patch("building_profit_advisor._production_building_codes", return_value=([Building("/b/123/", "Factory", "F")], [])), \
             patch("building_profit_advisor.fetch_quotes", return_value=quotes) as fetch:
            recommendation = recommend_best_product(driver, "https://www.simcompanies.com/b/123/")
        self.assertEqual(recommendation, ("Processed", Decimal("20"), Decimal("14")))
        self.assertEqual(driver.visited, ["https://www.simcompanies.com/b/123/"])
        fetch.assert_called_once_with({10, 11, 20}, 0)

    def test_completed_product_identifies_building_when_idle_page_has_no_production_heading(self):
        class Driver:
            def get(self, url):
                pass

        constants = {
            "10": {"producedAt": "F", "isExchangeTradable": True, "image": "images/resources/plain.png", "producedFrom": {}},
            "11": {"producedAt": "F", "isExchangeTradable": True, "image": "images/resources/processed.png", "producedFrom": {"20": 2}},
            "20": {"producedAt": "X", "isExchangeTradable": True, "image": "images/resources/input.png", "producedFrom": {}},
        }
        quotes = {
            10: MarketQuote("Plain", Decimal("8"), None),
            11: MarketQuote("Processed", Decimal("20"), None),
            20: MarketQuote("Input", Decimal("3"), None),
        }
        with patch("building_profit_advisor._get_json", side_effect=[{"authCompany": {"realmId": 0}}, constants]), \
             patch("building_profit_advisor._production_building_codes", return_value=([Building("/b/123/", "Factory", None)], ["no active production heading"])), \
             patch("building_profit_advisor.fetch_quotes", return_value=quotes) as fetch:
            recommendation = recommend_best_product(
                Driver(), "https://www.simcompanies.com/b/123/", completed_product_name="Processed"
            )
        self.assertEqual(recommendation, ("Processed", Decimal("20"), Decimal("14")))
        fetch.assert_called_once_with({10, 11, 20}, 0)

    def test_best_product_rejects_non_simcompanies_urls(self):
        with self.assertRaises(ValueError):
            recommend_best_product(object(), "https://example.com/b/123/")

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
            "G": [(Product(11, "Glass", {}, True), MarketQuote("Glass", Decimal("12"), None, "latest trade"), Decimal("12"))],
        }
        report = render_report(buildings, rows, [], "now")
        self.assertIn("Steel", report)
        self.assertIn("Glass", report)
        self.assertIn("Q0 日 VWAP", report)
        self.assertIn("Q0 最新成交價", report)
        self.assertIn("Factory（生產類型 F）", report)
        self.assertIn("Factory（生產類型 G）", report)

    def test_report_does_not_label_unavailable_quote_as_vwap(self):
        building = Building("/b/101/", "Factory", "F")
        row = (
            Product(10, "Widget", {}, True),
            MarketQuote("Widget", None, None, "unavailable"),
            None,
        )
        report = render_report([building], {"F": [row]}, [], "now")
        self.assertIn("Q0 報價 無報價", report)
        self.assertNotIn("Q0 日 VWAP 無報價", report)

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
