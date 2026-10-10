import os
import time
import datetime
import re
import traceback
import logging
from logging.handlers import RotatingFileHandler
import random
import json
from dateutil import parser
from dotenv import load_dotenv


from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
    NoSuchWindowException
)

from driver_utils import initialize_driver
from email_utils import send_email_notify
from telegram_utils import send_telegram_notify
from config import POWER_PLANT_PATHS
from retail_profit_advisor import RetailProfitAdvisor

# --- Logging Setup ---
def setup_logger(name, log_filename):
    log_path = os.path.join('record', log_filename)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger

# --- Constants ---
BASE_URL = "https://www.simcompanies.com"
DEFAULT_RETRY_DELAY = 60  # seconds
LONG_RETRY_DELAY = 100 # seconds 
LOGIN_CHECK_TIMEOUT = 20 # seconds
ACTIVITY_PANEL_WAIT = 8 # seconds
BUILDING_CONTENT_WAIT = 20 # seconds
MISSING_CONFIRMATIONS_REQUIRED = 2
CONSTRUCTION_CHECK_BUFFER = 60 # seconds
PRODUCTION_CHECK_BUFFER = 60 # seconds
MANUAL_ACTIVITY_RECHECK_SECONDS = 3600
DUE_ACTIVITY_RECHECK_SECONDS = 60
REBUILD_DELAY = 60 # seconds

# --- Ensure 'record' directory exists ---
if not os.path.exists('record'):
    os.makedirs('record')

# --- Base Monitor Class ---
class BaseMonitor:
    """Base class for monitoring tasks."""
    def __init__(self, name, base_url=BASE_URL, logger=None, user_data_dir=None):
        self.name = name
        self.base_url = base_url
        self.driver = None
        self.logger = logger
        self.user_data_dir = user_data_dir
        self._login_alert_sent = False

    def _login_state(self):
        """Return authenticated, login_required, or None while the SPA is loading."""
        try:
            login_elements = self.driver.find_elements(
                By.XPATH,
                "//form[contains(@action, '/login') or contains(@action, '/signin')] | "
                "//a[contains(@href, '/signin') or contains(@href, '/login')] | "
                "//button[contains(translate(normalize-space(.), 'LOGIN', 'login'), 'login') and @type='submit']"
            )
            if any(element.is_displayed() for element in login_elements):
                return "login_required"

            authenticated_elements = self.driver.find_elements(
                By.XPATH,
                "//a[contains(@href,'/landscape')] | //a[contains(@href,'/logout')]"
            )
            if any(element.is_displayed() for element in authenticated_elements):
                return "authenticated"
            return None
        except Exception as e:
            self.logger.warning(f"[{self.name}] Error checking login status: {e}")
            return None

    def _is_logged_in(self):
        """Require a positive authenticated-page indicator."""
        return self._login_state() == "authenticated"

    def _wait_for_login_state(self):
        try:
            WebDriverWait(self.driver, LOGIN_CHECK_TIMEOUT, poll_frequency=0.5).until(
                lambda _driver: self._is_logged_in()
            )
            return "authenticated"
        except TimeoutException:
            return self._login_state() or "unknown"

    def _notify_login_problem(self, state):
        if self._login_alert_sent:
            return
        current_url = ""
        try:
            current_url = self.driver.current_url
        except Exception:
            pass
        reason = "登入已失效" if state == "login_required" else "頁面載入逾時，無法確認登入狀態"
        message = (
            "⚠️ SimCompanies 監控暫停！\n"
            f"監控：{self.name}\n"
            f"原因：{reason}\n"
            f"網址：{current_url or self.base_url}\n"
            "請開啟 SimCompanies 確認登入；程式會自動重試。"
        )
        if send_telegram_notify(message):
            self._login_alert_sent = True

    def _initialize_driver(self):
        self.logger.info(f"[{self.name}] Initializing WebDriver with profile: {self.user_data_dir or 'default'}...")
        try:
            self.driver = initialize_driver(user_data_dir=self.user_data_dir)

            if self.driver:
                self.logger.info(f"[{self.name}] WebDriver initialized for profile: {self.user_data_dir or 'default'}.")
                self.logger.info(f"[{self.name}] Navigating to {self.base_url} for initial login check.")
                try:
                    self.driver.get(self.base_url)
                    login_state = self._wait_for_login_state()
                    if login_state == "authenticated":
                        self._login_alert_sent = False
                        self.logger.info(f"[{self.name}] Detected already logged in, proceeding automatically.")
                        return True

                    self.logger.warning(
                        f"[{self.name}] Login check did not authenticate (state: {login_state}). "
                        f"Retrying in {LONG_RETRY_DELAY} seconds."
                    )
                    self._notify_login_problem(login_state)
                    self._quit_driver()
                    return False
                except WebDriverException as e_nav:
                    self.logger.error(f"[{self.name}] Error navigating to {self.base_url} for login check: {e_nav}")
                    if self.driver:
                        try:
                            self.driver.quit()
                        except Exception as e_quit_nav:
                            self.logger.error(f"[{self.name}] Error quitting driver during navigation exception cleanup: {e_quit_nav}")
                        self.driver = None
                    return False
            else:
                self.logger.error(f"[{self.name}] WebDriver initialization returned None (failed) for profile: {self.user_data_dir or 'default'}.")
                return False

        except Exception as e:
            self.logger.error(f"[{self.name}] Critical error during WebDriver initialization or login check for profile '{self.user_data_dir or 'default'}': {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e_quit:
                    self.logger.error(f"[{self.name}] Error quitting driver during general exception cleanup: {e_quit}")
                self.driver = None
            return False

    def _quit_driver(self):
        if self.driver:
            self.logger.info(f"[{self.name}] Quitting WebDriver.")
            try:
                self.driver.quit()
            except Exception as e:
                self.logger.error(f"[{self.name}] Error quitting WebDriver: {e}", exc_info=True)
            finally:
                self.driver = None

    def _check_login_required(self, check_url):
        try:
            self.logger.info(f"[{self.name}] Checking for login requirement at {check_url}...")
            login_indicator_xpath = (
                "//form[@action='/login'] | "
                "//a[contains(@href,'/login') and (contains(normalize-space(.), 'Login') or contains(normalize-space(.), 'Sign In'))] | "
                "//button[contains(translate(normalize-space(.), 'LOGIN', 'login'), 'login') and @type='submit']"
            )
            WebDriverWait(self.driver, 7).until(
                EC.visibility_of_element_located((By.XPATH, login_indicator_xpath))
            )
            current_url = self.driver.current_url
            self.logger.warning(f"[{self.name}] Login required detected (URL: {current_url}).")
            send_email_notify(
                subject=f"SimCompany {self.name} Monitoring Requires Login",
                body=f"The script detected a login requirement when trying to access {check_url} (URL: {current_url}).\n"
                     f"Please manually log in to SimCompanies. The script will retry in {LONG_RETRY_DELAY} seconds."
            )
            return True # Login is required
        except TimeoutException:
            self.logger.info(f"[{self.name}] No login page detected. Continuing...")
            return False # Login not required
        except Exception as e:
            self.logger.error(f"[{self.name}] Error checking login status: {e}", exc_info=True)
            return True # Assume login might be required on error


# --- Forest Nursery Monitor ---
class ForestNurseryMonitor(BaseMonitor):
    """Monitors Forest Nursery production and construction."""
    def __init__(self, target_paths, logger=None, user_data_dir=None):
        super().__init__("ForestNursery", logger=logger, user_data_dir=user_data_dir)
        self.target_paths = target_paths

    def run(self):
        """Starts the continuous monitoring loop."""
        self.logger.info(f"[{self.name}] Starting monitoring loop.")
        while True:
            wait_seconds = self._process_nurseries()
            if wait_seconds is None: # Indicates a critical error or manual stop
                self.logger.warning(f"[{self.name}] No valid wait time returned. Stopping.")
                break
            if wait_seconds > 0:
                self.logger.info(f"[{self.name}] Next check in {wait_seconds:.0f} +60 seconds.")
                try:
                    time.sleep(wait_seconds + 60) # Add 60 seconds buffer
                except KeyboardInterrupt:
                    self.logger.info(f"[{self.name}] Monitoring loop interrupted by user.")
                    break
            else:
                 self.logger.info(f"[{self.name}] No wait time needed, checking again immediately (with small delay).")
                 time.sleep(5) # Small delay to prevent tight loop on errors
            self.logger.info(f"\n[{self.name}] === Starting new check cycle ===\n")

    def _process_nurseries(self):
        """Processes all target nurseries once and returns wait time."""
        if not self._initialize_driver():
            return LONG_RETRY_DELAY # Wait a long time if driver fails

        construction_finish_times = []
        production_finish_times = []
        any_nurture_started = False
        now_for_parsing = datetime.datetime.now()
        error_occurred = False
        restart_after_cut = False  # 新增 flag

        try:
            self.logger.info("For first-time use, please log in using python main.py login, and close the browser after logging in.")

            for target_path in self.target_paths:
                building_url = self.base_url + target_path
                self.logger.info(f"[{self.name}] Checking: {building_url}")
                try:
                    self.driver.get(building_url)
                    time.sleep(2) # Allow page to load

                    # Check Construction
                    if self._check_construction(target_path, construction_finish_times):
                        continue # Move to next nursery if under construction

                    # Try Nurture / Cut down
                    nurture_result = self._try_nurture_or_cutdown(target_path)
                    if nurture_result == "RESTART":
                        restart_after_cut = True
                        break  # 不 quit driver，直接 break

                    any_nurture_started = any_nurture_started or (nurture_result == "NURTURED")

                    # Get Production Time if not nurtured or construction
                    self._get_production_time(target_path, production_finish_times)

                    time.sleep(1)

                except WebDriverException as e_wd:
                    self.logger.error(f"[{self.name}] WebDriver error processing {building_url}: {e_wd}", exc_info=True)
                    error_occurred = True
                    break # Exit loop on major WebDriver error
                except Exception as e_building:
                    self.logger.error(f"[{self.name}] Failed to process {building_url}: {e_building}", exc_info=True)
                    error_occurred = True # Continue with others if possible, but flag for longer wait


        except KeyboardInterrupt:
            self.logger.info(f"[{self.name}] Processing interrupted by user.")
            self._quit_driver()
            return None # Signal to stop
        except Exception as e_main:
            self.logger.critical(f"[{self.name}] Unhandled error in processing loop: {e_main}", exc_info=True)
            error_occurred = True
        finally:
            if not restart_after_cut:
                self._quit_driver()  # 只有不是 cutdown 才 quit

        if restart_after_cut:
            return 5  # 只等 5 秒，且不 quit driver

        if error_occurred:
            return DEFAULT_RETRY_DELAY * 5 # Longer delay on errors

        # Calculate Wait Time
        wait_construction = self._calculate_wait(construction_finish_times, now_for_parsing, True)
        wait_production = self._calculate_wait(production_finish_times, now_for_parsing, False)

        if wait_construction is not None:
            return wait_construction + CONSTRUCTION_CHECK_BUFFER

        if wait_production is not None:
            return wait_production + PRODUCTION_CHECK_BUFFER

        if any_nurture_started or (not production_finish_times and not construction_finish_times):
            self.logger.info(f"[{self.name}] Nurture started or no times found. Retrying soon.")
            return DEFAULT_RETRY_DELAY

        self.logger.warning(f"[{self.name}] No specific event found. Retrying after default delay.")
        return DEFAULT_RETRY_DELAY * 5

    def _check_construction(self, target_path, construction_finish_times):
        """Checks if a building is under construction."""
        try:
            # Use WebDriverWait to wait for the Construction header
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//h3[normalize-space(text())='Construction']"))
            )
            finish_time_p = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]"))
            )
            finish_time_str = finish_time_p.text.strip().replace('Finishes at', '').strip()
            self.logger.info(f"{target_path} is under construction, expected completion time: {finish_time_str}")
            finish_dt = parser.parse(finish_time_str)
            construction_finish_times.append(finish_dt)
            return True
        except TimeoutException:
            self.logger.info(f"{target_path} is not under construction, checking production status...")
            return False
        except Exception as e:
            self.logger.error(f"Error occurred while checking construction status for {target_path}: {e}", exc_info=True)
            return False

    def _try_nurture_or_cutdown(self, target_path):
        """Tries to click Max and Nurture, handles resource errors by cutting down. Also checks for 'Not enough input resources of quality 5 available' or 'Water missing' if Nurture/Max not found. After Cut down, retries Nurture until 'Cancel Nurturing' is found or max retries reached."""
        def try_nurture():
            return self._click_max_and_nurture()

        # 先檢查是否正在生產中，若是則直接 return "NONE"
        try:
            self.driver.get(self.base_url + target_path)
            # Use WebDriverWait to check for Cancel Nurturing button
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Cancel Nurturing') and contains(@class, 'btn-secondary')]"))
            )
            self.logger.info(f"{target_path} is producing (Cancel Nurturing button found), skip cut down.")
            return "NONE"
        except TimeoutException:
            pass

        try:
            if try_nurture():
                # Check for not enough resources
                try:
                    WebDriverWait(self.driver, 2).until(
                        EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'Not enough input resources')]")
                    ))
                    self.logger.info(f"{target_path} Not enough resources, attempting to click 'Cut down'.")
                    if self._click_cutdown(target_path):
                        return self._retry_nurture_until_success(target_path)
                except TimeoutException:
                    # Check if Nurture succeeded
                    if self._check_cancel_nurturing():
                        self.logger.info(f"{target_path} Nurture started successfully after Max.")
                        return "NURTURED"
                    else:
                        self.logger.info(f"{target_path} Nurture did not start, retrying...")
                        return self._retry_nurture_until_success(target_path)
            else:
                # Could not find Nurture button, check for resource errors
                error_elements_5 = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Not enough input resources of quality 5 available')]")
                error_elements_water = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Water missing')]")
                if error_elements_5 or error_elements_water:
                    msg = "'Not enough input resources of quality 5 available'" if error_elements_5 else "'Water missing'"
                    self.logger.info(f"{target_path} Detected {msg}, attempting to click 'Cut down'.")
                    if self._click_cutdown(target_path):
                        return self._retry_nurture_until_success(target_path)
                else:
                    self.logger.info(f"{target_path} No 'Not enough input resources of quality 5 available' or 'Water missing' message found.")
        except Exception as e:
            self.logger.error(f"Error occurred while trying Nurture/Cut down for {target_path}: {e}", exc_info=False)
        return "NONE"

    def _click_cutdown(self, target_path):
        """Clicks the Cut down button and confirms. Returns True if successful."""
        try:
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"))
            ).click()
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'modal-content')]//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"))
            ).click()
            self.logger.info(f"{target_path} 'Cut down' clicked. Will retry Nurture.")
            return True
        except Exception as e:
            self.logger.error(f"{target_path} Failed to click 'Cut down': {e}", exc_info=False)
            return False

    def _check_cancel_nurturing(self):
        """Checks if the Cancel Nurturing button is present (production started)."""
        try:
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Cancel Nurturing') and contains(@class, 'btn-secondary')]"))
            )
            return True
        except TimeoutException:
            return False

    def _retry_nurture_until_success(self, target_path, max_retries=5):
        """Retries Nurture after Cut down until Cancel Nurturing is found or max retries reached."""
        for attempt in range(1, max_retries+1):
            self.logger.info(f"{target_path} Retrying Nurture after Cut down (attempt {attempt}/{max_retries})...")
            self.driver.get(self.base_url + target_path)
            time.sleep(2)
            if self._check_cancel_nurturing():
                self.logger.info(f"{target_path} Production started successfully after Cut down (Cancel Nurturing found).")
                return "NURTURED"
            if not self._try_nurture_button_only():
                self.logger.warning(f"{target_path} Nurture button not found or not clickable on retry {attempt}.")
            else:
                time.sleep(2)
                if self._check_cancel_nurturing():
                    self.logger.info(f"{target_path} Production started successfully after Nurture retry.")
                    return "NURTURED"
            time.sleep(2)
        self.logger.error(f"{target_path} Failed to start production after Cut down and {max_retries} retries.")
        return "FAILED"

    def _click_max_and_nurture(self):
        """Clicks the Max button and then the Nurture button. Returns True if successful, False otherwise."""
        try:
            WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//label[contains(., 'Max') and @type='button']"))
            ).click()
            time.sleep(0.5)
            nurture_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Nurture') and contains(@class, 'btn-primary')]"))
            )
            if nurture_btn.is_enabled():
                nurture_btn.click()
                time.sleep(1)
                return True
        except Exception as e:
            self.logger.info(f"Max+Nurture click failed: {e}")
        return False

    def _try_nurture_button_only(self):
        """Tries to click Max and Nurture button (for retry)."""
        return self._click_max_and_nurture()

    def _get_production_time(self, target_path, production_finish_times):
        """Finds and records the production finish time."""
        finish_time_str = None
        try:
            # Try finding within "PROJECTED STAGE" first (simplified)
            proj_divs = self.driver.find_elements(By.XPATH, "//h3[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'projected stage')]/following-sibling::div[1]")
            for div in proj_divs:
                p_tags = div.find_elements(By.TAG_NAME, 'p')
                for p in p_tags:
                    text = p.text.strip()
                    if '/' in text and ':' in text:
                        try:
                            parser.parse(text)
                            finish_time_str = text
                            break
                        except Exception: continue
                if finish_time_str: break

            # Fallback: Search all <p> tags if not found above
            if not finish_time_str:
                all_p_tags = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_all_elements_located((By.TAG_NAME, 'p'))
                )
                for p in all_p_tags:
                    text = p.text.strip()
                    if ('/' in text and ':' in text) or ('Finishes at' in text):
                         text_to_parse = text.replace('Finishes at', '').strip()
                         try:
                             parser.parse(text_to_parse)
                             finish_time_str = text_to_parse
                             break
                         except Exception: continue

            if finish_time_str:
                self.logger.info(f"{target_path} Expected production completion time: {finish_time_str}")
                production_finish_times.append(parser.parse(finish_time_str))
            else:
                self.logger.warning(f"{target_path} No clear production countdown time found.")

        except Exception as e:
            self.logger.error(f"Error occurred while finding production completion time for {target_path}: {e}")

    def _calculate_wait(self, finish_times, now, is_construction):
        """Calculates the minimum wait time from a list of datetimes."""
        min_wait = None
        min_dt = None

        for dt in finish_times:
            wait = (dt - now).total_seconds()
            if wait > 0 and (min_wait is None or wait < min_wait):
                min_wait = wait
                min_dt = dt

        if min_wait is not None:
            type_str = "Construction" if is_construction else "Production"
            self.logger.info(f"Earliest {type_str} finish time: {min_dt.strftime('%Y-%m-%d %H:%M:%S')}, need to wait {min_wait:.0f} seconds.")
            if is_construction:
                send_email_notify(
                    subject=f"SimCompany {type_str} Completion Notification",
                    body=f"Building {type_str} was completed at {min_dt.strftime('%Y-%m-%d %H:%M:%S')}, please check."
                )
        return min_wait


# --- Power Plant Producer ---
class PowerPlantProducer(BaseMonitor):
    """Manages Power Plant production cycles."""
    # SimCompanies now renders this label in different elements depending on
    # the activity (for example, robot installation and building upgrades).
    # Do not tie the lookup to a <p> tag or to direct text nodes.
    FINISH_TIME_XPATH = (
        "//*[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'finishes at')]"
    )

    def __init__(self, target_paths, logger=None, user_data_dir=None):
        super().__init__("PowerPlant", logger=logger, user_data_dir=user_data_dir)
        self.target_paths = target_paths
        self._failure_alerted_paths = set()
        self.finish_times_file_path = os.path.join('record', 'powerplant_finish_times.json')
        self.plant_finish_times = self._load_finish_times()
        # Ensure all target_paths have an entry, defaulting to None if not in loaded_times
        for path in target_paths:
            if path not in self.plant_finish_times:
                self.plant_finish_times[path] = None

    def _load_finish_times(self):
        """Loads finish times from the JSON file."""
        try:
            if os.path.exists(self.finish_times_file_path):
                with open(self.finish_times_file_path, 'r') as f:
                    data = json.load(f)
                # Convert ISO strings back to datetime objects
                loaded_times = {}
                ignored_paths = sorted(set(data) - set(self.target_paths))
                if ignored_paths:
                    self.logger.info(
                        f"[{self.name}] Ignoring finish times for unconfigured plants: {ignored_paths}"
                    )
                for path in self.target_paths:
                    time_str = data.get(path)
                    if time_str:
                        try:
                            loaded_times[path] = self._parse_finish_time(time_str)
                        except (ValueError, TypeError):
                            self.logger.warning(f"[{self.name}] Invalid datetime format for {path} in {self.finish_times_file_path}: {time_str}. Setting to None.")
                            loaded_times[path] = None
                    else:
                        loaded_times[path] = None
                self.logger.info(f"[{self.name}] Successfully loaded finish times from {self.finish_times_file_path}")
                return loaded_times
            else:
                self.logger.info(f"[{self.name}] Finish times file not found ({self.finish_times_file_path}). Initializing with empty times.")
                return {path: None for path in self.target_paths}
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"[{self.name}] Error loading finish times from {self.finish_times_file_path}: {e}. Initializing with empty times.")
            return {path: None for path in self.target_paths}
        except Exception as e:
            self.logger.error(f"[{self.name}] Unexpected error loading finish times: {e}. Initializing with empty times.", exc_info=True)
            return {path: None for path in self.target_paths}

    def _save_finish_times(self):
        """Saves current finish times to the JSON file."""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.finish_times_file_path), exist_ok=True)
            # Convert datetime objects to ISO strings for JSON serialization
            data_to_save = {}
            for path, dt_obj in self.plant_finish_times.items():
                if dt_obj:
                    data_to_save[path] = dt_obj.isoformat()
                else:
                    data_to_save[path] = None
            
            temp_path = self.finish_times_file_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.finish_times_file_path)
            self.logger.info(f"[{self.name}] Successfully saved finish times to {self.finish_times_file_path}")
        except IOError as e:
            self.logger.error(f"[{self.name}] Error saving finish times to {self.finish_times_file_path}: {e}")
        except Exception as e:
            self.logger.error(f"[{self.name}] Unexpected error saving finish times: {e}", exc_info=True)

    def _find_visible_finish_time(self):
        """Return ``(element, text, datetime)`` for a visible finish timer.

        The site may nest the label and timestamp in spans or cards, so the
        smallest visible element with a *parseable* ``Finishes at`` value is
        selected.  This accepts production, robot-installation, and upgrade
        timers without mistaking an unrelated parent container for a timer.
        """
        candidates = []
        for element in self.driver.find_elements(By.XPATH, self.FINISH_TIME_XPATH):
            try:
                if not element.is_displayed():
                    continue
                text = " ".join(line.strip() for line in element.text.splitlines() if line.strip())
                match = re.search(r"\bfinishes\s+at\s*:?[\s]*(.+)", text, flags=re.IGNORECASE)
                if not match:
                    continue
                finish_dt = self._parse_finish_time(match.group(1).strip())
                candidates.append((len(text), element, text, finish_dt))
            except (ValueError, TypeError, OverflowError, StaleElementReferenceException):
                continue

        if not candidates:
            return None
        _, element, text, finish_dt = min(candidates, key=lambda candidate: candidate[0])
        return element, text, finish_dt

    def _find_visible_finish_time_element(self):
        """Return only the timer element for Selenium expected conditions."""
        finish_time = self._find_visible_finish_time()
        return finish_time[0] if finish_time else False

    @staticmethod
    def _parse_finish_time(value):
        """Parse finish times consistently in the machine's local timezone."""
        parsed = parser.parse(value)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=local_tz)
        return parsed.astimezone(local_tz)

    def run(self):
        """Starts the continuous production loop."""
        self.logger.info(f"[{self.name}] Starting production loop.")
        while True:
            if not self._initialize_driver():
                self.logger.error(f"[{self.name}] Failed to initialize WebDriver. Retrying after long delay ({LONG_RETRY_DELAY * 2}s).")
                time.sleep(LONG_RETRY_DELAY * 2)
                continue

            # Process plants and get the time to wait for the next due plant
            wait_seconds = self._process_plants() # This now returns wait time for the *next* event or an error code
            self._quit_driver() # Quit driver after processing all due plants in this cycle

            if wait_seconds is None: # Indicates a critical error or user interruption
                self.logger.warning(f"[{self.name}] Critical error or user interruption in _process_plants. Stopping monitor.")
                break # Exit the loop

            effective_wait = 0
            if wait_seconds < 0: # Negative value indicates an error and is the delay to apply
                self.logger.warning(f"[{self.name}] An error occurred in _process_plants. Applying delay: {-wait_seconds:.0f}s.")
                effective_wait = -wait_seconds
            elif wait_seconds == 0: # No plants are currently producing or scheduled (all are None or in the past and processed)
                self.logger.info(f"[{self.name}] No future production times set or all plants processed. Checking again after default delay ({DEFAULT_RETRY_DELAY}s).")
                effective_wait = DEFAULT_RETRY_DELAY
            else: # Positive value is the time in seconds until the next plant is due
                # Add a small buffer to ensure we don't check too early
                effective_wait = wait_seconds + PRODUCTION_CHECK_BUFFER 
                self.logger.info(f"[{self.name}] Next check for a due plant in {wait_seconds:.0f}s (plus {PRODUCTION_CHECK_BUFFER}s buffer). Effective wait: {effective_wait:.0f}s.")

            self.logger.info(f"[{self.name}] Next overall check cycle in {effective_wait:.0f} seconds.")
            try:
                time.sleep(effective_wait)
            except KeyboardInterrupt:
                self.logger.info(f"[{self.name}] Production loop interrupted by user.")
                break
            self.logger.info(f"\n[{self.name}] === Starting new production check cycle ===\n")

    def _process_plants(self):
        now = datetime.datetime.now().astimezone()
        error_occurred_in_cycle = False
        started_paths_in_cycle = []
        due_paths = []
        # 只處理到期的powerplant
        # Modified to include plants finishing in the next 60 seconds
        process_threshold_time = now + datetime.timedelta(seconds=60)
        for path, finish_dt in self.plant_finish_times.items():
            if finish_dt is None or finish_dt <= process_threshold_time:
                due_paths.append(path)
        if not due_paths:
            # 沒有任何到期的plant，計算下次最早的完成時間
            future_times = [dt for dt in self.plant_finish_times.values() if dt is not None and dt > now]
            if future_times:
                min_wait = min((dt - now).total_seconds() for dt in future_times)
                return max(0, min_wait)
            else:
                return 0

        self.logger.info(f"[{self.name}] Due plants to process: {due_paths}")
        try:
            for target_path in due_paths:
                self.logger.info(f"[{self.name}] Processing plant in the current tab: {target_path}")
                try:
                    self.driver.get(self.base_url + target_path)
                    WebDriverWait(self.driver, 15).until(EC.url_contains(target_path.split('/')[-2]))
                    WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'btn-secondary') and normalize-space(.)='Reposition']"))
                    )
                    production_started_here = self._check_and_start_production(target_path)
                    if production_started_here:
                        started_paths_in_cycle.append(target_path)
                    else:
                        self._get_existing_finish_time(target_path)
                        if self.plant_finish_times.get(target_path) is None:
                            error_occurred_in_cycle = True
                except TimeoutException as e_timeout:
                    self.logger.error(f"[{self.name}] Timeout processing {target_path} at {self.driver.current_url}: {e_timeout}", exc_info=False)
                    error_occurred_in_cycle = True
                except NoSuchElementException as e_no_element:
                    self.logger.error(f"[{self.name}] Element not found processing {target_path} at {self.driver.current_url}: {e_no_element}", exc_info=False)
                    error_occurred_in_cycle = True
                except WebDriverException as e_wd_plant:
                    self.logger.error(f"[{self.name}] WebDriver error processing {target_path} at {self.driver.current_url} (Type: {type(e_wd_plant).__name__}): {e_wd_plant}", exc_info=True)
                    error_occurred_in_cycle = True
                    if "disconnected" in str(e_wd_plant).lower() or "session deleted" in str(e_wd_plant).lower() or "target window already closed" in str(e_wd_plant).lower():
                        self.logger.critical(f"[{self.name}] WebDriver seems disconnected or tab closed. Aborting cycle.")
                        return -LONG_RETRY_DELAY
                except Exception as e_plant:
                    self.logger.error(f"[{self.name}] Unexpected error processing {target_path} at {self.driver.current_url}: {e_plant}", exc_info=True)
                    error_occurred_in_cycle = True
                time.sleep(random.uniform(0.5, 1.0))
        except KeyboardInterrupt:
            self.logger.info(f"[{self.name}] Processing in _process_plants interrupted by user.")
            return None
        except WebDriverException as e_main_wd:
            self.logger.critical(f"[{self.name}] Critical WebDriver error during main plant processing loop (Type: {type(e_main_wd).__name__}): {e_main_wd}", exc_info=True)
            self._save_finish_times()
            return -LONG_RETRY_DELAY
        except Exception as e_main:
            self.logger.critical(f"[{self.name}] Unhandled error in _process_plants: {e_main}", exc_info=True)
            self._save_finish_times()
            return -DEFAULT_RETRY_DELAY
        
        self._save_finish_times()

        if error_occurred_in_cycle:
            return -DEFAULT_RETRY_DELAY

        # 計算下次最早的完成時間
        now = datetime.datetime.now().astimezone()
        future_times = [dt for dt in self.plant_finish_times.values() if dt is not None and dt > now]
        if future_times:
            min_wait = min((dt - now).total_seconds() for dt in future_times)
            return max(0, min_wait)
        else:
            return 0

    def _check_and_start_production(self, path):
        """Attempts to start production and updates self.plant_finish_times."""
        current_building_url = self.base_url + path
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                existing_finish_time = self._find_visible_finish_time()
                if existing_finish_time:
                    _, finish_time_str, finish_dt = existing_finish_time
                    self.logger.info(f"[{self.name}] {path} is ALREADY PRODUCING. Finish time: {finish_time_str}")
                    self.plant_finish_times[path] = finish_dt
                    self._failure_alerted_paths.discard(path)
                    return False
                self.logger.info(f"[{self.name}] {path} is not producing, attempting to start 24h production... (attempt {attempt}/{max_retries})")
                WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//button[normalize-space(.)='24h' or normalize-space(.)='24hr']",
                    ))
                ).click()
                time.sleep(random.uniform(0.2, 0.5))
                WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//button[starts-with(normalize-space(.), 'Produce')]",
                    ))
                ).click()
                self.logger.info(f"[{self.name}] {path} 'Produce' button clicked. Verifying production start... (attempt {attempt}/{max_retries})")
                time.sleep(random.uniform(0.5, 0.7))
                self.driver.get(current_building_url)
                confirmation_element = WebDriverWait(self.driver, 15).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, "//button[normalize-space(.)='Cancel Production' and contains(@class, 'btn-secondary')]")),
                        lambda _driver: self._find_visible_finish_time_element()
                    )
                )
                tag_name = confirmation_element.tag_name
                text_preview = confirmation_element.text.strip()[:30] if confirmation_element.text else ""
                self.logger.info(f"[{self.name}] {path} Production successfully STARTED or CONFIRMED by UI element: <{tag_name}>{text_preview}...")
                time.sleep(random.uniform(0.3, 0.7))
                new_finish_time = self._find_visible_finish_time()
                if new_finish_time:
                    _, new_finish_time_str, finish_dt = new_finish_time
                    self.plant_finish_times[path] = finish_dt
                    self.logger.info(f"[{self.name}] {path} New production finish time: {new_finish_time_str}")
                else:
                    self.logger.warning(f"[{self.name}] {path} Production confirmed, but 'Finishes at' text not immediately found/updated. Will rely on next cycle if needed.")
                    self.plant_finish_times[path] = None
                self._failure_alerted_paths.discard(path)
                return True
            except TimeoutException:
                self.logger.warning(f"[{self.name}] {path} Timeout during production start/verification. Production might NOT have started. (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    try:
                        self.driver.get(current_building_url)
                        time.sleep(2)
                    except Exception:
                        pass
                    continue
                else:
                    self.logger.error(f"[{self.name}] {path} Failed to start production after {max_retries} attempts.")
                    self._notify_production_failure_once(
                        path,
                        f"啟動生產連續 {max_retries} 次逾時",
                    )
                    self.plant_finish_times[path] = None
                    return False
            except Exception as e:
                self.logger.error(f"[{self.name}] Exception in _check_and_start_production for {path} (URL: {current_building_url}) (Type: {type(e).__name__}): {e}", exc_info=True)
                self.plant_finish_times[path] = None
                return False

    def _notify_production_failure_once(self, path, reason):
        """Notify once for a repeated plant failure to avoid retry-loop spam."""
        if path in self._failure_alerted_paths:
            return False
        message = (
            "⚠️ SimCompanies 發電廠自動生產異常！\n"
            f"發電廠：{path}\n"
            f"原因：{reason}\n"
            f"網址：{self.base_url + path}\n"
            "程式會繼續自動重試。"
        )
        if send_telegram_notify(message, logger=self.logger):
            self._failure_alerted_paths.add(path)
            return True
        return False

    def _get_existing_finish_time(self, path):
        """Gets existing finish time and updates self.plant_finish_times."""
        try:
            existing_finish_time = WebDriverWait(self.driver, 7).until(
                lambda _driver: self._find_visible_finish_time()
            )
            if existing_finish_time:
                _, finish_time_str, finish_dt = existing_finish_time
                self.logger.info(f"[{self.name}] {path} Found existing completion time: {finish_time_str}")
                self.plant_finish_times[path] = finish_dt
                return True
            self.logger.info(f"[{self.name}] {path} No visible, parseable 'Finishes at' time. Assuming no active production time visible.")
            self.plant_finish_times[path] = None
            return False
        except TimeoutException:
            self.logger.info(f"[{self.name}] {path} No 'Finishes at' time found (TimeoutException). Plant is likely idle.")
            self.plant_finish_times[path] = None
            return False
        except Exception as e:
            self.logger.error(f"[{self.name}] Exception in _get_existing_finish_time for {path} (Type: {type(e).__name__}): {e}", exc_info=True)
            self.plant_finish_times[path] = None
            return False

# --- Oil Rig Monitor ---
class OilRigMonitor(BaseMonitor):
    """Monitors Oil Rig construction and abundance, handles rebuilds."""
    def __init__(self, logger=None, user_data_dir=None):
        super().__init__("OilRig", logger=logger, user_data_dir=user_data_dir)
        self.landscape_url = f"{self.base_url}/landscape/"

    def run(self):
        """Starts the continuous monitoring loop."""
        self.logger.info(f"[{self.name}] Starting monitoring loop.")
        while True:
            wait_seconds = self._process_rigs()
            if wait_seconds is None:
                self.logger.warning(f"[{self.name}] No valid wait time returned. Stopping.")
                break

            if wait_seconds > 0:
                self.logger.info(f"[{self.name}] Next check in {wait_seconds:.0f} +60 seconds.")
                try:
                    time.sleep(wait_seconds + 60)
                except KeyboardInterrupt:
                    self.logger.info(f"[{self.name}] Monitoring loop interrupted by user.")
                    break
            else:
                 self.logger.warning(f"[{self.name}] No construction or rebuild needed, or error occurred. "
                                f"Monitoring ends (or retries after long delay if error).")
                 if wait_seconds == 0:
                     self.logger.info(f"[{self.name}] No active construction found. Exiting normally.")
                     return
                 else:
                     time.sleep(LONG_RETRY_DELAY)

            self.logger.info(f"\n[{self.name}] === Starting new check cycle ===\n")


    def _process_rigs(self):
        """Processes all oil rigs once and returns wait time or None."""
        if not self._initialize_driver():
            return -LONG_RETRY_DELAY

        min_wait_seconds = None
        now_for_parsing = datetime.datetime.now()
        error_occurred = False

        try:
            while True:
                action_taken = False
                oilrig_links = self._get_oilrig_links()
                if not oilrig_links:
                    return -LONG_RETRY_DELAY

                for oilrig_url in oilrig_links:
                    if action_taken: 
                        self.logger.info(f"[{self.name}] Rebuild started. Waiting 2 seconds before re-checking oil rigs.")
                        time.sleep(2)
                        continue

                    self.logger.info(f"[{self.name}] Checking: {oilrig_url}")
                    self.driver.get(oilrig_url)
                    WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, "//h3[normalize-space(text())='Construction']"))
                        )
                        finish_time_p = self.driver.find_element(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
                        finish_time_str = finish_time_p.text.strip().replace('Finishes at', '').strip()
                        finish_dt = parser.parse(finish_time_str)
                        wait = (finish_dt - now_for_parsing).total_seconds()

                        if wait > 0:
                            self.logger.info(f"  Under construction, completion time: {finish_time_str}")
                            if min_wait_seconds is None or wait < min_wait_seconds:
                                min_wait_seconds = wait
                        else:
                            self.logger.info(f"  Construction completed: {finish_time_str}.")
                            send_email_notify(
                                subject="SimCompany Oil Rig Construction Completion Notification",
                                body=f"Oil Rig ({oilrig_url}) construction has been completed, please check."
                            )

                    except TimeoutException:
                        self.logger.info(f"  Not under construction, checking abundance...")
                        abundance_result = self._check_and_rebuild_oilrig(oilrig_url)
                        if abundance_result == True:
                            action_taken = True
                        elif abundance_result == "WAIT_1HOUR":
                            self.logger.info(f"[{self.name}] Crude oil abundance > 95, will check again in 1 hour.")
                            self._quit_driver()
                            time.sleep(3600)
                            return 3600
                        elif abundance_result is False:
                            self.logger.warning(f"[{self.name}] Error occurred while checking Abundance or Rebuild, will immediately retry the check cycle.")
                            time.sleep(3)  # short sleep to avoid rapid loop
                            continue  # restart the while True loop for immediate retry

                    except Exception as e_constr:
                        self.logger.error(f"  Error occurred while checking construction status for {oilrig_url}: {e_constr}", exc_info=True)
                        error_occurred = True

                    time.sleep(1)

                if action_taken:
                    self.logger.info(f"[{self.name}] Rebuild started. Immediately re-checking oil rigs without quitting driver.")
                    continue
                break

        except KeyboardInterrupt:
            self.logger.info(f"[{self.name}] Processing interrupted by user.")
            return None
        except Exception as e_main:
            self.logger.critical(f"[{self.name}] Unhandled error in processing loop: {e_main}", exc_info=True)
            error_occurred = True
        finally:
            self._quit_driver()

        if error_occurred:
            return -DEFAULT_RETRY_DELAY * 5

        if min_wait_seconds is not None:
            self.logger.info(f"[{self.name}] Earliest construction completion requires waiting {min_wait_seconds:.0f} seconds.")
            return min_wait_seconds + CONSTRUCTION_CHECK_BUFFER

        self.logger.info(f"[{self.name}] No construction or rebuild needed for Oil Rigs.")
        return 0


    def _get_oilrig_links(self):
        """Gets all Oil Rig links from the landscape page with retries."""
        self.logger.info(f"[{self.name}] Entering {self.landscape_url} to find Oil Rigs...")
        self.driver.get(self.landscape_url)

        if self._check_login_required(self.landscape_url):
            return None

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # 等待直到出現含有 /b/ 的連結 (確保地圖載入)
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/b/')]"))
                )
                
                a_tags = self.driver.find_elements(By.TAG_NAME, "a")
                links = []
                for a in a_tags:
                    href = a.get_attribute('href')
                    if href and "/b/" in href:
                        is_oil_rig = False
                        
                        # 1. 檢查圖片 Alt (一般狀態)
                        if not is_oil_rig:
                            try:
                                imgs = a.find_elements(By.TAG_NAME, "img")
                                for img in imgs:
                                    alt = img.get_attribute('alt')
                                    if alt and 'oil rig' in alt.lower():
                                        is_oil_rig = True
                                        break
                            except Exception: pass

                        # 2. 檢查 Span 文字 (一般狀態)
                        if not is_oil_rig:
                            try:
                                spans = a.find_elements(By.TAG_NAME, "span")
                                for span in spans:
                                    text = span.text
                                    if text and 'oil rig' in text.lower():
                                        is_oil_rig = True
                                        break
                            except Exception: pass

                        # 3. [新增] 檢查 Aria-Label (升級/建造/生產狀態)
                        if not is_oil_rig:
                            try:
                                # 檢查連結本身或其子元素是否有 aria-label 包含 "oil rig"
                                elements_with_label = a.find_elements(By.XPATH, ".//*[@aria-label]")
                                for el in elements_with_label:
                                    label = el.get_attribute('aria-label')
                                    if label and 'oil rig' in label.lower():
                                        is_oil_rig = True
                                        break
                                # 順便檢查 a 標籤本身
                                if not is_oil_rig:
                                    a_label = a.get_attribute('aria-label')
                                    if a_label and 'oil rig' in a_label.lower():
                                        is_oil_rig = True
                            except Exception: pass
                        
                        if is_oil_rig and href not in links:
                            links.append(href)

                if links:
                    self.logger.info(f"[{self.name}] Found {len(links)} Oil Rig links.")
                    return links
                else:
                    self.logger.warning(f"[{self.name}] No Oil Rig links found on attempt {attempt + 1}.")
                    time.sleep(2)
                    if attempt == max_attempts - 1:
                        self._save_screenshot("no_oil_rigs_found")

                self.driver.refresh()

            except TimeoutException:
                self.logger.warning(f"[{self.name}] Timeout waiting for building links (/b/) to appear on attempt {attempt + 1}.")
                self.driver.refresh()
            except Exception as e:
                self.logger.error(f"[{self.name}] Error getting Oil Rig links (Attempt {attempt + 1}): {e}", exc_info=True)
                time.sleep(5)

        self.logger.error(f"[{self.name}] Failed to get Oil Rig links after {max_attempts} attempts.")
        return None

    def _check_and_rebuild_oilrig(self, oilrig_url):
        """Checks abundance and triggers rebuild based on new logic."""
        try:
            crude_abundance = None
            methane_abundance = None
            try:
                crude_img = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//img[@alt='Crude oil']"))
                )
                row_div = crude_img
                for _ in range(5):
                    row_div = WebDriverWait(row_div, 10).until(
                        EC.presence_of_element_located((By.XPATH, ".."))
                    )
                    if 'row' in row_div.get_attribute('class'):
                        break
                abundance_span = WebDriverWait(row_div, 10).until(
                    EC.presence_of_element_located((By.XPATH, ".//span[contains(text(), 'Abundance:')]"))
                )
                match = re.search(r'Abundance:\s*([\d.]+)', abundance_span.text)
                if match:
                    crude_abundance = float(match.group(1))
            except Exception:
                self.logger.error("  Crude oil abundance not found!")
                return False

            try:
                methane_img = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//img[@alt='Methane']"))
                )
                row_div = methane_img
                for _ in range(5):
                    row_div = WebDriverWait(row_div, 10).until(
                        EC.presence_of_element_located((By.XPATH, ".."))
                    )
                    if 'row' in row_div.get_attribute('class'):
                        break
                abundance_span = WebDriverWait(row_div, 10).until(
                    EC.presence_of_element_located((By.XPATH, ".//span[contains(text(), 'Abundance:')]"))
                )
                match = re.search(r'Abundance:\s*([\d.]+)', abundance_span.text)
                if match:
                    methane_abundance = float(match.group(1))
            except Exception:
                methane_abundance = None

            self.logger.info(f"  Crude oil abundance: {crude_abundance}, Methane abundance: {methane_abundance}")

            if crude_abundance is not None and crude_abundance > 95:
                self.logger.info(f"  Crude oil abundance > 95, no rebuild needed.")
                send_email_notify(
                    subject="SimCompany Oil Rig Abundance > 95 Notification",
                    body=f"Oil Rig ({oilrig_url}) Crude oil abundance is {crude_abundance} (>95). No rebuild needed. Will check again in 1 hour until construction starts."
                )
                return "WAIT_1HOUR"

            if crude_abundance is not None and 80 < crude_abundance <= 95:
                self.logger.info(f"  Crude oil abundance between 80 and 95, clicking rebuild twice.")
                for i in range(2):
                    try:
                        rebuild_btn = WebDriverWait(self.driver, 20).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Rebuild') and contains(@class, 'btn-danger')]"))
                        )
                        rebuild_btn.click()
                        self.logger.info(f"  Rebuild clicked. ({i+1}/2)")

                        modal_confirm_btn = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'modal-content')]//button[contains(@class, 'btn-primary') and contains(., 'Rebuild')]"))
                        )
                        modal_confirm_btn.click()
                        self.logger.info(f"  Confirmation modal 'Rebuild' clicked. ({i+1}/2)")
                        
                        # Wait a moment for the page to update after confirmation
                        time.sleep(5)

                    except TimeoutException:
                        self.logger.warning(f"  Could not find 'Rebuild' button on attempt {i+1}. The rig is likely under construction now. Breaking rebuild loop.")
                        break  # Exit the loop if the button is no longer available
                return True

            if crude_abundance is not None and crude_abundance <= 80:
                if methane_abundance is not None and methane_abundance > 80:
                    self.logger.info(f"  Crude oil <= 80, Methane > 80, clicking rebuild twice.")
                    for i in range(2):
                        try:
                            rebuild_btn = WebDriverWait(self.driver, 20).until(
                                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Rebuild') and contains(@class, 'btn-danger')]"))
                            )
                            rebuild_btn.click()
                            self.logger.info(f"  Rebuild clicked. ({i+1}/2)")

                            modal_confirm_btn = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'modal-content')]//button[contains(@class, 'btn-primary') and contains(., 'Rebuild')]"))
                            )
                            modal_confirm_btn.click()
                            self.logger.info(f"  Confirmation modal 'Rebuild' clicked. ({i+1}/2)")
                            
                            # Wait a moment for the page to update
                            time.sleep(5)

                        except TimeoutException:
                            self.logger.warning(f"  Could not find 'Rebuild' button on attempt {i+1}. The rig is likely under construction. Breaking rebuild loop.")
                            break # Exit the loop
                    return True
                else:
                    self.logger.info(f"  Crude oil <= 80, Methane <= 80 or not found, clicking rebuild once.")
                    rebuild_btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Rebuild') and contains(@class, 'btn-danger')]"))
                    )
                    rebuild_btn.click()
                    self.logger.info(f"  Rebuild clicked.")
                    # Also handle the confirmation modal for the single-click case
                    try:
                        modal_confirm_btn = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'modal-content')]//button[contains(@class, 'btn-primary') and contains(., 'Rebuild')]"))
                        )
                        modal_confirm_btn.click()
                        self.logger.info(f"  Confirmation modal 'Rebuild' clicked.")
                    except TimeoutException:
                        self.logger.warning("  Confirmation modal did not appear or Rebuild button not found in modal.")
                    
                    return True

            self.logger.info(f"  No rebuild action taken.")
            return False

        except NoSuchElementException:
            self.logger.error(f"  Abundance information not found, possibly due to page structure changes or building damage.")
            send_email_notify(
                subject="SimCompany Oil Rig Status Error",
                body=f"Oil Rig ({oilrig_url}) is not under construction, but Abundance information is missing. Please check."
            )
            return False
        except Exception as e:
            self.logger.error(f"  Error occurred while checking Abundance or Rebuild: {e}", exc_info=True)
            return False

    def _save_screenshot(self, filename_prefix):
        """Saves a screenshot for debugging."""
        screenshot_dir = 'record'
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
        filename = f'{filename_prefix}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        path = os.path.join(screenshot_dir, filename)
        try:
            if self.driver:
                self.driver.save_screenshot(path)
                print(f"[{self.name}] Screenshot saved to: {path}")
        except Exception as e:
            print(f"[{self.name}] Failed to save screenshot: {e}")

# --- All-building activity monitor ---
class BuildingConstructionMonitor(BaseMonitor):
    """Notifies Telegram when construction or product production completes."""

    def __init__(self, logger=None, user_data_dir=None, state_file_path=None, poll_seconds=None):
        super().__init__("BuildingActivity", logger=logger, user_data_dir=user_data_dir)
        self.landscape_url = f"{self.base_url}/landscape/"
        self.state_file_path = state_file_path or os.path.join("record", "building_activity_state.json")
        self.manual_recheck_seconds = self._get_manual_recheck_seconds(None)
        self.due_recheck_seconds = max(DUE_ACTIVITY_RECHECK_SECONDS, int(poll_seconds or 0))
        self.retail_profit_advisor = RetailProfitAdvisor(logger=self.logger)
        self.ignored_products = {
            product.strip().casefold()
            for product in os.getenv("TELEGRAM_IGNORED_PRODUCTS", "POWER").split(",")
            if product.strip()
        }
        self.state = self._load_state()
        self._building_paths = []
        self._next_scan_at = {}
        self._full_scan_pending = True

    @staticmethod
    def _get_manual_recheck_seconds(value):
        try:
            seconds = int(
                value if value is not None
                else os.getenv("ACTIVITY_MANUAL_RECHECK_SECONDS", str(MANUAL_ACTIVITY_RECHECK_SECONDS))
            )
            return max(60, seconds)
        except (TypeError, ValueError):
            return MANUAL_ACTIVITY_RECHECK_SECONDS

    def _load_state(self):
        default_state = {"initialized": False, "constructions": {}, "productions": {}}
        try:
            if not os.path.exists(self.state_file_path):
                return default_state
            with open(self.state_file_path, "r", encoding="utf-8") as state_file:
                state = json.load(state_file)
            if not isinstance(state.get("constructions"), dict) or not isinstance(state.get("productions"), dict):
                return default_state
            return {
                "initialized": bool(state.get("initialized")),
                "constructions": state["constructions"],
                "productions": state["productions"],
            }
        except (OSError, json.JSONDecodeError) as error:
            self.logger.warning(f"[{self.name}] Could not load activity state: {error}")
            return default_state

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_file_path) or ".", exist_ok=True)
            with open(self.state_file_path, "w", encoding="utf-8") as state_file:
                json.dump(self.state, state_file, ensure_ascii=False, indent=2)
        except OSError as error:
            self.logger.error(f"[{self.name}] Could not save activity state: {error}")

    def run(self):
        self.logger.info(f"[{self.name}] Starting all-building construction and production monitor.")
        while True:
            wait_seconds = self._process_once() or LONG_RETRY_DELAY
            self.logger.info(f"[{self.name}] Next scheduled building scan in {wait_seconds:.0f} seconds.")
            try:
                time.sleep(wait_seconds)
            except KeyboardInterrupt:
                self.logger.info(f"[{self.name}] Monitoring interrupted by user.")
                break

    def _process_once(self):
        now = time.time()
        full_scan = self._full_scan_pending
        if full_scan:
            building_paths = None
        else:
            building_paths = sorted(
                path for path, scan_at in self._next_scan_at.items()
                if scan_at <= now
            )
            if not building_paths:
                return self._next_wait_seconds(now)

        if not self._initialize_driver():
            return LONG_RETRY_DELAY
        try:
            if full_scan:
                building_paths = self._get_landscape_building_paths()
                if building_paths is None:
                    return LONG_RETRY_DELAY
                self._building_paths = list(building_paths)
                self._next_scan_at = {
                    path: scan_at for path, scan_at in self._next_scan_at.items()
                    if path in self._building_paths
                }
            inspected = {}
            for path in building_paths:
                result = self._inspect_building(path)
                if result is not None:
                    inspected[path] = result
            self._update_state_and_notify(inspected, active_paths=self._building_paths)
            scanned_at = time.time()
            for path in building_paths:
                if path in inspected:
                    self._schedule_path(path, scanned_at)
                else:
                    self._next_scan_at[path] = scanned_at + LONG_RETRY_DELAY
            if full_scan:
                self._full_scan_pending = False
            return self._next_wait_seconds()
        except Exception as error:
            self.logger.error(f"[{self.name}] Landscape scan failed: {error}", exc_info=True)
            return LONG_RETRY_DELAY
        finally:
            self._quit_driver()

    def _get_landscape_building_paths(self):
        landscape_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/landscape')]")
        if landscape_links:
            landscape_link = next((link for link in landscape_links if link.is_displayed()), landscape_links[0])
            resolved_url = landscape_link.get_attribute("href") or self.landscape_url
            self.logger.info(f"[{self.name}] Opening Landscape through authenticated navigation: {resolved_url}")
            self.driver.execute_script("arguments[0].click();", landscape_link)
        else:
            self.logger.info(f"[{self.name}] Landscape navigation link not found; opening {self.landscape_url} directly.")
            self.driver.get(self.landscape_url)
        WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        if self._check_login_required(self.landscape_url):
            return None
        building_xpath = "//*[contains(@href, '/b/') or contains(@data-href, '/b/') or @data-building-id]"
        try:
            building_elements = WebDriverWait(self.driver, 20, poll_frequency=0.5).until(
                lambda driver: driver.find_elements(By.XPATH, building_xpath)
            )
        except TimeoutException:
            current_url = self.driver.current_url
            page_title = self.driver.title
            self.logger.warning(
                f"[{self.name}] Landscape building list did not load within 20 seconds; "
                f"preserving the previous state and retrying (URL: {current_url}, title: {page_title!r})."
            )
            screenshot_path = os.path.join(
                "record", f"building_activity_landscape_timeout_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
            )
            try:
                self.driver.save_screenshot(screenshot_path)
                self.logger.info(f"[{self.name}] Landscape timeout screenshot saved to {screenshot_path}.")
            except Exception as screenshot_error:
                self.logger.warning(f"[{self.name}] Could not save Landscape timeout screenshot: {screenshot_error}")
            return None

        paths = set()
        for element in building_elements:
            target = element.get_attribute("href") or element.get_attribute("data-href") or ""
            match = re.search(r"/b/(\d+)", target)
            if not match:
                building_id = element.get_attribute("data-building-id")
                match = re.fullmatch(r"\d+", building_id or "")
                if match:
                    paths.add(f"/b/{building_id}/")
                continue
            paths.add(f"/b/{match.group(1)}/")
        self.logger.info(f"[{self.name}] Found {len(paths)} buildings on Landscape.")
        return sorted(paths)

    def _inspect_building(self, path):
        """Read construction and every product-production timer on one page."""
        building_url = self.base_url + path
        try:
            self.driver.get(building_url)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            # SimCompanies renders the production panels after the document body
            # appears. Waiting for document readiness prevents an early scan from
            # treating a still-loading building as idle.
            WebDriverWait(self.driver, 10).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            # The site now reports document readiness before the SPA has
            # fetched the building details.  Reading at that point returns
            # only "Fetching building info .." and makes an active timer look
            # absent, so wait for the actual building content instead.
            try:
                WebDriverWait(self.driver, BUILDING_CONTENT_WAIT, poll_frequency=0.5).until(
                    lambda driver: (
                        (body_text := driver.execute_script("return document.body.innerText || ''")).strip()
                        and "fetching building info" not in body_text.casefold()
                    )
                )
            except TimeoutException:
                self.logger.warning(
                    f"[{self.name}] Building details did not load for {path} within "
                    f"{BUILDING_CONTENT_WAIT} seconds; preserving prior activity state."
                )
                return None
            if "/signin" in self.driver.current_url or "/login" in self.driver.current_url:
                self.logger.warning(f"[{self.name}] Login required while inspecting {building_url}.")
                return None
            headings = self.driver.find_elements(By.TAG_NAME, "h1")
            name = headings[0].text.strip() if headings and headings[0].text.strip() else path
            # SimCompanies moved these timers from <p> into a nested <div>.
            # Match the timer's own node (rather than a parent container) so
            # each activity is read once regardless of the surrounding layout.
            finish_xpath = (
                "//*[self::p or self::div or self::span]"
                "[starts-with(normalize-space(.), 'Finishes at')]"
            )
            finish_elements = self.driver.find_elements(By.XPATH, finish_xpath)
            was_previously_active = (
                path in self.state["constructions"] or path in self.state["productions"]
            )
            if not finish_elements and was_previously_active:
                try:
                    finish_elements = WebDriverWait(
                        self.driver, ACTIVITY_PANEL_WAIT, poll_frequency=0.5
                    ).until(lambda driver: driver.find_elements(By.XPATH, finish_xpath))
                except TimeoutException:
                    self.logger.info(
                        f"[{self.name}] Previously tracked activity is not visible on {path} "
                        f"after waiting {ACTIVITY_PANEL_WAIT} seconds; completion will require confirmation."
                    )
            construction = None
            products = {}
            product_names = {}
            for index, finish_element in enumerate(finish_elements, start=1):
                finish_at = finish_element.text.replace("Finishes at", "").strip()
                preceding_headings = finish_element.find_elements(By.XPATH, "preceding::h3[1]")
                section_name = preceding_headings[0].text.strip() if preceding_headings else ""
                activity_type, activity_name = self._normalize_activity_heading(section_name)
                if activity_type == "construction":
                    construction = {"name": name, "url": building_url, "finish_at": finish_at}
                    continue
                display_name = activity_name or f"Product {index}"
                if self._is_ignored_product(display_name):
                    continue
                product_names[display_name] = product_names.get(display_name, 0) + 1
                product_key = f"{display_name}#{product_names[display_name]}"
                products[product_key] = {"name": display_name, "finish_at": finish_at}
            products = self._dedupe_products(products)
            if construction:
                self.logger.info(f"[{self.name}] {name} ({path}) construction finishes at {construction['finish_at'] or 'unknown'}.")
            for product in products.values():
                self.logger.info(f"[{self.name}] {name} ({path}) producing {product['name']} until {product['finish_at'] or 'unknown'}.")
            return {"name": name, "url": building_url, "construction": construction, "products": products}
        except Exception as error:
            self.logger.warning(f"[{self.name}] Could not inspect {building_url}: {error}")
            return None

    @staticmethod
    def _parse_time(value):
        try:
            return parser.parse(value) if value else None
        except (TypeError, ValueError, OverflowError):
            return None

    def _is_due(self, finish_at):
        finish_dt = self._parse_time(finish_at)
        if not finish_dt:
            return False
        now = datetime.datetime.now(finish_dt.tzinfo) if finish_dt.tzinfo else datetime.datetime.now()
        return finish_dt <= now

    def _is_later_time(self, old_time, new_time):
        old_dt, new_dt = self._parse_time(old_time), self._parse_time(new_time)
        return bool(old_dt and new_dt and new_dt > old_dt)

    @staticmethod
    def _normalize_activity_heading(value):
        """Return the activity type and the useful part of a SimCompanies heading."""
        lines = [line.strip() for line in (value or "").splitlines() if line.strip()]
        if not lines:
            return None, ""
        activity_type = lines[0].casefold()
        if activity_type in {"production", "selling", "construction"}:
            return activity_type, " ".join(lines[1:]).strip()
        return None, " ".join(lines)

    @classmethod
    def _timer_identity(cls, finish_at):
        parsed = cls._parse_time(finish_at)
        if parsed:
            return parsed.isoformat()
        return (finish_at or "").strip().casefold()

    @classmethod
    def _normalized_product(cls, product):
        normalized = dict(product)
        _activity_type, name = cls._normalize_activity_heading(product.get("name"))
        if name:
            normalized["name"] = name
        return normalized

    @classmethod
    def _product_name_score(cls, product):
        """Prefer a quality-specific label such as PROCESSORS Q2 over Processors."""
        name = cls._normalized_product(product).get("name", "")
        return (
            1 if re.search(r"\bQ\d+\b", name, flags=re.IGNORECASE) else 0,
            len(name),
        )

    @classmethod
    def _dedupe_products(cls, products):
        """Collapse alternate DOM labels that point at the same production timer."""
        selected = {}
        order = []
        for product_key, raw_product in products.items():
            product = cls._normalized_product(raw_product)
            timer_id = cls._timer_identity(product.get("finish_at"))
            if timer_id not in selected:
                selected[timer_id] = (product_key, product)
                order.append(timer_id)
                continue
            old_key, old_product = selected[timer_id]
            if cls._product_name_score(product) > cls._product_name_score(old_product):
                selected[timer_id] = (product_key, product)
        return {selected[timer_id][0]: selected[timer_id][1] for timer_id in order}

    def _is_ignored_product(self, product_name):
        normalized_name = (product_name or "").strip().casefold()
        return any(
            normalized_name == ignored or normalized_name.startswith(f"{ignored} ")
            for ignored in self.ignored_products
        )

    def _send_construction_notification(self, building):
        return send_telegram_notify(
            "🏗️ SimCompanies 建築完成！\n"
            f"建築：{building.get('name', 'Unknown')}\n"
            f"網址：{building.get('url', '')}",
            logger=self.logger,
        )

    def _send_production_notification(self, building, product, include_retail_advice=False):
        message = (
            "✅ SimCompanies 產品生產完成！\n"
            f"建築：{building.get('name', 'Unknown')}\n"
            f"產品：{product.get('name', 'Unknown')}\n"
            f"網址：{building.get('url', '')}"
        )
        # The target retail building is now idle.  Calculate its 48-hour
        # choices before the existing completion notification is delivered.
        if include_retail_advice and self.driver and self.retail_profit_advisor.is_target(building.get("url", "")):
            recommendations = self.retail_profit_advisor.analyse(self.driver, building.get("url", ""))
            advice = self.retail_profit_advisor.telegram_text(
                recommendations, self.retail_profit_advisor.hours
            )
            if not advice:
                details = '；'.join(self.retail_profit_advisor.errors) or '沒有可用的試算結果'
                self.logger.warning(
                    "[RetailProfitAdvisor] Profit report for %s was incomplete; "
                    "retaining completion state for retry. Errors: %s",
                    building.get("url", ""),
                    details,
                )
                return False
            message += f"\n\n資料時間：{self.retail_profit_advisor.checked_at}\n" + advice
            if self.retail_profit_advisor.errors:
                message += '\n未完成比較：' + '；'.join(self.retail_profit_advisor.errors)
        return send_telegram_notify(message, logger=self.logger)

    def _update_state_and_notify(self, inspected, active_paths=None):
        old_constructions = self.state["constructions"]
        old_productions = self.state["productions"]
        active_paths = set(inspected if active_paths is None else active_paths)
        # Preserve state when an active building temporarily fails inspection,
        # but discard records for buildings absent from a successfully loaded
        # Landscape so past timers cannot force a scan every minute forever.
        next_constructions = {
            path: value for path, value in old_constructions.items()
            if path not in inspected and path in active_paths
        }
        next_productions = {
            path: value for path, value in old_productions.items()
            if path not in inspected and path in active_paths
        }

        for path, current in inspected.items():
            old_construction = old_constructions.get(path)
            if self.state["initialized"] and old_construction and not current["construction"]:
                if not self._is_due(old_construction.get("finish_at")):
                    next_constructions[path] = old_construction
                else:
                    missing_count = int(old_construction.get("_missing_confirmations", 0)) + 1
                    if missing_count < MISSING_CONFIRMATIONS_REQUIRED:
                        pending_construction = dict(old_construction)
                        pending_construction["_missing_confirmations"] = missing_count
                        next_constructions[path] = pending_construction
                        self.logger.info(
                            f"[{self.name}] Construction timer missing for {path}; "
                            f"confirmation {missing_count}/{MISSING_CONFIRMATIONS_REQUIRED}."
                        )
                    elif not self._send_construction_notification(old_construction):
                        next_constructions[path] = old_construction
            if current["construction"]:
                next_constructions[path] = current["construction"]

            # Construction cancels production; do not report that as a completed product.
            if current["construction"]:
                continue

            current_products = self._dedupe_products(current["products"])
            old_building = old_productions.get(path)
            if self.state["initialized"] and old_building:
                old_products = self._dedupe_products(old_building.get("products", {}))
                for product_key, old_product in old_products.items():
                    if self._is_ignored_product(old_product.get("name")):
                        continue
                    current_product = current_products.get(product_key)
                    if current_product is None:
                        # The site can expose one timer under both a broad heading
                        # ("PRODUCTION / Processors") and a quality heading
                        # ("PROCESSORS Q2").  A heading change must not create a
                        # second activity or make the old one look completed.
                        old_timer_id = self._timer_identity(old_product.get("finish_at"))
                        alias_key = next(
                            (
                                key for key, product in current_products.items()
                                if self._timer_identity(product.get("finish_at")) == old_timer_id
                            ),
                            None,
                        )
                        if alias_key is not None:
                            current_product = current_products.pop(alias_key)
                            preferred_product = max(
                                (old_product, current_product), key=self._product_name_score
                            )
                            stable_product = self._normalized_product(preferred_product)
                            stable_product["finish_at"] = current_product.get("finish_at")
                            stable_product.pop("_missing_confirmations", None)
                            current_products[product_key] = stable_product
                    completed = False
                    if current_product is None:
                        if not self._is_due(old_product.get("finish_at")):
                            # A client-rendered panel can disappear temporarily.
                            # Keep its known timer until it is actually due.
                            current_products[product_key] = old_product
                        else:
                            missing_count = int(old_product.get("_missing_confirmations", 0)) + 1
                            if missing_count < MISSING_CONFIRMATIONS_REQUIRED:
                                pending_product = dict(old_product)
                                pending_product["_missing_confirmations"] = missing_count
                                current_products[product_key] = pending_product
                                self.logger.info(
                                    f"[{self.name}] Product timer {product_key} missing for {path}; "
                                    f"confirmation {missing_count}/{MISSING_CONFIRMATIONS_REQUIRED}."
                                )
                            else:
                                completed = True
                    restarted = current_product and self._is_later_time(
                        old_product.get("finish_at"), current_product.get("finish_at")
                    )
                    if completed or restarted:
                        if not self._send_production_notification(
                            old_building, old_product,
                            include_retail_advice=bool(completed and not current['products']),
                        ):
                            # Preserve the old timer so a failed Telegram request is retried.
                            current_products[product_key] = old_product

            if current_products:
                next_productions[path] = {
                    "name": current["name"], "url": current["url"], "products": current_products
                }

        self.state = {
            "initialized": True,
            "constructions": next_constructions,
            "productions": next_productions,
        }
        self._save_state()

    def _schedule_path(self, path, now=None):
        """Schedule one building at its next useful inspection time."""
        now = time.time() if now is None else now
        activities = []
        construction = self.state["constructions"].get(path)
        if construction:
            activities.append(construction)
        building = self.state["productions"].get(path)
        if building:
            activities.extend(building.get("products", {}).values())

        if not activities:
            # Idle/manual buildings are checked hourly until activity appears.
            self._next_scan_at[path] = now + self.manual_recheck_seconds
            return

        if any(activity.get("_missing_confirmations") for activity in activities):
            self._next_scan_at[path] = now + self.due_recheck_seconds
            return

        finish_epochs = []
        for activity in activities:
            finish_dt = self._parse_time(activity.get("finish_at"))
            if finish_dt:
                finish_epochs.append(finish_dt.timestamp())
        if not finish_epochs:
            self._next_scan_at[path] = now + self.due_recheck_seconds
            return

        next_finish = min(finish_epochs) + CONSTRUCTION_CHECK_BUFFER
        self._next_scan_at[path] = max(now + self.due_recheck_seconds, next_finish)

    def _next_wait_seconds(self, now=None):
        now = time.time() if now is None else now
        if not self._next_scan_at:
            return self.manual_recheck_seconds
        return max(1, min(self._next_scan_at.values()) - now)


# --- Electronics Factory (Batteries) Producer ---
class BatteryProducer(BaseMonitor):
    """Manages Electronics Factory (Batteries) production cycle."""
    def __init__(self, target_paths, logger=None, user_data_dir=None):
        super().__init__("BatteryProducer", logger=logger, user_data_dir=user_data_dir)
        self.target_paths = target_paths
        self.finish_times_file_path = os.path.join('record', 'battery_finish_times.json')
        self.battery_finish_times = self._load_finish_times()
        
        # 確保所有路徑都有紀錄，預設為 None
        for path in self.target_paths:
            if path not in self.battery_finish_times:
                self.battery_finish_times[path] = None

    def _load_finish_times(self):
        """Loads finish times for multiple buildings from the JSON file."""
        try:
            if os.path.exists(self.finish_times_file_path):
                with open(self.finish_times_file_path, 'r') as f:
                    data = json.load(f)
                loaded_times = {}
                for path, time_str in data.items():
                    if time_str:
                        try:
                            loaded_times[path] = parser.parse(time_str)
                        except (ValueError, TypeError):
                            loaded_times[path] = None
                    else:
                        loaded_times[path] = None
                self.logger.info(f"[{self.name}] Successfully loaded finish times.")
                return loaded_times
            return {path: None for path in self.target_paths}
        except Exception as e:
            self.logger.error(f"[{self.name}] Error loading finish times: {e}")
            return {path: None for path in self.target_paths}

    def _save_finish_times(self):
        """Saves finish times for multiple buildings to the JSON file."""
        try:
            os.makedirs(os.path.dirname(self.finish_times_file_path), exist_ok=True)
            data_to_save = {}
            for path, dt_obj in self.battery_finish_times.items():
                data_to_save[path] = dt_obj.isoformat() if dt_obj else None
            
            with open(self.finish_times_file_path, 'w') as f:
                json.dump(data_to_save, f, indent=4)
            self.logger.info(f"[{self.name}] Successfully saved finish times.")
        except Exception as e:
            self.logger.error(f"[{self.name}] Error saving finish times: {e}")

    def run(self):
        """Starts the continuous production loop for all battery factories."""
        self.logger.info(f"[{self.name}] Starting production loop for {len(self.target_paths)} buildings.")
        while True:
            if not self._initialize_driver():
                self.logger.error(f"[{self.name}] Failed to initialize WebDriver. Retrying after long delay.")
                time.sleep(LONG_RETRY_DELAY * 2)
                continue

            # 修改邏輯：處理到期的工廠，並返回「距離下一個完成時間」的秒數
            wait_seconds = self._process_all_battery_factories()
            self._quit_driver()

            if wait_seconds is None:
                break

            # 仿照 PowerPlant 邏輯：根據 wait_seconds 決定下次檢查時間
            effective_wait = 0
            if wait_seconds < 0: # 錯誤發生
                effective_wait = LONG_RETRY_DELAY
            elif wait_seconds == 0: # 沒事可做或全部閒置
                effective_wait = DEFAULT_RETRY_DELAY
            else:
                # 加上 Buffer，確保到期時再檢查
                effective_wait = wait_seconds + PRODUCTION_CHECK_BUFFER

            self.logger.info(f"[{self.name}] Next overall check in {effective_wait:.0f} seconds.")
            try:
                time.sleep(effective_wait)
            except KeyboardInterrupt:
                break

    def _process_all_battery_factories(self):
        """Processes all battery factories and returns the minimum wait time until the next completion."""
        now = datetime.datetime.now()
        due_paths = []
        
        # 1. 識別哪些工廠需要現在處理（已到期、60秒內到期、或沒在生產）
        process_threshold = now + datetime.timedelta(seconds=60)
        for path, finish_dt in self.battery_finish_times.items():
            if finish_dt is None or finish_dt <= process_threshold:
                due_paths.append(path)
        
        # 2. 如果沒有現在需要處理的，直接計算「離最近的未來完成時間」還有多久
        if not due_paths:
            future_times = [dt for dt in self.battery_finish_times.values() if dt and dt > now]
            if future_times:
                min_wait = min((dt - now).total_seconds() for dt in future_times)
                return max(0, min_wait)
            else:
                return 0 # 沒有任何生產紀錄

        self.logger.info(f"[{self.name}] Processing due factories: {due_paths}")
        
        # 3. 逐一處理到期的工廠
        for path in due_paths:
            building_url = self.base_url + path
            self.logger.info(f"[{self.name}] Checking/Starting: {building_url}")
            try:
                self.driver.get(building_url)
                # 等待頁面關鍵元素
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//h3[normalize-space(text())='Construction'] | //h3[contains(., 'Batteries')]"))
                )
                
                # 檢查是否施工中
                if self._check_construction_status(path):
                    continue

                # 嘗試啟動或抓取現有的生產時間
                self._check_and_start_battery_production(path)
                time.sleep(random.uniform(0.5, 1.0))

            except Exception as e:
                self.logger.error(f"[{self.name}] Error processing {path}: {e}")
                self.battery_finish_times[path] = None # 發生錯誤則下次重新檢查
        
        self._save_finish_times()
        
        # 4. 再次檢查最新的 battery_finish_times，計算「下一個到期事件」的時間間隔
        now_after = datetime.datetime.now()
        future_times = [dt for dt in self.battery_finish_times.values() if dt and dt > now_after]
        if future_times:
            min_wait = min((dt - now_after).total_seconds() for dt in future_times)
            return max(0, min_wait)
        else:
            return 0

    def _check_construction_status(self, path):
        """Checks if building is under construction and updates finish time."""
        try:
            # 偵測施工區塊
            construction_elements = self.driver.find_elements(By.XPATH, "//h3[normalize-space(text())='Construction']")
            if construction_elements:
                finish_time_p = self.driver.find_element(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
                finish_time_str = finish_time_p.text.strip().replace('Finishes at', '').strip()
                self.logger.info(f"[{self.name}] {path} is under construction. Finishes at: {finish_time_str}")
                self.battery_finish_times[path] = parser.parse(finish_time_str)
                return True
            return False
        except:
            return False

    def _check_and_start_battery_production(self, path):
        """Attempts to start max production for Batteries on the given path."""
        battery_section_xpath = "//img[@alt='Batteries']/ancestor::div[contains(@class, 'css-1ruhbe')]"
        battery_max_button_xpath = f"{battery_section_xpath}//button[normalize-space(.)='Max']"
        battery_produce_button_xpath = f"{battery_section_xpath}//button[normalize-space(.)='Produce']"
        battery_finish_time_xpath = f"//h3[contains(., 'Batteries')]/ancestor::div[contains(@class, 'row')]//p[starts-with(normalize-space(text()), 'Finishes at')]"

        try:
            # A. 檢查是否已經在生產中
            finish_time_elements = self.driver.find_elements(By.XPATH, battery_finish_time_xpath)
            if finish_time_elements and finish_time_elements[0].is_displayed():
                finish_time_str = finish_time_elements[0].text.strip()
                self.logger.info(f"[{self.name}] {path} is ALREADY PRODUCING. Finish: {finish_time_str}")
                self.battery_finish_times[path] = parser.parse(finish_time_str.replace('Finishes at', '').strip())
                return

            # B. 嘗試啟動生產
            self.logger.info(f"[{self.name}] {path} is idle. Clicking 'Max' for Batteries...")
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, battery_max_button_xpath))).click()
            time.sleep(random.uniform(0.3, 0.6))
            
            # 處理可能存在的 Produce 按鈕 (依據遊戲版本而定)
            try:
                produce_btn = self.driver.find_element(By.XPATH, battery_produce_button_xpath)
                if produce_btn.is_displayed():
                    produce_btn.click()
                    self.logger.info(f"[{self.name}] {path} 'Produce' button clicked.")
            except: pass
            
            time.sleep(2)
            
            # C. 重新整理頁面以獲取最新的完成時間（這最準確）
            self.driver.get(self.base_url + path)
            time.sleep(1)
            conf_elements = WebDriverWait(self.driver, 15).until(
                EC.presence_of_all_elements_located((By.XPATH, battery_finish_time_xpath))
            )
            if conf_elements:
                new_time_str = conf_elements[0].text.strip()
                self.logger.info(f"[{self.name}] {path} Production STARTED. New finish: {new_time_str}")
                self.battery_finish_times[path] = parser.parse(new_time_str.replace('Finishes at', '').strip())
            else:
                self.battery_finish_times[path] = None

        except Exception as e:
            self.logger.error(f"[{self.name}] Failed to start/confirm production on {path}: {e}")
            self.battery_finish_times[path] = None


# --- Main Execution ---
def main():
    """Main function to select and run monitoring tasks."""
    load_dotenv()

    print("Please select the function to execute:")
    print("1. Monitor Forest nursery production completion time")
    print("2. Batch start Power plant 24h production cycle")
    print("3. Monitor all Oil Rig construction status (auto-fetch landscape)")
    print("4. Send test email")
    choice = input("Enter a number (1/2/3/4):").strip()

    if choice == "1":
        logger_forest = setup_logger('ForestNurseryMonitor', 'monitor_forest.log')
        target_paths_forest = ["/b/43694783/"]
        user_data_dir_forest = os.getenv("USER_DATA_DIR_forestnursery")
        if not user_data_dir_forest:
            logger_forest.warning("USER_DATA_DIR_forestnursery not found in .env. Using default Chrome profile.")
        monitor = ForestNurseryMonitor(target_paths_forest, logger=logger_forest, user_data_dir=user_data_dir_forest)
        monitor.run()
    elif choice == "2":
        logger_power = setup_logger('PowerPlantProducer', 'monitor_powerplant.log')
        user_data_dir_powerplant = os.getenv("USER_DATA_DIR_powerplant")
        if not user_data_dir_powerplant:
            logger_power.warning("USER_DATA_DIR_powerplant not found in .env. Using default Chrome profile.")
        producer = PowerPlantProducer(POWER_PLANT_PATHS, logger=logger_power, user_data_dir=user_data_dir_powerplant)
        producer.run()
    elif choice == "3":
        logger_oil = setup_logger('OilRigMonitor', 'monitor_oilrig.log')
        user_data_dir_oilrig = os.getenv("USER_DATA_DIR_oiirig")
        if not user_data_dir_oilrig:
            logger_oil.warning("USER_DATA_DIR_oiirig not found in .env. Using default Chrome profile.")
        monitor = OilRigMonitor(logger=logger_oil, user_data_dir=user_data_dir_oilrig)
        monitor.run()
    elif choice == "4":
        logger = setup_logger("production_monitor.emailtest", "monitor_emailtest.log")
        logger.info("Sending test email...")
        send_email_notify(
            subject="SimCompanies Automation Tool Test Email",
            body="This is a test email from the SimCompanies automation tool.\n\nIf you receive this email, the email functionality is correctly configured."
        )
        logger.info("Test email function finished.")
    else:
        print("Invalid option, program terminated.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Program manually interrupted by user.")
    except Exception as e:
        print(f"Unexpected critical error occurred: {e}")
