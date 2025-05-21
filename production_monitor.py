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
import datetime
from dateutil import parser
import winsound
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from email.mime.text import MIMEText

load_dotenv()

def _initialize_driver():
    options = webdriver.ChromeOptions()
    user_data_dir = os.getenv("USER_DATA_DIR")
    profile_dir = "Default"
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--remote-debugging-port=9222')
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    if user_data_dir and os.path.exists(user_data_dir):
        try:
            options.add_argument(f"user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile_dir}")
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            return driver
        except Exception as e:
            print(f"[警告] 使用 user-data-dir 啟動 Chrome 失敗: {e}\n將改用預設 profile 啟動。")
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

SCOPES = ['https://www.googleapis.com/auth/gmail.send']
def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    service = build('gmail', 'v1', credentials=creds)
    return service

def send_email_notify(subject, body):
    mail_to = os.getenv('MAIL_TO')
    mail_from = os.getenv('MAIL_FROM')

    if not mail_to:
        print('[警告] .env 檔案缺少 MAIL_TO 設定，無法發送通知郵件。')
        return
    if not mail_from:
        print('[警告] .env 檔案缺少 MAIL_FROM 設定，郵件中的寄件人欄位可能不會顯示預期的寄件人。')

    try:
        service = get_gmail_service()
        message = MIMEText(body, 'plain', 'utf-8')
        message['to'] = mail_to
        if mail_from:
            message['from'] = mail_from
        message['subject'] = subject
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': raw_message}
        
        send_message = (service.users().messages().send(userId="me", body=create_message).execute())
        print(f'[通知] 郵件已發送至 {mail_to}, Message Id: {send_message["id"]}')
    except Exception as e:
        print(f'[錯誤] 郵件發送失敗 (Gmail API): {e}')
        if "invalid_grant" in str(e).lower() or "token has been expired or revoked" in str(e).lower():
            print("[提示] Gmail API 憑證可能已失效。請嘗試刪除 'token.json' 檔案後重新執行程式以重新驗證。")
        elif "file not found" in str(e).lower() and "credentials.json" in str(e).lower():
            print("[錯誤] 找不到 'credentials.json' 檔案。請確保該檔案與您的應用程式在同一個目錄下，並且已正確設定。")
            print("       您可以從 Google Cloud Console 下載您的 OAuth 2.0 用戶端憑證。")

def get_forest_nursery_finish_time():
    driver = _initialize_driver()
    base_url = "https://www.simcompanies.com"
    target_paths = [
        "/b/43694783/",
    ]
    
    production_finish_times = [] 
    construction_finish_datetimes = []
    any_nurture_started = False
    
    now_for_parsing = datetime.datetime.now()

    try:
        print("第一次使用請先使用python main.py login 登入，並在登入後關閉瀏覽器")

        for target_path in target_paths:
            building_url = base_url + target_path
            try:
                driver.get(building_url)
                time.sleep(2)

                # Check if building is under construction
                try:
                    construction_header = driver.find_element(By.XPATH, "//h3[normalize-space(text())='Construction']")
                    finish_time_p = driver.find_element(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
                    finish_time_str_raw = finish_time_p.text.strip()
                    finish_time_str = finish_time_str_raw.replace('Finishes at', '').strip()
                    
                    print(f"{target_path} 正在施工中，預計完成時間: {finish_time_str}")
                    finish_dt = parser.parse(finish_time_str)
                    construction_finish_datetimes.append(finish_dt)
                    time.sleep(1)
                    continue
                except NoSuchElementException:
                    print(f"{target_path} 未在施工中，檢查生產狀態...")
                except Exception as e_constr:
                    print(f"{target_path} 檢查施工狀態時發生錯誤: {e_constr}")

                # Try to click Max and Nurture
                try:
                    max_label = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//label[contains(., 'Max') and @type='button']"))
                    )
                    max_label.click()
                    time.sleep(0.5)
                    try:
                        nurture_btn = WebDriverWait(driver, 5).until(
                           EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Nurture') and contains(@class, 'btn-primary')]"))
                        )
                        if nurture_btn.is_enabled():
                            nurture_btn.click()
                            print(f"{target_path} 已自動點擊 Max 並啟動 Nurture！")
                            any_nurture_started = True
                            time.sleep(2)
                            continue
                    except Exception:
                        print(f"{target_path} 找不到可點擊的 Nurture 按鈕，改為查詢預計完成時間。")
                except Exception:
                    print(f"{target_path} 找不到 Max 按鈕，改為查詢預計完成時間。")

                # Find production finish time
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
                            if '/' in p_in_proj.text or ':' in p_in_proj.text:
                                finish_time_production_str = p_in_proj.text.strip()
                                break
                    
                    if not finish_time_production_str:
                        timer_spans = driver.find_elements(By.XPATH, "//span[contains(@class, 'ejaaut33') and contains(text(), ':')]")
                        if timer_spans:
                            finish_time_production_str = timer_spans[-1].text.strip()
                except Exception as e_find_time:
                    print(f"{target_path} 尋找生產完成時間時出錯: {e_find_time}")

                if finish_time_production_str:
                    print(f"{target_path} 預計生產完成時間: {finish_time_production_str}")
                    production_finish_times.append((target_path, finish_time_production_str))
                else:
                    print(f"{target_path} 未找到明確的生產倒數時間。")
                
                time.sleep(1)

            except Exception as e_building:
                print(f"[處理 {building_url} 失敗]: {e_building}")
        
        with open('finish_time.txt', 'w', encoding='utf-8') as f:
            for path, ft_str in production_finish_times:
                f.write(f"{path}: {ft_str}\n")
    finally:
        try:
            if 'driver' in locals() and driver:
                driver.quit()
        except (Exception, KeyboardInterrupt):
            pass

    if construction_finish_datetimes:
        latest_construction_finish_dt = max(construction_finish_datetimes)
        wait_seconds_construction = (latest_construction_finish_dt - now_for_parsing).total_seconds()

        if wait_seconds_construction > 0:
            print(f"檢測到建築施工中，將於 {wait_seconds_construction:.0f} 秒後 (最晚施工完成時間: {latest_construction_finish_dt.strftime('%Y-%m-%d %H:%M:%S')}) 自動重新執行監控！")
            for _ in range(3):
                winsound.Beep(1000, 500)
                time.sleep(0.5)
            try:
                time.sleep(wait_seconds_construction)
            except KeyboardInterrupt:
                print("\n[中斷] 等待施工完成期間被手動中斷，安全結束。")
                return
            print("\n=== 施工可能已完成，發送通知郵件並等待10分鐘後重新執行監控！===\n")
            send_email_notify(
                subject="SimCompany 施工完成通知",
                body=f"建築施工已於 {latest_construction_finish_dt.strftime('%Y-%m-%d %H:%M:%S')} 完成，請前往檢查。"
            )
            time.sleep(600)
            get_forest_nursery_finish_time()
            return
        else:
            print("所有偵測到的施工均已過期或完成，立即重新執行檢查...")
            get_forest_nursery_finish_time()
            return

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
        print(f"將於 {min_wait_production:.0f} 秒後 (最早生產完成: {min_path_production}) 自動重新執行批次 Nurture/監控！")
        for _ in range(3):
            winsound.Beep(1000, 500)
            time.sleep(0.5)
        try:
            time.sleep(min_wait_production)
        except KeyboardInterrupt:
            print("\n[中斷] 等待生產完成期間被手動中斷，安全結束。")
            return
        print("\n=== 生產可能已完成，重新執行批次 Nurture/監控！===\n")
        get_forest_nursery_finish_time()
        return

    if any_nurture_started or (not production_finish_times and not construction_finish_datetimes):
        print("無法取得預計完成時間，或已啟動Nurture。將於 60 秒後重試查詢...")
        time.sleep(60)
        get_forest_nursery_finish_time()
        return
    else:
        print("所有監控項目均無明確等待事件。將於 300 秒後重新檢查。")
        time.sleep(300)
        get_forest_nursery_finish_time()
        return

def produce_power_plant():
    """
    自動點擊 Power plant 並啟動 24h 生產。
    """
    driver = _initialize_driver()
    finish_times = []  # 新增：收集所有完成時間
    base_url = "https://www.simcompanies.com"
    try:
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
                time.sleep(2)
                try:
                    btn_24h = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., '24h')]") )
                    )
                    btn_24h.click()
                    time.sleep(1)
                    btn_produce = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Produce')]") )
                    )
                    btn_produce.click()
                    print(f"{target_path} 已自動啟動 24h 生產！")
                    time.sleep(2)
                except Exception:
                    print(f"{target_path} 已在生產中，略過。嘗試抓取完成時間...")
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
                time.sleep(1)
            except Exception as e:
                print(f"[Power plant {target_path} 啟動失敗]: {e}")
    finally:
        try:
            driver.quit()
        except (Exception, KeyboardInterrupt):
            pass
    max_wait = 0
    max_time_str = None
    now = datetime.datetime.now()
    for finish_time in finish_times:
        try:
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
            time.sleep(0.5)
        try:
            time.sleep(max_wait)
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
    elif choice == "3":
        send_email_notify(
                subject="SimCompany 施工完成通知",
                body=f"建築施工已於完成，請前往檢查。"
            )
    else:
        print("無效選項，程式結束。")