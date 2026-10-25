"""Take a second snapshot of the sampling frame, so two of its limits can be measured.

The paper has one snapshot of the venue's public address list, taken on
2026-10-05, and says twice that this costs it something it cannot recover:

  - the survival curve is an upper bound, because an account that blew up and
    was delisted inside an evaluation window is absent from the frame rather
    than present and stopped, and one snapshot cannot tell those apart;
  - the turnover charged at a decision date is a lifetime average, because the
    venue publishes lifetime volume as of the snapshot rather than a series,
    and "two snapshots of lifetime volume would bracket a window and identify
    the volume traded inside it; one does not."

A second snapshot answers the first directly and tests the second. Fourteen days
do not bracket a twenty-six week evaluation window, so this does not replace the
proxy; it measures what the proxy gets wrong over the only window we can observe
exactly, which turns an assertion in the limitations into a number.

The first snapshot is irreplaceable. This writes to data/hl_frames/ and never
opens data/hl_gold/leaderboard.parquet for writing.

Usage: python or_journal/collect_frame.py [--date 2026-10-19]
"""
import argparse
import datetime as dt
import json
import os
import urllib.request

URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
OUT = "data/hl_frames"
H = {"User-Agent": "Mozilla/5.0 (research frame snapshot; one request)"}
# the first snapshot's schema, so the two are directly comparable
COLS = ["addr", "acct", "pnl_all", "roi_all", "vlm_all", "pnl_month"]


def fetch() -> list:
    req = urllib.request.Request(URL, headers=H)
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()
    d = json.loads(raw)
    return d.get("leaderboardRows") or d


def window(row: dict, name: str) -> dict:
    for w in row.get("windowPerformances") or []:
        if w and w[0] == name:
            return w[1] or {}
    return {}


def to_rows(rows: list) -> list:
    out = []
    for r in rows:
        a = window(r, "allTime")
        m = window(r, "month")
        try:
            out.append({"addr": str(r["ethAddress"]).lower(),
                        "acct": float(r.get("accountValue") or 0.0),
                        "pnl_all": float(a.get("pnl") or 0.0),
                        "roi_all": float(a.get("roi") or 0.0),
                        "vlm_all": float(a.get("vlm") or 0.0),
                        "pnl_month": float(m.get("pnl") or 0.0)})
        except (TypeError, ValueError, KeyError):
            continue        # a malformed row is counted, not guessed at
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--force", action="store_true",
                    help="replace an existing snapshot for this date, which discards a record")
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"leaderboard_{args.date}.parquet")
    # A snapshot, once taken, is a historical record: re-fetching the same date
    # would replace it with different live numbers, and the manuscript is pinned
    # to one of these files. So an existing snapshot is never overwritten, and a
    # weekly job that fires twice in a day is a no-op rather than a loss.
    if os.path.exists(path) and not args.force:
        print(f"{path} already exists; refusing to overwrite a snapshot "
              f"(pass --force only if you mean to discard it)")
        return 0
    raw_rows = fetch()
    rows = to_rows(raw_rows)
    dropped = len(raw_rows) - len(rows)
    import pandas as pd
    d = pd.DataFrame(rows, columns=COLS)
    tmp = path + ".part"
    d.to_parquet(tmp, index=False)
    os.replace(tmp, path)                     # the only copy is never the target
    meta = {"date": args.date, "url": URL, "rows_served": len(raw_rows),
            "rows_parsed": len(rows), "rows_dropped": dropped,
            "unique_addresses": int(d["addr"].nunique())}
    mp = os.path.join(OUT, f"meta_{args.date}.json") + ".part"
    json.dump(meta, open(mp, "w", encoding="utf-8"), indent=1)
    os.replace(mp, mp[:-5])
    print(json.dumps(meta, indent=1))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
