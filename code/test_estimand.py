"""Estimand tests: does the code compute the quantity its name claims?

The point-in-time tests in test_pit.py ask whether a rule can see the future,
and the gate in check_or.py asks whether a printed number came from a run and
whether a run reached the paper. None of the three can see the failure that has
now happened twice: a quantity computed correctly, recorded faithfully and
printed honestly, which is not the quantity the paper says it is.

Both instances were in the maintenance section. The risk term in the band was
measured between the pool's best and worst decile when the band needs the two
leaders either side of the basket's boundary, and the state the boundary lives
in was measured as the spread across the held set when it is the margin between
the best candidate outside and the weakest sleeve inside. In each case the
docstring named the right quantity and the code computed a different one, and a
docstring is not a record.

So each test below builds a case in which the intended quantity and the
plausible wrong one have opposite signs, and asserts which one comes back.

Usage: python or_journal/test_estimand.py
"""
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis import TURNOVER_CAP, basket_fast, turnover  # noqa: E402
from theory import gap_walk, swap_band  # noqa: E402

WEEK = 1000
CAL = {"beta": 1.0, "past_mean": 0.0, "prior": 0.0}


def fail(msg: str) -> None:
    print("  FAIL", msg)
    raise SystemExit(1)


def leader(addr, mean, var, birth=WEEK - 40, last=WEEK + 30, vol=0.0, acct=5e5):
    """A leader whose past weekly returns have a chosen mean and variance."""
    rets, alt = {}, (var ** 0.5)
    for i, w in enumerate(range(birth + 1, last + 1)):
        rets[w] = mean + (alt if i % 2 == 0 else -alt)
    weeks = list(range(birth, last + 1))
    return {"r": {"addr": addr, "rets": rets, "birth": birth, "last": last,
                  "live": set(weeks), "live_sorted": weeks, "funded": 0,
                  "acct_week": {w: acct for w in weeks}, "vlm_frame": vol,
                  "acct_frame": acct, "dead": False},
            "f": {"sharpe": mean / alt if alt else 0.0, "acct": acct, "active": True,
                  "age": WEEK - birth, "worst": mean - alt, "vol": alt, "mean": mean,
                  "n": len(rets)},
            "turn": 1.0}


def test_margin_is_not_the_spread() -> None:
    """The state a swap decides on is the margin at the basket's edge.

    The pool below has a wide spread and a held set that is already the best
    twenty, so the margin must be non-positive. A measurement that returns the
    spread returns something large and positive instead."""
    k = 20
    pool = [leader(f"0x{i:040x}", 0.02 - 0.0008 * i, 0.0004) for i in range(k + 6)]
    w = gap_walk(pool, WEEK, 8, k, CAL)
    if not w:
        fail("gap_walk returned nothing on a pool it should handle")
    spread = max(c["f"]["mean"] for c in pool) - sorted(
        (c["f"]["mean"] for c in pool), reverse=True)[k - 1]
    first = w["margins"][0]
    if first > 0:
        fail(f"the first margin is {1e4 * first:.1f} bp and must not be positive: "
             f"the held set is already the best {k}")
    if abs(first - spread) < 1e-9:
        fail("the margin equals the spread, so the spread is what is being measured")
    print(f"  ok   the margin at the edge is {1e4 * first:+.1f} bp, not the "
          f"{1e4 * spread:+.1f} bp spread across the held set")


def test_risk_term_is_measured_at_the_boundary() -> None:
    """The band's risk term is a difference between two adjacent leaders.

    Here the pool's variance falls with rank, so a decile comparison sees a
    large positive difference, while the leader a swap would take in has lower
    variance than the one it displaces, so the boundary comparison is
    negative."""
    k = 20
    pool = []
    for i in range(70):
        # variance falls steeply with rank, so the pool's top decile minus its
        # bottom decile is strongly positive while rank 21 minus rank 20, which
        # is what a swap exchanges, is negative
        pool.append(leader(f"0x{i:040x}", 0.02 - 0.0003 * i, 0.01 / (1 + i) ** 2,
                           birth=WEEK - 60, last=WEEK + 20))
    rows = [c["r"] for c in pool]
    out = swap_band(rows, [WEEK], k, 0.01, 12, every=1)
    if not out:
        fail("swap_band returned nothing on a pool built for it")
    top = st.mean([0.01 / (1 + i) ** 2 for i in range(7)])
    bot = st.mean([0.01 / (1 + i) ** 2 for i in range(63, 70)])
    if top - bot <= 0:
        fail("the stub pool does not have the variance gradient the test needs")
    if out["delta_var_median"] > 0:
        fail(f"delta_var at the boundary came back {out['delta_var_median']:+.4f}; "
             "on this pool the incoming leader is the less volatile one")
    print(f"  ok   the risk term is measured at the boundary (delta_var "
          f"{out['delta_var_median']:+.4f}), not across the pool")


def test_turnover_divides_by_the_life_the_volume_came_from() -> None:
    """Lifetime volume is reported as of the snapshot, so it has to be divided
    by the life up to the snapshot and not by the age at the decision date."""
    birth, cut, snap = WEEK - 100, WEEK, WEEK + 100
    c = leader("0xa", 0.0, 0.0001, birth=birth, last=snap, vol=1e6, acct=1e5)
    f = dict(c["f"], age=cut - birth)
    got = turnover(c["r"], f, cut, snap)
    right = 1e6 / 1e5 / (snap - birth)
    wrong = 1e6 / 1e5 / (cut - birth)
    if abs(got - wrong) < abs(got - right):
        fail(f"turnover came back {got:.4f}, which is the age-at-the-cut figure "
             f"{wrong:.4f} rather than {right:.4f}")
    if abs(got - min(right, TURNOVER_CAP)) > 1e-9:
        fail(f"turnover came back {got:.4f} and should be {min(right, TURNOVER_CAP):.4f}")
    print(f"  ok   turnover is {got:.4f} a week, over the life the volume came from")


def test_a_stopped_sleeve_costs_nothing() -> None:
    """A sleeve whose leader has stopped earns nothing, and must also mirror
    nothing: charging it turnover would price trading that did not happen."""
    span = 6
    alive = leader("0xa", 0.01, 0.0001, birth=WEEK - 20, last=WEEK + span)
    stopped = leader("0xb", 0.01, 0.0001, birth=WEEK - 20, last=WEEK + 2)
    for m in (alive, stopped):
        m["fut"] = [m["r"]["rets"].get(WEEK + i, 0.0) for i in range(1, span + 1)]
        m["wt"] = [1.0 if (WEEK + i) in m["r"]["rets"] or (WEEK + i) not in m["r"]["live"]
                   else 0.0 for i in range(1, span + 1)]
        m["trd"] = [1.0 if (WEEK + i) in m["r"]["rets"] else 0.0 for i in range(1, span + 1)]
        m["turn"] = 2.0
    ser, turn = basket_fast([alive, stopped], span)
    if abs(turn[0] - 2.0) > 1e-9:
        fail(f"both sleeves trade in week 1, so turnover should be 2.0 and is {turn[0]}")
    if turn[-1] >= 2.0 - 1e-9:
        fail(f"one sleeve has stopped by the last week, so turnover must fall below "
             f"2.0 and it is {turn[-1]}")
    print(f"  ok   turnover falls from {turn[0]:.2f} to {turn[-1]:.2f} as a sleeve stops")


def main() -> int:
    print("ESTIMAND TESTS")
    test_margin_is_not_the_spread()
    test_risk_term_is_measured_at_the_boundary()
    test_turnover_divides_by_the_life_the_volume_came_from()
    test_a_stopped_sleeve_costs_nothing()
    print("  every quantity computes what its name claims")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
