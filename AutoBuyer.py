import requests
import time
import traceback
import json
from urllib.parse import urlparse
# Import shared configurations
from config import (
    MARKET_HEADERS, COOKIES, CASH_API_URL,
    BUY_THRESHOLD_PERCENTAGE, DEFAULT_CHECK_INTERVAL_SECONDS,
    PURCHASE_WAIT_MULTIPLIER, MARKET_REQUEST_TIMEOUT as REQUEST_TIMEOUT,
    MONEY_REQUEST_TIMEOUT
)
from market_utils import get_market_data, get_current_money

# --- Selenium Imports ---
from selenium.webdriver.remote.webdriver import WebDriver # For type hinting
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException

from dotenv import load_dotenv
import os

load_dotenv()

class AutoBuyer:
    # --- Modified __init__ to accept target_products dictionary ---
    def __init__(self, target_products, max_buy_quantity, market_headers, headers, cookies, driver: WebDriver): # Removed product_api_url, target_quality
        self.TARGET_PRODUCTS = target_products # Store the dictionary
        self.MAX_BUY_QUANTITY = max_buy_quantity # Store the dictionary instead of a single value
        self.MARKET_HEADERS = market_headers
        self.session = requests.Session() # Keep requests session for market data fetching
        self.session.headers.update(self.MARKET_HEADERS)
        self.driver = driver # This will be None initially, set in main_loop

    def _extract_resource_id(self, url):
        """從產品 API URL 解析資源 ID"""
        try:
            path_parts = urlparse(url).path.strip('/').split('/')
            if len(path_parts) >= 4 and path_parts[0] == 'api' and path_parts[2] == 'market':
                return int(path_parts[4])
        except (ValueError, IndexError) as e:
            print(f"解析資源 ID 時出錯 ({url}): {e}")
        return None

    # --- Modified get_market_data to accept product details ---
    def get_market_data(self, product_name, product_info):
        temp_session = requests.Session()
        temp_session.headers.update(self.MARKET_HEADERS)
        print(f"--- 開始處理 {product_name} (Q{product_info['quality']}) 市場數據 ---")
        return get_market_data(
            temp_session,
            product_info['url'], # Use URL from product_info
            product_info['quality'], # Use quality from product_info
            timeout=REQUEST_TIMEOUT,
            return_order_detail=True
        )

    # --- Modified trigger_buy_action to accept product details ---
    def trigger_buy_action(self, product_name, product_info, order_id, price, quantity_available):
        if not self.driver:
            print("XXX Selenium 購買失敗：WebDriver 實例無效。 XXX")
            return False

        resource_id = self._extract_resource_id(product_info['url'])
        if resource_id is None:
            print(f"XXX Selenium 購買失敗：無法從 {product_info['url']} 解析 {product_name} 的資源 ID。 XXX")
            return False
        market_page_url = f"https://www.simcompanies.com/market/resource/{resource_id}/"
        target_quality = product_info['quality'] # Get quality for logging/logic

        print(f"===========觸發 Selenium 購買條件 ({product_name}) ===========")
        print(f"準備使用 Selenium 購買 {product_name} (Q{target_quality}) 商品 (資源 ID: {resource_id})")
        print(f"訂單 ID: {order_id} (注意：Selenium 可能不直接使用 ID，而是根據價格/位置)")
        print(f"價格: ${price:.3f}")
        print(f"可用數量: {quantity_available}")

        buy_quantity = min(quantity_available, self.MAX_BUY_QUANTITY.get(product_name, float('inf'))) # Use product-specific max quantity

        if buy_quantity <= 0:
            print("錯誤：計算出的購買數量為 0 或更少，取消購買。")
            return False

        print(f"嘗試購買數量: {buy_quantity}")

        try:
            if self.driver.current_url != market_page_url:
                print(f"警告：目前不在目標市場頁面 ({product_name})，嘗試導航至: {market_page_url}")
                self.driver.get(market_page_url)
                print("等待數量輸入框可見且可點擊...")
                WebDriverWait(self.driver, 20).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="quantity"]'))
                )
                print("數量輸入框已找到。")

            wait = WebDriverWait(self.driver, 15)
            quantity_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="quantity"]')))
            quantity_input.click()
            quantity_input.clear()
            quantity_input.send_keys(str(buy_quantity))
            time.sleep(0.3)
            actual_value = quantity_input.get_attribute('value')
            if str(actual_value) != str(buy_quantity):
                print(f"send_keys 無效，改用 JS 設值...")
                self.driver.execute_script(
                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true})); arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    quantity_input, str(buy_quantity)
                )
                time.sleep(0.3)
                actual_value = quantity_input.get_attribute('value')
            if str(actual_value) != str(buy_quantity):
                print(f"警告：數量欄位填入失敗，實際值為 {actual_value}")
            else:
                print(f"已成功填入數量：{actual_value}")

            buy_button_selector = 'button.btn.btn-primary'
            buy_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, buy_button_selector)))

            is_button_enabled = False
            for _ in range(10):
                if buy_button.is_enabled():
                    is_button_enabled = True
                    break
                time.sleep(0.5)

            if not is_button_enabled:
                print("XXX Buy 按鈕持續為 disabled，無法點擊。可能是餘額不足或數量無效。 XXX")
                print(f"===================================")
                return False

            print("點擊購買按鈕...")
            buy_button.click()

            try:
                print("購買按鈕已點擊，等待短暫時間...")
                time.sleep(3)
                print(f">>> Selenium 購買操作 ({product_name}) 已執行 (未檢測到立即錯誤) <<<")

                try:
                    with open('successful_trade.txt', 'a', encoding='utf-8') as f:
                        import datetime
                        f.write(f"{datetime.datetime.now().isoformat()} | 商品:{product_name} | 資源ID:{resource_id} | 訂單ID:{order_id} | 價格:{price} | 數量:{buy_quantity} | 品質:{target_quality}\n") # Added product_name
                except Exception as log_err:
                    print(f"[Log] 寫入 successful_trade 檔案失敗: {log_err}")
                print(f"===================================")
                return True

            except TimeoutException:
                try:
                    error_element_xpath = "//div[contains(@class, 'error-message') or contains(@class, 'alert-danger') or contains(@class, 'alert-warning')]"
                    error_message = self.driver.find_element(By.XPATH, error_element_xpath).text
                    print(f"XXX Selenium 購買失敗 ({product_name})：檢測到錯誤/警告訊息: {error_message} XXX")
                except NoSuchElementException:
                    print(f"XXX Selenium 購買超時 ({product_name})：未檢測到成功或錯誤標誌。 XXX")
                print(f"===================================")
                return False

        except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
            print(f"XXX Selenium 購買失敗 ({product_name})：尋找元素或操作時出錯: {type(e).__name__} XXX")
            print(f"錯誤訊息: {e}")
            print(f"===================================")
            return False
        except Exception as e:
            print(f"XXX Selenium 購買失敗 ({product_name})：執行購買時發生不可預期的錯誤:")
            traceback.print_exc()
            print(f"===================================")
            return False

    def main_loop(self):
        driver = None
        try:
            options = webdriver.ChromeOptions()
            user_data_dir = os.getenv("USER_DATA_DIR")
            if not os.path.exists(user_data_dir):
                raise FileNotFoundError(f"The specified user data directory does not exist: {user_data_dir}")
            print(user_data_dir)
            profile_dir = "Default"
            options.add_argument(f"user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile_dir}")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            while True:
                purchase_attempted_in_cycle = False
                print("\n" + "=" * 15 + " 開始新一輪檢查 (所有目標產品) " + "=" * 15)

                for product_name, product_info in self.TARGET_PRODUCTS.items():
                    print(f"\n--- 檢查產品: {product_name} (Q{product_info['quality']}) ---")

                    market_data = self.get_market_data(product_name, product_info)  # Pass product details

                    if market_data and 'lowest_order' in market_data and 'second_lowest_price' in market_data:
                        lowest_order = market_data['lowest_order']
                        lowest_price = lowest_order['price']
                        second_lowest_price = market_data['second_lowest_price']

                        buy_threshold_price = second_lowest_price * BUY_THRESHOLD_PERCENTAGE
                        print(f"計算閾值 ({product_name}): 次低價 ${second_lowest_price:.3f} 的 {BUY_THRESHOLD_PERCENTAGE*100:.1f}% = ${buy_threshold_price:.3f}")

                        if lowest_price < buy_threshold_price:
                            print(f"***> 條件滿足 ({product_name})! 最低價 ${lowest_price:.3f} < 閾值 ${buy_threshold_price:.3f}")
                            if self.driver is None:
                                print("正在初始化 Selenium WebDriver...")
                                service = ChromeService(ChromeDriverManager().install())
                                driver = webdriver.Chrome(service=service, options=options)
                                self.driver = driver

                            resource_id = self._extract_resource_id(product_info['url'])
                            if resource_id is None:
                                print(f"XXX 無法為 {product_name} 啟動購買，因無法解析資源 ID。跳過此產品。 XXX")
                                continue  # Skip to the next product

                            market_page_url = f"https://www.simcompanies.com/market/resource/{resource_id}/"

                            print(f"導航至市場頁面進行登入檢查 ({product_name}): {market_page_url}")
                            self.driver.get(market_page_url)
                            login_confirmed = False
                            try:
                                login_check_element_selector = 'input[name="quantity"]'
                                print(f"等待登入標誌元素 ({login_check_element_selector}) 可見且可點擊...")
                                WebDriverWait(self.driver, 15).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, login_check_element_selector))
                                )
                                print("登入狀態正常。")
                                login_confirmed = True
                            except TimeoutException:
                                print("\n" + "*"*20)
                                print("警告：未在預期時間內找到登入標誌元素。")
                                print(">>> 您可能需要手動登入 SimCompanies <<<")
                                print("請在已開啟的 Chrome 瀏覽器視窗中，輸入您的帳號和密碼進行登入。")
                                input(">>> 完成登入後，請回到這裡按 Enter 鍵繼續 <<<")
                                print("*"*20 + "\n")
                                print("嘗試重新整理頁面並再次檢查登入狀態...")
                                self.driver.refresh()
                                try:
                                    WebDriverWait(self.driver, 10).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, login_check_element_selector))
                                    )
                                    print("重新整理後確認登入成功。")
                                    login_confirmed = True
                                except TimeoutException:
                                    print("XXX 警告：重新整理後仍無法確認登入狀態。後續購買操作可能失敗。 XXX")

                            if login_confirmed:
                                success = self.trigger_buy_action(  # Pass product details
                                    product_name=product_name,
                                    product_info=product_info,
                                    order_id=lowest_order['id'],
                                    price=lowest_price,
                                    quantity_available=lowest_order['quantity']
                                )
                                purchase_attempted_in_cycle = True  # Mark that an attempt was made in this cycle
                                if success:
                                    print(f"Selenium 購買操作 ({product_name}) 成功完成。")
                                else:
                                    print(f"Selenium 購買操作 ({product_name}) 失敗或未執行。")
                            else:
                                print(f"登入未確認 ({product_name})，跳過本次購買嘗試。")

                        else:
                            print(f"---> 條件未滿足 ({product_name})。最低價 ${lowest_price:.3f} >= 閾值 ${buy_threshold_price:.3f}")

                    elif market_data and 'lowest_order' in market_data:
                        lowest_order = market_data['lowest_order']
                        print(f"僅找到一個價格水平 ({product_name}: 最低價訂單 ID:{lowest_order['id']}, ${lowest_order['price']:.3f}, {lowest_order['quantity']}件)，無法比較，跳過觸發檢查。")
                    else:
                        print(f"本次檢查未能獲取足夠的市場數據 ({product_name}: 最低價訂單和次低價)，稍後重試。")

                    time.sleep(1)  # Optional: Add a small delay between checking different products
                if self.driver:
                    print("購買完成，關閉 WebDriver...")
                    self.driver.quit()
                    print("WebDriver 已關閉。")
                    self.driver = None
                wait_modifier = PURCHASE_WAIT_MULTIPLIER if purchase_attempted_in_cycle else 1
                check_interval_seconds = DEFAULT_CHECK_INTERVAL_SECONDS * wait_modifier
                print(f"\n所有產品檢查完成，休眠 {check_interval_seconds:.0f} 秒...")
                time.sleep(check_interval_seconds)

        except WebDriverException as e:
            print(f"XXX 啟動或操作 WebDriver 時發生錯誤: {type(e).__name__} XXX")
            print(f"錯誤訊息: {e}")
            traceback.print_exc()
        except Exception as e:
            print(f"XXX 執行主循環時發生未預期的錯誤: {type(e).__name__} XXX")
            traceback.print_exc()
        finally:
            if self.driver:
                print("正在關閉 Selenium WebDriver...")
                self.driver.quit()
                print("WebDriver 已關閉。")
                self.driver = None  # Reset driver for the next potential purchase