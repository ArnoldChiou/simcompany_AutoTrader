from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import os
from dotenv import load_dotenv # Import load_dotenv
from filelock import FileLock
import re
import subprocess

load_dotenv() # Load environment variables from .env file

def get_installed_chrome_version():
    try:
        # Use reg query to get Chrome version from registry
        output = subprocess.check_output(
            r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version',
            shell=True, encoding='utf-8', stderr=subprocess.DEVNULL
        )
        match = re.search(r'version\s+REG_SZ\s+([\d.]+)', output)
        if match:
            return match.group(1)
    except Exception:
        pass
    # Fallback: try default install path
    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    try:
        output = subprocess.check_output(f'"{chrome_path}" --version', shell=True, encoding='utf-8')
        match = re.search(r'(\d+\.\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None

def initialize_driver(user_data_dir=None, user_data_dir_env_var="USER_DATA_DIR", profile_dir="Default"):
    """
    Initializes and returns a Selenium WebDriver instance.

    Args:
        user_data_dir (str): The user data directory path. If provided, takes precedence over env var.
        user_data_dir_env_var (str): The environment variable name for the user data directory.
        profile_dir (str): The profile directory to use.

    Returns:
        webdriver.Chrome: The initialized WebDriver instance.
    """
    lock_path = os.path.join(os.getcwd(), 'selenium.lock')
    # Increased timeout for file lock, adjust if necessary
    with FileLock(lock_path, timeout=900):  # 最多等15分鐘
        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        # options.add_argument('--remote-debugging-port=9222') # REMOVED: To avoid port collision
        options.add_argument('--disable-gpu') # Added for stability
        options.add_argument('--start-maximized') # Added for stability
        options.add_argument('--disable-extensions') # Added for stability
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        # Ensure headless is not accidentally enabled if not intended, or explicitly enable if needed
        # options.add_argument('--headless') # Uncomment if headless is desired

        # 新增: 支援直接傳 user_data_dir 參數
        effective_user_data_dir = user_data_dir
        if effective_user_data_dir is None:
            effective_user_data_dir = os.getenv(user_data_dir_env_var)

        if effective_user_data_dir and os.path.exists(effective_user_data_dir):
            try:
                options.add_argument(f"user-data-dir={effective_user_data_dir}")
                # It's generally better to let Chrome manage profiles within the user-data-dir
                # unless you have a very specific reason to use --profile-directory.
                # If profile_dir is "Default" and user-data-dir is set, Chrome usually handles it.
                # If you want truly separate profiles, ensure user-data-dir itself is unique per instance.
                if profile_dir != "Default": # Only add if not default, and ensure user_data_dir is distinct
                    options.add_argument(f"--profile-directory={profile_dir}")
                print(f"[資訊] 嘗試使用 User Data Directory: {effective_user_data_dir} 和 Profile: {profile_dir} 啟動 Chrome。")
                
                chrome_version = get_installed_chrome_version()
                if chrome_version:
                    print(f"[資訊] 偵測到 Chrome 版本: {chrome_version}。使用此版本對應的 ChromeDriver。")
                    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager(driver_version=chrome_version).install()), options=options)
                else:
                    print("[警告] 未偵測到已安裝的 Chrome 版本。嘗試使用最新版 ChromeDriver。")
                    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
                print("[資訊] Chrome 使用指定的 User Data Directory 啟動成功。")
                return driver
            except Exception as e:
                print(f"[警告] 使用 user-data-dir ({effective_user_data_dir}) 啟動 Chrome 失敗: {e}")
                print("[資訊] 將改用預設 (臨時) profile 啟動 Chrome。")
                # Reset options for a clean default profile attempt
                options = webdriver.ChromeOptions()
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                # options.add_argument('--remote-debugging-port=9222') # REMOVED
                options.add_argument('--disable-gpu')
                options.add_argument('--start-maximized')
                options.add_argument('--disable-extensions')
                options.add_experimental_option("excludeSwitches", ["enable-logging"])
                # options.add_argument('--headless') # Uncomment if headless is desired for fallback

                chrome_version = get_installed_chrome_version()
                if chrome_version:
                    print(f"[資訊] (Fallback) 偵測到 Chrome 版本: {chrome_version}。使用此版本對應的 ChromeDriver。")
                    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager(driver_version=chrome_version).install()), options=options)
                else:
                    print("[警告] (Fallback) 未偵測到已安裝的 Chrome 版本。嘗試使用最新版 ChromeDriver。")
                    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
                print("[資訊] Chrome 已使用預設 (臨時) profile 啟動。")
                return driver
        else:
            if not effective_user_data_dir:
                print(f"[警告] 未指定 user_data_dir 且環境變數 {user_data_dir_env_var} 未設置或為空。")
            elif not os.path.exists(effective_user_data_dir):
                print(f"[警告] 指定的 USER_DATA_DIR 路徑不存在: {effective_user_data_dir}")
            
            print("[資訊] 將使用預設 (臨時) profile 啟動 Chrome。")
            # Ensure options are for a default profile
            options = webdriver.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            # options.add_argument('--remote-debugging-port=9222') # REMOVED
            options.add_argument('--disable-gpu')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-extensions')
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            # options.add_argument('--headless') # Uncomment if headless is desired for default

            chrome_version = get_installed_chrome_version()
            if chrome_version:
                print(f"[資訊] (Default) 偵測到 Chrome 版本: {chrome_version}。使用此版本對應的 ChromeDriver。")
                driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager(driver_version=chrome_version).install()), options=options)
            else:
                print("[警告] (Default) 未偵測到已安裝的 Chrome 版本。嘗試使用最新版 ChromeDriver。")
                driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            print("[資訊] Chrome 已使用預設 (臨時) profile 啟動。")
            return driver
