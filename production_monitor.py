import os
import time
import datetime
import re
import traceback
import logging
import random
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

# --- Logging Setup ---
def setup_logger(name, log_filename):
    log_path = os.path.join('record', log_filename)
    if os.path.exists(log_path):
        os.remove(log_path)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
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
CONSTRUCTION_CHECK_BUFFER = 60 # seconds
PRODUCTION_CHECK_BUFFER = 60 # seconds
REBUILD_DELAY = 60 # seconds

# --- Ensure 'record' directory exists ---
if not os.path.exists('record'):
    os.makedirs('record')

# --- Helper Function for Beeping (Optional & Cross-Platform Safe) ---
def play_notification_sound(logger, count=3, duration=500, frequency=1000):
    """Plays a beep sound if possible (Windows only for now, safely skips otherwise)."""
    try:
        import winsound
        logger.info("Playing notification sound (Windows only).")
        for _ in range(count):
            winsound.Beep(frequency, duration)
            time.sleep(0.5)
    except ImportError:
        logger.warning("Could not import 'winsound'. Notification sounds disabled (not on Windows or module missing).")
    except Exception as e:
        logger.error(f"Error playing sound: {e}")

# --- Base Monitor Class ---
class BaseMonitor:
    """Base class for monitoring tasks."""
    def __init__(self, name, base_url=BASE_URL, logger=None, user_data_dir=None):
        self.name = name
        self.base_url = base_url
        self.driver = None
        self.logger = logger
        self.user_data_dir = user_data_dir

    def _is_logged_in(self):
        """Check if the user is already logged in by looking for login/signin links."""
        try:
            # SimCompanies: if there's a 'Sign in' or 'Login' link, not logged in
            login_btns = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/signin') or contains(@href, '/login')]")
            return not bool(login_btns)
        except Exception as e:
            self.logger.warning(f"[{self.name}] Error checking login status: {e}")
            return False

    def _initialize_driver(self):
        self.logger.info(f"[{self.name}] Initializing WebDriver with profile: {self.user_data_dir or 'default'}...")
        try:
            self.driver = initialize_driver(user_data_dir=self.user_data_dir)

            if self.driver:
                self.logger.info(f"[{self.name}] WebDriver initialized for profile: {self.user_data_dir or 'default'}.")
                self.logger.info(f"[{self.name}] Navigating to {self.base_url} for initial login check.")
                try:
                    self.driver.get(self.base_url)
                    time.sleep(2)
                    if not self._is_logged_in():
                        input(
                            f"[{self.name}] Profile: '{self.user_data_dir or 'Default'}'. "
                            f"Browser window should be open. Please ensure you are logged in at {self.base_url}. "
                            "Press Enter in this console to continue..."
                        )
                        self.logger.info(f"[{self.name}] User confirmed login check. Proceeding.")
                    else:
                        self.logger.info(f"[{self.name}] Detected already logged in, proceeding automatically.")
                    return True
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
            play_notification_sound(self.logger)
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
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//label[contains(., 'Max') and @type='button']"))
                ).click()
                time.sleep(0.5)
                nurture_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Nurture') and contains(@class, 'btn-primary')]")
                ))
                if nurture_btn.is_enabled():
                    nurture_btn.click()
                    time.sleep(1)
                    return True
            except Exception as e:
                self.logger.info(f"{target_path} Nurture attempt failed: {e}")
            return False

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

    def _try_nurture_button_only(self):
        """Tries to click Nurture button only (assumes Max already set)."""
        try:
            nurture_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Nurture') and contains(@class, 'btn-primary')]")
            ))
            if nurture_btn.is_enabled():
                nurture_btn.click()
                return True
        except Exception:
            pass
        return False

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
    def __init__(self, target_paths, logger=None, user_data_dir=None):
        super().__init__("PowerPlant", logger=logger, user_data_dir=user_data_dir)
        self.target_paths = target_paths

    def run(self):
        """Starts the continuous production loop."""
        self.logger.info(f"[{self.name}] Starting production loop.")
        while True:
            if not self._initialize_driver():
                self.logger.error(f"[{self.name}] Failed to initialize WebDriver. Retrying after long delay ({LONG_RETRY_DELAY * 2}s).")
                time.sleep(LONG_RETRY_DELAY * 2)
                continue

            wait_seconds = self._process_plants()
            self._quit_driver()

            if wait_seconds is None:
                self.logger.warning(f"[{self.name}] Critical error or user interruption in _process_plants. Stopping monitor.")
                break

            effective_wait = 0
            if wait_seconds < 0:
                self.logger.warning(f"[{self.name}] An error occurred in _process_plants. Applying delay: {-wait_seconds:.0f}s.")
                effective_wait = -wait_seconds
            elif wait_seconds == 0:
                self.logger.info(f"[{self.name}] Production likely finished for all plants or no active plants. Checking again after default delay ({DEFAULT_RETRY_DELAY}s).")
                effective_wait = DEFAULT_RETRY_DELAY
            else:
                effective_wait = wait_seconds + PRODUCTION_CHECK_BUFFER # 使用原有的緩衝
                self.logger.info(f"[{self.name}] Next check for ongoing production in {effective_wait:.0f} seconds (raw wait: {wait_seconds:.0f}s).")

            self.logger.info(f"[{self.name}] Next overall check cycle in {effective_wait:.0f} seconds.")
            try:
                time.sleep(effective_wait)
            except KeyboardInterrupt:
                self.logger.info(f"[{self.name}] Production loop interrupted by user.")
                break
            self.logger.info(f"\n[{self.name}] === Starting new production check cycle ===\n")

    def _process_plants(self):
        finish_times_collected = []
        now = datetime.datetime.now()
        error_occurred_in_cycle = False
        started_paths_in_cycle = []
        
        opened_tabs_map = {} # {path_str: window_handle_str}

        try:
            num_targets = len(self.target_paths)
            if num_targets == 0:
                self.logger.info(f"[{self.name}] No target paths configured. Skipping processing.")
                return 0

            self.logger.info(f"[{self.name}] Attempting to open {num_targets} tabs for power plants...")
            
            initial_main_window_handle = None
            try:
                initial_main_window_handle = self.driver.current_window_handle
            except WebDriverException as e:
                self.logger.error(f"[{self.name}] Could not get initial window handle: {type(e).__name__} - {e}. Aborting.")
                return -LONG_RETRY_DELAY

            for idx, target_path in enumerate(self.target_paths):
                url = self.base_url + target_path
                self.logger.info(f"[{self.name}] Opening tab {idx + 1}/{num_targets} for: {url}")
                
                try:
                    current_handles_before_open = set(self.driver.window_handles)
                    if idx == 0: 
                        if self.driver.current_url.strip('/') != url.strip('/'):
                             self.driver.get(url)
                        WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body"))) # 縮短至15s
                        opened_tabs_map[target_path] = self.driver.current_window_handle
                    else:
                        self.driver.execute_script(f"window.open('{url}', '_blank');")
                        WebDriverWait(self.driver, 10).until( # 縮短至10s
                            lambda d: len(set(d.window_handles) - current_handles_before_open) == 1
                        )
                        new_window_handle = list(set(self.driver.window_handles) - current_handles_before_open)[0]
                        self.driver.switch_to.window(new_window_handle)
                        WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body"))) # 縮短至15s
                        opened_tabs_map[target_path] = new_window_handle

                    if not self.driver.current_url.strip("/").endswith(target_path.strip("/")):
                        self.logger.warning(f"[{self.name}] Tab for {target_path} opened, but current URL is '{self.driver.current_url}'. Expected to end with '{target_path.strip('/')}'.")

                    self.logger.info(f"[{self.name}] Successfully opened and focused tab for {target_path}.")
                    time.sleep(random.uniform(0.8, 1.5)) # **縮短** 原 (1.8, 3.5)

                except WebDriverException as e_tab_open:
                    self.logger.error(f"[{self.name}] Error opening/switching to tab for {url} (Type: {type(e_tab_open).__name__}): {e_tab_open}. Skipping this plant.")
                    error_occurred_in_cycle = True
                    try: 
                        _ = self.driver.title 
                    except WebDriverException:
                        self.logger.critical(f"[{self.name}] WebDriver session seems to be dead after failing to open tab for {url}. Aborting cycle.")
                        return -LONG_RETRY_DELAY
                    if idx == 0 and not opened_tabs_map:
                         self.logger.critical(f"[{self.name}] Failed to process the very first target path {target_path}. WebDriver might be unusable.")
                         return -LONG_RETRY_DELAY
                    continue

            self.logger.info(f"[{self.name}] Finished attempting to open tabs. {len(opened_tabs_map)} tabs were mapped.")

            if error_occurred_in_cycle or len(opened_tabs_map) != num_targets:
                 self.logger.warning(f"[{self.name}] Potential issues during tab opening ({len(opened_tabs_map)}/{num_targets} successful). Checking driver health.")
                 try:
                     _ = self.driver.title
                 except WebDriverException as e_dead_driver:
                     self.logger.critical(f"[{self.name}] WebDriver session is dead BEFORE processing tabs: {e_dead_driver}. Aborting cycle.")
                     return -LONG_RETRY_DELAY
            
            for target_path in self.target_paths:
                if target_path not in opened_tabs_map:
                    self.logger.warning(f"[{self.name}] Skipping processing for {target_path} as it was not successfully opened or mapped.")
                    error_occurred_in_cycle = True
                    continue

                window_handle = opened_tabs_map[target_path]
                self.logger.info(f"[{self.name}] Processing plant: {target_path} on its tab (Handle: {window_handle})")
                
                try:
                    self.driver.switch_to.window(window_handle)
                    time.sleep(random.uniform(0.1, 0.2)) # **縮短** 原 (0.1, 0.3)
                    
                    if not self.driver.current_url.strip("/").endswith(target_path.strip("/")):
                        self.logger.warning(f"[{self.name}] Switched to tab for {target_path}, but URL is '{self.driver.current_url}'. Forcing navigation.")
                        self.driver.get(self.base_url + target_path)
                        WebDriverWait(self.driver, 15).until(EC.url_contains(target_path.split('/')[-2])) # 縮短至15s
                    WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'btn-secondary') and normalize-space(.)='Reposition']"))
                    )
                    time.sleep(random.uniform(0.2, 0.4)) # **縮短** 原 (0.5, 1.0)

                    production_started_here = self._check_and_start_production(target_path, finish_times_collected)
                    if production_started_here:
                        started_paths_in_cycle.append(target_path)
                    elif not self._get_existing_finish_time(target_path, finish_times_collected):
                        self.logger.warning(f"[{self.name}] For {target_path}: No new production started and no existing finish time found.")

                except NoSuchWindowException:
                    self.logger.error(f"[{self.name}] Window for {target_path} (Handle: {window_handle}) not found. It might have closed. Skipping.")
                    error_occurred_in_cycle = True
                    try: _ = self.driver.title
                    except WebDriverException:
                        self.logger.critical(f"[{self.name}] WebDriver session dead after NoSuchWindowException. Aborting.")
                        return -LONG_RETRY_DELAY
                    continue
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
                
                time.sleep(random.uniform(0.5, 1.0)) # **縮短** 原 (0.8, 2.0)

            if started_paths_in_cycle:
                self.logger.info(f"[{self.name}] Verification phase for {len(started_paths_in_cycle)} plants where production was attempted.")
                if not self._verify_all_producing(started_paths_in_cycle, opened_tabs_map):
                    self.logger.warning(f"[{self.name}] Some plants failed production verification after attempts to start them.")
                    error_occurred_in_cycle = True
            
            if initial_main_window_handle:
                try:
                    self.driver.switch_to.window(initial_main_window_handle)
                except NoSuchWindowException:
                    self.logger.warning(f"[{self.name}] Initial main window handle {initial_main_window_handle} no longer valid.")
                except WebDriverException as e_switch_main:
                     self.logger.warning(f"[{self.name}] Error switching back to initial main window: {e_switch_main}")

        except KeyboardInterrupt:
            self.logger.info(f"[{self.name}] Processing in _process_plants interrupted by user.")
            return None
        except WebDriverException as e_main_wd:
            self.logger.critical(f"[{self.name}] Critical WebDriver error during main plant processing loop (Type: {type(e_main_wd).__name__}): {e_main_wd}", exc_info=True)
            return -LONG_RETRY_DELAY
        except Exception as e_main:
            self.logger.critical(f"[{self.name}] Unhandled error in _process_plants: {e_main}", exc_info=True)
            return -DEFAULT_RETRY_DELAY

        min_wait_seconds = float('inf')
        earliest_finish_dt_str = "N/A"
        found_active_production = False

        if not finish_times_collected and not error_occurred_in_cycle:
             self.logger.info(f"[{self.name}] No production times collected and no errors during processing. All plants might be idle or processing attempts failed to gather time.")
             return 0

        for time_str_entry in finish_times_collected:
            try:
                actual_time_str = time_str_entry.replace('Finishes at', '').strip()
                finish_dt = parser.parse(actual_time_str)
                wait = (finish_dt - now).total_seconds()
                if wait > 0:
                    found_active_production = True
                    if wait < min_wait_seconds:
                        min_wait_seconds = wait
                        earliest_finish_dt_str = finish_dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception as e_parse_time:
                self.logger.warning(f"[{self.name}] Could not parse finish time string '{time_str_entry}': {e_parse_time}")
                error_occurred_in_cycle = True
                continue
        
        if found_active_production and min_wait_seconds != float('inf'):
            self.logger.info(f"[{self.name}] Earliest production finish time: {earliest_finish_dt_str}. Min wait: {min_wait_seconds:.0f} seconds.")
            play_notification_sound(self.logger)
            return min_wait_seconds
        else:
            self.logger.info(f"[{self.name}] No active future production found, or all parsed times were in the past.")
            return -DEFAULT_RETRY_DELAY if error_occurred_in_cycle else 0

    def _check_and_start_production(self, path, finish_times_list):
        current_building_url = self.base_url + path
        try:
            finish_time_elements = self.driver.find_elements(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
            if finish_time_elements and finish_time_elements[0].is_displayed():
                finish_time_str = finish_time_elements[0].text.strip()
                self.logger.info(f"[{self.name}] {path} is ALREADY PRODUCING. Finish time: {finish_time_str}")
                if finish_time_str not in finish_times_list: finish_times_list.append(finish_time_str)
                return False

            self.logger.info(f"[{self.name}] {path} is not producing, attempting to start 24h production...")
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='24h']"))).click()
            time.sleep(random.uniform(0.2, 0.5)) # **縮短** 原 (0.4, 0.8)

            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Produce']"))).click()
            self.logger.info(f"[{self.name}] {path} 'Produce' button clicked. Verifying production start...")
            self.driver.get(current_building_url) # 確保在正確的頁面上
            # WebDriverWait 超時維持15s，因為這一步是等待伺服器響應和頁面更新的關鍵
            confirmation_element = WebDriverWait(self.driver, 15).until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//button[normalize-space(.)='Cancel Production' and contains(@class, 'btn-secondary')]")),
                    EC.presence_of_element_located((By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]"))
                )
            )
            tag_name = confirmation_element.tag_name
            text_preview = confirmation_element.text.strip()[:30] if confirmation_element.text else ""
            self.logger.info(f"[{self.name}] {path} Production successfully STARTED or CONFIRMED by UI element: <{tag_name}>{text_preview}...")
            
            time.sleep(random.uniform(0.3, 0.7)) # **縮短** 原 (0.5,1.2)
            new_finish_time_elements = self.driver.find_elements(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
            if new_finish_time_elements and new_finish_time_elements[0].is_displayed():
                new_finish_time_str = new_finish_time_elements[0].text.strip()
                self.logger.info(f"[{self.name}] {path} New production finish time: {new_finish_time_str}")
                if new_finish_time_str not in finish_times_list: finish_times_list.append(new_finish_time_str)
            else:
                self.logger.warning(f"[{self.name}] {path} Production confirmed, but 'Finishes at' text not immediately found/updated. Will rely on next cycle if needed.")
            return True

        except TimeoutException:
            self.logger.warning(f"[{self.name}] {path} Timeout during production start/verification. Production might NOT have started.")
            try:
                error_alerts = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'alert-danger') or contains(@class, 'alert-warning')]")
                for alert in error_alerts:
                    if alert.is_displayed():
                        self.logger.warning(f"[{self.name}] {path} Found alert message on page: {alert.text.strip()}")
            except Exception: pass
            return False
        except Exception as e:
            self.logger.error(f"[{self.name}] Exception in _check_and_start_production for {path} (URL: {current_building_url}) (Type: {type(e).__name__}): {e}", exc_info=True)
            return False

    def _get_existing_finish_time(self, path, finish_times_list):
        try:
            # WebDriverWait 超時維持7s
            finish_time_elements = WebDriverWait(self.driver, 7).until(
                EC.presence_of_all_elements_located((By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]"))
            )
            if finish_time_elements and finish_time_elements[0].is_displayed():
                finish_time_str = finish_time_elements[0].text.strip()
                self.logger.info(f"[{self.name}] {path} Found existing completion time: {finish_time_str}")
                if finish_time_str not in finish_times_list:
                    finish_times_list.append(finish_time_str)
                return True
            self.logger.info(f"[{self.name}] {path} 'Finishes at' element list empty or not displayed. Assuming no active production time visible.")
            return False
        except TimeoutException:
            self.logger.info(f"[{self.name}] {path} No 'Finishes at' time found (TimeoutException). Plant is likely idle.")
            return False
        except Exception as e:
            self.logger.error(f"[{self.name}] Exception in _get_existing_finish_time for {path} (Type: {type(e).__name__}): {e}", exc_info=True)
            return False

    def _is_producing(self, path_for_log):
        try:
            # WebDriverWait 超時維持較短時間，因為這是快速檢查
            cancel_buttons = WebDriverWait(self.driver, 3).until(
                EC.presence_of_all_elements_located((By.XPATH, "//button[normalize-space(.)='Cancel Production' and contains(@class, 'btn-secondary')]"))
            )
            if cancel_buttons and cancel_buttons[0].is_displayed():
                return True
            
            finish_texts = WebDriverWait(self.driver, 2).until(
                EC.presence_of_all_elements_located((By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]"))
            )
            if finish_texts and finish_texts[0].is_displayed():
                return True
                
            return False
        except TimeoutException: # 預期內的，如果元素不存在
            return False 
        except WebDriverException as e_wd:
             self.logger.debug(f"[{self.name}] WebDriver error checking production status for {path_for_log} (likely page unresponsive): {type(e_wd).__name__}")
             return False
        except Exception as e:
            self.logger.error(f"[{self.name}] Unexpected error in _is_producing for {path_for_log} (Type: {type(e).__name__}): {e}", exc_info=False)
            return False

    def _verify_all_producing(self, started_paths, opened_tabs_map, retry_limit=2):
        if not started_paths:
            self.logger.info(f"[{self.name}] No plants were marked as 'started' in this cycle, skipping verification.")
            return True

        all_verified_successfully = True
        paths_needing_retry = list(started_paths) 

        for attempt in range(1, retry_limit + 1):
            self.logger.info(f"[{self.name}] Verification attempt {attempt}/{retry_limit} for {len(paths_needing_retry)} plant(s).")
            if not paths_needing_retry: break

            current_round_failed_paths = [] 
            for path_to_verify in list(paths_needing_retry): 
                handle_to_verify = opened_tabs_map.get(path_to_verify)
                if not handle_to_verify:
                    self.logger.error(f"[{self.name}] No valid window handle found for '{path_to_verify}' in opened_tabs_map during verification. Skipping.")
                    current_round_failed_paths.append(path_to_verify)
                    all_verified_successfully = False
                    continue
                
                try:
                    self.driver.switch_to.window(handle_to_verify)
                    time.sleep(random.uniform(0.1, 0.3)) # **縮短** 原 (0.2, 0.5)

                    if not self._is_producing(path_to_verify):
                        self.logger.warning(f"[{self.name}] VERIFICATION FAILED for '{path_to_verify}' (Attempt {attempt}). Not producing. Attempting to restart...")
                        temp_finish_times = [] 
                        if self._check_and_start_production(path_to_verify, temp_finish_times): 
                            self.logger.info(f"[{self.name}] Successfully restarted production for '{path_to_verify}' during verification.")
                            time.sleep(0.5) # **縮短** 原 1s
                            if self._is_producing(path_to_verify):
                                self.logger.info(f"[{self.name}] Confirmed '{path_to_verify}' is now producing after restart.")
                            else:
                                self.logger.error(f"[{self.name}] Restarted '{path_to_verify}', but it's STILL NOT producing.")
                                current_round_failed_paths.append(path_to_verify)
                                all_verified_successfully = False
                        else:
                            self.logger.error(f"[{self.name}] Failed to restart production for '{path_to_verify}' during verification attempt {attempt}.")
                            current_round_failed_paths.append(path_to_verify)
                            all_verified_successfully = False
                    else:
                        self.logger.info(f"[{self.name}] VERIFICATION SUCCESS for '{path_to_verify}' (Attempt {attempt}). It is producing.")
                        if path_to_verify in paths_needing_retry: paths_needing_retry.remove(path_to_verify) # 從paths_needing_retry中移除已成功的

                except NoSuchWindowException:
                    self.logger.error(f"[{self.name}] NoSuchWindowException for '{path_to_verify}' during verification. Tab might have closed. (Handle: {handle_to_verify})")
                    current_round_failed_paths.append(path_to_verify)
                    all_verified_successfully = False
                except WebDriverException as e_wd_verify:
                    self.logger.error(f"[{self.name}] WebDriver error during verification of '{path_to_verify}' (Type: {type(e_wd_verify).__name__}): {e_wd_verify}", exc_info=False)
                    current_round_failed_paths.append(path_to_verify)
                    all_verified_successfully = False
                except Exception as e_verify:
                    self.logger.error(f"[{self.name}] Unexpected error during verification of '{path_to_verify}' (Type: {type(e_verify).__name__}): {e_verify}", exc_info=True)
                    current_round_failed_paths.append(path_to_verify)
                    all_verified_successfully = False
            
            paths_needing_retry = list(set(current_round_failed_paths)) 

        if paths_needing_retry:
            self.logger.error(f"[{self.name}] After {retry_limit} verification attempts, the following plants are still NOT producing or encountered errors: {paths_needing_retry}")
            all_verified_successfully = False
        elif all_verified_successfully : 
             self.logger.info(f"[{self.name}] All initially started plants successfully verified and are producing.")
        
        return all_verified_successfully

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
                a_tags = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.TAG_NAME, "a"))
                )
                links = []
                for a in a_tags:
                    href = a.get_attribute('href')
                    if href and "/b/" in href:
                        is_oil_rig = False
                        try:
                            imgs = a.find_elements(By.TAG_NAME, "img")
                            if any('Oil rig' in img.get_attribute('alt') for img in imgs if img.get_attribute('alt')):
                                is_oil_rig = True
                            if not is_oil_rig:
                                spans = a.find_elements(By.TAG_NAME, "span")
                                if any('Oil rig' in span.text for span in spans):
                                     is_oil_rig = True
                        except StaleElementReferenceException:
                            self.logger.warning(f"[{self.name}] Stale element while checking tag {href}. Retrying...")
                            raise
                        
                        if is_oil_rig and href not in links:
                            links.append(href)

                if links:
                    self.logger.info(f"[{self.name}] Found {len(links)} Oil Rig links.")
                    return links
                else:
                    self.logger.warning(f"[{self.name}] No Oil Rig links found on attempt {attempt + 1}.")
                    if attempt == max_attempts - 1:
                        self._save_screenshot("no_oil_rigs_found")
                        send_email_notify(
                           subject="SimCompany Oil Rig Monitoring Error - No Buildings Found",
                           body=f"No Oil Rig buildings found on the landscape page ({self.landscape_url})."
                        )

                self.driver.refresh()

            except StaleElementReferenceException:
                self.logger.warning(f"[{self.name}] StaleElementReferenceException during link collection (Attempt {attempt + 1}). Refreshing...")
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
                crude_img = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//img[@alt='Crude oil']"))
                )
                row_div = crude_img
                for _ in range(5):
                    row_div = WebDriverWait(row_div, 2).until(
                        EC.presence_of_element_located((By.XPATH, ".."))
                    )
                    if 'row' in row_div.get_attribute('class'):
                        break
                abundance_span = WebDriverWait(row_div, 2).until(
                    EC.presence_of_element_located((By.XPATH, ".//span[contains(text(), 'Abundance:')]"))
                )
                match = re.search(r'Abundance:\s*([\d.]+)', abundance_span.text)
                if match:
                    crude_abundance = float(match.group(1))
            except Exception:
                self.logger.error("  Crude oil abundance not found!")
                return False

            try:
                methane_img = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//img[@alt='Methane']"))
                )
                row_div = methane_img
                for _ in range(5):
                    row_div = WebDriverWait(row_div, 2).until(
                        EC.presence_of_element_located((By.XPATH, ".."))
                    )
                    if 'row' in row_div.get_attribute('class'):
                        break
                abundance_span = WebDriverWait(row_div, 2).until(
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
                    rebuild_btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Rebuild') and contains(@class, 'btn-danger')]"))
                    )
                    rebuild_btn.click()
                    self.logger.info(f"  Rebuild clicked. ({i+1}/2)")
                    try:
                        modal = WebDriverWait(self.driver, 3).until(
                            EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal-body')]"))
                        )
                        confirm_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-primary') and contains(., 'Rebuild')]"))
                        )
                        confirm_btn.click()
                        self.logger.info(f"  Confirmation modal 'Rebuild' clicked. ({i+1}/2)")
                        time.sleep(1)
                    except TimeoutException:
                        self.logger.warning("  Confirmation modal did not appear or Rebuild button not found.")
                        break
                time.sleep(2)
                return True

            if crude_abundance is not None and crude_abundance <= 80:
                if methane_abundance is not None and methane_abundance > 80:
                    self.logger.info(f"  Crude oil <= 80, Methane > 80, clicking rebuild twice.")
                    for i in range(2):
                        rebuild_btn = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Rebuild') and contains(@class, 'btn-danger')]"))
                        )
                        rebuild_btn.click()
                        self.logger.info(f"  Rebuild clicked. ({i+1}/2)")
                        try:
                            modal = WebDriverWait(self.driver, 3).until(
                                EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal-body')]"))
                            )
                            confirm_btn = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-primary') and contains(., 'Rebuild')]"))
                            )
                            confirm_btn.click()
                            self.logger.info(f"  Confirmation modal 'Rebuild' clicked. ({i+1}/2)")
                            time.sleep(1)
                        except TimeoutException:
                            self.logger.warning("  Confirmation modal did not appear or Rebuild button not found.")
                            break
                    time.sleep(2)
                    return True
                else:
                    self.logger.info(f"  Crude oil <= 80, Methane <= 80 or not found, clicking rebuild once.")
                    rebuild_btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Rebuild') and contains(@class, 'btn-danger')]"))
                    )
                    rebuild_btn.click()
                    self.logger.info(f"  Rebuild clicked.")
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
        pp_paths = [
            "/b/40253730/", "/b/39825683/", "/b/39888395/", "/b/39915579/",
            "/b/43058380/", "/b/39825725/", "/b/39825679/", "/b/39693844/",
            "/b/39825691/", "/b/39825676/", "/b/39825686/", "/b/41178098/",
        ]
        user_data_dir_powerplant = os.getenv("USER_DATA_DIR_powerplant")
        if not user_data_dir_powerplant:
            logger_power.warning("USER_DATA_DIR_powerplant not found in .env. Using default Chrome profile.")
        producer = PowerPlantProducer(pp_paths, logger=logger_power, user_data_dir=user_data_dir_powerplant)
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