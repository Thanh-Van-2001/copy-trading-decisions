"""The market benchmark, on the same weekly grid as the panel.

A basket of leaders holds crypto risk, so a Sharpe ratio measured over a rising
window says little until it is set against the market the leaders trade. This
pulls daily closes from the same exchange the panel comes from, buckets them
into the panel's weeks (epoch weeks, as load_panel does) and keeps the last
close in each week, so the benchmark return for week w is close(w)/close(w-1)-1.

Written atomically: a .part file, then os.replace.

Usage: python or_journal/collect_bench.py [--out data/hl_bench/bench.json]
"""
import argparse
import json
import os
import time
import urllib.request

INFO = "https://api.hyperliquid.xyz/info"
WEEK_MS = 7 * 24 * 3600 * 1000
COINS = ("BTC", "ETH")
DAY_MS = 24 * 3600 * 1000


def post(payload: dict, tries: int = 4) -> object:
    body = json.dumps(payload).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(INFO, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as fh:
                return json.load(fh)
        except Exception as exc:                                   # noqa: BLE001
            if attempt == tries - 1:
                raise
            print(f"  retry {attempt + 1}: {exc}")
            time.sleep(2 + 3 * attempt)
    return None


def candles(coin: str, start_ms: int, end_ms: int) -> list:
    """Daily candles, in chunks the endpoint will serve."""
    out, t = [], start_ms
    while t < end_ms:
        stop = min(t + 400 * DAY_MS, end_ms)
        got = post({"type": "candleSnapshot",
                    "req": {"coin": coin, "interval": "1d", "startTime": t, "endTime": stop}}) or []
        out.extend(got)
        if not got:
            break
        t = int(got[-1]["T"]) + 1
        time.sleep(0.4)
    seen = {}
    for c in out:
        seen[int(c["t"])] = float(c["c"])
    return sorted(seen.items())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/hl_bench/bench.json")
    ap.add_argument("--years", type=float, default=4.0)
    args = ap.parse_args(argv)
    now = int(time.time() * 1000)
    start = now - int(args.years * 365.25 * DAY_MS)
    rec = {"source": "Hyperliquid candleSnapshot, daily closes", "fetched_ms": now,
           "week_ms": WEEK_MS, "coins": list(COINS), "weekly": {}, "close": {}}
    for coin in COINS:
        rows = candles(coin, start, now)
        last = {}
        for t, c in rows:
            last[t // WEEK_MS] = c                 # the last close inside each epoch week
        weeks = sorted(last)
        rets = {}
        for a, b in zip(weeks, weeks[1:]):
            if b - a == 1:
                rets[str(b)] = round(last[b] / last[a] - 1.0, 6)
        rec["weekly"][coin] = rets
        rec["close"][coin] = {str(w): last[w] for w in weeks}
        print(f"{coin}: {len(rows)} daily closes, {len(rets)} weekly returns, weeks {weeks[0]}-{weeks[-1]}")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = args.out + ".part"
    json.dump(rec, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, args.out)
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
