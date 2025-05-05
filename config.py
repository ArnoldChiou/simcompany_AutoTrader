# Shared configuration for AutoBuyer and TradeMonitor

import os
from dotenv import load_dotenv

# 載入 .env 檔案
load_dotenv()

# --- API URLs ---
PRODUCT_API_URL_POWER = "https://www.simcompanies.com/api/v3/market/0/1/" # Example: Power
BUY_API_URL = "https://www.simcompanies.com/api/v2/market-order/take/"
CASH_API_URL = "https://www.simcompanies.com/api/v2/companies/me/cashflow/recent/"

# --- Target Product ---
PRODUCT_API_URL = PRODUCT_API_URL_POWER # Default to Power
TARGET_QUALITY = 0

# --- Buying Parameters ---
MAX_BUY_QUANTITY = 1000 # Set to None for no limit

# --- Request Parameters ---
MARKET_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/json'
}

# Cookies (IMPORTANT: Update sessionid and csrftoken)
COOKIES = {
    'sessionid': os.getenv('SESSIONID', ''),
    'csrftoken': os.getenv('CSRFTOKEN', ''),
}

# --- Logic Parameters ---
if not COOKIES.get('sessionid') or not COOKIES.get('csrftoken'):
    print("錯誤：請在 config.py 中填入有效的 COOKIES (sessionid, csrftoken)。")

BUY_THRESHOLD_PERCENTAGE = 0.96
DEFAULT_CHECK_INTERVAL_SECONDS = 300
PURCHASE_WAIT_MULTIPLIER = 1.5

# --- Request Timeouts (seconds) ---
MARKET_REQUEST_TIMEOUT = 20
BUY_REQUEST_TIMEOUT = 30
MONEY_REQUEST_TIMEOUT = 15

# --- Validation ---
if not COOKIES.get('sessionid') or not COOKIES.get('csrftoken'):
    print("錯誤：請在 config.py 中填入有效的 COOKIES (sessionid, csrftoken)。")

