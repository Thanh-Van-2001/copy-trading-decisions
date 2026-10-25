"""Is how much each leader gets a decision, or is it not one?

The paper fixes the weights at 1/k and justifies it by citing the finding that
the equally weighted rule beats estimated-optimal weights out of sample when
the moments are noisy. That is a citation and not a measurement, and the
citation is about asset classes with decades of history rather than leaders
with a few months of it. Nothing in it says the same holds on a panel where
the average pairwise correlation is high and every history is short. So we run
the comparison here.

Four weightings of the same basket, at the same decision dates, on the same
screened and ordered set the rest of the paper recommends:

  equal      1/k, the paper's rule
  invvol     proportional to the reciprocal of each leader's past volatility
  minvar     the long-only minimum-variance weights of the past covariance
  tangency   the long-only maximum-Sharpe weights of the past moments

Every weight is formed from weeks that close strictly before the decision date
and graded on the weeks after it. No leader can be sold short on a copy-trading
platform, so the weights are non-negative and sum to one; the long-only
programme is solved by the usual active set, dropping the names that want a
negative weight and re-solving on the rest.

The covariance is shrunk towards its own diagonal by DELTA, because twenty
leaders and twenty-six weeks do not identify two hundred and ten covariances.
At DELTA = 1 the minimum-variance weights become inverse-variance weights, so
the sweep over DELTA spans the whole distance between using the correlations
and ignoring them.

Usage: python or_journal/weights.py [--out out/or/weights.json]
"""
import argparse
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis import (COPY_BP, DEAD_WEEKS, MIN_WEEKS, cagr, features,  # noqa: E402
                      last_live_at, load_panel, nw_tstat, sharpe, turnover)
from policy import FAMILIES, HOLD, SPACING, net  # noqa: E402

K = 20              # the basket size the paper reports its rule at
EST = HOLD          # weeks of history each weighting is formed from
MIN_EST = 10        # fewer members with usable history and the date is skipped
MIN_OWN = 8         # weeks a leader needs before his own moments are used
MIN_PAIR = 8        # weeks a pair needs before its correlation is estimated
DELTAS = (0.0, 0.5, 1.0)
DELTA = 0.5         # the central case, a judgement and reported as one
RIDGE = 1e-10       # keeps the solve from failing on a singular shrunk matrix


def value_at(m: dict, w: int):
    """The three-state convention of the paper's return equation, as a number or
    None. A measured week is the leader's return. A week in which his account
    holds nothing is a zero: the sleeve earns nothing and costs nothing. A week
    in which he still holds capital but the week cannot be measured has no
    value, and carries no weight anywhere."""
    if w in m["r"]["rets"]:
        return m["r"]["rets"][w]
    if w not in m["r"]["live"]:
        return 0.0
    return None


def past_matrix(members: list, cut: int) -> list:
    """The ragged block of history: one row per week, None where a week cannot
    be measured. Asking for complete rows returns nothing on this panel, since
    between eight and nineteen of twenty members are measurable in a given week
    and never all of them."""
    return [[value_at(m, w) for m in members]
            for w in range(cut - EST + 1, cut + 1)]


def shrink(cov: list, delta: float) -> list:
    n = len(cov)
    return [[cov[i][j] * (1.0 - delta) + (cov[i][j] + RIDGE if i == j else 0.0) * delta
             for j in range(n)] for i in range(n)]


def moments(block: list) -> tuple:
    """Means, standard deviations and correlations from a ragged block.

    Each variance uses the leader's own measurable weeks and each correlation
    the overlap of its pair. A pair with fewer than MIN_PAIR weeks in common
    takes the median of the correlations that are estimable, which is the
    assumption a reader should see rather than infer, so the count of filled
    pairs is returned with the matrix. The result is projected onto the nearest
    positive semidefinite matrix, because one assembled from different supports
    need not be one."""
    import numpy as np
    x = np.array([[np.nan if v is None else v for v in row] for row in block],
                 dtype=float)
    k = x.shape[1]
    own = (~np.isnan(x)).sum(axis=0)
    keep = own >= MIN_OWN
    mu = np.zeros(k)
    sd = np.full(k, np.nan)
    for i in range(k):
        if keep[i]:
            col = x[~np.isnan(x[:, i]), i]
            mu[i] = col.mean()
            sd[i] = col.std(ddof=1)
    med_sd = float(np.nanmedian(sd)) if keep.any() else 1e-6
    sd = np.where(np.isnan(sd) | (sd < 1e-12), med_sd, sd)
    mu = np.where(keep, mu, 0.0)

    rho = np.eye(k)
    pair_n, got = [], []
    for i in range(k):
        for j in range(i + 1, k):
            both = ~np.isnan(x[:, i]) & ~np.isnan(x[:, j])
            m = int(both.sum())
            pair_n.append(m)
            if m >= MIN_PAIR:
                a, b = x[both, i], x[both, j]
                sa, sb = a.std(ddof=1), b.std(ddof=1)
                if sa > 1e-12 and sb > 1e-12:
                    r = float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))
                    rho[i, j] = rho[j, i] = max(-0.99, min(0.99, r))
                    got.append(r)
                    continue
            rho[i, j] = rho[j, i] = np.nan
    fill = float(np.nanmedian(got)) if got else 0.0
    filled = int(np.isnan(rho).sum() // 2)
    rho = np.where(np.isnan(rho), fill, rho)

    # the nearest positive semidefinite correlation matrix, by clipping
    ev, V = np.linalg.eigh((rho + rho.T) / 2.0)
    rho = V @ np.diag(np.clip(ev, 1e-8, None)) @ V.T
    d = np.sqrt(np.diag(rho))
    rho = rho / np.outer(d, d)

    cov = rho * np.outer(sd, sd)
    diag = {"own_median": int(np.median(own)),
            "pair_median": int(np.median(pair_n)) if pair_n else 0,
            "pairs_filled": filled, "pairs": len(pair_n),
            "fill_rho": round(fill, 3),
            "members_with_history": int(keep.sum())}
    return mu.tolist(), cov.tolist(), diag


def solve(a: list, b: list):
    """One linear system, or None when the matrix will not support it."""
    import numpy as np
    try:
        return list(np.linalg.solve(np.array(a, dtype=float),
                                    np.array(b, dtype=float)))
    except np.linalg.LinAlgError:
        return None


def long_only(cov: list, mu: list = None) -> list:
    """Minimum-variance weights, or maximum-Sharpe weights when mu is given,
    under w >= 0 and sum(w) = 1. The active set drops whichever names want a
    negative weight and re-solves on the rest, which terminates because the
    live set strictly shrinks."""
    n = len(cov)
    live = list(range(n))
    for _ in range(n):
        sub = [[cov[i][j] for j in live] for i in live]
        rhs = [1.0] * len(live) if mu is None else [mu[i] for i in live]
        z = solve(sub, rhs)
        if z is None:
            break
        tot = sum(z)
        if abs(tot) < 1e-18:
            break
        w = [x / tot for x in z]
        bad = [live[i] for i, x in enumerate(w) if x < 0.0]
        if not bad:
            out = [0.0] * n
            for i, j in enumerate(live):
                out[j] = w[i]
            return out
        live = [i for i in live if i not in bad]
        if len(live) < 2:
            break
    out = [0.0] * n
    for i in (live or range(n)):
        out[i] = 1.0 / len(live or range(n))
    return out


def schemes(members: list, cut: int, delta: float) -> dict:
    block = past_matrix(members, cut)
    mu, cov, diag = moments(block)
    if diag["members_with_history"] < MIN_EST:
        return {}
    sd = [max(cov[i][i], 1e-12) ** 0.5 for i in range(len(mu))]
    shr = shrink(cov, delta)
    inv = [1.0 / s for s in sd]
    tot = sum(inv)
    return {"est_weeks": diag["pair_median"], "diag": diag,
            "equal": [1.0 / len(mu)] * len(mu),
            "invvol": [x / tot for x in inv],
            "minvar": long_only(shr),
            "tangency": long_only(shr, mu)}


def run_weighted(members: list, weights: list, cut: int, hold: int) -> tuple:
    """The copier's weekly series and the turnover he mirrors, under weights
    that need not be equal. A week renormalises over the weight actually
    carried, so an unmeasurable sleeve does not dilute the rest."""
    series, turns = [], []
    for w in range(cut + 1, cut + hold + 1):
        acc = tacc = carried = 0.0
        for m, wt in zip(members, weights):
            v = value_at(m, w)
            if v is None:
                continue
            carried += wt
            acc += wt * v
            if w in m["r"]["rets"]:
                tacc += wt * m["turn"]
        series.append(acc / carried if carried > 1e-12 else 0.0)
        turns.append(tacc / carried if carried > 1e-12 else 0.0)
    return series, turns


def one_grid(rows: list, snap_w: int, spacing: int, n_dates: int) -> dict:
    dates = sorted(snap_w - HOLD - i * spacing for i in range(n_dates))
    earliest = min(r["birth"] for r in rows) + MIN_WEEKS + 4
    dates = [d for d in dates if d > earliest]
    out = {"spacing": spacing, "hold": HOLD, "k": K, "delta": DELTA,
           "dates": [], "series": {}, "summary": {}, "skipped": 0}
    for cut in dates:
        cand = []
        for r in rows:
            f = features(r, cut)
            if f and last_live_at(r, cut) >= cut - DEAD_WEEKS:
                cand.append({"r": r, "f": f, "turn": turnover(r, f, cut, snap_w)})
        if len(cand) < 40:
            continue
        rec = {"cut": cut, "fam": {}}
        for fam, test in FAMILIES.items():
            if fam == "open":
                continue
            pool = [c for c in cand if test(c["f"])]
            if len(pool) < K:
                continue
            members = sorted(pool, key=lambda c: -c["f"]["sharpe"])[:K]
            ws = schemes(members, cut, DELTA)
            if not ws:
                out["skipped"] += 1
                continue
            got = {"est_weeks": ws["est_weeks"], "diag": ws["diag"]}
            for name in ("equal", "invvol", "minvar", "tangency"):
                s, t = run_weighted(members, ws[name], cut, HOLD)
                nt = net(s, t, COPY_BP)
                got[name] = {"net": sharpe(nt), "gross": sharpe(s),
                             "cagr": cagr(nt),
                             "maxw": round(max(ws[name]), 3),
                             "nonzero": sum(1 for x in ws[name] if x > 1e-6)}
                out["series"].setdefault(f"{fam}|{name}", []).extend(nt)
            rec["fam"][fam] = got
        if rec["fam"]:
            out["dates"].append(rec)
    # the difference between each weighting and equal weights, stitched over the
    # dates of this grid and carried with a Newey-West standard error
    # the level of each weighting, so the growth criterion can be compared too:
    # a ratio and a compound growth rate do not have to move together, and here
    # they do not
    for fam in ("risk", "big"):
        for name in ("equal", "invvol", "minvar", "tangency"):
            got = [r["fam"][fam][name] for r in out["dates"] if fam in r["fam"]]
            if got:
                out["summary"][f"{fam}|{name}|level"] = {
                    "net": round(st.mean(g["net"] for g in got), 3),
                    "cagr": round(st.mean(g["cagr"] for g in got), 3),
                    "maxw": round(st.mean(g["maxw"] for g in got), 3),
                    "nonzero": round(st.mean(g["nonzero"] for g in got), 1)}
    for fam in ("risk", "big"):
        base = out["series"].get(f"{fam}|equal")
        if not base:
            continue
        for name in ("invvol", "minvar", "tangency"):
            alt = out["series"].get(f"{fam}|{name}")
            if not alt or len(alt) != len(base):
                continue
            d = [a - b for a, b in zip(alt, base)]
            per = [r["fam"][fam][name]["net"] - r["fam"][fam]["equal"]["net"]
                   for r in out["dates"] if fam in r["fam"]]
            out["summary"][f"{fam}|{name}"] = {
                "weeks": len(d),
                "weekly_bp": round(1e4 * st.mean(d), 2),
                "t": round(nw_tstat(d), 2),
                "sharpe_mean": round(st.mean(per), 3) if per else None,
                "wins": sum(1 for x in per if x > 0),
                "dates": len(per)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/or/weights.json")
    args = ap.parse_args(argv)
    snap_w, n_files, rows, drops, grid = load_panel()
    res = {"panel": {"accounts": len(rows), "snapshot_week": snap_w},
           "overlapping": one_grid(rows, snap_w, SPACING, 5),
           "disjoint": one_grid(rows, snap_w, HOLD, 3),
           "delta_sweep": {}}
    # how much of the answer is the shrinkage rather than the weighting
    for delta in DELTAS:
        globals()["DELTA"] = delta
        g = one_grid(rows, snap_w, HOLD, 3)
        res["delta_sweep"][f"{delta}"] = {
            k: v["weekly_bp"] for k, v in g["summary"].items()
            if "weekly_bp" in v}
    globals()["DELTA"] = DELTA
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(res, open(args.out, "w", encoding="utf-8"), indent=1)
    for grid in ("overlapping", "disjoint"):
        print(grid, json.dumps(res[grid]["summary"], indent=1))
    print("delta sweep", json.dumps(res["delta_sweep"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
