import os
import traceback
import time
import inquirer
from selenium import webdriver
from production_monitor import setup_logger
from AutoBuyer import AutoBuyer
from production_monitor import (
    ForestNurseryMonitor,
    PowerPlantProducer,
    OilRigMonitor,
    BatteryProducer
)
from config import (
    TARGET_PRODUCTS, MAX_BUY_QUANTITY, # Import TARGET_PRODUCTS
    MARKET_HEADERS # Import MARKET_HEADERS
)

def run_auto_buyer():
    print("\nStarting AutoBuyer automatic purchase mode (monitoring all target products)...")
    print(f"Target products: {list(TARGET_PRODUCTS.keys())}") # Show all target product names    print(f"Max purchase quantity: {MAX_BUY_QUANTITY if MAX_BUY_QUANTITY is not None else 'Unlimited'}")
    print("-------------------------------------")
    try:
        user_data_dir = os.getenv("USER_DATA_DIR_autobuy")
        buyer = AutoBuyer(
            target_products=TARGET_PRODUCTS, # Pass the dictionary
            max_buy_quantity=MAX_BUY_QUANTITY, # Pass the dictionary instead of a single value
            market_headers=MARKET_HEADERS,
            headers=None, # AutoBuyer uses MARKET_HEADERS internally for requests
            cookies=None,  # AutoBuyer handles cookies via Selenium profile
            drivers=user_data_dir
        )
        buyer.main_loop()
    except KeyboardInterrupt:
        print("\nUser interrupted auto-buy mode, program ended.")
    except Exception as e:
        print(f"Unexpected error occurred while running AutoBuyer: {e}")
        traceback.print_exc()

def login_to_game():
    print("\nStarting login function...")
    driver = None # Initialize driver
    try:
        # Consider using initialize_driver from driver_utils for consistency
        driver = webdriver.Chrome()  # Use Chrome browser
        driver.get("https://www.simcompanies.com/signin/")  # Replace with the game's login page URL

        print("Please log in to the game manually in the browser...")
        # A more robust way might involve checking cookies or a specific element
        # after login, but manual confirmation is simpler.
        input("Press Enter after you have logged in and are ready to close the browser: ")
        print("Login confirmed by user. Closing browser.")
    except Exception as e:
        print(f"Error occurred during login process: {e}")
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()

# --- Functions to start monitors ---

def run_forest_nursery_monitor(logger):
    """Starts the Forest Nursery monitor."""
    fn_paths = ["/b/43694783/"] # Or load from config
    user_data_dir = os.getenv("USER_DATA_DIR_forestnursery")
    monitor = ForestNurseryMonitor(fn_paths, logger=logger, user_data_dir=user_data_dir)
    monitor.run()


def run_power_plant_producer(logger):
    """Starts the Power Plant producer."""
    pp_paths = [
        "/b/40253730/", "/b/39825683/", "/b/39888395/", "/b/39915579/",
        "/b/39825725/", "/b/39825679/", "/b/39693844/",
        "/b/39825691/", "/b/39825676/", "/b/39825686/", "/b/41178098/",
    ] # Or load from config
    user_data_dir = os.getenv("USER_DATA_DIR_powerplant")
    producer = PowerPlantProducer(pp_paths, logger=logger, user_data_dir=user_data_dir)
    producer.run()


def run_oil_rig_monitor(logger):
    """Starts the Oil Rig monitor."""
    user_data_dir = os.getenv("USER_DATA_DIR_oiirig")
    monitor = OilRigMonitor(logger=logger, user_data_dir=user_data_dir)
    monitor.run()

def run_battery_producer(logger):
    """Starts the Battery producer."""
    battery_path = "/b/46938475/" # 這是你的目標 URL
    # 你可能需要為這個 profile 在 .env 中設定一個新的 USER_DATA_DIR
    # 例如 USER_DATA_DIR_battery
    user_data_dir = os.getenv("USER_DATA_DIR_battery") 
    producer = BatteryProducer(battery_path, logger=logger, user_data_dir=user_data_dir)
    producer.run()

def run_init_all_profiles():
    import subprocess
    print("\n開始初始化所有 Chrome profiles ...")
    try:
        # 直接呼叫 python init_all_profiles.py
        subprocess.run(["python", "init_all_profiles.py"], check=True)
    except Exception as e:
        print(f"初始化 profiles 發生錯誤: {e}")

if __name__ == "__main__":
    try:
        questions = [
            inquirer.List(
                "mode",
                message="請選擇要執行的功能:",
                choices=[
                    ("Login to game", "1"),
                    ("Auto-buy", "2"),
                    ("Monitor Forest Nursery", "3"),
                    ("Produce Power Plant", "4"),
                    ("Monitor All Oil Rigs", "5"),
                    ("Produce Batteries", "6"),
                    ("Init all Chrome profiles", "init_profiles"),
                    ("Exit", "exit"),
                ],
            ),
        ]
        answers = inquirer.prompt(questions)

        if not answers:
            print("\nNo selection made, program ended.")
            exit()

        mode = answers["mode"]

        if mode == "1":
            login_to_game()
        elif mode == "2":
            run_auto_buyer()
        elif mode == "3":
            logger = setup_logger("production_monitor.forest", "monitor_forest.log")
            run_forest_nursery_monitor(logger)
        elif mode == "4":
            logger = setup_logger("production_monitor.powerplant", "monitor_powerplant.log")
            run_power_plant_producer(logger)
        elif mode == "5":
            logger = setup_logger("production_monitor.oilrig", "monitor_oilrig.log")
            run_oil_rig_monitor(logger)
        elif mode == "6":
            logger = setup_logger("production_monitor.battery", "monitor_battery.log")
            run_battery_producer(logger)
        elif mode == "init_profiles":
            run_init_all_profiles()
        elif mode == "exit":
            print("Program ended.")
        else:
            print("Invalid selection, program ended.")

    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred in main.py: {e}")
        traceback.print_exc()