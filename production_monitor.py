import os
import time
import datetime
import re
import traceback
import logging
from dateutil import parser

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
LONG_RETRY_DELAY = 3600 # seconds (1 hour)
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
    def __init__(self, name, base_url=BASE_URL, logger=None):
        self.name = name
        self.base_url = base_url
        self.driver = None
        self.logger = logger

    def _initialize_driver(self):
        self.logger.info(f"[{self.name}] Initializing WebDriver...")
        try:
            self.driver = initialize_driver()
            if self.driver:
                self.logger.info(f"[{self.name}] WebDriver initialized successfully.")
                return True
            else:
                self.logger.error(f"[{self.name}] Failed to initialize WebDriver after all attempts.")
                return False
        except Exception as e:
            self.logger.critical(f"[{self.name}] Critical error during WebDriver initialization: {e}", exc_info=True)
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
    def __init__(self, target_paths, logger=None):
        super().__init__("ForestNursery", logger=logger)
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

            self._save_finish_times(production_finish_times)

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
            self.driver.find_element(By.XPATH, "//h3[normalize-space(text())='Construction']")
            finish_time_p = self.driver.find_element(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
            finish_time_str = finish_time_p.text.strip().replace('Finishes at', '').strip()
            self.logger.info(f"{target_path} is under construction, expected completion time: {finish_time_str}")
            finish_dt = parser.parse(finish_time_str)
            construction_finish_times.append(finish_dt)
            return True
        except NoSuchElementException:
            self.logger.info(f"{target_path} is not under construction, checking production status...")
            return False
        except Exception as e:
            self.logger.error(f"Error occurred while checking construction status for {target_path}: {e}", exc_info=True)
            return False

    def _try_nurture_or_cutdown(self, target_path):
        """Tries to click Max and Nurture, handles resource errors by cutting down. Also checks for 'Not enough input resources of quality 5 available' or 'Water missing' if Nurture/Max not found."""
        try:
            WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//label[contains(., 'Max') and @type='button']"))
            ).click()
            time.sleep(0.5)

            nurture_btn = WebDriverWait(self.driver, 10).until( # Reduced wait
               EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Nurture') and contains(@class, 'btn-primary')]"))
            )
            if nurture_btn.is_enabled():
                nurture_btn.click()
                time.sleep(1)

                try: # Check for "Not enough input resources"
                    WebDriverWait(self.driver, 2).until(
                        EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'Not enough input resources')]"))
                    )
                    self.logger.warning(f"{target_path} Not enough resources, attempting to click 'Cut down'.")
                    WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"))
                    ).click()
                    time.sleep(1)
                    WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'modal-content')]//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"))
                    ).click()
                    self.logger.info(f"{target_path} 'Cut down' clicked. Restarting monitoring.")
                    return "RESTART"
                except TimeoutException:
                    self.logger.info(f"{target_path} Automatically clicked Max and started Nurture.")
                    # Navigate back if needed, as Nurture might redirect
                    current_url = self.driver.current_url
                    if target_path not in current_url:
                        self.logger.info(f"After Nurture, navigating back to {self.base_url + target_path}")
                        self.driver.get(self.base_url + target_path)
                        time.sleep(3)
                    return "NURTURED"

        except TimeoutException:
            self.logger.info(f"{target_path} Could not find Nurture or Max button, checking for resource errors before expected completion time.")
            # 檢查是否有 "Not enough input resources of quality 5 available" 或 "Water missing"
            try:
                error_elements_5 = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Not enough input resources of quality 5 available')]")
                error_elements_water = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Water missing')]")
                if error_elements_5 or error_elements_water:
                    msg = "'Not enough input resources of quality 5 available'" if error_elements_5 else "'Water missing'"
                    self.logger.warning(f"{target_path} Detected {msg}, attempting to click 'Cut down'.")
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"))
                        ).click()
                        time.sleep(1)
                        WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'modal-content')]//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"))
                        ).click()
                        self.logger.info(f"{target_path} 'Cut down' clicked due to resource error. Restarting monitoring.")
                        return "RESTART"
                    except Exception as e:
                        self.logger.error(f"{target_path} Failed to click 'Cut down' after resource error: {e}", exc_info=True)
                else:
                    self.logger.info(f"{target_path} No 'Not enough input resources of quality 5 available' or 'Water missing' message found.")
            except Exception as e:
                self.logger.error(f"{target_path} Error while checking for resource error: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Error occurred while trying Nurture/Cut down for {target_path}: {e}", exc_info=True)
        return "NONE"


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
                all_p_tags = self.driver.find_elements(By.TAG_NAME, 'p')
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


    def _save_finish_times(self, production_finish_times):
        """Saves production finish times to a file."""
        try:
            with open('record/finish_time.txt', 'w', encoding='utf-8') as f:
                for dt in production_finish_times:
                    f.write(f"{dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.logger.info("Finish times saved to record/finish_time.txt")
        except Exception as e:
            self.logger.error(f"Failed to save finish times: {e}")

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
    def __init__(self, target_paths, logger=None):
        super().__init__("PowerPlant", logger=logger)
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

            handles = self.driver.window_handles
            self.logger.info(f"[{self.name}] Opened {len(handles)} tabs.")

            # Process each tab
            for idx, handle in enumerate(handles):
                try:
                    self.driver.switch_to.window(handle)
                    current_path = self.target_paths[idx] # Assuming order matches
                    self.logger.info(f"[{self.name}] Processing: {current_path}")
                    WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'btn-secondary') and normalize-space(.)='Reposition']"))
                    )
                    time.sleep(0.5)

                    if not self._check_and_start_production(current_path, finish_times):
                        self._get_existing_finish_time(current_path, finish_times)

                except WebDriverException as e_wd:
                     self.logger.error(f"[{self.name}] WebDriver error processing tab {idx}: {e_wd}", exc_info=True)
                     error_occurred = True
                     break # Stop processing tabs on major error
                except Exception as e_tab:
                    self.logger.error(f"[{self.name}] Error processing tab {idx}: {e_tab}", exc_info=True)
                    error_occurred = True

        except KeyboardInterrupt:
            self.logger.info(f"[{self.name}] Processing interrupted by user.")
            return None
        except Exception as e_main:
            self.logger.critical(f"[{self.name}] Unhandled error in processing loop: {e_main}", exc_info=True)
            error_occurred = True
        finally:
            self._quit_driver()

        if error_occurred:
            return DEFAULT_RETRY_DELAY * 5

        # Calculate max wait time
        max_wait = 0
        max_time_str = "N/A"
        for ft_str in finish_times:
            try:
                time_str = ft_str.replace('Finishes at', '').strip()
                finish_dt = parser.parse(time_str)
                wait = (finish_dt - now).total_seconds()
                if wait > max_wait:
                    max_wait = wait
                    max_time_str = ft_str
            except Exception:
                continue

        if max_wait > 0:
            self.logger.info(f"[{self.name}] Max wait time: {max_wait:.0f} seconds (Until: {max_time_str}).")
            play_notification_sound(self.logger)
            return max_wait
        else:
            self.logger.info(f"[{self.name}] No production currently running or all finished.")
            return 0 # Indicate immediate recheck (loop will add delay)

    def _check_and_start_production(self, path, finish_times):
        """Checks if production is running, if not, starts 24h production."""
        try:
            # Check if 'Finishes at' exists
            self.driver.find_element(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
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
                self.logger.info(f"{path} Automatically started 24h production!")
                time.sleep(2) # Wait for finish time to appear
                self._get_existing_finish_time(path, finish_times) # Get time after starting
                return True # Started production
            except Exception as e_start:
                self.logger.error(f"Failed to start production for {path}: {e_start}")
                return False

    def _get_existing_finish_time(self, path, finish_times):
        """Gets the 'Finishes at' time if it exists."""
        try:
            p_tags = self.driver.find_elements(By.TAG_NAME, 'p')
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


# --- Oil Rig Monitor ---
class OilRigMonitor(BaseMonitor):
    """Monitors Oil Rig construction and abundance, handles rebuilds."""
    def __init__(self, logger=None):
        super().__init__("OilRig", logger=logger)
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
                 # If wait_seconds is 0, it means no construction found.
                 # If negative, it was an error code, use long delay.
                 if wait_seconds == 0:
                     self.logger.info(f"[{self.name}] No active construction found. Exiting normally.")
                     return # Exit the loop normally
                 else:
                     time.sleep(LONG_RETRY_DELAY) # Long wait on errors

            self.logger.info(f"\n[{self.name}] === Starting new check cycle ===\n")


    def _process_rigs(self):
        """Processes all oil rigs once and returns wait time or None."""
        if not self._initialize_driver():
            return -LONG_RETRY_DELAY # Negative indicates error wait

        min_wait_seconds = None
        now_for_parsing = datetime.datetime.now()
        action_taken = False # Did we rebuild?
        error_occurred = False

        try:
            oilrig_links = self._get_oilrig_links()
            if not oilrig_links:
                return -LONG_RETRY_DELAY # Wait long if no links found (likely error/login issue)

            for oilrig_url in oilrig_links:
                if action_taken: break # Restart if we rebuilt one

                self.logger.info(f"[{self.name}] Checking: {oilrig_url}")
                self.driver.get(oilrig_url)
                WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                try:
                    # Check Construction
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
                    if self._check_and_rebuild_oilrig(oilrig_url):
                        action_taken = True # Rebuild started, need to restart loop

                except Exception as e_constr:
                    self.logger.error(f"  Error occurred while checking construction status for {oilrig_url}: {e_constr}", exc_info=True)
                    error_occurred = True

                time.sleep(1) # Small delay between checks

        except KeyboardInterrupt:
            self.logger.info(f"[{self.name}] Processing interrupted by user.")
            return None # Signal to stop
        except Exception as e_main:
            self.logger.critical(f"[{self.name}] Unhandled error in processing loop: {e_main}", exc_info=True)
            error_occurred = True
        finally:
            self._quit_driver()

        if action_taken:
            self.logger.info(f"[{self.name}] Rebuild started. Restarting check after {REBUILD_DELAY}s.")
            return REBUILD_DELAY

        if error_occurred:
            return -DEFAULT_RETRY_DELAY * 5 # Negative indicates error wait

        if min_wait_seconds is not None:
            self.logger.info(f"[{self.name}] Earliest construction completion requires waiting {min_wait_seconds:.0f} seconds.")
            return min_wait_seconds + CONSTRUCTION_CHECK_BUFFER

        self.logger.info(f"[{self.name}] No construction or rebuild needed for Oil Rigs.")
        return 0 # 0 indicates nothing to wait for, exit loop


    def _get_oilrig_links(self):
        """Gets all Oil Rig links from the landscape page with retries."""
        self.logger.info(f"[{self.name}] Entering {self.landscape_url} to find Oil Rigs...")
        self.driver.get(self.landscape_url)

        if self._check_login_required(self.landscape_url):
            return None # Exit if login is needed

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
                time.sleep(5) # Allow dynamic content to load

                a_tags = self.driver.find_elements(By.TAG_NAME, "a")
                links = []
                for a in a_tags:
                    href = a.get_attribute('href')
                    if href and "/b/" in href:
                        # Check for 'Oil rig' in alt text or span
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
                            raise # Trigger retry
                        
                        if is_oil_rig and href not in links:
                            links.append(href)

                if links:
                    self.logger.info(f"[{self.name}] Found {len(links)} Oil Rig links.")
                    return links
                else:
                    self.logger.warning(f"[{self.name}] No Oil Rig links found on attempt {attempt + 1}.")
                    # Save screenshot on last attempt if still failing
                    if attempt == max_attempts - 1:
                        self._save_screenshot("no_oil_rigs_found")
                        send_email_notify(
                           subject="SimCompany Oil Rig Monitoring Error - No Buildings Found",
                           body=f"No Oil Rig buildings found on the landscape page ({self.landscape_url})."
                        )

                # If no links found, refresh and retry
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
        """Checks abundance and triggers rebuild if below 95. Handles confirmation modal if abundance > 80%."""
        try:
            abundance_span = self.driver.find_element(By.XPATH, "//span[contains(text(), 'Abundance:')]")
            match = re.search(r'Abundance:\s*([\d.]+)', abundance_span.text)
            if not match:
                self.logger.error(f"  Unable to parse Abundance: {abundance_span.text}")
                return False

            abundance = float(match.group(1))
            self.logger.info(f"  Crude Oil Abundance: {abundance}")

            if abundance < 95:
                self.logger.warning(f"  Abundance ({abundance}) is below 95, automatically clicking Rebuild...")
                rebuild_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Rebuild') and contains(@class, 'btn-danger')]"))
                )
                rebuild_btn.click()
                self.logger.info("  Rebuild clicked.")
                # 只有 abundance > 80 才需要處理確認 modal
                if abundance > 80:
                    self.logger.info("  Abundance > 80, waiting for confirmation modal...")
                    try:
                        modal = WebDriverWait(self.driver, 3).until(
                            EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal-body')]"))
                        )
                        self.logger.info("  Confirmation modal appeared, waiting for Rebuild button...")
                        confirm_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-primary') and contains(., 'Rebuild')]"))
                        )
                        confirm_btn.click()
                        self.logger.info("  Confirmation modal 'Rebuild' clicked.")
                    except TimeoutException:
                        self.logger.warning("  Confirmation modal did not appear or Rebuild button not found.")
                time.sleep(2) # Wait for modal to close/transition
                return True # Rebuild initiated
            else:
                self.logger.info(f"  Abundance >= 95, no Rebuild needed.")
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
    print("Please select the function to execute:")
    print("1. Monitor Forest nursery production completion time")
    print("2. Batch start Power plant 24h production cycle")
    print("3. Monitor all Oil Rig construction status (auto-fetch landscape)")
    print("4. Send test email")
    choice = input("Enter a number (1/2/3/4):").strip()

    if choice == "1":
        logger = setup_logger("production_monitor.forest", "monitor_forest.log")
        fn_paths = ["/b/43694783/"]
        monitor = ForestNurseryMonitor(fn_paths, logger=logger)
        monitor.run()
    elif choice == "2":
        logger = setup_logger("production_monitor.powerplant", "monitor_powerplant.log")
        pp_paths = [
            "/b/40253730/", "/b/39825683/", "/b/39888395/", "/b/39915579/",
            "/b/43058380/", "/b/39825725/", "/b/39825679/", "/b/39693844/",
            "/b/39825691/", "/b/39825676/", "/b/39825686/", "/b/41178098/",
        ]
        producer = PowerPlantProducer(pp_paths, logger=logger)
        producer.run()
    elif choice == "3":
        logger = setup_logger("production_monitor.oilrig", "monitor_oilrig.log")
        monitor = OilRigMonitor(logger=logger)
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