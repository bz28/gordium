"""Pull every line of text out of a source PDF, with its page and position.

Output (one JSON object per line, a ".jsonl" file):
    {"file": ..., "sha256": ..., "pages": N, "extractor": ..., "rotated_chars_skipped": N}  <- header
    {"page": 1, "line": 1, "text": "...", "x0": .., "top": .., "x1": .., "bottom": ..}
Positions are in PDF points (1/72 inch) from the page's top-left corner.
Footnote markers (characters smaller than the page's normal text and raised above the line) are
written as a sealed token, "[fn11]", so "3/2 [fn11] 4" can never be read or quoted as the value 11.
Raised letters right after a number ("19th") are ordinal endings and stay plain text. Text that isn't level
(tilted more than 5°: most map street labels, angled or vertical diagram labels) is left out; the
header counts how many characters were skipped. Text within 5° of level is kept.

Plain code, no AI, no judgment: the same PDF always gives the same file.
"""

import hashlib
import json
import math
import statistics
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import pdfplumber

EXTRACTOR = (f"pdfplumber {version('pdfplumber')} + pdfminer.six {version('pdfminer.six')} "
             "(dedupe_chars, level text only, extract_text_lines, footnotes as [fnN])")
SUPERSCRIPT = 0.8  # footnote markers are smaller than this share of the page's normal text size…
RAISED = 0.2       # …and sit at least this share of that size above the line's baseline
MAX_TILT = 5       # degrees; text tilted more than this (map street labels, angled diagram labels) is left out
POSITION = ("x0", "top", "x1", "bottom")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(pdf_path: Path) -> list[dict]:
    """The header row, then one row per line of text, page by page, top to bottom."""
    rows, rotated = [], 0
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            rotated += sum(not _level(c) for c in page.chars)
            # Some PDFs draw text twice, slightly offset, to look bold ("RREESS..."); keep one copy.
            level = page.dedupe_chars().filter(lambda o: o.get("object_type") != "char" or _level(o))
            lines = level.extract_text_lines(return_chars=True)
            body = _body_size(level)
            rows += [{"page": page_number, "line": n, "text": _mark_superscripts(line, body),
                      **{k: round(line[k], 1) for k in POSITION}}
                     for n, line in enumerate(lines, 1)]
        header = {"file": pdf_path.name, "sha256": sha256(pdf_path), "pages": len(pdf.pages),
                  "extractor": EXTRACTOR, "rotated_chars_skipped": rotated}
    return [header, *rows]


def _level(char: dict) -> bool:
    """Is this character's baseline within MAX_TILT degrees of horizontal, reading left to right?"""
    a, b = char["matrix"][:2]
    return abs(math.degrees(math.atan2(b, a))) <= MAX_TILT


def _body_size(page) -> float:
    """The page's normal text size: the most common character size (ties: the larger)."""
    sizes = Counter(round(c["size"], 1) for c in page.chars)
    return max(sizes, key=lambda size: (sizes[size], size)) if sizes else 0.0


def _mark_superscripts(line: dict, body: float) -> str:
    """Wrap each footnote marker as a sealed token: [fn11]. A footnote marker is a run of characters
    smaller than the page's normal text and raised above the baseline of the line's normal-size text.
    A raised run of letters right after a digit is an ordinal ending ("19th") and stays plain."""
    chars, text = line["chars"], line["text"]
    if len(text.replace(" ", "")) != len(chars):  # text and characters must line up one to one
        raise ValueError(f"can't align text and characters: {text!r}")
    normal = [c["bottom"] for c in chars if c["size"] >= SUPERSCRIPT * body]
    baseline = statistics.median(normal) if normal else None

    def footnote(c):
        return (baseline is not None and c["size"] < SUPERSCRIPT * body
                and baseline - c["bottom"] >= RAISED * body)

    marks, i = [], 0
    for t in text:
        marks.append(t != " " and footnote(chars[i]))
        i += t != " "
    # Ordinal endings: a raised run of letters directly after a digit ("19th", "2nd") is plain text.
    for start in range(len(text)):
        if marks[start] and (start == 0 or not marks[start - 1]) and start > 0 and text[start - 1].isdigit():
            end = start
            while end < len(text) and marks[end]:
                end += 1
            if text[start:end].isalpha():
                marks[start:end] = [False] * (end - start)
    out, in_run = [], False
    for t, mark in zip(text, marks):
        if mark != in_run:  # a space is never marked, so a run always closes before it
            out.append("[fn" if mark else "]")
            in_run = mark
        out.append(t)
    return "".join(out) + ("]" if in_run else "")


def to_jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
