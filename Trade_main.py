import requests
import time
import traceback
import json
# Import shared configurations
from config import (
    PRODUCT_API_URL, TARGET_QUALITY, MARKET_HEADERS as HEADERS, COOKIES,
    BUY_THRESHOLD_PERCENTAGE, DEFAULT_CHECK_INTERVAL_SECONDS,
    MARKET_REQUEST_TIMEOUT as REQUEST_TIMEOUT
)
from market_utils import get_market_data

class TradeMonitor:
    def __init__(self, product_api_url, target_quality, headers, cookies):
        self.PRODUCT_API_URL = product_api_url
        self.TARGET_QUALITY = target_quality
        self.BUY_TRIGGERED = False
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.session.cookies.update(cookies)

    def get_market_data(self):
        return get_market_data(
            self.session,
            self.PRODUCT_API_URL,
            self.TARGET_QUALITY,
            timeout=REQUEST_TIMEOUT,
            return_order_detail=False
        )

    def trigger_buy_action(self, product_id_or_url, price, quality):
        print(f"===========觸發購買條件===========")
        print(f"商品 (Q{quality}): {product_id_or_url}")
        print(f"觸發時最低價: ${price:.3f}")
        print("!!! 警告：自動購買操作未執行 (TradeMonitor 模式)，請確認遊戲規則並手動操作 !!!")
        print(f"===================================")
        self.BUY_TRIGGERED = True

    def main_loop(self):
        while True:
            self.BUY_TRIGGERED = False
            print("\n" + "=" * 10 + f" 開始新一輪檢查 (目標 Q{self.TARGET_QUALITY}) " + "=" * 10)
            market_data = self.get_market_data()

            if market_data and 'lowest_price' in market_data and 'second_lowest_price' in market_data:
                lowest_price = market_data['lowest_price']
                second_lowest_price = market_data['second_lowest_price']

                buy_threshold_price = second_lowest_price * BUY_THRESHOLD_PERCENTAGE
                print(f"計算閾值: 次低價 ${second_lowest_price:.3f} 的 {BUY_THRESHOLD_PERCENTAGE*100}% = ${buy_threshold_price:.3f}")

                if lowest_price < buy_threshold_price:
                    print(f"***> 條件滿足! 最低價 ${lowest_price:.3f} < 閾值 ${buy_threshold_price:.3f}")
                    self.trigger_buy_action(self.PRODUCT_API_URL, lowest_price, self.TARGET_QUALITY)
                else:
                    print(f"---> 條件未滿足。最低價 ${lowest_price:.3f} >= 閾值 ${buy_threshold_price:.3f}")

            elif market_data and 'lowest_price' in market_data:
                print(f"僅找到一個價格 (最低價 ${market_data['lowest_price']:.3f})，無法比較，跳過觸發檢查。")
            else:
                print("本次檢查未能獲取足夠的市場數據 (最低價和次低價)，稍後重試。")

            check_interval_seconds = DEFAULT_CHECK_INTERVAL_SECONDS
            print(f"檢查完成，休眠 {check_interval_seconds} 秒...")
            time.sleep(check_interval_seconds)