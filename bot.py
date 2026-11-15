import os, json, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
KEY = os.environ["TWELVE_DATA_KEY"]
LOG = "signals.json"
MINS = {"5min": 5, "15min": 15, "1h": 60, "4h": 240}
MIN_RISK = {"SCALP": 2.0, "SWING": 8.0}
PROFILES = {
    "SCALP": {"entry": "5min", "trend": "15min", "rr": [1.5, 2, 3], "max_age": 12, "cooldown": 30},
    "SWING": {"entry": "1h", "trend": "4h", "rr": [2, 3, 5], "max_age": 25, "cooldown": 360},
}


def fetch(interval, size=120):
    q = urllib.parse.urlencode({"symbol": "XAU/USD", "interval": interval,
                                "outputsize": size, "timezone": "UTC", "apikey": KEY})
    with urllib.request.urlopen("https://api.twelvedata.com/time_series?" + q, timeout=20) as r:
        d = json.loads(r.read())
    if "values" not in d:
        raise RuntimeError(f"Data error: {d.get('message', d)}")
    rows = list(reversed(d["values"]))[:-1]  # oldest first, drop forming candle
    return [{"t": datetime.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc),
             "o": float(v["open"]), "h": float(v["high"]),
             "l": float(v["low"]), "c": float(v["close"])} for v in rows]


def ema(vals, n):
    k = 2 / (n + 1)
    e = vals[0]
    out = [e]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def atr(c, n=14):
    trs = [max(x["h"] - x["l"], abs(x["h"] - p["c"]), abs(x["l"] - p["c"]))
           for p, x in zip(c, c[1:])]
    return sum(trs[-n:]) / n


def swings(c, k=2):
    hi, lo = [], []
    for i in range(k, len(c) - k):
        w = c[i - k:i + k + 1]
        if c[i]["h"] == max(x["h"] for x in w):
            hi.append(c[i]["h"])
        if c[i]["l"] == min(x["l"] for x in w):
            lo.append(c[i]["l"])
    return hi, lo


def trend(c):
    cl = [x["c"] for x in c]
    e20, e50 = ema(cl, 20)[-1], ema(cl, 50)[-1]
    hi, lo = swings(c)
    ok = len(hi) > 1 and len(lo) > 1
    if e20 > e50 and cl[-1] > e50:
        return "UP", ok and hi[-1] > hi[-2] and lo[-1] > lo[-2]
    if e20 < e50 and cl[-1] < e50:
        return "DOWN", ok and hi[-1] < hi[-2] and lo[-1] < lo[-2]
    return "RANGE", False


def build(name, p, side, kind, strategy, entry, sl, a, score, bias):
    risk = abs(entry - sl)
    if risk < max(0.5 * a, MIN_RISK[name]) or risk > 3 * a:
        return None
    sg = 1 if side == "BUY" else -1
    return {"profile": name, "tf": p["entry"], "trend_tf": p["trend"], "side": side,
            "kind": kind, "strategy": strategy, "entry": entry, "sl": sl,
            "rr": p["rr"], "tps": [entry + sg * risk * r for r in p["rr"]],
            "score": int(score), "bias": bias}


def analyse(name, p, ec, tc):
    bias, struct = trend(tc)
    cl = [x["c"] for x in ec]
    e20, e50 = ema(cl, 20)[-1], ema(cl, 50)[-1]
    a = atr(ec)
    last = ec[-1]
    rng = last["h"] - last["l"]
    strong = rng > 0 and abs(last["c"] - last["o"]) > 0.5 * rng
    bull, bear = last["c"] > last["o"], last["c"] < last["o"]
    hi, lo = swings(ec)
    f = []
    if bias == "UP" and e20 > e50 and last["l"] <= e20 + 0.1 * a and last["c"] > e20 and bull:
        sl = min(x["l"] for x in ec[-8:]) - 0.2 * a
        f.append(build(name, p, "BUY", "Continuation", "Price Action + EMA trend pullback",
                       last["c"], sl, a, 3 + struct + strong, bias))
    if bias == "DOWN" and e20 < e50 and last["h"] >= e20 - 0.1 * a and last["c"] 
