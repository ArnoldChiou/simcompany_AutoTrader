# Import classes
from AutoBuyer import AutoBuyer
import traceback
from selenium import webdriver
# from selenium.webdriver.common.by import By # No longer used directly here
# from selenium.webdriver.common.keys import Keys # No longer used directly here
import time
import inquirer # Import inquirer
# Import NEW classes from production_monitor.py
from production_monitor import (
    ForestNurseryMonitor,
    PowerPlantProducer,
    OilRigMonitor
)

# Import shared configurations from config.py
from config import (
    TARGET_PRODUCTS, MAX_BUY_QUANTITY, # Import TARGET_PRODUCTS
    MARKET_HEADERS # Import MARKET_HEADERS
)

def run_auto_buyer():
    print("\nStarting AutoBuyer automatic purchase mode (monitoring all target products)...")
    print(f"Target products: {list(TARGET_PRODUCTS.keys())}") # Show all target product names
    print(f"Max purchase quantity: {MAX_BUY_QUANTITY if MAX_BUY_QUANTITY is not None else 'Unlimited'}")
    print("-------------------------------------")
    try:
        buyer = AutoBuyer(
            target_products=TARGET_PRODUCTS, # Pass the dictionary
            max_buy_quantity=MAX_BUY_QUANTITY, # Pass the dictionary instead of a single value
            market_headers=MARKET_HEADERS,
            headers=None, # AutoBuyer uses MARKET_HEADERS internally for requests
            cookies=None, # AutoBuyer handles cookies via Selenium profile
            driver=None
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

def run_forest_nursery_monitor():
    """Starts the Forest Nursery monitor."""
    # --- IMPORTANT: Define your Forest Nursery paths here ---
    fn_paths = ["/b/43694783/"] # Or load from config
    monitor = ForestNurseryMonitor(fn_paths)
    monitor.run()


def run_power_plant_producer():
    """Starts the Power Plant producer."""
    # --- IMPORTANT: Define your Power Plant paths here ---
    pp_paths = [
        "/b/40253730/", "/b/39825683/", "/b/39888395/", "/b/39915579/",
        "/b/43058380/", "/b/39825725/", "/b/39825679/", "/b/39693844/",
        "/b/39825691/", "/b/39825676/", "/b/39825686/", "/b/41178098/",
    ] # Or load from config
    producer = PowerPlantProducer(pp_paths)
    producer.run()


def run_oil_rig_monitor():
    """Starts the Oil Rig monitor."""
    monitor = OilRigMonitor()
    monitor.run()


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
            # Call the new function for Forest Nursery
            run_forest_nursery_monitor()
        elif mode == "4":
            # Call the new function for Power Plant
            run_power_plant_producer()
        elif mode == "5":
            # Call the new function for Oil Rigs
            run_oil_rig_monitor()
        elif mode == "exit":
            print("Program ended.")
        else:
            print("Invalid selection, program ended.")

    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred in main.py: {e}")
        traceback.print_exc()