# Import classes
from AutoBuyer import AutoBuyer
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

# Import shared configurations from config.py
from config import (
    TARGET_PRODUCTS, MAX_BUY_QUANTITY, # Import TARGET_PRODUCTS
    MARKET_HEADERS # Import MARKET_HEADERS
)

def run_auto_buyer():
    print("\n啟動 AutoBuyer 自動購買模式 (監控所有目標產品)...")
    print(f"目標產品: {list(TARGET_PRODUCTS.keys())}") # Show all target product names
    print(f"最大購買數量: {MAX_BUY_QUANTITY if MAX_BUY_QUANTITY is not None else '無限制'}")
    print("-------------------------------------")
    try:
        buyer = AutoBuyer(
            target_products=TARGET_PRODUCTS, # Pass the dictionary
            max_buy_quantity=MAX_BUY_QUANTITY, # Pass the dictionary instead of a single value
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

def login_to_game():
    print("\n啟動登入功能...")
    try:
        driver = webdriver.Chrome()  # 使用 Chrome 瀏覽器
        driver.get("https://www.simcompanies.com/signin/")  # 替換為遊戲的登入頁面 URL

        print("請在瀏覽器中手動登入遊戲，完成後關閉瀏覽器以繼續...")
        input("按 Enter 確認已完成登入: ")
        print("登入資訊已儲存，您可以繼續使用自動購買功能。")
    except Exception as e:
        print(f"登入過程中發生錯誤: {e}")
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    print("請選擇要執行的功能：")
    print("1. 登入遊戲")
    print("2. 自動購買")
    mode = input("輸入 1 或 2: ").strip()
    if mode == "1":
        login_to_game()
    elif mode == "2":
        run_auto_buyer()
    else:
        print("輸入錯誤，程式結束。")
