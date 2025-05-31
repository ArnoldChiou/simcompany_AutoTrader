import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

load_dotenv()

# 所有要初始化的 profile 變數名稱
PROFILE_KEYS = [
    "USER_DATA_DIR_autobuy",
    "USER_DATA_DIR_forestnursery",
    "USER_DATA_DIR_powerplant",
    "USER_DATA_DIR_oiirig",
]

LOGIN_URL = "https://www.simcompanies.com/signin/"

for key in PROFILE_KEYS:
    profile = os.getenv(key)
    if not profile:
        print(f"[SKIP] {key} is empty in .env, skip.")
        continue
    if not os.path.exists(profile):
        os.makedirs(profile)
        print(f"[INFO] Created profile directory: {profile}")
    print(f"[START] Launching Chrome for {key}: {profile}")
    options = webdriver.ChromeOptions()
    options.add_argument(f"user-data-dir={profile}")
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    driver.get(LOGIN_URL)
    print(f"請在新開的 Chrome 視窗登入遊戲 ({key})。登入完成後關閉分頁並回到這裡按 Enter 繼續...")
    input(f"[{key}] 按 Enter 繼續...")
    driver.quit()
    print(f"[DONE] {key} 已初始化完畢。\n")

print("所有 profile 已初始化並可用於自動化。")
