"""Step 1 of the OR paper: is leader attrition a first-order constraint?

Reads the 2026-07-29 snapshot of Hyperliquid leader wallets (one row per wallet,
with first and last activity and a staleness flag) and computes the survival
curve of a leader, the monthly hazard, and what attrition does to the
diversification benefit of a basket of k leaders.

Usage: python or_journal/survival_step1.py
"""
import csv
import datetime as dt
import math
import os

SRC = "hl_all230_stats_2026_07_29.csv"
SNAP = dt.date(2026, 7, 29)
RHO = 0.05          # median pairwise correlation of leader weekly returns (measured 2026-09)
STALE_ALIVE = 2.0   # a wallet with at most this many stale weeks is treated as still active


def load(path: str) -> list:
    out = []
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                since = dt.date.fromisoformat(r["since"])
                last = dt.date.fromisoformat(r["last"])
            except (ValueError, KeyError):
                continue
            stale = float(r.get("stale_w") or 0)
            out.append({"addr": r["addr"], "since": since, "last": last,
                        "days": (last - since).days, "stale_w": stale,
                        "alive": stale <= STALE_ALIVE,
                        "sharpe": float(r["sharpe"] or 0), "weeks": float(r["weeks"] or 0),
                        "av_now": float(r.get("av_now") or 0)})
    return out


def kaplan_meier(rows: list) -> list:
    """Survival of "the leader is still trading", event = last activity before the snapshot."""
    obs = sorted(((r["days"], not r["alive"]) for r in rows), key=lambda x: x[0])
    n = len(obs)
    surv, at_risk, curve = 1.0, n, []
    i = 0
    while i < n:
        t = obs[i][0]
        deaths = 0
        tied = 0
        while i < n and obs[i][0] == t:
            deaths += obs[i][1]
            tied += 1
            i += 1
        if at_risk > 0 and deaths:
            surv *= 1 - deaths / at_risk
        curve.append((t, at_risk, deaths, surv))
        at_risk -= tied
    return curve


def surv_at(curve: list, day: float) -> float:
    s = 1.0
    for t, _, _, v in curve:
        if t <= day:
            s = v
        else:
            break
    return s


def sharpe_of(k: float, rho: float = RHO, single: float = 2.53) -> float:
    """Sharpe of an equally weighted basket of k leaders with pairwise correlation rho,
    from the measured single-leader Sharpe."""
    if k <= 0:
        return 0.0
    return single * math.sqrt(k / (1 + (k - 1) * rho))


def main() -> int:
    rows = load(SRC)
    dead = [r for r in rows if not r["alive"]]
    print(f"{len(rows)} leaders in the snapshot, {len(dead)} already inactive, {len(rows) - len(dead)} censored (still trading)")
    med_life = sorted(r["days"] for r in rows)[len(rows) // 2]
    print(f"median observed age (days): {med_life}; median age of the inactive ones: {sorted(r['days'] for r in dead)[len(dead) // 2] if dead else '--'}")

    curve = kaplan_meier(rows)
    print("\nsurvival of a leader, from first activity:")
    for months in (1, 2, 3, 6, 9, 12, 18):
        print(f"  {months:>2} months: {100 * surv_at(curve, 30.4 * months):5.1f}% still trading")
    s6 = surv_at(curve, 182)
    s12 = surv_at(curve, 365)
    print(f"\nhazard: {100 * (1 - s6 ** (1 / 6)):.1f}% of leaders stop per month over the first six months, "
          f"{100 * (1 - s12 ** (1 / 12)):.1f}% per month over a year")

    print("\nwhat attrition does to a basket picked today and never replaced")
    print("  k picked | alive after 1m / 3m / 6m | Sharpe now -> after 6m")
    for k in (3, 5, 10, 20, 40):
        a1, a3, a6 = (k * surv_at(curve, 30.4 * m) / surv_at(curve, 0.0) for m in (1, 3, 6))
        print(f"  {k:>8} | {a1:12.1f} / {a3:4.1f} / {a6:4.1f} | {sharpe_of(k):9.2f} -> {sharpe_of(a6):5.2f}")

    # how many replacements a year does holding k alive cost
    print("\nreplacement load to hold k leaders alive, at the six-month hazard:")
    h = 1 - s6 ** (1 / 6)
    for k in (10, 20, 40):
        print(f"  k={k:>2}: {12 * h * k:5.1f} replacements a year ({h * k:4.2f} a month)")

    # is the attrition selective? compare the Sharpe of the ones that stopped with the ones that stayed
    def mean(xs):
        xs = list(xs)
        return sum(xs) / len(xs) if xs else float("nan")
    print(f"\nmean Sharpe of leaders who stopped: {mean(r['sharpe'] for r in dead):.2f}; "
          f"of those still trading: {mean(r['sharpe'] for r in rows if r['alive']):.2f}")
    print(f"mean account now, stopped: ${mean(r['av_now'] for r in dead):,.0f}; "
          f"still trading: ${mean(r['av_now'] for r in rows if r['alive']):,.0f}")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
