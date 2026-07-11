# Shared configuration for AutoBuyer and TradeMonitor

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

DEFAULT_MAX_TOTAL_COST = float(os.getenv("DEFAULT_MAX_TOTAL_COST", "50000000"))

# --- API URLs ---
CASH_API_URL = "https://www.simcompanies.com/api/v2/companies/me/cashflow/recent/"

POWER_PLANT_PATHS = [
    "/b/40253730/", "/b/39825683/", "/b/39888395/", "/b/39915579/",
    "/b/53860676/", "/b/39825679/", "/b/39693844/", "/b/39825691/",
    "/b/39825676/", "/b/39825686/", "/b/41178098/",
]

# --- Consolidated Product Configuration ---
# Add new products by adding a new dictionary to this list
PRODUCT_CONFIGS = [
    {
        "name": "Power",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/1/",
        "quality": 0,
        "max_buy_quantity": 10000000,
        "buy_threshold_percentage": 0.94,
        "max_total_cost": 50000000
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
    },
    {
       "name":"Chemicals",
       "api_url": "https://www.simcompanies.com/api/v3/market/0/17/",
       "quality": 0,
       "max_buy_quantity": 10000
    },
    {
        "name": "Minerals",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/14/",
        "quality": 0,
        "max_buy_quantity": 50000
    },
    {
        "name": "Bauxite",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/15/",
        "quality": 0,
        "max_buy_quantity": 50000
    },
    {
        "name": "Aluminium",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/18/",
        "quality": 0,
        "max_buy_quantity": 50000
    },
    {
        "name": "Plastic",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/19/",
        "quality": 0,
        "max_buy_quantity": 50000
    },
    {
        "name": "IronOre",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/42/",
        "quality": 0,
        "max_buy_quantity": 50000
    },
    {
        "name": "Steel",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/43/",
        "quality": 0,
        "max_buy_quantity": 50000
    },
    {
        "name": "Sand",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/44/",
        "quality": 0,
        "max_buy_quantity": 50000
    },
    {
        "name": "Glass",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/45/",
        "quality": 0,
        "max_buy_quantity": 50000
    },
    {
        "name": "GoldOre",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/68/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "GoldenBars",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/69/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "CarbonFibers",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/75/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "CarbonComposite",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/76/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Electronicsresearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/32/",
        "quality": 0,
        "max_buy_quantity": 500
    },
    {
         "name": "Silicon",
         "api_url": "https://www.simcompanies.com/api/v3/market/0/16/",
         "quality": 0,
         "max_buy_quantity": 50000
    },

    {
        "name": "PlantResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/29/",
        "quality": 0,
        "max_buy_quantity": 500
    },
    {
        "name": "BreedingResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/33/",
        "quality": 0,
        "max_buy_quantity": 500
    },
    {
        "name": "ChemistryResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/34/",
        "quality": 0,
        "max_buy_quantity": 500
    },
    {
        "name": "Software",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/35/",
        "quality": 0,
        "max_buy_quantity": 1000
    },
    {
        "name": "AutomotiveResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/58/",
        "quality": 0,
        "max_buy_quantity": 500
    },
    {
        "name": "FashionResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/59/",
        "quality": 0,
        "max_buy_quantity": 500
    },
    {
        "name": "AerospaceResearch",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/100/",
        "quality": 0,
        "max_buy_quantity": 500
    },
    {
        "name": "Recipes",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/145/",
        "quality": 0,
        "max_buy_quantity": 1000
    },
    {
        "name": "Dough",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/137/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Sauce",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/138/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Steak",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/7/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Sausages",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/8/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Eggs",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/9/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Milk",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/117/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "CoffeePowder",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/119/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Flour",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/133/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Bread",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/121/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "ApplePie",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/123/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "OrangeJuice",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/124/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "AppleCider",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/125/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "GingerBeer",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/126/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "FrozenPizza",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/127/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Pasta",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/128/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Butter",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/134/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Cheese",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/122/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Chocolate",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/140/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Sugar",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/135/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Hamburger",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/129/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Lasagna",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/130/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "MeatBalls",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/131/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Cocktails",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/132/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "VegetableOil",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/141/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Salad",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/142/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "Samosa",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/143/",
        "quality": 0,
        "max_buy_quantity": 10000
    },
    {
        "name": "PumpkinSoup",
        "api_url": "https://www.simcompanies.com/api/v3/market/0/149/",
        "quality": 0,
        "max_buy_quantity": 10000
    }
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

BUY_THRESHOLDS = {
    config["name"]: config.get("buy_threshold_percentage", 0.94)
    for config in PRODUCT_CONFIGS
}

MAX_TOTAL_COST = {
    config["name"]: config.get("max_total_cost", DEFAULT_MAX_TOTAL_COST)
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
MIN_CASH_RESERVE = float(os.getenv("MIN_CASH_RESERVE", "5000000"))
DEFAULT_CHECK_INTERVAL_SECONDS = int(os.getenv("AUTOBUY_CYCLE_INTERVAL_SECONDS", "600"))
AUTOBUY_PRODUCT_DELAY_MIN_SECONDS = float(os.getenv("AUTOBUY_PRODUCT_DELAY_MIN_SECONDS", "8"))
AUTOBUY_PRODUCT_DELAY_MAX_SECONDS = float(os.getenv("AUTOBUY_PRODUCT_DELAY_MAX_SECONDS", "15"))
AUTOBUY_RATE_LIMIT_BASE_DELAY_SECONDS = int(os.getenv("AUTOBUY_RATE_LIMIT_BASE_DELAY_SECONDS", "300"))
PURCHASE_WAIT_MULTIPLIER = 1.5

# --- Request Timeouts (seconds) ---
MARKET_REQUEST_TIMEOUT = 20
BUY_REQUEST_TIMEOUT = 30
MONEY_REQUEST_TIMEOUT = 15

# --- Validation ---
if not COOKIES.get('sessionid'):
    print("Error: Please enter a valid COOKIES (sessionid) in config.py.")

