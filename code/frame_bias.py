"""What two snapshots of the frame can say that one cannot.

The paper names two limits it could not measure with a single snapshot of the
venue's address list. This measures both, on the snapshot of 2026-10-05 and a
second taken on 2026-10-19.

First, the listing rule. An account that blew up and was delisted inside an
evaluation window is absent from a later snapshot rather than present and
stopped, so the survival curve estimated on one snapshot is an upper bound by an
amount nobody could bound. With two snapshots the addresses that left are
visible, and so is what they looked like before they left: if they are
concentrated at account values near zero, the rule is a value threshold and the
bias is small and measurable; if accounts with real equity disappear, it is not.

Second, the turnover proxy. The venue publishes lifetime volume as of a snapshot
rather than a series, so the paper charges a lifetime average at every decision
date and says that two snapshots would identify the volume traded between them.
Fourteen days do not bracket a twenty-six week evaluation window, so this does
not replace the proxy. It does something the paper could not do at all: measure
the volume these accounts actually traded over a window we observe exactly, and
compare it with what the proxy predicts for the same accounts over the same
window. The paper's mitigation rests on the claim that the overstatement is
concentrated in the unscreened pool rather than in the screened one. That claim
is testable here, and either it holds or the mitigation does not.

Usage: python or_journal/frame_bias.py [--out out/or/frame_bias.json]
"""
import argparse
import datetime as dt
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis import COPY_BP, MIN_NOTIONAL, features, load_panel, turnover  # noqa: E402
from policy import ACCT_MIN  # noqa: E402

S1 = ("data/hl_gold/leaderboard.parquet", "2026-10-05")
# pinned, so that a weekly collection job cannot move the manuscript's numbers.
# --latest overrides it, which is what a revision with a longer series wants.
S2 = ("data/hl_frames/leaderboard_2026-10-19.parquet", "2026-10-19")
DUST = 100.0          # the value under which an account holds nothing that matters


def q(xs: list, p: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    i = min(len(xs) - 1, max(0, int(p * len(xs))))
    return xs[i]


def listing(a, b) -> dict:
    """Who left the list, and what they were worth before they did."""
    left = a[~a["addr"].isin(set(b["addr"]))]
    joined = b[~b["addr"].isin(set(a["addr"]))]
    acct = left["acct"].tolist()
    # the boundary is the result, so it is reported rather than described
    below = a[a["acct"] < ACCT_MIN]
    below_left = below[~below["addr"].isin(set(b["addr"]))]
    above = a[a["acct"] >= ACCT_MIN]
    out = {"s1_rows": int(len(a)), "s2_rows": int(len(b)),
           "both": int(len(a) - len(left)), "left": int(len(left)),
           "joined": int(len(joined)),
           "left_pct": round(100.0 * len(left) / len(a), 3)}
    if acct:
        out.update({"left_acct_median": round(float(st.median(acct)), 2),
                    "left_under_dust": int(sum(1 for x in acct if x < DUST)),
                    "left_under_dust_pct": round(100.0 * sum(1 for x in acct if x < DUST) / len(acct), 1),
                    "left_acct_max": round(float(max(acct)), 2),
                    "left_over_acctmin": int(sum(1 for x in acct if x >= ACCT_MIN)),
                    "left_losers_pct": round(100.0 * float((left["pnl_all"] < 0).sum()) / len(left), 1),
                    "frame_losers_pct": round(100.0 * float((a["pnl_all"] < 0).sum()) / len(a), 1),
                    "below_acctmin": int(len(below)),
                    "below_acctmin_left": int(len(below_left)),
                    "above_acctmin": int(len(above)),
                    "above_acctmin_left_pct": round(100.0 * len(left) / max(1, len(above)), 2),
                    "left_acct_min": round(float(min(acct)), 2),
                    "frame_acct_median": round(float(a["acct"].median()), 1)})
    # the same question asked of the accounts that were actually drawn
    return out


def proxy_test(a, b, rows: list, snap_w: int, weeks: float) -> dict:
    """The proxy against the volume the same accounts actually traded.

    The proxy is the paper's own: lifetime volume divided by the account at the
    decision date and by the weeks the account has lived, capped where the paper
    caps it. The realised figure is the difference in lifetime volume between
    the two snapshots, over the weeks between them, divided by the same account
    value, so the two differ only in the numerator's span.
    """
    v1 = dict(zip(a["addr"], a["vlm_all"]))
    v2 = dict(zip(b["addr"], b["vlm_all"]))
    got = []
    for r in rows:
        ad = r["addr"].lower()
        if ad not in v1 or ad not in v2:
            continue
        f = features(r, snap_w)
        if not f or f.get("acct", 0.0) < MIN_NOTIONAL:
            continue
        dv = float(v2[ad]) - float(v1[ad])
        if dv < 0:                 # lifetime volume cannot fall; the row is bad
            continue
        actual = (dv / weeks) / f["acct"]
        pred = turnover(r, f, snap_w, snap_w)
        if pred is None or actual != actual:
            continue
        got.append({"addr": ad, "acct": f["acct"], "pred": pred, "actual": actual,
                    "big": f["acct"] >= ACCT_MIN})

    def block(sel: list, name: str) -> dict:
        """Every matched account counts, including the ones that traded nothing.

        A ratio cannot be formed when the realised figure is zero, and those are
        the accounts the proxy is most wrong about, so the headline statistic is
        the difference in turnover units and the ratio is reported beside it as
        what it is: a statistic conditioned on having traded."""
        if len(sel) < 10:
            return {"n": len(sel)}
        pr = [g["pred"] for g in sel]
        ac = [g["actual"] for g in sel]
        diff = [g["pred"] - g["actual"] for g in sel]
        traded = [g for g in sel if g["actual"] > 1e-9]
        ratio = [g["pred"] / g["actual"] for g in traded]
        zero = [g for g in sel if g["actual"] <= 1e-9]
        charged_nothing = [g for g in zero if g["pred"] > 1e-9]
        return {"n": len(sel),
                "pred_median": round(float(st.median(pr)), 3),
                "actual_median": round(float(st.median(ac)), 3),
                # the honest headline: over-charge in multiples of the account a week
                "excess_median": round(float(st.median(diff)), 3),
                "excess_p75": round(q(diff, 0.75), 2),
                "overstates_pct": round(100.0 * sum(1 for x in diff if x > 1e-9) / len(sel), 1),
                # and what that over-charge costs at the paper's own level
                "excess_bp_median": round(float(st.median(diff)) * COPY_BP, 1),
                "traded_nothing": len(zero),
                "traded_nothing_pct": round(100.0 * len(zero) / len(sel), 1),
                "charged_but_idle": len(charged_nothing),
                "charged_but_idle_pct": round(100.0 * len(charged_nothing) / len(sel), 1),
                # conditioned on having traded, which is what the first version
                # reported on its own and should not have
                "ratio_median_if_traded": round(float(st.median(ratio)), 2) if ratio else None,
                "ratio_p25_if_traded": round(q(ratio, 0.25), 2) if ratio else None,
                "ratio_p75_if_traded": round(q(ratio, 0.75), 2) if ratio else None}

    return {"weeks_between": round(weeks, 3),
            "all": block(got, "all"),
            "screened": block([g for g in got if g["big"]], "screened"),
            "unscreened": block([g for g in got if not g["big"]], "unscreened")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/or/frame_bias.json")
    ap.add_argument("--second", default=None,
                    help="path to the second snapshot; defaults to the pinned one")
    ap.add_argument("--latest", action="store_true",
                    help="use the newest snapshot on disk instead of the pinned one, "
                         "which is what a revision with a longer series wants")
    args = ap.parse_args(argv)
    import pandas as pd
    global S2
    if args.second:
        S2 = (args.second, os.path.basename(args.second).split("_")[-1].replace(".parquet", ""))
    elif args.latest:
        files = sorted(f for f in os.listdir(os.path.dirname(S2[0]))
                       if f.startswith("leaderboard_") and f.endswith(".parquet"))
        if files:
            S2 = (os.path.join(os.path.dirname(S2[0]), files[-1]),
                  files[-1].split("_")[-1].replace(".parquet", ""))
    for path, _ in (S1, S2):
        if not os.path.exists(path):
            print(f"missing {path}")
            return 1
    a = pd.read_parquet(S1[0], columns=["addr", "acct", "pnl_all", "vlm_all"])
    b = pd.read_parquet(S2[0], columns=["addr", "acct", "pnl_all", "vlm_all"])
    a["addr"] = a["addr"].str.lower()
    b["addr"] = b["addr"].str.lower()
    days = (dt.date.fromisoformat(S2[1]) - dt.date.fromisoformat(S1[1])).days
    snap_w, n_files, rows, drops, grid = load_panel()

    res = {"dates": [S1[1], S2[1]], "days_between": days,
           "listing": listing(a, b),
           "turnover": proxy_test(a, b, rows, snap_w, days / 7.0)}
    # and the same listing question restricted to the addresses that were drawn
    drawn = {r["addr"].lower() for r in rows}
    res["listing"]["panel_drawn"] = len(drawn)
    res["listing"]["panel_left"] = len(drawn - set(b["addr"]))
    res["listing"]["panel_left_pct"] = round(
        100.0 * len(drawn - set(b["addr"])) / max(1, len(drawn)), 2)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(res, open(args.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
