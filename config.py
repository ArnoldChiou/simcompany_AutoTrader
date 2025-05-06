# Shared configuration for AutoBuyer and TradeMonitor

import os
from dotenv import load_dotenv

# 載入 .env 檔案
load_dotenv()

# --- API URLs ---
CASH_API_URL = "https://www.simcompanies.com/api/v2/companies/me/cashflow/recent/"

# --- Consolidated Product Configuration ---
# Add new products by adding a new dictionary to this list
PRODUCT_CONFIGS = [
    {
        "name": "Power",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/1/",
        "quality": 0,
        "max_buy_quantity": 100000
    },
    {
        "name": "Transport",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/13/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "PlantResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/29/",
        "quality": 0,
        "max_buy_quantity": 10
    },
    # Example of adding a new product:
    # {
    #     "name": "Water",
    #     "api_url": "https://www.simcompanies.com/api/v3/market/0/2/",
    #     "quality": 1,
    #     "max_buy_quantity": 5000
    # },
]

# --- Dynamically Generated Dictionaries (for compatibility) ---
TARGET_PRODUCTS = {
    config["name"]: {"url": config["api_url"], "quality": config["quality"]}
    for config in PRODUCT_CONFIGS
}

MAX_BUY_QUANTITY = {
    config["name"]: config["max_buy_quantity"]
    for config in PRODUCT_CONFIGS
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

