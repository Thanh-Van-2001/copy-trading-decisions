"""Turn the collected portfolio answers into the panel the paper needs.

For each sampled address: the birth (first point above a dust threshold), the
last movement, whether the account is still alive at the snapshot, and a weekly
equity path from which returns are taken. Writes data/hl_panel/panel.json.

Usage: python or_journal/panel.py
"""
import glob
import json
import os
import statistics as st

SRC = "data/hl_panel"
DUST = 100.0            # an account below this is treated as empty
SNAP_MS = None          # filled from the data: the latest timestamp seen
WEEK_MS = 7 * 24 * 3600 * 1000


def series(rec: dict) -> list:
    """The all-time account-value path as (ms, value), ascending."""
    for period, blk in rec.get("portfolio") or []:
        if period == "allTime":
            out = [(int(t), float(v)) for t, v in (blk.get("accountValueHistory") or [])]
            return sorted(out)
    return []


def weekly(path: list) -> list:
    """Last value of each week bucket."""
    if not path:
        return []
    buckets = {}
    for t, v in path:
        buckets[t // WEEK_MS] = (t, v)
    return [buckets[k] for k in sorted(buckets)]


def main() -> int:
    files = [f for f in glob.glob(os.path.join(SRC, "*.json")) if not f.endswith("draw.json")]
    snap = 0
    recs = []
    for f in files:
        try:
            rec = json.load(open(f, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        path = series(rec)
        if not path:
            continue
        snap = max(snap, path[-1][0])
        recs.append((rec, path))
    rows = []
    for rec, path in recs:
        wk = weekly(path)
        live = [(t, v) for t, v in wk if v > DUST]
        if not live:
            continue
        birth, last_live = live[0][0], live[-1][0]
        # death: the account went to dust and stayed there, or has not moved for four weeks
        tail_dust = all(v <= DUST for _, v in wk if _ > last_live) if last_live < wk[-1][0] else False
        stale_weeks = (snap - last_live) / WEEK_MS
        rets = []
        for (t0, v0), (t1, v1) in zip(live, live[1:]):
            if v0 > DUST and (t1 - t0) <= 3 * WEEK_MS:
                rets.append((t1, v1 / v0 - 1.0))
        rows.append({"addr": rec["addr"], "frame": rec.get("frame", {}),
                     "birth_ms": birth, "last_ms": last_live, "snap_ms": snap,
                     "age_weeks": (last_live - birth) / WEEK_MS,
                     "weeks_observed": len(live), "stale_weeks": stale_weeks,
                     "dead": bool(tail_dust or stale_weeks > 4),
                     "acct_last": live[-1][1], "acct_peak": max(v for _, v in live),
                     "returns": rets})
    json.dump({"snap_ms": snap, "dust": DUST, "wallets": rows},
              open(os.path.join(SRC, "panel.json"), "w", encoding="utf-8"))
    n = len(rows)
    dead = sum(r["dead"] for r in rows)
    ages = sorted(r["age_weeks"] for r in rows)
    obs = sorted(r["weeks_observed"] for r in rows)
    print(f"{len(files)} files, {n} wallets with a usable path, {dead} dead at the snapshot ({100*dead/max(n,1):.1f}%)")
    print(f"age in weeks: median {st.median(ages):.1f}, quartiles {ages[n//4]:.1f} / {ages[3*n//4]:.1f}, max {ages[-1]:.1f}")
    print(f"weekly points per wallet: median {st.median(obs):.0f}, min {obs[0]}, max {obs[-1]}")
    print(f"wallets with at least 8 weekly returns: {sum(1 for r in rows if len(r['returns']) >= 8)}")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
