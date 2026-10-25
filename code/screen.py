"""Stage two of the measurement: what a screen does to the signal, to the
basket and to attrition.

Every feature used by a screen is observable at the decision date: the account
value and all-time volume of the leaderboard snapshot, the account's age, its
realised weekly volatility, its worst weekly loss and its turnover. For each
screen we report how many leaders pass, the rank correlation between past and
future performance inside the surviving set, the Sharpe of an equally weighted
basket of k of them, and the share of them that stop trading.

Usage: python or_journal/screen.py
"""
import os
import random
import statistics as st

from facts import MIN_WEEKS, WEEK_MS, km, load, sharpe, spearman, surv_at, wallet_rows  # noqa: E402

HALF = None


def features(r: dict, cut: int) -> dict:
    """What a decision maker could see about wallet r at week `cut`."""
    past = {w: v for w, v in r["rets"].items() if w <= cut}
    if len(past) < MIN_WEEKS:
        return {}
    vals = list(past.values())
    return {"n": len(vals), "acct": r["acct0"], "age": cut - r["birth"],
            "vol": st.pstdev(vals) if len(vals) > 1 else float("inf"),
            "worst": min(vals), "mean": st.mean(vals), "sharpe": sharpe(vals),
            "active": (r["last"] >= cut - 2)}


def basket_sharpe(pick: list, cut: int, rng: random.Random) -> float:
    weeks = sorted({w for r in pick for w in r["rets"] if w > cut})
    ser = []
    for w in weeks:
        xs = [r["rets"][w] for r in pick if w in r["rets"]]
        if len(xs) >= max(1, len(pick) // 2):
            ser.append(st.mean(xs))
    return sharpe(ser)


def main() -> int:
    snap, recs = load()
    rows = wallet_rows(snap, recs)
    snap_w = snap // WEEK_MS
    cut = snap_w - 26            # decide at six months before the snapshot, judge after
    cand = []
    for r in rows:
        f = features(r, cut)
        fut = [v for w, v in r["rets"].items() if w > cut]
        if f and len(fut) >= 8:
            cand.append((r, f, st.mean(fut), sharpe(fut)))
    print(f"snapshot week {snap_w}; decision week {cut}; {len(cand)} wallets with 8+ weeks on each side")

    screens = {
        "no screen": lambda f: True,
        "active at the decision date": lambda f: f["active"],
        "account >= $100k": lambda f: f["acct"] >= 1e5,
        "account >= $100k and active": lambda f: f["acct"] >= 1e5 and f["active"],
        "worst week >= -15%": lambda f: f["worst"] >= -0.15,
        "weekly vol <= 10%": lambda f: f["vol"] <= 0.10,
        "past Sharpe >= 1": lambda f: f["sharpe"] == f["sharpe"] and f["sharpe"] >= 1,
        "past Sharpe >= 2": lambda f: f["sharpe"] == f["sharpe"] and f["sharpe"] >= 2,
        "active, >= $100k, worst >= -15%": lambda f: f["active"] and f["acct"] >= 1e5 and f["worst"] >= -0.15,
        "the same plus past Sharpe >= 1": lambda f: f["active"] and f["acct"] >= 1e5 and f["worst"] >= -0.15 and f["sharpe"] == f["sharpe"] and f["sharpe"] >= 1,
    }
    rng = random.Random(11)
    print("\nscreen                            pass  IC(past,future)  median future  Sharpe k=1 / 5 / 20  stop trading")
    for name, test in screens.items():
        keep = [(r, f, m, s) for r, f, m, s in cand if test(f)]
        if len(keep) < 5:
            print(f"{name:<33} {len(keep):>5}   too few")
            continue
        ic = spearman([f["sharpe"] for _, f, _, _ in keep if f["sharpe"] == f["sharpe"]],
                      [m for _, f, m, _ in keep if f["sharpe"] == f["sharpe"]])
        med = st.median([m for _, _, m, _ in keep])
        sh = {}
        for k in (1, 5, 20):
            if len(keep) < k:
                sh[k] = float("nan")
                continue
            vals = []
            for _ in range(300):
                pick = [r for r, _, _, _ in rng.sample(keep, k)]
                v = basket_sharpe(pick, cut, rng)
                if v == v:
                    vals.append(v)
            sh[k] = st.median(vals) if vals else float("nan")
        dead = sum(1 for r, _, _, _ in keep if r["dead"]) / len(keep)
        print(f"{name:<33} {len(keep):>5}   {ic:+13.3f}   {100*med:+12.2f}%   "
              f"{sh[1]:5.2f} / {sh[5]:5.2f} / {sh[20]:5.2f}   {100*dead:9.1f}%")

    # attrition inside the screened set, measured forward from the decision date
    print("\nsurvival after the decision date, screened against unscreened")
    for name in ("no screen", "active, >= $100k, worst >= -15%"):
        test = screens[name]
        keep = [r for r, f, _, _ in cand if test(f)]
        if len(keep) < 20:
            continue
        c = km([{"age_weeks": min(r["last"], snap_w) - cut, "dead": r["dead"]} for r in keep if r["last"] >= cut])
        print(f"  {name:<33} alive after 1m {100*surv_at(c, 4.33):5.1f}%  3m {100*surv_at(c, 13):5.1f}%  6m {100*surv_at(c, 26):5.1f}%  (n={len(keep)})")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import sys
    sys.path.insert(0, os.path.join(os.getcwd(), "or_journal"))
    raise SystemExit(main())
