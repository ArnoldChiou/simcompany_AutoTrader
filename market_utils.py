import requests
import json
import traceback

def get_market_data(session, api_url, target_quality, timeout=20, return_order_detail=False):
    print(f"--- 開始處理 Q{target_quality} 市場數據 (API: {api_url}) ---")
    try:
        response = session.get(api_url, timeout=timeout)
        response.raise_for_status()
        try:
            orders = response.json()
        except json.JSONDecodeError:
            print("錯誤：無法解析 API 回應的 JSON 數據。")
            print(f"回應內容: {response.text[:500]}...")
            return None
        if not isinstance(orders, list):
            print("錯誤：API 回應的格式不是預期的列表。")
            return None
        if not orders:
            print("警告：API 回應中沒有任何訂單數據。")
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
            print(f"警告：未找到任何有效的 Q{target_quality} 賣單。")
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
        print(f"錯誤：請求 API {api_url} 超時。")
        return None
    except requests.exceptions.RequestException as e:
        print(f"錯誤：請求 API {api_url} 失敗: {e}")
        return None
    except Exception as e:
        print(f"錯誤：處理市場數據時發生不可預期的錯誤:")
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
        money_data = data.get("cash", {}).get("value")
        if money_data is not None:
            print(f"取得帳戶現金 (API): {money_data}")
            return money_data
        else:
            print("警告：API 回應中未找到預期的現金欄位。")
            print(f"API Response sample: {str(data)[:200]}...")
            return None
    except requests.exceptions.Timeout:
        print(f"取得帳戶現金時請求超時 ({url})。")
        return None
    except requests.exceptions.RequestException as e:
        print(f"取得帳戶現金時發生請求錯誤 ({url}): {e}")
        if e.response is not None:
            print(f"Status Code: {e.response.status_code}")
        return None
    except json.JSONDecodeError:
        print(f"取得帳戶現金時解析 JSON 失敗 ({url})。")
        return None
    except Exception as e:
        print(f"取得帳戶現金時發生不可預期的錯誤:")
        traceback.print_exc()
        return None
