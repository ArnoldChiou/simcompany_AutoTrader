from market_utils import get_current_money
from config import COOKIES, CASH_API_URL, MARKET_HEADERS, MONEY_REQUEST_TIMEOUT
import requests

def test_get_current_money():
    session = requests.Session()
    cash = get_current_money(session, COOKIES, CASH_API_URL, MARKET_HEADERS, MONEY_REQUEST_TIMEOUT)
    if cash is not None:
        print(f"成功取得現金數值: {cash}")
    else:
        print("無法取得現金數值，請檢查 API 或設定。")

if __name__ == "__main__":
    test_get_current_money()