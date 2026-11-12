"""Which other parts of an ICC code book point into the brought-in sections, and where the brought-in pieces point
out of them: how New York's README lists ("References in the brought-in sections that are not brought in", "Ways
into these sections from outside them") are found, so they can be found again.

    python -m document_extraction.icc_references    # where the code cache has the book: print both lists

"Into": every line of the whole book, outside the brought-in pieces, that names a brought-in section ("Section
R318", "R321.1", "R325.6"). "Out of": every section, table, appendix or chapter a brought-in piece names that is not
brought in. The whole book is read once into the code cache (<book>.full.jsonl, the same extractor as the pages
read, all pages); the table of contents, the list of standards and the index only list section numbers, so they
are left out. Plain code, no AI. The README says which hits are egress and what is done with each: that judgment
is a person's.
"""

import json
import re
import sys
from pathlib import Path

from rule_format.rulebook import REPO, cached, load, read_jsonl, utf8_console

from .icc import extract_icc
from .icc_sections import parse_pages

CITED = re.compile(r"\b(?:Appendix [A-Z]{1,2}\b|Chapter \d+\b|ICC \d+\b|Table [A-Z]?\d+(?:\.\d+)*(?:\(\d+\))?"
                   r"|[A-Z]{1,2}\d{3,4}(?:\.\d+)*)")
# Pages that only list section numbers, per book (by file name): its contents, its list of standards, its index.
LISTS_ONLY = {"gov.ny.residential.2025.pdf": "16, 852, 1070-1076"}


def _brought(code: str, sections: list[str]) -> bool:
    return any(code == s or code.startswith(s + ".") for s in sections)


def ways_in(rows: list[dict], sections: list[str], owned: set[tuple[int, int]], skip: set[int]) -> list[tuple]:
    """(page, line, cited section, the line's first words) for each line outside the brought-in pieces (`owned`:
    their (page, line)s) that names a brought-in section."""
    out = []
    for r in rows:
        if "page" not in r or r["page"] in skip or (r["page"], r["line"]) in owned:
            continue
        for code in CITED.findall(r["text"]):
            if _brought(code, sections):
                out.append((r["page"], r["line"], code, r["text"][:70]))
    return out


def ways_out(pieces: list[dict], lines: dict[tuple[int, int], str], sections: list[str]) -> dict[str, list[str]]:
    """{cited section, table, appendix or chapter: [the brought-in pieces that name it]}, for those not brought in.
    Definitions (R202) are left out: a definition naming another code's chapter is not egress law brought in."""
    out: dict[str, list[str]] = {}
    for p in pieces:
        if p["kind"] == "definition" or p["id"] == "R202":
            continue
        text = " ".join(lines[(pg, n)] for pg, a, b in p["lines"] for n in range(a, b + 1))
        for code in CITED.findall(text):
            if code != p["id"] and not _brought(code, sections) and not code.startswith("R202"):
                out.setdefault(code, [])
                if p["id"] not in out[code]:
                    out[code].append(p["id"])
    return out


def main() -> int:
    j = REPO / "regulations/jurisdictions/new_york/new_york_state"
    entry = load(j / "1_source_documents/sources.yaml")["documents"][0]
    pdf, full = cached(entry), cached(entry, ".full.jsonl")
    if not pdf.exists():
        print(f"– {entry['file']} is not in the code cache here; nothing searched")
        return 0
    if not full.exists():                       # once per book version: every page, the same extractor
        full.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in extract_icc(pdf)), encoding="utf-8")
    sections = entry["brought_in"]["sections"]
    cut = read_jsonl(j / "2_extracted_text" / f"{Path(entry['file']).stem}.sections.jsonl")
    owned = {(pg, n) for p in cut[1:] for pg, a, b in p["lines"] for n in range(a, b + 1)}
    lines = {(r["page"], r["line"]): r["text"] for r in read_jsonl(cached(entry, ".jsonl"))[1:]}
    print("Ways in (the whole book, outside the brought-in pieces):")
    for page, line, code, words in ways_in(read_jsonl(full)[1:], sections, owned,
                                           set(parse_pages(LISTS_ONLY.get(entry["file"], "0")))):
        print(f"  p.{page} line {line}: {code}  {words}")
    print("Ways out (named by a brought-in piece, not brought in):")
    for code, by in sorted(ways_out(cut[1:], lines, sections).items()):
        print(f"  {code}: from {', '.join(by)}")
    return 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main())
