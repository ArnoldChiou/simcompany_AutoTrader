import requests
import time
import traceback
import json
from urllib.parse import urlparse
# Import shared configurations
from config import (
    PRODUCT_API_URL, TARGET_QUALITY, MAX_BUY_QUANTITY,
    MARKET_HEADERS, COOKIES, CASH_API_URL, 
    BUY_THRESHOLD_PERCENTAGE, DEFAULT_CHECK_INTERVAL_SECONDS,
    PURCHASE_WAIT_MULTIPLIER, MARKET_REQUEST_TIMEOUT as REQUEST_TIMEOUT,
    BUY_REQUEST_TIMEOUT, MONEY_REQUEST_TIMEOUT
)
from market_utils import get_market_data

# --- Selenium Imports ---
from selenium.webdriver.remote.webdriver import WebDriver # For type hinting
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

class AutoBuyer:
    # --- Modified __init__ to accept WebDriver ---
    def __init__(self, product_api_url, target_quality, buy_api_url, max_buy_quantity, market_headers, headers, cookies, driver: WebDriver): # Added driver parameter
        self.PRODUCT_API_URL = product_api_url
        self.TARGET_QUALITY = target_quality
        # BUY_API_URL might not be needed if only using Selenium for buying
        # self.BUY_API_URL = buy_api_url
        self.MAX_BUY_QUANTITY = max_buy_quantity if max_buy_quantity is not None else float('inf') # Use infinity if None
        self.MARKET_HEADERS = market_headers
        # HEADERS and COOKIES might not be needed for Selenium buy action
        # self.HEADERS = headers
        # self.COOKIES = cookies
        self.session = requests.Session() # Keep requests session for market data fetching
        self.session.headers.update(self.MARKET_HEADERS)
        # self.session.cookies.update(self.COOKIES) # Cookies handled by Selenium driver now
        self.RESOURCE_ID = self._extract_resource_id(product_api_url)
        if self.RESOURCE_ID is None:
            print(f"錯誤：無法從 URL {product_api_url} 解析資源 ID。")
            raise ValueError("無效的產品 API URL，無法解析資源 ID。")
        # --- Store WebDriver instance ---
        self.driver = driver
        # --- Store the market page URL (You might need to get this from config or construct it) ---
        # Example: Constructing market URL (adjust based on actual URL structure)
        # url_parts = urlparse(product_api_url)
        # self.MARKET_PAGE_URL = f"{url_parts.scheme}://{url_parts.netloc}/market/{self.RESOURCE_ID}"
        # Or define it directly if it's constant for the resource
        self.MARKET_PAGE_URL = f"https://www.simcompanies.com/market/resource/{self.RESOURCE_ID}" # Adjust this URL structure if needed!
        print(f"將使用 Selenium 在此頁面購買: {self.MARKET_PAGE_URL}")


    def _extract_resource_id(self, url):
        """從產品 API URL 解析資源 ID"""
        try:
            path_parts = urlparse(url).path.strip('/').split('/')
            # Expected format: /api/v3/market/{exchange_id}/{resource_id}/
            if len(path_parts) >= 4 and path_parts[0] == 'api' and path_parts[2] == 'market':
                return int(path_parts[4])
        except (ValueError, IndexError) as e:
            print(f"解析資源 ID 時出錯 ({url}): {e}")
        return None

    def get_market_data(self):
        return get_market_data(
            self.session,
            self.PRODUCT_API_URL,
            self.TARGET_QUALITY,
            timeout=REQUEST_TIMEOUT,
            return_order_detail=True
        )

    # --- Rewritten trigger_buy_action using Selenium ---
    def trigger_buy_action(self, order_id, price, quantity_available, quality):
        print(f"===========觸發 Selenium 購買條件===========")
        print(f"準備使用 Selenium 購買 Q{quality} 商品 (資源 ID: {self.RESOURCE_ID})")
        print(f"訂單 ID: {order_id} (注意：Selenium 可能不直接使用 ID，而是根據價格/位置)")
        print(f"價格: ${price:.3f}")
        print(f"可用數量: {quantity_available}")

        buy_quantity = min(quantity_available, self.MAX_BUY_QUANTITY)

        if buy_quantity <= 0:
            print("錯誤：計算出的購買數量為 0 或更少，取消購買。")
            return False

        print(f"嘗試購買數量: {buy_quantity}")
        print(f"目標頁面: {self.MARKET_PAGE_URL}")

        try:
            # 1. Navigate to the market page (optional, if driver might be elsewhere)
            if self.driver.current_url != self.MARKET_PAGE_URL:
                print(f"導航至市場頁面: {self.MARKET_PAGE_URL}")
                self.driver.get(self.MARKET_PAGE_URL)
                # 直接等待數量輸入框出現，避免等待不存在的 market-item
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="quantity"]'))
                )
            else:
                print("驅動程式已在目標市場頁面，無需導航。")
                # 可選：刷新頁面
                self.driver.refresh()
                WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="quantity"]')))

            # 找到下方的數量輸入框
            wait = WebDriverWait(self.driver, 10)
            quantity_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="quantity"]')))
            quantity_input.click()  # 聚焦
            quantity_input.clear()
            quantity_input.send_keys(str(buy_quantity))
            time.sleep(0.3)  # 等待前端反應
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

            # 找到 Buy 按鈕並等待其啟用（enabled）再點擊
            buy_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.btn.btn-primary')))
            # 確保按鈕已啟用（不是 disabled）
            for _ in range(10):
                if buy_button.is_enabled():
                    break
                time.sleep(0.5)
            else:
                print("XXX Buy 按鈕持續為 disabled，無法點擊。 XXX")
                print(f"===================================")
                return False
            buy_button.click()

            # 5. Wait for confirmation/check for errors (Optional but recommended)
            #    Example: Wait for a success message or for the order row to disappear
            try:
                # Example: Wait for the original order row to become stale (disappear/change)
                # Locate the order row element before waiting for it to become stale
                #order_row = wait.until(EC.presence_of_element_located((By.XPATH, f"//div[contains(@data-order-id, '{order_id}')]")))
                #wait.until(EC.staleness_of(order_row))
                print(">>> Selenium 購買操作似乎成功 (訂單元素已消失/改變) <<<")
                # --- 新增：寫入成功交易 log ---
                try:
                    with open('successful_trade', 'a', encoding='utf-8') as f:
                        import datetime
                        f.write(f"{datetime.datetime.now().isoformat()} | 資源ID:{self.RESOURCE_ID} | 訂單ID:{order_id} | 價格:{price} | 數量:{buy_quantity} | 品質:{quality}\n")
                except Exception as log_err:
                    print(f"[Log] 寫入 successful_trade 檔案失敗: {log_err}")
                print(f"===================================")
                return True
            except TimeoutException:
                # Example: Check for an error message
                try:
                    error_element_xpath = "//div[contains(@class, 'error-message') or contains(@class, 'alert-danger')]" # Adjust selector
                    error_message = self.driver.find_element(By.XPATH, error_element_xpath).text
                    print(f"XXX Selenium 購買失敗：檢測到錯誤訊息: {error_message} XXX")
                except NoSuchElementException:
                    print("XXX Selenium 購買超時：未檢測到成功標誌，也未找到明確的錯誤訊息。 XXX")
                print(f"===================================")
                return False

        except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
            print(f"XXX Selenium 購買失敗：尋找元素或操作時出錯: {type(e).__name__} XXX")
            print(f"錯誤訊息: {e}")
            # Consider taking a screenshot for debugging
            # timestamp = time.strftime("%Y%m%d-%H%M%S")
            # self.driver.save_screenshot(f"selenium_error_{timestamp}.png")
            # print(f"已儲存錯誤截圖: selenium_error_{timestamp}.png")
            print(f"===================================")
            return False
        except Exception as e:
            print(f"XXX Selenium 購買失敗：執行購買時發生不可預期的錯誤:")
            traceback.print_exc()
            # Consider taking a screenshot
            # timestamp = time.strftime("%Y%m%d-%H%M%S")
            # self.driver.save_screenshot(f"selenium_error_{timestamp}.png")
            # print(f"已儲存錯誤截圖: selenium_error_{timestamp}.png")
            print(f"===================================")
            return False

    def get_current_money(self):
        url = CASH_API_URL # Use constant from config
        try:
            response = self.session.get(url, timeout=MONEY_REQUEST_TIMEOUT) # Use constant from config
            response.raise_for_status()
            data = response.json()
            money = data.get("money")
            if money is not None:
                print(f"取得帳戶現金: {money}")
                return money
            else:
                print("警告：API 回應中未找到 'money' 欄位。")
                return None
        except requests.exceptions.Timeout:
            print(f"取得帳戶現金時請求超時 ({url})。")
            return None
        except requests.exceptions.RequestException as e:
            print(f"取得帳戶現金時發生請求錯誤 ({url}): {e}")
            return None
        except json.JSONDecodeError:
            print(f"取得帳戶現金時解析 JSON 失敗 ({url})。")
            return None
        except Exception as e:
            print(f"取得帳戶現金時發生不可預期的錯誤:")
            traceback.print_exc()
            return None

    # --- main_loop rewritten to include Selenium driver management ---
    def main_loop(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service as ChromeService
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.common.exceptions import WebDriverException
        while True:
            purchase_attempted_in_cycle = False
            print("\n" + "=" * 10 + f" 開始新一輪檢查 (目標 Q{self.TARGET_QUALITY}) " + "=" * 10)

            market_data = self.get_market_data() # Still uses requests

            if market_data and 'lowest_order' in market_data and 'second_lowest_price' in market_data:
                lowest_order = market_data['lowest_order']
                lowest_price = lowest_order['price']
                second_lowest_price = market_data['second_lowest_price']

                buy_threshold_price = second_lowest_price * BUY_THRESHOLD_PERCENTAGE
                print(f"計算閾值: 次低價 ${second_lowest_price:.3f} 的 {BUY_THRESHOLD_PERCENTAGE*100}% = ${buy_threshold_price:.3f}")

                if lowest_price < buy_threshold_price:
                    print(f"***> 條件滿足! 最低價 ${lowest_price:.3f} < 閾值 ${buy_threshold_price:.3f}")
                    # 僅在需要時啟動 Selenium
                    options = webdriver.ChromeOptions()
                    options.add_argument("user-data-dir=C:\\Users\\arrno\\AppData\\Local\\Google\\Chrome\\simauto2")
                    options.add_argument("--profile-directory=Default")
                    options.add_argument("--remote-debugging-port=9222")
                    driver = None
                    try:
                        service = ChromeService(ChromeDriverManager().install())
                        driver = webdriver.Chrome(service=service, options=options)
                        self.driver = driver
                        success = self.trigger_buy_action(
                            order_id=lowest_order['id'],
                            price=lowest_price,
                            quantity_available=lowest_order['quantity'],
                            quality=self.TARGET_QUALITY
                        )
                        purchase_attempted_in_cycle = True
                        if success:
                            print("Selenium 購買操作完成，將等待下一個檢查週期。")
                        else:
                            print("Selenium 購買操作失敗或未執行，將等待下一個檢查週期。")
                    except WebDriverException as e:
                        print(f"啟動 WebDriver 失敗: {e}")
                    finally:
                        if driver:
                            print("正在關閉 Selenium WebDriver...")
                            driver.quit()
                            print("WebDriver 已關閉。")
                        self.driver = None
                else:
                    print(f"---> 條件未滿足。最低價 ${lowest_price:.3f} >= 閾值 ${buy_threshold_price:.3f}")

            elif market_data and 'lowest_order' in market_data:
                lowest_order = market_data['lowest_order']
                print(f"僅找到一個價格水平 (最低價訂單 ID:{lowest_order['id']}, ${lowest_order['price']:.3f}, {lowest_order['quantity']}件)，無法比較，跳過觸發檢查。")
            else:
                print("本次檢查未能獲取足夠的市場數據 (最低價訂單和次低價)，稍後重試。")

            wait_modifier = PURCHASE_WAIT_MULTIPLIER if purchase_attempted_in_cycle else 1
            check_interval_seconds = DEFAULT_CHECK_INTERVAL_SECONDS * wait_modifier
            print(f"檢查完成，休眠 {check_interval_seconds:.0f} 秒...")
            time.sleep(check_interval_seconds)