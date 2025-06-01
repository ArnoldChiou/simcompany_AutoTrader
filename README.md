# SimCompanies AutoTrader & Monitor

## Project Overview

This project offers a suite of tools designed to automate various tasks within the SimCompanies browser game. It utilizes Selenium for web automation and Python scripts to manage tasks such as automatic purchasing, production monitoring, and status notifications.

## Features

*   **Automated Purchasing (Auto-Buying)**: Automatically purchases specified products from the market when prices fall below a defined threshold relative to the second-lowest price.
*   **Production & Construction Monitoring**:
    *   **Forest Nursery**: Monitors production, automatically initiates "Nurture" when ready, handles low-resource situations by starting "Cut down," and awaits construction/production completion.
    *   **Power Plant**: Batch-starts 24-hour production cycles across multiple power plants and monitors their completion.
    *   **Oil Rig**: Monitors construction status, checks resource abundance, and automatically triggers "Rebuild" if abundance drops below 95%.
*   **Email Notifications**: Sends email alerts via Gmail for critical events like required logins, completed constructions, or monitoring errors.
*   **Selenium Automation**: Employs Selenium with `webdriver-manager` to control a Chrome browser. It supports using a specific Chrome user profile to maintain login sessions.
*   **Logging**: Records successful trades and detailed monitoring activities to text files for review.
*   **Interactive Menu**: Provides a command-line interface to select and run tasks.

## Project Structure

*   `main.py`: The main entry point for the application. Displays a menu to select the desired function (Login, Auto-Buy, Monitors).
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