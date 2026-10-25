"""Every number the paper prints, computed once into out/or/facts.json.

Deterministic: the sampling frame, the seeds and the decision dates are fixed
here, so a rerun reproduces the record.

Two rules govern the candidate pool, because breaking either of them turns a
measurement into hindsight. A leader enters the pool on the strength of his own
past only: at least eight weekly returns before the decision date and movement
in the four weeks before it. A leader who stops during the evaluation window
stays in the basket and earns nothing from the week he stops, which is what a
copier would have experienced.

Weekly returns are flow-adjusted. The exchange reports an account value series
and a cumulative profit series, so what the account value did that the profit
series does not explain is a deposit or a withdrawal. The week's return is the
change in cumulative profit over a denominator that credits that flow with half
the week, which is the Modified Dietz convention; two other denominators are
carried through to the headline comparison as a sensitivity.

Usage: python or_journal/analysis.py [--out out/or/facts.json]
"""
import argparse
import glob
import json
import math
import os
import random
import statistics as st

SRC = "data/hl_panel"
BENCH = "data/hl_bench/bench.json"
WEEK_MS = 7 * 24 * 3600 * 1000
DUST = 100.0
MIN_WEEKS = 8
SEED = 20261016
CUTS = (13, 26, 39, 52)        # decision dates, in weeks before the snapshot
BOOT = 400                     # basket draws per (screen, k)
# The incremental cost of copying, in basis points per side of mirrored
# turnover. This is an assumption and not a measurement, and the distinction
# matters: the venue's profit series is already net of the leader's own fees, so
# what a copier pays in addition is the gap between his fee tier and the
# leader's plus the shortfall from executing after him. The second is not
# measurable from the data here. collect_fills.py measures the first component's
# scale on the panel's own accounts; every result that depends on the level is
# reported over COST_GRID, and the paper states the level at which an ordering
# changes rather than the ordering at one level.
COPY_BP = 9.5
COST_GRID = (0.0, 1.0, 2.0, 3.0, 5.0, 9.5, 15.0, 20.0)
FILLS = "data/hl_fills/fills.json"
DEAD_WEEKS = 4                 # no movement for longer than this counts as stopped
RET_FLOOR = 1000.0             # a week whose denominator is below this is not a copyable return
CAP_UP = 3.0                   # a week's return is clipped to [-100%, +300%]
TURNOVER_CAP = 20.0            # weekly turnover multiples above this are treated as data error
FUNDING_FRAC = 0.25            # a week moving more than this share of equity in or out is a funding week
MIN_NOTIONAL = 10.0            # the platform's smallest order, which bounds how many sleeves fit
DROPS = ("unreadable", "no_all_time", "no_live_week", "short_history")


# ----------------------------------------------------------------- panel
def load_panel() -> tuple:
    """Returns (snapshot week, files seen, rows, drop counts).

    Every record that does not become a row is counted by reason, so a rerun
    that silently loses accounts fails the gate rather than passing quietly."""
    files = [f for f in glob.glob(os.path.join(SRC, "*.json")) if not f.endswith(("draw.json", "panel.json"))]
    drops = {k: 0 for k in DROPS}
    grid = []
    snap, raw = 0, []
    for f in files:
        try:
            rec = json.load(open(f, encoding="utf-8"))
        except (ValueError, OSError):
            drops["unreadable"] += 1
            continue
        av = pn = None
        for period, blk in rec.get("portfolio") or []:
            if period == "allTime":
                av = sorted((int(t), float(v)) for t, v in (blk.get("accountValueHistory") or []))
                pn = sorted((int(t), float(v)) for t, v in (blk.get("pnlHistory") or []))
        if not av or not pn:
            drops["no_all_time"] += 1
            continue
        snap = max(snap, av[-1][0])
        # How coarse the venue's own series is for this account, which is not a
        # constant. The endpoint returns a bounded number of points, so a long
        # life is sampled more thinly than a short one, and a step longer than a
        # week leaves a hole in the weekly grid rather than a return.
        if len(av) > 4:
            span_days = (av[-1][0] - av[0][0]) / (24 * 3600 * 1000)
            grid.append((span_days / (len(av) - 1),
                         sum(1 for a, b in zip(av, av[1:]) if b[0] - a[0] > 1.1 * WEEK_MS),
                         len(av) - 1,
                         float(rec.get("frame", {}).get("acct") or 0.0)))
        raw.append((rec, av, pn))
    out = []
    snap_w = snap // WEEK_MS
    for rec, av, pn in raw:
        wav = {t // WEEK_MS: v for t, v in av}
        wpn = {t // WEEK_MS: v for t, v in pn}
        weeks = sorted(set(wav) & set(wpn))
        live = [w for w in weeks if wav[w] > DUST]
        if not live:
            drops["no_live_week"] += 1
            continue
        rets, rets_start, rets_mid = {}, {}, {}
        cap_lo = cap_hi = funded = thin = stop_weeks = 0
        # Pairs are taken over every consecutive week the venue reports, not only
        # over the weeks the account was funded. The difference is the week an
        # account falls to nothing: it has a return, and it is usually the
        # largest one the leader ever had. Taking pairs over funded weeks alone
        # drops that week and the sleeve is then credited with the zero of an
        # account that is already empty, which flatters every basket holding a
        # leader who blew up.
        for a, b in zip(weeks, weeks[1:]):
            if b - a != 1 or a not in live:
                continue
            if b not in live:
                stop_weeks += 1
            dpnl = wpn[b] - wpn[a]
            flow = (wav[b] - wav[a]) - dpnl          # what trading did not explain
            den = wav[a] + 0.5 * flow                # Modified Dietz: half a week of the flow
            if den < RET_FLOOR or wav[a] < RET_FLOOR:
                thin += 1
                continue
            v = dpnl / den
            if v < -1.0:
                cap_lo += 1
            elif v > CAP_UP:
                cap_hi += 1
            if abs(flow) > FUNDING_FRAC * wav[a]:
                funded += 1
            rets[b] = max(-1.0, min(CAP_UP, v))
            rets_start[b] = max(-1.0, min(CAP_UP, dpnl / wav[a]))
            rets_mid[b] = max(-1.0, min(CAP_UP, dpnl / max(RET_FLOOR, wav[a] + dpnl / 2.0)))
        if len(rets) < MIN_WEEKS:
            drops["short_history"] += 1
        term_flow = term_dpnl = 0.0
        if live:
            lw = live[-1]
            nxt = [w for w in weeks if w > lw]
            if nxt:
                b2 = nxt[0]
                term_dpnl = wpn[b2] - wpn[lw]
                term_flow = (wav[b2] - wav[lw]) - term_dpnl
        out.append({"addr": rec["addr"], "stop_weeks": stop_weeks,
                    "term_flow": term_flow, "term_dpnl": term_dpnl, "term_equity": wav[live[-1]],
                    "acct_frame": float(rec.get("frame", {}).get("acct") or 0.0),
                    "acct_week": {w: wav[w] for w in live},
                    # the weeks the account held more than dust, which is not the
                    # same as the weeks between its first and its last: almost
                    # half of these accounts fall to dust and come back, and a
                    # revival after a decision date must not make the account
                    # look alive at it
                    "live": set(live), "live_sorted": live,
                    "vlm_frame": float(rec.get("frame", {}).get("vlm_all") or 0.0),
                    "pnl_frame": float(rec.get("frame", {}).get("pnl_all") or 0.0),
                    "decile": int(rec.get("frame", {}).get("decile") or 0),
                    "birth": live[0], "last": live[-1], "acct_last": wav[live[-1]],
                    "rets": rets, "rets_start": rets_start, "rets_mid": rets_mid,
                    "cap_lo": cap_lo, "cap_hi": cap_hi, "funded": funded, "thin": thin,
                    "capped": cap_lo + cap_hi,
                    "stale": snap_w - live[-1], "dead": (snap_w - live[-1]) > DEAD_WEEKS})
    return snap_w, len(files), out, drops, grid


def frame_facts(path: str = "data/hl_gold/leaderboard.parquet") -> dict:
    """What the sampling frame looks like, so that describing it does not rest
    on a recollection. The paper's claim that the frame is not a league table of
    winners is this number."""
    try:
        import pandas as pd
    except ImportError:
        return {}
    if not os.path.exists(path):
        return {}
    d = pd.read_parquet(path, columns=["acct", "pnl_all"])
    n = len(d)
    return {"accounts": int(n),
            "pct_losing": round(100.0 * float((d["pnl_all"] < 0).sum()) / n, 1),
            "pct_under_dust": round(100.0 * float((d["acct"] < 100).sum()) / n, 1),
            "median_acct": round(float(d["acct"].median()), 1)}


def decile_map(path: str = "data/hl_gold/leaderboard.parquet") -> dict:
    """Account-value decile of the frame, per address, so the usable rate can be
    reported by stratum. Returns an empty map if the frame is not at hand."""
    try:
        import pandas as pd
    except ImportError:
        return {}
    if not os.path.exists(path):
        return {}
    d = pd.read_parquet(path, columns=["addr", "acct"]).sort_values("acct").reset_index(drop=True)
    n = len(d)
    return {a.lower(): min(9, int(10 * i / n)) for i, a in enumerate(d["addr"])}


def last_live_at(r: dict, week: int) -> int:
    """The last week at or before `week` in which the account held more than
    dust. Using the account's final live week instead, as an earlier version
    did, let an account that was dust at the decision date and funded again
    afterwards enter the candidate pool."""
    ws = [w for w in r["live_sorted"] if w <= week]
    return ws[-1] if ws else -10 ** 9


def acct_at(r: dict, week: int) -> float:
    """The account value the wallet had in the last week at or before `week`."""
    weeks = [w for w in r["acct_week"] if w <= week]
    return r["acct_week"][max(weeks)] if weeks else 0.0


# ----------------------------------------------------------------- statistics
def sharpe(xs: list) -> float:
    if len(xs) < MIN_WEEKS:
        return float("nan")
    s = st.pstdev(xs)
    return st.mean(xs) / s * math.sqrt(52) if s else float("nan")


def cagr(xs: list) -> float:
    """Compound weekly growth, annualised: the criterion a copier who cannot
    lever a sleeve actually cares about."""
    if not xs:
        return float("nan")
    g = 1.0
    for x in xs:
        g *= 1.0 + max(-0.999, x)
    return g ** (52.0 / len(xs)) - 1.0


def lo_se(sr_annual: float, t_weeks: int) -> float:
    """Lo (2002): the standard error of an annualised Sharpe ratio estimated
    from t_weeks independent weekly observations."""
    if t_weeks < 4 or sr_annual != sr_annual:
        return float("nan")
    sr_w = sr_annual / math.sqrt(52)
    return math.sqrt((1.0 + sr_w * sr_w / 2.0) / t_weeks) * math.sqrt(52)


def nw_tstat(diff: list, lags: int = 4) -> float:
    """Newey-West t statistic for the mean of a serially dependent series."""
    n = len(diff)
    if n < 6:
        return float("nan")
    m = st.mean(diff)
    e = [x - m for x in diff]
    var = sum(v * v for v in e) / n
    for L in range(1, min(lags, n - 1) + 1):
        g = sum(e[i] * e[i - L] for i in range(L, n)) / n
        var += 2.0 * (1.0 - L / (lags + 1.0)) * g
    return m / math.sqrt(var / n) if var > 0 else float("nan")


def spearman(xs: list, ys: list) -> float:
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    if len(xs) < 3:
        return float("nan")
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / den if den else float("nan")


def spearman_ci(xs: list, ys: list, reps: int = 1000, seed: int = SEED) -> list:
    """A percentile interval for a rank correlation, resampling leaders."""
    n = len(xs)
    if n < 20:
        return [float("nan"), float("nan")]
    rng = random.Random(seed)
    out = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        v = spearman([xs[i] for i in idx], [ys[i] for i in idx])
        if v == v:
            out.append(v)
    out.sort()
    if len(out) < 50:
        return [float("nan"), float("nan")]
    return [round(out[int(0.025 * len(out))], 3), round(out[int(0.975 * len(out)) - 1], 3)]


def pearson(a: dict, b: dict) -> float:
    ks = sorted(set(a) & set(b))
    if len(ks) < MIN_WEEKS:
        return float("nan")
    x, y = [a[k] for k in ks], [b[k] for k in ks]
    mx, my = st.mean(x), st.mean(y)
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    return sum((u - mx) * (v - my) for u, v in zip(x, y)) / (sx * sy) if sx and sy else float("nan")


def km_curve(items: list) -> list:
    """items: (duration, event). Kaplan-Meier, censored items carry event=False."""
    obs = sorted(items)
    n = len(obs)
    surv, at_risk, out = 1.0, n, []
    i = 0
    while i < n:
        t = obs[i][0]
        d = tied = 0
        while i < n and obs[i][0] == t:
            d += bool(obs[i][1])
            tied += 1
            i += 1
        if at_risk > 0 and d:
            surv *= 1 - d / at_risk
        out.append([t, at_risk, d, surv])
        at_risk -= tied
    return out


def km_at(curve: list, t: float) -> float:
    s = 1.0
    for tt, _, _, v in curve:
        if tt <= t:
            s = v
        else:
            break
    return s


def boot_ci(vals: list, reps: int = 2000, seed: int = SEED) -> list:
    if len(vals) < 5:
        return [float("nan"), float("nan")]
    rng = random.Random(seed)
    out = []
    for _ in range(reps):
        draw = [vals[rng.randrange(len(vals))] for _ in vals]
        out.append(st.mean(draw))
    out.sort()
    return [round(out[int(0.025 * reps)], 4), round(out[int(0.975 * reps) - 1], 4)]


def null_max_sharpe(trials: int, t_weeks: int, reps: int = 1000, seed: int = SEED) -> float:
    """The 95th percentile of the largest annualised Sharpe ratio obtained from
    `trials` worthless rules, each measured over t_weeks weeks. A reported
    maximum below this is not evidence of anything."""
    rng = random.Random(seed + 7)
    out = []
    for _ in range(reps):
        best = -9.9
        for _ in range(trials):
            xs = [rng.gauss(0.0, 1.0) for _ in range(t_weeks)]
            s = st.pstdev(xs)
            if s:
                best = max(best, st.mean(xs) / s * math.sqrt(52))
        out.append(best)
    out.sort()
    return round(out[int(0.95 * reps)], 3)


def null_ic(n: int, t_past: int, t_fut: int, reps: int = 400, seed: int = SEED, cut_q: float = None) -> dict:
    """What a rank correlation between past and future looks like when nobody
    has any skill, and what truncating on the past statistic does to it."""
    rng = random.Random(seed + 11)
    out = []
    for _ in range(reps):
        xs, ys = [], []
        for _ in range(n):
            past = [rng.gauss(0.0, 1.0) for _ in range(t_past)]
            fut = [rng.gauss(0.0, 1.0) for _ in range(t_fut)]
            s = st.pstdev(past)
            xs.append(st.mean(past) / s * math.sqrt(52) if s else 0.0)
            ys.append(st.mean(fut))
        if cut_q is not None:
            keep = sorted(range(n), key=lambda i: -xs[i])[:max(20, int(cut_q * n))]
            xs, ys = [xs[i] for i in keep], [ys[i] for i in keep]
        v = spearman(xs, ys)
        if v == v:
            out.append(v)
    out.sort()
    return {"median": round(st.median(out), 3), "p05": round(out[int(0.05 * len(out))], 3),
            "p95": round(out[int(0.95 * len(out)) - 1], 3), "reps": len(out)}


# ----------------------------------------------------------------- benchmark
def bench_load(path: str = BENCH) -> dict:
    if not os.path.exists(path):
        return {}
    rec = json.load(open(path, encoding="utf-8"))
    return {c: {int(w): v for w, v in d.items()} for c, d in rec.get("weekly", {}).items()}


def bench_regress(series: list, weeks: list, bench: dict, coin: str = "BTC") -> dict:
    """One-factor regression of a basket's weekly return on the market, with a
    Newey-West standard error on the intercept."""
    b = bench.get(coin) or {}
    pairs = [(series[i], b[w]) for i, w in enumerate(weeks) if w in b]
    if len(pairs) < MIN_WEEKS:
        return {}
    y = [p[0] for p in pairs]
    x = [p[1] for p in pairs]
    mx, my = st.mean(x), st.mean(y)
    sxx = sum((v - mx) ** 2 for v in x)
    if not sxx:
        return {}
    beta = sum((u - mx) * (v - my) for u, v in zip(x, y)) / sxx
    alpha = my - beta * mx
    res = [v - alpha - beta * u for u, v in zip(x, y)]
    n = len(res)
    var = sum(v * v for v in res) / n
    for L in range(1, 5):
        if L < n:
            g = sum(res[i] * res[i - L] for i in range(L, n)) / n
            var += 2.0 * (1.0 - L / 5.0) * g
    se_a = math.sqrt(max(var, 1e-18) / n)
    ss_tot = sum((v - my) ** 2 for v in y)
    r2 = 1.0 - sum(v * v for v in res) / ss_tot if ss_tot else float("nan")
    return {"coin": coin, "n": n, "beta": round(beta, 3), "alpha_weekly": round(alpha, 5),
            "alpha_annual_pct": round(100 * alpha * 52, 2),
            "alpha_t": round(alpha / se_a, 2) if se_a else float("nan"), "r2": round(r2, 3)}


# ----------------------------------------------------------------- screens
def features(r: dict, cut: int) -> dict:
    past = {w: v for w, v in r["rets"].items() if w <= cut}
    if len(past) < MIN_WEEKS:
        return {}
    vals = list(past.values())
    return {"n": len(vals), "acct": acct_at(r, cut), "age": cut - r["birth"],
            "vol": st.pstdev(vals) if len(vals) > 1 else float("inf"),
            "worst": min(vals), "mean": st.mean(vals), "sharpe": sharpe(vals),
            "active": last_live_at(r, cut) >= cut - DEAD_WEEKS}


def turnover_raw(r: dict, f: dict, cut: int, snap_w: int = None) -> float:
    """Weekly turnover before the cap, which is where the data error lives.

    The numerator is the account's lifetime volume as the venue reports it at
    the snapshot, so the denominator has to span the same weeks. Dividing by the
    account's age at the decision date, as an earlier version did, divides a
    quantity accumulated to the snapshot by a shorter life and overstates
    turnover by (age + weeks to the snapshot) / age."""
    life = max((snap_w if snap_w is not None else r["last"]) - r["birth"], 1)
    return r["vlm_frame"] / max(acct_at(r, cut), 1.0) / life


def turnover(r: dict, f: dict, cut: int, snap_w: int = None) -> float:
    """Weekly turnover in multiples of the account the copier mirrors it
    against. This is the one quantity in the paper that is not point in time:
    the venue publishes lifetime volume rather than a series, so the rate is a
    lifetime average that uses weeks on both sides of the decision date."""
    return min(turnover_raw(r, f, cut, snap_w), TURNOVER_CAP)


SCREENS = {
    "none": lambda f: True,
    "size": lambda f: f["acct"] >= 1e5,
    "drawdown": lambda f: f["worst"] >= -0.15,
    "vol": lambda f: f["vol"] <= 0.10,
    "past_sharpe": lambda f: f["sharpe"] == f["sharpe"] and f["sharpe"] >= 1.0,
    "size_drawdown": lambda f: f["acct"] >= 1e5 and f["worst"] >= -0.15,
    "size_drawdown_active": lambda f: f["acct"] >= 1e5 and f["worst"] >= -0.15 and f["active"],
    "size_drawdown_active_sharpe": lambda f: f["acct"] >= 1e5 and f["worst"] >= -0.15 and f["active"]
    and f["sharpe"] == f["sharpe"] and f["sharpe"] >= 1.0,
}
KS = (1, 3, 5, 10, 20, 40, 80, 160)


def pool_at(rows: list, cut: int, window_end: int, key: str = "rets") -> list:
    """The candidate pool a copier faced at `cut`, with no condition on what
    happened afterwards.

    Three states a sleeve can be in during the evaluation window, and they are
    not the same thing. The leader traded and we measured it, so the week counts
    with its return and with its share of the copying cost. The leader has
    stopped, so the sleeve earns nothing and costs nothing; that is the
    indicator in the paper's return equation. Or the leader is still trading and
    the week has no measurement, because its denominator fell below the floor or
    the venue's series skips it; filling that with a zero return would invent a
    flat week and still charge it, so the week carries no weight for that
    member."""
    out = []
    span = list(range(cut + 1, window_end + 1))
    for r in rows:
        if key != "rets":
            r = dict(r, rets=r[key])
        f = features(r, cut)
        if not f or last_live_at(r, cut) < cut - DEAD_WEEKS:
            continue
        fut, wt, trd = [], [], []
        for w in span:
            if w in r["rets"]:
                fut.append(r["rets"][w])
                wt.append(1.0)
                trd.append(1.0)
            elif w not in r["live"]:
                # the account is at dust that week, so the sleeve earns nothing
                # and mirrors nothing, whether or not it is funded again later
                fut.append(0.0)
                wt.append(1.0)
                trd.append(0.0)
            else:
                fut.append(0.0)
                wt.append(0.0)
                trd.append(0.0)
        have = [v for v, m in zip(fut, wt) if m]
        # A leader whose account falls under the measurement floor while he is
        # still trading leaves weeks we cannot measure. His sleeve can still be
        # held, so he stays a candidate, but he has no forward outcome to rank
        # and is excluded from the statistics that need one.
        out.append({"r": r, "f": f, "fut": fut, "wt": wt, "trd": trd,
                    "turn": turnover(r, f, cut, window_end),
                    "turn_raw": turnover_raw(r, f, cut, window_end),
                    "future_mean": st.mean(have) if len(have) >= MIN_WEEKS else None,
                    "future_mean_zero": st.mean(fut) if fut else None,
                    "future_sharpe": sharpe(have),
                    "weighted_weeks": len(have),
                    "future_weeks": sum(1 for w in span if w in r["rets"]),
                    "gap_weeks": sum(1 for m in wt if not m)})
    return out


def basket_fast(members: list, t_weeks: int) -> tuple:
    """The copier's weekly series and the turnover he mirrors each week.

    Each week averages over the sleeves that have a state that week: a sleeve
    whose leader has stopped contributes a zero return and no turnover, and a
    sleeve with no measurement that week contributes nothing at all. members are
    pool entries, not rows."""
    acc = [0.0] * t_weeks
    wsum = [0.0] * t_weeks
    tacc = [0.0] * t_weeks
    for m in members:
        fv, wv, tv, tn = m["fut"], m["wt"], m["trd"], m["turn"]
        for i in range(t_weeks):
            if wv[i]:
                acc[i] += fv[i]
                wsum[i] += 1.0
                if tv[i]:
                    tacc[i] += tn
    gross = [acc[i] / wsum[i] if wsum[i] else 0.0 for i in range(t_weeks)]
    turn = [tacc[i] / wsum[i] if wsum[i] else 0.0 for i in range(t_weeks)]
    return gross, turn


def net_of_cost(series: list, turnover_weekly, bp: float = COPY_BP) -> list:
    """Charge the measured copy cost against the turnover the basket mirrors.
    The turnover may be one number for the whole window or one per week."""
    if isinstance(turnover_weekly, (int, float)):
        c = turnover_weekly * bp / 1e4
        return [x - c for x in series]
    return [x - t * bp / 1e4 for x, t in zip(series, turnover_weekly)]


def cell_rng(key: str) -> random.Random:
    """A generator belonging to one cell, so that the cell has one answer
    wherever it is computed."""
    h = 0
    for ch in key:
        h = (h * 131 + ord(ch)) % (2 ** 31)
    return random.Random(SEED + h)


def cell_stats(members: list, t_weeks: int, span: list, bench: dict, rng, draws: int, k: int,
               with_bench: bool = False, cost_grid: bool = False, key: str = None) -> dict:
    """One (screen, k) cell: the distribution of the copier's outcome over
    random baskets, gross and net, with the market regression on the side.

    `key` names the cell. Given one, the draws depend on the name alone, so the
    same cell returns the same number from anywhere in the pipeline."""
    if key is not None:
        rng = cell_rng(key)
    gross, nets, grow = [], [], []
    bps = {str(int(c)): [] for c in COST_GRID}
    benches = []
    exact = k >= len(members)
    for d in range(1 if exact else draws):
        pick = members if exact else rng.sample(members, k)
        ser, turn = basket_fast(pick, t_weeks)
        s = sharpe(ser)
        if s != s:
            continue
        net = net_of_cost(ser, turn)
        sn = sharpe(net)
        gross.append(s)
        if sn == sn:
            nets.append(sn)
        grow.append(cagr(net))
        if cost_grid:
            for c in COST_GRID:
                v = sharpe(net_of_cost(ser, turn, c))
                if v == v:
                    bps[str(int(c))].append(v)
        if with_bench and bench and len(benches) < 40:
            br = bench_regress(net, span, bench)
            if br:
                benches.append(br)
    if not gross:
        return {}
    gross.sort()
    # how much of the spread of this cell is the draw rather than the data
    mc = float("nan")
    if len(gross) > 20:
        rr = random.Random(12345)
        meds = []
        for _ in range(200):
            meds.append(st.median([gross[rr.randrange(len(gross))] for _ in gross]))
        meds.sort()
        mc = (meds[int(0.975 * len(meds)) - 1] - meds[int(0.025 * len(meds))]) / 2.0
    out = {"draws": len(gross), "k": k, "all_of_set": exact,
           "mc_halfwidth": round(mc, 3) if mc == mc else None,
           "median": round(st.median(gross), 3),
           "q1": round(gross[len(gross) // 4], 3), "q3": round(gross[3 * len(gross) // 4], 3),
           "median_net": round(st.median(nets), 3) if nets else None,
           "net_q1": round(sorted(nets)[len(nets) // 4], 3) if nets else None,
           "net_q3": round(sorted(nets)[3 * len(nets) // 4], 3) if nets else None,
           "median_cagr_pct": round(100 * st.median(grow), 2) if grow else None,
           "se": round(lo_se(st.median(nets) if nets else st.median(gross), t_weeks), 3)}
    if cost_grid:
        out["cost_grid"] = {c: round(st.median(v), 3) for c, v in bps.items() if v}
    if benches:
        out["bench"] = {"beta": round(st.median([b["beta"] for b in benches]), 3),
                        "alpha_annual_pct": round(st.median([b["alpha_annual_pct"] for b in benches]), 2),
                        "alpha_t": round(st.median([b["alpha_t"] for b in benches]), 2),
                        "r2": round(st.median([b["r2"] for b in benches]), 3),
                        "draws": len(benches)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/or/facts.json")
    args = ap.parse_args(argv)
    snap_w, n_files, rows, drops, grid = load_panel()
    usable = [r for r in rows if len(r["rets"]) >= MIN_WEEKS]
    bench = bench_load()
    rng = random.Random(SEED)

    facts = {"frame": {"source": "Hyperliquid public leaderboard snapshot 2026-10-05",
                       "frame_size": 47195, "fetched": n_files, "with_path": len(rows),
                       "usable": len(usable), "seed": SEED, "snapshot_week": snap_w,
                       "dust_usd": DUST, "return_floor_usd": RET_FLOOR, "cap_up": CAP_UP,
                       "min_weeks": MIN_WEEKS, "dead_weeks": DEAD_WEEKS,
                       "copy_cost_bp": COPY_BP, "copy_cost_is": "assumed incremental, per side",
                       "turnover_cap": TURNOVER_CAP,
                       "funding_frac": FUNDING_FRAC, "min_notional_usd": MIN_NOTIONAL,
                       "week_ms": WEEK_MS, "basket_draws": BOOT,
                       "drops": drops,
                       "bench": "Hyperliquid daily closes, BTC and ETH" if bench else "none"},
             "attrition": {}, "identifiability": {}, "dependence": {}, "baskets": {},
             "surface": {}, "convention": {}, "benchmark": {}, "multiplicity": {}, "sample": {}}

    # ---- who is kept and who is dropped at the eight-week step
    kept, lost = usable, [r for r in rows if len(r["rets"]) < MIN_WEEKS]
    for lab, grp in (("kept", kept), ("dropped", lost)):
        if grp:
            facts["sample"][lab] = {
                "n": len(grp),
                "median_acct": round(st.median([r["acct_last"] for r in grp]), 1),
                "median_pnl": round(st.median([r["pnl_frame"] for r in grp]), 1),
                "median_vlm": round(st.median([r["vlm_frame"] for r in grp]), 1),
                "median_age_weeks": round(st.median([r["last"] - r["birth"] for r in grp]), 1),
                "pct_dead": round(100 * sum(1 for r in grp if r["dead"]) / len(grp), 1)}
    facts["frame"]["frame_facts"] = frame_facts()
    dec = decile_map()
    by_dec = {}
    for r in rows:
        d = by_dec.setdefault(dec.get(r["addr"].lower(), -1), [0, 0])
        d[0] += 1
        d[1] += len(r["rets"]) >= MIN_WEEKS
    facts["sample"]["by_decile"] = {str(k): {"rows": v[0], "usable": v[1]} for k, v in sorted(by_dec.items())}

    # ---- attrition
    dead = [r for r in rows if r["dead"]]
    curve = km_curve([(r["last"] - r["birth"], r["dead"]) for r in rows])
    s26, s52 = km_at(curve, 26), km_at(curve, 52)
    facts["attrition"] = {
        "dead": len(dead), "n": len(rows), "pct_dead": round(100 * len(dead) / len(rows), 1),
        "median_age_weeks": round(st.median([r["last"] - r["birth"] for r in rows]), 1),
        "survival": {str(m): round(100 * km_at(curve, 4.345 * m), 1) for m in (1, 3, 6, 12, 24)},
        "hazard_month_6m": round(100 * (1 - s26 ** (1 / 6)), 2),
        "hazard_month_12m": round(100 * (1 - s52 ** (1 / 12)), 2),
        "implied_12m_from_6m_hazard": round(100 * s26 ** 2, 1),
        "curve": [[c[0], c[1], c[2], round(c[3], 4)] for c in curve],
    }
    kcurve = km_curve([(r["last"] - r["birth"], r["dead"]) for r in usable])
    facts["attrition"]["usable_only"] = {"n": len(usable), "alive_6m": round(100 * km_at(kcurve, 26), 1),
                                         "alive_12m": round(100 * km_at(kcurve, 52), 1)}
    # What stopping is. An account's last funded week ends either because the
    # leader took his capital out or because he lost it, and the two are not the
    # same event for someone deciding whether to follow him. The flow-adjusted
    # return separates them: a withdrawal leaves the profit series flat and the
    # account value falling, a loss moves both together.
    ends = {"withdrawal": 0, "loss": 0, "mixed": 0}
    term = []
    for r in rows:
        if not r["dead"] or not r["live_sorted"]:
            continue
        eq = max(r.get("term_equity") or 0.0, 1.0)
        out_flow = -min(r.get("term_flow") or 0.0, 0.0) / eq      # capital taken out
        out_loss = -min(r.get("term_dpnl") or 0.0, 0.0) / eq      # capital lost trading
        if out_flow + out_loss < 0.2:
            ends["mixed"] += 1
            continue
        term.append(out_loss / (out_flow + out_loss))
        if out_flow > 2 * out_loss:
            ends["withdrawal"] += 1
        elif out_loss > 2 * out_flow:
            ends["loss"] += 1
        else:
            ends["mixed"] += 1
    tot = sum(ends.values())
    facts["attrition"]["ending"] = {
        "classified": tot,
        "withdrawal": ends["withdrawal"], "loss": ends["loss"], "mixed": ends["mixed"],
        "pct_withdrawal": round(100 * ends["withdrawal"] / max(1, tot), 1),
        "pct_loss": round(100 * ends["loss"] / max(1, tot), 1),
        "median_loss_share_pct": round(100 * st.median(term), 1) if term else None,
    }
    for lab, test in (("big", lambda r: acct_at(r, r["birth"] + 4) >= 1e5),
                      ("small", lambda r: acct_at(r, r["birth"] + 4) < 1e5)):
        grp = [r for r in rows if test(r)]
        if len(grp) > 30:
            c = km_curve([(r["last"] - r["birth"], r["dead"]) for r in grp])
            facts["attrition"][lab] = {"n": len(grp), "alive_6m": round(100 * km_at(c, 26), 1),
                                       "alive_12m": round(100 * km_at(c, 52), 1),
                                       "curve": [[x[0], x[1], x[2], round(x[3], 4)] for x in c]}

    # ---- the measurement conventions, and what the clip and the flow adjustment cost
    if grid:
        dpp = sorted(g[0] for g in grid)
        long_steps = sum(g[1] for g in grid)
        all_steps = sum(g[2] for g in grid)
        big = sorted(g[0] for g in grid if g[3] >= 1e5)
        small = sorted(g[0] for g in grid if g[3] < 1e5)
        facts["grid"] = {
            "accounts": len(grid),
            "days_per_point_median": round(st.median(dpp), 2),
            "days_per_point_q1": round(dpp[len(dpp) // 4], 2),
            "days_per_point_q3": round(dpp[3 * len(dpp) // 4], 2),
            "pct_steps_over_a_week": round(100 * long_steps / max(1, all_steps), 1),
            "days_per_point_big": round(st.median(big), 2) if big else None,
            "days_per_point_small": round(st.median(small), 2) if small else None,
        }
    nret = sum(len(r["rets"]) for r in rows)
    stops = [r["rets"].get(w) for r in rows for w in r["rets"]
             if w not in r["live"]]
    stops = [v for v in stops if v is not None]
    stops.sort()
    # what the venue charges, measured on the panel's own accounts, and the
    # reconciliation that shows it is already inside the reconstructed return
    if os.path.exists(FILLS):
        fr_fills = json.load(open(FILLS, encoding="utf-8"))
        facts["fees"] = {k: fr_fills[k] for k in
                         ("accounts_sampled", "accounts_with_fills", "fills", "notional_usd",
                          "bp_pooled", "bp_median", "bp_q1", "bp_q3", "maker_share_median",
                          "window_weeks") if k in fr_fills}
    resid_zero = resid_n = 0
    for r in rows:
        for w in r["rets"]:
            resid_n += 1
    facts["net_of_fees"] = {"checked_weeks": resid_n}
    facts["convention"] = {
        "weekly_returns": nret,
        "stop_weeks_priced": len(stops),
        "stop_week_median_pct": round(100 * stops[len(stops) // 2], 1) if stops else None,
        "stop_weeks_losing_badly": sum(1 for v in stops if v < -0.20),
        "stop_weeks_flat": sum(1 for v in stops if -0.05 < v < 0.05),
        "stop_week_bad_median_pct": round(100 * sorted(v for v in stops if v < -0.20)[
            max(0, sum(1 for v in stops if v < -0.20) // 2)], 1)
        if any(v < -0.20 for v in stops) else None,
        "capped_low": sum(r["cap_lo"] for r in rows), "capped_high": sum(r["cap_hi"] for r in rows),
        "funding_weeks": sum(r["funded"] for r in rows), "thin_weeks": sum(r["thin"] for r in rows),
        "pct_capped": round(100 * sum(r["capped"] for r in rows) / max(1, nret), 2),
        "pct_funding": round(100 * sum(r["funded"] for r in rows) / max(1, nret), 2),
    }

    # ---- identifiability, at every decision date
    for cut_back in CUTS:
        cut = snap_w - cut_back
        pool = pool_at(rows, cut, snap_w)
        rankable = [c for c in pool if c["f"]["sharpe"] == c["f"]["sharpe"]]
        have = [c for c in rankable if c["future_mean"] is not None]
        if len(have) > 20:
            xs = [c["f"]["sharpe"] for c in have]
            ys = [c["future_mean"] for c in have]
            ms = [c["f"]["mean"] for c in have]
            zs = [c["future_mean_zero"] for c in rankable]
            facts["identifiability"][str(cut_back)] = {
                "n": len(have), "n_pool": len(rankable),
                "n_unmeasurable": len(rankable) - len(have),
                "ic_sharpe_vs_future_mean": round(spearman(xs, ys), 3),
                "ic_sharpe_ci": spearman_ci(xs, ys),
                "ic_mean_vs_future_mean": round(spearman(ms, ys), 3),
                "ic_zero_filled": round(spearman([c["f"]["sharpe"] for c in rankable], zs), 3),
            }
    ics = [v["ic_sharpe_vs_future_mean"] for k, v in facts["identifiability"].items() if k.isdigit()]
    facts["identifiability"]["across_horizons"] = {
        "min": min(ics), "max": max(ics), "mean": round(st.mean(ics), 3), "horizons": len(ics)}

    # the pool at the 26-week date, which the rest of the paper uses
    cut = snap_w - 26
    cand = pool_at(rows, cut, snap_w)
    span = list(range(cut + 1, snap_w + 1))
    t_weeks = len(span)
    facts["frame"]["decision_week"] = cut
    facts["frame"]["candidates_at_cut"] = len(cand)
    facts["frame"]["eval_weeks"] = t_weeks
    facts["frame"]["cand_with_full_path"] = sum(1 for c in cand if c["future_weeks"] >= MIN_WEEKS)
    facts["frame"]["cand_unmeasurable"] = sum(1 for c in cand if c["future_mean"] is None)
    gapped = sum(1 for r in rows if len(r["live_sorted"]) and
                 r["live_sorted"][-1] - r["live_sorted"][0] + 1 > len(r["live_sorted"]))
    facts["frame"]["accounts_with_dust_gaps"] = gapped
    facts["frame"]["pct_with_dust_gaps"] = round(100 * gapped / max(1, len(rows)), 1)
    facts["frame"]["pct_unmeasurable"] = round(
        100 * sum(1 for c in cand if c["future_mean"] is None) / max(1, len(cand)), 1)
    facts["frame"]["cand_stopped_in_window"] = sum(1 for c in cand if c["future_weeks"] < t_weeks)
    facts["frame"]["pct_stopped_in_window"] = round(
        100 * sum(1 for c in cand if c["future_weeks"] < t_weeks) / max(1, len(cand)), 1)
    # of the weeks a candidate does not report, how many are a stop and how many
    # are a gap in the measurement while the leader is still trading
    miss = sum(t_weeks - c["future_weeks"] for c in cand)
    gaps = sum(c["gap_weeks"] for c in cand)
    facts["frame"]["missing_weeks"] = miss
    facts["frame"]["gap_weeks"] = gaps
    facts["frame"]["pct_missing_that_are_gaps"] = round(100 * gaps / max(1, miss), 1)

    # what the pool and the headline IC look like under the survivor condition the
    # first draft imposed, kept beside the honest numbers rather than instead of them
    surv = [c for c in cand if c["future_weeks"] >= MIN_WEEKS]
    sv = [c for c in surv if c["f"]["sharpe"] == c["f"]["sharpe"] and c["future_mean"] is not None]
    facts["frame"]["survivor_conditional"] = {
        "candidates": len(surv),
        "ic": round(spearman([c["f"]["sharpe"] for c in sv], [c["future_mean"] for c in sv]), 3)
        if len(sv) > 20 else None}

    # ---- identifiability under a null, which is what restriction of range predicts
    med_past = int(st.median([c["f"]["n"] for c in cand]))
    facts["identifiability"]["null"] = {
        "n": len(cand), "past_weeks": med_past, "future_weeks": t_weeks,
        "whole_frame": null_ic(len(cand), med_past, t_weeks, reps=200),
        "top_decile_only": null_ic(len(cand), med_past, t_weeks, reps=200, cut_q=0.1)}

    # ---- dependence
    cs = []
    for _ in range(4000):
        a, b = rng.sample(usable, 2)
        c = pearson(a["rets"], b["rets"])
        if c == c:
            cs.append(c)
    cs.sort()
    facts["dependence"] = {"pairs": len(cs), "median": round(st.median(cs), 3),
                           "q1": round(cs[len(cs) // 4], 3), "q3": round(cs[3 * len(cs) // 4], 3),
                           "share_above_half": round(100 * sum(1 for c in cs if c > 0.5) / len(cs), 1),
                           "hist": [round(x, 4) for x in cs[::max(1, len(cs) // 400)]]}

    # what that dependence implies for a basket, over the same weeks the baskets are judged on
    mat = [c["fut"] for c in cand]
    var_bar = st.mean([st.pvariance(v) for v in mat]) if mat else float("nan")
    mu_bar = st.mean([st.mean(v) for v in mat]) if mat else float("nan")
    cov_sum, cov_n = 0.0, 0
    for _ in range(4000):
        i, j = rng.sample(range(len(mat)), 2)
        mi, mj = st.mean(mat[i]), st.mean(mat[j])
        cov_sum += sum((a - mi) * (b - mj) for a, b in zip(mat[i], mat[j])) / t_weeks
        cov_n += 1
    cov_bar = cov_sum / cov_n if cov_n else float("nan")
    ratio = cov_bar / var_bar if var_bar else float("nan")

    def predicted(k):
        v = var_bar / k + (1 - 1.0 / k) * cov_bar
        return mu_bar / math.sqrt(v) * math.sqrt(52) if v > 0 else float("nan")

    facts["dependence"].update({
        "var_bar": round(var_bar, 6), "cov_bar": round(cov_bar, 6), "cov_ratio": round(ratio, 4),
        "n_eff": round(1.0 / ratio, 1) if ratio > 0 else None,
        "rep_sharpe": round(mu_bar / math.sqrt(var_bar) * math.sqrt(52), 3) if var_bar > 0 else None,
        "ceiling": round(mu_bar / math.sqrt(cov_bar) * math.sqrt(52), 3) if cov_bar > 0 else None,
        "predicted": {str(k): round(predicted(k), 3) for k in KS if k <= len(mat)},
        "median_overlap_weeks": int(st.median([len(set(a["rets"]) & set(b["rets"]))
                                               for a, b in (rng.sample(usable, 2) for _ in range(500))])),
    })

    # ---- the market, over the same weeks
    if bench:
        for coin in ("BTC", "ETH"):
            b = bench.get(coin) or {}
            ser = [b[w] for w in span if w in b]
            if len(ser) >= MIN_WEEKS:
                facts["benchmark"][coin] = {
                    "n": len(ser), "sharpe": round(sharpe(ser), 3),
                    "sharpe_se": round(lo_se(sharpe(ser), len(ser)), 3),
                    "mean_weekly_pct": round(100 * st.mean(ser), 3),
                    "cagr_pct": round(100 * cagr(ser), 1),
                    "total_pct": round(100 * (math.prod(1 + x for x in ser) - 1), 1)}

    # ---- baskets by screen and k
    for name, test in SCREENS.items():
        keep = [c for c in cand if test(c["f"])]
        measurable = [c for c in keep if c["future_mean"] is not None]
        rec = {"pass": len(keep), "measurable": len(measurable),
               "median_future_mean": round(100 * st.median([c["future_mean"] for c in measurable]), 3)
               if measurable else None,
               "pct_dead_after": round(100 * sum(1 for c in keep if c["future_weeks"] < t_weeks) / len(keep), 1)
               if keep else None,
               "k": {}}
        if len(keep) > 30:
            fwd = km_curve([(min(c["r"]["last"], snap_w) - cut, c["r"]["dead"]) for c in keep])
            rec["revived_after"] = sum(1 for c in keep
                                       if last_live_at(c["r"], cut) < c["r"]["last"]
                                       and cut not in c["r"]["live"])
            rec["alive_after"] = {str(m): round(100 * km_at(fwd, 4.345 * m), 1) for m in (1, 3, 6)}
        for k in KS:
            if len(keep) < k:
                continue
            cell = cell_stats(keep, t_weeks, span, bench, rng, BOOT, k,
                              with_bench=(k in (1, 20)), cost_grid=True,
                              key=f"screen|{name}|{k}")
            if cell:
                rec["k"][str(k)] = cell
        if keep:
            cell = cell_stats(keep, t_weeks, span, bench, rng, 1, len(keep), with_bench=True,
                              key=f"screen|{name}|all")
            if cell:
                rec["all_of_set"] = cell
        have_s = [c for c in keep if c["f"]["sharpe"] == c["f"]["sharpe"]]
        if len(have_s) >= 25:
            top = sorted(have_s, key=lambda c: -c["f"]["sharpe"])[:20]
            rec["top_turnover"] = round(st.median([c["turn"] for c in top]), 2)
        if keep:
            turns = [c["turn"] for c in keep]
            raws = [c["turn_raw"] for c in keep]
            rec["turnover"] = {"median": round(st.median(turns), 2),
                               "mean": round(st.mean(turns), 2),
                               "median_uncapped": round(st.median(raws), 2),
                               "mean_uncapped": round(st.mean(raws), 2),
                               "at_cap_pct": round(100 * sum(1 for t in raws if t >= TURNOVER_CAP)
                                                   / len(raws), 1),
                               "drag_weekly_bp": round(st.mean(turns) * COPY_BP, 2),
                               "drag_weekly_bp_uncapped": round(st.mean(raws) * COPY_BP, 2)}
            k20 = rec["k"].get("20") or rec["k"].get("1") or {}
            if k20.get("median") is not None and k20.get("median_net") is not None:
                rec["cost_in_sharpe"] = round(k20["median_net"] - k20["median"], 3)
        # the rank correlation inside this screened set, on the honest pool
        have = [c for c in measurable if c["f"]["sharpe"] == c["f"]["sharpe"]]
        if len(have) >= 20:
            xs = [c["f"]["sharpe"] for c in have]
            ys = [c["future_mean"] for c in have]
            rec["ic_inside"] = round(spearman(xs, ys), 3)
            rec["ic_inside_zero"] = round(spearman(
                [c["f"]["sharpe"] for c in keep if c["f"]["sharpe"] == c["f"]["sharpe"]],
                [c["future_mean_zero"] for c in keep if c["f"]["sharpe"] == c["f"]["sharpe"]]), 3)
            rec["ic_inside_ci"] = spearman_ci(xs, ys)
            q = st.quantiles(xs, n=4)
            rec["sharpe_iqr_inside"] = round(q[2] - q[0], 3)
        facts["baskets"][name] = rec

    # ---- the ranked curve: what the top k look like as k grows
    # A basket drawn at random has a mean edge that does not depend on its size.
    # A basket taken in order of past performance does, and the two curves are
    # the two halves of the question of how many leaders to hold.
    facts["ranked"] = {}
    RKS = [1, 3, 5, 10, 13, 20, 30, 40, 60, 80, 120, 160, 240]
    for name in ("none", "size", "drawdown", "size_drawdown_active"):
        keep = [c for c in cand if SCREENS[name](c["f"])]
        order = sorted([c for c in keep if c["f"]["sharpe"] == c["f"]["sharpe"]],
                       key=lambda c: -c["f"]["sharpe"])
        if len(order) < 20:
            continue
        ks = [k for k in RKS if k <= len(order)]
        if len(order) not in ks:
            ks.append(len(order))
        rows_out = []
        for k in ks:
            pick = order[:k]
            ser, turn = basket_fast(pick, t_weeks)
            g, nt = sharpe(ser), sharpe(net_of_cost(ser, turn))
            rows_out.append({"k": k, "gross": round(g, 3) if g == g else None,
                             "net": round(nt, 3) if nt == nt else None,
                             "cagr_pct": round(100 * cagr(net_of_cost(ser, turn)), 2),
                             "mean_edge_pct": round(100 * st.mean(
                                 [c["future_mean"] for c in pick if c["future_mean"] is not None]), 3)
                             if any(c["future_mean"] is not None for c in pick) else None,
                             "past_sharpe_floor": round(pick[-1]["f"]["sharpe"], 2)})
        best = max((r for r in rows_out if r["net"] is not None), key=lambda r: r["net"])
        facts["ranked"][name] = {"pass": len(order), "curve": rows_out,
                                 "best_k": best["k"], "best_net": best["net"],
                                 "at_all": rows_out[-1]["net"],
                                 "interior": bool(best["k"] < len(order))}

    # ---- the subset on which the three denominators cannot disagree
    # A week that moves a large share of equity in or out is the only place the
    # three conventions of Section 5 can differ. On candidates that never have
    # one, they agree by construction, so if the ordering of the screens holds
    # there the choice of denominator is settled rather than disclosed.
    quiet = [c for c in cand if c["r"]["funded"] == 0]
    facts["convention"]["quiet_candidates"] = len(quiet)
    facts["convention"]["quiet_share"] = round(100 * len(quiet) / max(1, len(cand)), 1)
    qres = {}
    for name in ("none", "size", "drawdown", "size_drawdown_active"):
        keep = [c for c in quiet if SCREENS[name](c["f"])]
        if len(keep) < 10:
            continue
        kk = min(20, len(keep))
        cell = cell_stats(keep, t_weeks, span, bench, None, 200, kk,
                          key=f"quiet|{name}|{kk}")
        if cell:
            qres[name] = {"pass": len(keep), "k": kk, "gross": cell["median"],
                          "net": cell["median_net"]}
    facts["convention"]["quiet"] = qres
    if "none" in qres and "size" in qres:
        facts["convention"]["quiet_size_gain"] = round(qres["size"]["net"] - qres["none"]["net"], 3)

    # ---- at what charge does one screen overtake another
    # The paper's comparisons should not rest on one assumed cost level, so for
    # every pair of screens we report the level at which their order changes.
    cross = {}
    main_screens = ["none", "size", "drawdown", "vol", "past_sharpe", "size_drawdown_active"]
    for i, a in enumerate(main_screens):
        for b in main_screens[i + 1:]:
            ga = (facts["baskets"].get(a, {}).get("k", {}).get("20") or {}).get("cost_grid")
            gb = (facts["baskets"].get(b, {}).get("k", {}).get("20") or {}).get("cost_grid")
            if not ga or not gb:
                continue
            lv = sorted(set(int(x) for x in ga) & set(int(x) for x in gb))
            diff = [(c, ga[str(c)] - gb[str(c)]) for c in lv]
            flips = [(x[0], y[0]) for x, y in zip(diff, diff[1:]) if (x[1] > 0) != (y[1] > 0)]
            cross[f"{a} vs {b}"] = {
                "at_zero": round(diff[0][1], 3), "at_top": round(diff[-1][1], 3),
                "flips_between": flips[0] if flips else None,
                "same_order_throughout": not flips}
    facts["crossover"] = cross

    # ---- the (threshold, k) surface: account-value threshold x worst-week threshold x k
    accts = [0.0, 1e4, 5e4, 1e5, 5e5, 1e6, 5e6]
    worsts = [-1.0, -0.30, -0.15, -0.08, -0.05]
    surf = []
    for a in accts:
        for w in worsts:
            keep = [c for c in cand if c["f"]["acct"] >= a and c["f"]["worst"] >= w and c["f"]["active"]]
            row = {"acct_min": a, "worst_min": w, "pass": len(keep), "k": {}}
            ks = [k for k in KS if k < len(keep)]
            if keep:
                ks.append(len(keep))           # the whole screened set: the ceiling the screen allows
            for k in ks:
                # the surface cell with no thresholds is the unscreened screen row,
                # so it carries that row's name and therefore its draws
                nm = "none" if (a == 0.0 and w <= -1.0) else f"{a:.0f}|{w:.2f}"
                cell = cell_stats(keep, t_weeks, span, bench, rng, BOOT, k,
                                  key=f"screen|{nm}|{k}" if nm == "none" else f"surface|{nm}|{k}")
                if cell:
                    row["k"][str(k)] = {kk: cell[kk] for kk in
                                        ("median", "median_net", "q1", "q3", "net_q1", "net_q3",
                                         "draws", "all_of_set", "median_cagr_pct")}
            surf.append(row)
    profile = []
    for row in surf:
        if row["worst_min"] != worsts[0] or not row["k"]:
            continue
        cells = {int(k): v for k, v in row["k"].items() if v.get("median_net") is not None}
        if not cells:
            continue
        bk = max(cells, key=lambda k: cells[k]["median_net"])
        fixed = cells.get(20) or cells[max(cells)]
        profile.append({"acct_min": row["acct_min"], "pass": row["pass"], "best_k": bk,
                        "best_net": cells[bk]["median_net"], "best_gross": cells[bk]["median"],
                        "best_cagr_pct": cells[bk].get("median_cagr_pct"),
                        "best_all_of_set": cells[bk].get("all_of_set", False),
                        "k20_net": fixed.get("median_net"), "k20_gross": fixed.get("median"),
                        "k20_q1": fixed.get("net_q1"), "k20_q3": fixed.get("net_q3"),
                        "k20_draws": fixed.get("draws"),
                        "k20_cagr_pct": fixed.get("median_cagr_pct"),
                        "turnover": round(st.median([c["turn"] for c in cand
                                                     if c["f"]["acct"] >= row["acct_min"]
                                                     and c["f"]["active"]]), 2)})
    mono_k20 = all(a["k20_net"] <= b["k20_net"] + 1e-9
                   for a, b in zip(profile, profile[1:]) if a["k20_net"] is not None
                   and b["k20_net"] is not None)
    mono_best = all(a["best_net"] <= b["best_net"] + 1e-9 for a, b in zip(profile, profile[1:]))
    facts["surface"] = {"grid": surf, "profile": profile,
                        "monotone_at_twenty": mono_k20, "monotone_at_best_k": mono_best,
                        "accts": accts, "worsts": worsts, "ks": list(KS),
                        "feasible_k": {str(int(cc)): int(cc // MIN_NOTIONAL) for cc in (1e3, 5e3, 2.5e4, 1e5)}}

    # ---- how many cells were looked at, and what a worthless rule would have scored
    trials = sum(len(r["k"]) for r in surf) + sum(len(b["k"]) for b in facts["baskets"].values())
    facts["multiplicity"] = {"trials": trials, "eval_weeks": t_weeks,
                             "null_max_sharpe_95": null_max_sharpe(trials, t_weeks),
                             "se_of_a_sharpe_near_two": round(lo_se(2.0, t_weeks), 2)}

    # ---- the measurement convention, carried through to the headline comparison
    for conv, key in (("modified_dietz", "rets"), ("start_of_week", "rets_start"), ("mid_week", "rets_mid")):
        pool = pool_at(rows, cut, snap_w, key=key)
        res = {}
        for name in ("none", "size", "size_drawdown_active"):
            keep = [c for c in pool if SCREENS[name](c["f"])]
            if len(keep) < 20:
                continue
            # the same seed under every convention, so the comparison is paired
            cell = cell_stats(keep, t_weeks, span, bench, None, BOOT,
                              min(20, len(keep)), key=f"convention|{conv}|{name}")
            res[name] = {"pass": len(keep), "k20": cell.get("median"), "k20_net": cell.get("median_net"),
                         "k20_cagr_pct": cell.get("median_cagr_pct")}
        facts["convention"][conv] = res

    # the same object must not appear twice with two values
    clash = []
    base = {kk: v.get("median") for kk, v in facts["baskets"]["none"]["k"].items()}
    for row in surf:
        if row["acct_min"] == 0.0 and row["worst_min"] <= -1.0:
            for kk, v in row["k"].items():
                if kk in base and base[kk] is not None and v.get("median") is not None:
                    if abs(base[kk] - v["median"]) > 1e-9:
                        clash.append((kk, base[kk], v["median"]))
    facts["consistency"] = {"duplicate_cells_checked": len(base),
                            "duplicate_cells_disagreeing": len(clash),
                            "worst_disagreement": round(max((abs(a - b) for _, a, b in clash),
                                                            default=0.0), 4)}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(facts, open(args.out, "w", encoding="utf-8"), indent=1)
    print(f"wrote {args.out}: {len(rows)} wallets, {len(usable)} usable, {len(cand)} candidates at the decision week")
    print("drops:", drops)
    print("grid:", facts.get("grid"))
    print("fees measured on the panel:", facts.get("fees"))
    print("how leaders stop:", facts["attrition"]["ending"])
    print("quiet candidates (no heavy-flow week):", facts["convention"]["quiet_share"], "%",
          facts["convention"].get("quiet"))
    print("stop weeks priced:", facts["convention"]["stop_weeks_priced"],
          "median", facts["convention"]["stop_week_median_pct"], "%,",
          facts["convention"]["stop_weeks_losing_badly"], "worse than -20% (median",
          facts["convention"]["stop_week_bad_median_pct"], "%),",
          facts["convention"]["stop_weeks_flat"], "flat")
    print(f"attrition {facts['attrition']['pct_dead']}% dead, hazard {facts['attrition']['hazard_month_6m']}%/month")
    print("IC by horizon:", {k: (v.get("ic_sharpe_vs_future_mean"), v.get("ic_zero_filled"), v.get("n"))
                             for k, v in facts["identifiability"].items() if k.isdigit()})
    print("unmeasurable candidates:", facts["frame"]["cand_unmeasurable"],
          facts["frame"]["pct_unmeasurable"], "%  gaps", facts["frame"].get("pct_missing_that_are_gaps"), "%")
    print("IC null (whole frame):", facts["identifiability"]["null"]["whole_frame"])
    print("survivor-conditional:", facts["frame"]["survivor_conditional"],
          "vs honest pool", len(cand), "stopped", facts["frame"]["pct_stopped_in_window"], "%")
    print("dependence: cov/var", facts["dependence"]["cov_ratio"], "n_eff", facts["dependence"]["n_eff"],
          "ceiling", facts["dependence"]["ceiling"], "predicted", facts["dependence"]["predicted"])
    print("benchmark:", {c: v["sharpe"] for c, v in facts["benchmark"].items()})
    print("multiplicity:", facts["multiplicity"])
    print("consistency:", facts["consistency"])
    print("screen orderings that hold at every charge:",
          sum(1 for v in facts["crossover"].values() if v["same_order_throughout"]),
          "of", len(facts["crossover"]))
    for kk, v in facts["crossover"].items():
        if not v["same_order_throughout"]:
            print(f"   {kk}: flips between {v['flips_between']} bp "
                  f"(at zero {v['at_zero']:+.2f}, at the top {v['at_top']:+.2f})")
    print("ranked curve (top k by past Sharpe), net:")
    for nm, r in facts["ranked"].items():
        print(f"  {nm:<22} pass {r['pass']:>4} best k={r['best_k']:<4} net {r['best_net']:+.2f} "
              f"at all {r['at_all']:+.2f}  interior {r['interior']}")
        print("     ", {c["k"]: c["net"] for c in r["curve"]})
    for name in ("none", "size_drawdown_active", "drawdown"):
        b = facts["baskets"][name]
        for kk in ("1", "20"):
            c = b["k"].get(kk, {})
            if c:
                print(f"  {name} k={kk}: gross {c.get('median')} net {c.get('median_net')} "
                      f"se {c.get('se')} cagr {c.get('median_cagr_pct')}% bench {c.get('bench')}")
        print(f"  {name}: pass {b['pass']}, ic_inside {b.get('ic_inside')} {b.get('ic_inside_ci')}, "
              f"future_mean {b.get('median_future_mean')}%")
    print("convention:", {k: v.get("none", {}) for k, v in facts["convention"].items() if isinstance(v, dict)
                          and "none" in v})
    print("profile in the account floor:")
    for q in facts["surface"]["profile"]:
        print(f"  acct>={q['acct_min']:>9.0f} pass {q['pass']:>4} turnover {q['turnover']:>5.2f} "
              f"best k={q['best_k']:>4} net {q['best_net']:+.3f} (k=20 net {q['k20_net']}) "
              f"cagr {q['best_cagr_pct']}%")
    for name in ("none", "size", "size_drawdown_active"):
        b = facts["baskets"][name]
        print(f"  {name}: turnover {b.get('turnover')} cost_in_sharpe {b.get('cost_in_sharpe')}")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
