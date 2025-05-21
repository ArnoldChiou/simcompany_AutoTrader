from market_utils import get_current_money
from driver_utils import initialize_driver

def test_get_current_money():
    driver = None  # Initialize driver to None for the finally block
    try:
        driver = initialize_driver() # Initialize the Selenium driver
        cash = get_current_money(driver)
        if cash is not None:
            print(f"Successfully obtained cash value: {cash}")
        else:
            print("Unable to obtain cash value, please check Selenium setup or website structure.")
    except Exception as e:
        print(f"An error occurred during the test: {e}")
    finally:
        if driver:
            driver.quit() # Ensure the driver is closed

if __name__ == "__main__":
    test_get_current_money()