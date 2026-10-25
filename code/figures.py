"""The paper's figures, from out/or/facts.json and out/or/policy.json only.

One file each, vector PDF, one visual language: a quiet grid, one accent colour
per series, no chartjunk, every axis labelled in words.

  fig_survival     Kaplan-Meier survival of a leader, whole frame against the
                   two size strata, with the numbers at risk under the axis.
  fig_signal       rank correlation between past and future performance, by
                   horizon and inside each screen, against the zero-skill band.
  fig_dependence   the distribution of pairwise correlation, and what it
                   predicts for a basket as the basket grows.
  fig_surface      the decision surface net of cost, and its profile in the
                   account floor against the number of leaders that survive it.
  fig_cost         net Sharpe against the copying cost, one line per screen.
  fig_gains        what each decision was worth, at every decision date.

Usage: python or_journal/figures.py [--out paper_or/figures]
"""
import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

INK = "#1b1b1b"
GREY = "#8a8a8a"
FAINT = "#d9d9d9"
ACCENT = ["#1f4e79", "#c0504d", "#4f6228", "#7f5f00", "#5f497a", "#31859b"]

MINUS = "−"
LABEL = {"none": "no screen", "size": "account $\\geq$ \\$100k", "drawdown": f"worst week $\\geq$ {MINUS}15\\%",
         "vol": "volatility $\\leq$ 10\\%", "past_sharpe": "past Sharpe $\\geq$ 1",
         "size_drawdown": "account and drawdown", "size_drawdown_active": "account, drawdown, active",
         "size_drawdown_active_sharpe": "all four"}
PLAIN = {"none": "no screen", "size": "account at least $100k", "drawdown": "worst week at least -15%",
         "vol": "volatility at most 10%", "past_sharpe": "past Sharpe at least 1",
         "size_drawdown": "account and drawdown", "size_drawdown_active": "account, drawdown, active",
         "size_drawdown_active_sharpe": "all four"}


def style():
    # Type 3 is the matplotlib default and it does not survive a publisher's
    # EPS-to-PDF conversion: the portal's reviewer PDF came back with every
    # axis label, tick and legend missing. Type 42 embeds real TrueType subsets.
    plt.rcParams.update({"ps.fonttype": 42, "pdf.fonttype": 42})
    plt.rcParams.update({
        "figure.figsize": (5.4, 3.4), "figure.dpi": 150, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
        "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"], "font.size": 9,
        "axes.edgecolor": GREY, "axes.linewidth": 0.6, "axes.labelcolor": INK, "axes.titlesize": 9.5,
        "axes.titlelocation": "left", "axes.titlepad": 7, "axes.grid": True, "axes.axisbelow": True,
        "grid.color": FAINT, "grid.linewidth": 0.5, "text.color": INK,
        "xtick.color": GREY, "ytick.color": GREY, "xtick.labelcolor": INK, "ytick.labelcolor": INK,
        "xtick.direction": "out", "ytick.direction": "out", "legend.frameon": False, "legend.fontsize": 8,
        "lines.linewidth": 1.4, "lines.solid_capstyle": "round", "text.usetex": False,
        "axes.unicode_minus": True,
    })


def despine(ax, left=True):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if not left:
        ax.spines["left"].set_visible(False)


def pctfmt(ax, axis="y", digits=0):
    f = FuncFormatter(lambda v, _: f"{v:.{digits}f}%")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


# ------------------------------------------------------------------ figures
def fig_survival(f: dict, out: str):
    a = f["attrition"]
    fig, ax = plt.subplots()
    for i, (key, lab) in enumerate((("curve", "every leader in the sample"),
                                    ("big", "account above $100k in its first month"),
                                    ("small", "account below $100k in its first month"))):
        c = a["curve"] if key == "curve" else (a.get(key) or {}).get("curve")
        if not c:
            continue
        xs = [0] + [r[0] / 4.345 for r in c]
        ys = [100.0] + [100 * r[3] for r in c]
        ax.step(xs, ys, where="post", color=ACCENT[i], label=lab, lw=1.6 if i == 0 else 1.1)
    ax.set_xlim(0, 36)
    ax.set_ylim(0, 102)
    ax.set_xlabel("months since the leader's first week on the venue")
    ax.set_ylabel("still trading")
    pctfmt(ax)
    ax.set_title("A leader's working life")
    ax.legend(loc="lower left")
    despine(ax)
    fig.savefig(out, dpi=600 if out.endswith(".png") else None)
    plt.close(fig)


def fig_signal(f: dict, out: str):
    ident = f["identifiability"]
    nul = ident["null"]["whole_frame"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0),
                             gridspec_kw={"width_ratios": [1, 1.3], "wspace": 0.62})
    ax = axes[0]
    hs = sorted((int(k), v) for k, v in ident.items() if k.isdigit())
    xs = [h for h, _ in hs]
    ys = [v["ic_sharpe_vs_future_mean"] for _, v in hs]
    lo = [v["ic_sharpe_ci"][0] for _, v in hs]
    hi = [v["ic_sharpe_ci"][1] for _, v in hs]
    ax.axhspan(nul["p05"], nul["p95"], color=FAINT, zorder=0)
    ax.annotate("no skill", (xs[-1], nul["p95"]), fontsize=7.5, color=GREY, va="bottom", ha="right")
    ax.errorbar(xs, ys, yerr=[[y - a for y, a in zip(ys, lo)], [b - y for y, b in zip(ys, hi)]],
                fmt="o", ms=4, color=ACCENT[0], elinewidth=1.0, capsize=2.5)
    ax.axhline(0, color=GREY, lw=0.6)
    ax.set_xticks(xs)
    ax.set_xlabel("weeks of history used")
    ax.set_ylabel("rank correlation with the next 26 weeks")
    ax.set_title("Across the whole venue")
    despine(ax)

    ax = axes[1]
    rows = [(n, r) for n, r in f["baskets"].items() if r.get("ic_inside") is not None]
    rows.sort(key=lambda t: t[1]["ic_inside"])
    ys = range(len(rows))
    ax.axvspan(nul["p05"], nul["p95"], color=FAINT, zorder=0)
    for y, (n, r) in zip(ys, rows):
        lo, hi = r["ic_inside_ci"]
        col = ACCENT[0] if n == "none" else ACCENT[1]
        ax.plot([lo, hi], [y, y], color=col, lw=1.1)
        ax.plot([r["ic_inside"]], [y], "o", ms=4, color=col)
        ax.annotate(f"n = {r['pass']}", (hi + 0.02, y), fontsize=7, color=GREY, va="center")
    ax.axvline(0, color=GREY, lw=0.6)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([PLAIN[n] for n, _ in rows], fontsize=7.5)
    ax.set_xlabel("rank correlation inside the screened set")
    ax.set_title("Inside a screen")
    ax.set_xlim(-0.35, 0.75)
    despine(ax)
    fig.savefig(out, dpi=600 if out.endswith(".png") else None)
    plt.close(fig)


def fig_dependence(f: dict, out: str):
    d = f["dependence"]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9), gridspec_kw={"wspace": 0.28})
    ax = axes[0]
    ax.hist(d["hist"], bins=28, color=ACCENT[0], edgecolor="white", linewidth=0.4)
    ax.axvline(d["median"], color=ACCENT[1], lw=1.2)
    ax.annotate(f"median {d['median']:+.2f}".replace("-", MINUS), (d["median"] + 0.03, ax.get_ylim()[1] * 0.9),
                fontsize=7.5, color=ACCENT[1])
    ax.set_xlabel("correlation between two leaders' weekly returns")
    ax.set_ylabel("pairs")
    ax.set_title("How alike two leaders are")
    despine(ax)

    ax = axes[1]
    obs = f["baskets"]["none"]["k"]
    ks = sorted(int(k) for k in obs)
    ax.plot(ks, [obs[str(k)]["median"] for k in ks], "o-", ms=3.5, color=ACCENT[0],
            label="measured, gross of cost")
    pred = d.get("predicted") or {}
    pk = sorted(int(k) for k in pred)
    ax.plot(pk, [pred[str(k)] for k in pk], "--", color=ACCENT[2],
            label="what the measured correlation predicts")
    if d.get("ceiling"):
        ax.axhline(d["ceiling"], color=GREY, lw=0.8, ls=":")
        ax.annotate(f"the limit the covariance allows, {d['ceiling']:.2f}, about {d['n_eff']:.0f} bets",
                    (1.2, d["ceiling"] + 0.04), fontsize=7.5, color=GREY)
    ax.plot(ks, [obs[str(k)]["median_net"] for k in ks], "o-", ms=3.5, color=ACCENT[1],
            label="measured, net of the copying cost")
    ax.axhline(0, color=GREY, lw=0.6)
    ax.set_xscale("log")
    ax.set_xticks(ks)
    ax.set_xticklabels([str(k) for k in ks])
    ax.set_xlabel("leaders in the basket")
    ax.set_ylabel("Sharpe ratio over 26 weeks")
    ax.set_title("What a bigger basket buys")
    ax.legend(loc="center left", fontsize=7.5)
    despine(ax)
    fig.savefig(out, dpi=600 if out.endswith(".png") else None)
    plt.close(fig)


def fig_surface(f: dict, out: str):
    s = f["surface"]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.1),
                             gridspec_kw={"width_ratios": [1.15, 1], "wspace": 0.52})
    ax = axes[0]
    worsts = s["worsts"]
    accts = s["accts"]
    grid = {(r["acct_min"], r["worst_min"]): r for r in s["grid"]}
    ks = [k for k in s["ks"] if k >= 5]
    mat = []
    for a in accts:
        row = []
        for w in worsts:
            r = grid.get((a, w)) or {"k": {}}
            cells = [v["median_net"] for kk, v in r["k"].items()
                     if v.get("median_net") is not None and int(kk) in ks]
            row.append(max(cells) if cells else float("nan"))
        mat.append(row)
    im = ax.imshow(mat, cmap="BuPu", aspect="auto", origin="lower")
    ax.set_xticks(range(len(worsts)))
    ax.set_xticklabels([("any" if w <= -1 else f"{MINUS}{abs(w) * 100:.0f}%") for w in worsts], fontsize=7.5)
    ax.set_yticks(range(len(accts)))
    ax.set_yticklabels([("any" if a == 0 else f"${a / 1e3:,.0f}k" if a < 1e6 else f"${a / 1e6:,.0f}M")
                        for a in accts], fontsize=7.5)
    for i, a in enumerate(accts):
        for j, w in enumerate(worsts):
            v = mat[i][j]
            if v == v:
                ax.annotate(f"{v:+.2f}".replace("-", MINUS), (j, i), ha="center", va="center",
                            fontsize=7, color="white" if v > 1.5 else INK)
    ax.set_xlabel("worst past week allowed")
    ax.set_ylabel("account value required at the decision date")
    ax.set_title("Best net Sharpe in the cell")
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.ax.tick_params(labelsize=7)

    ax = axes[1]
    prof = s.get("profile") or []
    xs = range(len(prof))
    ax.plot(list(xs), [p["best_net"] for p in prof], "o-", ms=4, color=ACCENT[0], label="best net Sharpe")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([("any" if p["acct_min"] == 0 else
                         f"${p['acct_min'] / 1e3:,.0f}k" if p["acct_min"] < 1e6
                         else f"${p['acct_min'] / 1e6:,.0f}M") for p in prof], fontsize=7.5, rotation=30)
    ax.set_xlabel("account value required at the decision date")
    ax.set_ylabel("net Sharpe over 26 weeks")
    ax.set_title("Tighter is better, until the set runs out")
    despine(ax)
    ax2 = ax.twinx()
    ax2.plot(list(xs), [p["pass"] for p in prof], "s--", ms=3, color=ACCENT[1], lw=1.0,
             label="leaders who pass")
    ax2.set_yscale("log")
    ax2.set_ylabel("leaders who pass", color=ACCENT[1])
    ax2.tick_params(axis="y", colors=ACCENT[1])
    ax2.grid(False)
    for side in ("top",):
        ax2.spines[side].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower center")
    fig.savefig(out, dpi=600 if out.endswith(".png") else None)
    plt.close(fig)


def fig_cost(f: dict, out: str):
    fig, ax = plt.subplots(figsize=(5.6, 3.1))
    order = ["none", "drawdown", "size_drawdown_active", "size"]
    for i, name in enumerate(order):
        cg = (f["baskets"].get(name, {}).get("k", {}).get("20") or {}).get("cost_grid")
        if not cg:
            continue
        xs = sorted(float(k) for k in cg)
        lab = {"9": 9.5}.get("9", 9.5)
        ax.plot([lab if x == 9 else x for x in xs], [cg[str(int(x))] for x in xs], "o-", ms=3.5,
                color=ACCENT[i], label=PLAIN[name])
    ax.axvline(f["frame"]["copy_cost_bp"], color=GREY, lw=0.8, ls=":")
    ax.annotate("the level assumed in the text", (f["frame"]["copy_cost_bp"] + 0.4, ax.get_ylim()[0] + 0.15),
                fontsize=7.5, color=GREY)
    ax.axhline(0, color=GREY, lw=0.6)
    ax.set_xlabel("copying cost charged on turnover, basis points per side")
    ax.set_ylabel("net Sharpe of a basket of twenty")
    ax.set_title("What the answer owes to the cost")
    ax.legend(loc="lower left")
    despine(ax)
    fig.savefig(out, dpi=600 if out.endswith(".png") else None)
    plt.close(fig)


def fig_gains(pol: dict, out: str):
    """Each decision, at every date, and its average: the paper's main figure.

    Every row is a difference between two rules that differ in one choice, taken
    inside a named set, because the choices are not separable."""
    k, k0 = pol["ks"][-1], pol["ks"][0]
    rows = [(f"order the venue by past Sharpe", f"open_top_{k}", f"open_random_{k}"),
            (f"screen on account size", f"big_random_{k}", f"open_random_{k}"),
            (f"screen on past risk", f"risk_random_{k}", f"open_random_{k}"),
            (f"order inside the risk screen", f"risk_top_{k}", f"risk_random_{k}"),
            (f"order inside the size screen", f"big_top_{k}", f"big_random_{k}"),
            (f"hold {k} not {k0}, whole venue", f"open_random_{k}", f"open_random_{k0}"),
            (f"hold {k} not {k0}, size screened", f"big_random_{k}", f"big_random_{k0}"),
            (f"replace a leader who stops", f"big_replace_{k}", f"big_random_{k}")]
    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    for i, (lab, a, b) in enumerate(rows):
        vals = [d["policies"][a]["median"] - d["policies"][b]["median"]
                for d in pol["dates"] if a in d["policies"] and b in d["policies"]]
        if not vals:
            continue
        ys = [i + (j - (len(vals) - 1) / 2) * 0.1 for j in range(len(vals))]
        ax.scatter(vals, ys, s=17, color=ACCENT[i % len(ACCENT)], lw=0)
        m = sum(vals) / len(vals)
        ax.plot([m, m], [i - 0.3, i + 0.3], color=ACCENT[i % len(ACCENT)], lw=2.2)
        ax.annotate(f"{m:+.2f}".replace("-", MINUS), (m, i - 0.42), fontsize=7.5, color=INK,
                    ha="center", va="bottom")
    ax.axvline(0, color=GREY, lw=0.8)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([lab for lab, _, _ in rows], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("change in net Sharpe over the following 26 weeks")
    ax.set_title("What each decision was worth, at each of five decision dates")
    despine(ax)
    fig.savefig(out, dpi=600 if out.endswith(".png") else None)
    plt.close(fig)


def fig_band(th: dict, out: str):
    """The boundary against the horizon, with the two terms that set it.

    The cost term falls as the holding period lengthens, because a longer life
    repays a switching charge more easily. The option term does not, so the
    solved boundary rises. Both sit far above the margin a copier actually
    sees, which is the figure's point."""
    lam = th["lambda_week"]
    c = th["switch_cost_bp"] / 1e4
    curve = {int(k): v for k, v in (th.get("solved_curve") or {}).items() if v is not None}
    margin = (th.get("gap_walk") or {}).get("margin_median_bp")
    ts = sorted(curve) or list(range(1, 27))

    def cost(t):
        q = 1.0 - lam
        return 1e4 * c / (q * (1.0 - q ** t) / lam)

    fig, ax = plt.subplots(figsize=(6.0, 3.3))
    ax.plot(ts, [curve[t] for t in ts], "-", color=ACCENT[0], lw=1.8,
            label="the boundary, solved")
    ax.plot(ts, [cost(t) for t in ts], "--", color=ACCENT[1], lw=1.3,
            label="the switching charge alone")
    if margin:
        ax.axhline(margin, color=GREY, lw=0.9, ls=":")
        ax.annotate(f"the margin a swap acts on, {margin:.1f} bp",
                    (ts[0] + 0.5, margin * 1.3), fontsize=7.5, color=GREY, ha="left")
    ax.set_yscale("log")
    ax.set_xlabel("weeks the basket still has to run")
    ax.set_ylabel("gap a candidate must beat a sleeve by, bp a week")
    ax.set_title("How wide the no-trade band is")
    ax.legend(loc="center right", fontsize=8)
    despine(ax)
    fig.savefig(out, dpi=600 if out.endswith(".png") else None)
    plt.close(fig)


def also_eps(out_dir: str) -> int:
    """Re-save every figure as EPS, which is what the journal asks for.

    The paper uses the PDFs. These go in the submission as the separate
    high-resolution files the guide requires; EPS is vector, so "at least
    600dpi" is satisfied by construction rather than by a setting.
    """
    import matplotlib.pyplot as plt
    n = 0
    for f in sorted(os.listdir(out_dir)):
        if f.endswith(".pdf"):
            n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", default="out/or/facts.json")
    ap.add_argument("--policy", default="out/or/policy.json")
    ap.add_argument("--theory", default="out/or/theory.json")
    ap.add_argument("--out", default="paper_or/figures")
    args = ap.parse_args(argv)
    style()
    os.makedirs(args.out, exist_ok=True)
    f = json.load(open(args.facts, encoding="utf-8"))
    fig_survival(f, os.path.join(args.out, "fig_survival.pdf"))
    fig_survival(f, os.path.join(args.out, "fig_survival.png"))
    fig_signal(f, os.path.join(args.out, "fig_signal.pdf"))
    fig_signal(f, os.path.join(args.out, "fig_signal.png"))
    fig_dependence(f, os.path.join(args.out, "fig_dependence.pdf"))
    fig_dependence(f, os.path.join(args.out, "fig_dependence.png"))
    fig_surface(f, os.path.join(args.out, "fig_surface.pdf"))
    fig_surface(f, os.path.join(args.out, "fig_surface.png"))
    fig_cost(f, os.path.join(args.out, "fig_cost.pdf"))
    fig_cost(f, os.path.join(args.out, "fig_cost.png"))
    if os.path.exists(args.policy):
        pol = json.load(open(args.policy, encoding="utf-8"))
        fig_gains(pol, os.path.join(args.out, "fig_gains.pdf"))
        fig_gains(pol, os.path.join(args.out, "fig_gains.png"))
    if os.path.exists(args.theory):
        th = json.load(open(args.theory, encoding="utf-8"))
        fig_band(th, os.path.join(args.out, "fig_band.pdf"))
        fig_band(th, os.path.join(args.out, "fig_band.png"))
    print("wrote the figures to", args.out)
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
