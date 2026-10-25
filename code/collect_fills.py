"""The copying cost, measured on the leaders' own fills rather than assumed.

An earlier version of this work carried the cost as a constant with a comment
claiming it had been measured. The comment was inherited from a different study
on a different set of wallets, and nothing in this repository supported it. This
script measures it on the accounts this paper actually uses.

What is measurable from fills is the fee the venue charged per unit of notional
traded. A copier mirroring a leader trades the same notional on the same fee
schedule, so that fee is the part of the copying cost the data can pin down.
What is not measurable from fills alone is the spread a copier pays by arriving
after the leader, since that needs the book at the moment of the fill; the paper
reports the whole decision over a grid of cost levels for that reason.

Written atomically: a .part file, then os.replace.

Usage: python or_journal/collect_fills.py [--n 120] [--weeks 26]
"""
import argparse
import glob
import json
import os
import random
import statistics as st
import time
import urllib.request

API = "https://api.hyperliquid.xyz/info"
SRC = "data/hl_panel"
OUT = "data/hl_fills/fills.json"
SEED = 20261016
PAGE_SLEEP = 1.5
MAX_PAGES = 6


def post(payload: dict, tries: int = 4):
    body = json.dumps(payload).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as fh:
                return json.load(fh)
        except Exception as exc:                                   # noqa: BLE001
            if attempt == tries - 1:
                print("   give up:", exc)
                return None
            time.sleep(4 + 6 * attempt)
    return None


def fills_for(addr: str, start_ms: int, end_ms: int) -> list:
    out, t0, pages = [], start_ms, 0
    while pages < MAX_PAGES:
        batch = post({"type": "userFillsByTime", "user": addr, "startTime": t0,
                      "endTime": end_ms, "aggregateByTime": True})
        pages += 1
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 2000:
            break
        t0 = int(batch[-1]["time"]) + 1
        time.sleep(PAGE_SLEEP)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--weeks", type=int, default=26)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)

    files = [f for f in glob.glob(os.path.join(SRC, "*.json")) if not f.endswith("draw.json")]
    addrs, snap = [], 0
    for f in files:
        try:
            rec = json.load(open(f, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for period, blk in rec.get("portfolio") or []:
            if period == "allTime":
                av = blk.get("accountValueHistory") or []
                if av:
                    last = int(av[-1][0])
                    snap = max(snap, last)
                    # only accounts that still held capital near the snapshot can
                    # have fills in the window the paper charges
                    if float(av[-1][1]) > 1000.0:
                        addrs.append((rec["addr"], last))
    rng = random.Random(SEED)
    rng.shuffle(addrs)
    pick = [a for a, _ in addrs[:args.n]]
    end_ms = snap
    start_ms = end_ms - args.weeks * 7 * 24 * 3600 * 1000
    print(f"{len(addrs)} funded accounts in the panel; sampling {len(pick)} over {args.weeks} weeks")

    per, rows = [], 0
    for i, a in enumerate(pick, 1):
        fl = fills_for(a, start_ms, end_ms)
        time.sleep(PAGE_SLEEP)
        if not fl:
            continue
        notional = fee = 0.0
        maker = 0
        for x in fl:
            try:
                px, sz, fe = float(x["px"]), float(x["sz"]), float(x.get("fee") or 0.0)
            except (TypeError, ValueError):
                continue
            notional += px * sz
            fee += fe
            maker += fe < 0
        if notional <= 0:
            continue
        rows += len(fl)
        per.append({"addr": a, "fills": len(fl), "notional": notional, "fee": fee,
                    "bp": 1e4 * fee / notional, "maker_share": maker / max(1, len(fl))})
        if i % 20 == 0:
            print(f"  {i}/{len(pick)}: {len(per)} with fills, {rows:,} fills so far")

    if not per:
        print("no fills returned; nothing written")
        return 1
    bps = sorted(p["bp"] for p in per)
    pooled = 1e4 * sum(p["fee"] for p in per) / sum(p["notional"] for p in per)
    rec = {"source": "Hyperliquid userFillsByTime, aggregated by time",
           "fetched_ms": int(time.time() * 1000),
           "window_weeks": args.weeks, "start_ms": start_ms, "end_ms": end_ms,
           "accounts_sampled": len(pick), "accounts_with_fills": len(per),
           "fills": rows, "notional_usd": round(sum(p["notional"] for p in per), 2),
           "fee_usd": round(sum(p["fee"] for p in per), 2),
           "bp_pooled": round(pooled, 3),
           "bp_median": round(st.median(bps), 3),
           "bp_q1": round(bps[len(bps) // 4], 3),
           "bp_q3": round(bps[3 * len(bps) // 4], 3),
           "maker_share_median": round(st.median([p["maker_share"] for p in per]), 3),
           "per_account": per}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = args.out + ".part"
    json.dump(rec, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, args.out)
    print(f"wrote {args.out}")
    print(f"  {rows:,} fills from {len(per)} accounts, ${rec['notional_usd']:,.0f} notional")
    print(f"  fee per side: pooled {rec['bp_pooled']} bp, median account {rec['bp_median']} bp "
          f"(quartiles {rec['bp_q1']} to {rec['bp_q3']})")
    print(f"  median maker share {rec['maker_share_median']}")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
