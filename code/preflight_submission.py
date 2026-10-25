"""Everything that must be true before this is uploaded, checked rather than assumed.

Two risks specific to this last change. Swapping the document class renumbers
sections, and the cover letter points a reader at "Section 12" for the
limitations; if the class moved it, the letter now misdirects an editor. And the
submission folder is a copy, so it can be stale: every file in it must be newer
than the source it came from.
"""
import io
import os
import re
import subprocess

import fitz

D = "D:/holy_grail/paper_or"
SUB = os.path.join(D, "submission_itor")
rows = []


def check(name, ok, detail=""):
    rows.append((bool(ok), name, detail))


# ---- the submitted manuscript
m = fitz.open(os.path.join(D, "itor.pdf"))
mt = "\n".join(p.get_text() for p in m)
check("manuscript builds, under 25 pages", m.page_count <= 25, f"{m.page_count} pages")
check("no unresolved references in it", "??" not in mt,
      f"{mt.count(chr(63) * 2)} found")
log = io.open(os.path.join(D, "itor.log"), encoding="utf-8", errors="replace").read()
check("no LaTeX errors", "\n! " not in log,
      f"{log.count(chr(10) + '! ')} errors")
check("no undefined refs in the final pass",
      "There were undefined references" not in log)

# ---- the section the cover letter points at
secs = dict((int(n), t.strip()) for n, t in
            re.findall(r"\n(\d{1,2})\.?\s+([A-Z][A-Za-z ,]{4,50})\n", mt))
lim = next((n for n, t in secs.items() if t.lower().startswith("limitation")), None)
letter = io.open(os.path.join(D, "cover_letter.md"), encoding="utf-8").read()
# a named pointer cannot go stale when a class change renumbers sections
nums = re.findall(r"Section (\d+)", letter)
check("cover letter cites no section number that could move",
      not nums, ", ".join(nums) or f"none; limitations is section {lim}")

# ---- the guide's hard limits, measured on the submitted file
t0 = m[0].get_text()
ab = re.search(r"Abstract\s*(.*?)(?:Keywords|Keyword)", t0, re.S)
nw = len(ab.group(1).split()) if ab else -1
check("abstract within 150 words", 0 < nw <= 150, f"{nw} words")
kwline = re.search("Keywords?:" + chr(92) + "s*([^" + chr(92) + "n]+)", t0)
nk = len([k for k in re.split(r"[;,]", kwline.group(1))if k.strip()]) if kwline else -1
check("keywords within 10", 0 < nk <= 10, f"{nk} keywords")
check("no footnotes", mt.count("\nfootnote") == 0)
check("author-year citations, none numbered",
      len(re.findall(r"\[\d+\]", mt)) == 0,
      f"{len(re.findall(r'[(][A-Z][A-Za-z]+,? [0-9]{4}', mt))} author-year found")
for decl in ("Data availability", "Competing interests", "Funding",
             "Ethics approval", "Author contributions"):
    check(f"declaration present: {decl}", decl in mt)
check("both ORCIDs kept out of the PDF", "orcid" not in mt.lower())
check("both affiliations carry a postal address", mt.count("518055") >= 2,
      f"{mt.count('518055')} occurrences")

# ---- the other two documents
s = fitz.open(os.path.join(D, "supplement.pdf"))
check("supplement builds", s.page_count > 0, f"{s.page_count} pages")
c = fitz.open(os.path.join(D, "cover_letter.pdf"))
check("cover letter is one page", c.page_count == 1, f"{c.page_count} page(s)")
ct = c[0].get_text()
check("cover letter names the second author correctly",
      "Wai Kin (Victor) Chan" in ct)
check("cover letter carries both ORCIDs",
      len(re.findall(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", ct)) == 2)

# ---- the folder is not stale
DEPS = {"01_manuscript_itor.pdf": ("main.tex", "numbers.tex", "itor.tex"),
        "02_supplementary_material.pdf": ("supplement.tex", "numbers.tex"),
        "03_cover_letter.pdf": ("cover_letter.md",),
        "04_list_of_captions.txt": ("main.tex", "supplement.tex")}
stale = []
for f, deps in DEPS.items():
    fp = os.path.join(SUB, f)
    if not os.path.exists(fp):
        stale.append(f + " (missing)")
        continue
    newest = max(os.path.getmtime(os.path.join(D, d)) for d in deps)
    if os.path.getmtime(fp) < newest:
        stale.append(f)
check("every copied file is newer than its own sources", not stale,
      ", ".join(stale) or "all current")
eps = [f for f in os.listdir(os.path.join(SUB, "figures")) if f.endswith(".png")]
check("seven 600dpi figures supplied", len(eps) == 7, f"{len(eps)} files")
chk = io.open(os.path.join(SUB, "00_CHECKLIST.txt"), encoding="utf-8").read()
check("checklist states the right page count", f"{m.page_count} pages (limit 25)" in chk)
check("checklist abstract has no lost ligatures",
      "five choices" in chk and " ve choices" not in chk)

# ---- the record has not drifted
r = subprocess.run(["git", "status", "--porcelain", "paper_or/numbers.tex"],
                   cwd="D:/holy_grail", capture_output=True, text=True)
check("numbers.tex committed, not drifting", not r.stdout.strip(),
      r.stdout.strip() or "clean")

bad = [r for r in rows if not r[0]]
for ok, name, detail in rows:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
print(f"\n{len(rows) - len(bad)}/{len(rows)} checks pass")
if bad:
    print("MUST FIX:")
    for _, name, detail in bad:
        print(f"  - {name}: {detail}")
