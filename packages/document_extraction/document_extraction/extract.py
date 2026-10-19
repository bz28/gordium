"""Pull every line of text out of a source PDF, with its page and position.

Output (one JSON object per line, a ".jsonl" file):
    {"file": ..., "sha256": ..., "pages": N, "extractor": ...}          <- header: which exact PDF
    {"page": 1, "line": 1, "text": "...", "x0": .., "top": .., "x1": .., "bottom": ..}
Positions are in PDF points (1/72 inch) from the page's top-left corner.

Plain code, no AI, no judgment: the same PDF always gives the same file.
"""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import pdfplumber

EXTRACTOR = f"pdfplumber {version('pdfplumber')} (dedupe_chars + extract_text_lines)"
POSITION = ("x0", "top", "x1", "bottom")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(pdf_path: Path) -> list[dict]:
    """The header row, then one row per line of text, page by page, top to bottom."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            # Some PDFs draw text twice, slightly offset, to look bold ("RREESS..."); keep one copy.
            lines = page.dedupe_chars().extract_text_lines()
            rows += [{"page": page_number, "line": n, "text": line["text"],
                      **{k: round(line[k], 1) for k in POSITION}}
                     for n, line in enumerate(lines, 1)]
        header = {"file": pdf_path.name, "sha256": sha256(pdf_path), "pages": len(pdf.pages),
                  "extractor": EXTRACTOR}
    return [header, *rows]


def to_jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
