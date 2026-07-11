import requests
import json
import traceback
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re

def get_market_data(session, api_url, target_quality, timeout=20, return_order_detail=False, error_details=None):
    if error_details is not None:
        error_details.clear()

    def set_error(kind, message, status_code=None, retry_after=None):
        if error_details is not None:
            error_details.update({
                'kind': kind,
                'message': message,
                'status_code': status_code,
                'retry_after': retry_after,
            })

    print(f"--- Start processing Q{target_quality} market data (API: {api_url}) ---")
    try:
        response = session.get(api_url, timeout=timeout)
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After')
            set_error('rate_limited', 'HTTP 429 Too Many Requests', 429, retry_after)
        response.raise_for_status()
        try:
            orders = response.json()
        except json.JSONDecodeError:
            set_error('invalid_json', 'API response was not valid JSON', response.status_code)
            print("Error: Unable to parse JSON data from API response.")
            print(f"Response content: {response.text[:500]}...")
            return None
        if not isinstance(orders, list):
            set_error('invalid_response', 'API response was not a list', response.status_code)
            print("Error: API response format is not the expected list.")
            return None
        if not orders:
            set_error('empty_market', 'API returned no market orders', response.status_code)
            print("Warning: No order data found in API response.")
            return None
        filtered = []
        for i, order in enumerate(orders):
            quality = order.get('quality')
            price = order.get('price')
            quantity = order.get('quantity')
            order_id = order.get('id')
            if quality is None or price is None or quantity is None:
                continue
            try:
                quality = int(quality)
                price = float(price)
                quantity = int(quantity)
            except (ValueError, TypeError):
                continue
            if quality >= target_quality and price > 0 and quantity > 0:
                if return_order_detail and order_id is not None:
                    filtered.append({'id': order_id, 'price': price, 'quantity': quantity})
                else:
                    filtered.append(price)
        if not filtered:
            set_error('no_valid_orders', f'No valid Q{target_quality} sell orders', response.status_code)
            print(f"Warning: No valid Q{target_quality} sell orders found.")
            return None
        if return_order_detail:
            filtered.sort(key=lambda x: x['price'])
            lowest_order = filtered[0]
            lowest_price = lowest_order['price']
            second_lowest_price = None
            for o in filtered:
                if o['price'] > lowest_price:
                    second_lowest_price = o['price']
                    break
            result = {'lowest_order': lowest_order}
            if second_lowest_price is not None:
                result['second_lowest_price'] = second_lowest_price
            return result
        else:
            distinct_prices = sorted(list(set(filtered)))
            if len(distinct_prices) >= 2:
                return {'lowest_price': distinct_prices[0], 'second_lowest_price': distinct_prices[1]}
            elif len(distinct_prices) == 1:
                return {'lowest_price': distinct_prices[0]}
            else:
                return None
    except requests.exceptions.Timeout:
        set_error('timeout', f'Request timed out after {timeout}s')
        print(f"Error: Request to API {api_url} timed out.")
        return None
    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else None
        if status_code != 429:
            kind = 'server_error' if status_code and status_code >= 500 else 'http_error'
            set_error(kind, str(e), status_code)
        print(f"Error: Request to API {api_url} failed: {e}")
        return None
    except Exception as e:
        set_error('unexpected_error', f'{type(e).__name__}: {e}')
        print(f"Error: Unexpected error occurred while processing market data:")
        traceback.print_exc()
        return None

def get_current_money(driver, landscape_url="https://www.simcompanies.com/landscape/"):
    try:
        print(f"Navigating to {landscape_url}...")
        driver.get(landscape_url)
        # Wait for the money element to be present and visible
        money_element = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.ID, "js-animation-money"))
        )
        money_text = money_element.text
        # Extract the numerical value using regex, removing $ and commas
        match = re.search(r"\$([\d,]+\.?\d*)", money_text)
        if match:
            cash_value_str = match.group(1).replace(",", "")
            cash_value = float(cash_value_str)
            print(f"Account cash obtained (Selenium): {cash_value}")
            return cash_value
        else:
            print("Warning: Could not extract cash value from element.")
            print(f"Element text: {money_text}")
            return None
    except Exception as e:
        print(f"Unexpected error occurred while obtaining account cash via Selenium:")
        traceback.print_exc()
        return None
