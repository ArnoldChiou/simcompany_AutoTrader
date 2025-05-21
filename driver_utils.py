from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import os
from dotenv import load_dotenv # Import load_dotenv

load_dotenv() # Load environment variables from .env file

def initialize_driver(user_data_dir_env_var="USER_DATA_DIR", profile_dir="Default"):
    """
    Initializes and returns a Selenium WebDriver instance.

    Args:
        user_data_dir_env_var (str): The environment variable name for the user data directory.
        profile_dir (str): The profile directory to use.

    Returns:
        webdriver.Chrome: The initialized WebDriver instance.
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--remote-debugging-port=9222')
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    user_data_dir = os.getenv(user_data_dir_env_var)

    if user_data_dir and os.path.exists(user_data_dir):
        try:
            options.add_argument(f"user-data-dir={user_data_dir}")
            options.add_argument(f"--profile-directory={profile_dir}")
            print(f"[資訊] 嘗試使用 User Data Directory: {user_data_dir} 和 Profile: {profile_dir} 啟動 Chrome。")
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
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            return driver
    else:
        if not user_data_dir:
            print(f"[警告] 環境變數 {user_data_dir_env_var} 未設置。")
        elif not os.path.exists(user_data_dir):
            print(f"[警告] 指定的 USER_DATA_DIR 路徑不存在: {user_data_dir}")
        print("[資訊] 將使用預設 profile 啟動 Chrome。")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        return driver
