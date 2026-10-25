"""The gate for the OR paper: it builds, every number is a macro from a run
record, every reference resolves to a real record, no rule can see the week it
is judged on, and the prose passes the house check.

Usage: python or_journal/check_or.py
"""
import os
import re
import subprocess
import sys

ENGINE = "D:/iclr2027"
sys.path.insert(0, ENGINE)
import io  # noqa: E402
import json  # noqa: E402

from paperengine import provenance, refcheck, style  # noqa: E402

D = "paper_or"
MAIN = "main.tex"
# the reader gets two documents, so the gate audits two
SUP = "supplement.tex"
# the manuscript in the journal's own class, which is the file actually submitted
ITOR = "itor.tex"
FININNOV = "fininnov.tex"
# hand-written literals that are not measurements: the screen thresholds, the
# percentages that name a screen, the year of the frame, the significance level,
# and the authors' postcode, which the journal requires on the title page and
# which no reader could mistake for a result
ALLOW = "0.5,1,5,10,15,20,100,2025,2026,0.05,40,518055"


def with_inputs(name: str) -> str:
    """A document's own source plus whatever it inputs, which is where the
    audits have to look now that the paper comes in two files."""
    path = os.path.join(D, name)
    if not os.path.exists(path):
        return ""
    tex = io.open(path, encoding="utf-8").read()
    for inc in re.findall(r"\\input\{([^}]+)\}", tex):
        sub = os.path.join(D, inc if inc.endswith(".tex") else inc + ".tex")
        if os.path.exists(sub):
            tex += io.open(sub, encoding="utf-8").read()
    return tex


def build() -> bool:
    out, ok = "", True
    # the journal manuscript is derived from main.tex, so regenerate it here
    # rather than trust whatever is on disk to be current
    if subprocess.call([sys.executable, "or_journal/make_fininnov.py"]) != 0:
        print(f"  FAIL {FININNOV} could not be derived from {MAIN}")
        return False
    for doc in (MAIN, SUP, FININNOV):
        if not os.path.exists(os.path.join(D, doc)):
            continue
        subprocess.run(["latexmk", "-C", doc], cwd=D, capture_output=True, text=True)
        r = subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", doc],
                           cwd=D, capture_output=True, text=True)
        out += r.stdout + r.stderr
        if r.returncode != 0:
            print(f"  FAIL {doc} did not build")
            ok = False
        else:
            # the last pass overwrites the .log, so this is the final state
            lg = os.path.join(D, doc.replace(".tex", ".log"))
            txt = io.open(lg, encoding="utf-8", errors="replace").read() if os.path.exists(lg) else ""
            multi = sorted(set(re.findall(r"Label `([^']+)' multiply defined", txt)))
            if multi:
                print(f"  FAIL {doc} defines {len(multi)} label(s) twice: "
                      + ", ".join(multi[:6]))
                print("       a reference to one of these resolves to the wrong target")
                ok = False
            if "There were undefined references" in txt:
                bad = re.findall(r"Reference `([^']+)' on page", txt)
                print(f"  FAIL {doc} leaves {len(set(bad))} reference(s) undefined: "
                      + ", ".join(sorted(set(bad))[:6]))
                ok = False
    open(os.path.join(D, "build.log"), "w", encoding="utf-8").write(out)
    return ok


def citations() -> bool:
    """refcheck, plus the sources the public record does not index.

    Crossref and OpenAlex hold no regulator reports, so refcheck can only
    return NOT_FOUND for one however real it is. verify_primary settles those
    by retrieving the document and finding our own title inside it, which is
    stronger evidence than a Crossref hit, not weaker. A NOT_FOUND is forgiven
    only for a key that verification covers; every other verdict still stands.
    """
    code = refcheck.main([os.path.join(D, "refs.bib"), "--json",
                          "out/or/refcheck.json"])
    rows = json.load(io.open("out/or/refcheck.json", encoding="utf-8"))
    if subprocess.call([sys.executable, "or_journal/verify_primary.py"]) != 0:
        print("   citations: a primary source could not be verified by retrieval")
        return False
    verified = {r["key"] for r in json.load(
        io.open("out/or/primary_sources.json", encoding="utf-8")) if r["ok"]}
    unexplained = [r["key"] for r in rows
                   if r["verdict"] != refcheck.VERDICT_OK
                   and not (r["verdict"] == refcheck.VERDICT_NOT_FOUND
                            and r["key"] in verified)]
    if unexplained:
        print(f"   citations: unresolved -> {', '.join(unexplained)}")
        return False
    if code != 0:
        print(f"   citations: {len(verified)} source(s) carried by retrieval "
              f"instead of the bibliographic record")
    return True


def macros() -> bool:
    """No macro may print its own name where its value belonged.

    A backslash lost in editing turns a macro call into a newline followed by
    the bare word plus braces. That compiles without error, so the build and
    the number audit both pass while the manuscript prints "SnapScreenedExcessBp"
    at a referee. Eleven checks let exactly that reach a submitted PDF, so this
    one reads the compiled text the referee sees, and the sources too, looking
    for the names themselves. CamelCase runs do not occur in English prose,
    which is what makes the search safe.
    """
    defs = io.open(os.path.join(D, "numbers.tex"), encoding="utf-8").read()
    names = set(re.findall(r"BSBSnewcommand\{BSBS(n[A-Za-z]+)\}".replace("BSBS", "\\\\"), defs))
    tails = {n[1:]: n for n in names if len(re.findall("[A-Z]", n)) >= 2}
    bad = []

    text_path = os.path.join("out", "or", "paper_text.txt")
    if os.path.exists(text_path):
        body = io.open(text_path, encoding="utf-8").read()
        for tail, full in sorted(tails.items()):
            if re.search(r"(?<![A-Za-z])" + tail + r"(?![A-Za-z])", body):
                bad.append(f"compiled PDF prints the name {full}")

    for src in ("main.tex", "supplement.tex"):
        path = os.path.join(D, src)
        if not os.path.exists(path):
            continue
        txt = io.open(path, encoding="utf-8").read()
        for tail, full in sorted(tails.items()):
            for m in re.finditer(r"(?<![A-Za-z\\])" + tail + r"\{\}", txt):
                bad.append(f"{src}:{txt[:m.start()].count(chr(10)) + 1} "
                           f"has {tail}{{}} with no backslash-n")

    # A lost backslash also strands a LaTeX command as prose. The giveaway is
    # the tail of the command name followed by a brace, which no English
    # sentence contains: "ef{eq:sizing}" is what \ref becomes when its \r is
    # turned into a carriage return by a careless edit.
    strays = ("ef{", "eqref{", "abel{", "ite{", "itep{", "aragraph{",
              "ection{", "extit{", "mph{", "ncludegraphics{")
    if os.path.exists(text_path):
        body = io.open(text_path, encoding="utf-8").read()
        for frag in strays:
            for m in re.finditer(r"(?<![A-Za-z\\])" + re.escape(frag), body):
                bad.append(f"compiled PDF prints {frag!r} as text: "
                           f"{body[max(0, m.start() - 40):m.start() + 30]!r}")

    # A lone carriage return inside a line is the same accident upstream.
    for src in ("main.tex", "supplement.tex"):
        path = os.path.join(D, src)
        if not os.path.exists(path):
            continue
        raw = io.open(path, encoding="utf-8", newline="").read()
        lone = [i for i, c in enumerate(raw)
                if c == "\r" and raw[i + 1:i + 2] != "\n"]
        for i in lone[:3]:
            bad.append(f"{src} has a lone carriage return at offset {i}: "
                       f"{raw[max(0, i - 40):i + 20]!r}")

    for line in bad[:10]:
        print(f"   {line}")
    if bad:
        print(f"   MACRO CHECK FAILED: {len(bad)} stray name(s) or control character(s)")
        return False
    print(f"   no literal macro names in the compiled text or the sources "
          f"({len(tails)} names searched)")
    return True


def pairing() -> bool:
    """A number reported gross of the copying cost must be reported net of it in
    the same paper. The first draft of this work defined the net column and
    printed only the gross one, which is the kind of selective reporting a gate
    can catch and a reader cannot.
    """
    tex = io.open(os.path.join(D, MAIN), encoding="utf-8").read()
    defined = set(re.findall(r"newcommand\{..([A-Za-z]+)\}",
                             io.open(os.path.join(D, "numbers.tex"), encoding="utf-8").read()))
    used = set(re.findall(r"..n([A-Za-z]+)\{\}", tex))
    used &= defined
    bad = []
    for m in sorted(used):
        if m.endswith("Gross") and m[:-5] + "Net" not in used:
            bad.append(f"{m} printed without {m[:-5]}Net")
    missing = sorted(m for m in used if m not in defined)
    print(f"  {len(used)} macros printed, {len(defined)} defined, {len(defined) - len(used)} held in reserve")
    for b in bad:
        print("  FAIL", b)
    if missing:
        print("  FAIL undefined:", ", ".join(missing))
    return not bad and not missing


def floats() -> bool:
    """Every figure and table is cited in the document that carries it.

    A float a reader is never pointed at is a defect the journal names, and one
    this gate created for itself: moving text to the supplement left two figures
    behind in the manuscript with nothing referring to them. The reverse is
    checked too, since a reference to a float in the other document is how the
    build broke while the move was being made.
    """
    ok = True
    for doc in (MAIN, SUP):
        tex = with_inputs(doc)
        if not tex:
            continue
        labels = set(re.findall(r"\\label\{((?:fig|tab):[^}]+)\}", tex))
        refs = set(re.findall(r"\\ref\{((?:fig|tab):[^}]+)\}", tex))
        orphans = sorted(labels - refs)
        dangling = sorted(refs - labels)
        print(f"  {os.path.basename(doc)}: {len(labels)} floats, "
              f"{len(orphans)} uncited, {len(dangling)} pointing elsewhere")
        for o in orphans:
            print(f"  FAIL {doc} defines {o} and never cites it")
            ok = False
        for d in dangling:
            print(f"  FAIL {doc} cites {d}, which it does not define")
            ok = False
    return ok


def cover() -> bool:
    """Every number in the cover letter has to be one the record produced.

    The letter is hand-written, an editor reads it before the manuscript, and no
    other step was looking at it. Three of its numbers had drifted away from the
    paper by the time this check was written: a cell count, a null maximum and a
    section number. Section and item numbers are exempt because they are
    properties of the document rather than measurements; everything else has to
    match a macro value.
    """
    mp = os.path.join(D, "cover_letter.md")
    if not os.path.exists(mp):
        print("  no cover letter")
        return True
    txt = io.open(mp, encoding="utf-8").read()
    vals = set()
    for ln in io.open(os.path.join(D, "numbers.tex"), encoding="utf-8"):
        m = re.search(r"newcommand\{..[A-Za-z]+\}\{(.*)\}\s*$", ln)
        if m:
            raw = re.sub(r"\\[a-zA-Z]+|[{}$\\]", "", m.group(1)).strip()
            for tok in re.findall(r"\d[\d,]*\.?\d*", raw):
                vals.add(tok.replace(",", ""))
    # an ORCID is an identifier, not a quantity: its digits describe a person,
    # not a measurement, and the pattern is narrow enough that an ordinary
    # number cannot be laundered through it
    txt = re.sub(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b", "ORCID", txt)
    # numbers that describe the document, not the data
    skip = set()
    for m in re.finditer(r"(?:Section|Table|Figure|Appendix|Proposition)~?\s*(\d+)", txt):
        skip.add(m.group(1))
    bad = []
    for m in re.finditer(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?![\w])", txt):
        tok = m.group(1).replace(",", "")
        if tok in skip or tok in vals:
            continue
        if float(tok) <= 4 or tok in {"2026", "2025"}:
            continue              # small counts written out, and the year
        bad.append((tok, re.sub(r"\s+", " ", txt[max(0, m.start() - 70):m.end() + 30])))
    print(f"  {len(vals)} record values, {len(bad)} numbers in the letter without one")
    for tok, ctx in bad[:6]:
        print(f"  FAIL {tok}: ...{ctx}...")
    return not bad


def point_in_time() -> bool:
    """Two synthetic suites. test_pit.py fails if a rule regains the ability to
    see the week it is judged on; test_estimand.py fails if a quantity stops
    computing what its name claims, which is the failure the other gates are
    structurally unable to see."""
    r = subprocess.run([sys.executable, os.path.join("or_journal", "test_pit.py")],
                       capture_output=True, text=True)
    e = subprocess.run([sys.executable, os.path.join("or_journal", "test_estimand.py")],
                       capture_output=True, text=True)
    for line in (e.stdout or "").splitlines():
        if line.strip():
            print(" ", line.strip())
    if e.returncode:
        if e.stderr:
            print(" ", e.stderr.strip().splitlines()[-1])
        return False
    for line in (r.stdout or "").splitlines():
        if line.strip():
            print(" ", line.strip())
    if r.returncode and r.stderr:
        print(" ", r.stderr.strip().splitlines()[-1])
    return r.returncode == 0


def constants() -> bool:
    """A constant that reaches a printed number has to say where it came from.

    The cost of copying sat in the code as a bare literal with a comment
    claiming a measurement that no file supported, and four rounds of review
    passed over it because every gate ran between the record and the paper,
    never between the code and the record. This one asks each declared constant
    whether a run record carries it.
    """
    src = io.open(os.path.join("or_journal", "analysis.py"), encoding="utf-8").read()
    # only plain numeric literals: a constant written as an expression is
    # derived from something else and carries its own explanation
    declared = dict(re.findall(r"^([A-Z][A-Z_]+) = ([0-9.]+)\s*(?:#.*)?$", src, re.M))
    facts_path = os.path.join("out", "or", "facts.json")
    if not os.path.exists(facts_path):
        print("  no record to check against")
        return True
    blob = io.open(facts_path, encoding="utf-8").read()
    # a constant is accounted for if the record carries its value in the frame
    # block, which is where the measurement conventions are written down
    fr = json.loads(blob).get("frame", {})
    vals = {str(v) for v in fr.values() if isinstance(v, (int, float))}
    vals |= {str(float(v)) for v in fr.values() if isinstance(v, (int, float))}
    missing = [k for k, v in declared.items()
               if k not in ("SEED",) and v not in vals and str(float(v)) not in vals]
    print(f"  {len(declared)} declared constants, {len(missing)} not carried in the record")
    for k in missing:
        print("  FAIL unrecorded constant:", k)
    return not missing


def scan_paper() -> bool:
    """The mechanical checks that referees of five related submissions used to
    reject them: a declared count against what is listed, a metric pair that
    cannot hold together, an annualised ratio from a month, a headline word used
    as a number without a definition, a claim with nothing measured near it.

    Only the checks with no false positives fail the build. The counting check
    reports and does not fail, because a paper may legitimately say "four
    agents" of a baseline and "twelve" of its own.
    """
    sys.path.insert(0, "or_journal")
    import scan_defects
    r = scan_defects.scan(os.path.join(D, "main.pdf"))
    if not r:
        print("  the paper could not be read")
        return False
    hard = (r.get("metrics") or []) + (r.get("undefined") or []) + (r.get("sharpe") or [])
    for kind in ("counts", "claims"):
        for it in (r.get(kind) or [])[:3]:
            print(f"  note [{kind}]", str(it)[:120])
    for h in hard:
        print("  FAIL", str(h)[:160])
    print(f"  {len(hard)} hard findings, "
          f"{len(r.get('counts') or []) + len(r.get('claims') or [])} to read over")
    return not hard


def reserve() -> bool:
    """Every rule that was run has to reach the reader.

    The gate already checks that a printed number comes from a record and that a
    gross figure is printed with its net partner. Neither of those catches the
    opposite failure, which is a number computed and quietly left out, and three
    rounds of review in a row found one. So: every policy that was evaluated,
    at every basket size, must appear in the paper or be named in
    paper_or/reserve.md with a reason. The file is part of the submission.
    """
    pol_path = os.path.join("out", "or", "policy.json")
    if not os.path.exists(pol_path):
        print("  no policy record to audit")
        return True
    pol = json.load(open(pol_path, encoding="utf-8"))
    tex = with_inputs(MAIN) + with_inputs(SUP)
    used = set(re.findall(r"..n([A-Za-z]+)\{\}", tex))
    mp = os.path.join(D, "reserve.md")
    excused = io.open(mp, encoding="utf-8").read() if os.path.exists(mp) else ""

    kw = {"1": "One", "3": "Three", "5": "Five", "10": "Ten", "20": "Twenty", "40": "Forty"}

    def camel(key):
        return "".join(kw.get(part, part.capitalize()) for part in key.split("_"))

    missing = []
    for key in sorted(pol.get("summary", {})):
        if key.endswith(("_gain", "gain")) or "gain" in key:
            continue                      # comparisons are audited by their arms
        tag = "Policy" + camel(key)
        if not any(m.startswith(tag) for m in used) and key not in excused:
            missing.append(key)
    gains = [k for k in sorted(pol.get("summary", {})) if "gain" in k]
    gmissing = [k for k in gains
                if not any(m.startswith("Policy" + camel(k)) for m in used) and k not in excused]
    print(f"  {len(pol.get('summary', {}))} rules and comparisons in the record, "
          f"{len(missing) + len(gmissing)} neither printed nor excused")
    for k in (missing + gmissing)[:12]:
        print("  FAIL unreported:", k)
    if len(missing) + len(gmissing) > 12:
        print(f"  ... and {len(missing) + len(gmissing) - 12} more")
    return not missing and not gmissing


def main() -> int:
    ok = {}
    print("0. POINT IN TIME AND ESTIMANDS")
    ok["point_in_time"] = point_in_time()
    print("1. BUILD")
    ok["build"] = build()
    print("  compiled" if ok["build"] else "  FAILED (see paper_or/build.log)")
    if ok["build"]:
        import fitz
        doc = fitz.open(os.path.join(D, "main.pdf"))
        print(f"2. PAGES: {doc.page_count}")
        # the extraction reviewers read is rewritten from the build that just
        # happened, so it cannot describe an older version of the paper
        os.makedirs(os.path.join("out", "or"), exist_ok=True)
        io.open(os.path.join("out", "or", "paper_text.txt"), "w", encoding="utf-8").write(
            "\n".join(pg.get_text() for pg in doc))
    print("3. CITATIONS")
    ok["citations"] = citations()
    print("4. NUMBERS")
    ok["numbers"] = provenance.main([os.path.join(D, MAIN), "--allow", ALLOW, "--json", "out/or/numbers.json"]) == 0
    print("4b. MACRO NAMES")
    ok["macros"] = macros()
    print("5. PAIRING")
    ok["pairing"] = pairing()
    print("5b. CONSTANTS")
    ok["constants"] = constants()
    print("5c. DEFECT SCAN")
    ok["scan"] = scan_paper()
    print("5d. FLOATS")
    ok["floats"] = floats()
    print("5e. COVER LETTER")
    if subprocess.call([sys.executable, "or_journal/make_cover.py"]) != 0:
        print("   cover letter could not be generated from the record")
        ok["cover"] = False
    else:
        ok["cover"] = cover()
    print("6. RESERVE")
    ok["reserve"] = reserve()
    print("7. PROSE")
    ok["prose"] = style.main([os.path.join(D, MAIN), "--json", "out/or/style.json", "--max-style", "30"]) == 0
    print("\nVERDICT")
    for k, v in ok.items():
        print(f"  {'pass' if v else 'FAIL':<5} {k}")
    return 0 if all(ok.values()) else 1


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())
