# SimCompanies AutoTrader & Monitor

## Project Overview

This project offers a suite of tools designed to automate various tasks within the SimCompanies browser game. It utilizes Selenium for web automation and Python scripts to manage tasks such as automatic purchasing, production monitoring, and status notifications.

## Features

*   **Automated Purchasing (Auto-Buying)**: Automatically purchases specified products from the market when prices fall below a defined threshold relative to the second-lowest price.
*   **Production & Construction Monitoring**:
    *   **Forest Nursery**: Monitors production, automatically initiates "Nurture" when ready, handles low-resource situations by starting "Cut down," and awaits construction/production completion.
    *   **Power Plant**: Batch-starts 24-hour production cycles across multiple power plants and monitors their completion.
    *   **Oil Rig**: Monitors construction status, checks resource abundance, and automatically triggers "Rebuild" if abundance drops below 95%.
*   **Telegram Activity Notifications**: Scans every building on your Landscape and sends a Telegram message when construction or product production completes.
*   **Retail Profit Advisor**: When `/b/54696865/` finishes selling and becomes idle, appends a 48-hour product ranking to its Telegram completion notice. It subtracts the quantity-weighted cost of buying each product from the Exchange; it never submits a buy or production order.
*   **Building Product Profit Advisor**: `building_profit_advisor.py` reads the authenticated Landscape, deduplicates building instances, lists each product for owned production-building types, and ranks products by estimated Q0 unit gross margin using current SimcoTools prices and game recipe constants. It is read-only; wages, transport, exchange fees, and building production modifiers are excluded.
*   **Warehouse VWAP company-description updater**: Reads positive, unblocked warehouse stock for every quality, fetches daily VWAP from SimcoTools, prices each listing 2% below VWAP (three decimals below $1; otherwise two), groups products by the category sections shown on the warehouse page in a text table, and updates only the listing section in the public company description through the game's settings form. It backs up the original description and verifies the saved text by reading it back.
*   **Daily VWAP Telegram report**: The daily Task Scheduler entry point `run_company_vwap_update.py` sends the full warehouse-category report after a verified update (or an unchanged-price check), using `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from `.env`. Messages include product names, quality, and the exact discounted listing prices; long reports are split into safe Telegram-sized parts. Update failures send a failure notice. Telegram delivery failure returns exit code 2 rather than marking the task successful; update failure returns 1.
*   **Email Notifications**: Sends email alerts via Gmail for critical events like required logins, completed constructions, or monitoring errors.
*   **Selenium Automation**: Employs Selenium with `webdriver-manager` to control a Chrome browser. It supports using a specific Chrome user profile to maintain login sessions.
*   **Logging**: Records successful trades and detailed monitoring activities to text files for review.
*   **Interactive Menu**: Provides a command-line interface to select and run tasks.

## Project Structure

*   `main.py`: The main entry point for the application. Displays a menu to select the desired function (Login, Auto-Buy, Monitors).
*   `company_vwap_updater.py`: Reads warehouse stock, fetches matching VWAPs from SimcoTools, and updates the company-description listing.
*   `retail_profit_advisor.py`: Reads the retail form and calculates expected net profit against quantity-weighted Exchange purchase prices; it never submits an order.
*   `building_profit_advisor.py`: Read-only Landscape inventory and product gross-margin comparison by owned production-building type.
*   `AutoBuyer.py`: Contains the `AutoBuyer` class, handling the logic for automatic market purchases using Selenium.
*   `production_monitor.py`: Includes classes (`ForestNurseryMonitor`, `PowerPlantProducer`, `OilRigMonitor`) for monitoring and managing production/construction tasks.
*   `config.py`: Central configuration file for API URLs, product lists, purchase thresholds, and market headers.
*   `market_utils.py`: Utility functions for fetching market data and current cash using APIs and Selenium.
*   `driver_utils.py`: Utility function to initialize the Selenium Chrome WebDriver, supporting the use of user data directories.
*   `email_utils.py`: Handles authentication with Google and sending emails via the Gmail API.
*   `Trade_main.py`: A simpler market monitor (likely for manual or trigger-based trading).
*   `test_cash.py`: A script to test fetching the current cash amount.
*   `requirements.txt`: Lists all necessary Python packages for the project.
*   `.env` (To be created): Stores sensitive information like `SESSIONID`, `USER_DATA_DIR`, and email addresses.
*   `secret/` (To be created): Stores Google API credentials (`credentials.json`) and token (`token.json`).
*   `record/`: Directory for log files.

## File Descriptions

*   `AutoBuyer.py`: Handles automated purchasing of items from the in-game market.
*   `config.py`: Contains configuration settings for the application, such as API endpoints and product details.
*   `driver_utils.py`: Provides utility functions for initializing and managing the Selenium WebDriver.
*   `email_utils.py`: Manages sending email notifications.
*   `init_all_profiles.py`: Script to initialize all Chrome profiles for different automation tasks.
*   `main.py`: The main entry point of the application, providing a menu to run different tasks.
*   `market_utils.py`: Contains utility functions for fetching and processing market data.
*   `production_monitor.py`: Monitors and manages in-game production and construction tasks.
*   `test_cash.py`: A script for testing the functionality of fetching the current in-game cash amount.
*   `Trade_main.py`: Likely an alternative or supplementary script for market monitoring or trading.

## Installation

1.  **Clone/Download Repository:** Clone or download the project files to your local machine.
2.  **Install Python:** Ensure Python 3.x is installed on your system.
3.  **Install Dependencies:** Open a terminal or command prompt in the project directory and run:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Create `.env` File:** In the project's root directory, create a file named `.env`. Add the following content, replacing placeholder values with your actual information:
    ```env
    # Obtain this from your browser's cookies for SimCompanies
    SESSIONID=your_simcompanies_session_id

    # Find this in chrome://version/ under "Profile Path" (use the parent directory of "Profile Path")
    USER_DATA_DIR=C:\Users\YourUser\AppData\Local\Google\Chrome\User Data

    # Email settings for notifications (optional but recommended)
    MAIL_TO=your_recipient_email@example.com
    MAIL_FROM=your_gmail_address@gmail.com

    # Telegram settings for the all-building construction monitor
    # Create a bot with @BotFather, then start a chat with that bot.
    TELEGRAM_BOT_TOKEN=123456789:your_bot_token
    TELEGRAM_CHAT_ID=your_telegram_chat_id
    USER_DATA_DIR_construction_monitor=C:\Users\YourUser\AppData\Local\Google\Chrome\User Data
    # Do not share this directory with Forest Nursery or another Selenium service.
    # Idle/manual buildings are rechecked hourly; active buildings are scanned
    # at their recorded completion time.
    ACTIVITY_MANUAL_RECHECK_SECONDS=3600
    TELEGRAM_IGNORED_PRODUCTS=POWER
    # Optional separate profile; otherwise the construction-monitor profile is used.
    USER_DATA_DIR_retail_advisor=C:\Users\YourUser\AppData\Local\Google\Chrome\User Data
    RETAIL_ADVISOR_BUILDING_PATH=/b/54696865/
    RETAIL_ADVISOR_HOURS=48
    RETAIL_ADVISOR_REALM=0
    ```
5.  **Set up Google Cloud & Gmail API:**
    *   Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
    *   Create a new project or select an existing one.
    *   Enable the "Gmail API" for your project.
    *   Create OAuth 2.0 Client ID credentials (Application type: Desktop app).
    *   Download the `credentials.json` file.
    *   Create a directory named `secret` in the project root.
    *   Place the downloaded `credentials.json` file into the `secret` directory.
    *   When you first run a feature requiring email access (e.g., monitors, test email), your browser will open to prompt for authorization. Upon successful authorization, a `token.json` file will be saved in the `secret` directory.

## Configuration

*   **Products & Thresholds:** Modify `PRODUCT_CONFIGS` and `BUY_THRESHOLD_PERCENTAGE` in `config.py` to define which products to monitor and the conditions for purchasing.
*   **Building Paths:** To change which specific buildings are monitored (e.g., Forest Nurseries, Power Plants), you will need to edit the path lists directly in `main.py` within the respective functions (e.g., `run_forest_nursery_monitor`, `run_power_plant_producer`).
*   **All-building Telegram monitor:** Select **Monitor All Construction & Product Completions (Telegram)**. It opens your Landscape, finds every `/b/.../` building, and remembers active construction and product timers in `record/building_activity_state.json`. The first scan only establishes a baseline; later scans notify when either activity completes. Use **Send Telegram Test** to verify the token and chat ID first.
*   **Retail-profit advisor:** The target defaults to `/b/54696865/`. When its tracked sale completes and the building becomes idle, the Telegram message lists its retail products ordered by approximately 48-hour net profit. Product IDs and names come directly from the page. Net profit is `(retail revenue per unit − wages per unit − Exchange VWAP) × quantity`. The game's **Retailing breakdown** supplies revenue, wages, and COGS: any warehouse book cost already deducted from the headline profit is added back before replacing it with market cost. Exchange sourcing accepts the preview quality or higher; the preview's sales speed is retained without assuming extra capacity for higher-quality purchases. The program fills `48hr` and Average price, uses the quantity arrows to reveal the integer quantity, and reads the Help breakdown. It does not submit orders. Run the same calculation any time from menu option **Compare Retail Profit (48h, Telegram)**, including while the current sale is still running.

## Usage

1.  **Run the Main Script:** Open a terminal or command prompt in the project directory and execute:
    ```bash
    python main.py
    ```
2.  **Select an Option:** Use the displayed menu to choose an action:
    *   **Login to game**: It is **highly recommended** to run this option first, especially if you are not using `USER_DATA_DIR` or if your game session has expired. This action opens a browser window for manual login. *Note: The `AutoBuyer` currently relies heavily on `USER_DATA_DIR` and may bypass manual login if a valid session exists in the specified Chrome profile.*
    *   **Auto-buy**: Starts the automated purchasing bot.
    *   **Monitor Forest Nursery**: Initiates the Forest Nursery monitoring and automation task.
    *   **Produce Power Plant**: Begins the Power Plant batch production task.
    *   **Monitor All Oil Rigs**: Starts the Oil Rig monitoring and rebuild task.
    *   **Monitor All Construction & Product Completions (Telegram)**: Monitors every building shown on Landscape and sends a Telegram alert after construction or product production completes.
    *   **Compare Retail Profit (48h, Telegram)**: Runs the same read-only comparison immediately and sends the ranking to Telegram.
    *   **Compare products by owned production buildings**: Run `python building_profit_advisor.py` for a read-only report of unique owned building types, their producible products, Q0 latest-trade prices, estimated unit gross margins, and the best-margin product per type. Uses `USER_DATA_DIR_construction_monitor` from `.env` (or `SIMCOMPANIES_VWAP_PROFILE`).
    *   **Update company description from warehouse VWAPs**: Scans the signed-in warehouse, lists each stocked product quality at 2% below its SimcoTools daily VWAP (three decimals for prices below $1; otherwise two), grouped by the exact category sections shown on the warehouse page in a text table, and saves the listing to the `Change company description` area. The original text is backed up and the saved description is read back for verification. Uses `USER_DATA_DIR_construction_monitor` unless `SIMCOMPANIES_VWAP_PROFILE` is set.
    *   **Exit**: Closes the application.

## Logs

*   Successful purchase records are stored in `record/successful_trade.txt`.
*   Error logs for the auto-buyer can be found in `record/autobuyer_error.log`.
*   Detailed logs from production monitoring tasks are saved in the `record/` directory, including:
    *   `record/monitor_forest.log` (for Forest Nursery)
    *   `record/monitor_oilrig.log` (for Oil Rigs)
    *   `record/monitor_powerplant.log` (for Power Plants)
    *   `record/finish_time.txt` (records production completion times)

## Troubleshooting

*   **Selenium/WebDriver Errors:** Ensure Chrome is installed. `webdriver-manager` is intended to handle the driver automatically. If issues arise, verify your Chrome browser version and ensure its compatibility with the WebDriver. Confirm that the `USER_DATA_DIR` path in your `.env` file is correct and accessible.
*   **Login Issues:** If not using `USER_DATA_DIR`, ensure your `SESSIONID` (if utilized by `config.py`, though `AutoBuyer` primarily uses Selenium profiles) is valid. If using `USER_DATA_DIR`, confirm that your Chrome profile is logged into SimCompanies.
*   **Gmail Errors (`invalid_grant`)**: This error typically indicates that your `token.json` has expired or been revoked. To resolve this, delete the `secret/token.json` file and re-run the script. This will re-initiate the authorization process.
*   **`ImportError`**: Make sure you have successfully installed all dependencies by running `pip install -r requirements.txt`. Also, verify that all project files are in their correct locations as per the project structure.

## Disclaimer

This tool automates interactions with the SimCompanies game. Use it responsibly and at your own risk. Be mindful of the game's terms of service and any rules regarding automation. The developers of this tool are not liable for any consequences that may arise from its use.
