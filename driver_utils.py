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
    with FileLock(lock_path, timeout=600):  # 最多等10分鐘
        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--remote-debugging-port=9222')
        options.add_argument('--disable-gpu') # Added for stability
        options.add_argument('--start-maximized') # Added for stability
        options.add_argument('--disable-extensions') # Added for stability
        options.add_experimental_option("excludeSwitches", ["enable-logging"])

        # 新增: 支援直接傳 user_data_dir 參數
        if user_data_dir is None:
            user_data_dir = os.getenv(user_data_dir_env_var)

        if user_data_dir and os.path.exists(user_data_dir):
            try:
                options.add_argument(f"user-data-dir={user_data_dir}")
                options.add_argument(f"--profile-directory={profile_dir}")
                print(f"[資訊] 嘗試使用 User Data Directory: {user_data_dir} 和 Profile: {profile_dir} 啟動 Chrome。")
                chrome_version = get_installed_chrome_version()
                if chrome_version:
                    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager(driver_version=chrome_version).install()), options=options)
                else:
                    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
                print("[資訊] Chrome 使用指定的 User Data Directory 啟動成功。")
                return driver
            except Exception as e:
                print(f"[警告] 使用 user-data-dir ({user_data_dir}) 啟動 Chrome 失敗: {e}")
                print("[資訊] 將改用預設 profile 啟動 Chrome。")
                # Reset options to avoid conflicts if the user-data-dir was problematic
                options = webdriver.ChromeOptions()
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--remote-debugging-port=9222')
                options.add_argument('--disable-gpu') # Added for stability
                options.add_argument('--start-maximized') # Added for stability
                options.add_argument('--disable-extensions') # Added for stability
                options.add_experimental_option("excludeSwitches", ["enable-logging"])
                chrome_version = get_installed_chrome_version()
                if chrome_version:
                    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager(driver_version=chrome_version).install()), options=options)
                else:
                    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
                return driver
        else:
            if not user_data_dir:
                print(f"[警告] 未指定 user_data_dir 或環境變數 {user_data_dir_env_var} 未設置。")
            elif not os.path.exists(user_data_dir):
                print(f"[警告] 指定的 USER_DATA_DIR 路徑不存在: {user_data_dir}")
            print("[資訊] 將使用預設 profile 啟動 Chrome。")
            chrome_version = get_installed_chrome_version()
            if chrome_version:
                driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager(driver_version=chrome_version).install()), options=options)
            else:
                driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            return driver
