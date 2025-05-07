import requests
import json
import traceback

def get_market_data(session, api_url, target_quality, timeout=20, return_order_detail=False):
    print(f"--- Start processing Q{target_quality} market data (API: {api_url}) ---")
    try:
        response = session.get(api_url, timeout=timeout)
        response.raise_for_status()
        try:
            orders = response.json()
        except json.JSONDecodeError:
            print("Error: Unable to parse JSON data from API response.")
            print(f"Response content: {response.text[:500]}...")
            return None
        if not isinstance(orders, list):
            print("Error: API response format is not the expected list.")
            return None
        if not orders:
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
        print(f"Error: Request to API {api_url} timed out.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: Request to API {api_url} failed: {e}")
        return None
    except Exception as e:
        print(f"Error: Unexpected error occurred while processing market data:")
        traceback.print_exc()
        return None

def get_current_money(session, cookies, cash_api_url, market_headers, money_request_timeout):
    url = cash_api_url
    try:
        session_to_use = session if session.cookies else requests.Session()
        session_to_use.headers.update(market_headers)
        if not session_to_use.cookies and cookies.get('sessionid'):
            session_to_use.cookies.update(cookies)

        response = session_to_use.get(url, timeout=money_request_timeout)
        response.raise_for_status()
        data = response.json()
        
        # Extract the 'money' field from the response
        money_data = data.get("money")
        if money_data is not None:
            print(f"Account cash obtained (API): {money_data}")
            return money_data
        else:
            print("Warning: Expected cash field not found in API response.")
            print(f"API Response sample: {str(data)[:200]}...")
            return None
    except requests.exceptions.Timeout:
        print(f"Request timed out while obtaining account cash ({url}).")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Request error occurred while obtaining account cash ({url}): {e}")
        if e.response is not None:
            print(f"Full response content: {e.response.text[:500]}...")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON while obtaining account cash ({url}): {e}")
        if response is not None:
            print(f"Response content: {response.text[:500]}...")
        return None
    except Exception as e:
        print(f"Unexpected error occurred while obtaining account cash:")
        traceback.print_exc()
        return None
