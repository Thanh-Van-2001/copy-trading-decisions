"""Collect the leader panel for the OR paper, from a stated sampling frame.

Frame: the 47,195 addresses of the Hyperliquid public leaderboard snapshot of
2026-10-05 (data/hl_gold/leaderboard.parquet), which includes losing and dormant
accounts, so it is not a winners-only list. We draw a stratified random sample
by account-value decile with a fixed seed, and for each address store the raw
`portfolio` answer of the public API: the all-time equity path, from which the
account's birth, its death (equity to zero, or no movement since) and its
returns are read.

Writes one JSON file per address under data/hl_panel/, atomically (.part then
replace), and is resumable: an address already on disk is skipped.

Usage: python or_journal/collect_panel.py [--n 2500] [--seed 20261016] [--delay 0.5]
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

API = "https://api.hyperliquid.xyz/info"
FRAME = "data/hl_gold/leaderboard.parquet"
OUT = "data/hl_panel"
H = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (research panel; one request per half second)"}


def post(body: dict, timeout: int = 30) -> object:
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def frame_rows() -> list:
    import pandas as pd
    d = pd.read_parquet(FRAME)
    d = d.sort_values("acct", ascending=False).reset_index(drop=True)
    return d.to_dict("records")


def sample(rows: list, n: int, seed: int) -> list:
    """Stratified by account-value decile of the frame, equal draw per stratum."""
    rng = random.Random(seed)
    per = max(n // 10, 1)
    out = []
    size = len(rows)
    for d in range(10):
        lo, hi = d * size // 10, (d + 1) * size // 10
        block = rows[lo:hi]
        out.extend(rng.sample(block, min(per, len(block))))
    rng.shuffle(out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2500)
    ap.add_argument("--seed", type=int, default=20261016)
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    rows = frame_rows()
    drawn = sample(rows, args.n, args.seed)
    meta = {"frame": FRAME, "frame_size": len(rows), "frame_date": "2026-10-05",
            "drawn": len(drawn), "seed": args.seed, "stratification": "account-value decile of the frame, equal draw per decile",
            "endpoint": "POST https://api.hyperliquid.xyz/info {type: portfolio, user: addr}"}
    with open(os.path.join(OUT, "draw.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(meta, addresses=[r["addr"] for r in drawn]), fh, indent=1)
    ok = fail = skip = 0
    for i, r in enumerate(drawn, 1):
        addr = r["addr"]
        path = os.path.join(OUT, f"{addr}.json")
        if os.path.exists(path):
            skip += 1
            continue
        try:
            body = post({"type": "portfolio", "user": addr})
            rec = {"addr": addr, "frame": {k: r[k] for k in ("acct", "pnl_all", "roi_all", "vlm_all", "pnl_month")},
                   "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "portfolio": body}
            tmp = path + ".part"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(rec, fh)
            os.replace(tmp, path)
            ok += 1
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            fail += 1
            print(f"  {addr} failed: {str(exc)[:80]}", flush=True)
        if i % 100 == 0:
            print(f"{i}/{len(drawn)}: ok {ok}, fail {fail}, already had {skip}", flush=True)
        time.sleep(args.delay)
    print(f"done: ok {ok}, fail {fail}, already had {skip} -> {OUT}")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())
