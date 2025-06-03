import os
import time
import datetime
import re
import traceback
import logging
from dateutil import parser
from dotenv import load_dotenv

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException
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
                    self.logger.warning(f"{target_path} Not enough resources, attempting to click 'Cut down'.")
                    if self._click_cutdown(target_path):
                        return self._retry_nurture_until_success(target_path)
                except TimeoutException:
                    # Check if Nurture succeeded
                    if self._check_cancel_nurturing():
                        self.logger.info(f"{target_path} Nurture started successfully after Max.")
                        return "NURTURED"
                    else:
                        self.logger.warning(f"{target_path} Nurture did not start, retrying...")
                        return self._retry_nurture_until_success(target_path)
            else:
                # Could not find Nurture button, check for resource errors
                error_elements_5 = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Not enough input resources of quality 5 available')]")
                error_elements_water = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Water missing')]")
                if error_elements_5 or error_elements_water:
                    msg = "'Not enough input resources of quality 5 available'" if error_elements_5 else "'Water missing'"
                    self.logger.warning(f"{target_path} Detected {msg}, attempting to click 'Cut down'.")
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
            WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"))
            ).click()
            time.sleep(1)
            WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'modal-content')]//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"))
            ).click()
            self.logger.info(f"{target_path} 'Cut down' clicked. Will retry Nurture.")
            time.sleep(2)
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
            wait_seconds = self._process_plants()
            if wait_seconds is None:
                self.logger.warning(f"[{self.name}] No valid wait time returned. Stopping.")
                break
            if wait_seconds <= 0:
                self.logger.info(f"[{self.name}] Production likely finished, checking again soon.")
                wait_seconds = DEFAULT_RETRY_DELAY # If all finished, wait a bit before re-checking
            
            self.logger.info(f"[{self.name}] Next check in {wait_seconds:.0f} +60 seconds.")
            try:
                time.sleep(wait_seconds + 60)
            except KeyboardInterrupt:
                self.logger.info(f"[{self.name}] Production loop interrupted by user.")
                break
            self.logger.info(f"\n[{self.name}] === Starting new production cycle ===\n")

    def _process_plants(self):
        """Processes all target power plants once and returns max wait time."""
        if not self._initialize_driver():
            return LONG_RETRY_DELAY

        finish_times = []
        now = datetime.datetime.now()
        error_occurred = False

        try:
            # Open all tabs first
            for idx, target_path in enumerate(self.target_paths):
                url = self.base_url + target_path
                if idx == 0:
                    self.driver.get(url)
                else:
                    self.driver.execute_script(f"window.open('{url}', '_blank');")
                time.sleep(0.3)

            handles = self.driver.window_handles  # Always refresh handles after (re)opening tabs
            for idx in range(len(handles)):
                retry_count = 0
                while retry_count < 2:  # Try at most twice per tab
                    try:
                        self.driver.switch_to.window(self.driver.window_handles[idx])  # Use fresh handles
                        current_path = self.target_paths[idx]  # Assuming order matches
                        self.logger.info(f"[{self.name}] Processing: {current_path}")
                        WebDriverWait(self.driver, 20).until(
                            EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'btn-secondary') and normalize-space(.)='Reposition']"))
                        )
                        time.sleep(0.5)

                        if not self._check_and_start_production(current_path, finish_times):
                            self._get_existing_finish_time(current_path, finish_times)
                        break  # Success, break retry loop
                    except (WebDriverException, ConnectionResetError, Exception) as e_wd:
                        self.logger.error(f"[{self.name}] WebDriver/connection error processing tab {idx} (attempt {retry_count+1}): {e_wd}", exc_info=True)
                        retry_count += 1
                        if retry_count < 2:
                            self.logger.info(f"[{self.name}] Attempting to re-initialize driver and retry tab {idx}...")
                            try:
                                self._quit_driver()
                            except Exception:
                                pass
                            if not self._initialize_driver():
                                self.logger.error(f"[{self.name}] Failed to re-initialize driver on retry.")
                                error_occurred = True
                                break
                            # Re-open all tabs up to current
                            for reopen_idx in range(idx+1):
                                url = self.base_url + self.target_paths[reopen_idx]
                                if reopen_idx == 0:
                                    self.driver.get(url)
                                else:
                                    self.driver.execute_script(f"window.open('{url}', '_blank');")
                                time.sleep(0.3)
                            # Refresh handles after re-opening
                            handles = self.driver.window_handles
                        else:
                            error_occurred = True
                            break
        except KeyboardInterrupt:
            self.logger.info(f"[{self.name}] Processing interrupted by user.")
            self._quit_driver()
            return None
        except Exception as e_main:
            self.logger.critical(f"[{self.name}] Unhandled error in processing loop: {e_main}", exc_info=True)
            error_occurred = True
        finally:
            # After main production attempt, verify all are producing
            self._verify_all_producing(retry_limit=2)
            self._quit_driver()

        if error_occurred:
            return DEFAULT_RETRY_DELAY * 5

        

        # Calculate min wait time
        min_wait = None
        min_time_str = "N/A"
        for ft_str in finish_times:
            try:
                time_str = ft_str.replace('Finishes at', '').strip()
                finish_dt = parser.parse(time_str)
                wait = (finish_dt - now).total_seconds()
                if wait > 0 and (min_wait is None or wait < min_wait):
                    min_wait = wait
                    min_time_str = ft_str
            except Exception:
                continue

        if min_wait is not None and min_wait > 0:
            self.logger.info(f"[{self.name}] Min wait time: {min_wait:.0f} seconds (Until: {min_time_str}).")
            play_notification_sound(self.logger)
            return min_wait
        else:
            self.logger.info(f"[{self.name}] No production currently running or all finished.")
            return 0 # Indicate immediate recheck (loop will add delay)

    def _check_and_start_production(self, path, finish_times):
        """Checks if production is running, if not, starts 24h production."""
        try:
            # Check if 'Finishes at' exists
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]"))
            )
            self.logger.info(f"{path} is already producing.")
            return False # Already producing, will try to get time later
        except NoSuchElementException:
            # Not producing, try to start
            try:
                self.logger.info(f"{path} is not producing, attempting to start 24h production...")
                WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., '24h')]"))
                ).click()
                WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Produce')]"))
                ).click()
                self.logger.info(f"{path} 'Produce' button clicked. Verifying production status...")
                time.sleep(2) # Wait for page to update

                # Navigate back to the building page to verify
                building_url = self.base_url + path
                self.logger.info(f"Navigating back to {building_url} to verify production status.")
                self.driver.get(building_url)
                time.sleep(2) # Allow page to load

                # Verify if "Cancel Production" button is present
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, "//button[normalize-space(.)='Cancel Production' and contains(@class, 'btn-secondary')]"))
                    )
                    self.logger.info(f"{path} Production successfully started (Cancel Production button found).")
                    self._get_existing_finish_time(path, finish_times) # Get time after starting
                    return True # Started production
                except TimeoutException:
                    self.logger.warning(f"{path} Failed to confirm production start. 'Cancel Production' button not found after timeout.")
                    return False
                except Exception as e_verify:
                    self.logger.error(f"{path} Error verifying production start: {e_verify}")
                    return False

            except Exception as e_start:
                self.logger.error(f"Failed to start production for {path}: {e_start}")
                return False

    def _get_existing_finish_time(self, path, finish_times):
        """Gets the 'Finishes at' time if it exists."""
        try:
            p_tags = WebDriverWait(self.driver, 5).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, 'p'))
            )
            for p in p_tags:
                if p.text.strip().startswith('Finishes at'):
                    finish_time = p.text.strip()
                    self.logger.info(f"{path} Completion time: {finish_time}")
                    finish_times.append(finish_time)
                    return True
            self.logger.warning(f"{path} No completion time found.")
            return False
        except Exception as e:
            self.logger.error(f"Failed to fetch completion time for {path}: {e}")
            return False

    def _is_producing(self, path):
        """Checks if the power plant at the given path is producing (Cancel Production button present)."""
        try:
            self.driver.get(self.base_url + path)
            WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, "//button[normalize-space(.)='Cancel Production' and contains(@class, 'btn-secondary')]"))
                    )
            return True
        except NoSuchElementException:
            return False
        except Exception as e:
            self.logger.error(f"Error checking production status for {path}: {e}")
            return False

    def _verify_all_producing(self, retry_limit=2):
        """Verifies all power plants are producing. Retries starting production if not."""
        for attempt in range(1, retry_limit+1):
            not_producing = []
            for idx, path in enumerate(self.target_paths):
                self.driver.switch_to.window(self.driver.window_handles[idx])
                if not self._is_producing(path):
                    self.logger.warning(f"{path} is NOT producing after attempt {attempt}. Retrying start...")
                    self._check_and_start_production(path, [])
                    not_producing.append(path)
                else:
                    self.logger.info(f"{path} is confirmed producing.")
            if not not_producing:
                self.logger.info("All power plants are confirmed producing.")
                return True
            else:
                self.logger.warning(f"Retrying for {len(not_producing)} plants not producing. Attempt {attempt}/{retry_limit}.")
        if not_producing:
            self.logger.error(f"After {retry_limit} retries, the following plants are still NOT producing: {not_producing}")
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
                    try:
                        modal = WebDriverWait(self.driver, 3).until(
                            EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal-body')]"))
                        )
                        confirm_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-primary') and contains(., 'Rebuild')]"))
                        )
                        confirm_btn.click()
                        self.logger.info(f"  Confirmation modal 'Rebuild' clicked.")
                        time.sleep(1)
                    except TimeoutException:
                        self.logger.warning("  Confirmation modal did not appear or Rebuild button not found.")
                    time.sleep(2)
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