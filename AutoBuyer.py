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
        # --- Add market data cache ---
        self._market_data_cache = {}  # key: (product_name, quality), value: (timestamp, data)
        self._market_data_cache_ttl = 60  # seconds, adjust as needed

    def _extract_resource_id(self, url):
        """Parse resource ID from product API URL"""
        try:
            path_parts = urlparse(url).path.strip('/').split('/')
            if len(path_parts) >= 4 and path_parts[0] == 'api' and path_parts[2] == 'market':
                return int(path_parts[4])
        except (ValueError, IndexError) as e:
            print(f"Error parsing resource ID ({url}): {e}")
        return None

    # --- Modified get_market_data to accept product details ---
    def get_market_data(self, product_name, product_info):
        # --- Use cache to reduce web requests ---
        cache_key = (product_name, product_info['quality'])
        now = time.time()
        if cache_key in self._market_data_cache:
            ts, data = self._market_data_cache[cache_key]
            if now - ts < self._market_data_cache_ttl:
                print(f"[CACHE] Using cached market data for {product_name} (Q{product_info['quality']})")
                return data
        temp_session = requests.Session()
        temp_session.headers.update(self.MARKET_HEADERS)
        print(f"--- Start processing {product_name} (Q{product_info['quality']}) market data ---")
        data = get_market_data(
            temp_session,
            product_info['url'], # Use URL from product_info
            product_info['quality'], # Use quality from product_info
            timeout=REQUEST_TIMEOUT,
            return_order_detail=True
        )
        # --- Update cache ---
        self._market_data_cache[cache_key] = (now, data)
        return data

    # --- Modified trigger_buy_action to accept product details ---
    def trigger_buy_action(self, product_name, product_info, order_id, price, quantity_available):
        if not self.driver:
            print("XXX Selenium purchase failed: WebDriver instance is invalid. XXX")
            return False

        resource_id = self._extract_resource_id(product_info['url'])
        if resource_id is None:
            print(f"XXX Selenium purchase failed: Unable to parse resource ID for {product_name} from {product_info['url']}. XXX")
            return False
        market_page_url = f"https://www.simcompanies.com/market/resource/{resource_id}/"
        target_quality = product_info['quality'] # Get quality for logging/logic

        print(f"===========Trigger Selenium buy condition ({product_name}) ===========")
        print(f"Preparing to use Selenium to buy {product_name} (Q{target_quality}) (Resource ID: {resource_id})")
        print(f"Order ID: {order_id} (Note: Selenium may not use ID directly, but by price/position)")
        print(f"Price: ${price:.3f}")
        print(f"Available quantity: {quantity_available}")

        buy_quantity = min(quantity_available, self.MAX_BUY_QUANTITY.get(product_name, float('inf'))) # Use product-specific max quantity

        if buy_quantity <= 0:
            print("Error: Calculated buy quantity is 0 or less, canceling purchase.")
            return False

        print(f"Attempting to buy quantity: {buy_quantity}")

        try:
            if self.driver.current_url != market_page_url:
                print(f"Warning: Not on target market page ({product_name}), navigating to: {market_page_url}")
                self.driver.get(market_page_url)
                print("Waiting for quantity input box to be visible and clickable...")
                WebDriverWait(self.driver, 20).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="quantity"]'))
                )
                print("Quantity input box found.")

            wait = WebDriverWait(self.driver, 15)
            quantity_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="quantity"]')))
            quantity_input.click()
            quantity_input.clear()
            quantity_input.send_keys(str(buy_quantity))
            time.sleep(0.3)
            actual_value = quantity_input.get_attribute('value')
            if str(actual_value) != str(buy_quantity):
                print(f"send_keys ineffective, using JS to set value...")
                self.driver.execute_script(
                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true})); arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    quantity_input, str(buy_quantity)
                )
                time.sleep(0.3)
                actual_value = quantity_input.get_attribute('value')
            if str(actual_value) != str(buy_quantity):
                print(f"Warning: Failed to fill in quantity field, actual value is {actual_value}")
            else:
                print(f"Successfully filled in quantity: {actual_value}")

            buy_button_selector = 'button.btn.btn-primary'
            buy_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, buy_button_selector)))

            is_button_enabled = False
            for _ in range(10):
                if buy_button.is_enabled():
                    is_button_enabled = True
                    break
                time.sleep(0.5)

            if not is_button_enabled:
                print("XXX Buy button remains disabled, cannot click. Possibly insufficient balance or invalid quantity. XXX")
                print(f"===================================")
                return False

            print("Clicking buy button...")
            buy_button.click()

            try:
                print("Buy button clicked, waiting briefly...")
                time.sleep(3)
                print(f">>> Selenium buy operation ({product_name}) executed (no immediate error detected) <<<")

                try:
                    with open('successful_trade.txt', 'a', encoding='utf-8') as f:
                        import datetime
                        f.write(f"{datetime.datetime.now().isoformat()} | Product:{product_name} | ResourceID:{resource_id} | OrderID:{order_id} | Price:{price} | Quantity:{buy_quantity} | Quality:{target_quality}\n") # Added product_name
                except Exception as log_err:
                    print(f"[Log] Failed to write to successful_trade file: {log_err}")
                print(f"===================================")
                return True

            except TimeoutException:
                try:
                    error_element_xpath = "//div[contains(@class, 'error-message') or contains(@class, 'alert-danger') or contains(@class, 'alert-warning')]"
                    error_message = self.driver.find_element(By.XPATH, error_element_xpath).text
                    print(f"XXX Selenium purchase failed ({product_name}): Detected error/warning message: {error_message} XXX")
                except NoSuchElementException:
                    print(f"XXX Selenium purchase timeout ({product_name}): No success or error indicator detected. XXX")
                print(f"===================================")
                return False

        except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
            print(f"XXX Selenium purchase failed ({product_name}): Error finding element or during operation: {type(e).__name__} XXX")
            print(f"Error message: {e}")
            print(f"===================================")
            return False
        except Exception as e:
            print(f"XXX Selenium purchase failed ({product_name}): Unexpected error during purchase:")
            traceback.print_exc()
            print(f"===================================")
            return False

    def main_loop(self):
        driver = None
        try:
            options = webdriver.ChromeOptions()
            user_data_dir = os.getenv("USER_DATA_DIR")
            if not user_data_dir:
                raise ValueError("USER_DATA_DIR environment variable not set or empty in .env file, please check configuration.")
            if not os.path.exists(user_data_dir):
                raise FileNotFoundError(f"The specified user data directory does not exist: {user_data_dir}")
            print(user_data_dir)
            profile_dir = "Default"
            options.add_argument(f"user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile_dir}")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            while True:
                purchase_attempted_in_cycle = False
                api_error_in_cycle = False  # New flag for API errors
                print("\n" + "=" * 15 + " Starting new check cycle (all target products) " + "=" * 15)

                # --- Shuffle product order to avoid pattern ---
                import random
                product_items = list(self.TARGET_PRODUCTS.items())
                random.shuffle(product_items)

                for product_name, product_info in product_items:
                    if api_error_in_cycle:  # If an error occurred, skip remaining products for this cycle
                        print(f"Skipping remaining products in this cycle due to an earlier API error.")
                        break

                    print(f"\n--- Checking product: {product_name} (Q{product_info['quality']}) ---")

                    market_data = self.get_market_data(product_name, product_info)

                    if market_data is None:
                        # This indicates a failure in get_market_data, e.g. 429 error.
                        # market_utils.get_market_data is expected to print the specific error.
                        print(f"Failed to fetch market data for {product_name}. Assuming API issue (e.g., rate limit). Backing off for this cycle.")
                        api_error_in_cycle = True
                        break  # Exit the product loop immediately to enforce backoff

                    # Proceed if market_data is not None
                    if 'lowest_order' in market_data and 'second_lowest_price' in market_data:
                        lowest_order = market_data['lowest_order']
                        lowest_price = lowest_order['price']
                        second_lowest_price = market_data['second_lowest_price']

                        buy_threshold_price = second_lowest_price * BUY_THRESHOLD_PERCENTAGE
                        print(f"Threshold calculation ({product_name}): 2nd lowest price ${second_lowest_price:.3f} at {BUY_THRESHOLD_PERCENTAGE*100:.1f}% = ${buy_threshold_price:.3f}")

                        if lowest_price < buy_threshold_price:
                            print(f"***> Condition met ({product_name})! Lowest price ${lowest_price:.3f} < threshold ${buy_threshold_price:.3f}")
                            if self.driver is None:
                                print("Initializing Selenium WebDriver...")
                                service = ChromeService(ChromeDriverManager().install())
                                self.driver = webdriver.Chrome(service=service, options=options)

                            resource_id = self._extract_resource_id(product_info['url'])
                            if resource_id is None:
                                print(f"XXX Unable to start purchase for {product_name}, could not parse resource ID. Skipping this product. XXX")
                                continue

                            market_page_url = f"https://www.simcompanies.com/market/resource/{resource_id}/"

                            print(f"Navigating to market page for login check ({product_name}): {market_page_url}")
                            self.driver.get(market_page_url)
                            login_confirmed = False
                            try:
                                login_check_element_selector = 'input[name="quantity"]'
                                print(f"Waiting for login indicator element ({login_check_element_selector}) to be visible and clickable...")
                                # Robust wait: retry if StaleElementReferenceException occurs
                                wait = WebDriverWait(self.driver, 20)
                                for attempt in range(3):
                                    try:
                                        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, login_check_element_selector)))
                                        print("Login status OK.")
                                        login_confirmed = True
                                        break
                                    except StaleElementReferenceException:
                                        print(f"StaleElementReferenceException caught while waiting for login element, retrying ({attempt+1}/3)...")
                                        time.sleep(1)
                                        continue
                                else:
                                    raise TimeoutException("Failed to get a stable reference to the login element after retries.")
                            except TimeoutException:
                                print("\n" + "*"*20)
                                print("Warning: Login indicator element not found within expected time.")
                                print(">>> You may need to log in to SimCompanies manually <<<")
                                print("Please enter your account and password in the opened Chrome browser window to log in.")
                                input(">>> After logging in, return here and press Enter to continue <<<")
                                print("*"*20 + "\n")
                                print("Trying to refresh the page and check login status again...")
                                self.driver.refresh()
                                try:
                                    wait = WebDriverWait(self.driver, 15)
                                    for attempt in range(3):
                                        try:
                                            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, login_check_element_selector)))
                                            print("Login confirmed after refresh.")
                                            login_confirmed = True
                                            break
                                        except StaleElementReferenceException:
                                            print(f"StaleElementReferenceException caught after refresh, retrying ({attempt+1}/3)...")
                                            time.sleep(1)
                                            continue
                                    else:
                                        print("XXX Warning: Still unable to confirm login status after refresh. Subsequent purchase may fail. XXX")
                                except TimeoutException:
                                    print("XXX Warning: Still unable to confirm login status after refresh. Subsequent purchase may fail. XXX")

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
                                    print(f"Selenium buy operation ({product_name}) completed successfully.")
                                else:
                                    print(f"Selenium buy operation ({product_name}) failed or not executed.")
                            else:
                                print(f"Login not confirmed ({product_name}), skipping this purchase attempt.")

                        else:
                            print(f"---> Condition not met ({product_name}). Lowest price ${lowest_price:.3f} >= threshold ${buy_threshold_price:.3f}")

                    elif 'lowest_order' in market_data:  # market_data is not None here
                        lowest_order = market_data['lowest_order']
                        print(f"Only one price level found ({product_name}: lowest order ID:{lowest_order['id']}, ${lowest_order['price']:.3f}, {lowest_order['quantity']} units), cannot compare, skipping trigger check.")
                    else:  # market_data is not None, but doesn't have expected keys
                        print(f"Not enough market data obtained this check ({product_name}: missing lowest order and/or second lowest price), will retry later.")
                        # If market_data is incomplete (e.g. after a 429 error was logged by a utility),
                        # treat this as an API error to trigger backoff.
                        print(f"Assuming API issue for {product_name} due to incomplete data. Backing off for this cycle.")
                        api_error_in_cycle = True
                        break  # Exit the product loop immediately to enforce backoff

                    if not api_error_in_cycle:  # Only sleep if no API error caused an early break
                        # --- Add random jitter between product checks (2-8s) ---
                        sleep_time = random.uniform(2, 8)
                        print(f"Sleeping {sleep_time:.2f} seconds before next product check...")
                        time.sleep(sleep_time)

                if self.driver:  # If WebDriver was initialized in this cycle
                    print("\nEnsuring WebDriver is closed at the end of the cycle...")
                    try:
                        self.driver.quit()
                        print("WebDriver closed successfully.")
                    except Exception as e:  # Catch more general exceptions during quit
                        print(f"Error closing WebDriver: {type(e).__name__} - {e}")
                    finally:
                        self.driver = None  # Important to reset for the next cycle

                # --- Increase and randomize sleep duration between cycles ---
                min_sleep = DEFAULT_CHECK_INTERVAL_SECONDS * 0.8
                max_sleep = DEFAULT_CHECK_INTERVAL_SECONDS * 2.5
                sleep_duration_seconds = random.uniform(min_sleep, max_sleep)

                if api_error_in_cycle:
                    # Override with a longer, fixed backoff if an API error (e.g., 429) occurred
                    sleep_duration_seconds = max(120.0, sleep_duration_seconds)  # At least 2 minutes backoff
                    print(f"\nAPI error occurred in this cycle. Applying a fixed backoff delay of {sleep_duration_seconds:.2f} seconds.")
                else:
                    print(f"\nAll product checks complete for this cycle, sleeping for {sleep_duration_seconds:.2f} seconds...")

                time.sleep(sleep_duration_seconds)

        except WebDriverException as e:
            print(f"XXX Error occurred while starting or operating WebDriver: {type(e).__name__} XXX")
            print(f"Error message: {e}")
            traceback.print_exc()
        except Exception as e:
            print(f"XXX Unexpected error occurred during main loop: {type(e).__name__} XXX")
            traceback.print_exc()
        finally:
            if self.driver:
                print("Closing Selenium WebDriver due to an exception or loop termination in finally block...")
                try:
                    self.driver.quit()
                    print("WebDriver closed successfully in finally block.")
                except Exception as e:  # Catch more general exceptions during quit
                    print(f"Error closing WebDriver in finally block: {type(e).__name__} - {e}")
                finally:
                    self.driver = None  # Ensure it's reset