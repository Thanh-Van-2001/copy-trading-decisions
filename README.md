# Which copy-trading decision pays — replication package

Code, data and run records for:

> **Screening beats ranking: the value of five copy-trading decisions on a perpetual futures exchange.**
> Thanh Van Nguyen and Wai Kin (Victor) Chan.
> Tsinghua Shenzhen International Graduate School / Tsinghua-Berkeley Shenzhen Institute.

A copy-trading investor makes five choices: whom to admit as a candidate, how
to rank the admitted, how many to hold, what to do when one of them stops, and
how much capital each one gets. The paper measures what each is worth on the
same panel, against the same objective, net of cost and over a grid of cost
levels. They are not of comparable size.

## What is here

```
code/            the pipeline, one file per step (see code/README.md)
run_records/     the JSON each step writes; every number in the paper comes from these
numbers.tex      the macro file the manuscript reads — 2,207 macros, one per figure quoted
data/            the inputs (see below)
```

Every number printed in the manuscript is generated from `run_records/` into
`numbers.tex`. A number typed into the LaTeX by hand fails the build, which is
checked by `code/check_or.py` along with eleven other gates.

## The data

`data/hl_panel.tar.gz` — one JSON per sampled account, 2,491 of them, as
returned by Hyperliquid's public `info` endpoint: the account-value and
cumulative-profit histories plus the lifetime aggregates the venue publishes.

`data/hl_frames.tar.gz` — two snapshots of the venue's public leaderboard
address list, taken 2026-10-16 and 2026-10-19. The second exists to test two of
the paper's own stated limitations; see Section 13 of the manuscript.

`data/fills.json`, `data/bench.json` — pooled fee statistics from public fills,
and the BTC and ETH benchmark series.

All of it is public, pseudonymous, on-chain data. Accounts appear only under
the addresses the venue itself publishes. No proprietary feed and no personal
data were used, and nothing here identifies a person.

The sampling frame is deliberately **not** a league table. 47.4% of the
accounts drawn lost money over their lifetime. Databases of surviving managers
overstate both returns and lifespans, which is the mistake this frame exists to
avoid.

## Reproducing

Python 3.11+ with `numpy`, `pandas`, `pyarrow`, `matplotlib`, `pymupdf`, and a
TeX installation providing `latexmk`.

```bash
tar -xzf data/hl_panel.tar.gz -C data/
tar -xzf data/hl_frames.tar.gz -C data/

python code/panel.py            # weekly equity paths from the raw records
python code/analysis.py         # the primitives -> run_records/facts.json
python code/policy.py           # the decision surface -> run_records/policy.json
python code/capacity.py         # the capacity test  -> run_records/capacity.json
python code/sizing.py           # Proposition 5 priced on the moments
python code/weights.py          # the fifth choice
python code/make_numbers_or.py  # all of the above -> numbers.tex
```

`code/theory.py` solves the maintenance boundary by backward induction on the
measured innovations. `code/figures.py` draws the figures at 600 dpi.

One caveat on `code/check_or.py`: it imports a shared library of ours
(`paperengine`) for the number registry, the reference checker and the prose
checker, and that library is not in this repository, so the gate will not run
as given. Everything it guards is reproducible without it — the steps above
regenerate `numbers.tex` from the run records, and `code/verify_primary.py`,
`code/test_pit.py` and `code/test_estimand.py` stand alone.

Two synthetic suites run before the paper compiles. `code/test_pit.py` fails if
any rule regains the ability to use information from the week it is judged on.
`code/test_estimand.py` fails if a quantity stops computing what its name
claims: each case is built so the intended quantity and the plausible wrong one
have opposite signs.

## A note on what the paper does and does not claim

The decision surface was searched over 221 cells on 26 weekly observations
each, and a rule with no edge reaches a Sharpe ratio of +5.83 at the 95th
percentile of its maximum. The paper therefore claims a direction and never a
location, applies the multiple-testing hurdle the literature proposes for a
newly claimed effect to its own statistics, and reports that one of four
differences clears it. The panel is one venue over a rising market. The
limitations section states this at length, and `code/frame_bias.py` converts
two of those limitations into measurements — one of which runs against the
comparison it is used in.

## Licence

Code under the MIT licence (`LICENSE`). The data files are redistributions of
public on-chain records and carry no additional restriction from us.
