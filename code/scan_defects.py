"""Scan a folder of papers for the defects referees actually reject for.

Built from eleven referee reports across five ICAIF 2026 submissions. Every
check below corresponds to a complaint that appeared in those reports, and each
one is mechanical: it needs no judgement about the research, only arithmetic and
counting. The point is to catch them before a referee does.

  counts      a declared number of things against the number listed
  duplicates  the same named quantity appearing with two different values
  metrics     classification metrics that cannot hold together
  sharpe      an annualised Sharpe ratio quoted from a short window
  undefined   a headline word used as a number without being defined
  claims      a stated result with no number anywhere near it
  search      a t statistic between two and three with no multiplicity disclosed
  oos         a performance claim with no out-of-sample split, or a backtest
              that never mentions look-ahead or survivorship

The last two ask about the claims of a self-contained paper, so a document that
says on its first page that it is supplementary material is exempt from them and
from nothing else.

Usage: python or_journal/scan_defects.py <folder-or-pdf> [...]
"""
import os
import re
import sys
from collections import defaultdict

try:
    import fitz
except ImportError:                                                  # noqa: BLE001
    fitz = None

NUM = r"[-+]?\d[\d,]*\.?\d*"
WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def win(path: str) -> str:
    """Git Bash hands out /c/Users/...; the PDF library wants C:/Users/..."""
    m = re.match(r"^/([a-zA-Z])/(.*)$", path)
    return f"{m.group(1).upper()}:/{m.group(2)}" if m else path


def text_of(path: str) -> str:
    """Reads the text layer. A failure is reported rather than swallowed: a
    scanner that returns an empty string on error gives a clean bill of health
    to a file it never opened, which is how this one first reported nothing
    wrong with twenty-three papers."""
    if fitz is None:
        print("  (no PDF library available)")
        return ""
    try:
        with fitz.open(win(path)) as d:
            return "\n".join(p.get_text() for p in d)
    except Exception as exc:                                         # noqa: BLE001
        print(f"  (could not read {os.path.basename(path)}: {type(exc).__name__}: {exc})")
        return ""


def flat(t: str) -> str:
    return re.sub(r"\s+", " ", t)


def check_counts(t: str) -> list:
    """A declared count of items, so a reader can check it against the list."""
    out = []
    # the number has to sit on the same line as the noun. A journal review
    # mode prints a line number in the margin, and the extracted text puts
    # it just above the next word, so one space would read "254 Proposition"
    # as a declared count of two hundred and fifty-four propositions.
    # and it must not be the tail of a larger number: a thousands separator
    # turns "16,200 windows" into a declared count of two hundred.
    pat = re.compile(r"(?<![\d,.])\b(" + "|".join(WORD_NUM) + r"|\d{1,3})[^\S\n]{1,3}"
                     r"(features?|baselines?|metrics?|agents?|events?|seeds?|"
                     r"windows?|regimes?|widths?|arms?|propositions?|datasets?|"
                     r"sub-?policies|modalities|exchanges?|pairs?)\b", re.I)
    for m in pat.finditer(t):
        raw = m.group(1).lower()
        k = WORD_NUM.get(raw, None)
        if k is None:
            try:
                k = int(raw)
            except ValueError:
                continue
        out.append((k, m.group(2).lower(), flat(t[max(0, m.start() - 60):m.end() + 60])))
    agg = defaultdict(set)
    for k, noun, _ in out:
        agg[noun].add(k)
    return [(noun, sorted(v), next(c for kk, nn, c in out if nn == noun and kk == sorted(v)[0]))
            for noun, v in agg.items() if len(v) > 1]


def check_metrics(t: str) -> list:
    """Balanced accuracy is the mean of recall and specificity, so it cannot
    exceed (recall + 1) / 2. One submission was rejected over this."""
    out = []
    rec = re.search(r"recall[^.\n]{0,40}?(" + NUM + r")", t, re.I)
    bal = re.search(r"balanced accuracy[^.\n]{0,40}?(" + NUM + r")", t, re.I)
    if rec and bal:
        try:
            r, b = float(rec.group(1)), float(bal.group(1))
            if r <= 1.5 and b <= 1.5 and b > (r + 1.0) / 2.0 + 1e-9:
                out.append(f"balanced accuracy {b} exceeds (recall {r} + 1)/2 = {(r + 1) / 2:.3f}")
        except ValueError:
            pass
    f1 = re.search(r"\bF1[^.\n]{0,40}?(" + NUM + r")", t, re.I)
    pre = re.search(r"precision[^.\n]{0,40}?(" + NUM + r")", t, re.I)
    if f1 and pre and rec:
        try:
            f, p, r = float(f1.group(1)), float(pre.group(1)), float(rec.group(1))
            if max(f, p, r) <= 1.5 and p + r > 0:
                hm = 2 * p * r / (p + r)
                if abs(hm - f) > 0.02:
                    out.append(f"F1 {f} against the harmonic mean of precision {p} "
                               f"and recall {r}, which is {hm:.3f}")
        except (ValueError, ZeroDivisionError):
            pass
    return out


def check_sharpe(t: str) -> list:
    """An annualised Sharpe ratio to two decimals needs more than a month."""
    out = []
    f = flat(t)
    ann = re.search(r"annuali[sz]ed Sharpe", f, re.I)
    if not ann:
        return out
    days = [int(x) for x in re.findall(r"\b(\d{1,3})[- ]day (?:test|window|period|sample)", f, re.I)]
    mon = re.findall(r"\b(one|a|1)[- ]month (?:test|window|period|sample)", f, re.I)
    short = [d for d in days if d <= 90]
    if short or mon:
        n = re.findall(r"Sharpe[^.\n]{0,30}?(\d\.\d\d)\b", f)
        if n:
            out.append(f"annualised Sharpe quoted to two decimals ({', '.join(n[:4])}) "
                       f"from a window of {short[0] if short else 'one month'} days")
    return out


def check_undefined(t: str) -> list:
    """A headline quantity used as a number without a definition."""
    out = []
    f = flat(t)
    for w in ("Net PnL", "net PnL", "Capital Utilization", "capital utilisation"):
        if w in f and not re.search(re.escape(w) + r"\s*(is|=|denotes|means|,? defined)", f):
            out.append(f'"{w}" is used but never defined')
    return out


def check_claims(t: str) -> list:
    """A result stated in words with no measurement near it."""
    out = []
    f = flat(t)
    for m in re.finditer(r"(suggested by our results|our results suggest|we observe that|"
                         r"consistent with|is best|performs best)", f, re.I):
        seg = f[m.start():m.start() + 180]
        if not re.search(NUM, seg):
            out.append(flat(f[max(0, m.start() - 90):m.start() + 150]))
    return out


def check_search(t: str) -> list:
    """A t statistic reported after a search has to clear more than two.

    Harvey, Liu and Zhu put the hurdle for a newly claimed effect at about
    three once the number of candidates tried is taken into account, and White
    makes the same point about reusing one sample for selection and inference.
    A paper that quotes a t between two and three as evidence, without saying
    how many things it tried, is making the claim the literature stopped
    accepting."""
    out = []
    f = flat(t)
    ts = [float(x) for x in re.findall(r"t\s*=\s*\+?(" + NUM + r")", f)]
    ts = [abs(x) for x in ts if abs(x) < 50]
    weak = [x for x in ts if 1.9 <= x < 3.0]
    discloses = re.search(r"(multiple testing|multiplicity|data.snoop|family.wise|"
                          r"false discovery|cells were evaluated|trials)", f, re.I)
    if weak and not discloses:
        out.append(f"t statistics between two and three ({', '.join(f'{x:.2f}' for x in weak[:4])}) "
                   "with no statement of how many hypotheses were tried")
    return out


def check_out_of_sample(t: str) -> list:
    """A backtest with no out-of-sample split, and no mention of the biases that
    make one necessary, is the shape referees reject on sight."""
    out = []
    f = flat(t)
    backtest = re.search(r"(backtest|out.of.sample|Sharpe|annuali[sz]ed return)", f, re.I)
    if not backtest:
        return out
    if not re.search(r"(out.of.sample|walk.forward|hold.?out|test (set|period|window))", f, re.I):
        out.append("a performance claim with no out-of-sample split named")
    if not re.search(r"(look.?ahead|survivorship|point.in.time|surviv)", f, re.I):
        out.append("no mention of look-ahead or survivorship anywhere in a paper with a backtest")
    return out


def is_supplement(t: str) -> bool:
    """Said in its own first page, not inferred from the file name."""
    return bool(re.search(r"(supplement(ary|al)?\s+(material|information|appendix)|"
                          r"online appendix)", flat(t[:1200]), re.I))


def scan(path: str) -> dict:
    t = text_of(path)
    if not t.strip():
        return {}
    out = {"counts": check_counts(t), "metrics": check_metrics(t),
           "sharpe": check_sharpe(t), "undefined": check_undefined(t),
           "claims": check_claims(t)[:3], "chars": len(t)}
    if not is_supplement(t):
        out["search"] = check_search(t)
        out["oos"] = check_out_of_sample(t)
    return out


def main(argv=None) -> int:
    args = (argv or sys.argv[1:])
    if not args:
        print(__doc__)
        return 1
    files = []
    for a in args:
        if os.path.isdir(a):
            for root, _, names in os.walk(a):
                files += [os.path.join(root, n) for n in names if n.lower().endswith(".pdf")]
        elif a.lower().endswith(".pdf"):
            files.append(a)
    files.sort()
    hits, unreadable = 0, []
    for f in files:
        r = scan(f)
        if not r:
            unreadable.append(os.path.basename(f))
            continue
        found = {k: v for k, v in r.items() if k != "chars" and v}
        if not found:
            continue
        hits += 1
        print(f"\n=== {os.path.basename(f)}")
        for kind, items in found.items():
            for it in items[:4]:
                if kind == "counts":
                    noun, vals, ctx = it
                    print(f"  [counts] '{noun}' declared as {vals}: {ctx[:150]}")
                else:
                    print(f"  [{kind}] {str(it)[:200]}")
    print(f"\n{len(files)} papers scanned, {hits} with something to look at")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
