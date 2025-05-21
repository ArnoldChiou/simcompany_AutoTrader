# AutoTrader Project

## Project Overview
AutoTrader is an automated trading system designed for SimCompanies, providing modules for auto-buying, market monitoring, and utility functions. It uses Selenium for browser automation and Python requests for API interactions.

## Project Structure
- `AutoBuyer.py`: Handles automated purchasing of products based on market conditions.
- `Trade_main.py`: Monitors market data and provides manual triggers for purchases.
- `market_utils.py`: Contains utility functions for fetching market data and account information.
- `config.py`: Centralized configuration file for API URLs, product settings, and thresholds.
- `main.py`: Entry point for running the application, offering options for login and auto-buying.
- `.env`: Stores sensitive information like session IDs and user data directory paths.
- `record/successful_trade.txt`: Logs successful trades for record-keeping.
- `requirements.txt`: Lists required Python packages.
- `.gitignore`: Specifies files and directories to exclude from version control.

## Installation
1. Ensure Python 3.13 or above is installed.
2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project root with the following structure:
   ```env
   SESSIONID=your_session_id
   USER_DATA_DIR=path_to_your_chrome_user_data
   ```

## Usage
### Step 1: Login to SimCompanies
1. Run the program and select the login option:
   ```bash
   python main.py
   ```
2. Choose option `1` to open a browser window for manual login.
3. After logging in, close the browser to save the session.

### Step 2: Start Auto-Buying
1. Run the program again and select the auto-buying option:
   ```bash
   python main.py
   ```
2. Choose option `2` to start monitoring and purchasing products based on the configured thresholds.

### Configuration
- **Products**: Add or modify products in `config.py` under `PRODUCT_CONFIGS`. Example:
  ```python
  {
      "name": "NewProduct",
      "api_url": "https://www.simcompanies.com/api/v3/market/0/99/",
      "quality": 1,
      "max_buy_quantity": 5000
  }
  ```
- **Thresholds**: Adjust `BUY_THRESHOLD_PERCENTAGE` in `config.py` to change the price threshold for purchases.

### Logs
- Successful trades are logged in `record/successful_trade.txt` with details like product name, price, and quantity.

## Troubleshooting
- Ensure the `.env` file is correctly configured with a valid `SESSIONID`.
- If Selenium fails to start, verify that ChromeDriver is installed and compatible with your Chrome version.
- For API errors, check the URLs and headers in `config.py`.

## Contact
For questions or issues, please contact the project maintainer.
