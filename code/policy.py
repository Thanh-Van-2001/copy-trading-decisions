"""What a rule would have earned, over several decision dates.

Each policy is a rule a copier could have run: at a decision date it may use
only what was observable then, it holds the basket for the evaluation window, it
earns nothing on a sleeve whose leader has stopped, and it pays the measured
copying cost on the turnover it mirrors.

A rule is a family and a choice inside it. The family is the set the copier will
choose from, which is the screening decision:

  open    everything on offer at the date
  risk    a worst past week no worse than WORST_MIN, weekly volatility at most
          VOL_MAX, and recent movement
  big     an account above ACCT_MIN at the date, and recent movement

Inside a family the rule is one of:

  random   k leaders drawn at random from the set
  top      the k highest past Sharpe ratios in it, a single path
  all      every leader in it, equally weighted, a single path
  replace  as random, but a sleeve whose leader has been silent for DETECT_LAG
           weeks is moved to another leader who is not known to be stale at that
           week, which costs the round trip

Two things the first draft of this script got wrong, and this one does not. A
leader is a candidate on the strength of his past alone: requiring him to have
returns inside the holding window admitted only the survivors. And a stop is
noticed with a lag, because an account that has not moved this week has not
necessarily stopped.

Windows are reported twice. Dates spaced SPACING weeks apart with HOLD-week
holds overlap, so the fuller grid is reported as overlapping and the disjoint
grid, spaced by the holding period itself, carries the inference.

Usage: python or_journal/policy.py [--out out/or/policy.json]
"""
import argparse
import json
import os
import random
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis import (COPY_BP, COST_GRID, DEAD_WEEKS, MIN_WEEKS, acct_at,  # noqa: E402
                      bench_load, bench_regress,
                      cagr, features, last_live_at, load_panel, lo_se, nw_tstat, sharpe,
                      spearman, turnover)
from theory import expected_trading_weeks, shrink_slope, weekly_hazard  # noqa: E402

SEED = 20261016
HOLD = 26          # weeks the basket is held and judged
SPACING = 13       # weeks between decision dates on the overlapping grid
DATES = 5
DRAWS = 200        # random baskets per policy and date
KS = (5, 10, 20)
DETECT_LAG = DEAD_WEEKS    # weeks of silence before a copier would notice a stop
SWITCH_COST = 2 * COPY_BP / 1e4   # a replacement unwinds one book and opens another
WORST_MIN = -0.15
VOL_MAX = 0.25
ACCT_MIN = 1e5
NAMES = ("random", "top", "all", "replace", "index", "hold_index")
# the band widths swept in Section 9, in weekly return units; None is the width
# Proposition 2 derives and inf never swaps
BANDS = (0.0, None, 10e-4, 50e-4, 200e-4, float("inf"), "solved")
# the boundary solved by backward induction in theory.py, in weekly return units
# and indexed by the weeks a basket still has to run
SOLVED = {}
try:
    _th = json.load(open("out/or/theory.json", encoding="utf-8"))
    SOLVED = {int(k): v / 1e4 for k, v in (_th.get("solved_curve") or {}).items()
              if v is not None}
except Exception:                                                   # noqa: BLE001
    SOLVED = {}
TOP_CURVE_KS = (1, 3, 5, 10, 20, 40, 80, 160)


def risk_screen(f: dict) -> bool:
    """The screen the first draft recommended: a leader whose worst past week is
    no worse than WORST_MIN, who has traded recently, and whose weekly
    volatility is at most VOL_MAX."""
    return f["worst"] >= WORST_MIN and f["active"] and f["vol"] <= VOL_MAX


def size_screen(f: dict) -> bool:
    """The screen the decision surface selects: an account above ACCT_MIN at the
    decision date, still trading."""
    return f["acct"] >= ACCT_MIN and f["active"]


FAMILIES = {"open": lambda f: True, "risk": risk_screen, "big": size_screen}


def run_basket(pick: list, cut: int, hold: int, replace_from: list = None,
               rng: random.Random = None) -> tuple:
    """Weekly series of the copier's book, the turnover it mirrors each week, and
    the number of replacements made. `pick` and `replace_from` hold pool entries.

    A sleeve is in one of three states each week, as in the paper's return
    equation. The leader traded and we measured it, so the week carries his
    return and his share of the cost. The leader has stopped, so the sleeve earns
    nothing and costs nothing. Or he is still trading and the week has no
    measurement, in which case the sleeve carries no weight that week rather
    than a invented flat return."""
    members = list(pick)
    series, turns, swaps = [], [], 0
    for w in range(cut + 1, cut + hold + 1):
        if replace_from is not None:
            for j, m in enumerate(members):
                # silent for DETECT_LAG weeks is the earliest a copier could tell
                if last_live_at(m["r"], w - 1) <= w - 1 - DETECT_LAG:
                    pool = [c for c in replace_from
                            if c not in members
                            and last_live_at(c["r"], w - 1) > w - 1 - DETECT_LAG]
                    if pool:
                        members[j] = rng.choice(pool)
                        swaps += 1
        acc = wsum = tacc = 0.0
        for m in members:
            if w in m["r"]["rets"]:
                acc += m["r"]["rets"][w]
                tacc += m["turn"]
                wsum += 1.0
            elif w not in m["r"]["live"]:
                wsum += 1.0
        series.append(acc / wsum if wsum else 0.0)
        turns.append(tacc / wsum if wsum else 0.0)
    return series, turns, swaps


def posteriors_at(src: list, w: int, cal: dict) -> dict:
    """Every candidate's shrunk weekly edge using returns up to week w only.

    A leader who has been silent for DETECT_LAG weeks is known to be earning
    nothing, so his edge is zero whatever his record says; that is the same
    state the paper's return equation gives a stopped sleeve, and it is what
    makes the maintenance rule and the replacement rule one rule."""
    beta, pm, pr = cal["beta"], cal["past_mean"], cal["prior"]
    out = {}
    for c in src:
        r = c["r"]
        if last_live_at(r, w) <= w - DEAD_WEEKS:
            out[r["addr"]] = 0.0
            continue
        tot, cnt = 0.0, 0
        for ww, v in r["rets"].items():
            if ww <= w:
                tot += v
                cnt += 1
        out[r["addr"]] = pr + beta * (tot / cnt - pm) if cnt >= MIN_WEEKS else pr
    return out


def calibrate(src: list, cut: int) -> dict:
    """The shrinkage slope, from two windows that both close before `cut`.

    At the earliest decision dates the venue is too young for two windows of the
    holding length, so the split is shortened until enough leaders have a record
    on both sides of it. The width used is recorded, because a slope fitted on
    eight-week windows is a weaker instrument than one fitted on twenty-six."""
    for width in (HOLD, 13, MIN_WEEKS):
        a, b = [], []
        for c in src:
            past = [v for w, v in c["r"]["rets"].items() if w <= cut - width]
            mid = [v for w, v in c["r"]["rets"].items() if cut - width < w <= cut]
            if len(past) >= MIN_WEEKS and len(mid) >= min(MIN_WEEKS, width):
                a.append(st.mean(past))
                b.append(st.mean(mid))
        if len(a) >= 50:
            sh = shrink_slope(a, b)
            if sh:
                return {"beta": sh["beta"], "past_mean": sh["past_mean_weekly_pct"] / 100.0,
                        "prior": sh["prior_weekly_pct"] / 100.0, "n": sh["n"],
                        "correlation": sh["correlation"], "window": width}
    return {"beta": 0.0, "past_mean": 0.0, "prior": 0.0, "n": 0, "window": None}


def run_index(src: list, k: int, cut: int, hold: int, lam: float, cal: dict,
              band_fixed: float = None) -> tuple:
    """The band rule of Proposition 2, run week by week.

    Hold the k leaders with the highest shrunk edge. Each week, re-rank on what
    is known by then and swap a sleeve only when a candidate's edge exceeds its
    own by more than the band c / A(T), which widens as the horizon shortens."""
    post = posteriors_at(src, cut, cal)
    order = sorted(src, key=lambda c: -post[c["r"]["addr"]])
    members = order[:k]
    series, turns, swaps = [], [], 0
    for w in range(cut + 1, cut + hold + 1):
        remaining = cut + hold - w + 1
        if band_fixed is None:
            band = SWITCH_COST / max(expected_trading_weeks(lam, remaining), 1e-9)
        elif band_fixed == "solved":
            # the solved boundary at this many weeks remaining, which is what
            # Propositions 3 and 4 say the rule should use
            band = SOLVED.get(remaining, SOLVED.get(max(SOLVED), 0.0)) if SOLVED else 0.0
        else:
            band = band_fixed
        post = posteriors_at(src, w - 1, cal)       # only what is known before the week
        held = {m["r"]["addr"] for m in members}
        outside = sorted((c for c in src if c["r"]["addr"] not in held),
                         key=lambda c: -post[c["r"]["addr"]])
        for _ in range(k):                          # at most one pass over the sleeves
            if not outside:
                break
            worst = min(range(len(members)), key=lambda i: post[members[i]["r"]["addr"]])
            best = outside[0]
            if post[best["r"]["addr"]] - post[members[worst]["r"]["addr"]] <= band:
                break
            outside.pop(0)
            members[worst] = best
            swaps += 1
        acc = wsum = tacc = 0.0
        for m in members:
            if w in m["r"]["rets"]:
                acc += m["r"]["rets"][w]
                tacc += m["turn"]
                wsum += 1.0
            elif w not in m["r"]["live"]:
                wsum += 1.0
        series.append(acc / wsum if wsum else 0.0)
        turns.append(tacc / wsum if wsum else 0.0)
    return series, turns, swaps


def net(series: list, turn, bp: float = COPY_BP, swaps: int = 0, k: int = 1) -> list:
    """The copier's series after the cost charged on the turnover he mirrors.
    `turn` is one number for the window or one per week."""
    if isinstance(turn, (int, float)):
        out = [x - turn * bp / 1e4 for x in series]
    else:
        out = [x - t * bp / 1e4 for x, t in zip(series, turn)]
    if swaps and out:
        out[0] -= SWITCH_COST * swaps / k
    return out


def evaluate(src: list, name: str, k: int, cut: int, rng: random.Random,
             lam: float = 0.0, cal: dict = None) -> dict:
    """One rule at one date: the distribution over random baskets, or the single
    path a deterministic rule would have taken."""
    vals, nets, grow, swaps, costs = [], [], [], [], {str(int(c)): [] for c in COST_GRID}
    series_of, gross_of = [], []
    deterministic = name in ("top", "all", "index")
    if name in ("index", "hold_index"):
        ser, turn, sw = run_index(src, k, cut, HOLD, lam, cal,
                                  band_fixed=(float("inf") if name == "hold_index" else None))
        nser = net(ser, turn, COPY_BP, sw, k)
        sv = sharpe(nser)
        if sv != sv:
            return {}
        return {"weekly": [round(v, 6) for v in nser], "weekly_gross": [round(v, 6) for v in ser],
                "draws_net": [round(sv, 4)],
                "median": round(sv, 3), "mean": round(sv, 3), "gross": round(sharpe(ser), 3),
                "cagr_pct": round(100 * cagr(nser), 2), "se": round(lo_se(sv, HOLD), 3),
                "n": 1, "deterministic": True, "swaps": sw, "members": k,
                "cost_grid": {str(int(cc)): round(sharpe(net(ser, turn, cc, sw, k)), 3)
                              for cc in COST_GRID}}
    if deterministic:
        if name == "all":
            order = src
        else:
            order = sorted([c for c in src if c["f"]["sharpe"] == c["f"]["sharpe"]],
                           key=lambda c: -c["f"]["sharpe"])[:k]
            if len(order) < k:
                return {}
        runs = [order]
    else:
        runs = [rng.sample(src, k) for _ in range(DRAWS)]
    for pick in runs:
        rep = src if name == "replace" else None
        ser, turn, sw = run_basket(pick, cut, HOLD, replace_from=rep, rng=rng)
        nser = net(ser, turn, COPY_BP, sw, len(pick))
        s = sharpe(nser)
        if s != s:
            continue
        vals.append(sharpe(ser))
        nets.append(s)
        series_of.append(nser)
        gross_of.append(ser)
        grow.append(cagr(nser))
        swaps.append(sw)
        for c in COST_GRID:
            v = sharpe(net(ser, turn, c, sw, len(pick)))
            if v == v:
                costs[str(int(c))].append(v)
    if not nets:
        return {}
    weekly = [round(sum(col) / len(col), 6) for col in zip(*series_of)] if series_of else []
    weekly_gross = [round(sum(col) / len(col), 6) for col in zip(*gross_of)] if gross_of else []
    return {"weekly": weekly, "weekly_gross": weekly_gross, "draws_net": sorted(round(v, 4) for v in nets),
            "median": round(st.median(nets), 3), "mean": round(st.mean(nets), 3),
            "gross": round(st.median(vals), 3),
            "cagr_pct": round(100 * st.median(grow), 2),
            "se": round(lo_se(st.median(nets), HOLD), 3),
            "n": len(nets), "deterministic": deterministic,
            "swaps": round(st.mean(swaps), 2) if swaps else 0.0,
            "members": len(src) if name == "all" else k,
            "cost_grid": {c: round(st.median(v), 3) for c, v in costs.items() if v}}


def one_grid(rows: list, snap_w: int, spacing: int, n_dates: int, rng: random.Random,
             lam: float = 0.0) -> dict:
    """The whole rule table on one grid of decision dates."""
    dates = sorted(snap_w - HOLD - i * spacing for i in range(n_dates))
    earliest = min(r["birth"] for r in rows) + MIN_WEEKS + 4
    dates = [d for d in dates if d > earliest]
    out = {"spacing": spacing, "hold": HOLD, "dates": [], "summary": {}, "series": {},
           "series_gross": {}}
    dists = {}
    for cut in dates:
        cand = []
        for r in rows:
            f = features(r, cut)
            if f and last_live_at(r, cut) >= cut - DEAD_WEEKS:
                cand.append({"r": r, "f": f, "turn": turnover(r, f, cut, snap_w)})
        if len(cand) < 40:
            continue
        sets = {fam: [c for c in cand if test(c["f"])] for fam, test in FAMILIES.items()}
        cal = calibrate(cand, cut)
        screened = sets["risk"]
        # the same three-state convention the baskets use: a stopped leader earns
        # zero, an unmeasurable week carries no weight, and a leader with fewer
        # than MIN_WEEKS measurable weeks has no outcome to rank
        fut = {}
        for c in cand:
            vals = [c["r"]["rets"][w] if w in c["r"]["rets"] else 0.0
                    for w in range(cut + 1, cut + HOLD + 1)
                    if w in c["r"]["rets"] or w not in c["r"]["live"]]
            fut[c["r"]["addr"]] = st.mean(vals) if len(vals) >= MIN_WEEKS else None
        def ic_of(group):
            g = [c for c in group if c["f"]["sharpe"] == c["f"]["sharpe"]
                 and fut[c["r"]["addr"]] is not None]
            if len(g) < 20:
                return None
            return round(spearman([c["f"]["sharpe"] for c in g],
                                  [fut[c["r"]["addr"]] for c in g]), 3)

        rec = {"cut": cut, "candidates": len(cand), "screened": len(screened),
               "sets": {fam: len(v) for fam, v in sets.items()},
               "ic_inside": {fam: ic_of(v) for fam, v in sets.items()},
               "median_age": round(st.median([c["f"]["age"] for c in cand]), 1),
               "stopped_in_hold": round(100 * sum(1 for c in cand
                                                  if last_live_at(c["r"], cut + HOLD)
                                                  < cut + HOLD - DEAD_WEEKS) / len(cand), 1),
               "revived_after": sum(1 for c in cand if cut not in c["r"]["live"]),
               "unmeasurable": sum(1 for c in cand if fut[c["r"]["addr"]] is None),
               "shrinkage": {kk: cal.get(kk) for kk in ("beta", "correlation", "n", "window")},
               "ic_whole_pool": ic_of(cand),
               "policies": {}}
        for fam, src in sets.items():
            for k in KS:
                for name in NAMES:
                    if len(src) < max(k, 5) or (name == "all" and k != KS[0]):
                        continue
                    if name == "replace" and fam == "open":
                        continue
                    cell = evaluate(src, name, k, cut, rng, lam, cal)
                    if cell:
                        key = f"{fam}_all" if name == "all" else f"{fam}_{name}_{k}"
                        weekly = cell.pop("weekly", [])
                        weekly_gross = cell.pop("weekly_gross", [])
                        draws_net = cell.pop("draws_net", [])
                        if name in ("random", "top", "index") and k == KS[-1]:
                            out["series"].setdefault(key, {})[str(cut)] = weekly
                            out["series_gross"].setdefault(key, {})[str(cut)] = weekly_gross
                        if name == "random":
                            dists.setdefault(key, {})[cut] = draws_net
                        rec["policies"][key] = cell
        # where a deterministic rule's single path sits inside the matching random distribution
        for fam in sets:
            for k in KS:
                a, b = f"{fam}_top_{k}", f"{fam}_random_{k}"
                draws = (dists.get(b) or {}).get(cut) or []
                if a in rec["policies"] and draws:
                    x = rec["policies"][a]["median"]
                    rec["policies"][a]["percentile_in_random"] = round(
                        100 * sum(1 for v in draws if v < x) / len(draws), 1)
        # the curve Proposition 1 is about, taken in order rather than at random
        rec["top_curve"] = {}
        for fam in ("open", "big"):
            src = sets[fam]
            order = sorted([c for c in src if c["f"]["sharpe"] == c["f"]["sharpe"]],
                           key=lambda c: -c["f"]["sharpe"])
            ks = [kk for kk in TOP_CURVE_KS if kk <= len(order)]
            if order and len(order) not in ks:
                ks.append(len(order))
            curve = {}
            for kk in ks:
                ser, turn, _ = run_basket(order[:kk], cut, HOLD)
                nser = net(ser, turn)
                sv = sharpe(nser)
                if sv == sv:
                    curve[str(kk)] = {"net": round(sv, 3), "gross": round(sharpe(ser), 3),
                                      "cagr_pct": round(100 * cagr(nser), 1)}
            rec["top_curve"][fam] = {"n": len(order), "curve": curve}

        # how wide the band has to be before it changes anything
        rec["band_sweep"] = {}
        for fam in ("big", "risk"):
            src = sets[fam]
            if len(src) <= KS[-1]:
                continue
            arms = {}
            for b in BANDS:
                ser, turn, sw = run_index(src, KS[-1], cut, HOLD, lam, cal, band_fixed=b)
                nser = net(ser, turn, COPY_BP, sw, KS[-1])
                sv = sharpe(nser)
                if sv == sv:
                    if b is None:
                        lab = "derived"
                    elif b == "solved":
                        lab = "solved"
                    elif b == float("inf"):
                        lab = "never"
                    else:
                        lab = f"{1e4 * b:.0f}bp"
                    arms[lab] = {"net": round(sv, 3), "swaps": sw,
                                 "cagr_pct": round(100 * cagr(nser), 1)}
            rec["band_sweep"][fam] = arms
        out["dates"].append(rec)

    keys = sorted({k for d in out["dates"] for k in d["policies"]})
    for key in keys:
        vals = [d["policies"][key]["median"] for d in out["dates"] if key in d["policies"]]
        cag = [d["policies"][key].get("cagr_pct") for d in out["dates"] if key in d["policies"]]
        cag = [c for c in cag if c is not None]
        if len(vals) >= 2:
            out["summary"][key] = {"dates": len(vals), "mean": round(st.mean(vals), 3),
                                   "cagr_median": round(st.median(cag), 1) if cag else None,
                                   "median": round(st.median(vals), 3),
                                   "min": round(min(vals), 3), "max": round(max(vals), 3),
                                   "sd": round(st.pstdev(vals), 3) if len(vals) > 1 else 0.0,
                                   "positive": sum(1 for v in vals if v > 0)}
    # the top-k curve averaged across dates, which one date cannot resolve
    out["top_curve"] = {}
    for fam in ("open", "big"):
        agg = {}
        for d in out["dates"]:
            for kk, v in (d.get("top_curve", {}).get(fam, {}).get("curve") or {}).items():
                agg.setdefault(kk, []).append(v["net"])
        if agg:
            out["top_curve"][fam] = {kk: {"dates": len(v), "mean": round(st.mean(v), 3),
                                          "median": round(st.median(v), 3)}
                                     for kk, v in sorted(agg.items(), key=lambda t: int(t[0]))}
    # the band sweep averaged across dates
    out["band_sweep"] = {}
    for fam in ("big", "risk"):
        agg = {}
        for d in out["dates"]:
            for lab, v in (d.get("band_sweep", {}).get(fam) or {}).items():
                agg.setdefault(lab, {"net": [], "swaps": [], "cagr": []})
                agg[lab]["net"].append(v["net"])
                agg[lab]["swaps"].append(v["swaps"])
                agg[lab]["cagr"].append(v["cagr_pct"])
        if agg:
            out["band_sweep"][fam] = {lab: {"dates": len(v["net"]),
                                            "mean": round(st.mean(v["net"]), 3),
                                            "swaps": round(st.mean(v["swaps"]), 1),
                                            "cagr_median": round(st.median(v["cagr"]), 1)}
                                      for lab, v in agg.items()}

    # the paired questions, date by date
    wanted = []
    for k in KS:
        for fam in ("open", "risk", "big"):
            wanted.append((f"rank_gain_{fam}_{k}", f"{fam}_top_{k}", f"{fam}_random_{k}"))
        for fam in ("risk", "big"):
            wanted.append((f"screen_gain_{fam}_{k}", f"{fam}_random_{k}", f"open_random_{k}"))
            wanted.append((f"replace_gain_{fam}_{k}", f"{fam}_replace_{k}", f"{fam}_random_{k}"))
            wanted.append((f"index_gain_{fam}_{k}", f"{fam}_index_{k}", f"{fam}_random_{k}"))
            wanted.append((f"index_over_top_{fam}_{k}", f"{fam}_index_{k}", f"{fam}_top_{k}"))
            # the decomposition: what the ranking statistic costs, and what churn adds
            wanted.append((f"statistic_{fam}_{k}", f"{fam}_hold_index_{k}", f"{fam}_top_{k}"))
            wanted.append((f"churn_{fam}_{k}", f"{fam}_index_{k}", f"{fam}_hold_index_{k}"))
        wanted.append((f"all_gain_open_{k}", "open_all", f"open_random_{k}"))
        wanted.append((f"all_gain_big_{k}", "big_all", f"big_random_{k}"))
        wanted.append((f"all_gain_risk_{k}", "risk_all", f"risk_random_{k}"))
        for fam in ("open", "risk", "big"):
            wanted.append((f"spread_gain_{fam}_{k}", f"{fam}_random_{k}", f"{fam}_random_{KS[0]}"))
    for lab, a, b in wanted:
        pairs = [(d["policies"][a]["median"], d["policies"][b]["median"])
                 for d in out["dates"] if a in d["policies"] and b in d["policies"]]
        gpairs = [(d["policies"][a]["gross"], d["policies"][b]["gross"])
                  for d in out["dates"] if a in d["policies"] and b in d["policies"]]
        if len(pairs) >= 2:
            diff = [x - y for x, y in pairs]
            gdiff = [x - y for x, y in gpairs]
            cpairs = [(d["policies"][a].get("cagr_pct"), d["policies"][b].get("cagr_pct"))
                      for d in out["dates"] if a in d["policies"] and b in d["policies"]]
            cpairs = [(x, y) for x, y in cpairs if x is not None and y is not None]
            out["summary"][lab] = {"dates": len(diff), "mean": round(st.mean(diff), 3),
                                   "min": round(min(diff), 3), "max": round(max(diff), 3),
                                   "wins": sum(1 for d in diff if d > 0),
                                   "gross_mean": round(st.mean(gdiff), 3),
                                   "gross_wins": sum(1 for d in gdiff if d > 0)}
            if cpairs:
                out["summary"][lab]["cagr_median_a"] = round(st.median([x for x, _ in cpairs]), 1)
                out["summary"][lab]["cagr_median_b"] = round(st.median([y for _, y in cpairs]), 1)
                out["summary"][lab]["cagr_wins"] = sum(1 for x, y in cpairs if x > y)
    # How much of the table is the date and how much is the rule. A share of the
    # sum of squares is not the right statistic for this: with d dates and r
    # rules it rises with the number of levels even under pure noise, which is
    # how two grids of the same experiment came to disagree about the answer.
    # Two-factor analysis of variance with the degrees of freedom carried gives
    # a comparison that does not move with the shape of the table.
    cells = [(d["cut"], key, d["policies"][key]["median"]) for d in out["dates"] for key in d["policies"]]
    keys_all = sorted({c[1] for c in cells})
    dates_all = sorted({c[0] for c in cells})
    full = {(c[0], c[1]): c[2] for c in cells}
    balanced = [(dd, kk, full[(dd, kk)]) for dd in dates_all for kk in keys_all
                if (dd, kk) in full]
    if len(balanced) > 6 and len(dates_all) > 1 and len(keys_all) > 1:
        grand = st.mean([v for _, _, v in balanced])
        bydate, byrule = {}, {}
        for cut, key, v in balanced:
            bydate.setdefault(cut, []).append(v)
            byrule.setdefault(key, []).append(v)
        ss_tot = sum((v - grand) ** 2 for _, _, v in balanced)
        ss_date = sum(len(v) * (st.mean(v) - grand) ** 2 for v in bydate.values())
        ss_rule = sum(len(v) * (st.mean(v) - grand) ** 2 for v in byrule.values())
        ss_res = ss_tot - ss_date - ss_rule
        df_date = len(bydate) - 1
        df_rule = len(byrule) - 1
        df_res = len(balanced) - df_date - df_rule - 1
        ms_res = ss_res / df_res if df_res > 0 else float("nan")
        out["variance"] = {
            "cells": len(balanced), "dates": len(bydate), "rules": len(byrule),
            "pct_date": round(100 * ss_date / ss_tot, 1) if ss_tot else None,
            "pct_rule": round(100 * ss_rule / ss_tot, 1) if ss_tot else None,
            "df_date": df_date, "df_rule": df_rule, "df_residual": df_res,
            "f_date": round((ss_date / df_date) / ms_res, 2) if ms_res == ms_res and ms_res > 0 else None,
            "f_rule": round((ss_rule / df_rule) / ms_res, 2) if ms_res == ms_res and ms_res > 0 else None,
            # what each share would be under pure noise, which is the thing the
            # raw shares were being compared against without saying so
            "pct_date_under_noise": round(100 * df_date / (len(balanced) - 1), 1),
            "pct_rule_under_noise": round(100 * df_rule / (len(balanced) - 1), 1)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/or/policy.json")
    args = ap.parse_args(argv)
    snap_w, _, rows, _, _ = load_panel()
    out = {"seed": SEED, "hold": HOLD, "spacing": SPACING, "draws": DRAWS, "ks": list(KS),
           "detect_lag": DETECT_LAG, "switch_cost_bp": round(1e4 * SWITCH_COST, 1),
           "screen": {"worst_min": WORST_MIN, "vol_max": VOL_MAX, "acct_min": ACCT_MIN,
                      "silent_weeks": DEAD_WEEKS}}

    lam = weekly_hazard(rows)
    out["lambda_week"] = round(lam, 5)
    rng = random.Random(SEED)
    over = one_grid(rows, snap_w, SPACING, DATES, rng, lam)
    rng = random.Random(SEED)
    disj = one_grid(rows, snap_w, HOLD, 3, rng, lam)

    # the overlapping grid is the fuller picture; the disjoint grid carries the inference
    out.update({k: over[k] for k in ("dates", "summary", "variance", "top_curve", "band_sweep")
                if k in over})
    out["overlapping"] = {"spacing": SPACING, "summary": over["summary"],
                          "n_dates": len(over["dates"])}
    out["disjoint"] = {"spacing": HOLD, "summary": disj["summary"], "n_dates": len(disj["dates"]),
                       "variance_split": disj.get("variance"),
                       "dates": [{kk: d[kk] for kk in ("cut", "candidates", "screened", "median_age",
                                                       "stopped_in_hold", "ic_whole_pool", "sets",
                                                       "ic_inside")}
                                 for d in disj["dates"]],
                       "variance": disj.get("variance")}
    # a Newey-West t on the stitched difference between screening and not screening
    bench = bench_load()
    k = KS[-1]
    for lab, a, b in (("index_big", f"big_index_{k}", f"big_random_{k}"),
                      ("index_over_top_big", f"big_index_{k}", f"big_top_{k}"),
                      ("screen_big", f"big_random_{k}", f"open_random_{k}"),
                      ("screen_risk", f"risk_random_{k}", f"open_random_{k}"),
                      ("rank_open", f"open_top_{k}", f"open_random_{k}"),
                      ("rank_big", f"big_top_{k}", f"big_random_{k}")):
        diffs = [d["policies"][a]["median"] - d["policies"][b]["median"]
                 for d in disj["dates"] if a in d["policies"] and b in d["policies"]]
        # the stitched weekly difference over the disjoint windows: 3 x HOLD weeks
        rec = {"dates": len(diffs), "mean": round(st.mean(diffs), 3) if diffs else None,
               "wins": sum(1 for v in diffs if v > 0),
               "values": [round(v, 3) for v in diffs]}
        for tag, book in (("", disj["series"]), ("gross_", disj["series_gross"])):
            stitched = []
            for cut in sorted(book.get(a, {}), key=int):
                sa = book[a].get(cut) or []
                sb = book[b].get(cut) or []
                if len(sa) == len(sb) and sa:
                    stitched.extend(x - y for x, y in zip(sa, sb))
            if stitched:
                t = nw_tstat(stitched, 4)
                rec.update({f"{tag}weeks": len(stitched),
                            f"{tag}weekly_mean_bp": round(1e4 * st.mean(stitched), 1),
                            f"{tag}t_nw": round(t, 2) if t == t else None,
                            f"{tag}series": [round(v, 6) for v in stitched]})
        # what each arm's market exposure was, over the same weeks. The caveat
        # this answers is that a difference between two sets of leaders could be
        # a difference in beta; if the two betas agree, it is not.
        if bench:
            betas = {}
            for tag, arm in (("a", a), ("b", b)):
                ser, wks = [], []
                for cut in sorted(disj["series"].get(arm, {}), key=int):
                    block = disj["series"][arm][cut] or []
                    ser.extend(block)
                    wks.extend(range(int(cut) + 1, int(cut) + 1 + len(block)))
                reg = bench_regress(ser, wks, bench, "BTC") if ser else {}
                if reg:
                    betas[tag] = reg
            if len(betas) == 2:
                rec["beta_a"] = betas["a"]["beta"]
                rec["beta_b"] = betas["b"]["beta"]
                rec["beta_diff"] = round(betas["a"]["beta"] - betas["b"]["beta"], 3)
                rec["alpha_a_annual_pct"] = betas["a"]["alpha_annual_pct"]
                rec["alpha_b_annual_pct"] = betas["b"]["alpha_annual_pct"]
                rec["beta_weeks"] = betas["a"]["n"]
        out["disjoint"].setdefault("gains", {})[lab] = rec

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=1)
    print(f"wrote {args.out}: {len(out['dates'])} overlapping dates, {out['disjoint']['n_dates']} disjoint")
    print("variance split:", out.get("variance"))
    for key in sorted(out["summary"]):
        s = out["summary"][key]
        print(f"  {key:<22} mean {s['mean']:+.2f} sd {s.get('sd', 0):.2f} "
              f"({s['min']:+.2f} to {s['max']:+.2f}), {s.get('positive', 0)}/{s['dates']} positive")
    print("disjoint gains:")
    for lab, v in (out["disjoint"].get("gains") or {}).items():
        print(f"  {lab:<12} mean {v['mean']} wins {v['wins']}/{v['dates']} "
              f"weeks {v.get('weeks')} weekly {v.get('weekly_mean_bp')}bp t {v.get('t_nw')}")
    print("variance, overlapping grid:", out.get("variance"))
    print("variance, disjoint grid:", out["disjoint"].get("variance_split"))
    print("gains net vs gross:")
    for lab in sorted(out["summary"]):
        if "gain" in lab and lab.endswith(("_20",)):
            v = out["summary"][lab]
            print(f"  {lab:<24} net {v['mean']:+.3f} ({v['wins']}/{v['dates']})  "
                  f"gross {v.get('gross_mean'):+.3f} ({v.get('gross_wins')}/{v['dates']})")
    print("top-k curve (ordered, net, mean over dates):")
    for fam, v in out["top_curve"].items():
        print(f"  {fam}: " + "  ".join(f"k={kk}:{c['mean']:+.2f}" for kk, c in v.items()))
    print("band sweep (net Sharpe, mean over dates):")
    for fam, v in out["band_sweep"].items():
        print(f"  {fam}: " + "  ".join(f"{lab}:{c['mean']:+.2f}({c['swaps']:.0f}sw)"
                                       for lab, c in v.items()))
    print("decomposition at k=%d:" % KS[-1])
    for fam in ("big", "risk"):
        a = out["summary"].get(f"statistic_{fam}_{KS[-1]}")
        b = out["summary"].get(f"churn_{fam}_{KS[-1]}")
        c = out["summary"].get(f"index_over_top_{fam}_{KS[-1]}")
        if a and b and c:
            print(f"  {fam}: statistic {a['mean']:+.3f} + churn {b['mean']:+.3f} "
                  f"= {a['mean'] + b['mean']:+.3f}  (reported total {c['mean']:+.3f})")
    print("index rule, swaps and Sharpe by date:")
    for d in out["dates"]:
        c = d["policies"].get(f"big_index_{KS[-1]}")
        r = d["policies"].get(f"big_random_{KS[-1]}")
        t = d["policies"].get(f"big_top_{KS[-1]}")
        if c:
            print(f"  cut {d['cut']}: index {c['median']:+.2f} ({c['swaps']} swaps)  "
                  f"top {t['median']:+.2f}  random {r['median']:+.2f}  "
                  f"beta {d.get('shrinkage', {}).get('beta')}")
    print("IC by family, by date:", [d.get("ic_inside") for d in out["dates"]])
    print("set sizes by date:", [d.get("sets") for d in out["dates"]])
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
