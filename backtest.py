import time
from collections import defaultdict
from datetime import timedelta
import bot

# entry candles, trend candles, max trade length in entry candles
CFG = {"SCALP": (5000, 1700, 288), "SWING": (2500, 700, 120)}


def run(name):
    p = bot.PROFILES[name]
    n_e, n_t, exp = CFG[name]
    ec_all = bot.fetch(p["entry"], n_e)
    time.sleep(10)
    tc_all = bot.fetch(p["trend"], n_t)
    time.sleep(10)
    em = timedelta(minutes=bot.MINS[p["entry"]])
    tm = timedelta(minutes=bot.MINS[p["trend"]])
    cd = p["cooldown"] / bot.MINS[p["entry"]]
    stats = defaultdict(lambda: {"n": 0, "w": 0, "l": 0, "x": 0, "tp3": 0, "r": 0.0})
    last, k = {}, 0
    for i in range(119, len(ec_all) - 1):
        close = ec_all[i]["t"] + em
        while k < len(tc_all) and tc_all[k]["t"] + tm <= close:
            k += 1
        tc = tc_all[max(0, k - 120):k]
        if len(tc) < 60:
            continue
        for s in bot.analyse(name, p, ec_all[i - 119:i + 1], tc):
            if i - last.get(s["side"], -10**9) < cd:
                continue
            last[s["side"]] = i
            buy = s["side"] == "BUY"
            hits, hit_sl = 0, False
            for x in ec_all[i + 1:i + 1 + exp]:
                if (x["l"] <= s["sl"]) if buy else (x["h"] >= s["sl"]):
                    hit_sl = True
                    break
                while hits < 3 and ((x["h"] >= s["tps"][hits]) if buy else (x["l"] <= s["tps"][hits])):
                    hits += 1
                if hits == 3:
                    break
            st = stats[s["strategy"]]
            st["n"] += 1
            if hits >= 1:
                st["w"] += 1
                st["r"] += s["rr"][0]
                st["tp3"] += hits == 3
            elif hit_sl:
                st["l"] += 1
                st["r"] -= 1
            else:
                st["x"] += 1
    span = f"{ec_all[0]['t']:%d %b} to {ec_all[-1]['t']:%d %b %Y}"
    lines = [f"🔬 BACKTEST {name} ({p['entry']})\n{span}"]
    for strat, v in stats.items():
        done = v["w"] + v["l"]
        rate = f"{100 * v['w'] / done:.0f}%" if done else "n/a"
        lines.append(f"\n{strat}\nSignals: {v['n']} | Wins: {v['w']} | Losses: {v['l']} | "
                     f"Expired: {v['x']}\nWin rate: {rate} | Reached TP3: {v['tp3']}\n"
                     f"Avg result: {v['r'] / v['n']:+.2f}R per trade")
    if not stats:
        lines.append("\nNo signals in this period.")
    return "\n".join(lines)


if __name__ == "__main__":
    out = []
    for n in bot.PROFILES:
        out.append(run(n))
    text = "\n\n".join(out) + "\n\nWin = reached TP1. Avg result assumes exit at TP1 or SL. Past results do not guarantee future results."
    print(text)
    bot.send(text)
