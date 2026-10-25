"""Assemble the Financial Innovation submission.

The portal compiles LaTeX server-side with pdfLaTeX, so the source goes up as
a flat directory with no subdirectory in any path, and is proved to compile by
compiling it there before it is zipped.

ITOR desk-rejected the paper as out of scope and takes no resubmission, so the
old folder is kept as a record and nothing here writes into it.
"""
import glob
import io
import os
import re
import shutil
import subprocess
import sys

SRC = "paper_or"
OUT = os.path.join(SRC, "submission_fininnov")
FLAT = os.path.join(OUT, "04_latex_source")


def pdf_pages(path: str) -> int:
    import fitz
    return fitz.open(path).page_count


def cover_pdf() -> str:
    """The letter as a PDF, from the generated markdown."""
    md = os.path.join(SRC, "cover_letter.md")
    out = os.path.join(SRC, "cover_letter.pdf")
    subprocess.run(["pandoc", md, "-o", out, "--pdf-engine=xelatex",
                    "-V", "mainfont=Times New Roman",
                    "-V", "geometry:margin=2.2cm", "-V", "fontsize=11pt"],
                   check=True, capture_output=True, text=True)
    return out


def flat_source() -> int:
    """fininnov.tex with every input beside it, compiled in place to prove it."""
    os.makedirs(FLAT, exist_ok=True)
    tex = io.open(os.path.join(SRC, "fininnov.tex"), encoding="utf-8").read()
    # the portal has no subdirectories, so figure paths lose theirs
    tex = re.sub(r"\{figures/(\w+)(\.pdf)?\}", r"{\1}", tex)
    assert "figures/" not in tex, "a figure path kept its directory"
    io.open(os.path.join(FLAT, "fininnov.tex"), "w", encoding="utf-8").write(tex)

    for name in ("numbers.tex", "refs.bib"):
        shutil.copy2(os.path.join(SRC, name), os.path.join(FLAT, name))
    figs = sorted(glob.glob(os.path.join(SRC, "figures", "*.pdf")))
    used = set(re.findall(r"\\includegraphics\[[^\]]*\]\{(\w+)\}", tex))
    for f in figs:
        if os.path.splitext(os.path.basename(f))[0] in used:
            shutil.copy2(f, os.path.join(FLAT, os.path.basename(f)))

    subprocess.run(["latexmk", "-C", "fininnov"], cwd=FLAT,
                   capture_output=True, text=True)
    for _ in range(3):
        subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode",
                        "fininnov"], cwd=FLAT, capture_output=True, text=True)
    built = os.path.join(FLAT, "fininnov.pdf")
    assert os.path.exists(built), "the flat source did not compile"
    pages = pdf_pages(built)
    # keep the bbl the portal needs, drop the rest of the build litter
    for junk in glob.glob(os.path.join(FLAT, "fininnov.*")):
        if not junk.endswith((".tex", ".bbl")):
            os.remove(junk)
    shutil.make_archive(FLAT, "zip", FLAT)
    return pages


def main() -> int:
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "05_figures"))

    cover = cover_pdf()
    files = [("fininnov.pdf", "01_manuscript.pdf"),
             ("supplement.pdf", "02_supplement.pdf"),
             (os.path.basename(cover), "03_cover_letter.pdf")]
    for a, b in files:
        p = os.path.join(SRC, a)
        assert os.path.exists(p), f"missing {a}"
        shutil.copy2(p, os.path.join(OUT, b))

    figs = sorted(glob.glob(os.path.join(SRC, "figures", "*.pdf")))
    for f in figs:
        shutil.copy2(f, os.path.join(OUT, "05_figures", os.path.basename(f)))

    flat_pages = flat_source()
    man = pdf_pages(os.path.join(OUT, "01_manuscript.pdf"))
    sup = pdf_pages(os.path.join(OUT, "02_supplement.pdf"))
    cov = pdf_pages(os.path.join(OUT, "03_cover_letter.pdf"))

    io.open(os.path.join(OUT, "00_CHECKLIST.txt"), "w", encoding="utf-8").write(
        f"""FINANCIAL INNOVATION SUBMISSION
===============================
Journal: Financial Innovation (SpringerOpen, sponsored by SWUFE)
Indexed: Social Science Citation Index, Scopus, ABS, ABDC, CNKI, Wanfang
Portal : https://link.springer.com/journal/40854/submission-guidelines
APC    : GBP 1190 / USD 1750 / EUR 1440 -- ask about an institutional
         agreement or a discretionary waiver AT SUBMISSION, not after.

WHAT THE GUIDE ASKS FOR, AND WHERE IT IS MET
--------------------------------------------
  double-line spacing          \\doublespacing in the preamble
  line and page numbering      \\linenumbers, page numbers by the class
  no page breaks               asserted by or_journal/make_fininnov.py
  editable source              04_latex_source.zip, not only the PDF
  data availability statement  "Availability of data and materials"
  author-year citations        natbib with plainnat

FILES
-----
  01_manuscript.pdf        the manuscript, {man} pages double-spaced
  02_supplement.pdf        proofs, full measurements, every rule evaluated
                           ({sup} pages)
  03_cover_letter.pdf      {cov} page(s), generated from the run record
  04_latex_source/         flat source: fininnov.tex, numbers.tex, refs.bib,
  04_latex_source.zip      fininnov.bbl and the figures, no subdirectory in
                           any path. Verified by compiling it in that flat
                           directory from scratch: {flat_pages} pages.
  05_figures/              {len(figs)} figures as vector PDF

STILL OPEN BEFORE YOU UPLOAD
----------------------------
  The data-availability statement says the inputs are released but names no
  repository. SpringerOpen wants a repository name and a persistent link.
  Create the public repository, put its URL in main.tex, rerun the gate.
""")

    print(f"wrote {OUT}")
    print(f"manuscript {man}pp, supplement {sup}pp, cover {cov}pp, "
          f"flat source compiles to {flat_pages}pp, {len(figs)} figures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
