"""How large should the basket be, once leaders die and move together?

Proposition 1 says a basket drawn without discrimination should be as large as
the screen allows. That is true and nearly useless, because it does not say how
fast the gain arrives, and the paper measures the gain from holding twenty
rather than five to be nothing at all. Something has to give.

This prices the theory so the disagreement can be read. Under equal weights,
independent stopping and an equicorrelation among the leaders who are still
trading, the basket's Sharpe ratio has a closed form whose level is set by one
leader and whose shape is set by two measured quantities. Calibrating the level
at k = 1 and letting the model predict the shape turns Proposition 1 into a
falsifiable number for every k the paper evaluated.

Two results fall out before any comparison. Mortality does not lower the
ceiling that diversification can reach, only the rate of approach to it, so a
copier facing attrition should hold more leaders rather than fewer. And the
count needed to reach most of that ceiling is far above any basket the paper
holds.

Writes out/or/sizing.json.
"""
import io
import json
import math
import os
import sys

FACTS = "out/or/facts.json"
OUT = "out/or/sizing.json"
WEEKS_PER_MONTH = 52.0 / 12.0
TARGET = 0.9              # the fraction of the ceiling we report a count for
SCREEN = "none"           # the unscreened pool: Proposition 1's own setting


def moments(f: dict) -> dict:
    """The three inputs the closed form needs, all already measured."""
    d = f["dependence"]
    var_bar = float(d["var_bar"])            # mean weekly variance of a leader
    cov_bar = float(d["cov_bar"])            # mean weekly covariance of a pair
    rho = cov_bar / var_bar                  # the equicorrelation they imply
    haz_m = float(f["attrition"]["hazard_month_6m"]) / 100.0
    p_week = (1.0 - haz_m) ** (1.0 / WEEKS_PER_MONTH)
    weeks = int(f["frame"]["eval_weeks"])
    # the share still trading, averaged over the weeks the basket is held
    p_bar = sum(p_week ** t for t in range(1, weeks + 1)) / weeks
    return {"var_bar": var_bar, "cov_bar": cov_bar, "rho": rho,
            "hazard_month": haz_m, "p_week": p_week, "p_bar": p_bar,
            "weeks": weeks, "n_eff_ceiling": 1.0 / rho}


def attainment(k: int, m: dict, mu: float, mortality: bool = True) -> float:
    """S(k)/S(infinity): the fraction of the ceiling a basket of k reaches.

    With E[R] = p*mu and Var(R) = A/k + B(1 - 1/k), where
      A = p*sigma^2 + p*mu^2*(1-p)   the own-variance term, diluted by stopping
      B = p^2*rho*sigma^2            the common term, which k cannot remove
    the ratio S(k)/S(inf) is sqrt(kB / (A + B(k-1))), free of mu's level.
    """
    p = m["p_bar"] if mortality else 1.0
    s2 = m["var_bar"]
    A = p * s2 + p * mu * mu * (1.0 - p)
    B = p * p * m["rho"] * s2
    return math.sqrt(k * B / (A + B * (k - 1)))


def count_for(frac: float, m: dict, mu: float, mortality: bool = True) -> float:
    """The k at which that fraction of the ceiling is reached.

    Inverting the attainment ratio: k = f^2 (A - B) / (B (1 - f^2)).
    """
    p = m["p_bar"] if mortality else 1.0
    s2 = m["var_bar"]
    A = p * s2 + p * mu * mu * (1.0 - p)
    B = p * p * m["rho"] * s2
    f2 = frac * frac
    return f2 * (A - B) / (B * (1.0 - f2))


def main() -> int:
    f = json.load(io.open(FACTS, encoding="utf-8"))
    m = moments(f)

    ks = f["baskets"][SCREEN]["k"]
    measured = {int(k): float(v["median"]) for k, v in ks.items()
                if v.get("median") is not None}
    assert 1 in measured, "the k = 1 basket is needed to set the level"
    grid = sorted(measured)

    # The level belongs to the representative leader the paper's own ceiling is
    # built from, not to the median Sharpe ratio of a single-leader draw. Those
    # differ by a factor of three here, because one noisy leader's estimated
    # Sharpe ratio is a heavy-tailed quantity and its median is not the moment
    # the closed form takes. Calibrating on the draw instead of the moment put
    # the whole predicted curve out by that factor.
    rep = float(f["dependence"]["rep_sharpe"])
    ceiling = float(f["dependence"]["ceiling"])
    mu = rep / math.sqrt(52.0) * math.sqrt(m["var_bar"])
    # The paper's ceiling is computed without mortality, so the closed form
    # must reproduce the representative leader exactly in that case. It then
    # sits slightly below him once stopping is allowed for, by the root of the
    # surviving share, which is the whole point of adding it.
    assert abs(ceiling * attainment(1, m, mu, False) - rep) < 0.01, \
        "the closed form does not reproduce the paper's own single-leader Sharpe"

    rows = []
    for k in grid:
        pred = ceiling * attainment(k, m, mu)
        rows.append({"k": k, "measured": measured[k], "predicted": round(pred, 3),
                     "gap": round(measured[k] - pred, 3),
                     "measured_share_of_ceiling": round(measured[k] / ceiling, 3),
                     "model_share_of_ceiling": round(attainment(k, m, mu), 3)})

    def at(k: int, key: str):
        return next((r[key] for r in rows if r["k"] == k), None)

    lo, hi = 5, 20
    out = {"screen": SCREEN, "rep_sharpe": rep, "ceiling": ceiling, "moments": {k: (round(v, 6) if isinstance(v, float) else v)
                                         for k, v in m.items()},
           "mu_weekly": round(mu, 6), "curve": rows,
           "target": TARGET,
           "k_for_target": round(count_for(TARGET, m, mu), 1),
           "k_for_target_no_mortality": round(count_for(TARGET, m, mu, False), 1),
           "attained_at_five": round(attainment(lo, m, mu), 3),
           "attained_at_twenty": round(attainment(hi, m, mu), 3)}

    if at(lo, "measured") is not None and at(hi, "measured") is not None:
        pred_gain = at(hi, "predicted") - at(lo, "predicted")
        meas_gain = at(hi, "measured") - at(lo, "measured")
        out["predicted_gain_five_to_twenty"] = round(pred_gain, 3)
        out["measured_gain_five_to_twenty"] = round(meas_gain, 3)
        out["predicted_ratio_five_to_twenty"] = round(
            attainment(hi, m, mu) / attainment(lo, m, mu), 3)

    print(f"rho implied by the measured moments: {m['rho']:.4f} "
          f"(a ceiling of {m['n_eff_ceiling']:.1f} independent bets)")
    print(f"share of leaders still trading, averaged over {m['weeks']} weeks: "
          f"{m['p_bar']:.3f}")
    print(f"a basket of {lo} reaches {out['attained_at_five']:.1%} of the "
          f"ceiling, one of {hi} reaches {out['attained_at_twenty']:.1%}")
    print(f"reaching {TARGET:.0%} of it needs {out['k_for_target']:.0f} leaders "
          f"with mortality, {out['k_for_target_no_mortality']:.0f} without")
    if "predicted_gain_five_to_twenty" in out:
        print(f"so {lo} -> {hi} is predicted to multiply the Sharpe ratio by "
              f"{out['predicted_ratio_five_to_twenty']:.2f}, a gain of "
              f"{out['predicted_gain_five_to_twenty']:+.2f}; measured "
              f"{out['measured_gain_five_to_twenty']:+.2f}")
    print()
    print("  k   measured  predicted   measured%ceil  model%ceil")
    for r in rows:
        print(f"{r['k']:>3}   {r['measured']:>8.3f}  {r['predicted']:>9.3f}  "
              f"{r['measured_share_of_ceiling']:>12.1%}  "
              f"{r['model_share_of_ceiling']:>10.1%}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, io.open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
