# Shared configuration for AutoBuyer and TradeMonitor

import os
from dotenv import load_dotenv

# Load .env file
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
        "max_buy_quantity": 10000000
    },
    {
        "name": "Water",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/2/",
        "quality": 0,
        "max_buy_quantity": 10000000
    },
    {
        "name": "Transport",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/13/",
        "quality": 0,
        "max_buy_quantity": 100000000
    },
    {
        "name": "MiningResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/31/",
        "quality": 0,
        "max_buy_quantity": 500
    },
    {
        "name": "EnergyResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/30/",
        "quality": 0,
        "max_buy_quantity": 500
    },
    {
        "name":"MaterialsResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/113/",
        "quality": 0,
        "max_buy_quantity": 1000
    }
    #{
    #    "name":"AerospaceResearch",
    #    "api_url": "https://www.simcompanies.com/api/v3/market/0/100/",
    #    "quality": 0,
    #    "max_buy_quantity": 1000
    #},

    #{
    #    "name":"Recipes",
    #    "api_url": "https://www.simcompanies.com/api/v3/market/0/145/",
    #    "quality": 0,
    #    "max_buy_quantity": 1000
    #}

    #{
    #    "name":"BreedingResearch",
    #    "api_url": "https://www.simcompanies.com/api/v3/market/0/33/",
    #    "quality": 0,
    #    "max_buy_quantity": 500
    #}

    #{
    #    "name": "Electronicsresearch",
    #    "api_url": "https://www.simcompanies.com/api/v3/market/0/32/",
    #    "quality": 0,
    #    "max_buy_quantity": 500
    #}

    #{
    #    "name": "PlantResearch",
    #    "api_url": "https://www.simcompanies.com/api/v3/market/0/29/",
    #    "quality": 0,
    #    "max_buy_quantity": 500
    #}

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

# Cookies (IMPORTANT: Update sessionid)
COOKIES = {
    'sessionid': os.getenv('SESSIONID', ''),
}

# --- Logic Parameters ---
if not COOKIES.get('sessionid'):
    print("Error: Please create a .env file and enter a valid SESSIONID. ex: SESSIONID=your_session_id")
    print("If you don't know how to get the Session ID, please refer to README.md")
BUY_THRESHOLD_PERCENTAGE = 0.94
DEFAULT_CHECK_INTERVAL_SECONDS = 300
PURCHASE_WAIT_MULTIPLIER = 1.5

# --- Request Timeouts (seconds) ---
MARKET_REQUEST_TIMEOUT = 20
BUY_REQUEST_TIMEOUT = 30
MONEY_REQUEST_TIMEOUT = 15

# --- Validation ---
if not COOKIES.get('sessionid'):
    print("Error: Please enter a valid COOKIES (sessionid) in config.py.")

