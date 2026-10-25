"""Point-in-time tests: a rule must not be able to see the week it is judged on.

Three checks, each of which fails loudly if the pipeline regains a look-ahead.
They run on synthetic panels, so they are fast and they do not depend on the
collected data.

  1. A leader's posterior at week w does not move when his return in week w, or
     in any later week, is changed. This is the property the index rule of
     Section 9 needs and the one that is easiest to lose while editing.
  2. The candidate pool at a decision date does not move when the returns after
     that date are changed. This is the defect the first round of review found.
  3. A basket's weekly series treats the three states apart: a stopped leader
     contributes a zero and no cost, an unmeasurable week contributes nothing,
     and the rest contribute their return.

Usage: python or_journal/test_pit.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis import MIN_WEEKS, basket_fast, pool_at  # noqa: E402
from policy import calibrate, posteriors_at  # noqa: E402

WEEK = 1000


def make_leader(addr: str, birth: int, last: int, seed: int, acct: float = 5e5,
                dust: tuple = None) -> dict:
    """`dust` is an inclusive range of weeks in which the account holds nothing,
    which is how an account that stops and is funded again looks in the panel."""
    rng = random.Random(seed)
    weeks = list(range(birth, last + 1))
    if dust:
        weeks = [w for w in weeks if not (dust[0] <= w <= dust[1])]
    rets = {w: rng.gauss(0.01, 0.08) for w in weeks if w - 1 in weeks}
    return {"addr": addr, "acct_frame": acct, "acct_week": {w: acct for w in weeks},
            "vlm_frame": acct * 10, "pnl_frame": 0.0, "birth": weeks[0], "last": weeks[-1],
            "acct_last": acct, "rets": rets, "rets_start": dict(rets), "rets_mid": dict(rets),
            "live": set(weeks), "live_sorted": weeks,
            "cap_lo": 0, "cap_hi": 0, "funded": 0, "thin": 0, "capped": 0,
            "stale": 0, "dead": False}


def panel(n: int = 80, birth: int = WEEK - 60, last: int = WEEK + 26) -> list:
    return [make_leader(f"0x{i:040x}", birth, last, i) for i in range(n)]


def fail(msg: str) -> None:
    print("  FAIL", msg)
    raise SystemExit(1)


def test_posterior_is_blind_to_the_future() -> None:
    rows = panel()
    cut = WEEK
    cand = [{"r": r, "f": {"age": cut - r["birth"], "sharpe": 0.0}, "turn": 1.0} for r in rows]
    cal = calibrate(cand, cut)
    base = posteriors_at(cand, cut, cal)
    victim = rows[0]["addr"]
    for w in (cut, cut + 1, cut + 13):
        rows2 = panel()
        rows2[0]["rets"][w] = 5.0                     # an enormous week, later than the posterior
        cand2 = [{"r": r, "f": {"age": cut - r["birth"], "sharpe": 0.0}, "turn": 1.0} for r in rows2]
        after = posteriors_at(cand2, cut - 1, cal)
        before = posteriors_at(cand, cut - 1, cal)
        if abs(after[victim] - before[victim]) > 1e-12:
            fail(f"a return in week {w} moved the posterior computed at week {cut - 1}")
    print("  ok   the posterior at a week ignores that week and every later one")


def test_pool_is_blind_to_the_future() -> None:
    rows = panel()
    cut = WEEK
    a = pool_at(rows, cut, cut + 26)
    rows2 = panel()
    for r in rows2[:20]:                              # twenty leaders stop right after the date
        r["last"] = cut + 1
        r["rets"] = {w: v for w, v in r["rets"].items() if w <= cut + 1}
    b = pool_at(rows2, cut, cut + 26)
    if len(a) != len(b):
        fail(f"the pool changed from {len(a)} to {len(b)} when only the future changed")
    fa = {c["r"]["addr"]: c["f"]["sharpe"] for c in a}
    fb = {c["r"]["addr"]: c["f"]["sharpe"] for c in b}
    if fa != fb:
        fail("a feature at the decision date moved when the future changed")
    print("  ok   the candidate pool and its features ignore what happens after the date")


def test_three_states() -> None:
    cut, end = WEEK, WEEK + 4
    alive = make_leader("0xa", cut - 20, end, 1)
    stopped = make_leader("0xb", cut - 20, cut + 1, 2)
    gapped = make_leader("0xc", cut - 20, end, 3)
    del gapped["rets"][cut + 2]                       # alive, but one week cannot be measured
    rows = [alive, stopped, gapped]
    pool = pool_at(rows, cut, end)
    if len(pool) != 3:
        fail("a leader with a gap was dropped from the pool")
    by = {c["r"]["addr"]: c for c in pool}
    if by["0xb"]["wt"][2] != 1.0 or by["0xb"]["trd"][2] != 0.0:
        fail("a stopped sleeve should carry weight with no trading")
    if by["0xc"]["wt"][1] != 0.0:
        fail("an unmeasurable week should carry no weight")
    ser, turn = basket_fast(list(by.values()), 4)
    # in week cut+2 the gapped sleeve is absent and the stopped one is a zero
    w3 = (alive["rets"][cut + 2] + 0.0) / 2.0
    if abs(ser[1] - w3) > 1e-12:
        fail(f"the week's average was {ser[1]} and should have been {w3}")
    if turn[1] <= 0:
        fail("the trading sleeve should carry its turnover")
    print("  ok   the three states of a sleeve are kept apart")


def test_a_revival_does_not_count_as_being_alive() -> None:
    """The defect the third round of review found: an account that is dust at
    the decision date and funded again afterwards must not be a candidate, and
    must not carry a posterior while it is dust."""
    cut = WEEK
    rows = panel(n=60)
    revived = make_leader("0xdead", cut - 60, cut + 26, 99, dust=(cut - 15, cut + 5))
    rows.append(revived)
    pool = pool_at(rows, cut, cut + 26)
    if any(c["r"]["addr"] == "0xdead" for c in pool):
        fail("an account that was dust at the decision date entered the pool "
             "because it was funded again afterwards")
    cand = [{"r": r, "f": {"age": cut - r["birth"], "sharpe": 0.0}, "turn": 1.0} for r in rows]
    cal = calibrate(cand, cut)
    for w in (cut - 10, cut, cut + 3):
        post = posteriors_at(cand, w, cal)
        if abs(post["0xdead"]) > 1e-12:
            fail(f"a dust account carried a posterior of {post['0xdead']} in week {w}")
    # and in the basket its weeks of dust are a zero, not a gap
    entry = [c for c in pool_at([revived], cut - 30, cut + 26)]
    if entry:
        e = entry[0]
        i = (cut - 10) - (cut - 30) - 1
        if e["wt"][i] != 1.0 or e["trd"][i] != 0.0:
            fail("a week at dust should earn nothing and mirror nothing")
    print("  ok   an account that revives after the date is not alive at it")


def main() -> int:
    print("POINT-IN-TIME TESTS")
    test_posterior_is_blind_to_the_future()
    test_pool_is_blind_to_the_future()
    test_three_states()
    test_a_revival_does_not_count_as_being_alive()
    print("  all point-in-time tests passed")
    return 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
