"""Pull every line of text out of a source PDF, with its page and position.

Output (one JSON object per line, a ".jsonl" file):
    {"file": ..., "sha256": ..., "pages": N, "extractor": ...}          <- header: which exact PDF
    {"page": 1, "line": 1, "text": "...", "x0": .., "top": .., "x1": .., "bottom": ..}
Positions are in PDF points (1/72 inch) from the page's top-left corner.
Small raised characters (footnote markers) are written with a "^" in front, so "3/2 ^11" can't be
read as the value 11. Sideways text (rotated labels on diagrams and maps) is left out; the header
counts how many characters were skipped.

Plain code, no AI, no judgment: the same PDF always gives the same file.
"""

import hashlib
import json
import statistics
from importlib.metadata import version
from pathlib import Path

import pdfplumber

EXTRACTOR = (f"pdfplumber {version('pdfplumber')} + pdfminer.six {version('pdfminer.six')} "
             "(dedupe_chars, upright text only, extract_text_lines, superscripts marked '^')")
SUPERSCRIPT = 0.8  # a character smaller than this share of its line's typical size is a footnote marker
POSITION = ("x0", "top", "x1", "bottom")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(pdf_path: Path) -> list[dict]:
    """The header row, then one row per line of text, page by page, top to bottom."""
    rows, rotated = [], 0
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            rotated += sum(not c.get("upright", True) for c in page.chars)
            # Some PDFs draw text twice, slightly offset, to look bold ("RREESS..."); keep one copy.
            upright = page.dedupe_chars().filter(lambda o: o.get("object_type") != "char" or o.get("upright", True))
            lines = upright.extract_text_lines(return_chars=True)
            rows += [{"page": page_number, "line": n, "text": _mark_superscripts(line),
                      **{k: round(line[k], 1) for k in POSITION}}
                     for n, line in enumerate(lines, 1)]
        header = {"file": pdf_path.name, "sha256": sha256(pdf_path), "pages": len(pdf.pages),
                  "extractor": EXTRACTOR, "rotated_chars_skipped": rotated}
    return [header, *rows]


def _mark_superscripts(line: dict) -> str:
    """Put '^' before each run of characters much smaller than the line's typical size."""
    chars, text = line["chars"], line["text"]
    if len(text.replace(" ", "")) != len(chars):  # text and characters must line up one to one
        raise ValueError(f"can't align text and characters: {text!r}")
    typical = statistics.median(c["size"] for c in chars)
    out, i, in_run = [], 0, False
    for t in text:
        if t == " ":
            out.append(t)
            in_run = False
            continue
        small = chars[i]["size"] < SUPERSCRIPT * typical
        out.append(("^" if small and not in_run else "") + t)
        in_run, i = small, i + 1
    return "".join(out)


def to_jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
