import os
import time
import datetime
import re
import traceback
import logging
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
    def __init__(self, target_paths, logger=None, user_data_dir=None):
        super().__init__("PowerPlant", logger=logger, user_data_dir=user_data_dir)
        self.target_paths = target_paths
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
                for path, time_str in data.items():
                    if time_str:
                        try:
                            loaded_times[path] = parser.parse(time_str)
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
            
            with open(self.finish_times_file_path, 'w') as f:
                json.dump(data_to_save, f, indent=4)
            self.logger.info(f"[{self.name}] Successfully saved finish times to {self.finish_times_file_path}")
        except IOError as e:
            self.logger.error(f"[{self.name}] Error saving finish times to {self.finish_times_file_path}: {e}")
        except Exception as e:
            self.logger.error(f"[{self.name}] Unexpected error saving finish times: {e}", exc_info=True)

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
        now = datetime.datetime.now()
        error_occurred_in_cycle = False
        started_paths_in_cycle = []
        opened_tabs_map = {}
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
            num_targets = len(due_paths)
            if num_targets == 0:
                self.logger.info(f"[{self.name}] No due plants configured. Skipping processing.")
                return 0
            self.logger.info(f"[{self.name}] Attempting to open {num_targets} tabs for due power plants...")
            initial_main_window_handle = None
            try:
                initial_main_window_handle = self.driver.current_window_handle
            except WebDriverException as e:
                self.logger.error(f"[{self.name}] Could not get initial window handle: {type(e).__name__} - {e}. Aborting.")
                return -LONG_RETRY_DELAY
            for idx, target_path in enumerate(due_paths):
                url = self.base_url + target_path
                self.logger.info(f"[{self.name}] Opening tab {idx + 1}/{num_targets} for: {url}")
                try:
                    current_handles_before_open = set(self.driver.window_handles)
                    if idx == 0:
                        if self.driver.current_url.strip('/') != url.strip('/'):
                            self.driver.get(url)
                        WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                        opened_tabs_map[target_path] = self.driver.current_window_handle
                    else:
                        self.driver.execute_script(f"window.open('{url}', '_blank');")
                        WebDriverWait(self.driver, 10).until(
                            lambda d: len(set(d.window_handles) - current_handles_before_open) == 1
                        )
                        new_window_handle = list(set(self.driver.window_handles) - current_handles_before_open)[0]
                        self.driver.switch_to.window(new_window_handle)
                        WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                        opened_tabs_map[target_path] = new_window_handle
                    if not self.driver.current_url.strip("/").endswith(target_path.strip("/")):
                        self.logger.warning(f"[{self.name}] Tab for {target_path} opened, but current URL is '{self.driver.current_url}'. Expected to end with '{target_path.strip('/')}'.")
                    self.logger.info(f"[{self.name}] Successfully opened and focused tab for {target_path}.")
                    time.sleep(random.uniform(0.8, 1.5))
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
            for target_path in due_paths:
                if target_path not in opened_tabs_map:
                    self.logger.warning(f"[{self.name}] Skipping processing for {target_path} as it was not successfully opened or mapped.")
                    error_occurred_in_cycle = True
                    continue
                window_handle = opened_tabs_map[target_path]
                self.logger.info(f"[{self.name}] Processing plant: {target_path} on its tab (Handle: {window_handle})")
                try:
                    self.driver.switch_to.window(window_handle)
                    time.sleep(random.uniform(0.1, 0.2))
                    if not self.driver.current_url.strip("/").endswith(target_path.strip("/")):
                        self.logger.warning(f"[{self.name}] Switched to tab for {target_path}, but URL is '{self.driver.current_url}'. Forcing navigation.")
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
                time.sleep(random.uniform(0.5, 1.0))
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
            self._save_finish_times()
            return -LONG_RETRY_DELAY
        except Exception as e_main:
            self.logger.critical(f"[{self.name}] Unhandled error in _process_plants: {e_main}", exc_info=True)
            self._save_finish_times()
            return -DEFAULT_RETRY_DELAY
        
        self._save_finish_times()

        # 計算下次最早的完成時間
        now = datetime.datetime.now()
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
                finish_time_elements = self.driver.find_elements(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
                if finish_time_elements and finish_time_elements[0].is_displayed():
                    finish_time_str = finish_time_elements[0].text.strip()
                    self.logger.info(f"[{self.name}] {path} is ALREADY PRODUCING. Finish time: {finish_time_str}")
                    try:
                        finish_dt = parser.parse(finish_time_str.replace('Finishes at', '').strip())
                        self.plant_finish_times[path] = finish_dt
                    except Exception:
                        self.plant_finish_times[path] = None
                    return False
                self.logger.info(f"[{self.name}] {path} is not producing, attempting to start 24h production... (attempt {attempt}/{max_retries})")
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='24h']"))).click()
                time.sleep(random.uniform(0.2, 0.5))
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Produce']"))).click()
                self.logger.info(f"[{self.name}] {path} 'Produce' button clicked. Verifying production start... (attempt {attempt}/{max_retries})")
                time.sleep(random.uniform(0.5, 0.7))
                self.driver.get(current_building_url)
                confirmation_element = WebDriverWait(self.driver, 15).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, "//button[normalize-space(.)='Cancel Production' and contains(@class, 'btn-secondary')]")),
                        EC.presence_of_element_located((By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
                        )
                    )
                )
                tag_name = confirmation_element.tag_name
                text_preview = confirmation_element.text.strip()[:30] if confirmation_element.text else ""
                self.logger.info(f"[{self.name}] {path} Production successfully STARTED or CONFIRMED by UI element: <{tag_name}>{text_preview}...")
                time.sleep(random.uniform(0.3, 0.7))
                new_finish_time_elements = self.driver.find_elements(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
                if new_finish_time_elements and new_finish_time_elements[0].is_displayed():
                    new_finish_time_str = new_finish_time_elements[0].text.strip()
                    try:
                        finish_dt = parser.parse(new_finish_time_str.replace('Finishes at', '').strip())
                        self.plant_finish_times[path] = finish_dt
                    except Exception:
                        self.plant_finish_times[path] = None
                    self.logger.info(f"[{self.name}] {path} New production finish time: {new_finish_time_str}")
                else:
                    self.logger.warning(f"[{self.name}] {path} Production confirmed, but 'Finishes at' text not immediately found/updated. Will rely on next cycle if needed.")
                    self.plant_finish_times[path] = None
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
                    from email_utils import send_email_notify
                    subject = f"[SimCompany PowerPlant] 連續{max_retries}次啟動生產失敗通知 ({path})"
                    body = f"PowerPlant {path} 連續{max_retries}次點擊生產按鈕皆失敗，請手動檢查。\nURL: {current_building_url}"
                    send_email_notify(subject, body)
                    self.logger.error(f"[{self.name}] {path} Failed to start production after {max_retries} attempts. Notification email sent.")
                    self.plant_finish_times[path] = None
                    return False
            except Exception as e:
                self.logger.error(f"[{self.name}] Exception in _check_and_start_production for {path} (URL: {current_building_url}) (Type: {type(e).__name__}): {e}", exc_info=True)
                self.plant_finish_times[path] = None
                return False

    def _get_existing_finish_time(self, path):
        """Gets existing finish time and updates self.plant_finish_times."""
        try:
            finish_time_elements = WebDriverWait(self.driver, 7).until(
                EC.presence_of_all_elements_located((By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
            ))
            if finish_time_elements and finish_time_elements[0].is_displayed():
                finish_time_str = finish_time_elements[0].text.strip()
                self.logger.info(f"[{self.name}] {path} Found existing completion time: {finish_time_str}")
                try:
                    finish_dt = parser.parse(finish_time_str.replace('Finishes at', '').strip())
                    self.plant_finish_times[path] = finish_dt
                except Exception:
                    self.plant_finish_times[path] = None
                return True
            self.logger.info(f"[{self.name}] {path} 'Finishes at' element list empty or not displayed. Assuming no active production time visible.")
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