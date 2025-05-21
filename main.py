# Import classes
from AutoBuyer import AutoBuyer
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
# Import functions from production_monitor.py
from production_monitor import get_forest_nursery_finish_time, produce_power_plant,monitor_all_oil_rigs_status

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
    try:
        driver = webdriver.Chrome()  # Use Chrome browser
        driver.get("https://www.simcompanies.com/signin/")  # Replace with the game's login page URL

        print("Please log in to the game manually in the browser, then close the browser to continue...")
        input("Press Enter to confirm login is complete: ")
        print("Login information saved, you can continue to use the auto-buy function.")
    except Exception as e:
        print(f"Error occurred during login process: {e}")
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    try:
        print("Please select the function to execute:")
        print("1. Login to game")
        print("2. Auto-buy")
        print("3. Monitor Forest Nursery")
        print("4. Produce Power Plant")
        print("5. Monitor All Oil Rigs") # Added option 5 to the prompt
        mode = input("Enter 1, 2, 3, 4, or 5: ").strip() # Updated input prompt
        if mode == "1":
            login_to_game()
        elif mode == "2":
            run_auto_buyer()
        elif mode == "3":
            get_forest_nursery_finish_time()
        elif mode == "4":
            produce_power_plant()
        elif mode == "5":
            monitor_all_oil_rigs_status()
        else:
            print("Input error, program ended.")
    except KeyboardInterrupt:
        print("\n程式被終止 (Program terminated by user).")
