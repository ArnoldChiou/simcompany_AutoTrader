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
        print(f"--- 開始處理 {product_name} (Q{product_info['quality']}) 市場數據 ---")
        return get_market_data(
            self.session,
            product_info['url'],
            product_info['quality'],
            timeout=REQUEST_TIMEOUT,
            return_order_detail=False
        )

    def trigger_buy_action(self, product_name, product_info, price):
        print(f"===========觸發購買條件 ({product_name})===========")
        print(f"商品 ({product_name} Q{product_info['quality']})")
        print(f"觸發時最低價: ${price:.3f}")
        print("!!! 警告：自動購買操作未執行 (TradeMonitor 模式)，請確認遊戲規則並手動操作 !!!")
        print(f"===================================")

    def main_loop(self):
        while True:
            print("\n" + "=" * 15 + " 開始新一輪檢查 (所有目標產品) " + "=" * 15)

            for product_name, product_info in self.TARGET_PRODUCTS.items():
                print(f"\n--- 檢查產品: {product_name} (Q{product_info['quality']}) ---")
                market_data = self.get_market_data(product_name, product_info)

                if market_data and 'lowest_price' in market_data and 'second_lowest_price' in market_data:
                    lowest_price = market_data['lowest_price']
                    second_lowest_price = market_data['second_lowest_price']

                    buy_threshold_price = second_lowest_price * BUY_THRESHOLD_PERCENTAGE
                    print(f"計算閾值 ({product_name}): 次低價 ${second_lowest_price:.3f} 的 {BUY_THRESHOLD_PERCENTAGE*100}% = ${buy_threshold_price:.3f}")

                    if lowest_price < buy_threshold_price:
                        print(f"***> 條件滿足 ({product_name})! 最低價 ${lowest_price:.3f} < 閾值 ${buy_threshold_price:.3f}")
                        self.trigger_buy_action(product_name, product_info, lowest_price)
                    else:
                        print(f"---> 條件未滿足 ({product_name})。最低價 ${lowest_price:.3f} >= 閾值 ${buy_threshold_price:.3f}")

                elif market_data and 'lowest_price' in market_data:
                    print(f"僅找到一個價格 ({product_name}: 最低價 ${market_data['lowest_price']:.3f})，無法比較，跳過觸發檢查。")
                else:
                    print(f"本次檢查未能獲取足夠的市場數據 ({product_name}: 最低價和次低價)，稍後重試。")

                time.sleep(1)

            check_interval_seconds = DEFAULT_CHECK_INTERVAL_SECONDS
            print(f"\n所有產品檢查完成，休眠 {check_interval_seconds} 秒...")
            time.sleep(check_interval_seconds)