from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import os
from dotenv import load_dotenv
import time

load_dotenv()

def _initialize_driver():
    options = webdriver.ChromeOptions()
    user_data_dir = os.getenv("USER_DATA_DIR")
    profile_dir = "Default"
    # 新增常見修復參數
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--remote-debugging-port=9222')
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    # 嘗試使用 user-data-dir，若失敗則 fallback
    if user_data_dir and os.path.exists(user_data_dir):
        try:
            options.add_argument(f"user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile_dir}")
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            return driver
        except Exception as e:
            print(f"[警告] 使用 user-data-dir 啟動 Chrome 失敗: {e}\n將改用預設 profile 啟動。")
            # 移除 user-data-dir 參數再試一次
            options = webdriver.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--remote-debugging-port=9222')
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            return driver
    else:
        print("[警告] USER_DATA_DIR 未設置或不存在，將用預設 profile 啟動 Chrome。")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        return driver

def get_forest_nursery_finish_time():
    driver = _initialize_driver()
    try:
        driver.get("https://www.simcompanies.com/landscape/")
        print("第一次使用請先使用python main.py login 登入，並在登入後關閉瀏覽器")
        target_selectors = [
            'a[href="/b/43694783/"]',
        ]
        finish_times = []
        for target_selector in target_selectors:
            try:
                WebDriverWait(driver, 30).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, target_selector))
                )
                driver.find_element(By.CSS_SELECTOR, target_selector).click()
                time.sleep(2)
                # 先嘗試點擊 Max 按鈕
                try:
                    max_label = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//label[contains(., 'Max') and @type='button']"))
                    )
                    max_label.click()
                    time.sleep(0.5)
                    # 再嘗試點擊 Nurture 按鈕
                    try:
                        nurture_btn = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Nurture') and contains(@class, 'btn-primary')]"))
                        )
                        if nurture_btn.is_enabled():
                            nurture_btn.click()
                            print(f"{target_selector} 已自動點擊 Max 並啟動 Nurture！")
                            time.sleep(2)
                            driver.get("https://www.simcompanies.com/landscape/")
                            time.sleep(1)
                            continue
                    except Exception:
                        print(f"{target_selector} 找不到可點擊的 Nurture 按鈕，改為查詢預計完成時間。")
                except Exception:
                    print(f"{target_selector} 找不到 Max 按鈕，改為查詢預計完成時間。")
                # 若無法點擊 Nurture，則按照原本方式查詢預計完成日期
                h3s = driver.find_elements(By.TAG_NAME, 'h3')
                proj_div = None
                for h3 in h3s:
                    if h3.text.strip().upper() == 'PROJECTED STAGE':
                        parent = h3
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
                    for h3 in h3s:
                        if h3.text.strip().upper() == 'PROJECTED STAGE':
                            try:
                                sibling = h3.find_element(By.XPATH, 'following-sibling::*[1]')
                                if sibling.tag_name == 'div':
                                    proj_div = sibling
                            except Exception:
                                pass
                finish_time = None
                if proj_div:
                    p_tags = proj_div.find_elements(By.TAG_NAME, 'p')
                    for p in p_tags:
                        if '/' in p.text or ':' in p.text:
                            finish_time = p.text
                if not finish_time:
                    try:
                        timer_spans = driver.find_elements(By.XPATH, "//span[contains(@class, 'ejaaut33') and contains(text(), ':')]")
                        if timer_spans:
                            finish_time = timer_spans[-1].text
                    except Exception:
                        pass
                if finish_time:
                    print(f"{target_selector} 預計完成時間: {finish_time}")
                    finish_times.append((target_selector, finish_time))
                else:
                    print(f"{target_selector} 未找到生產倒數時間")
                driver.get("https://www.simcompanies.com/landscape/")
                time.sleep(1)
            except Exception as e:
                print(f"[Power plant 啟動失敗] {target_selector}: {e}")
        # 寫入所有 finish_times
        with open('finish_time.txt', 'w', encoding='utf-8') as f:
            for selector, finish_time in finish_times:
                f.write(f"{selector}: {finish_time}\n")
    finally:
        try:
            driver.quit()
        except (Exception, KeyboardInterrupt):
            pass
    # 計算最早的 finish_time 並等待
    import datetime
    import winsound
    from dateutil import parser
    min_wait = None
    min_selector = None
    for selector, finish_time in finish_times:
        try:
            finish_dt = parser.parse(finish_time)
            now = datetime.datetime.now()
            wait_seconds = (finish_dt - now).total_seconds()
            if wait_seconds > 0 and (min_wait is None or wait_seconds < min_wait):
                min_wait = wait_seconds
                min_selector = selector
        except Exception:
            continue
    import time as _time
    if min_wait and min_wait > 0:
        print(f"將於 {min_wait:.0f} 秒後自動重新執行批次 Nurture/監控！")
        for _ in range(3):
            winsound.Beep(1000, 500)
            _time.sleep(0.5)
        try:
            _time.sleep(min_wait)
        except KeyboardInterrupt:
            print("\n[中斷] 等待期間被手動中斷，安全結束。")
            return
        print("\n=== 生產已完成，重新執行批次 Nurture/監控！===\n")
        # 重新查詢預計完成時間並等待
        get_forest_nursery_finish_time()
    else:
        # 若剛剛有成功啟動 Nurture，則強制重新查詢直到有 finish_time
        if any('已自動點擊 Max 並啟動 Nurture' in str(x) for x in finish_times) or len(finish_times) == 0:
            print("無法取得預計完成時間，將於 60 秒後重試查詢...")
            _time.sleep(60)
            get_forest_nursery_finish_time()
        else:
            print("所有建築皆無需等待或時間解析失敗。")

def produce_power_plant():
    """
    自動點擊 Power plant 並啟動 24h 生產。
    """
    driver = _initialize_driver()
    finish_times = []  # 新增：收集所有完成時間
    base_url = "https://www.simcompanies.com"
    try:
        # target_selectors now store only the path part of the URL
        target_paths = [
            "/b/40253730/",
            "/b/39825683/",
            "/b/39888395/",
            "/b/39915579/",
            "/b/43058380/",
            "/b/39825725/",
            "/b/39825679/",
            "/b/39693844/",
            "/b/39825691/",
            "/b/39825676/",
            "/b/39825686/",
            "/b/41178098/",
        ]
        for target_path in target_paths:
            building_url = base_url + target_path
            try:
                driver.get(building_url)
                time.sleep(2) # Wait for page to load
                # 嘗試點擊 24h 按鈕，若無則略過並抓取完成時間
                try:
                    btn_24h = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., '24h')]") )
                    )
                    btn_24h.click()
                    time.sleep(1)
                    # 點擊 Produce 按鈕
                    btn_produce = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Produce')]") )
                    )
                    btn_produce.click()
                    print(f"{target_path} 已自動啟動 24h 生產！")
                    time.sleep(2)
                except Exception:
                    print(f"{target_path} 已在生產中，略過。嘗試抓取完成時間...")
                    # 抓取 Finishes at ...
                    # No need to re-navigate, already on the building page
                    try:
                        finish_time = None
                        p_tags = driver.find_elements(By.TAG_NAME, 'p')
                        for p in p_tags:
                            if p.text.strip().startswith('Finishes at'):
                                finish_time = p.text.strip()
                                break
                        if finish_time:
                            print(f"{target_path} {finish_time}")
                            finish_times.append(finish_time)
                        else:
                            print(f"{target_path} 未找到完成時間。")
                    except Exception as e2:
                        print(f"{target_path} 抓取完成時間失敗: {e2}")
                # No need to go back to landscape page explicitly in the loop for each building
                time.sleep(1) # Small delay before processing next building
            except Exception as e:
                print(f"[Power plant {target_path} 啟動失敗]: {e}")
    finally:
        try:
            driver.quit()
        except (Exception, KeyboardInterrupt):
            pass
    # 點擊完成後，等待所有建築的最晚完成時間再次執行
    import time as _time
    import winsound
    import datetime
    from dateutil import parser
    max_wait = 0
    max_time_str = None
    now = datetime.datetime.now()
    for finish_time in finish_times:
        try:
            # 例: 'Finishes at 5/20/2025 3:59 PM'
            time_str = finish_time.replace('Finishes at', '').strip()
            finish_dt = parser.parse(time_str)
            wait_seconds = (finish_dt - now).total_seconds()
            if wait_seconds > max_wait:
                max_wait = wait_seconds
                max_time_str = finish_time
        except Exception:
            continue
    if max_wait > 0:
        print(f"將於 {max_wait:.0f} 秒後(最晚: {max_time_str})自動重新執行批次生產！")
        for _ in range(3):
            winsound.Beep(1000, 500)
            _time.sleep(0.5)
        try:
            _time.sleep(max_wait)
        except KeyboardInterrupt:
            print("\n[中斷] 等待期間被手動中斷，安全結束。")
            return
        print("\n=== 生產已完成，重新執行批次生產！===\n")
        produce_power_plant()
    else:
        print("所有建築皆無需等待或時間解析失敗。")
        produce_power_plant()

if __name__ == "__main__":
    print("請選擇要執行的功能：")
    print("1. 監控 Forest nursery 生產結束時間")
    print("2. 批次自動啟動 Power plant 24h 生產循環")
    choice = input("請輸入數字 (1/2)：").strip()
    if choice == "1":
        get_forest_nursery_finish_time()
    elif choice == "2":
        produce_power_plant()
    else:
        print("無效選項，程式結束。")