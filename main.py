# Import classes
from AutoBuyer import AutoBuyer
from Trade_main import TradeMonitor
import traceback

# Import shared configurations from config.py
from config import (
    TARGET_PRODUCTS, BUY_API_URL, MAX_BUY_QUANTITY, # Import TARGET_PRODUCTS
    MARKET_HEADERS, COOKIES # Import COOKIES
)

def run_auto_buyer():
    print("\n啟動 AutoBuyer 自動購買模式 (監控所有目標產品)...")
    print(f"目標產品: {list(TARGET_PRODUCTS.keys())}") # Show all target product names
    print(f"最大購買數量: {MAX_BUY_QUANTITY if MAX_BUY_QUANTITY is not None else '無限制'}")
    print("-------------------------------------")
    try:
        buyer = AutoBuyer(
            target_products=TARGET_PRODUCTS, # Pass the dictionary
            buy_api_url=BUY_API_URL,
            max_buy_quantity=MAX_BUY_QUANTITY,
            market_headers=MARKET_HEADERS,
            headers=None, # AutoBuyer uses MARKET_HEADERS internally for requests
            cookies=None, # AutoBuyer handles cookies via Selenium profile
            driver=None
        )
        buyer.main_loop()
    except KeyboardInterrupt:
        print("\n使用者中斷自動購買模式，程式結束。")
    except Exception as e:
        print(f"AutoBuyer 執行時發生未預期的錯誤: {e}")
        traceback.print_exc()

def run_trade_monitor():
    print("\n啟動 TradeMonitor 市場監控模式 (監控所有目標產品)...")
    print(f"目標產品: {list(TARGET_PRODUCTS.keys())}") # Show all target product names
    print("-------------------------------------")
    try:
        monitor = TradeMonitor(
            target_products=TARGET_PRODUCTS, # Pass the dictionary
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
