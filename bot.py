import os, json, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
KEY = os.environ["TWELVE_DATA_KEY"]
LOG = "signals.json"
MINS = {"5min": 5, "15min": 15, "1h": 60, "4h": 240}
MIN_RISK = {"SCALP": 2.0, "SWING": 8.0}
PIP = 0.10  # 1 pip = 0.10 on gold (10 pips = $1 move)
PROFILES = {
    "SCALP": {"entry": "5min", "trend": "15min", "rr": [1.5, 3, 5], "max_age": 12, "cooldown": 30},
    "SWING": {"entry": "1h", "trend": "4h", "rr": [2, 4, 6], "max_age": 25, "cooldown": 360},
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
    if bias == "DOWN" and e20 < e50 and last["h"] >= e20 - 0.1 * a and last["c"] < e20 and bear:
        sl = max(x["h"] for x in ec[-8:]) + 0.2 * a
        f.append(build(name, p, "SELL", "Continuation", "Price Action + EMA trend pullback",
                       last["c"], sl, a, 3 + struct + strong, bias))
    if hi and last["h"] > hi[-1] and last["c"] < hi[-1] and bear and strong:
        score = 3 + (bias != "UP") + (e20 < e50)
        if score >= 4:
            f.append(build(name, p, "SELL", "Reversal", "Liquidity sweep above swing high",
                           last["c"], last["h"] + 0.2 * a, a, score, bias))
    if lo and last["l"] < lo[-1] and last["c"] > lo[-1] and bull and strong:
        score = 3 + (bias != "DOWN") + (e20 > e50)
        if score >= 4:
            f.append(build(name, p, "BUY", "Reversal", "Liquidity sweep below swing low",
                           last["c"], last["l"] - 0.2 * a, a, score, bias))
    return [x for x in f if x]


def pips(a, b):
    return abs(a - b) / PIP


def fmt(s):
    icon = "🟢" if s["side"] == "BUY" else "🔴"
    lines = []
    prev = s["entry"]
    for i, (t, r) in enumerate(zip(s["tps"], s["rr"])):
        extra = f" (+{pips(t, prev):.0f} from TP{i})" if i else ""
        lines.append(f"TP{i+1}: {t:.2f} | {pips(t, s['entry']):.0f} pips | 1:{r}{extra}")
        prev = t
    return (f"{icon} {s['side']} XAUUSD | {s['profile']} ({s['tf']})\n"
            f"Type: {s['kind']}\nStrategy: {s['strategy']}\n"
            f"Entry: {s['entry']:.2f}\n"
            f"SL: {s['sl']:.2f} | {pips(s['sl'], s['entry']):.0f} pips\n"
            + "\n".join(lines) +
            f"\nTrend bias ({s['trend_tf']}): {s['bias']}\n"
            f"Rule score: {s['score']}/5\n\n"
            f"Trade plan:\n"
            f"- TP1 hit: move SL to entry\n"
            f"- TP2 hit: move SL to TP1\n"
            f"- TP3 hit: close the trade\n"
            f"I will message you at each step and warn you if the market shifts.\n"
            f"Analysis only, not financial advice.")


def send(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    urllib.request.urlopen(url, data=body, timeout=20)


def floor5(dt):
    return dt.replace(minute=dt.minute - dt.minute % 5, second=0, microsecond=0)


def track(log, c5, now):
    for s in log:
        if s.get("status") != "open":
            continue
        t0 = datetime.fromisoformat(s["time"])
        start = floor5(t0)
        checked = datetime.fromisoformat(s["checked"]) if s.get("checked") else None
        hits = s.get("hits", 0)
        cur = s.get("sl_now", s["sl"])
        buy = s["side"] == "BUY"
        label = f"{s['side']} XAUUSD | {s['profile']}"
        for x in c5:
            if x["t"] < start or (checked and x["t"] <= checked):
                continue
            sl_hit = x["l"] <= cur if buy else x["h"] >= cur
            if sl_hit:  # SL checked first = conservative
                s["status"] = "closed"
                if hits == 0:
                    s["result"] = "SL"
                    send(f"❌ {label}\nStopped out at SL {cur:.2f}\nEntry was {s['entry']:.2f}.")
                elif hits == 1:
                    s["result"] = "TP1 then BE"
                    send(f"🟡 {label}\nPrice returned to entry {cur:.2f}. "
                         f"Closed at breakeven after TP1. No loss.")
                else:
                    s["result"] = f"TP{hits} then SL"
                    send(f"🟡 {label}\nTrailing stop hit at {cur:.2f} after TP{hits}. "
                         f"Profit secured from TP{hits-1}.")
                break
            while hits < 3 and ((x["h"] >= s["tps"][hits]) if buy else (x["l"] <= s["tps"][hits])):
                hits += 1
                tp = s["tps"][hits - 1]
                p_ = f"{pips(tp, s['entry']):.0f} pips"
                if hits == 1:
                    cur = s["entry"]
                    send(f"✅ {label}\nTP1 hit at {tp:.2f} (+{p_})\n"
                         f"ACTION: move SL to entry {cur:.2f}. Trade is now risk-free.")
                elif hits == 2:
                    cur = s["tps"][0]
                    send(f"✅✅ {label}\nTP2 hit at {tp:.2f} (+{p_})\n"
                         f"ACTION: move SL to TP1 {cur:.2f}.")
                else:
                    send(f"🏆 {label}\nTP3 hit at {tp:.2f} (+{p_})\n"
                         f"ACTION: close the trade. Full target reached.")
            if hits == 3:
                s["status"] = "closed"
                s["result"] = "TP3"
                break
        s["hits"] = hits
        s["sl_now"] = cur
        s["checked"] = c5[-1]["t"].isoformat()
        if s["status"] == "open" and (now - t0).total_seconds() > 24 * 3600:
            s["status"] = "closed"
            s["result"] = "expired" if hits == 0 else f"TP{hits} then expired"
            send(f"⏱ {label}\nSignal expired after 24h. Consider closing manually "
                 f"if still open.")


def shift_check(log, name, bias_now, found):
    for s in log:
        if s.get("status") != "open" or s["profile"] != name or s.get("warned"):
            continue
        opposite = any(f["side"] != s["side"] for f in found)
        against = (s["side"] == "BUY" and bias_now == "DOWN") or \
                  (s["side"] == "SELL" and bias_now == "UP")
        flipped = against and bias_now != s["bias"]
        if opposite or flipped:
            why = "an opposite setup has formed" if opposite else f"trend bias flipped to {bias_now}"
            send(f"⚠️ MARKET SHIFT | {s['side']} XAUUSD {s['profile']}\n"
                 f"Entry {s['entry']:.2f}. Reason: {why}.\n"
                 f"What to do: if in profit, secure it (close part or all or tighten SL). "
                 f"If still near entry, consider closing early. The market may be reversing.")
            s["warned"] = True


def main():
    now = datetime.now(timezone.utc)
    log = json.load(open(LOG)) if os.path.exists(LOG) else []
    c5 = fetch("5min", 288)
    track(log, c5, now)
    for name, p in PROFILES.items():
        if name == "SWING" and now.minute >= 10:
            continue
        ec = c5[-120:] if p["entry"] == "5min" else fetch(p["entry"])
        tc = fetch(p["trend"])
        closed = ec[-1]["t"] + timedelta(minutes=MINS[p["entry"]])
        if (now - closed).total_seconds() / 60 > p["max_age"]:
            print(name, "market closed or data stale")
            continue
        found = analyse(name, p, ec, tc)
        print(name, "setups found:", len(found))
        shift_check(log, name, trend(tc)[0], found)
        for s in found:
            recent = [x for x in log if x["profile"] == name and x["side"] == s["side"]
                      and (now - datetime.fromisoformat(x["time"])).total_seconds() / 60 < p["cooldown"]]
            if recent:
                continue
            send(fmt(s))
            s["time"] = now.isoformat()
            s["status"] = "open"
            s["hits"] = 0
            s["sl_now"] = s["sl"]
            log.append(s)
    json.dump(log, open(LOG, "w"), indent=1)


if __name__ == "__main__":
    main()
