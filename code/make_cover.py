"""Generate the cover letter from the run record, like everything else.

The letter was the one document whose numbers were only weakly guarded. The
gate asked whether each figure existed somewhere in the record, which a stale
figure can satisfy by coincidence -- and one did: the letter claimed the
decision surface was searched over 277 cells long after the paper settled at
221, and passed, because 277 happens to be some other macro's value.

So the letter is now written with macro placeholders and substituted here from
the same numbers.tex the manuscript uses. A figure cannot go stale without the
macro going stale, and a placeholder naming a macro that does not exist stops
the build.
"""
import io
import os
import re
import sys

NUM = "paper_or/numbers.tex"
TPL = "paper_or/cover_letter_template.md"
OUT = "paper_or/cover_letter.md"


def values() -> dict:
    """Macro name to its plain-text value, with the LaTeX taken off."""
    txt = io.open(NUM, encoding="utf-8").read()
    out = {}
    for name, raw in re.findall(
            r"\\newcommand\{\\(n[A-Za-z]+)\}\{(.*)\}\s*$", txt, re.M):
        # a letter is prose: an ASCII hyphen reads correctly and a typeset
        # minus does not survive a plain-text file
        s = raw.replace(r"\ensuremath{\mathrm{-}}", "-").replace(r"\%", "%")
        s = re.sub(r"\\[a-zA-Z]+|[{}$]", "", s)
        out[name] = s.strip()
    return out


def main() -> int:
    if not os.path.exists(TPL):
        print(f"missing {TPL}")
        return 1
    tpl = io.open(TPL, encoding="utf-8").read()
    v = values()

    used = set(re.findall(r"\{(n[A-Za-z]+)\}", tpl))
    missing = sorted(used - set(v))
    if missing:
        print(f"the template names {len(missing)} macro(s) the record does not "
              f"define: {', '.join(missing)}")
        return 1

    text = re.sub(r"\{(n[A-Za-z]+)\}", lambda m: v[m.group(1)], tpl)
    io.open(OUT, "w", encoding="utf-8").write(text)
    print(f"wrote {OUT} from {len(used)} macros")
    return 0


if __name__ == "__main__":
    sys.exit(main())
