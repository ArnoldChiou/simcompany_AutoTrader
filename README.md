# SimCompanies AutoTrader & Monitor

## Project Overview

This project provides a set of tools to automate various tasks within the SimCompanies browser game. It leverages Selenium for web automation and Python scripts to handle tasks like automatic purchasing, production monitoring, and status notifications.

## Features

* **Auto-Buying**: Automatically purchases specified products from the market when prices fall below a defined threshold relative to the second-lowest price.
* **Production & Construction Monitoring**:
    * **Forest Nursery**: Monitors production, automatically starts "Nurture" when ready, handles low-resource situations by initiating "Cut down", and waits for construction/production completion.
    * **Power Plant**: Batch-starts 24-hour production cycles across multiple power plants and monitors their completion times.
    * **Oil Rig**: Monitors construction status, checks resource abundance, and automatically triggers "Rebuild" if abundance drops below 95%.
* **Email Notifications**: Sends email alerts via Gmail for critical events like required logins, completed constructions, or monitoring errors.
* **Selenium Automation**: Uses Selenium with `webdriver-manager` to control a Chrome browser. It supports using a specific Chrome user profile to maintain login sessions.
* **Logging**: Records successful trades and detailed monitoring activities to text files for review.
* **Interactive Menu**: Provides a command-line interface to select which task to run.

## Project Structure

* `main.py`: The main entry point for the application. Displays a menu to select the desired function (Login, Auto-Buy, Monitors).
* `AutoBuyer.py`: Contains the `AutoBuyer` class, handling the logic for automatic market purchases using Selenium.
* `production_monitor.py`: Includes classes (`ForestNurseryMonitor`, `PowerPlantProducer`, `OilRigMonitor`) for monitoring and managing production/construction tasks.
* `config.py`: Central configuration file for API URLs, product lists, purchase thresholds, and market headers.
* `market_utils.py`: Utility functions for fetching market data and current cash using APIs and Selenium.
* `driver_utils.py`: Utility function to initialize the Selenium Chrome WebDriver, supporting the use of user data directories.
* `email_utils.py`: Handles authentication with Google and sending emails via the Gmail API.
* `Trade_main.py`: A simpler market monitor (likely for manual/trigger-based trading).
* `test_cash.py`: A script to test fetching the current cash amount.
* `requirements.txt`: Lists all the necessary Python packages for the project.
* `.env` (To be created): Stores sensitive information like `SESSIONID`, `USER_DATA_DIR`, and email addresses.
* `secret/` (To be created): Stores Google API credentials (`credentials.json`) and token (`token.json`).
* `record/`: Directory for log files (`successful_trade.txt`, `monitor.log`).

## Installation

1.  **Clone/Download:** Get the project files onto your local machine.
2.  **Install Python:** Ensure you have Python 3.x installed.
3.  **Install Dependencies:** Open a terminal or command prompt in the project directory and run:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Create `.env` File:** Create a file named `.env` in the project's root directory. Add the following, replacing the placeholder values:
    ```env
    # Get this from your browser's cookies for SimCompanies
    SESSIONID=your_simcompanies_session_id

    # Find this in chrome://version/ under "Profile Path", use the parent directory
    USER_DATA_DIR=C:\Users\YourUser\AppData\Local\Google\Chrome\User Data

    # Email settings for notifications (optional but recommended)
    MAIL_TO=your_email@example.com
    MAIL_FROM=your_gmail_address@gmail.com
    ```
5.  **Setup Google Cloud & Gmail API:**
    * Go to the [Google Cloud Console](https://console.cloud.google.com/).
    * Create a new project.
    * Enable the "Gmail API".
    * Create "OAuth 2.0 Client IDs" credentials (Type: Desktop App).
    * Download the `credentials.json` file.
    * Create a directory named `secret` in the project root.
    * Place the downloaded `credentials.json` file inside the `secret` directory.
    * The first time you run a feature needing email (like monitors or test email), it will open a browser window asking you to authorize access. After authorization, a `token.json` file will be saved in the `secret` directory.

## Configuration

* **Products & Thresholds:** Modify `PRODUCT_CONFIGS` and `BUY_THRESHOLD_PERCENTAGE` in `config.py` to define which products to buy and the purchase conditions.
* **Building Paths:** If you need to change which specific buildings are monitored (Forest Nurseries, Power Plants), you will need to edit the path lists directly in `main.py` within the `run_forest_nursery_monitor` and `run_power_plant_producer` functions.

## Usage

1.  **Run the Main Script:** Open a terminal or command prompt in the project directory and run:
    ```bash
    python main.py
    ```
2.  **Select an Option:** Use the menu to choose an action:
    * **Login to game**: This is **highly recommended** to run first *if you are not using `USER_DATA_DIR` or if your session has expired*. It opens a browser window for you to log in manually. *Note: The current `AutoBuyer` relies heavily on `USER_DATA_DIR` and might skip manual login.*
    * **Auto-buy**: Starts the automated purchasing bot.
    * **Monitor Forest Nursery**: Starts the Forest Nursery monitoring and automation task.
    * **Produce Power Plant**: Starts the Power Plant batch production task.
    * **Monitor All Oil Rigs**: Starts the Oil Rig monitoring and rebuild task.
    * **Exit**: Closes the application.

## Logs

* Successful purchase records are saved in `record/successful_trade.txt`.
* Detailed logs from the `production_monitor` are saved in `record/monitor.log`.

## Troubleshooting

* **Selenium/WebDriver Errors:** Ensure Chrome is installed. `webdriver-manager` should handle the driver, but if issues arise, check your Chrome version and driver compatibility. Ensure the `USER_DATA_DIR` path in `.env` is correct and accessible.
* **Login Issues:** Make sure your `SESSIONID` (if used by `config.py`, though currently `AutoBuyer` focuses on Selenium profiles) is valid or that your Chrome profile in `USER_DATA_DIR` is logged into SimCompanies.
* **Gmail Errors (`invalid_grant`)**: This usually means your `token.json` has expired or been revoked. Delete `secret/token.json` and run the script again to re-authorize.
* **`ImportError`**: Ensure you have run `pip install -r requirements.txt` and all files are in their correct locations.

## Disclaimer

This tool automates interactions with SimCompanies. Use it responsibly and at your own risk. Be aware of the game's terms of service and rules regarding automation. The developers of this tool are not responsible for any consequences arising from its use.