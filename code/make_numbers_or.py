"""Every number the OR paper prints, as a LaTeX macro traced to the run record.

Reads out/or/facts.json and out/or/policy.json and writes paper_or/numbers.tex.
A number typed into the LaTeX by hand fails the gate.

Macro names carry no digits, because the registry mangles digits into letters
and two different numbers would collide; so sizes and thresholds are spelled.

Usage: python or_journal/make_numbers_or.py
"""
import json
import os
import sys

ENGINE = "D:/iclr2027"            # the shared paper engine (provenance, refcheck, style)
sys.path.insert(0, ENGINE)
from paperengine.provenance import NumberRegistry  # noqa: E402

PCT = chr(92) + "%"
RUN = "or_analysis (or_journal/analysis.py on data/hl_panel)"
POL = "or_policy (or_journal/policy.py on data/hl_panel)"

KW = {"1": "one", "3": "three", "5": "five", "10": "ten", "20": "twenty", "40": "forty",
      "80": "eighty", "160": "onesixty"}
AW = {0.0: "zero", 10000.0: "tenk", 50000.0: "fiftyk", 100000.0: "hundredk",
      500000.0: "halfm", 1000000.0: "onem", 5000000.0: "fivem"}
SW = {"none": "none", "size": "size", "drawdown": "drawdown", "vol": "vol",
      "past_sharpe": "pastsharpe", "size_drawdown": "sizedrawdown",
      "size_drawdown_active": "sizeactive", "size_drawdown_active_sharpe": "sizeactivesharpe"}
MW = {"1": "one", "3": "three", "6": "six", "12": "twelve", "24": "twentyfour"}
HW = {"13": "thirteen", "26": "twentysix", "39": "thirtynine", "52": "fiftytwo"}


MINUS = chr(92) + "ensuremath{" + chr(92) + "mathrm{-}}"


def minus(text: str) -> str:
    """A typeset minus sign, not a hyphen, wherever a number is negative."""
    return text.replace("-", MINUS, 1) if text.startswith("-") else text


def pct(x, digits: int = 1) -> str:
    return minus(f"{x:.{digits}f}{PCT}") if isinstance(x, (int, float)) else "--"


def sg(x, digits: int = 2) -> str:
    """A signed number, because a Sharpe ratio near zero must show its sign."""
    return minus(f"{x:+.{digits}f}") if isinstance(x, (int, float)) else "--"


def main() -> int:
    f = json.load(open("out/or/facts.json", encoding="utf-8"))
    reg = NumberRegistry()
    fr = f["frame"]

    def add(name, value, prov=RUN):
        if value is None:
            return
        reg.add(name, value, provenance=prov)

    # ---- the frame and the measurement rules
    add("frame size", f"{fr['frame_size']:,}")
    # counts carry a thousands separator like every other count in the paper;
    # a value under a thousand is unchanged by the format
    for k in ("fetched", "with_path", "usable", "candidates_at_cut", "eval_weeks",
              "cand_with_full_path", "cand_stopped_in_window"):
        add(f"frame {k.replace('_', ' ')}", f"{fr[k]:,}")
    add("frame pct stopped", pct(fr["pct_stopped_in_window"]))
    add("frame min weeks", fr["min_weeks"])
    add("frame dead weeks", fr["dead_weeks"])
    add("frame return floor", f"{int(fr['return_floor_usd']):,}")
    add("frame cap up", f"{int(100 * fr['cap_up'])}{PCT}")
    add("frame copy cost bp", f"{fr['copy_cost_bp']:.1f}")
    add("frame turnover cap", f"{int(fr['turnover_cap'])}")
    add("frame funding frac", pct(100 * fr["funding_frac"], 0))
    add("frame min notional", f"{int(fr['min_notional_usd'])}")
    add("frame drops no live", fr["drops"]["no_live_week"])
    add("frame drops short", fr["drops"]["short_history"])
    add("frame missing weeks", f"{fr.get('missing_weeks', 0):,}")
    add("frame unmeasurable", fr.get("cand_unmeasurable"))
    add("frame dust gap accounts", fr.get("accounts_with_dust_gaps"))
    ff = fr.get("frame_facts") or {}
    if ff:
        add("frame losing", pct(ff["pct_losing"]))
        add("frame under dust", pct(ff["pct_under_dust"]))
        add("frame median acct", f"{ff['median_acct']:,.0f}")
    fe = f.get("fees") or {}
    if fe:
        add("fee pooled", f"{fe['bp_pooled']:.2f}")
        add("fee median", f"{fe['bp_median']:.2f}")
        add("fee band", f"{fe['bp_q1']:.2f} to {fe['bp_q3']:.2f}")
        add("fee fills", f"{fe['fills']:,}")
        add("fee accounts", fe["accounts_with_fills"])
        add("fee notional", f"{fe['notional_usd'] / 1e9:.1f}")
    gd = f.get("grid") or {}
    if gd:
        add("grid days per point", f"{gd['days_per_point_median']:.1f}")
        add("grid long steps", pct(gd["pct_steps_over_a_week"]))
        add("grid days big", f"{gd['days_per_point_big']:.1f}")
        add("grid days small", f"{gd['days_per_point_small']:.1f}")
    cv = f.get("convention") or {}
    if cv.get("stop_weeks_priced"):
        add("stop weeks priced", f"{cv['stop_weeks_priced']:,}")
        add("stop week median", pct(cv["stop_week_median_pct"]))
        add("stop weeks bad", f"{cv['stop_weeks_losing_badly']:,}")
        add("stop week bad median", pct(cv["stop_week_bad_median_pct"]))
        add("stop weeks flat", f"{cv['stop_weeks_flat']:,}")
    cr = f.get("crossover") or {}
    if cr:
        add("crossover same throughout",
            f"{sum(1 for v in cr.values() if v['same_order_throughout'])} of {len(cr)}")
        sd = cr.get("size vs drawdown") or {}
        if sd:
            add("crossover size drawdown at zero", sg(sd["at_zero"]))
            add("crossover size drawdown at top", sg(sd["at_top"]))
            add("crossover size drawdown holds",
                "at every level" if sd["same_order_throughout"] else "not at every level")
        tags = {"size vs drawdown": "size drawdown", "drawdown vs past_sharpe": "drawdown pastsharpe",
                "size vs past_sharpe": "size pastsharpe", "none vs size": "open size"}
        for key, tag in tags.items():
            v = cr.get(key) or {}
            if v.get("flips_between"):
                add(f"crossover {tag} low", f"{v['flips_between'][0]:.0f}")
                add(f"crossover {tag} high", f"{v['flips_between'][1]:.0f}")
    add("frame pct dust gaps", pct(fr.get("pct_with_dust_gaps")))
    add("frame pct unmeasurable", pct(fr.get("pct_unmeasurable")))
    add("frame gap weeks", f"{fr.get('gap_weeks', 0):,}")
    add("frame pct gaps", pct(fr.get("pct_missing_that_are_gaps")))
    add("frame survivor candidates", fr["survivor_conditional"]["candidates"])
    add("frame survivor ic", sg(fr["survivor_conditional"]["ic"], 3))

    c = f["convention"]
    add("conv weekly returns", f"{c['weekly_returns']:,}")
    add("conv capped low", f"{c['capped_low']:,}")
    add("conv capped high", f"{c['capped_high']:,}")
    add("conv funding weeks", f"{c['funding_weeks']:,}")
    add("conv thin weeks", f"{c['thin_weeks']:,}")
    add("conv pct capped", pct(c["pct_capped"], 2))
    add("conv pct funding", pct(c["pct_funding"], 2))
    for conv, tag in (("modified_dietz", "dietz"), ("start_of_week", "startweek"), ("mid_week", "midweek")):
        if conv in c and isinstance(c[conv], dict):
            for name, short in (("none", "open"), ("size", "big")):
                d = c[conv].get(name)
                if d:
                    add(f"conv {tag} {short} gross", sg(d["k20"]))
                    add(f"conv {tag} {short} net", sg(d["k20_net"]))

    sm = f.get("sample", {})
    for lab in ("kept", "dropped"):
        if lab in sm:
            add(f"sample {lab} n", sm[lab]["n"])
            add(f"sample {lab} acct", f"{sm[lab]['median_acct']:,.0f}")
            add(f"sample {lab} age", f"{sm[lab]['median_age_weeks']:.0f}")
            add(f"sample {lab} dead", pct(sm[lab]["pct_dead"]))
    if "by_decile" in sm:
        rates = [(v["usable"] / v["rows"], k) for k, v in sm["by_decile"].items() if v["rows"] > 20]
        if rates:
            rates.sort()
            add("sample usable low", pct(100 * rates[0][0]))
            add("sample usable high", pct(100 * rates[-1][0]))

    # ---- attrition
    a = f["attrition"]
    add("attrition dead", a["dead"])
    add("attrition n", a["n"])
    add("attrition pct dead", pct(a["pct_dead"]))
    add("attrition median age", f"{a['median_age_weeks']:.0f}")
    for m, v in a["survival"].items():
        add(f"attrition alive {MW[m]} months", pct(v))
    add("attrition hazard six", pct(a["hazard_month_6m"]))
    add("attrition hazard twelve", pct(a["hazard_month_12m"]))
    add("attrition implied twelve", pct(a["implied_12m_from_6m_hazard"]))
    en = a.get("ending") or {}
    if en:
        add("ending classified", en["classified"])
        add("ending withdrawal", pct(en["pct_withdrawal"]))
        add("ending loss", pct(en["pct_loss"]))
        add("ending loss share", pct(en["median_loss_share_pct"]))
    cq = (f.get("convention") or {})
    if cq.get("quiet_share") is not None:
        add("quiet share", pct(cq["quiet_share"]))
        add("quiet candidates", cq["quiet_candidates"])
        for nm, tag in (("none", "open"), ("size", "big")):
            v = (cq.get("quiet") or {}).get(nm)
            if v:
                add(f"quiet {tag} net", sg(v["net"]))
                add(f"quiet {tag} gross", sg(v["gross"]))
                add(f"quiet {tag} pass", v["pass"])
        if cq.get("quiet_size_gain") is not None:
            add("quiet size gain", sg(cq["quiet_size_gain"]))
    if "usable_only" in a:
        add("attrition usable alive twelve", pct(a["usable_only"]["alive_12m"]))
    for lab in ("big", "small"):
        if lab in a:
            add(f"attrition {lab} n", a[lab]["n"])
            add(f"attrition {lab} alive six", pct(a[lab]["alive_6m"]))
            add(f"attrition {lab} alive twelve", pct(a[lab]["alive_12m"]))

    # ---- identifiability
    ident = f["identifiability"]
    for h, d in ident.items():
        if not h.isdigit():
            continue
        key = HW[h]
        add(f"ic {key} sharpe", sg(d["ic_sharpe_vs_future_mean"], 3))
        add(f"ic {key} mean", sg(d["ic_mean_vs_future_mean"], 3))
        add(f"ic {key} n", d["n"])
        add(f"ic {key} unmeasurable", d.get("n_unmeasurable"))
        if d.get("ic_zero_filled") is not None:
            add(f"ic {key} zero filled", sg(d["ic_zero_filled"], 3))
        lo, hi = d["ic_sharpe_ci"]
        if lo == lo:
            add(f"ic {key} low", sg(lo, 3))
            add(f"ic {key} high", sg(hi, 3))
    ah = ident["across_horizons"]
    add("ic across low", sg(ah["min"], 3))
    add("ic across high", sg(ah["max"], 3))
    add("ic across mean", sg(ah["mean"], 3))
    add("ic across horizons", ah["horizons"])
    nl = ident["null"]
    add("ic null median", sg(nl["whole_frame"]["median"], 3))
    add("ic null low", sg(nl["whole_frame"]["p05"], 3))
    add("ic null high", sg(nl["whole_frame"]["p95"], 3))
    add("ic null top median", sg(nl["top_decile_only"]["median"], 3))
    add("ic null top low", sg(nl["top_decile_only"]["p05"], 3))
    add("ic null top high", sg(nl["top_decile_only"]["p95"], 3))
    add("ic null reps", nl["whole_frame"]["reps"])

    # ---- dependence, and what it predicts for a basket
    d = f["dependence"]
    add("dep pairs", f"{d['pairs']:,}")
    add("dep median", sg(d["median"], 3))
    add("dep lower", sg(d["q1"], 3))
    add("dep upper", sg(d["q3"], 3))
    add("dep share above half", pct(d["share_above_half"]))
    add("dep overlap weeks", d.get("median_overlap_weeks"))
    add("dep cov ratio", f"{d['cov_ratio']:.3f}")
    add("dep n eff", f"{d['n_eff']:.1f}" if d.get("n_eff") else None)
    add("dep rep sharpe", sg(d["rep_sharpe"]))
    add("dep ceiling", sg(d["ceiling"]))
    for k, v in (d.get("predicted") or {}).items():
        if k in KW:
            add(f"dep predicted {KW[k]}", sg(v))

    # ---- the market over the same weeks
    for coin, v in f.get("benchmark", {}).items():
        tag = coin.lower()
        add(f"bench {tag} sharpe", sg(v["sharpe"]))
        add(f"bench {tag} se", f"{v['sharpe_se']:.2f}")
        add(f"bench {tag} cagr", pct(v["cagr_pct"], 0))
        add(f"bench {tag} total", pct(v["total_pct"], 0))

    # ---- baskets by screen and size
    for name, rec in f["baskets"].items():
        tag = SW[name]
        add(f"sc {tag} pass", rec["pass"])
        add(f"sc {tag} future mean", pct(rec["median_future_mean"], 2))
        add(f"sc {tag} pct dead after", pct(rec["pct_dead_after"]))
        if "alive_after" in rec:
            add(f"sc {tag} alive six", pct(rec["alive_after"]["6"]))
        add(f"sc {tag} measurable", rec.get("measurable"))
        if rec.get("ic_inside_zero") is not None:
            add(f"sc {tag} ic zero", sg(rec["ic_inside_zero"], 3))
        if rec.get("ic_inside") is not None:
            add(f"sc {tag} ic", sg(rec["ic_inside"], 3))
            lo, hi = rec["ic_inside_ci"]
            if lo == lo:
                add(f"sc {tag} ic low", sg(lo, 3))
                add(f"sc {tag} ic high", sg(hi, 3))
            add(f"sc {tag} sharpe iqr", f"{rec['sharpe_iqr_inside']:.2f}")
        if rec.get("top_turnover") is not None:
            add(f"sc {tag} top turnover", f"{rec['top_turnover']:.2f}")
        if "turnover" in rec:
            t = rec["turnover"]
            add(f"sc {tag} turnover", f"{t['median']:.2f}")
            add(f"sc {tag} turnover uncapped", f"{t['median_uncapped']:.2f}")
            add(f"sc {tag} at cap", pct(t["at_cap_pct"]))
            add(f"sc {tag} drag", f"{t['drag_weekly_bp']:.0f}")
        if rec.get("cost_in_sharpe") is not None:
            add(f"sc {tag} cost in sharpe", sg(rec["cost_in_sharpe"]))
        for k, cell in rec["k"].items():
            if k not in KW:
                continue
            kk = KW[k]
            add(f"sc {tag} k {kk} gross", sg(cell["median"]))
            add(f"sc {tag} k {kk} net", sg(cell["median_net"]))
            add(f"sc {tag} k {kk} se", f"{cell['se']:.2f}")
            add(f"sc {tag} k {kk} cagr", pct(cell["median_cagr_pct"], 0))
            if cell.get("cost_grid"):
                for bp, v in cell["cost_grid"].items():
                    bw = {"0": "zero", "5": "five", "9": "measured", "20": "twenty"}.get(bp)
                    if bw:
                        add(f"sc {tag} k {kk} cost {bw}", sg(v))
            if cell.get("bench"):
                b = cell["bench"]
                add(f"sc {tag} k {kk} beta", f"{b['beta']:.2f}")
                add(f"sc {tag} k {kk} alpha", pct(b["alpha_annual_pct"], 0))
                add(f"sc {tag} k {kk} alpha t", sg(b["alpha_t"]))
        if rec.get("all_of_set"):
            add(f"sc {tag} all net", sg(rec["all_of_set"]["median_net"]))

    # ---- the decision surface: the profile in the account floor
    for q in f["surface"].get("profile", []):
        tag = AW.get(q["acct_min"])
        if not tag:
            continue
        add(f"profile {tag} pass", q["pass"])
        add(f"profile {tag} best k", q["best_k"])
        add(f"profile {tag} best net", sg(q["best_net"]))
        add(f"profile {tag} best gross", sg(q["best_gross"]))
        add(f"profile {tag} best cagr", pct(q["best_cagr_pct"], 0))
        add(f"profile {tag} turnover", f"{q['turnover']:.2f}")
        add(f"profile {tag} best all of set", "the whole set" if q.get("best_all_of_set") else "a draw")
        if q.get("k20_net") is not None:
            add(f"profile {tag} k twenty net", sg(q["k20_net"]))
            add(f"profile {tag} k twenty gross", sg(q["k20_gross"]))
            add(f"profile {tag} k twenty cagr", pct(q["k20_cagr_pct"], 0))
            if q.get("k20_q1") is not None:
                add(f"profile {tag} k twenty band", f"{sg(q['k20_q1'])} to {sg(q['k20_q3'])}")
            add(f"profile {tag} k twenty draws", q.get("k20_draws"))
    add("surface monotone twenty", "is monotone" if f["surface"].get("monotone_at_twenty")
        else "is not monotone")
    add("surface monotone best", "is monotone" if f["surface"].get("monotone_at_best_k")
        else "is not monotone")
    best = None
    for row in f["surface"]["grid"]:
        for k, v in row["k"].items():
            if v.get("median_net") is None or row["pass"] < 10:
                continue
            if best is None or v["median_net"] > best[0]:
                best = (v["median_net"], row["acct_min"], row["worst_min"], int(k), row["pass"], v["median"])
    if best:
        add("surface best net", sg(best[0]))
        add("surface best acct", f"{int(best[1]):,}")
        add("surface best worst", pct(100 * best[2], 0))
        add("surface best k", best[3])
        add("surface best pass", best[4])
        add("surface best gross", sg(best[5]))
    add("surface cells", sum(len(r["k"]) for r in f["surface"]["grid"]))
    fk = f["surface"].get("feasible_k", {})
    for cc, tag in (("1000", "onek"), ("5000", "fivek"), ("25000", "twentyfivek"), ("100000", "hundredk")):
        if cc in fk:
            add(f"feasible {tag}", fk[cc])
            add(f"capital {tag}", f"{int(cc):,}")
    # what the largest basket we report would cost to fund at the minimum order
    add("capital for the largest basket",
        f"{int(fr['min_notional_usd'] * max(f['surface']['ks'])):,}")
    for a, tag in AW.items():
        if a:
            add(f"floor {tag}", f"{a / 1e3:,.0f}k" if a < 1e6 else f"{a / 1e6:,.0f}M")
    add("ic null band", pct(90, 0))

    m = f["multiplicity"]
    add("mult trials", m["trials"])
    add("mult null max", sg(m["null_max_sharpe_95"]))
    add("mult se near two", f"{m['se_of_a_sharpe_near_two']:.2f}")
    add("mult eval weeks", m["eval_weeks"])

    # ---- policies over several decision dates
    pol_path = "out/or/policy.json"
    if os.path.exists(pol_path):
        pol = json.load(open(pol_path, encoding="utf-8"))
        add("policy dates", len(pol["dates"]), POL)
        add("policy hold", pol["hold"], POL)
        add("policy spacing", pol["spacing"], POL)
        add("policy draws", pol["draws"], POL)
        add("policy detect lag", pol["detect_lag"], POL)
        add("policy switch cost", f"{pol['switch_cost_bp']:.1f}", POL)
        add("policy screen worst", pct(100 * pol["screen"]["worst_min"], 0), POL)
        add("policy screen vol", pct(100 * pol["screen"]["vol_max"], 0), POL)
        add("policy screen acct", f"{int(pol['screen']['acct_min']):,}", POL)

        def words(key):
            parts = key.split("_")
            return " ".join(KW.get(p, p) for p in parts)

        for key, v in pol["summary"].items():
            tag = "policy " + words(key)
            add(f"{tag} mean", sg(v["mean"]), POL)
            add(f"{tag} min", sg(v["min"]), POL)
            add(f"{tag} max", sg(v["max"]), POL)
            if "sd" in v:
                add(f"{tag} sd", f"{v['sd']:.2f}", POL)
            if "positive" in v:
                add(f"{tag} positive", f"{v['positive']} of {v['dates']}", POL)
            if "wins" in v:
                add(f"{tag} wins", f"{v['wins']} of {v['dates']}", POL)
            if v.get("gross_mean") is not None:
                add(f"{tag} gross mean", sg(v["gross_mean"]), POL)
                add(f"{tag} gross wins", f"{v['gross_wins']} of {v['dates']}", POL)
            if v.get("cagr_median_a") is not None:
                add(f"{tag} growth", pct(v["cagr_median_a"], 0), POL)
                add(f"{tag} growth against", pct(v["cagr_median_b"], 0), POL)
                add(f"{tag} growth wins", f"{v['cagr_wins']} of {v['dates']}", POL)
            if v.get("cagr_median") is not None:
                add(f"{tag} growth", pct(v["cagr_median"], 0), POL)
        for key in ("open_top_20", "risk_top_20", "big_top_20"):
            ps = [d["policies"][key].get("percentile_in_random") for d in pol["dates"]
                  if key in d["policies"]]
            ps = [x for x in ps if x is not None]
            if ps:
                tag = "policy pct " + words(key)
                add(f"{tag} low", f"{min(ps):.0f}", POL)
                add(f"{tag} high", f"{max(ps):.0f}", POL)
                add(f"{tag} median", f"{sorted(ps)[len(ps) // 2]:.0f}", POL)
                add(f"{tag} above half", f"{sum(1 for x in ps if x > 50)} of {len(ps)}", POL)
        cand = [d["candidates"] for d in pol["dates"]]
        add("policy candidates low", min(cand), POL)
        add("policy candidates high", max(cand), POL)
        for fam in ("open", "risk", "big"):
            sizes = [d["sets"][fam] for d in pol["dates"] if fam in d.get("sets", {})]
            if sizes:
                add(f"policy {fam} low", min(sizes), POL)
                add(f"policy {fam} high", max(sizes), POL)
            ics = [d["ic_inside"].get(fam) for d in pol["dates"] if d.get("ic_inside")]
            ics = [x for x in ics if x is not None]
            if ics:
                add(f"policy {fam} ic low", sg(min(ics), 3), POL)
                add(f"policy {fam} ic high", sg(max(ics), 3), POL)
                add(f"policy {fam} ic mean", sg(sum(ics) / len(ics), 3), POL)
        swaps = [d["policies"]["big_replace_20"]["swaps"] for d in pol["dates"]
                 if "big_replace_20" in d["policies"]]
        if swaps:
            add("policy swaps", f"{sum(swaps) / len(swaps):.1f}", POL)
        for v, tag in ((pol.get("variance"), "policy var"),
                       ((pol.get("disjoint") or {}).get("variance_split"), "policy disjoint var")):
            if not v:
                continue
            add(f"{tag} date", pct(v["pct_date"]), POL)
            add(f"{tag} rule", pct(v["pct_rule"]), POL)
            add(f"{tag} cells", v["cells"], POL)
            if v.get("f_date") is not None:
                add(f"{tag} f date", f"{v['f_date']:.1f}", POL)
                add(f"{tag} f rule", f"{v['f_rule']:.2f}", POL)
                add(f"{tag} date noise", pct(v["pct_date_under_noise"]), POL)
                add(f"{tag} rule noise", pct(v["pct_rule_under_noise"]), POL)
                add(f"{tag} df rule", v["df_rule"], POL)
                add(f"{tag} df residual", v["df_residual"], POL)
        rev = [d.get("revived_after") for d in pol["dates"] if d.get("revived_after") is not None]
        if rev:
            add("policy revived low", min(rev), POL)
            add("policy revived high", max(rev), POL)
        # the band sweep, and the top-k curve taken in order
        arms = (pol.get("band_sweep") or {}).get("big") or {}
        if arms:
            add("sweep arms", len(arms), POL)
        # how many of the six decisions change sign once the cost is charged
        six = ("screen_gain_big_20", "rank_gain_open_20", "screen_gain_risk_20",
               "rank_gain_big_20", "replace_gain_big_20", "spread_gain_open_20")
        got = [pol["summary"][kk] for kk in six if kk in pol["summary"]]
        if got:
            flips = sum(1 for v in got
                        if v.get("gross_mean") is not None
                        and (v["mean"] > 0) != (v["gross_mean"] > 0))
            add("policy decisions counted", len(got), POL)
            add("policy decisions flipping", flips, POL)
        words_b = {"0bp": "zero", "derived": "derived", "10bp": "ten", "50bp": "fifty",
                   "200bp": "twohundred", "never": "never", "solved": "solved"}
        for fam, arms in (pol.get("band_sweep") or {}).items():
            for lab, v in arms.items():
                tag = f"sweep {fam} {words_b.get(lab, lab)}"
                add(f"{tag} net", sg(v["mean"]), POL)
                add(f"{tag} swaps", f"{v['swaps']:.0f}", POL)
                add(f"{tag} cagr", pct(v["cagr_median"], 0), POL)
            best = max(arms.items(), key=lambda t: t[1]["mean"])
            add(f"sweep {fam} best arm", {"never": "never swapping", "derived": "the derived band",
                                          "0bp": "swapping on any gap"}.get(best[0], best[0] + " band"), POL)
            add(f"sweep {fam} spread", sg(max(v["mean"] for v in arms.values())
                                          - min(v["mean"] for v in arms.values())), POL)
        for fam, curve in (pol.get("top_curve") or {}).items():
            vals = [v["mean"] for v in curve.values()]
            ks = [int(k) for k in curve]
            if vals:
                bi = max(range(len(vals)), key=lambda i: vals[i])
                add(f"topcurve {fam} best k", ks[bi], POL)
                add(f"topcurve {fam} best", sg(vals[bi]), POL)
                add(f"topcurve {fam} low", sg(min(vals)), POL)
                add(f"topcurve {fam} high", sg(max(vals)), POL)
                add(f"topcurve {fam} points", len(vals), POL)
        dj = pol.get("disjoint") or {}
        add("policy disjoint dates", dj.get("n_dates"), POL)
        vs = dj.get("variance_split") or {}
        if vs.get("pct_date") is not None:
            add("policy disjoint var date", pct(vs["pct_date"]), POL)
            add("policy disjoint var rule", pct(vs["pct_rule"]), POL)
            add("policy disjoint var cells", vs["cells"], POL)
        for key, v in (dj.get("gains") or {}).items():
            tag = "policy disjoint " + key.replace("_", " ")
            add(f"{tag} mean", sg(v["mean"]), POL)
            add(f"{tag} wins", f"{v['wins']} of {v['dates']}", POL)
            add(f"{tag} weeks", v.get("weeks"), POL)
            if v.get("weekly_mean_bp") is not None:
                add(f"{tag} weekly", minus(f"{v['weekly_mean_bp']:.0f}"), POL)
            if v.get("t_nw") is not None:
                add(f"{tag} t", sg(v["t_nw"]), POL)
            if v.get("gross_weekly_mean_bp") is not None:
                add(f"{tag} gross weekly", minus(f"{v['gross_weekly_mean_bp']:.0f}"), POL)
            if v.get("gross_t_nw") is not None:
                add(f"{tag} gross t", sg(v["gross_t_nw"]), POL)

    # ---- the two propositions and their calibration
    th_path = "out/or/theory.json"
    if os.path.exists(th_path):
        th = json.load(open(th_path, encoding="utf-8"))
        THE = "or_theory (or_journal/theory.py on data/hl_panel)"
        add("theory hazard week", pct(100 * th["lambda_week"], 2), THE)
        add("theory hazard month", pct(th["lambda_month_pct"]), THE)
        add("theory switch cost", f"{th['switch_cost_bp']:.1f}", THE)
        sh = th.get("shrinkage") or {}
        if sh:
            add("theory beta", f"{sh['beta']:.3f}", THE)
            add("theory beta corr", sg(sh["correlation"], 3), THE)
            add("theory beta n", sh["n"], THE)
        shw = th.get("shrinkage_in_window") or {}
        if shw:
            add("theory beta in window", f"{shw['beta']:.3f}", THE)
            add("theory beta in window corr", sg(shw["correlation"], 3), THE)
        add("theory muR", pct(th["muR_weekly_pct"], 2), THE)
        add("theory posterior spread", pct(th["posterior_spread_pct"], 2), THE)
        words_t = {"26": "twentysix", "13": "thirteen", "8": "eight", "4": "four",
                   "2": "two", "1": "one"}
        for t, v in (th.get("horizons") or {}).items():
            tag = f"theory band {words_t.get(t, t)}"
            add(f"{tag} weeks", f"{v['expected_trading_weeks']:.1f}", THE)
            add(f"{tag} bp", f"{v['band_weekly_bp']:.2f}", THE)
            add(f"{tag} share", pct(100 * v["band_in_pool_spreads"], 1), THE)
        for lab, v in (th.get("comparative") or {}).items():
            tag = "theory hazard " + lab.replace(" ", "")
            add(f"{tag} month", pct(v["lambda_month_pct"]), THE)
            add(f"{tag} band", f"{v['band_weekly_bp']:.2f}", THE)
            add(f"{tag} weeks", f"{v['expected_trading_weeks']:.1f}", THE)
        sb = th.get("swap_band") or {}
        if sb:
            add("swap band examined", sb["swaps_examined"], THE)
            add("swap band dates", sb["dates"], THE)
            add("swap band median", f"{sb['bp_median']:+.0f}", THE)
            add("swap band low", f"{sb['bp_p10']:+,.0f}", THE)
            add("swap band high", f"{sb['bp_p90']:+,.0f}", THE)
            add("swap band negative", pct(100 * sb["share_negative"]), THE)
            add("swap band pairs", sb["median_pairs_with_overlap"], THE)
            add("swap band possible", sb["possible_pairs"], THE)
        pg = th.get("pool_variance_gradient") or {}
        if pg:
            add("pool gradient", f"{pg['risk_term_weekly_bp']:+,.0f}", THE)
        rb = th.get("risk_band") or {}
        if rb:
            add("band risk term", f"{rb['risk_term_weekly_bp']:,.0f}", THE)
            add("band var term", f"{rb['var_term_bp']:,.0f}", THE)
            add("band cov term", f"{rb['cov_term_bp']:,.0f}", THE)
            add("band with risk", f"{rb['band_with_risk_bp']:,.0f}", THE)
            add("band widening", f"{rb['widening']:,.0f}", THE)
            add("band delta var", f"{rb['delta_var']:.3f}", THE)
            add("band delta cov", f"{rb['delta_cov']:.3f}", THE)
            add("band k", rb["k"], THE)
        gw = th.get("gap_walk") or {}
        if gw:
            add("margin level", f"{gw['margin_median_bp']:.1f}", THE)
            add("margin positive", pct(100 * gw["margin_positive_share"]), THE)
            add("margin restart", f"{gw['restart_median_bp']:+.1f}", THE)
            add("margin move", f"{gw['innovation_mean_abs_bp']:.0f}", THE)
            add("margin drift", f"{gw['innovation_signed_bp']:+.1f}", THE)
            add("margin weeks", gw["weeks"], THE)
        sv = th.get("solved") or {}
        wt = {"1": "one", "2": "two", "4": "four", "8": "eight", "13": "thirteen",
              "26": "twentysix"}
        for t, v in sv.items():
            if v.get("boundary_bp") is not None:
                add(f"solved {wt.get(t, t)}", f"{v['boundary_bp']:.1f}", THE)
                add(f"solved {wt.get(t, t)} breakeven", f"{v['break_even_bp']:.2f}", THE)
        if th.get("solved_inside_bracket"):
            add("solved inside bracket", th["solved_inside_bracket"], THE)
        if th.get("solved_innovations"):
            add("solved innovations", th["solved_innovations"], THE)
        br = th.get("bracket") or {}
        words_t = {"26": "twentysix", "13": "thirteen", "8": "eight", "4": "four",
                   "2": "two", "1": "one"}
        for t, v in br.items():
            tag = f"bracket {words_t.get(t, t)}"
            add(f"{tag} low", f"{v['lower_bp']:.2f}", THE)
            if v.get("upper_bp") is not None:
                add(f"{tag} high", f"{v['upper_bp']:,.0f}", THE)
            if v.get("ratio"):
                add(f"{tag} ratio", f"{v['ratio']:,.0f}", THE)
            add(f"{tag} week cost", f"{v['one_week_of_gap']:.2f}", THE)
        closed = [t for t, v in br.items()
                  if v.get("upper_bp") is not None and v["upper_bp"] <= v["lower_bp"]]
        if closed:
            add("bracket closes at", max(int(t) for t in closed), THE)
        gi = th.get("gap_innovation") or {}
        if gi:
            add("gap innovation median", f"{gi['median_bp']:.1f}", THE)
            add("gap innovation mean", f"{gi['mean_bp']:.1f}", THE)
            add("gap innovation high", f"{gi['p90_bp']:.1f}", THE)
            add("gap innovation weeks", gi["weeks"], THE)
            if gi.get("signed_mean_bp") is not None:
                add("gap drift", f"{gi['signed_mean_bp']:+.1f}", THE)
                add("gap drift t", sg(gi["signed_t"]), THE)
            if gi.get("level_median_bp") is not None:
                add("gap level", f"{gi['level_median_bp']:,.0f}", THE)
        p1 = th.get("proposition_one") or {}
        if p1:
            add("prop one gross rises", p1.get("gross_rises_in"), THE)
            add("prop one net rises", p1.get("net_rises_in"), THE)
            add("prop one gross monotone", p1.get("gross_monotone_in"), THE)
            add("prop one net monotone", p1.get("net_monotone_in"), THE)
            add("prop one var bar", f"{p1['var_bar']:.5f}", THE)
            add("prop one cov bar", f"{p1['cov_bar']:.5f}", THE)

    # ---- the index rule as run, and the shrinkage it used
    if os.path.exists(pol_path):
        idx = [d["policies"].get("big_index_20") for d in pol["dates"]]
        idx = [c for c in idx if c]
        if idx:
            sw = [c["swaps"] for c in idx]
            add("policy index swaps low", min(sw), POL)
            add("policy index swaps high", max(sw), POL)
            add("policy index swaps mean", f"{sum(sw) / len(sw):.0f}", POL)
        betas = [d.get("shrinkage", {}).get("beta") for d in pol["dates"]]
        betas = [b for b in betas if b is not None]
        if betas:
            add("policy beta low", f"{min(betas):.3f}", POL)
            add("policy beta high", f"{max(betas):.3f}", POL)

    # ---- how much each leader gets, measured rather than cited
    wt_path = "out/or/weights.json"
    if os.path.exists(wt_path):
        wt = json.load(open(wt_path, encoding="utf-8"))
        WGT = "or_weights (or_journal/weights.py on data/hl_panel)"
        dj = wt["disjoint"]
        add("weight k", dj["k"], WGT)
        add("weight delta", f"{dj['delta']:.2f}", WGT)
        add("weight dates", len(dj["dates"]), WGT)
        d0 = dj["dates"][0]["fam"].get("big", {}).get("diag") or {}
        if d0:
            add("weight own median", d0["own_median"], WGT)
            add("weight pair median", d0["pair_median"], WGT)
            add("weight pairs filled", d0["pairs_filled"], WGT)
            add("weight pairs", d0["pairs"], WGT)
        words_w = {"equal": "Equal", "invvol": "Invvol", "minvar": "Minvar",
                   "tangency": "Tangency"}
        words_f = {"big": "Big", "risk": "Risk"}
        better_sharpe = better_growth = total = 0
        for fam, fw in words_f.items():
            base = dj["summary"].get(f"{fam}|equal|level")
            for name, nw in words_w.items():
                lv = dj["summary"].get(f"{fam}|{name}|level")
                if not lv:
                    continue
                add(f"weight {fam} {name} net", sg(lv["net"]), WGT)
                add(f"weight {fam} {name} growth", pct(100 * lv["cagr"], 0), WGT)
                add(f"weight {fam} {name} maxw", pct(100 * lv["maxw"], 0), WGT)
                add(f"weight {fam} {name} names", f"{lv['nonzero']:.1f}", WGT)
                if name == "equal" or not base:
                    continue
                total += 1
                better_sharpe += 1 if lv["net"] > base["net"] else 0
                better_growth += 1 if lv["cagr"] > base["cagr"] else 0
                sm = dj["summary"].get(f"{fam}|{name}")
                if sm:
                    add(f"weight {fam} {name} weekly", minus(f"{sm['weekly_bp']:.0f}"), WGT)
                    add(f"weight {fam} {name} t", sg(sm["t"]), WGT)
                    add(f"weight {fam} {name} wins", f"{sm['wins']} of {sm['dates']}", WGT)
        # the two weightings that use the covariance matrix, against the one
        # that uses only its diagonal: the distinction the growth column makes
        cov_tot = cov_worse = 0
        for fam in words_f:
            base = dj["summary"].get(f"{fam}|equal|level")
            for name in ("minvar", "tangency"):
                lv = dj["summary"].get(f"{fam}|{name}|level")
                if lv and base:
                    cov_tot += 1
                    cov_worse += 1 if lv["cagr"] < base["cagr"] else 0
        add("weight cov comparisons", cov_tot, WGT)
        add("weight cov worse growth", cov_worse, WGT)
        add("weight comparisons", total, WGT)
        add("weight better sharpe", better_sharpe, WGT)
        add("weight worse growth", total - better_growth, WGT)
        ts = [abs(v["t"]) for k, v in dj["summary"].items() if "t" in v]
        if ts:
            add("weight max abs t", f"{max(ts):.2f}", WGT)
        # the shrinkage the answer does not survive
        sw = wt.get("delta_sweep") or {}
        signs = {}
        for dl, row in sw.items():
            for k, v in row.items():
                signs.setdefault(k, set()).add(v > 0)
        add("weight sign flips", sum(1 for v in signs.values() if len(v) > 1), WGT)
        add("weight sweep deltas", len(sw), WGT)

    # ---- what a second snapshot of the frame shows
    fb_path = "out/or/frame_bias.json"
    if os.path.exists(fb_path):
        fb = json.load(open(fb_path, encoding="utf-8"))
        SNP = "or_frame_bias (or_journal/frame_bias.py on two frame snapshots)"
        li = fb["listing"]
        add("snap days", fb["days_between"], SNP)
        add("snap second date", fb["dates"][1], SNP)
        add("snap rows two", f"{li['s2_rows']:,}", SNP)
        add("snap left", f"{li['left']:,}", SNP)
        add("snap joined", f"{li['joined']:,}", SNP)
        add("snap left pct", pct(li["left_pct"], 1), SNP)
        add("snap below acctmin", f"{li['below_acctmin']:,}", SNP)
        add("snap below acctmin left", li["below_acctmin_left"], SNP)
        add("snap above acctmin", f"{li['above_acctmin']:,}", SNP)
        add("snap above left pct", pct(li["above_acctmin_left_pct"], 1), SNP)
        add("snap left acct min", f"{li['left_acct_min']:,.0f}", SNP)
        add("snap left acct median", f"{li['left_acct_median']:,.0f}", SNP)
        add("snap left losers", pct(li["left_losers_pct"], 1), SNP)
        add("snap frame losers", pct(li["frame_losers_pct"], 1), SNP)
        add("snap panel left pct", pct(li["panel_left_pct"], 1), SNP)
        tv = fb["turnover"]
        add("snap weeks", f"{tv['weeks_between']:.0f}", SNP)
        for tag, key in (("all", "all"), ("screened", "screened"), ("unscreened", "unscreened")):
            bl = tv.get(key) or {}
            if "excess_median" not in bl:
                continue
            add(f"snap {tag} n", f"{bl['n']:,}", SNP)
            add(f"snap {tag} idle", pct(bl["traded_nothing_pct"], 1), SNP)
            add(f"snap {tag} charged idle", pct(bl["charged_but_idle_pct"], 1), SNP)
            add(f"snap {tag} excess", f"{bl['excess_median']:.3f}", SNP)
            add(f"snap {tag} excess bp", f"{bl['excess_bp_median']:.1f}", SNP)
            add(f"snap {tag} overstates", pct(bl["overstates_pct"], 1), SNP)
            add(f"snap {tag} proxy median", f"{bl['pred_median']:.3f}", SNP)
            if bl.get("ratio_median_if_traded") is not None:
                add(f"snap {tag} ratio traded", f"{bl['ratio_median_if_traded']:.2f}", SNP)

    # ---- the market exposure of each arm of a headline comparison
    if os.path.exists(pol_path):
        for lab, tag in (("screen_big", "screen big"), ("screen_risk", "screen risk"),
                         ("rank_open", "rank open"), ("rank_big", "rank big")):
            rec = (pol.get("disjoint", {}).get("gains") or {}).get(lab) or {}
            if "beta_diff" in rec:
                add(f"{tag} beta a", f"{rec['beta_a']:.2f}", POL)
                add(f"{tag} beta b", f"{rec['beta_b']:.2f}", POL)
                add(f"{tag} beta diff", minus(f"{rec['beta_diff']:.2f}"), POL)
                add(f"{tag} alpha a", pct(rec["alpha_a_annual_pct"], 0), POL)
                add(f"{tag} alpha b", pct(rec["alpha_b_annual_pct"], 0), POL)
                add(f"{tag} beta weeks", rec["beta_weeks"], POL)

    # ---- whether a leader's return decays as the capital behind him grows
    cap_path = "out/or/capacity.json"
    if os.path.exists(cap_path):
        import math as _m
        cp = json.load(open(cap_path, encoding="utf-8"))
        CAP = "or_capacity (or_journal/capacity.py on data/hl_panel)"
        w, nl, pm, ev = cp["within"], cp["null"], cp["null_permuted"], cp["event"]
        add("cap leaders", f"{cp['leaders']:,}", CAP)
        add("cap checked", f"{cp['returns_cross_checked']:,}", CAP)
        add("cap min weeks", cp["min_weeks"], CAP)
        add("cap obs", f"{w['obs']:,}", CAP)
        add("cap weeks", w["weeks"], CAP)
        add("cap beta", minus(f"{w['beta']:.4f}"), CAP)
        add("cap t", sg(w["t"]), CAP)
        # the same slope in a unit a reader can hold: a tenfold larger account
        ten = _m.log(10.0)
        add("cap decade", pct(100 * ten * w["beta"], 1), CAP)
        add("cap null median", minus(f"{pm['median']:.4f}"), CAP)
        add("cap null low", minus(f"{pm['low']:.4f}"), CAP)
        add("cap null high", minus(f"{pm['high']:.4f}"), CAP)
        add("cap null decade", pct(100 * ten * pm["median"], 1), CAP)
        add("cap null sims", pm["sims"], CAP)
        add("cap sim median", minus(f"{nl['median']:.4f}"), CAP)
        add("cap sim low", minus(f"{nl['low']:.4f}"), CAP)
        add("cap sim high", minus(f"{nl['high']:.4f}"), CAP)
        add("cap ratio", f"{pm['median'] / w['beta']:.1f}", CAP)
        if ev.get("events", 0) >= 10:
            add("cap events", f"{ev['events']:,}", CAP)
            add("cap event leaders", ev["leaders"], CAP)
            add("cap event before", pct(100 * ev["mean_before"], 2), CAP)
            add("cap event after", pct(100 * ev["mean_after"], 2), CAP)
            add("cap event change", pct(100 * ev["change"], 2), CAP)
            add("cap event t", sg(ev["t"]), CAP)
            add("cap event window", ev["window_weeks"], CAP)
            add("cap inflow pct", pct(100 * ev["inflow_threshold"], 0), CAP)

    # ---- how large the basket should be once leaders die and move together
    sz_path = "out/or/sizing.json"
    if os.path.exists(sz_path):
        sz = json.load(open(sz_path, encoding="utf-8"))
        SZ = "or_sizing (or_journal/sizing.py on out/or/facts.json)"
        mo = sz["moments"]
        add("size rho", f"{mo['rho']:.4f}", SZ)
        add("size pbar", pct(100 * mo["p_bar"], 1), SZ)
        add("size weeks", mo["weeks"], SZ)
        add("size rep", f"{sz['rep_sharpe']:.3f}", SZ)
        add("size ceiling", sg(sz["ceiling"]), SZ)
        add("size target", pct(100 * sz["target"], 0), SZ)
        add("size k target", f"{sz['k_for_target']:.0f}", SZ)
        add("size k target nomort", f"{sz['k_for_target_no_mortality']:.0f}", SZ)
        add("size attain five", pct(100 * sz["attained_at_five"], 1), SZ)
        add("size attain twenty", pct(100 * sz["attained_at_twenty"], 1), SZ)
        if "predicted_ratio_five_to_twenty" in sz:
            add("size pred ratio", f"{sz['predicted_ratio_five_to_twenty']:.2f}", SZ)
            add("size pred gain", sg(sz["predicted_gain_five_to_twenty"]), SZ)
            add("size meas gain", sg(sz["measured_gain_five_to_twenty"]), SZ)
        one = next((r for r in sz["curve"] if r["k"] == 1), None)
        if one:
            add("size meas share one", pct(100 * one["measured_share_of_ceiling"], 1), SZ)
            add("size model share one", pct(100 * one["model_share_of_ceiling"], 1), SZ)
        big = max(sz["curve"], key=lambda r: r["k"])
        add("size k big", big["k"], SZ)
        add("size meas big", sg(big["measured"]), SZ)
        add("size pred big", sg(big["predicted"]), SZ)

    out = "paper_or/numbers.tex"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    reg.write(out)
    json.dump(reg.manifest(), open("out/or/numbers.json", "w", encoding="utf-8"), indent=1)
    print(f"wrote {out}: {len(reg.entries)} macros")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
