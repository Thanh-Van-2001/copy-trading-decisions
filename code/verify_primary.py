"""Verify the citations that Crossref and OpenAlex do not index.

refcheck takes nothing on trust, which is right, but it can only confirm what
the public bibliographic record holds. Regulator reports, central bank papers
and standards are not in Crossref, so under refcheck alone they could never be
cited at all -- and they are often the best source available.

This closes that gap without weakening the rule. An entry is accepted only if
the document itself is retrieved and its own text is found to carry the title
we cite it by, and the report number if the entry claims one. The retrieval is
recorded with the sha256 of the exact bytes that were read, so a later run can
tell whether the document behind the URL has changed under us.

An allowlist would have been five lines. It would also have meant asserting a
source is real because we said so, which is the thing refcheck exists to stop.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time

BIB = "paper_or/refs.bib"
OUT = "out/or/primary_sources.json"
CACHE = os.path.join(
    os.environ.get("TEMP", "."), "claude", "or_primary_sources")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
# A PDF breaks a title across lines and sometimes across pages, so compare on
# tokens rather than on the exact string, and require nearly all of them.
MIN_TOKEN_SHARE = 0.9


def entries(path: str) -> list:
    """Parse the bib loosely: one dict per entry, fields lowercased."""
    txt = io.open(path, encoding="utf-8").read()
    out = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", txt):
        start = m.end()
        depth, i = 1, start
        while i < len(txt) and depth:
            if txt[i] == "{":
                depth += 1
            elif txt[i] == "}":
                depth -= 1
            i += 1
        body = txt[start:i - 1]
        rec = {"_type": m.group(1).lower(), "_key": m.group(2)}
        for fm in re.finditer(r"(\w+)\s*=\s*\{(.*?)\}\s*(?:,|$)", body, re.S):
            rec[fm.group(1).lower()] = " ".join(fm.group(2).split())
        out.append(rec)
    return out


def needs_retrieval(rec: dict) -> bool:
    """True when the public record cannot settle this entry but a URL can."""
    if rec.get("doi") or rec.get("eprint"):
        return False
    return bool(rec.get("url"))


def fetch(url: str, dest: str) -> bytes:
    """Download atomically: a part file, then replace. Never a half file."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    cmd = ["curl", "-sL", "--max-time", "60", "-A", UA,
           "-H", "Accept: application/pdf,text/html,*/*", "-o", part, url]
    if subprocess.call(cmd) != 0:
        if os.path.exists(part):
            os.remove(part)
        raise RuntimeError(f"download failed: {url}")
    os.replace(part, dest)
    return io.open(dest, "rb").read()


def text_of(path: str, blob: bytes) -> str:
    if blob[:5] == b"%PDF-":
        import fitz
        doc = fitz.open(path)
        return " ".join(p.get_text() for p in doc)
    html = blob.decode("utf-8", "replace")
    return re.sub(r"<[^>]*>", " ", html)


def tokens(s: str) -> list:
    return re.findall(r"[a-z0-9]+", s.lower())


def check(rec: dict) -> dict:
    """Retrieve the document and look for our own claims inside it."""
    key, url = rec["_key"], rec["url"]
    dest = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9_.-]", "_", key))
    blob = fetch(url, dest)
    body = " ".join(text_of(dest, blob).split())
    flat = " ".join(tokens(body))

    want = tokens(rec.get("title", ""))
    assert want, f"{key}: entry has no title to verify"
    found = sum(1 for t in set(want) if t in set(tokens(body)))
    share = found / len(set(want))

    num = rec.get("number", "")
    # The number may be typeset with different spacing than the entry gives.
    num_ok = (not num) or re.sub(r"\s+", "", num).lower() in re.sub(
        r"\s+", "", body).lower()

    ok = share >= MIN_TOKEN_SHARE and num_ok
    return {"key": key, "url": url, "ok": ok,
            "title_token_share": round(share, 3),
            "number": num or None, "number_found": num_ok,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob), "chars_extracted": len(flat),
            "retrieved": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def main() -> int:
    recs = [r for r in entries(BIB) if needs_retrieval(r)]
    if not recs:
        print("no primary sources to verify")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    results, bad = [], 0
    for rec in recs:
        try:
            res = check(rec)
        except Exception as exc:                       # retrieval or parse
            res = {"key": rec["_key"], "url": rec.get("url"), "ok": False,
                   "error": str(exc)}
        results.append(res)
        if res["ok"]:
            print(f"  OK   {res['key']}: title {res['title_token_share']:.0%} "
                  f"in document, number {'found' if res['number_found'] else 'n/a'}, "
                  f"sha256 {res['sha256'][:12]}")
        else:
            bad += 1
            print(f"  FAIL {res['key']}: "
                  f"{res.get('error') or 'document does not carry this title'}")
    json.dump(results, io.open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"{len(results) - bad}/{len(results)} primary sources verified "
          f"by retrieval -> {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
