import os
import json
import urllib.request
import urllib.parse

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
KEY = os.environ["TWELVE_DATA_KEY"]


def get_gold_price():
    url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={KEY}"
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read())
    if "price" not in data:
        raise RuntimeError(f"Data error: {data}")
    return float(data["price"])


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    urllib.request.urlopen(url, data=body, timeout=20)


if __name__ == "__main__":
    try:
        price = get_gold_price()
        send_telegram(f"DM Minah is online.\nXAUUSD: {price:.2f}")
    except Exception as e:
        send_telegram(f"DM Minah error: {e}")
        raise
