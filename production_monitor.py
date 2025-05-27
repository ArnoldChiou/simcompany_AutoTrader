from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import os
import time
import datetime
from dateutil import parser
import winsound
from driver_utils import initialize_driver
from email_utils import send_email_notify
import re
import traceback

def _get_forest_nursery_finish_time_worker():
    driver = None
    try:
        driver = initialize_driver()
        if driver is None:
            print("Forest Nursery Worker: WebDriver initialization failed. Will retry later.")
            time.sleep(300) # Wait before the orchestrator tries again
            return 0, "WebDriver init failed, retrying cycle"

        base_url = "https://www.simcompanies.com"
        target_paths = [
            "/b/43694783/",
        ]
        
        production_finish_times = [] 
        construction_finish_datetimes = []
        any_nurture_started = False
        
        now_for_parsing = datetime.datetime.now()

        print("First time use: please run 'python main.py login' to log in, then close the browser after login.")

        for target_path in target_paths:
            building_url = base_url + target_path
            try:
                driver.get(building_url)
                time.sleep(2) # Allow page to load

                # Check if building is under construction
                try:
                    construction_header = driver.find_element(By.XPATH, "//h3[normalize-space(text())='Construction']")
                    finish_time_p = driver.find_element(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
                    finish_time_str_raw = finish_time_p.text.strip()
                    finish_time_str = finish_time_str_raw.replace('Finishes at', '').strip()
                    
                    print(f"{target_path} is under construction, estimated finish time: {finish_time_str}")
                    finish_dt = parser.parse(finish_time_str)
                    construction_finish_datetimes.append(finish_dt)
                    time.sleep(1)
                    continue # Next target_path
                except NoSuchElementException:
                    print(f"{target_path} is not under construction, checking production status...")
                except Exception as e_constr:
                    print(f"{target_path} error occurred while checking construction status: {e_constr}")

                # Try to click Max and Nurture
                try:
                    max_label = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//label[contains(., 'Max') and @type='button']"))
                    )
                    max_label.click()
                    time.sleep(0.5) 
                    try:
                        nurture_btn = WebDriverWait(driver, 20).until(
                           EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Nurture') and contains(@class, 'btn-primary')]"))
                        )
                        if nurture_btn.is_enabled():
                            nurture_btn.click()
                            time.sleep(1)

                            try:
                                error_div_xpath = "//div[contains(text(), 'Not enough input resources of quality 5 available')]"
                                WebDriverWait(driver, 2).until(
                                    EC.visibility_of_element_located((By.XPATH, error_div_xpath))
                                )
                                print(f"{target_path} Not enough resources (quality 5), detected error message. Will click 'Cut down'.")
                                cut_down_button_xpath = "//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"
                                cut_down_button = WebDriverWait(driver, 5).until(
                                    EC.element_to_be_clickable((By.XPATH, cut_down_button_xpath))
                                )
                                cut_down_button.click()
                                print(f"{target_path} Clicked the first 'Cut down' button.")
                                time.sleep(1) 

                                try:
                                    confirm_cut_down_button_xpath = "//div[contains(@class, 'modal-content')]//button[contains(@class, 'btn-danger') and normalize-space(.)='Cut down']"
                                    confirm_cut_down_button = WebDriverWait(driver, 5).until(
                                        EC.element_to_be_clickable((By.XPATH, confirm_cut_down_button_xpath))
                                    )
                                    confirm_cut_down_button.click()
                                    print(f"{target_path} Clicked 'Cut down' button in confirmation window. Will retry.")
                                    if driver: driver.quit(); driver = None 
                                    return 0, "Cut down successful, immediate re-evaluation"
                                except Exception as e_confirm_cut_down:
                                    print(f"{target_path} Failed to click 'Cut down' in confirmation window: {e_confirm_cut_down}. Maybe window did not appear or button is different.")
                                    if driver: driver.quit(); driver = None
                                    return 0, "Cut down (confirm failed), immediate re-evaluation"
                                
                            except TimeoutException:
                                print(f"{target_path} Automatically clicked Max and started Nurture (no specific resource error detected)!")
                                any_nurture_started = True
                                print(f"After successful Nurture, re-navigating to {building_url} to read finish time.")
                                driver.get(building_url)
                                time.sleep(3)
                            except Exception as e_cut_down_logic:
                                print(f"{target_path} Unexpected error after trying Nurture with insufficient resources: {e_cut_down_logic}. Will check estimated finish time instead.")

                    except Exception: 
                        print(f"{target_path} Could not find clickable Nurture button, will check estimated finish time instead.")
                except Exception: 
                    print(f"{target_path} Could not find Max button, will check estimated finish time instead.")

                # Find production finish time (logic remains the same)
                finish_time_production_str = None
                try:
                    h3s_tags = driver.find_elements(By.TAG_NAME, 'h3')
                    proj_div = None
                    for h3_tag in h3s_tags:
                        if h3_tag.text.strip().upper() == 'PROJECTED STAGE':
                            parent = h3_tag
                            for _ in range(5): 
                                try:
                                    parent = parent.find_element(By.XPATH, './..')
                                    if parent.tag_name == 'div':
                                        proj_div = parent
                                        break
                                except Exception:
                                    break 
                            if proj_div:
                                break
                    
                    if not proj_div: 
                        for h3_tag in h3s_tags:
                            if h3_tag.text.strip().upper() == 'PROJECTED STAGE':
                                try:
                                    sibling = h3_tag.find_element(By.XPATH, 'following-sibling::*[1]')
                                    if sibling.tag_name == 'div':
                                        proj_div = sibling
                                        break
                                except Exception:
                                    pass
                    
                    if proj_div:
                        p_tags_in_proj = proj_div.find_elements(By.TAG_NAME, 'p')
                        for p_in_proj in p_tags_in_proj:
                            potential_time_str = p_in_proj.text.strip()
                            if ('/' in potential_time_str and 
                                ':' in potential_time_str and 
                                any(char.isdigit() for char in potential_time_str)):
                                try:
                                    parser.parse(potential_time_str) 
                                    finish_time_production_str = potential_time_str
                                    break 
                                except (ValueError, OverflowError, TypeError):
                                    pass 
                    
                    if not finish_time_production_str:
                        all_p_tags_on_page = driver.find_elements(By.TAG_NAME, 'p')
                        for p_tag_candidate in all_p_tags_on_page:
                            candidate_text = p_tag_candidate.text.strip()
                            if ('/' in candidate_text and 
                                ':' in candidate_text and 
                                any(char.isdigit() for char in candidate_text)):
                                try:
                                    parser.parse(candidate_text)
                                    try:
                                        parent_div_of_p = p_tag_candidate.find_element(By.XPATH, "./parent::div")
                                        if parent_div_of_p:
                                            try:
                                                parent_div_of_p.find_element(By.XPATH, ".//h3[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'projected stage')]")
                                                finish_time_production_str = candidate_text
                                                break 
                                            except NoSuchElementException:
                                                pass
                                    except NoSuchElementException:
                                        pass
                                    if finish_time_production_str: 
                                        break
                                except (ValueError, OverflowError, TypeError):
                                    pass 
                            if finish_time_production_str: 
                                break
                except Exception as e_find_time:
                    print(f"{target_path} Error occurred while searching for production finish time: {e_find_time}")

                if finish_time_production_str:
                    print(f"{target_path} Estimated production finish time: {finish_time_production_str}")
                    production_finish_times.append((target_path, finish_time_production_str))
                else:
                    print(f"{target_path} No clear production countdown time found.")
                
                time.sleep(1)

            except Exception as e_building:
                print(f"[Failed to process {building_url}]: {e_building}")
                traceback.print_exc() # Add traceback for building processing errors
        
        if not os.path.exists('record'):
            os.makedirs('record')
        with open('record/finish_time.txt', 'w', encoding='utf-8') as f:
            for path, ft_str in production_finish_times:
                f.write(f"{path}: {ft_str}\n")

    except KeyboardInterrupt:
        print("\n[Interrupted] Forest Nursery worker interrupted by user.")
        if driver: 
            try: driver.quit() 
            except: pass
        return None, "Worker interrupted by user" # Signal orchestrator to stop
    except Exception as e_main_worker:
        print(f"Error in Forest Nursery worker: {e_main_worker}")
        traceback.print_exc()
        if driver: 
            try: driver.quit()
            except: pass
        time.sleep(300) 
        return 0, f"Unhandled error in worker ({type(e_main_worker).__name__}), retrying cycle"
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e_quit:
                print(f"Error quitting driver in worker: {e_quit}")

    if construction_finish_datetimes:
        latest_construction_finish_dt = max(construction_finish_datetimes)
        wait_seconds_construction = (latest_construction_finish_dt - now_for_parsing).total_seconds()

        if wait_seconds_construction > 0:
            print(f"Detected building under construction, will re-run monitoring in {wait_seconds_construction:.0f} seconds (latest finish: {latest_construction_finish_dt.strftime('%Y-%m-%d %H:%M:%S')})!")
            for _ in range(3):
                winsound.Beep(1000, 500)
                time.sleep(0.5)
            try:
                time.sleep(wait_seconds_construction)
            except KeyboardInterrupt:
                print("\n[Interrupted] Interrupted by user during construction wait.")
                return None, "Interrupted during construction wait"
            
            print("\n=== Construction may be finished, sending notification email and waiting 10 minutes before re-monitoring! ===\n")
            send_email_notify(
                subject="SimCompany Construction Finished Notification",
                body=f"Building construction finished at {latest_construction_finish_dt.strftime('%Y-%m-%d %H:%M:%S')}, please check."
            )
            try:
                time.sleep(600)
            except KeyboardInterrupt:
                print("\n[Interrupted] Interrupted by user during post-construction observation.")
                return None, "Interrupted during post-construction observation"
            return 0, "Construction cycle complete, immediate re-evaluation"
        else:
            print("All detected constructions are expired or finished, re-checking immediately...")
            return 0, "Previously detected construction already finished, immediate re-evaluation"

    min_wait_production = None
    min_path_production = None
    for path, finish_time_str_prod in production_finish_times:
        try:
            finish_dt_prod = parser.parse(finish_time_str_prod)
            wait_seconds_prod = (finish_dt_prod - now_for_parsing).total_seconds()
            if wait_seconds_prod > 0 and (min_wait_production is None or wait_seconds_prod < min_wait_production):
                min_wait_production = wait_seconds_prod
                min_path_production = path
        except Exception:
            continue
    
    if min_wait_production and min_wait_production > 0:
        print(f"Will re-run batch Nurture/monitoring in {min_wait_production:.0f} +60 seconds (earliest production finish: {min_path_production})!")
        try:
            time.sleep(min_wait_production + 60)
        except KeyboardInterrupt:
            print("\n[Interrupted] Interrupted by user during production wait.")
            return None, "Interrupted during production wait"
        print("\n=== Production may be finished, re-running batch Nurture/monitoring! ===\n")
        return 0, "Production cycle complete, immediate re-evaluation"

    if any_nurture_started or (not production_finish_times and not construction_finish_datetimes):
        print("Could not get estimated finish time, or Nurture started. Will retry in 60 seconds...")
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            print("\n[Interrupted] Interrupted by user during short retry wait.")
            return None, "Interrupted during short retry wait"
        return 0, "Short retry cycle complete, immediate re-evaluation"
    else:
        print("No clear waiting events for all monitored items. Will re-check in 300 seconds.")
        try:
            time.sleep(300)
        except KeyboardInterrupt:
            print("\n[Interrupted] Interrupted by user during long re-check wait.")
            return None, "Interrupted during long re-check wait"
        return 0, "Long re-check cycle complete, immediate re-evaluation"

def get_forest_nursery_finish_time():
    while True:
        status_code, reason = _get_forest_nursery_finish_time_worker() 
        
        if status_code is None: 
            print(f"Forest Nursery monitoring stopped: {reason}")
            break 
        
        print(f"\n=== Forest Nursery: Cycle ended ({reason}). Starting new cycle. ===\n")
        time.sleep(1)

def produce_power_plant():
    while True:
        driver = None
        max_wait = 0.0 
        max_time_str = None
        
        try:
            now = datetime.datetime.now()
            print("Power Plant: Initializing WebDriver for new cycle...")
            driver = initialize_driver()
            if driver is None:
                print("Power Plant: WebDriver initialization failed. Retrying in 5 minutes.")
                try:
                    time.sleep(300)
                except KeyboardInterrupt:
                    print("\n[Interrupted] Power Plant monitoring interrupted by user during WebDriver retry wait.")
                    break 
                continue 

            finish_times = []
            base_url = "https://www.simcompanies.com"
            target_paths = [
                "/b/40253730/", "/b/39825683/", "/b/39888395/", "/b/39915579/",
                "/b/43058380/", "/b/39825725/", "/b/39825679/", "/b/39693844/",
                "/b/39825691/", "/b/39825676/", "/b/39825686/", "/b/41178098/",
            ]
            
            print(f"Power Plant: Processing {len(target_paths)} plants.")
            if target_paths:
                print(f"Power Plant: Opening first plant: {target_paths[0]}")
                driver.get(base_url + target_paths[0])
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'btn-secondary') and normalize-space(.)='Reposition']"))
                )
            
            for idx, target_path in enumerate(target_paths):
                if idx == 0:
                    continue 
                print(f"Power Plant: Opening new tab for: {target_path}")
                driver.execute_script(f"window.open('{base_url + target_path}', '_blank');")
                time.sleep(0.2) 

            handles = driver.window_handles
            print(f"Power Plant: Found {len(handles)} tabs. Expected {len(target_paths)}.")

            if len(handles) != len(target_paths) and target_paths: 
                 print(f"Power Plant: Warning - Mismatch in expected tabs ({len(target_paths)}) and actual tabs ({len(handles)}). Proceeding with available tabs.")
            
            for i in range(len(handles)):
                current_path_for_logging = target_paths[i] if i < len(target_paths) else f"unknown_target_path_for_handle_{i}"
                try:
                    driver.switch_to.window(handles[i])
                    print(f"Power Plant: Switched to tab for {current_path_for_logging}. Waiting for page elements...")
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'btn-secondary') and normalize-space(.)='Reposition']"))
                    )
                    time.sleep(0.5) 

                    is_producing = False
                    finish_time_text = None 
                    try:
                        p_tags = driver.find_elements(By.TAG_NAME, 'p')
                        for p in p_tags:
                            if p.text.strip().startswith('Finishes at'):
                                finish_time_text = p.text.strip()
                                is_producing = True
                                break
                    except StaleElementReferenceException:
                        print(f"Power Plant ({current_path_for_logging}): Stale element while checking production status. Re-fetching.")
                        driver.refresh() 
                        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'btn-secondary') and normalize-space(.)='Reposition']")))
                        p_tags = driver.find_elements(By.TAG_NAME, 'p')
                        for p in p_tags:
                            if p.text.strip().startswith('Finishes at'):
                                finish_time_text = p.text.strip()
                                is_producing = True
                                break
                    except Exception as e_check_prod:
                        print(f"Power Plant ({current_path_for_logging}): Error checking production: {e_check_prod}")


                    if is_producing and finish_time_text:
                        print(f"Power Plant ({current_path_for_logging}): Already producing. Finishes at: {finish_time_text}")
                        finish_times.append(finish_time_text)
                        continue 

                    print(f"Power Plant ({current_path_for_logging}): Not producing or finish time not found. Attempting to start 24h production.")
                    try:
                        btn_24h = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(., '24h')]"))
                        )
                        btn_24h.click()
                        time.sleep(0.5) 
                        btn_produce = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Produce')]"))
                        )
                        btn_produce.click()
                        print(f"Power Plant ({current_path_for_logging}): Successfully started 24h production.")
                        time.sleep(1) 
                        p_tags_after_produce = driver.find_elements(By.TAG_NAME, 'p')
                        for p_after in p_tags_after_produce:
                            if p_after.text.strip().startswith('Finishes at'):
                                new_finish_time = p_after.text.strip()
                                print(f"Power Plant ({current_path_for_logging}): New finish time: {new_finish_time}")
                                finish_times.append(new_finish_time)
                                break
                    except Exception as e_start_prod:
                        print(f"Power Plant ({current_path_for_logging}): Failed to start 24h production: {e_start_prod}. Attempting to find existing finish time again.")
                        try:
                            p_tags_fallback = driver.find_elements(By.TAG_NAME, 'p')
                            found_fallback_time = False
                            for p_fb in p_tags_fallback:
                                if p_fb.text.strip().startswith('Finishes at'):
                                    fallback_finish_time = p_fb.text.strip()
                                    print(f"Power Plant ({current_path_for_logging}): Found fallback finish time: {fallback_finish_time}")
                                    finish_times.append(fallback_finish_time)
                                    found_fallback_time = True
                                    break
                            if not found_fallback_time:
                                print(f"Power Plant ({current_path_for_logging}): No finish time found even after attempting to start production.")
                        except Exception as e2:
                            print(f"Power Plant ({current_path_for_logging}): Error re-checking finish time: {e2}")
                except TimeoutException:
                    print(f"Power Plant ({current_path_for_logging}): Timeout waiting for page elements. Skipping this plant for this cycle.")
                except Exception as e_handle:
                    print(f"Power Plant ({current_path_for_logging}): General error processing plant: {e_handle}")
                    traceback.print_exc()

            print("Power Plant: Finished processing all plants for this cycle.")
            for ft_str_from_list in finish_times:
                try:
                    time_str = ft_str_from_list.replace('Finishes at', '').strip()
                    finish_dt = parser.parse(time_str)
                    wait_seconds = (finish_dt - now).total_seconds()
                    if wait_seconds > max_wait:
                        max_wait = wait_seconds
                        max_time_str = ft_str_from_list
                except Exception as e_parse:
                    print(f"Power Plant: Error parsing finish time '{ft_str_from_list}': {e_parse}")
                    continue
        
        except KeyboardInterrupt:
            print("\n[Interrupted] Power Plant monitoring interrupted by user during main operation.")
            if driver:
                try: driver.quit()
                except: pass
            break 
        except Exception as e:
            print(f"Power Plant: Critical error in cycle: {e}")
            traceback.print_exc()
            max_wait = 300 
            print(f"Power Plant: Unexpected error, will retry cycle in {max_wait:.0f} seconds.")
        finally:
            if driver:
                print("Power Plant: Quitting WebDriver for this cycle.")
                try:
                    driver.quit()
                except Exception as e_quit:
                    print(f"Power Plant: Error quitting driver: {e_quit}")

        if max_wait > 0:
            print(f"Power Plant: Next check in {max_wait:.0f} seconds (latest finish: {max_time_str or 'N/A'}).")
        else:
            print("Power Plant: No specific wait tasks, or all tasks completed/failed to parse. Re-checking in 60 seconds.")
            max_wait = 60 

        print(f"Power Plant: Sleeping for {max_wait:.0f} +60 seconds...")
        try:
            time.sleep(max_wait + 60)
        except KeyboardInterrupt:
            print("\n[Interrupted] Power Plant monitoring interrupted by user during wait.")
            break 
        
        print("\n=== Power Plant: Cycle complete. Starting next cycle. ===\n")

def monitor_all_oil_rigs_status():
    base_url = "https://www.simcompanies.com"
    landscape_url = f"{base_url}/landscape/"
    
    while True:
        driver = None
        action_taken_requires_restart_after_rebuild = False
        try:
            print("Initializing WebDriver for oil rig monitoring...")
            driver = initialize_driver()
            if driver is None:
                print("CRITICAL: Failed to initialize WebDriver after all attempts. Exiting oil rig monitoring.")
                send_email_notify(
                    subject="SimCompany Oil Rig Monitoring CRITICAL FAILURE",
                    body="Could not initialize the WebDriver for oil rig monitoring. Manual intervention required."
                )
                return

            print(f"Navigating to {landscape_url} and searching for all Oil Rigs...")
            driver.get(landscape_url)
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "a"))
            )
            time.sleep(5)
            
            try:
                login_indicator_xpath = (
                    "//form[@action='/login'] | " 
                    "//a[contains(@href,'/login') and (contains(normalize-space(.), 'Login') or contains(normalize-space(.), 'Sign In'))] | " 
                    "//button[contains(translate(normalize-space(.), 'LOGIN', 'login'), 'login') and @type='submit']" 
                )
                WebDriverWait(driver, 7).until( 
                    EC.visibility_of_element_located((By.XPATH, login_indicator_xpath))
                )
                current_url_for_login_check = driver.current_url
                print(f"Detected login page or login prompt (URL: {current_url_for_login_check}). This may be due to Chrome profile switch or session expiration.")
                send_email_notify(
                    subject="SimCompany Oil Rig Monitoring Requires Login",
                    body=f"The script detected a login requirement after navigating to {landscape_url} (URL: {current_url_for_login_check}).\n"
                         f"This may be due to Chrome profile corruption/switch to default profile, or session expiration.\n"
                         f"Please manually log in to SimCompanies. The script will retry in 1 hour."
                )
                print("The script will pause for 1 hour. Please log in during this time. If you want to stop immediately, manually interrupt the script.")
                if driver: driver.quit() 
                time.sleep(3600) 
                continue 
            except TimeoutException:
                print("No direct login page detected, continuing to fetch Oil Rig information.")
            except Exception as e_login_check:
                print(f"Unexpected error occurred while checking login status: {e_login_check}")

            oilrig_links = []
            MAX_LINK_COLLECTION_ATTEMPTS = 3
            successful_link_collection = False
            for attempt in range(MAX_LINK_COLLECTION_ATTEMPTS):
                print(f"Attempting to collect Oil Rig links (Attempt {attempt + 1}/{MAX_LINK_COLLECTION_ATTEMPTS})...")
                try:
                    oilrig_links = [] 
                    if landscape_url not in driver.current_url:
                        print(f"Warning: Current URL ({driver.current_url}) is not the expected landscape URL ({landscape_url}). Re-navigating...")
                        driver.get(landscape_url)
                        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
                        time.sleep(5)

                    a_tags = driver.find_elements(By.TAG_NAME, "a")
                    print(f"Found {len(a_tags)} <a> tags.")
                    
                    current_rig_links_this_attempt = []
                    for a in a_tags:
                        try:
                            _ = a.tag_name 
                        except StaleElementReferenceException:
                            print("Detected stale <a> tag, will re-fetch all tags in the next attempt.")
                            raise 

                        href_val = a.get_attribute('href')
                        if not href_val or "/b/" not in href_val:
                            continue

                        found_oilrig = False
                        try:
                            imgs = a.find_elements(By.TAG_NAME, "img")
                            for img in imgs:
                                alt = img.get_attribute('alt')
                                if alt and 'Oil rig' in alt:
                                    found_oilrig = True
                                    break
                        except StaleElementReferenceException: 
                            print("Encountered StaleElementReferenceException while searching for img, marking for retry.")
                            raise 

                        if not found_oilrig:
                            try:
                                spans = a.find_elements(By.TAG_NAME, "span")
                                for span in spans:
                                    if 'Oil rig' in span.text:
                                        found_oilrig = True
                                        break
                            except StaleElementReferenceException: 
                                print("Encountered StaleElementReferenceException while searching for span, marking for retry.")
                                raise
                        
                        if found_oilrig:
                            if href_val not in current_rig_links_this_attempt:
                                current_rig_links_this_attempt.append(href_val)
                    
                    oilrig_links = current_rig_links_this_attempt
                    if not oilrig_links and len(a_tags) > 0 : 
                        print(f"Processed {len(a_tags)} <a> tags but did not identify any Oil Rig links. Check if the page content matches expectations.")
                    elif not oilrig_links and len(a_tags) == 0:
                        print("No <a> tags found on the page for analysis.")

                    print(f"Successfully collected {len(oilrig_links)} Oil Rig links.")
                    successful_link_collection = True
                    break  

                except StaleElementReferenceException:
                    print(f"Encountered StaleElementReferenceException while collecting Oil Rig links.")
                    if attempt < MAX_LINK_COLLECTION_ATTEMPTS - 1:
                        print("Refreshing page and retrying...")
                        time.sleep(3) 
                        driver.refresh() 
                        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
                        time.sleep(5) 
                    else:
                        print("Reached maximum retry attempts, unable to recover from StaleElementReferenceException.")
                except Exception as e_find_link_general: 
                    print(f"Unexpected error occurred while processing link elements (Attempt {attempt + 1}): {e_find_link_general}")
                    traceback.print_exc()
                    if attempt < MAX_LINK_COLLECTION_ATTEMPTS - 1:
                        print("Retrying after a short delay...")
                        time.sleep(5)
                    else:
                        print("Reached maximum retry attempts, unable to collect links due to other errors.")
            
            if not successful_link_collection or not oilrig_links:
                current_url_for_debug = driver.current_url
                page_title_for_debug = driver.title
                print(f"Could not find any Oil Rig buildings on {landscape_url} (Current actual URL: {current_url_for_debug}, Title: {page_title_for_debug}).")
                
                screenshot_dir = 'record'
                if not os.path.exists(screenshot_dir):
                    os.makedirs(screenshot_dir)
                screenshot_filename = f'no_oil_rigs_found_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
                screenshot_path = os.path.join(screenshot_dir, screenshot_filename)
                try:
                    driver.save_screenshot(screenshot_path)
                    print(f"Saved screenshot to: {screenshot_path}")
                except Exception as e_ss:
                    print(f"Failed to save screenshot: {e_ss}")

                send_email_notify(
                    subject="SimCompany Oil Rig Monitoring Abnormal - No Buildings Found",
                    body=f"Could not find any Oil Rig buildings on the landscape page ({landscape_url}).\n"
                         f"Current page URL: {current_url_for_debug}\n"
                         f"Current page title: {page_title_for_debug}\n"
                         f"Tried {MAX_LINK_COLLECTION_ATTEMPTS} times to collect links.\n"
                         f"Screenshot attempted to save to server at {screenshot_path} (if successful).\n"
                         f"Please manually check if logged in and if the landscape page is displaying buildings correctly."
                )
                print("Retrying in 1 hour.") 
                if driver: driver.quit()
                time.sleep(3600)
                continue 

            print(f"Found {len(oilrig_links)} Oil Rigs:")
            for link in oilrig_links:
                print(link)

            min_wait_seconds_construction = None
            min_finish_url_construction = None

            for oilrig_url in oilrig_links:
                if action_taken_requires_restart_after_rebuild:
                    break 

                print(f"\nChecking Oil Rig: {oilrig_url}")
                driver.get(oilrig_url)
                now_for_parsing = datetime.datetime.now()
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, "//h3[normalize-space(text())='Construction']"))
                        )
                        finish_time_p = driver.find_element(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
                        finish_time_str_raw = finish_time_p.text.strip()
                        finish_time_str = finish_time_str_raw.replace('Finishes at', '').strip()
                        
                        finish_dt = parser.parse(finish_time_str)
                        current_wait_seconds = (finish_dt - now_for_parsing).total_seconds()

                        if current_wait_seconds > 0:
                            print(f"Oil Rig is under construction, estimated finish time: {finish_time_str}")
                            if min_wait_seconds_construction is None or current_wait_seconds < min_wait_seconds_construction:
                                min_wait_seconds_construction = current_wait_seconds
                                min_finish_url_construction = oilrig_url
                            continue
                        else:
                            print(f"Construction finished or expired at {finish_dt.strftime('%Y-%m-%d %H:%M:%S')}.")
                            send_email_notify(
                                subject="SimCompany Oil Rig Construction Finished Notification",
                                body=f"Oil Rig ({oilrig_url}) construction finished at {finish_dt.strftime('%Y-%m-%d %H:%M:%S')}, please check."
                            )
                    except TimeoutException:
                        print(f"Oil Rig ({oilrig_url}) is not under construction, checking abundance...")
                        try:
                            abundance_span = driver.find_element(By.XPATH, "//span[contains(text(), 'Abundance:')]")
                            abundance_text = abundance_span.text
                            print(f"Abundance info: {abundance_text}")
                            match = re.search(r'Abundance:\s*([\d.]+)', abundance_text)
                            abundance_value = float(match.group(1)) if match else None
                            if abundance_value is not None:
                                print(f"Crude Oil Abundance: {abundance_value}")
                                if abundance_value < 95:
                                    print(f"Abundance below 95, automatically clicking Rebuild...")
                                    rebuild_btn = WebDriverWait(driver, 10).until(
                                        EC.visibility_of_element_located((By.XPATH, "//button[contains(., 'Rebuild') and contains(@class, 'btn-danger')]"))
                                    )
                                    WebDriverWait(driver, 10).until(
                                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Rebuild') and contains(@class, 'btn-danger')]"))
                                    )
                                    rebuild_btn.click()
                                    print("Clicked Rebuild, waiting for construction to start...")
                                    time.sleep(5)
                                    action_taken_requires_restart_after_rebuild = True
                                    break
                                else:
                                    print(f"Abundance >= 95, no need to Rebuild.")
                                    send_email_notify(
                                        subject="SimCompany Oil Rig Status Notification",
                                        body=f"Oil Rig ({oilrig_url}) is not under construction, Abundance={abundance_value}, no need to Rebuild."
                                    )
                            else:
                                print("Could not parse Abundance value.")
                                send_email_notify(
                                    subject="SimCompany Oil Rig Status Abnormal",
                                    body=f"Oil Rig ({oilrig_url}) is not under construction but could not parse Abundance value, please check."
                                )
                        except Exception as e_abun:
                            print(f"Failed to fetch Abundance: {e_abun}")
                            send_email_notify(
                                subject="SimCompany Oil Rig Status Abnormal",
                                body=f"Oil Rig ({oilrig_url}) is not under construction and failed to fetch Abundance: {e_abun}, please check."
                            )
                    except Exception as e_time_or_constr:
                        print(f"Error occurred while checking Oil Rig ({oilrig_url}) construction status: {e_time_or_constr}")
                        send_email_notify(
                            subject="SimCompany Oil Rig Construction Status Abnormal",
                            body=f"Oil Rig ({oilrig_url}) error occurred while checking construction status: {e_time_or_constr}. Please check."
                        )
                except Exception as e_rig_processing:
                    print(f"Error occurred while processing Oil Rig ({oilrig_url}): {e_rig_processing}")
                    send_email_notify(
                        subject="SimCompany Oil Rig Monitoring Error",
                        body=f"Error occurred while processing Oil Rig ({oilrig_url}): {e_rig_processing}. Please manually check."
                    )

            if action_taken_requires_restart_after_rebuild:
                print("\nRebuild action initiated for an oil rig. Restarting monitoring process after a 60s delay.")
                time.sleep(60) 
                continue

            if min_wait_seconds_construction and min_wait_seconds_construction > 0:
                wait_duration = min_wait_seconds_construction + 60
                print(f"\nAt least one Oil Rig is under construction. Waiting {wait_duration:.0f} seconds (based on earliest finish: {min_finish_url_construction}, plus 60 seconds buffer) before re-checking all Oil Rigs...")
                try:
                    if driver:  
                        driver.quit()
                        driver = None  
                    time.sleep(wait_duration)
                except KeyboardInterrupt:
                    print("\n[Interrupted] Interrupted by user during Oil Rig construction wait, safely exiting.")
                    return  
                continue  
            else:
                print("All detected constructions are finished/expired, or no clear future wait time. Monitoring ends this round.")
                return

        except KeyboardInterrupt:
            print("\n[Interrupted] Oil Rig monitoring interrupted by user, safely exiting.")
            return
        except Exception as e_main_loop:
            print(f"monitor_all_oil_rigs_status main loop encountered a critical error: {e_main_loop}")
            send_email_notify(
                subject="SimCompany Oil Rig Monitoring Critical Error",
                body=f"monitor_all_oil_rigs_status encountered a critical error: {e_main_loop}. Monitoring will retry in 60 seconds."
            )
            time.sleep(60)
            continue
        finally:
            if driver:
                print("Quitting WebDriver for oil rig monitoring.")
                try:
                    driver.quit()
                except Exception as e_quit:
                    print(f"Error quitting WebDriver: {e_quit}")

if __name__ == "__main__":
    print("Please select the function to execute:")
    print("1. Monitor Forest nursery production finish time")
    print("2. Batch auto-start Power plant 24h production cycle")
    print("3. Monitor all Oil Rig construction status (auto-fetch landscape)")
    print("4. Send test email")
    choice = input("Enter a number (1/2/3/4):").strip()
    if choice == "1":
        get_forest_nursery_finish_time()
    elif choice == "2":
        produce_power_plant()
    elif choice == "3":
        monitor_all_oil_rigs_status()
    elif choice == "4":
        test_subject = "SimCompanies Automation Tool Test Email"
        test_body = "This is a test email from the SimCompanies Automation Tool.\n\nIf you received this email, the email functionality is correctly configured."
        send_email_notify(test_subject, test_body)
    else:
        print("Invalid option, program exiting.")