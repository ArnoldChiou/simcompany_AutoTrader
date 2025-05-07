from market_utils import get_current_money
from config import COOKIES, CASH_API_URL, MARKET_HEADERS, MONEY_REQUEST_TIMEOUT
import requests

def test_get_current_money():
    session = requests.Session()
    cash = get_current_money(session, COOKIES, CASH_API_URL, MARKET_HEADERS, MONEY_REQUEST_TIMEOUT)
    if cash is not None:
        print(f"Successfully obtained cash value: {cash}")
    else:
        print("Unable to obtain cash value, please check API or settings.")

if __name__ == "__main__":
    test_get_current_money()