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

def get_forest_nursery_finish_time():
    driver = initialize_driver()  # Use the new utility function
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
    driver = initialize_driver()  # Use the new utility function
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

def monitor_all_oil_rigs_status():
    """
    進入 landscape 頁面，自動抓取所有 Oil Rig 建築，依序檢查是否在建設中。
    若有在建設中則等待最早完成時間後自動再檢查，否則寄信通知並結束。
    """
    base_url = "https://www.simcompanies.com"
    landscape_url = f"{base_url}/landscape/"
    while True:
        driver = None
        try:
            driver = initialize_driver()  # Use the new utility function
            print(f"正在進入 {landscape_url} 並搜尋所有 Oil Rig...")
            driver.get(landscape_url)
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "a"))
            )
            time.sleep(2)  # 確保所有建築都載入
            oilrig_links = []
            a_tags = driver.find_elements(By.TAG_NAME, "a")
            for a in a_tags:
                try:
                    if 'href' in a.get_attribute('outerHTML'):
                        span_texts = a.text
                        if "Oil rig" in span_texts:
                            href = a.get_attribute('href')
                            if href and "/b/" in href:
                                oilrig_links.append(href)
                except Exception:
                    continue
            if not oilrig_links:
                print("找不到任何 Oil Rig 建築。")
                send_email_notify(
                    subject="SimCompany Oil Rig 監控異常",
                    body="在 landscape 頁面找不到任何 Oil Rig 建築，請手動檢查。"
                )
                return
            print(f"共找到 {len(oilrig_links)} 個 Oil Rig：")
            for link in oilrig_links:
                print(link)
            # 依序檢查每個 Oil Rig
            min_wait_seconds = None
            min_finish_url = None
            all_not_under_construction = True
            for oilrig_url in oilrig_links:
                print(f"\n檢查 Oil Rig: {oilrig_url}")
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
                        # 施工中
                        all_not_under_construction = False
                        try:
                            finish_time_p = driver.find_element(By.XPATH, "//p[starts-with(normalize-space(text()), 'Finishes at')]")
                            finish_time_str_raw = finish_time_p.text.strip()
                            finish_time_str = finish_time_str_raw.replace('Finishes at', '').strip()
                            print(f"Oil Rig 正在施工中，預計完成時間: {finish_time_str}")
                            finish_dt = parser.parse(finish_time_str)
                            wait_seconds_construction = (finish_dt - now_for_parsing).total_seconds()
                            if wait_seconds_construction > 0:
                                print(f"將於 {wait_seconds_construction:.0f} 秒後 ({finish_dt.strftime('%Y-%m-%d %H:%M:%S')}) 重新檢查 {oilrig_url}")
                                if min_wait_seconds is None or wait_seconds_construction < min_wait_seconds:
                                    min_wait_seconds = wait_seconds_construction
                                    min_finish_url = oilrig_url
                                continue
                            else:
                                print(f"施工已於 {finish_dt.strftime('%Y-%m-%d %H:%M:%S')} 完成或已過期。")
                                send_email_notify(
                                    subject="SimCompany Oil Rig 施工完成通知",
                                    body=f"Oil Rig ({oilrig_url}) 建築施工已於 {finish_dt.strftime('%Y-%m-%d %H:%M:%S')} 完成，請前往檢查。"
                                )
                        except Exception as e_time:
                            print(f"找不到預計完成時間: {e_time}")
                            send_email_notify(
                                subject="SimCompany Oil Rig 施工狀態異常",
                                body=f"Oil Rig ({oilrig_url}) 顯示正在施工，但無法解析預計完成時間。請前往檢查。"
                            )
                    except TimeoutException:
                        print(f"Oil Rig ({oilrig_url}) 未在施工中。")
                        send_email_notify(
                            subject="SimCompany Oil Rig 狀態通知",
                            body=f"Oil Rig ({oilrig_url}) 目前未在施工中，請前往檢查。"
                        )
                except Exception as e:
                    print(f"檢查 Oil Rig ({oilrig_url}) 狀態時發生錯誤: {e}")
                    send_email_notify(
                        subject="SimCompany Oil Rig 監控錯誤",
                        body=f"檢查 Oil Rig ({oilrig_url}) 狀態時發生錯誤: {e}。請手動檢查。"
                    )
            if all_not_under_construction:
                print("所有 Oil Rig 均未在施工中，監控結束。")
                return
            if min_wait_seconds and min_wait_seconds > 0:
                print(f"\n等待 {min_wait_seconds:.0f} 秒後 (最早完成: {min_finish_url}) 重新檢查所有 Oil Rig...")
                for _ in range(3):
                    winsound.Beep(1000, 300)
                    time.sleep(0.3)
                if driver:
                    driver.quit()
                    driver = None
                try:
                    time.sleep(min_wait_seconds)
                except KeyboardInterrupt:
                    print("\n[中斷] 等待 Oil Rig 施工完成期間被手動中斷，安全結束。")
                    return
                continue  # 重新進入 while True
            else:
                print("無明確等待時間，監控結束。")
                return
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

if __name__ == "__main__":
    print("請選擇要執行的功能：")
    print("1. 監控 Forest nursery 生產結束時間")
    print("2. 批次自動啟動 Power plant 24h 生產循環")
    print("3. 監控所有 Oil Rig 施工狀態 (自動抓 landscape)")
    print("4. 發送測試郵件")
    choice = input("請輸入數字 (1/2/3/4)：").strip()
    if choice == "1":
        get_forest_nursery_finish_time()
    elif choice == "2":
        produce_power_plant()
    elif choice == "3":
        monitor_all_oil_rigs_status()
    elif choice == "4":
        test_subject = "SimCompanies 自動化工具測試郵件"
        test_body = "這是一封來自 SimCompanies 自動化工具的測試郵件。\n\n如果您收到此郵件，表示郵件功能設定正確。"
        send_email_notify(test_subject, test_body)
    else:
        print("無效選項，程式結束。")