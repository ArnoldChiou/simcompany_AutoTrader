# Import classes
from AutoBuyer import AutoBuyer
from Trade_main import TradeMonitor
import traceback

# Import shared configurations from config.py
from config import (
    PRODUCT_API_URL, TARGET_QUALITY, BUY_API_URL, MAX_BUY_QUANTITY,
    MARKET_HEADERS,
)

def run_auto_buyer():
    print("\n啟動 AutoBuyer 自動購買模式 (僅在觸發條件時才啟動 Selenium)...")
    print(f"目標商品 API: {PRODUCT_API_URL}")
    print(f"目標品質: Q{TARGET_QUALITY}")
    print(f"最大購買數量: {MAX_BUY_QUANTITY if MAX_BUY_QUANTITY is not None else '無限制'}")
    print("-------------------------------------")
    try:
        # 將 Selenium 相關邏輯與主循環交由 AutoBuyer.main_loop 處理
        buyer = AutoBuyer(
            product_api_url=PRODUCT_API_URL,
            target_quality=TARGET_QUALITY,
            buy_api_url=BUY_API_URL,
            max_buy_quantity=MAX_BUY_QUANTITY,
            market_headers=MARKET_HEADERS,
            headers=None,
            cookies=None,
            driver=None
        )
        buyer.main_loop()  # 直接呼叫 AutoBuyer 的主循環，內部自動處理 Selenium 啟動/關閉
    except KeyboardInterrupt:
        print("\n使用者中斷自動購買模式，程式結束。")

def run_trade_monitor():
    print("\n啟動 TradeMonitor 市場監控模式...")
    print(f"目標商品 API: {PRODUCT_API_URL}")
    print(f"目標品質: Q{TARGET_QUALITY}")
    print("-------------------------------------")
    try:
        from config import COOKIES
        monitor = TradeMonitor(
            product_api_url=PRODUCT_API_URL,
            target_quality=TARGET_QUALITY,
            headers=MARKET_HEADERS,
            cookies=COOKIES
        )
        monitor.main_loop()
    except KeyboardInterrupt:
        print("使用者中斷程式。")
    except Exception as e:
        print(f"TradeMonitor 執行時發生未預期的錯誤: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("請選擇要執行的功能：")
    print("1. 自動購買 (AutoBuyer - 使用 Selenium)")
    print("2. 市場監控 (TradeMonitor)")
    mode = input("輸入 1 或 2: ").strip()
    if mode == "1":
        run_auto_buyer()
    elif mode == "2":
        run_trade_monitor()
    else:
        print("輸入錯誤，程式結束。")
