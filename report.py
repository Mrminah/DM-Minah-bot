import os, json, urllib.request, urllib.parse
from collections import defaultdict

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
LOG = "signals.json"


def send(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    urllib.request.urlopen(url, data=body, timeout=20)


def main():
    log = json.load(open(LOG)) if os.path.exists(LOG) else []
    stats = defaultdict(lambda: {"w": 0, "l": 0, "x": 0})
    open_n = 0
    for s in log:
        if s.get("status") == "open":
            open_n += 1
            continue
        r = s.get("result", "")
        key = f"{s['profile']} | {s['strategy']}"
        if r.startswith("TP"):
            stats[key]["w"] += 1
        elif r == "SL":
            stats[key]["l"] += 1
        else:
            stats[key]["x"] += 1

    lines = ["📊 DM Minah Performance Report"]
    tw = tl = 0
    for key, v in stats.items():
        done = v["w"] + v["l"]
        rate = f"{100 * v['w'] / done:.0f}%" if done else "n/a"
        lines.append(f"\n{key}\nWins: {v['w']} | Losses: {v['l']} | "
                     f"Expired: {v['x']} | Win rate: {rate}")
        tw += v["w"]
        tl += v["l"]
    if not stats:
        lines.append("\nNo closed signals yet.")
    else:
        total = f"{100 * tw / (tw + tl):.0f}%" if tw + tl else "n/a"
        lines.append(f"\nOverall: {tw}W / {tl}L ({total})")
    lines.append(f"Open signals: {open_n}")
    lines.append("\nWin = reached at least TP1. Small samples are not reliable.")
    send("\n".join(lines))


if __name__ == "__main__":
    main()
