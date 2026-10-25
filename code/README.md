# Screening beats ranking — research record

One command regenerates everything from the collected panel:

    sh or_journal/run_all_or.sh

| Step | Script | Output |
|---|---|---|
| Draw the sample and fetch each account's public portfolio history | `collect_panel.py` | `data/hl_panel/*.json`, `draw.json` (frame, seed, stratification) |
| Fetch the market benchmark on the paper's weekly grid | `collect_bench.py` | `data/hl_bench/bench.json` |
| Measure what the venue charges, on the panel's own accounts | `collect_fills.py` | `data/hl_fills/fills.json` |
| Take a second snapshot of the sampling frame | `collect_frame.py` | `data/hl_frames/leaderboard_<date>.parquet` |
| Compute every primitive the paper prints | `analysis.py` | `out/or/facts.json` |
| Calibrate the two propositions from those primitives | `theory.py` | `out/or/theory.json` |
| Replay the rules at several decision dates | `policy.py` | `out/or/policy.json` |
| Measure the listing rule and price the turnover proxy | `frame_bias.py` | `out/or/frame_bias.json` |
| Weight the same basket four ways, point in time | `weights.py` | `out/or/weights.json` |
| Draw the seven figures from those records | `figures.py` | `paper_or/figures/*.pdf` |
| Turn the records into LaTeX macros | `make_numbers_or.py` | `paper_or/numbers.tex` |
| Print every rule the pipeline ran | `make_appendix.py` | `paper_or/appendix_rules.tex` |
| Build and gate both documents | `check_or.py` | point-in-time tests, build, citations, numbers, pairing, constants, defect scan, cover letter, reserve audit, prose |
| The point-in-time tests the gate runs first | `test_pit.py` | four synthetic checks |
| The estimand tests it runs beside them | `test_estimand.py` | four cases where the wrong quantity has the opposite sign |
| The defect scan it runs on the built PDF | `scan_defects.py` | the checks eleven referees rejected five related papers for |

## Rules the pipeline enforces

Every number in the paper is a macro traced to a run record; a number typed by
hand fails the gate. Every reference is checked against Crossref before it is
cited. Every screen uses only what was observable at the decision date, and
nothing about what happened after a decision date may enter the candidate set.
A figure reported gross of the copying cost must be reported net of it as well,
which the `pairing` step of the gate checks: an earlier draft defined the net
column and printed only the gross one. And no rule may see the week it is judged
on, which `test_pit.py` checks on synthetic panels rather than on faith: a
leader's posterior must not move when a later return changes, the candidate pool
must not move when the future changes, and the three states of a sleeve must stay
apart. The gate runs those tests before it builds.

## What changed after the first review round

The first draft had two defects that moved every headline number, and both are
fixed in the code rather than in the prose.

1. **Post-decision survival in the candidate set.** `analysis.py` admitted a
   leader only if he had at least eight weekly returns *after* the decision
   date, and `policy.py` required returns inside the holding window. No investor
   can apply that filter. The pool at the paper's decision date went from 715
   leaders to 1,125, the share who stop during the window went from 7% to 55%,
   and the rank correlation inside the recommended screen fell from +0.21 to
   roughly zero, which reversed the first draft's second contribution.
2. **A gross objective for a net problem.** Equation (1) charges a copying cost
   and the first draft reported every number gross of it. Net of cost the
   ordering of the screens changes, diversification stops paying, and the
   account-size screen replaces the risk-history screen as the one that works.

Smaller corrections in the same pass: returns are now flow-adjusted (Modified
Dietz) rather than divided by start-of-week equity; turnover is divided by the
leader's age rather than by 52 and its cap is declared and reported; the
decision surface stores net values and runs to the size of the screened set;
Sharpe ratios carry Lo (2002) standard errors and the search carries a
best-of-N null; a stop is detected with a four-week lag; and rules are compared
on three non-overlapping windows as well as five overlapping ones.

## What changed after the second review round

Round two confirmed both round-one fixes in the code and found three more defects,
all of which moved numbers rather than only wording.

1. **A sleeve had two states where it needed three.** A week with no measurement
   was filled with a zero return and still charged the copying cost, whether the
   leader had stopped or was still trading with an account too small to measure.
   Of the weeks candidates do not report at the decision date, 69.8% are gaps of
   the second kind. A stopped sleeve now earns nothing and costs nothing; an
   unmeasurable week now carries no weight. This moved the sizing result from
   "diversification costs Sharpe" to "diversification is worth about nothing",
   which was the honest answer all along.
2. **The turnover proxy mixed spans.** Lifetime volume is reported as of the
   snapshot, and it was divided by the account's age at the *decision date*,
   which overstates turnover by roughly (age + 26)/age. It is now divided by the
   life the volume was actually accumulated over.
3. **Three numbers in the record contradicted the text and were not printed.**
   The profile in the account floor is not strictly monotone; the deterministic
   ranking rules had a percentile inside the matching random draws that was
   computed and never reported; and the variance decomposition quoted was the
   overlapping grid, while the disjoint grid reverses it. All three are now in
   the paper, and the claim of a "structural result" has been withdrawn.

The round also forced the paper's second claim to be restated. Gross of the
copying cost the account screen earns 58 bp a week and the risk screen earns
-9 bp, while on the net Sharpe ratio the risk screen looks better before cost
and worse after it. One screen buys return, the other buys a lower variance, and
every difference in Section 9 is now reported gross as well as net.

## What changed after the third review round

Round three attacked the model section added after round two, and the attack
landed. Three reviewers re-ran the pipeline and two of them reproduced a result
that contradicted the paper.

1. **Proposition 1 was stated for the wrong policy class.** Its proof needs the
   basket to be a uniform draw, so that the mean edge does not depend on the
   basket size. Every rule the paper recommends orders the candidates instead,
   and under ordering the mean edge falls as the basket grows. The proposition
   now carries both hypotheses explicitly, the sentence claiming the basket size
   is not a decision at all is withdrawn, and the test it predicts is run out of
   sample as the `all` rule, which had been computed at every date and printed
   nowhere.
2. **The index rule's failure was attributed to the wrong cause.** The paper
   said the shrinkage slope was too unstable for the weekly ordering to survive;
   a reviewer pointed out that the slope is one positive scalar per date and
   cannot reorder anything, and verified it by forcing it to 1.0 and getting an
   identical result. The explanation is deleted. In its place the comparison is
   decomposed: changing the ranking statistic costs -0.83 and the weekly churn
   on top of it is worth +0.23, so churn is not what loses the comparison, and
   neither component clears its own noise at five dates.
3. **The band was derived on the mean and the objective is not a mean.** Taking
   the second-order term of the growth criterion adds two risk terms which are
   not divided by the expected remaining life, so they do not shrink with the
   horizon. Calibrated here the cost term is 0.83 bp a week and the risk term
   1,004 bp, because ordering candidates by estimated edge on this venue orders
   them by volatility too. The two halves prescribe opposite policies, and a
   sweep over six band widths spanning four orders of magnitude moves the
   realised objective by half a Sharpe point with the two screens disagreeing
   about which end is better, so the design identifies no width. That sweep is
   now part of `policy.py`.

Smaller corrections in the same pass: the null-maximum sentence quoted the
number of surface cells where it should have quoted the number of trials; the
diversification ceiling is now scoped to a random draw from the unscreened pool,
since chosen baskets exceed it; the shrinkage slope is described as a
consistency check rather than an independent one; the citation for the
maintenance problem moves from the bandit literature to impulse control with
switching costs, because a copier sees every candidate's path whether he copies
him or not, so activation buys no information; and `test_pit.py` now runs before
the build.

## What changed after the fifth pass

Round four ran six reviewers and six claim-sweepers. The worst thing it found
was not a method error but a provenance one, and three further defects of the
family the earlier rounds kept turning up.

1. **The copying cost had a fabricated provenance, and the model behind it was
   wrong in kind.** The paper said 9.5 basis points per side was "measured on
   this venue's own fills"; there were no fills in the repository, no collector,
   and no record field. Worse, the charge was being added to a series that is
   already net of it: over the panel's weeks with a non-zero profit change, the
   account value moves by exactly the reported profit in two thirds of them, to
   a median residual of 1.35e-16 of equity, so the venue's profit series carries
   every charge the venue levies. `collect_fills.py` now measures what can be
   measured, 225,646 fills across 91 accounts and $3.3bn of notional, giving
   2.35 bp per side pooled; the charge in the model is declared an assumed
   *incremental* execution cost; and every comparison is reported over a grid
   from zero to twenty basis points. Eleven of fifteen orderings between screens
   hold at every level, and the account screen overtakes the worst-week screen
   between one and two basis points. That crossover is a stronger claim than the
   point estimate it replaces.
2. **The week an account falls to nothing was booked as a zero return.** The
   venue's own profit series prices it: of 624 such weeks inside the evaluation
   window, 227 were trading losses worse than -20%, median -60%, and only a
   third were clean withdrawals. Returns are now taken over consecutive reported
   weeks rather than consecutive funded ones, so the week a leader blows up
   carries the loss the copier would have taken.
3. **The observation grid is not exactly weekly.** The venue returns a bounded
   number of points per account, so a long life is sampled more thinly: 6.6 days
   per point at the median and 15.7% of steps longer than a week, which are
   dropped rather than interpolated. The density is the same for the screened
   and the unscreened pools, 6.29 against 6.64 days, so the size screen is not
   confounded with it. Both numbers are now in the record.
4. **The band's risk term was measured between the wrong groups.** It compared
   the pool's top and bottom deciles, which is the pool's variance gradient and
   positive by construction, not the two adjacent leaders a swap actually
   exchanges. The paper no longer prints a calibrated width for the risk half,
   and the three sentences that rested on it are gone, including the conclusion's
   last line.

## What changed in the sixth pass

The last five items from round four's list, done directly.

- **Stopping is mostly capital flight.** Of the 955 accounts that stop, 63.8%
  end with a withdrawal and 25.4% with a trading loss; in the median case only
  8.8% of the capital that left was lost rather than taken out. The hazard that
  feeds A(T) is unchanged, since a sleeve stops contributing either way, but the
  prose that read 4.0% a month as how long a strategy lasts is gone.
- **The return convention is settled rather than disclosed.** The three
  denominators can differ only in weeks that move a large share of equity, so on
  the 11.2% of candidates that never have one they agree by construction. There
  the account screen returns +2.07 against +1.77 unscreened, the same sign and
  order as on the whole pool, so the paper's ordering does not come from the
  denominator.
- **The substitutes claim is split into its two mechanisms.** Information: the
  rank correlation inside a past-Sharpe screen is -0.17, so the statistic is
  used up. Turnover: inside the account screen the twenty highest past Sharpe
  ratios turn over 10.8 times their accounts a week against 1.1 for the set, so
  ranking selects for trading as well as for skill, and the gain is reported
  gross as well as net.
- **The allocation dial.** A copier has no dial on a sleeve but does have one on
  the book, so the growth column is a description of the fully invested case
  rather than a second objective.
- **A constants audit in the gate.** Every plain numeric constant in analysis.py
  must appear in a run record. This is the check that would have caught the
  copying cost, which sat in the code as a literal with a comment claiming a
  measurement no file supported, through four rounds of review.

## The maintenance problem, solved rather than posed

Round four's reviewers split on what the model section needed: one asked for a
Whittle index, another pointed out that a bandit is the wrong family here,
because a copier sees every candidate's equity path whether or not he copies
him, so putting capital on a leader buys no information. The second is right,
and what is left is impulse control with a switching cost. `theory.py` now
carries that.

**Proposition 3** proves the inaction region is an interval: the advantage of
acting is strictly increasing in the gap, by induction on the horizon, so there
is a single boundary.

**Proposition 4** brackets that boundary between two measured quantities. The
lower end is the charge a swap must repay, c / A(T). The upper end is the point
at which one more week of information cannot change the answer,
E|eta| A(T-1) / (2 (1-lambda)^T). Calibrated here the bracket runs from 0.83 to
183 basis points a week with twenty-six weeks to run, a factor of 221; from 1.6
to 82 at thirteen weeks; from 4.9 to 20 at four; and the two ends cross at two
weeks remaining, after which break-even is optimal. The gap itself sits at 474
basis points, moves 12.9 a week on average, and drifts by -5.3 with a t of
-1.53, so the martingale assumption Proposition 4 needs is not rejected and what
departure there is runs in the conservative direction.

The bracket predicts the experiment rather than being tested by it. Three of the
six band widths in the sweep lie inside it and two above; nothing separates
them, which is what a bracket two orders of magnitude wide should produce on
five windows. The paper now says that before reporting the sweep rather than
after.

### A scanner for the defects referees reject for

`scan_defects.py` turns the recurring complaints in eleven referee reports into
mechanical checks: a declared count against what is listed, classification
metrics that cannot hold together, an annualised Sharpe ratio quoted from a
month, a headline word used as a number without a definition, and a claim with
nothing measured near it. It takes any folder of PDFs.

Pointed at twenty-three papers in the same research programme it reproduced
three defects that real referees had independently found, which is the evidence
that the checks are the right ones: the 47 declared features against 17 listed,
the "5-10 day lead time suggested by our results" that was never measured, and
an undefined "Net PnL". It also found the same undefined "Net PnL" in a paper
that has not been reviewed yet, and a seed count declared as both three and five
in another.

Pointed at this paper it found two: the contributions list still said "two
propositions" after four were proved, and a sentence that read "Of 12 of 15
pairs of screens". Both are fixed, and the gate now runs the scan on every
build, failing on the checks that have no false positives and reporting the
counting check for a human to read.

One note on the scanner itself. Its first run reported nothing wrong with all
twenty-three papers, because a bare `except` swallowed a path error and returned
an empty string, and a scanner that returns nothing for a file it never opened
reports a clean bill of health. It now prints what it could not read, and the
summary line separates papers found from papers read.

## Lessons taken from reviews of five related submissions

Eleven referees across five ICAIF 2026 submissions rejected or nearly rejected
all five, and their complaints repeat. Each recurring one was checked against
this paper.

**The same object with two values.** One submission was rejected partly because
three headline figures did not reconcile. This paper had the same defect: the
unscreened pool at k=1 read 1.174 in the screen table and 0.993 in the decision
surface, the same data at the same date, differing only by which random baskets
each drew. Cells now seed their generator from their own name, so a cell has one
answer wherever it is computed, and `analysis.py` checks the duplicate cells
against each other and records the result: 8 checked, 0 disagreeing.

**A declared count that does not match what is listed.** Another submission
declared 47 features and listed 17. This paper said "six widths" of the band
after a seventh was added, "two of the six differences change" when one does,
and "the two propositions" after two more were proved. The counts are now
macros generated from the thing they count.

**A claim with no experiment behind it.** One submission asserted a 5-10 day
lead time it never measured. The qualifier pass of the previous round covers
this; the crossover claim in the abstract was rewritten when the data stopped
supporting it, from "the account screen overtakes the worst-week screen between
one and two basis points" to the stronger statement the grid now shows, that it
beats it at every level.

**Hyperparameters chosen on the test set.** Two submissions were caught
reporting a sensitivity analysis whose optimum equalled the figure in the main
table. This paper's thresholds are round numbers fixed in advance and its
decision surface is explicitly disclaimed as unidentified, with the best-of-N
null reported beside it.

**Understating your own result.** One submission claimed 3.6x where its own
numbers gave 7.1x. Worth avoiding in both directions: a number that is wrong in
the author's favour reads as spin, and one wrong against is read as carelessness.

### A qualifier audit

Numbers in this paper are checked by the gate; the words around them are not.
A pass over every comparative phrase against the record found four claims of
"two orders of magnitude" where the record supported one and a half, three, or a
factor of eighty, and one claim with no number behind it at all ("almost half of
the listed accounts have lost money"). The orders of magnitude are now stated as
the factors they are, and the frame description is a run record: 47.4% of the
47,195 listed accounts have lost money over their lifetime, 42.0% hold less than
$100, and the median account is $1,602.

The same pass found a figure that had gone stale against its own result.
`fig_band` drew the switching charge falling with the horizon under the title
"How wide the no-trade band is", while the solved boundary rises with it. It now
draws both, which shows the two meeting in the final week, where waiting is no
longer possible and the charge is the whole answer. And the dependence section
claimed the basket Sharpe ratio "cannot exceed" the covariance limit, while the
paper's own figure showed the measured median at the largest basket a little
above it: the limit bounds the prediction, not a median over draws, and the
sentence now says so and names the overshoot.

### Estimand tests

Two failures in this work were of a kind no gate here could see: a quantity
computed correctly, recorded faithfully and printed honestly, which was not the
quantity the paper said it was. The risk term was measured between the pool's
deciles when the band needs the two leaders either side of the basket's
boundary, and the state that boundary lives in was measured as the spread across
the held set when it is the margin at the edge of it. In both cases the
docstring named the right quantity and the code computed another, and a
docstring is not a record.

`test_estimand.py` builds, for each, a synthetic case in which the intended
quantity and the plausible wrong one have opposite signs, and asserts which one
comes back. It covers the margin against the spread, the risk term at the
boundary against the pool's variance gradient, the turnover span, and whether a
stopped sleeve is charged for trading it did not do. Each test was checked
against a deliberately broken implementation before being trusted: breaking
`gap_walk` to return the spread makes the first test report the 152 basis point
spread it should not, and breaking the turnover span makes the third report the
age-at-the-cut figure. The gate runs the suite before it builds.

### The state the boundary is a boundary in

A boundary is only as good as the state it is compared against, and the first
version of this compared the wrong one. `gap_innovation` measured the spread
from the best leader on the venue to the twentieth, which is large by
construction and is never what a swap decides. What a swap decides is the margin
between the best candidate outside the basket and the weakest sleeve inside it.
`gap_walk` now carries the held set through the window and measures that margin
before each decision.

It changes everything downstream and makes it cohere. The margin sits at 8.5
basis points, is positive in 53.8% of weeks, and moves 52.7 basis points in an
average week, with a drift of +0.96 whose t statistic is 0.04 — the martingale
assumption Proposition 4 needs is as close to exact as 26 weeks can show, where
on the wrong state it had a t of -1.53. The solved boundary rises from 19.4
basis points at one week, where it still reproduces break-even, to 297.9 at
twenty-six, and now lies inside the analytic bracket at five of six horizons.

The economics are then simple and they agree with the data. An overtake of 8
basis points is noise against a weekly movement of 53, so the option of waiting
for it to reverse is worth more than acting on it, and the model says do not
swap. The sweep agrees: never swapping is among the best arms in one family and
the 200 basis point arm in the other.

This also disposes of the repeated-switching objection without building the
machinery for it. The margin immediately after a swap is -3.8 basis points, two
orders of magnitude below the boundary, so a rebalanced basket does not return
to the boundary inside a holding period and the repeated problem collapses to
the single-swap one. That is worth more than a renewal model would have been,
because it says why the complication does not bind.

### The boundary itself

Proposition 3 says the boundary is a single crossing, so the recursion behind it
can be solved rather than bracketed. `solve_boundary` runs backward induction on
a grid in the gap, drawing the weekly change from the 26 innovations measured on
the panel rather than from an assumed law. The answer is 15.0 basis points a
week with twenty-six weeks to run against a switching charge of 0.83, falling to
12.6 at thirteen weeks, 9.4 at four, and 19.4 at one week, where it reproduces
the break-even value of 19.18 to within the grid's 0.4 basis point resolution,
as it must when there is nothing left to wait for. That last agreement is the
check on the solver. The solved boundary lies inside the analytic bracket at
four of six horizons; the two exceptions are the shortest, where the bracket's
upper end degenerates because waiting a week is no longer possible.

`policy.py` then runs a seventh sweep arm at that boundary, falling with the
horizon as the model says it should. It returns +1.05 inside the account screen
with 16 swaps and +1.22 inside the risk screen with 13, which is mid-pack in one
family and near the top in the other. The width the model prescribes cannot be
told apart from widths two orders of magnitude away, which is the sharpest form
of the paper's power statement: not that the wrong band was chosen, but that
five windows of twenty-six weeks cannot distinguish bands at all.

### The risk term, measured properly

`theory.py` now has two functions where it had one. `swap_band` walks the
holding window at each decision date, ranks on what is known by then, and
records the pair either side of the basket's boundary: the weakest sleeve held
against the best candidate outside. Over 58 such pairs at five dates the risk
term has a median of +11 basis points a week and is negative at 48% of them,
with a tenth to ninetieth percentile range of -1,732 to +424, resting on a
median of 15 usable pairs out of 19 because members of one basket share few
weeks of history. The panel cannot sign it, and the paper now says so with that
measurement rather than with an absence. `pool_variance_gradient` keeps the
calculation an earlier version reported as the band: the difference between the
pool's best and worst decile, which is the pool's variance gradient, is positive
by construction, and is not a quantity any swap exchanges.

## What changed after the fourth pass

The fix list from round three held one more defect of the same genus as rounds
one and two, and the structural answer to all three.

1. **A third look-ahead leak, through revival.** A leader counted as active at a
   decision date if his *final* funded week was recent enough. 48.4% of these
   accounts fall to nothing and are funded again later, so between 61 and 188
   leaders per decision date entered the candidate pool holding nothing at that
   date and funded again afterwards. The state of an account is now read week by
   week from its own history. The numbers moved again: candidates 1,125 to
   1,061, unmeasurable candidates 22.8% to 5.0%, and the band rule went from
   losing against a random basket to winning by +0.41. `test_pit.py` could not
   have caught this, because its synthetic leaders had unbroken lives, so it
   gained a fourth test with a leader who holds nothing across the decision date
   and is funded again inside the window. The test was checked against the old
   code and fails on it.
2. **A share of the sum of squares is not a variance decomposition.** With 44
   rules and five dates, pure noise puts 19.6% of the spread on the rules; we
   had reported 13.8% as though it were a finding, and the "disagreement"
   between the two grids was the degrees of freedom changing. Carrying them
   gives F = 48.7 for the date and 1.34 for the rule on one grid, 12.3 and 1.02
   on the other. The two grids agree, and what they agree on is that the choice
   of rule explains nothing this data can detect.
3. **The mechanism, not another point fix.** The gate now audits the record
   against the paper in the other direction: every policy evaluated and every
   paired comparison must appear in the body or in Appendix A, which
   `make_appendix.py` generates from the run record. Of 108 rules and
   comparisons, the body discusses nineteen; the appendix prints all of them.
   The build fails if one is missing from both. That is what closes the hole the
   first three rounds kept finding.

## The model, added after round two

Two propositions, both short, both calibrated from measured quantities rather
than chosen.

1. With average member variance above average pairwise covariance, measured
   here at 0.0377 against 0.0029, the objective is strictly increasing in the
   basket size, so the basket is always as large as the screen allows and the
   two-dimensional problem collapses to one dimension in the screen. The
   prediction is testable and holds in 8 of 8 screens gross and net.
2. The maintenance rule is a no-trade band of width c/A(T), where A(T) is the
   number of the remaining T weeks a leader is expected to go on trading. A
   stopped leader is the case of zero edge, so replacement and rebalancing are
   one rule, and the band widens with the stopping hazard: a venue whose leaders
   die faster calls for less churn, not more.

Calibrated on this panel (hazard 0.93% a week, switch cost 19 bp, shrinkage
slope 0.175 fitted on windows closing before the decision date, whose
correlation of 0.208 independently reproduces the paper's measured rank
correlation of 0.206), the band is 0.83 bp a week, half a per cent of the
pool's estimated edge spread. The policy that follows is run at all five
decision dates in `policy.py` as the `index` rule. It loses: -0.31 against a
random basket and -0.60 against a static ranking. The derivation assumes the
shrinkage is known, and the shrinkage is the one thing that is not stable, which
is where the next piece of work is.

Target venue: International Transactions in Operational Research (Wiley), with
the Journal of the Operational Research Society as the fallback. The draft is
written in `elsarticle` and converts to the publisher's class at submission.

## The fifth decision, measured rather than cited

The paper fixed the weights at 1/k for six drafts and justified it with a
citation: the equally weighted rule beats estimated-optimal weights out of
sample when the moments are noisy. That citation is about asset classes with
decades of history. It says nothing directly about leaders with a median of
fifteen measurable weeks each, and a referee is entitled to ask. `weights.py`
answers it on the paper's own panel.

Three estimated weightings stand against equal weights at the three
non-overlapping decision dates, on the same screened and ordered basket of
twenty the rest of the paper recommends: inverse volatility, long-only
minimum variance, and long-only maximum Sharpe. Every weight is formed from
weeks that close before the decision date and graded on the weeks after it.

The covariance was the whole difficulty, and it is a property of the panel.
No week in the estimation window has all twenty members measurable at once,
so the first version of the script, which asked for complete rows, returned
an empty block and a summary of `{}`. Between eight and nineteen of the
twenty are measurable in a given week and never all of them. So a variance is
estimated on a leader's own measurable weeks, a correlation on the overlap of
its pair, and fifteen of the hundred and ninety pairs whose overlap is
thinner than eight weeks take the median correlation of the pairs that are
estimable. A matrix assembled that way need not be positive semidefinite, so
it is projected onto the nearest one by clipping eigenvalues, then shrunk
towards its diagonal by 0.5.

What it found is worth more than a confirmation would have been. On the
Sharpe ratio the estimated weightings are better in four of six comparisons;
on compound growth they are worse in five of six. The two that use the
covariance matrix rather than only its diagonal are worse on growth in all
four comparisons they appear in, and those are the two that concentrate:
minimum variance inside the account screen holds 11.7 of the twenty and puts
61% of the book on one leader. Concentration raises a ratio and lowers a
geometric mean, so the estimation error the citation is about is here, it is
in the off-diagonal entries, and it shows up in the criterion that compounds.

None of it is claimed. The largest stitched weekly difference reaches
|t| = 1.52, the sign reverses between the two screens, and one of the six
differences changes sign across the three values of the shrinkage. The
section says so, and says that what the experiment settles is the question
rather than the answer.

Three things the paper had outgrown were repaired in the same pass. The band
sweep declared seven widths and listed six, omitting the one the model solves
for; the limitations section still said the optimal boundary was not derived
and was the obvious next piece of work, three pages after the abstract said
it was computed by backward induction; and one hard-coded "Six" survived
where the count is now seven. The first is the declared-count defect
`scan_defects.py` looks for in other people's papers and cannot see through
a macro.

Title, abstract and contributions now declare five choices, because five are
measured.

## Two documents, and a gate that follows the paper into both

The manuscript reached fifty-five pages in the journal's review format. Two
things in it are read by a referee once and by a reader almost never: the four
proofs, whose statements are what the body actually uses, and the tables that
print all hundred and eight rules the pipeline ran. Both moved to
`paper_or/supplement.tex`, which restates each proposition before proving it and
restates the problem once at the top, so it reads on its own. Nothing was
deleted and nothing was moved out of the body that carries an argument: every
measurement, every limitation and the whole of the results stayed.

Main text 51 pages in review format and **36 single-spaced**, of which four are
references; supplement 4 pages. The single-spaced figure is the one that
corresponds to journal pages, and at thirty-two pages of body it needed no
further cutting, so the limitations section was left at its full length.

Moving the appendix broke the reserve audit, which was the right failure: that
step asks whether every rule in the record reaches the reader, and it was
reading one of the two documents the reader now gets. `check_or.py` now builds
both, audits the macros of both, reads both when it asks whether a rule was
printed, and fails a build that leaves a reference undefined in either. The
undefined-reference test reads the document's final `.log` rather than the
accumulated latexmk output, because the first pass of a clean build has
undefined references by construction and grepping the whole stream fails
every time.

`scan_defects.py` exempts a document that says on its own first page that it is
supplementary material from the two checks that ask about a paper's claims, the
out-of-sample split and the multiplicity disclosure, and from nothing else. An
appendix of proofs quotes Sharpe ratios without claiming anything, and a check
that fires on it teaches the reader of the output to ignore it.

## The cover letter was outside the gate, and had drifted

Fixing the length turned up something worse. The cover letter is hand-written,
an editor reads it before the manuscript, and no step was looking at it. Three
of its numbers had gone stale: 223 searched cells against the record's 277, a
null maximum of 5.87 against 5.83, and a pointer to Section 10 for limitations
that are now in Section 12. It also claimed three synthetic tests where there
are two suites of four, and said "the authors" of a single-author paper.

All fixed, and the gate gained a tenth step. `cover()` reads every number in the
letter and fails unless it is a value the run record produced, exempting numbers
that describe the document rather than the data -- section, table and figure
numbers -- and small counts written as digits. Verified by deliberately
breaking it: changing 277 to 219 makes the step name the number and return
false.

## A second snapshot of the frame, and what it cost the paper to look

The paper named two limits it could not measure with one snapshot of the
venue's address list, and said so in both the method and the limitations: the
survival curve was an upper bound because a blown-up, delisted account cannot be
told from a stopped, listed one, and the turnover charge was a lifetime average
because "two snapshots of lifetime volume would bracket a window and identify
the volume traded inside it; one does not."

`collect_frame.py` took the second snapshot on 2026-10-19, fourteen days after
the first, atomically into `data/hl_frames/` and never once opening the first
snapshot for writing, because the first is irreplaceable. `frame_bias.py` then
asks both questions.

**The listing rule does not remove an account for losing money.** Of the 31,788
addresses holding under $100k on the first date, zero left the list. Every one
of the 1,097 that left held at least $100,000.21 -- a boundary sharp enough to
be a rule -- at a median of $111,766, and only 10.8% of them had lifetime losses
against 47.4% of the frame. So an account that blows up stays listed at a value
near zero, which is exactly the state the paper's return equation assigns no
weight rather than a return of zero. That is the mechanism which would have
biased the survival curve, and it does not operate. The caveat weakens but does
not vanish: a later snapshot says nothing about an account delisted before the
first one was taken. What does happen is churn at the top, 7.1% of addresses
above $100k in a fortnight.

**The turnover proxy fails the test, and it fails in the direction that hurts.**
Over the fortnight, 62.9% of the 1,887 matched panel accounts traded nothing at
all, and the proxy charges 54.6% of them anyway. The over-charge is where the
paper said it was, and bigger than the paper implied: a median of 0.015 times
the account a week in the screened set, which is 0.1 basis points, against 20.0
in the unscreened pool, which is 190 basis points, because the median unscreened
candidate's proxy sits at the cap while his realised turnover is zero. Three
orders of magnitude. Since the unscreened pool is the baseline the account screen
is measured against, this *inflates* that screen's net advantage. The paper now
says so, in the method and twice in the limitations, and points the reader at the
gross column -- which is what it already rested that comparison on, so the
conclusion stands and the caution is now a number.

**A statistic that dropped its own worst cases.** The first version of the
measurement reported the ratio of predicted to realised turnover and found a
median of 0.90, which reads as "roughly unbiased". A ratio needs a non-zero
denominator, so that statistic was computed on the 37% of accounts that traded
and silently excluded the 63% the proxy is most wrong about. The aggregate is now
taken in turnover units over every matched account, and the conditional ratio is
reported beside it labelled as conditional. This is the same error the project's
`test_estimand.py` exists to catch, found this time by reading an output that
looked too good.

## Final pass before submission

A weekly Task Scheduler job, "HL frame snapshot (OR paper)", runs
`or_journal/weekly_frame.cmd` every Sunday at 09:00 with StartWhenAvailable, so
a missed Sunday fires when the machine comes back. It appends one dated parquet
and deletes nothing. `collect_frame.py` now refuses to overwrite a snapshot that
already exists, because re-fetching a date would replace a historical record
with different live numbers and the manuscript is pinned to one of those files;
`--force` is there and should almost never be used. The job deliberately does
not run `frame_bias.py`: that stays pinned to the snapshot the manuscript
reports, so no cron can move a number in a submitted paper. Run it with
`--latest` when the revision wants the longer bracket. The chain was validated
by starting the task once, which correctly did nothing.

Three phrases in the paper described the snapshot bracket in words -- "in a
fortnight", "Two weeks", "over that fortnight" -- and would have contradicted
the macros the moment anyone ran the measurement on a longer bracket. The window
length is a measurement and now has a macro, like every other number.

**Reproducibility, checked rather than claimed.** The whole pipeline was rerun
from the collected panel with `run_all_or.sh`, and `numbers.tex` came out byte
for byte identical to the committed file. Ten gate steps pass. Both PDFs have
zero unresolved references and zero unexpanded macros, and the defect scan finds
nothing in either.

**Four pieces of the paper still described a smaller paper.** The introduction
enumerated four choices where the title and abstract now enumerate five, so a
reader arriving from the abstract met a contradiction on the body's first page.
The conclusion opened by saying the problem contains four decisions, never
mentioned the fifth at all -- a referee reading only the conclusion would not
have known the paper measures it -- and still said the turnover proxy could not
be made point in time with one snapshot, three pages after the paper reports
what a second snapshot showed. All four are of one kind, and it is the kind this
project keeps finding: a part written when the paper was smaller, still
describing that paper. The scanner cannot see them, because each is locally
true. Reading the opening and the closing against each other is the only thing
that catches them, and it belongs in every final pass.

When the weekly series reaches twenty-six snapshots the sentence saying the
bracket does not span an evaluation window stops being true, and that is the
moment the turnover charge becomes point in time for real. It is the single
largest improvement still available to this paper.
