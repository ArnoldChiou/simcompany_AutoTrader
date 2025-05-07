import requests
import time
# Import shared configurations
from config import (
    BUY_THRESHOLD_PERCENTAGE, DEFAULT_CHECK_INTERVAL_SECONDS,
    MARKET_REQUEST_TIMEOUT as REQUEST_TIMEOUT,
    TARGET_PRODUCTS, MARKET_HEADERS, COOKIES
)
from market_utils import get_market_data

class TradeMonitor:
    def __init__(self, target_products, headers, cookies):
        self.TARGET_PRODUCTS = target_products
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.session.cookies.update(cookies)

    def get_market_data(self, product_name, product_info):
        print(f"--- Start processing {product_name} (Q{product_info['quality']}) market data ---")
        return get_market_data(
            self.session,
            product_info['url'],
            product_info['quality'],
            timeout=REQUEST_TIMEOUT,
            return_order_detail=False
        )

    def trigger_buy_action(self, product_name, product_info, price):
        print(f"===========Trigger buy condition ({product_name})===========")
        print(f"Product ({product_name} Q{product_info['quality']})")
        print(f"Lowest price at trigger: ${price:.3f}")
        print("!!! WARNING: Auto-buy operation not executed (TradeMonitor mode), please check game rules and operate manually !!!")
        print(f"===================================")

    def main_loop(self):
        while True:
            print("\n" + "=" * 15 + " Start a new round of checks (all target products) " + "=" * 15)

            for product_name, product_info in self.TARGET_PRODUCTS.items():
                print(f"\n--- Checking product: {product_name} (Q{product_info['quality']}) ---")
                market_data = self.get_market_data(product_name, product_info)

                if market_data and 'lowest_price' in market_data and 'second_lowest_price' in market_data:
                    lowest_price = market_data['lowest_price']
                    second_lowest_price = market_data['second_lowest_price']

                    buy_threshold_price = second_lowest_price * BUY_THRESHOLD_PERCENTAGE
                    print(f"Threshold calculation ({product_name}): Second lowest price ${second_lowest_price:.3f} at {BUY_THRESHOLD_PERCENTAGE*100}% = ${buy_threshold_price:.3f}")

                    if lowest_price < buy_threshold_price:
                        print(f"***> Condition met ({product_name})! Lowest price ${lowest_price:.3f} < threshold ${buy_threshold_price:.3f}")
                        self.trigger_buy_action(product_name, product_info, lowest_price)
                    else:
                        print(f"---> Condition not met ({product_name}). Lowest price ${lowest_price:.3f} >= threshold ${buy_threshold_price:.3f}")

                elif market_data and 'lowest_price' in market_data:
                    print(f"Only one price found ({product_name}: lowest price ${market_data['lowest_price']:.3f}), cannot compare, skipping trigger check.")
                else:
                    print(f"Insufficient market data obtained this check ({product_name}: lowest and second lowest price), will retry later.")

                time.sleep(1)

            check_interval_seconds = DEFAULT_CHECK_INTERVAL_SECONDS
            print(f"\nAll product checks complete, sleeping for {check_interval_seconds} seconds...")
            time.sleep(check_interval_seconds)