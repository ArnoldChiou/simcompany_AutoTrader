# Shared configuration for AutoBuyer and TradeMonitor

import os
from dotenv import load_dotenv

# 載入 .env 檔案
load_dotenv()

# --- API URLs ---
PRODUCT_API_URL_POWER = "https://www.simcompanies.com/api/v3/market/0/1/"
PRODUCT_API_URL_TRANSPORT = "https://www.simcompanies.com/api/v3/market/0/13/"
# Add more product URLs as needed
# PRODUCT_API_URL_WATER = "https://www.simcompanies.com/api/v3/market/0/2/"

CASH_API_URL = "https://www.simcompanies.com/api/v2/companies/me/cashflow/recent/"

# --- Target Products ---
# Use a dictionary to store multiple product URLs and their qualities
TARGET_PRODUCTS = {
    "Power": {"url": PRODUCT_API_URL_POWER, "quality": 0},
    "Transport": {"url": PRODUCT_API_URL_TRANSPORT, "quality": 0},
    # Add more products here, e.g.:
    # "Water": {"url": PRODUCT_API_URL_WATER, "quality": 1},
}

# --- Buying Parameters ---
# Change MAX_BUY_QUANTITY to a dictionary for individual product settings
MAX_BUY_QUANTITY = {
    "Power": 2000,  # Example: Set max quantity for Power
    "Transport": 1000,  # Example: Set max quantity for Transport
    # Add more products here with their respective max quantities
}

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

