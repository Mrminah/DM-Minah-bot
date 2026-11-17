import time
from collections import defaultdict
from datetime import timedelta
import bot

# entry candles, trend candles, max trade length in entry candles
CFG = {"SCALP": (5000, 1700, 288), "SWING": (2500, 700, 120)}
MODES = ["old", "new", "new_session"]
NAMES = {"old": "BEFORE (old rules)", "new": "AFTER (new filters, all day)",
         "new_session": "AFTER + London/NY only"}
SHORT = {"Price Action + EMA trend pullback": "Pullback",
         "Liquidity sweep above swing high": "Sweep high (SELL)",
         "Liquidity sweep below swing low": "Sweep low (BUY)"}
COST = 0.30  # spread/slippage per trade in price points


def trade_r(s, cands):
    """Result in R. Trade split in 3 parts: exits at TP1, TP2, TP3.
    SL moves to entry after TP1 and to TP1 after TP2."""
    buy = s["side"] == "BUY"
    sg = 1 if buy else -1
    risk = abs(s["entry"] - s["sl"])
    rr = s["rr"]
    hits, cur = 0, s["sl"]
    for x in cands:
        if (x["l"] <= cur) if buy else (x["h"] >= cur):  # SL first = conservative
            exit_r = (cur - s["entry"]) / risk * sg
            return (sum(rr[:hits]) + (3 - hits) * exit_r) / 3, hits, "sl"
        while hits < 3 and ((x["h"] >= s["tps"][hits]) if buy else (x["l"] <= s["tps"][hits])):
            hits += 1
        if hits == 3:
            return sum(rr) / 3, 3, "tp3"
        if hits == 1:
            cur = s["entry"]
        elif hits == 2:
            cur = s["tps"][0]
    last = cands[-1]["c"] if cands else s["entry"]
    mark = (last - s["entry"]) / risk * sg
    return (sum(rr[:hits]) + (3 - hits) * mark) / 3, hits, "open"


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
    res = {m: defaultdict(lambda: {"n": 0, "tp1": 0, "tp3": 0, "r": 0.0}) for m in MODES}
    last = {m: {} for m in MODES}
    k = 0
    for i in range(119, len(ec_all) - 1):
        close = ec_all[i]["t"] + em
        while k < len(tc_all) and tc_all[k]["t"] + tm <= close:
            k += 1
        tc = tc_all[max(0, k - 120):k]
        if len(tc) < 60:
            continue
        window = ec_all[i - 119:i + 1]
        for m in MODES:
            for s in bot.analyse(name, p, window, tc, m):
                if i - last[m].get(s["side"], -10**9) < cd:
                    continue
                last[m][s["side"]] = i
                r, hits, end = trade_r(s, ec_all[i + 1:i + 1 + exp])
                r -= COST / abs(s["entry"] - s["sl"])
                st = res[m][SHORT[s["strategy"]]]
                st["n"] += 1
                st["r"] += r
                st["tp1"] += hits >= 1
                st["tp3"] += hits == 3
    span = f"{ec_all[0]['t']:%d %b} to {ec_all[-1]['t']:%d %b %Y}"
    lines = [f"🔬 BACKTEST {name} ({p['entry']})\n{span}"]
    for m in MODES:
        lines.append(f"\n{NAMES[m]}")
        tn, tr = 0, 0.0
        for strat, v in sorted(res[m].items()):
            lines.append(f"{strat}: {v['n']} signals | TP1+ {100 * v['tp1'] / v['n']:.0f}% | "
                         f"TP3 {100 * v['tp3'] / v['n']:.0f}% | avg {v['r'] / v['n']:+.2f}R")
            tn += v["n"]
            tr += v["r"]
        if tn:
            lines.append(f"ALL: {tn} signals | avg {tr / tn:+.2f}R | total {tr:+.1f}R")
        else:
            lines.append("No signals")
    return "\n".join(lines)


if __name__ == "__main__":
    for n in bot.PROFILES:
        text = run(n)
        print(text)
        bot.send(text)
    note = (f"Plan modelled: 3 equal parts exit at TP1/TP2/TP3, SL to entry after TP1, "
            f"to TP1 after TP2. Spread cost {COST} per trade included. "
            f"Past results do not guarantee future results.")
    print(note)
    bot.send(note)
