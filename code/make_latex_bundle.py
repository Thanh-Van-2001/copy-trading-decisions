"""A flat LaTeX source bundle the submission portal can compile.

Research Exchange takes the .tex file as the Main Document for a LaTeX
submission and compiles it on the server to produce the proof. That compile
happens over the files as uploaded, which is a flat list, so a manuscript whose
graphics live under figures/ fails there while building perfectly here. It also
needs every \\input file, the class, the bibliography style and the .bbl, since
it will not run BibTeX against a .bib it cannot resolve.

So this writes a directory in which the manuscript compiles with no
subdirectories at all, proves it by compiling it, and zips it for the portals
that prefer an archive. Nothing is retyped: the .tex is the generated one with
its graphics paths flattened.

Usage: python or_journal/make_latex_bundle.py
"""
import io
import os
import re
import shutil
import subprocess
import zipfile

D = "paper_or"
OUT = os.path.join(D, "submission_itor", "05_latex_source")
ZIP = os.path.join(D, "submission_itor", "05_latex_source.zip")


def main() -> int:
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    tex = io.open(os.path.join(D, "itor.tex"), encoding="utf-8").read()
    # the server compiles over a flat file list, so no path may survive
    flat = re.sub(r"(\\includegraphics\[[^\]]*\]\{)figures/", r"\1", tex)
    assert "figures/" not in flat, "a directory reference survived"
    io.open(os.path.join(OUT, "itor.tex"), "w", encoding="utf-8").write(flat)

    carried = ["numbers.tex", "itor.cls", "itor.bst", "refs.bib", "itor.bbl"]
    for f in carried:
        src = os.path.join(D, f)
        if not os.path.exists(src):
            print(f"missing {src}")
            return 1
        shutil.copy2(src, os.path.join(OUT, f))

    figs = []
    for f in sorted(os.listdir(os.path.join(D, "figures"))):
        # only the PDFs: the manuscript compiles with pdflatex, and the EPS
        # path loses its text in conversion
        if f.endswith(".pdf") and f.startswith("fig_"):
            shutil.copy2(os.path.join(D, "figures", f), os.path.join(OUT, f))
            figs.append(f)

    # prove it: compile in the flat directory, from scratch
    subprocess.run(["latexmk", "-C", "itor"], cwd=OUT, capture_output=True, text=True)
    for _ in range(3):
        subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "itor"],
                       cwd=OUT, capture_output=True, text=True)
    pdf = os.path.join(OUT, "itor.pdf")
    if not os.path.exists(pdf):
        print("the flat bundle does not compile; see", os.path.join(OUT, "itor.log"))
        return 1
    log = io.open(os.path.join(OUT, "itor.log"), encoding="utf-8", errors="replace").read()
    errors = log.count("\n! ")
    undefined = "There were undefined references" in log
    import fitz
    pages = fitz.open(pdf).page_count

    # the proof and the build artefacts do not go to the journal
    keep = {"itor.tex", *carried, *figs}
    for f in sorted(os.listdir(OUT)):
        if f not in keep:
            os.remove(os.path.join(OUT, f))

    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(OUT)):
            z.write(os.path.join(OUT, f), f)

    print(f"flat bundle compiles: {pages} pages, {errors} errors, "
          f"undefined references: {undefined}")
    print(f"{OUT}: {len(os.listdir(OUT))} files")
    print(f"{ZIP}: {os.path.getsize(ZIP) // 1024} KB")
    return 0 if (pages and not errors and not undefined) else 1


if __name__ == "__main__":
    raise SystemExit(main())
