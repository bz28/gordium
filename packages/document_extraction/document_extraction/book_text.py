"""The extracted text of a book kept outside the repo, as the code cache holds it: the same for every branch.

The cache holds one text per book version and extractor version: every page of the book, read once
(<cache>/<sha256>/<stem>.text_<key>.jsonl). `key` is a fingerprint of the code that reads the pages (icc.py and
extract.py, as they are) and of the PDF libraries' versions, so a branch that changes how pages are read gets a
text of its own and never overwrites another branch's. Nothing else is in the name: which pages a branch brings in
(sources.yaml `brought_in`) is chosen from the whole book when the text is read (select), never by what is written.

Why the whole book: a cache that held only the pages the last branch brought in served every other branch the
wrong pages (step 1c's page 898 came and went as branches were extracted in turn). Each page is read on its own,
so a page read with the whole book is the same as that page read alone; `python -m document_extraction --check`
reads the brought-in pages afresh and requires the selection to be the same, byte for byte, header included.

Light on purpose (no pdfplumber): rule_format reads the cache through this module.
"""

import hashlib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The code every row of a book's text comes from, by its layout in sources.yaml: an ICC book in its own fonts (icc),
# or a book in two columns read from its text layer (two_column: columns.py, which uses icc.py's line_text)
TEXT_CODE = {"icc": ("icc.py", "extract.py"), "two_column": ("columns.py", "icc.py", "extract.py")}
LIBRARIES = ("pdfplumber", "pdfminer.six")


def extractor_key(layout: str = "icc") -> str:
    """16 hex characters: the code that reads a book's pages in this layout and the PDF libraries' versions. Line
    endings are made the same first, so a Windows checkout of the same code has the same key."""
    h = hashlib.sha256()
    for lib in LIBRARIES:
        try:
            h.update(f"{lib} {version(lib)}\n".encode())
        except PackageNotFoundError:
            h.update(f"{lib} missing\n".encode())
    for name in TEXT_CODE[layout]:
        h.update(name.encode() + b"\n" + (HERE / name).read_bytes().replace(b"\r\n", b"\n") + b"\n")
    return h.hexdigest()[:16]


def file_name(entry: dict) -> str:
    """The cached text's file name for a sources.yaml entry: <stem>.text_<extractor key>.jsonl (the key of the
    entry's layout; icc when it names none)."""
    return f"{Path(entry['file']).stem}.text_{extractor_key(entry.get('layout') or 'icc')}.jsonl"


def header(file: str, sha: str, pages: int, extractor: str, counts: dict[int, tuple[int, int]],
           read: list[int] | None) -> dict:
    """The header extract_icc writes for the pages `read` (None: every page), from each page's (rotated characters
    skipped, fractions joined). One function, so a selection's header is the one a fresh extraction writes."""
    wanted = sorted(counts) if read is None else read
    return {"file": file, "sha256": sha, "pages": pages, "extractor": extractor,
            "rotated_chars_skipped": sum(counts[p][0] for p in wanted),
            "fractions_joined": sum(counts[p][1] for p in wanted),
            "pages_read": "all" if read is None else list(read)}


def as_printed(rows: list[dict], misreads: dict | None) -> tuple[list[dict], list[str]]:
    """The rows with the scan's OCR misreads put right, as sources.yaml's `brought_in.misread` names them: by line
    ("p.266 line 23"), each {ocr: what the text layer reads, printed: what the page image prints, why}; so a quote,
    a cut and a number read the printed words ("I-4", where the OCR reads the letter I as a 1). The cached text stays
    the OCR's own (it is the same for every branch, and --check compares it with a fresh reading); every check of
    this branch reads it through here. Each `ocr` must occur exactly once in its line: anything else is a problem,
    never applied (a stale line number must never rewrite whatever is printed there now). Returns (rows, problems).
    Italic and bold offsets after a change move with the text."""
    if not misreads:
        return rows, []
    problems, out = [], [rows[0]]
    named = dict(misreads)
    for r in rows[1:]:
        where = f"p.{r.get('page')} line {r.get('line')}"
        fixes = named.pop(where, None)
        if not fixes:
            out.append(r)
            continue
        r = dict(r)
        for fix in fixes if isinstance(fixes, list) else [fixes]:
            ocr, printed = str((fix or {}).get("ocr", "")), str((fix or {}).get("printed", ""))
            if not ocr or r["text"].count(ocr) != 1 or not str((fix or {}).get("why", "")).strip():
                problems.append(f"brought_in.misread {where}: {ocr!r} must occur exactly once in the line, with "
                                f"printed and why; not applied")
                continue
            at, delta = r["text"].index(ocr), len(printed) - len(ocr)
            r["text"] = r["text"][:at] + printed + r["text"][at + len(ocr):]
            for k in ("italic", "bold"):
                if k in r:
                    r[k] = [[a + (delta if a >= at + len(ocr) else 0), b + (delta if b > at else 0)] for a, b in r[k]]
        out.append(r)
    problems += [f"brought_in.misread names {w}, which is not a line read" for w in named]
    return out, problems


def select(book: list[dict], pages: list[int]) -> list[dict]:
    """The rows extract_icc(pdf, pages) gives, taken from the whole book's rows (a header with every page's counts,
    then every line): the same header, then each page's lines in the order `pages` names them."""
    head = book[0]
    if head.get("pages_read") != "all" or not isinstance(head.get("page_counts"), dict):
        raise ValueError("not a whole book's text (no pages_read: all and page_counts)")
    counts = {int(p): tuple(c) for p, c in head["page_counts"].items()}
    missing = [p for p in pages if p not in counts]
    if missing:
        raise ValueError(f"pages {missing} are not in the book ({head['pages']} pages)")
    by_page: dict[int, list[dict]] = {}
    for row in book[1:]:
        by_page.setdefault(row["page"], []).append(row)
    return [header(head["file"], head["sha256"], head["pages"], head["extractor"], counts, list(pages)),
            *(row for p in pages for row in by_page.get(p, []))]
