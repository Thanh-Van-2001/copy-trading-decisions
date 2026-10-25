"""The three measurements the model rests on, on the stated frame.

Returns are deposit-neutral: the change in the account's cumulative PnL over a
week, divided by the account value at the start of that week, so a deposit or a
withdrawal does not read as a return.

  1. Survival: how long a leader keeps trading (Kaplan-Meier, censored at the
     snapshot), and the monthly hazard by account size.
  2. Identifiability: does past performance rank future performance? Spearman
     between a wallet's first-half and second-half mean weekly return, and
     between an early window and the next 4 / 13 weeks.
  3. Diversification: the distribution of pairwise correlations, and the Sharpe
     of an equally weighted basket of k leaders drawn at random, with and
     without the deaths.

Usage: python or_journal/facts.py
"""
import glob
import json
import math
import os
import random
import statistics as st

SRC = "data/hl_panel"
WEEK_MS = 7 * 24 * 3600 * 1000
DUST = 100.0
MIN_WEEKS = 8


def load() -> tuple:
    files = [f for f in glob.glob(os.path.join(SRC, "*.json")) if not f.endswith(("draw.json", "panel.json"))]
    snap = 0
    recs = []
    for f in files:
        try:
            rec = json.load(open(f, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        av = pn = None
        for period, blk in rec.get("portfolio") or []:
            if period == "allTime":
                av = sorted((int(t), float(v)) for t, v in (blk.get("accountValueHistory") or []))
                pn = sorted((int(t), float(v)) for t, v in (blk.get("pnlHistory") or []))
        if not av or not pn:
            continue
        snap = max(snap, av[-1][0])
        recs.append((rec, av, pn))
    return snap, recs


def weekly(path: list) -> dict:
    """week bucket -> last value in that bucket"""
    out = {}
    for t, v in path:
        out[t // WEEK_MS] = v
    return out


def wallet_rows(snap: int, recs: list) -> list:
    rows = []
    for rec, av, pn in recs:
        wav, wpn = weekly(av), weekly(pn)
        weeks = sorted(set(wav) & set(wpn))
        live = [w for w in weeks if wav[w] > DUST]
        if not live:
            continue
        birth, last = live[0], live[-1]
        stale = (snap // WEEK_MS) - last
        rets = {}
        for a, b in zip(live, live[1:]):
            if b - a == 1 and wav[a] > DUST:
                rets[b] = (wpn[b] - wpn[a]) / wav[a]
        rows.append({"addr": rec["addr"], "acct0": rec.get("frame", {}).get("acct", 0.0),
                     "birth": birth, "last": last, "age_weeks": last - birth,
                     "dead": stale > 4, "stale": stale, "rets": rets,
                     "acct_last": wav[last]})
    return rows


def km(rows: list) -> list:
    obs = sorted((r["age_weeks"], r["dead"]) for r in rows)
    n = len(obs)
    surv, at_risk, out = 1.0, n, []
    i = 0
    while i < n:
        t = obs[i][0]
        d = tied = 0
        while i < n and obs[i][0] == t:
            d += obs[i][1]
            tied += 1
            i += 1
        if at_risk > 0 and d:
            surv *= 1 - d / at_risk
        out.append((t, at_risk, d, surv))
        at_risk -= tied
    return out


def surv_at(curve: list, week: float) -> float:
    s = 1.0
    for t, _, _, v in curve:
        if t <= week:
            s = v
        else:
            break
    return s


def spearman(xs: list, ys: list) -> float:
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    if len(xs) < 3:
        return float("nan")
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def corr(a: dict, b: dict) -> float:
    ks = sorted(set(a) & set(b))
    if len(ks) < 8:
        return float("nan")
    x = [a[k] for k in ks]
    y = [b[k] for k in ks]
    mx, my = st.mean(x), st.mean(y)
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if not sx or not sy:
        return float("nan")
    return sum((u - mx) * (v - my) for u, v in zip(x, y)) / (sx * sy)


def sharpe(series: list) -> float:
    if len(series) < 8:
        return float("nan")
    m, s = st.mean(series), st.pstdev(series)
    return m / s * math.sqrt(52) if s else float("nan")


def main() -> int:
    snap, recs = load()
    rows = wallet_rows(snap, recs)
    usable = [r for r in rows if len(r["rets"]) >= MIN_WEEKS]
    print(f"frame draw: {len(recs)} addresses fetched, {len(rows)} with a path, {len(usable)} with >= {MIN_WEEKS} weekly returns")
    dead = sum(r["dead"] for r in rows)
    print(f"dead at the snapshot (no movement for over four weeks): {dead} of {len(rows)} = {100*dead/len(rows):.1f}%")

    # 1. survival
    curve = km(rows)
    print("\n1. SURVIVAL of a leader, from the first week with money in the account")
    for mo in (1, 3, 6, 12, 24):
        print(f"   {mo:>2} months: {100*surv_at(curve, 4.33*mo):5.1f}% still trading")
    s6, s12 = surv_at(curve, 26), surv_at(curve, 52)
    print(f"   monthly hazard: {100*(1-s6**(1/6)):.1f}% over the first six months, {100*(1-s12**(1/12)):.1f}% over a year")
    big = [r for r in rows if r["acct0"] >= 1e5]
    small = [r for r in rows if r["acct0"] < 1e5]
    for lab, grp in (("account >= $100k", big), ("account < $100k", small)):
        if len(grp) > 30:
            c = km(grp)
            print(f"   {lab}: {100*surv_at(c, 26):.1f}% alive at 6 months, {100*surv_at(c, 52):.1f}% at a year (n={len(grp)})")

    # 2. identifiability
    print("\n2. IDENTIFIABILITY of a leader's skill")
    half = [(st.mean([v for k, v in r["rets"].items() if k <= (r['birth']+r['last'])//2]),
             st.mean([v for k, v in r["rets"].items() if k > (r['birth']+r['last'])//2]))
            for r in usable
            if len([v for k, v in r["rets"].items() if k <= (r['birth']+r['last'])//2]) >= 4
            and len([v for k, v in r["rets"].items() if k > (r['birth']+r['last'])//2]) >= 4]
    if half:
        print(f"   first half vs second half mean weekly return: Spearman {spearman([a for a,_ in half],[b for _,b in half]):+.3f} (n={len(half)})")
    snap_w = snap // WEEK_MS
    for horizon in (4, 13, 26):
        cut = snap_w - horizon
        pairs = []
        for r in usable:
            past = [v for k, v in r["rets"].items() if k <= cut]
            fut = [v for k, v in r["rets"].items() if k > cut]
            if len(past) >= 8 and len(fut) >= max(2, horizon // 2):
                pairs.append((sharpe(past), st.mean(fut)))
        pairs = [(a, b) for a, b in pairs if a == a]
        if len(pairs) > 20:
            print(f"   Sharpe up to week -{horizon} vs mean return of the last {horizon} weeks: "
                  f"Spearman {spearman([a for a,_ in pairs],[b for _,b in pairs]):+.3f} (n={len(pairs)})")

    # 3. diversification
    print("\n3. DIVERSIFICATION")
    rng = random.Random(7)
    pool = [r for r in usable if not r["dead"]]
    cs = []
    for _ in range(4000):
        a, b = rng.sample(usable, 2)
        c = corr(a["rets"], b["rets"])
        if c == c:
            cs.append(c)
    cs.sort()
    print(f"   pairwise correlation of weekly returns: median {st.median(cs):+.3f}, "
          f"quartiles {cs[len(cs)//4]:+.3f} / {cs[3*len(cs)//4]:+.3f}, share above +0.5: {100*sum(1 for c in cs if c > 0.5)/len(cs):.1f}% (n={len(cs)} pairs)")
    print("   Sharpe of an equally weighted basket of k leaders drawn at random (median of 400 draws)")
    print("   k | all leaders | still-alive leaders only")
    for k in (1, 3, 5, 10, 20, 40):
        out = {}
        for lab, src in (("all", usable), ("alive", pool)):
            if len(src) < k:
                out[lab] = float("nan")
                continue
            vals = []
            for _ in range(400):
                pick = rng.sample(src, k)
                weeks = sorted({w for r in pick for w in r["rets"]})
                ser = []
                for w in weeks:
                    xs = [r["rets"][w] for r in pick if w in r["rets"]]
                    if len(xs) >= max(1, k // 2):
                        ser.append(st.mean(xs))
                s = sharpe(ser)
                if s == s:
                    vals.append(s)
            out[lab] = st.median(vals) if vals else float("nan")
        print(f"  {k:>2} | {out['all']:11.2f} | {out['alive']:24.2f}")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
