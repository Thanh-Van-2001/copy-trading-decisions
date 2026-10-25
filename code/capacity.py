"""Does a leader's return decay as the capital behind him grows?

Copying is an injection of capital into someone else's strategy, so whether
that strategy has a capacity is a first-order question for the practice and
not a side issue. The mutual fund literature asks it of funds
\\citep{chen2004does,pastor2015scale}; on this venue the size of each account
is observable week by week, so it can be asked directly.

Three things make the naive answer wrong, and each is addressed here.

Flows. Equity moves when money is paid in or taken out, not only when trading
earns. The return used is the flow-adjusted one the paper already defines, and
the recomputation is checked against analysis.py's own output rather than
trusted to agree.

The market. The sample sits in a rising market, so a week in which everyone
earned would otherwise look like a week in which small accounts earned. Week
fixed effects remove it.

The mechanical bias. Equity is the cumulation of past returns, so regressing a
return on lagged equity inside a leader finds a negative coefficient even when
no capacity exists -- the bias Pastor, Stambaugh and Taylor identify for funds.
Rather than correct it analytically, the estimator is run on simulated leaders
who have no capacity at all, which measures the bias in exactly the quantity
being reported. The same device gives the paper its no-skill band elsewhere.

Writes out/or/capacity.json.
"""
import glob
import io
import json
import math
import os
import random
import sys

sys.path.insert(0, "or_journal")

import analysis as A                                            # noqa: E402

SEED = 20261025
SIMS = 400
MIN_WEEKS = 10            # a leader needs this many return weeks to carry a slope
EVENT_FRAC = 0.5          # an inflow above this share of equity is an event
EVENT_WIN = 4             # weeks compared either side of it
OUT = "out/or/capacity.json"


def panel_rows() -> tuple:
    """Per leader: weeks, flow-adjusted returns, starting equity, flows.

    Recomputed from the raw records because analysis.py keeps the flow only as
    a count, then checked against its returns so the two cannot diverge.
    """
    snap_w, nfiles, rows, drops, _ = A.load_panel()
    truth = {r["addr"]: r["rets"] for r in rows}

    out, checked, mismatch = {}, 0, 0
    for path in glob.glob(os.path.join(A.SRC, "*.json")):
        if path.endswith(("draw.json", "panel.json")):
            continue
        try:
            rec = json.load(io.open(path, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        av = pn = None
        for period, blk in rec.get("portfolio") or []:
            if period == "allTime":
                av = sorted((int(t), float(v))
                            for t, v in (blk.get("accountValueHistory") or []))
                pn = sorted((int(t), float(v))
                            for t, v in (blk.get("pnlHistory") or []))
        if not av or not pn:
            continue
        wav = {t // A.WEEK_MS: v for t, v in av}
        wpn = {t // A.WEEK_MS: v for t, v in pn}
        weeks = sorted(set(wav) & set(wpn))
        live = [w for w in weeks if wav[w] > A.DUST]
        if not live:
            continue
        recs = []
        for a, b in zip(weeks, weeks[1:]):
            if b - a != 1 or a not in live:
                continue
            dpnl = wpn[b] - wpn[a]
            flow = (wav[b] - wav[a]) - dpnl
            den = wav[a] + 0.5 * flow
            if den < A.RET_FLOOR or wav[a] < A.RET_FLOOR:
                continue
            ret = max(-1.0, min(A.CAP_UP, dpnl / den))
            recs.append({"week": b, "ret": ret, "equity": wav[a], "flow": flow})
        addr = rec["addr"]
        if addr in truth:
            for r in recs:
                if r["week"] in truth[addr]:
                    checked += 1
                    if abs(truth[addr][r["week"]] - r["ret"]) > 1e-12:
                        mismatch += 1
        if len(recs) >= MIN_WEEKS:
            out[addr] = recs
    assert checked, "nothing was cross-checked against analysis.py"
    assert not mismatch, f"{mismatch}/{checked} returns disagree with analysis.py"
    return out, snap_w, nfiles, checked


def two_way_beta(data: dict) -> dict:
    """OLS slope of return on log starting equity, leader and week demeaned.

    Vectorised: the nulls run this several hundred times over tens of
    thousands of leader-weeks, which pure Python cannot carry.
    """
    import numpy as np

    addrs, weeks, ys, xs = [], [], [], []
    for addr, recs in data.items():
        for r in recs:
            addrs.append(addr)
            weeks.append(r["week"])
            ys.append(r["ret"])
            xs.append(math.log(r["equity"]))
    if len(ys) < 50:
        return {}

    li = {a: i for i, a in enumerate(dict.fromkeys(addrs))}
    wi = {w: i for i, w in enumerate(dict.fromkeys(weeks))}
    lead = np.fromiter((li[a] for a in addrs), dtype=np.int64, count=len(addrs))
    week = np.fromiter((wi[w] for w in weeks), dtype=np.int64, count=len(weeks))
    y = np.asarray(ys, dtype=np.float64)
    x = np.asarray(xs, dtype=np.float64)

    nl, nw = len(li), len(wi)
    cl = np.bincount(lead, minlength=nl).astype(np.float64)
    cw = np.bincount(week, minlength=nw).astype(np.float64)

    def sweep(v: "np.ndarray") -> "np.ndarray":
        v = v - (np.bincount(lead, weights=v, minlength=nl) / cl)[lead]
        v = v - (np.bincount(week, weights=v, minlength=nw) / cw)[week]
        return v

    # alternate until neither fixed effect is left in
    for _ in range(12):
        y, x = sweep(y), sweep(x)

    sxx = float(x @ x)
    if sxx <= 0:
        return {}
    beta = float(x @ y) / sxx

    res = y - beta * x
    g = np.bincount(lead, weights=x * res, minlength=nl)
    meat = float(g @ g)
    se = math.sqrt(meat) / sxx if meat > 0 else float("nan")
    return {"beta": beta, "se": se,
            "t": beta / se if se == se and se else float("nan"),
            "obs": len(ys), "leaders": nl, "weeks": nw}


def null_band(data: dict, sims: int = SIMS, seed: int = SEED) -> dict:
    """The same slope on leaders who have no capacity, only compounding.

    Each simulated leader keeps a real leader's week indices, starting equity
    and return dispersion, and draws returns that are independent of his size.
    Whatever slope comes back is the estimator's own bias.
    """
    rng = random.Random(seed)
    shape = []
    for recs in data.values():
        rets = [r["ret"] for r in recs]
        mu = sum(rets) / len(rets)
        var = sum((v - mu) ** 2 for v in rets) / max(1, len(rets) - 1)
        shape.append(([r["week"] for r in recs], recs[0]["equity"],
                      mu, math.sqrt(max(var, 1e-12))))

    betas = []
    for _ in range(sims):
        sim = {}
        for i, (weeks, eq0, mu, sd) in enumerate(shape):
            eq, recs = eq0, []
            for w in weeks:
                r = rng.gauss(mu, sd)
                r = max(-0.99, min(A.CAP_UP, r))
                recs.append({"week": w, "ret": r, "equity": eq, "flow": 0.0})
                eq = max(A.RET_FLOOR, eq * (1.0 + r))
            sim[f"s{i}"] = recs
        fit = two_way_beta(sim)
        if fit:
            betas.append(fit["beta"])
    betas.sort()
    if not betas:
        return {}
    q = lambda p: betas[min(len(betas) - 1, int(p * len(betas)))]   # noqa: E731
    return {"sims": len(betas), "median": q(0.5),
            "low": q(0.025), "high": q(0.975),
            "mean": sum(betas) / len(betas)}


def permute_band(data: dict, sims: int = SIMS, seed: int = SEED) -> dict:
    """The strongest null available: a leader's own returns, reordered.

    The simulated band assumes a shape for the returns. This one assumes
    nothing. Each leader keeps the exact returns he earned and the exact weeks
    he traded; only their order is shuffled, so the equity path still
    compounds but cannot be related to the returns that follow it. Any slope
    left is mechanical by construction.
    """
    rng = random.Random(seed + 1)
    base = [(addr, [r["week"] for r in recs], recs[0]["equity"],
             [r["ret"] for r in recs]) for addr, recs in data.items()]
    betas = []
    for _ in range(sims):
        sim = {}
        for addr, weeks, eq0, rets in base:
            order = rets[:]
            rng.shuffle(order)
            eq, recs = eq0, []
            for w, r in zip(weeks, order):
                recs.append({"week": w, "ret": r, "equity": eq, "flow": 0.0})
                eq = max(A.RET_FLOOR, eq * (1.0 + r))
            sim[addr] = recs
        fit = two_way_beta(sim)
        if fit:
            betas.append(fit["beta"])
    betas.sort()
    if not betas:
        return {}
    q = lambda p: betas[min(len(betas) - 1, int(p * len(betas)))]   # noqa: E731
    return {"sims": len(betas), "median": q(0.5),
            "low": q(0.025), "high": q(0.975),
            "mean": sum(betas) / len(betas)}


def flow_event(data: dict) -> dict:
    """What happens to a leader's return after capital is paid in.

    A deposit moves size without being caused by the leader's recent returns
    the way compounding is, so the comparison either side of one is closer to
    the question a copier is actually asking.
    """
    before, after, n, leaders = [], [], 0, set()
    for addr, recs in data.items():
        by_week = {r["week"]: r for r in recs}
        for r in recs:
            if r["flow"] <= EVENT_FRAC * r["equity"]:
                continue
            w = r["week"]
            pre = [by_week[w - k]["ret"] for k in range(1, EVENT_WIN + 1)
                   if w - k in by_week]
            post = [by_week[w + k]["ret"] for k in range(1, EVENT_WIN + 1)
                    if w + k in by_week]
            if len(pre) < EVENT_WIN or len(post) < EVENT_WIN:
                continue
            before.append(sum(pre) / len(pre))
            after.append(sum(post) / len(post))
            n += 1
            leaders.add(addr)
    if n < 10:
        return {"events": n}
    diff = [b - a for a, b in zip(before, after)]
    mu = sum(diff) / len(diff)
    var = sum((d - mu) ** 2 for d in diff) / max(1, len(diff) - 1)
    se = math.sqrt(var / len(diff))
    return {"events": n, "leaders": len(leaders),
            "mean_before": sum(before) / len(before),
            "mean_after": sum(after) / len(after),
            "change": mu, "se": se,
            "t": mu / se if se else float("nan"),
            "window_weeks": EVENT_WIN, "inflow_threshold": EVENT_FRAC}


def main() -> int:
    data, snap_w, nfiles, checked = panel_rows()
    print(f"{len(data)} leaders with at least {MIN_WEEKS} return weeks "
          f"(of {nfiles} records); {checked} returns agree with analysis.py")

    fit = two_way_beta(data)
    assert fit, "the two-way estimator returned nothing"
    print(f"within-leader slope on log equity: {fit['beta']:+.5f} "
          f"(clustered t = {fit['t']:+.2f}) over {fit['obs']} leader-weeks")

    null = null_band(data)
    print(f"same estimator with no capacity present: median "
          f"{null['median']:+.5f}, central 95% "
          f"[{null['low']:+.5f}, {null['high']:+.5f}] over {null['sims']} runs")

    perm = permute_band(data)
    print(f"same estimator on his own returns reordered: median "
          f"{perm['median']:+.5f}, central 95% "
          f"[{perm['low']:+.5f}, {perm['high']:+.5f}] over {perm['sims']} runs")

    ev = flow_event(data)
    if ev.get("events", 0) >= 10:
        print(f"after an inflow above {int(100 * EVENT_FRAC)}% of equity "
              f"({ev['events']} events, {ev['leaders']} leaders): weekly return "
              f"{ev['mean_before']:+.4f} before vs {ev['mean_after']:+.4f} after, "
              f"change {ev['change']:+.4f} (t = {ev['t']:+.2f})")
    else:
        print(f"only {ev.get('events', 0)} inflow events: not enough to report")

    # Is the measured slope outside what no capacity at all would produce?
    # The distribution-free null is the one the finding rests on.
    verdict = ("inside" if perm["low"] <= fit["beta"] <= perm["high"]
               else "above" if fit["beta"] > perm["high"] else "below")
    print(f"against the reordered-returns null the measured slope lies {verdict}; "
          f"decay is {'weaker' if verdict == 'above' else 'stronger' if verdict == 'below' else 'no different'} "
          f"than compounding alone produces")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"leaders": len(data), "records_seen": nfiles,
               "returns_cross_checked": checked, "min_weeks": MIN_WEEKS,
               "within": fit, "null": null, "null_permuted": perm, "event": ev,
               "verdict_vs_null": verdict, "seed": SEED},
              io.open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
