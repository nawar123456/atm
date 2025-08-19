import requests

def get_exchange_rate(from_currency, to_currency):
    """
    استدعاء API للحصول على سعر صرف العملة.
    """
    url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        rate = data['rates'].get(to_currency)
        if not rate:
            return None
        return float(rate)
    except (requests.RequestException, KeyError):
        return None