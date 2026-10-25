"""The two results the measurement is there to serve, and their calibration.

Nothing here is deep. Both propositions are two lines of algebra. They earn
their place because they turn the grid search of Section 8 into a one
dimensional problem and the replacement heuristic of Section 9 into a threshold
rule whose threshold is computed from measured quantities rather than chosen.

Proposition 1 (the basket is always as large as it may be).
  An equally weighted basket of k leaders drawn from S has mean edge mu and
  variance v/k + (1 - 1/k) cbar, where v is the average variance of a member and
  cbar the average covariance of two. The cost charged in the paper's return
  equation is the average turnover of the members, whose expectation does not
  depend on k. So the objective
        U(k) = (mu - cost) / sqrt(v/k + (1 - 1/k) cbar)
  has a denominator strictly decreasing in k whenever v > cbar, and U is then
  strictly increasing in k. Hence k* = min(|S|, C/m): the cardinality constraint
  binds at every screen, the choice of k is not a choice, and the decision
  collapses to the single dimension theta.

Proposition 2 (the maintenance rule is a no-trade band whose width is set by
the cost and the remaining horizon).
  A sleeve held for T more weeks whose leader has posterior weekly edge m and
  stopping hazard lambda is worth m * A(T), with
        A(T) = (1 - lambda) (1 - (1 - lambda)^T) / lambda,
  the expected number of weeks he survives to trade. Swapping him for candidate
  j costs c and buys A(T) more weeks at edge m_j. The swap pays iff
        (m_j - m_i) A(T) > c,   that is   m_j - m_i > c / A(T) =: b(T).
  Three things follow and the third is not obvious. The rule is a band rather
  than a ranking: re-rank every week, but move only when the gap exceeds b(T).
  A stopped sleeve is the case m_i = 0, so refilling it is the same rule, and it
  stops paying when A(T) m_j <= c near the end of the holding period. And b(T)
  widens as the hazard rises, because A(T) shortens: a venue whose leaders die
  faster makes each swap less attractive, since what a swap buys is a difference
  in edge over a remaining life the hazard is cutting short. That is a statement
  about the width of the band and not about how often it is crossed; a higher
  hazard also sends more sleeves to m_i = 0, so the number of swaps a copier
  ends up making can rise while each one is harder to justify.

Proposition 2 as stated prices the mean and ignores the variance, which is right
under the growth criterion only to first order and is not right at all under a
ratio. Taking the second-order term of the growth criterion, a swap changes the
basket's variance by Dv/k^2 + 2(k-1)Dc/k^2, where Dv is the difference in the
two leaders' own variances and Dc the difference in their average covariance
with the rest of the basket, and the condition becomes
        m_j - m_i > c / A(T) + Dv / (2k) + (k-1) Dc / k.
The cost term is divided by A(T) and the risk terms are not. A longer horizon
therefore shrinks the part of the band that the switching cost explains and
leaves the part that risk explains where it is, so for any holding period beyond
a few weeks the band is a risk object rather than a cost object. That is the
sense in which a cost-based band of under a basis point was never going to be
the operative constraint.

The posterior is a shrinkage of the leader's own past mean toward the pool's.
We do not infer the shrinkage weight from a variance decomposition, because the
cross-section of weekly means here is heavy tailed and the decomposition is then
driven by a handful of accounts. We estimate it as the slope of the realised
future mean on the past mean across leaders, which is the weight a least squares
predictor would use and is the same primitive Section 6 reports as a rank
correlation. For the policy of Section 9 the slope is estimated on windows that
close before the decision date, so the rule uses no information from the period
it is judged on.

Usage: python or_journal/theory.py [--out out/or/theory.json]
"""
import argparse
import json
import math
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis import (COPY_BP, CUTS, MIN_WEEKS, SCREENS, km_curve, km_at,  # noqa: E402
                      load_panel, pool_at)

SWITCH_BP = 2 * COPY_BP          # a replacement unwinds one book and opens another
HORIZONS = (26, 13, 8, 4, 2, 1)


def weekly_hazard(rows: list) -> float:
    """The constant weekly stopping rate implied by the survival curve at six
    months, which is the horizon a copier holds over."""
    curve = km_curve([(r["last"] - r["birth"], r["dead"]) for r in rows])
    s26 = km_at(curve, 26)
    return 1.0 - s26 ** (1.0 / 26.0)


def expected_trading_weeks(lam: float, t: int) -> float:
    """A(T): how many of the next T weeks the leader is expected to trade."""
    if lam <= 0:
        return float(t)
    q = 1.0 - lam
    return q * (1.0 - q ** t) / lam


def expected_both_trading(lam: float, t: int) -> float:
    """A2(T): how many of the next T weeks two leaders are BOTH expected to be
    trading, which is what a covariance between them needs. Stopping is taken as
    independent across leaders, which is the same assumption the hazard is
    estimated under."""
    if lam <= 0:
        return float(t)
    q = (1.0 - lam) ** 2
    return q * (1.0 - q ** t) / (1.0 - q)


def winsorise(xs: list, q: float = 0.02) -> list:
    """Heavy tails make a least squares slope a statement about three accounts,
    so both variables are trimmed at the same quantile before it is taken."""
    v = sorted(xs)
    lo, hi = v[int(q * len(v))], v[min(len(v) - 1, int((1 - q) * len(v)))]
    return [min(max(x, lo), hi) for x in xs]


def shrink_slope(past: list, future: list, trim: float = 0.02) -> dict:
    """The weight a least squares predictor of next period's mean puts on this
    period's. This is the shrinkage the posterior should apply."""
    if len(past) < 50:
        return {}
    x, y = winsorise(past, trim), winsorise(future, trim)
    mx, my = st.mean(x), st.mean(y)
    sxx = sum((u - mx) ** 2 for u in x)
    if sxx <= 0:
        return {}
    beta = sum((u - mx) * (v - my) for u, v in zip(x, y)) / sxx
    syy = sum((v - my) ** 2 for v in y)
    r = (sum((u - mx) * (v - my) for u, v in zip(x, y)) / math.sqrt(sxx * syy)) if syy > 0 else float("nan")
    return {"n": len(x), "beta": round(beta, 4), "correlation": round(r, 3),
            "prior_weekly_pct": round(100 * my, 3),
            "past_mean_weekly_pct": round(100 * mx, 3),
            "trim": trim}


def posterior(mean_hat: float, beta: float, past_mean: float, prior: float) -> float:
    """The shrunk edge: the pool's mean plus the predictable share of this
    leader's deviation from it."""
    return prior + beta * (mean_hat - past_mean)


def swap_band(rows: list, cuts: list, k: int, lam: float, horizon: int,
              every: int = 2) -> dict:
    """The risk terms of the band, measured over the swaps the rule makes.

    The quantity the band needs is the difference between the leader a swap
    takes in and the one it puts out, in their own variance and in their
    covariance with the members that stay. Those two sit next to each other in
    the ranking, so the difference is small and can go either way; measuring
    instead between the pool's top and bottom deciles, as an earlier version
    did, prices a swap nobody makes and is positive by construction.

    We walk the holding window at each decision date, rank on what is known by
    then, and record the boundary pair."""
    out = []
    for cut in cuts:
        pool = pool_at(rows, cut, cut + horizon)
        pool = [c for c in pool if SCREENS["size"](c["f"])]
        if len(pool) < k + 4:
            continue
        a, b = [], []
        for c in pool:
            past = [v for w, v in c["r"]["rets"].items() if w <= cut - horizon]
            mid = [v for w, v in c["r"]["rets"].items() if cut - horizon < w <= cut]
            if len(past) >= MIN_WEEKS and len(mid) >= MIN_WEEKS:
                a.append(st.mean(past))
                b.append(st.mean(mid))
        sh = shrink_slope(a, b) if len(a) >= 50 else {}
        beta = sh.get("beta", 0.0)
        pm = sh.get("past_mean_weekly_pct", 0.0) / 100.0
        pr = sh.get("prior_weekly_pct", 0.0) / 100.0
        for w in range(cut, cut + horizon + 1, every):
            scored = []
            for c in pool:
                hist = {ww: v for ww, v in c["r"]["rets"].items() if ww <= w}
                if len(hist) < MIN_WEEKS:
                    continue
                scored.append((pr + beta * (st.mean(list(hist.values())) - pm), hist))
            if len(scored) < k + 2:
                continue
            scored.sort(key=lambda t: -t[0])
            held = [h for _, h in scored[:k]]
            outgoing = held[-1]
            incoming = scored[k][1]
            stay = held[:-1]

            def cov_against(x, group):
                acc, cnt = 0.0, 0
                for g in group:
                    ks = sorted(set(x) & set(g))
                    if len(ks) < MIN_WEEKS:
                        continue
                    xs = [x[i] for i in ks]
                    ys = [g[i] for i in ks]
                    mx, my = st.mean(xs), st.mean(ys)
                    acc += sum((u - mx) * (v - my) for u, v in zip(xs, ys)) / len(ks)
                    cnt += 1
                return (acc / cnt, cnt) if cnt else (float("nan"), 0)

            ci, ni = cov_against(incoming, stay)
            co, no = cov_against(outgoing, stay)
            if ci != ci or co != co:
                continue
            dv = st.pvariance(list(incoming.values())) - st.pvariance(list(outgoing.values()))
            dc = ci - co
            ratio = (expected_both_trading(lam, cut + horizon - w + 1)
                     / max(expected_trading_weeks(lam, cut + horizon - w + 1), 1e-9))
            out.append({"cut": cut, "week": w, "dv": dv, "dc": dc,
                        "bp": 1e4 * (dv / (2 * k) + (k - 1) / k * ratio * dc),
                        "pairs": min(ni, no)})
    if len(out) < 10:
        return {}
    bps = sorted(o["bp"] for o in out)
    dvs = sorted(o["dv"] for o in out)
    dcs = sorted(o["dc"] for o in out)

    def q(v, f):
        return round(v[int(f * (len(v) - 1))], 4)

    return {"swaps_examined": len(out), "k": k, "dates": len(set(o["cut"] for o in out)),
            "bp_median": round(st.median(bps), 1), "bp_mean": round(st.mean(bps), 1),
            "bp_p10": round(q(bps, 0.1), 1), "bp_p90": round(q(bps, 0.9), 1),
            "share_negative": round(sum(1 for v in bps if v < 0) / len(bps), 3),
            "delta_var_median": q(dvs, 0.5), "delta_cov_median": q(dcs, 0.5),
            "median_pairs_with_overlap": int(st.median([o["pairs"] for o in out])),
            "possible_pairs": k - 1}


def pool_variance_gradient(pool: list, cut: int, k: int, cal: dict, lam: float = 0.0,
                           horizon: int = 26) -> dict:
    """The risk terms of the band, measured across the boundary a swap crosses.

    A swap takes the weakest sleeve the basket holds and replaces it with the
    best candidate outside. Those two groups sit next to each other in the
    ranking, so the difference between them is small; measuring instead between
    the pool's top and bottom deciles, as an earlier version did, prices a swap
    nobody makes and overstates the band by an order of magnitude. The groups
    here are the bottom five of the basket against the best five outside it.

    The covariance term carries A2(T)/A(T) because a covariance needs both legs
    still trading, while the own-variance term does not."""
    beta, pm, pr = cal["beta"], cal["past_mean"], cal["prior"]
    rows = []
    for c in pool:
        past = [v for w, v in c["r"]["rets"].items() if w <= cut]
        if len(past) < MIN_WEEKS:
            continue
        rows.append({"c": c, "post": pr + beta * (st.mean(past) - pm),
                     "var": st.pvariance(past),
                     "fut": [v for w, v in c["r"]["rets"].items() if w > cut],
                     "ret": {w: v for w, v in c["r"]["rets"].items() if w <= cut}})
    if len(rows) < 50:
        return {}
    rows.sort(key=lambda r: -r["post"])
    if len(rows) < k + 6:
        return {}
    incumbent = rows[max(0, k - 5):k]          # the weakest sleeves the basket holds
    challenger = rows[k:k + 5]                 # the best candidates outside it
    top = challenger
    bot = incumbent
    dv = st.mean([r["var"] for r in challenger]) - st.mean([r["var"] for r in incumbent])
    dm = st.mean([r["post"] for r in challenger]) - st.mean([r["post"] for r in incumbent])

    # average covariance with the rest, on a sample of pairs
    import random as _r
    rng = _r.Random(11)

    def cov_with_pool(r):
        acc, cnt = 0.0, 0
        for _ in range(40):
            o = rows[rng.randrange(len(rows))]
            ks = sorted(set(r["ret"]) & set(o["ret"]))
            if len(ks) < MIN_WEEKS:
                continue
            x = [r["ret"][w] for w in ks]
            y = [o["ret"][w] for w in ks]
            mx, my = st.mean(x), st.mean(y)
            acc += sum((a - mx) * (b - my) for a, b in zip(x, y)) / len(ks)
            cnt += 1
        return acc / cnt if cnt else 0.0

    ct = st.mean([cov_with_pool(r) for r in top[:30]])
    cb = st.mean([cov_with_pool(r) for r in bot[:30]])
    dc = ct - cb
    ratio = (expected_both_trading(lam, horizon) / expected_trading_weeks(lam, horizon)
             if lam > 0 else 1.0)
    var_term = dv / (2 * k)
    cov_term = (k - 1) / k * ratio * dc
    # the same two groups, measured on what they went on to do rather than on
    # what they had done, which is the quantity the decision actually faces
    fv_c = st.mean([st.pvariance(r["fut"]) for r in challenger if len(r["fut"]) > 2] or [0.0])
    fv_i = st.mean([st.pvariance(r["fut"]) for r in incumbent if len(r["fut"]) > 2] or [0.0])
    return {"k": k, "delta_var": round(dv, 6), "delta_cov": round(dc, 6),
            "delta_edge_bp": round(1e4 * dm, 2),
            "a_two_over_a": round(ratio, 4),
            "risk_term_weekly_bp": round(1e4 * (var_term + cov_term), 2),
            "var_term_bp": round(1e4 * var_term, 2),
            "cov_term_bp": round(1e4 * cov_term, 2),
            "delta_var_forward": round(fv_c - fv_i, 6),
            "risk_term_forward_bp": round(1e4 * ((fv_c - fv_i) / (2 * k) + cov_term), 2),
            "pairs_with_enough_overlap": sum(
                1 for i, a in enumerate(incumbent + challenger)
                for b in (incumbent + challenger)[i + 1:]
                if len(set(a["ret"]) & set(b["ret"])) >= MIN_WEEKS),
            "pairs_total": len(incumbent + challenger) * (len(incumbent + challenger) - 1) // 2}


def gap_walk(pool: list, cut: int, hold: int, k: int, cal: dict) -> dict:
    """The state the band actually compares, week by week.

    The rule holds a set of k sleeves and each week asks whether the best
    candidate outside it beats the weakest one inside. That margin, and not the
    spread across the held set, is what the boundary is a boundary in. An
    earlier version measured the distance from the best leader on the venue to
    the twentieth, which is a different quantity by two orders of magnitude and
    is never what a swap decides.

    Returns the margin before each decision, its weekly changes, and the margin
    immediately after a swap, which is what the repeated problem restarts from.
    """
    beta, pm, pr = cal["beta"], cal["past_mean"], cal["prior"]

    def posts(w):
        out = []
        for c in pool:
            r = c["r"]
            if r["last"] <= w - 4:
                out.append((0.0, r["addr"]))
                continue
            tot = cnt = 0
            for ww, v in r["rets"].items():
                if ww <= w:
                    tot += v
                    cnt += 1
            out.append((pr + beta * (tot / cnt - pm) if cnt >= MIN_WEEKS else pr, r["addr"]))
        return dict((a, p) for p, a in out)

    p0 = posts(cut)
    if len(p0) <= k:
        return {}
    held = [a for a, _ in sorted(p0.items(), key=lambda t: -t[1])[:k]]
    margins, restarts = [], []
    for w in range(cut + 1, cut + hold + 1):
        pw = posts(w - 1)                      # what is known before the week
        inside = min(pw.get(a, 0.0) for a in held)
        out_best, out_who = max(((v, a) for a, v in pw.items() if a not in held),
                                default=(None, None))
        if out_best is None:
            break
        margins.append(out_best - inside)
        # the rule, run at a band of zero, so the restart margin is observed
        if out_best > inside:
            worst = min(held, key=lambda a: pw.get(a, 0.0))
            held[held.index(worst)] = out_who
            pw2_in = min(pw.get(a, 0.0) for a in held)
            pw2_out = max((v for a, v in pw.items() if a not in held), default=pw2_in)
            restarts.append(pw2_out - pw2_in)
    if len(margins) < 5:
        return {}
    innov = [b - a for a, b in zip(margins, margins[1:])]
    ms = sorted(margins)
    return {"weeks": len(margins), "margins": margins, "innovations": innov,
            "restarts": restarts,
            "margin_median_bp": round(1e4 * ms[len(ms) // 2], 2),
            "margin_positive_share": round(sum(1 for m in margins if m > 0) / len(margins), 3),
            "restart_median_bp": round(1e4 * sorted(restarts)[len(restarts) // 2], 2)
            if restarts else None,
            "innovation_mean_abs_bp": round(1e4 * st.mean([abs(x) for x in innov]), 2)
            if innov else None,
            "innovation_signed_bp": round(1e4 * st.mean(innov), 2) if innov else None}


def gap_innovations(pool: list, cut: int, hold: int, k: int, cal: dict) -> list:
    """The weekly changes in the margin the band compares."""
    d = gap_walk(pool, cut, hold, k, cal)
    return d.get("innovations", []) if d else []


def gap_innovation(pool: list, cut: int, hold: int, k: int, cal: dict, raw: bool = False):
    """How much the gap the band is compared against moves from week to week.

    If the weekly innovation is larger than the band, the band has no inaction
    region: the state crosses it almost every week by construction."""
    beta, pm, pr = cal["beta"], cal["past_mean"], cal["prior"]

    def posts(w):
        out = []
        for c in pool:
            r = c["r"]
            if r["last"] <= w - 4:
                out.append(0.0)
                continue
            tot = cnt = 0
            for ww, v in r["rets"].items():
                if ww <= w:
                    tot += v
                    cnt += 1
            out.append(pr + beta * (tot / cnt - pm) if cnt >= MIN_WEEKS else pr)
        return sorted(out, reverse=True)

    gaps, signed, levels = [], [], []
    prev = None
    for w in range(cut, cut + hold + 1):
        ps = posts(w)
        if len(ps) <= k:
            break
        gap = ps[0] - ps[k - 1]          # best outside against the weakest held
        levels.append(gap)
        if prev is not None:
            gaps.append(abs(gap - prev))
            signed.append(gap - prev)
        prev = gap
    if not gaps:
        return {}
    if raw:
        return signed
    gaps.sort()
    return {"weeks": len(gaps), "median_bp": round(1e4 * st.median(gaps), 2),
            "mean_bp": round(1e4 * st.mean(gaps), 2),
            "p90_bp": round(1e4 * gaps[int(0.9 * len(gaps))], 2),
            "signed_mean_bp": round(1e4 * st.mean(signed), 2),
            "signed_t": round(st.mean(signed) / (st.pstdev(signed) / len(signed) ** 0.5), 2)
            if len(signed) > 2 and st.pstdev(signed) > 0 else None,
            "level_median_bp": round(1e4 * st.median(levels), 2)}


def waiting_bracket(lam: float, c: float, e_abs_eta: float, horizons=HORIZONS) -> dict:
    """Where the optimal boundary has to lie, from measured quantities only.

    Acting now captures the gap one week earlier and costs c. Waiting keeps the
    option of never paying c at all, and that option is worth more the more the
    gap moves. Both ends of the bracket below are derived in Section 4:

      lower  c / A(T)              acting beats never acting again
      upper  E|eta| A(T-1) / (2 (1-lambda)^T)   acting beats waiting one week

    The lower end is the break-even boundary the paper used before. The gap
    between the two is the option value, and it is the reason a cost-based band
    is the wrong order of magnitude on any horizon a copier would hold for."""
    out = {}
    for t in horizons:
        A = expected_trading_weeks(lam, t)
        Am = expected_trading_weeks(lam, t - 1) if t > 1 else 0.0
        step = (1.0 - lam) ** t
        lo = c / A if A > 0 else float("inf")
        hi = (0.5 * e_abs_eta * Am / step) if step > 0 else float("inf")
        out[str(t)] = {"lower_bp": round(1e4 * lo, 2),
                       "upper_bp": round(1e4 * hi, 1) if hi < 1e6 else None,
                       "ratio": round(hi / lo, 0) if lo > 0 and hi < 1e6 else None,
                       "one_week_of_gap": round(step, 3)}
    return out


def solve_boundary(lam: float, c: float, innovations: list, t_max: int = 26,
                   grid_hi: float = 0.08, steps: int = 4000) -> dict:
    """The boundary itself, by backward induction.

    Proposition 3 says the advantage of acting is increasing in the gap, so the
    boundary is the single crossing of
        g A(T) - c   against   E W(g + eta, T-1),
    and the recursion W(g,T) = max of those two, started at W(.,0) = 0, can be
    solved on a grid. The innovations are drawn from the panel rather than from
    an assumed law, so the answer carries the shape of the measured distribution
    and not only its scale.

    The problem solved is the one the propositions describe: a single swap
    opportunity, with the gap exogenous until it is taken. A copier who swaps
    repeatedly faces a gap that resets each time, which this does not model."""
    if not innovations:
        return {}
    lo, hi = -grid_hi, grid_hi
    gs = [lo + (hi - lo) * i / (steps - 1) for i in range(steps)]
    idx_of = lambda g: min(steps - 1, max(0, int(round((g - lo) / (hi - lo) * (steps - 1)))))  # noqa: E731
    W = [0.0] * steps
    out = {}
    for T in range(1, t_max + 1):
        A = expected_trading_weeks(lam, T)
        prev = W
        cont = []
        for i, g in enumerate(gs):
            acc = 0.0
            for e in innovations:
                acc += prev[idx_of(g + e)]
            cont.append(acc / len(innovations))
        W = [max(g * A - c, cont[i]) for i, g in enumerate(gs)]
        b = None
        for i, g in enumerate(gs):
            if g >= 0 and g * A - c >= cont[i] - 1e-15:
                b = g
                break
        out[str(T)] = {"boundary_bp": round(1e4 * b, 2) if b is not None else None,
                       "break_even_bp": round(1e4 * c / A, 2)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/or/theory.json")
    args = ap.parse_args(argv)
    snap_w, _, rows, _, _ = load_panel()
    lam = weekly_hazard(rows)
    c = SWITCH_BP / 1e4
    out = {"lambda_week": round(lam, 5), "lambda_month_pct": round(100 * (1 - (1 - lam) ** 4.345), 2),
           "switch_cost_bp": SWITCH_BP, "horizons": {}, "pools": {}, "proposition_one": {}}

    # ---- Proposition 2, calibrated at the paper's decision date on earlier windows
    cut = snap_w - 26
    pool = pool_at(rows, cut, snap_w)
    for p in pool:
        p["cut"] = cut
    # the slope is estimated on two windows that both close before the decision
    # date, so nothing in the calibration comes from the period it is judged on
    prev, prevp = [], []
    for p in pool:
        a = [v for w, v in p["r"]["rets"].items() if w <= cut - 26]
        b = [v for w, v in p["r"]["rets"].items() if cut - 26 < w <= cut]
        if len(a) >= MIN_WEEKS and len(b) >= MIN_WEEKS:
            prevp.append(st.mean(a))
            prev.append(st.mean(b))
    sh = shrink_slope(prevp, prev)
    out["shrinkage"] = sh
    # the same slope measured on the window the paper judges, for comparison only
    now_past = [st.mean([v for w, v in p["r"]["rets"].items() if w <= cut]) for p in pool
                if p["future_mean"] is not None]
    now_fut = [p["future_mean"] for p in pool if p["future_mean"] is not None]
    out["shrinkage_in_window"] = shrink_slope(now_past, now_fut)
    beta = sh.get("beta", 0.0)
    past_mean = sh.get("past_mean_weekly_pct", 0.0) / 100.0
    prior = sh.get("prior_weekly_pct", 0.0) / 100.0

    for name in ("none", "size", "drawdown", "size_drawdown_active"):
        keep = [p for p in pool if SCREENS[name](p["f"])]
        if len(keep) < 20:
            continue
        posts = []
        for p in keep:
            past = [v for w, v in p["r"]["rets"].items() if w <= cut]
            posts.append(posterior(st.mean(past), beta, past_mean, prior))
        posts.sort(reverse=True)
        out["pools"][name] = {
            "n": len(keep),
            "prior_weekly_pct": round(100 * prior, 3),
            "posterior_mean_pct": round(100 * st.mean(posts), 3),
            "posterior_best_pct": round(100 * posts[0], 3),
            "posterior_top_decile_pct": round(100 * st.mean(posts[:max(1, len(posts) // 10)]), 3),
            "posterior_spread_pct": round(100 * st.pstdev(posts), 3)}

    # the band, and the horizon at which refilling a stopped sleeve stops paying
    ref = out["pools"].get("size", out["pools"]["none"])
    muR = ref["posterior_top_decile_pct"] / 100.0
    spread = ref["posterior_spread_pct"] / 100.0
    for t in HORIZONS:
        A = expected_trading_weeks(lam, t)
        band = c / A if A > 0 else float("inf")
        out["horizons"][str(t)] = {
            "expected_trading_weeks": round(A, 2),
            "band_weekly_bp": round(1e4 * band, 2),
            "band_in_pool_spreads": round(band / spread, 4) if spread > 0 else None,
            "refill_a_stopped_sleeve": bool(A * muR > c)}
    t_min = None
    for t in range(1, 27):
        if expected_trading_weeks(lam, t) * muR > c:
            t_min = t
            break
    out["refill_min_weeks"] = t_min
    out["muR_weekly_pct"] = round(100 * muR, 3)
    out["posterior_spread_pct"] = round(100 * spread, 3)
    out["cost_in_weeks_of_edge"] = round(c / muR, 2) if muR > 0 else None

    # the comparative static: the same band under other hazards
    out["comparative"] = {}
    for mult, lab in ((0.25, "a quarter of this hazard"), (0.5, "half of it"), (1.0, "as measured"),
                      (2.0, "twice"), (8.0, "eight times")):
        lm = 1.0 - (1.0 - lam) ** mult
        lm = min(max(lm, 1e-6), 0.5)
        A = expected_trading_weeks(lm, 26)
        A2 = expected_both_trading(lm, 26)
        rb = out.get("risk_band") or {}
        cov_at = ((rb.get("cov_term_bp", 0.0) / rb["a_two_over_a"]) * (A2 / A)
                  if rb.get("a_two_over_a") else 0.0)
        out["comparative"][lab] = {"lambda_week": round(lm, 5),
                                   "lambda_month_pct": round(100 * (1 - (1 - lm) ** 4.345), 2),
                                   "expected_trading_weeks": round(A, 2),
                                   "a_two_over_a": round(A2 / A, 4),
                                   "cost_term_bp": round(1e4 * c / A, 2),
                                   "band_weekly_bp": round(1e4 * c / A + rb.get("var_term_bp", 0.0)
                                                           + cov_at, 2)}

    # ---- the risk terms the mean-only band leaves out, and whether the band
    # ---- has any inaction region at all
    cal = {"beta": sh.get("beta", 0.0), "past_mean": past_mean, "prior": prior}
    big = [c for c in pool if SCREENS["size"](c["f"])]
    # Measured across the boundary a swap crosses, not between the pool's
    # deciles. An earlier version measured the deciles, which is the pool's
    # variance gradient and is positive by construction; it is kept under its
    # own name so the appendix can say why it was the wrong quantity.
    # the quantity the band needs, measured over the swaps the rule makes
    cuts = [snap_w - 26 - i * 13 for i in range(5)]
    cuts = [c for c in cuts if c - 26 > min(r["birth"] for r in rows) + MIN_WEEKS]
    out["swap_band"] = swap_band(rows, sorted(cuts), 20, lam, 26)
    # and the quantity an earlier version measured instead, kept under its own
    # name so the appendix can say why it was the wrong one
    out["pool_variance_gradient"] = pool_variance_gradient(big, cut, 20, cal, lam, 26)
    walk = gap_walk(big, cut, 26, 20, cal)
    out["gap_walk"] = {kk: walk[kk] for kk in
                       ("weeks", "margin_median_bp", "margin_positive_share",
                        "restart_median_bp", "innovation_mean_abs_bp", "innovation_signed_bp")
                       if kk in walk}
    inn = walk.get("innovations") or []
    out["gap_innovation"] = {
        "weeks": len(inn),
        "median_bp": round(1e4 * sorted([abs(x) for x in inn])[len(inn) // 2], 2) if inn else None,
        "mean_bp": walk.get("innovation_mean_abs_bp"),
        "p90_bp": round(1e4 * sorted([abs(x) for x in inn])[int(0.9 * len(inn))], 2) if inn else None,
        "signed_mean_bp": walk.get("innovation_signed_bp"),
        "signed_t": round(st.mean(inn) / (st.pstdev(inn) / len(inn) ** 0.5), 2)
        if len(inn) > 2 and st.pstdev(inn) > 0 else None,
        "level_median_bp": walk.get("margin_median_bp"),
    } if inn else {}

    # ---- Proposition 1, checked against the measured curves
    facts_path = "out/or/facts.json"
    if os.path.exists(facts_path):
        f = json.load(open(facts_path, encoding="utf-8"))
        d = f["dependence"]
        out["proposition_one"] = {
            "var_bar": d["var_bar"], "cov_bar": d["cov_bar"],
            "holds": bool(d["var_bar"] > d["cov_bar"]),
            "ratio": d["cov_ratio"],
            "screens": {}}
        for name, rec in f["baskets"].items():
            ks = sorted(int(k) for k in rec["k"])
            if len(ks) < 3:
                continue
            g = [rec["k"][str(k)]["median"] for k in ks]
            nn = [rec["k"][str(k)]["median_net"] for k in ks]
            out["proposition_one"]["screens"][name] = {
                "ks": ks,
                "gross_rises": bool(g[-1] > g[0]),
                "gross_monotone": all(a <= b + 1e-9 for a, b in zip(g, g[1:])),
                "net_rises": bool(nn[-1] > nn[0]),
                "net_monotone": all(a <= b + 1e-9 for a, b in zip(nn, nn[1:])),
                "gross_first_last": [g[0], g[-1]], "net_first_last": [nn[0], nn[-1]]}
        sc = out["proposition_one"]["screens"].values()
        out["proposition_one"]["gross_rises_in"] = f"{sum(v['gross_rises'] for v in sc)} of {len(sc)}"
        out["proposition_one"]["net_rises_in"] = f"{sum(v['net_rises'] for v in sc)} of {len(sc)}"
        out["proposition_one"]["gross_monotone_in"] = f"{sum(v['gross_monotone'] for v in sc)} of {len(sc)}"
        out["proposition_one"]["net_monotone_in"] = f"{sum(v['net_monotone'] for v in sc)} of {len(sc)}"

        # the ranked curve is the other half of the question, and the half the
        # recommended rules actually use
        rk = f.get("ranked") or {}
        out["proposition_one"]["ranked"] = {
            nm: {"pass": v["pass"], "best_k": v["best_k"], "best_net": v["best_net"],
                 "at_all": v["at_all"], "interior": v["interior"]} for nm, v in rk.items()}
        if rk:
            out["proposition_one"]["interior_in"] = (
                f"{sum(1 for v in rk.values() if v['interior'])} of {len(rk)}")
        d2 = f["dependence"]
        out["proposition_one"]["n_eff"] = d2.get("n_eff")

    gi0 = out.get("gap_innovation") or {}
    if gi0:
        out["bracket"] = waiting_bracket(lam, c, gi0["mean_bp"] / 1e4)
        # the boundary itself, on the measured innovations
        innov = gap_innovations(big, cut, 26, 20, cal)
        if innov:
            sol = solve_boundary(lam, c, innov)
            out["solved_curve"] = {t: v["boundary_bp"] for t, v in sol.items()}
            out["solved"] = {t: sol[t] for t in ("1", "2", "4", "8", "13", "26") if t in sol}
            out["solved_innovations"] = len(innov)
            br = out["bracket"]
            inside = 0
            for t, v in out["solved"].items():
                b = v["boundary_bp"]
                lo_b = br.get(t, {}).get("lower_bp")
                hi_b = br.get(t, {}).get("upper_bp")
                if b is not None and lo_b is not None and hi_b is not None:
                    v["inside_bracket"] = bool(lo_b - 1e-9 <= b <= max(hi_b, lo_b) + 1e-9)
                    inside += v["inside_bracket"]
            out["solved_inside_bracket"] = f"{inside} of {len(out['solved'])}"
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=1)
    print(f"wrote {args.out}")
    print(f"weekly hazard {100 * lam:.3f}%  ({out['lambda_month_pct']}% a month)")
    print("shrinkage:", sh)
    print("pools:", json.dumps(out["pools"], indent=1)[:600])
    print("shrinkage in window (not used):", out.get("shrinkage_in_window"))
    print("muR (top decile posterior) %.3f%%/week, pool spread %.3f%%, switch cost = %.2f weeks of edge"
          % (out["muR_weekly_pct"], out["posterior_spread_pct"], out["cost_in_weeks_of_edge"]))
    for t, v in out["horizons"].items():
        print(f"  T={t:>2}: A={v['expected_trading_weeks']:>5.2f}  band={v['band_weekly_bp']}bp "
              f"({v['band_in_pool_spreads']} pool spreads)  refill: {v['refill_a_stopped_sleeve']}")
    print("refill stops paying below", out["refill_min_weeks"], "weeks remaining")
    print("comparative:", json.dumps(out["comparative"], indent=1))
    print("risk term over the swaps the rule makes:", out.get("swap_band"))
    print("the pool's variance gradient (what an earlier version measured):",
          {kk: out.get("pool_variance_gradient", {}).get(kk)
           for kk in ("risk_term_weekly_bp", "delta_var", "delta_cov")})
    gi = out.get("gap_innovation") or {}
    print("weekly innovation of the gap:", gi)
    if out.get("solved"):
        print("the boundary, solved on %d measured innovations:" % out["solved_innovations"])
        for t, v in sorted(out["solved"].items(), key=lambda kv: int(kv[0])):
            print(f"  T={t:>2}: b* = {v['boundary_bp']} bp against a break-even of "
                  f"{v['break_even_bp']} bp, inside the bracket: {v.get('inside_bracket')}")
        print("  inside the bracket at", out["solved_inside_bracket"], "horizons")
    print("where the boundary has to lie:")
    for t, v in (out.get("bracket") or {}).items():
        print(f"  T={t:>2}: between {v['lower_bp']} and {v['upper_bp']} bp "
              f"(a factor of {v['ratio']}); one week costs {v['one_week_of_gap']} of the gap")
    p1 = out.get("proposition_one", {})
    print("Prop 1 holds (var > cov):", p1.get("holds"), " gross rises in", p1.get("gross_rises_in"),
          " net rises in", p1.get("net_rises_in"))
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
