"""Pull every line of text out of a code book printed in two columns, from the book's own text layer (layout:
two_column in sources.yaml): the 2009 International Building Code as Public.Resource.Org scanned it (its text layer
is the scanner's OCR, ABBYY FineReader 8.0) and NFPA 101, Life Safety Code, 2012 edition (NFPA's own text, in its
fonts). The rows have icc.py's shape (a header row, then one {"page", "line", "text", x0, top, x1, bottom, italic,
bold} per line), so quotes are checked, and pieces cut, the same way.

What is different from icc.py:
- **Two columns, read one after the other.** A line read straight across the page would join the left column's line
  to the right column's ("... shall not be 1015.2.2 Three or more exits ..."). So each page's gutter is found (the
  widest run of the page's middle that the fewest characters cross), and the page is read in bands from the top: a
  line that runs across the gutter (a title, a wide table, the running head) is a band of its own; between them, the
  left column's lines, then the right column's. A page with no gutter (a whole-page table) is read straight across.
- **Words from the gaps between letters.** Neither book's text layer has the spaces: a gap wider than WORD_GAP of the
  letters' size starts a new word (the scan's text runs its words together at pdfplumber's usual 3 points).
- **A fraction printed as one glyph** (½) is written in digits, "1/2", with a space after a whole number ("2 1/2"),
  as icc.py writes ICC's stacked fractions, so numbers.py reads it.
- **Italics and bold from the fonts**: the scan's OCR names its italic words' font Times-Italic and records no bold;
  NFPA's fonts are NewBaskerville-Roman, -Bold and -Italic.
Rotated characters (NFPA's diagonal licence watermark) are left out and counted, as extract.py does; footnote markers
(small raised characters) are sealed "[fna]", as everywhere.

Plain code, no AI, no judgment: the same PDF always gives the same file.
"""

import math
from importlib.metadata import version
from pathlib import Path

import pdfplumber

from . import book_text
from .extract import POSITION, SUPERSCRIPT, _body_size, _level, sha256
from .icc import join_fractions, line_text

EXTRACTOR = (f"pdfplumber {version('pdfplumber')} + pdfminer.six {version('pdfminer.six')} "
             "(two_column layout: dedupe_chars, level text only, columns by gutter, words by gaps, glyph fractions "
             "and stacked fractions in digits, footnotes as [fnN])")
WORD_GAP = 0.08          # a gap wider than this share of the letters' size starts a new word
LINE_GAP = 0.5           # characters whose feet differ by more than this share of their size are on different lines
TALL = 1.6               # a character this many times taller than a row is no letter of it (a change bar in the
                         # margin, which the scan's OCR reads as "I"): it is a line of its own, never joined
GUTTER_MIN = 8.0         # points: the narrowest gap at the gutter that still parts a line into two columns
MIDDLE = (0.35, 0.65)    # the share of the page's width the gutter is looked for in
SLACK = 2                # characters: the gutter is crossed by at most this many more than the fewest anywhere
GLYPHS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8",
          "⅞": "7/8"}
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}


def extract_columns(pdf_path: Path, pages: list[int] | None = None) -> list[dict]:
    """The header row, then one row per line of text, page by page, in reading order. `pages`: only these pages
    (1-based); None reads every page."""
    head, rows, counts = _read(pdf_path, pages)
    return [book_text.header(*head, counts, None if pages is None else list(pages)), *rows]


def read_book(pdf_path: Path) -> list[dict]:
    """Every page, as the code cache keeps it (book_text.py), with the extractor key and each page's counts."""
    head, rows, counts = _read(pdf_path, None)
    return [book_text.header(*head, counts, None) | {"extractor_key": book_text.extractor_key("two_column"),
                                                     "page_counts": {str(p): list(c) for p, c in counts.items()}},
            *rows]


def _read(pdf_path: Path, pages: list[int] | None) -> tuple[tuple, list[dict], dict[int, tuple[int, int]]]:
    """(file, sha256, page count, extractor), the rows of the pages read, and each page's (rotated characters
    skipped, glyph fractions written in digits)."""
    rows, counts = [], {}
    with pdfplumber.open(pdf_path) as pdf:
        wanted = range(1, len(pdf.pages) + 1) if pages is None else pages
        for page_number in wanted:
            page = pdf.pages[page_number - 1]
            rotated = sum(not _level(c) for c in page.chars)
            lines, body, written = column_lines(page)
            counts[page_number] = (rotated, written)
            for n, line in enumerate(lines, 1):
                text, styles = line_text(line, body)
                rows.append({"page": page_number, "line": n, "text": text,
                             **{k: round(line[k], 1) for k in POSITION}, **{k: v for k, v in styles.items() if v}})
            page.close()
        n_pages = len(pdf.pages)
    return (pdf_path.name, sha256(pdf_path), n_pages, EXTRACTOR), rows, counts


def column_lines(page) -> tuple[list[dict], float, int]:
    """A page's lines in reading order ({"text", "chars", x0, top, x1, bottom}), its normal text size, and how many
    fractions were written in digits: glyph fractions (½), and stacked ones (a small raised 1, a slash, a small
    lowered 2), put back on their line as icc.py does, NFPA's fraction slash (⁄) read as "/"."""
    level = page.dedupe_chars().filter(lambda o: o.get("object_type") != "char" or _level(o))
    body = _body_size(level)
    chars, written = spelled([dict(c) for c in level.chars if c["text"].strip()])
    for c in chars:
        if c["text"] == "⁄":
            c["text"] = "/"
    written += join_fractions(chars, body) + join_small_fractions(chars, body)
    return read_in_columns(chars, page.width, body), body, written


def join_small_fractions(chars: list[dict], body: float) -> int:
    """Put back on its line each stacked fraction printed all small (a small raised numerator, a small slash, a small
    lowered denominator: the scan's ½ in "2 1/2 years", NFPA's ½ in "1/2-hour"), which icc.join_fractions, wanting a
    full-size slash, leaves apart. The fraction takes the size and height of the nearest full-size character beside
    it, so it reads as a word of that line; after a whole number it is written "2 1/2". Returns how many."""
    small = [c for c in chars if c["size"] < SUPERSCRIPT * body]
    joined = 0
    for slash in [c for c in chars if c["text"] == "/" and not c.get("in_fraction")]:
        mid = (slash["x0"] + slash["x1"]) / 2
        near = lambda c: abs(c["top"] - slash["top"]) < body and c["text"].isdigit() and not c.get("in_fraction")
        num = [c for c in small if near(c) and c["x0"] < mid and slash["x0"] - 2.5 <= c["x1"]]
        den = [c for c in small if near(c) and c["x1"] > mid and c["x0"] <= slash["x1"] + 2.5]
        if len(num) != 1 or len(den) != 1 or not num[0]["bottom"] < den[0]["bottom"]:
            continue
        x0, x1 = num[0]["x0"], den[0]["x1"]
        host = min((c for c in chars if c["size"] >= SUPERSCRIPT * body and abs(c["bottom"] - den[0]["bottom"]) < body
                    and min(abs(c["x1"] - x0), abs(c["x0"] - x1)) < 3 * body),
                   key=lambda c: min(abs(c["x1"] - x0), abs(c["x0"] - x1)), default=None)
        if host is None:
            continue
        for c in (num[0], slash, den[0]):
            c.update(top=host["top"], bottom=host["bottom"], size=host["size"])
        slash["in_fraction"] = den[0]["in_fraction"] = True      # no space inside "1/2"
        num[0]["in_fraction"] = True
        before = [c for c in chars if c["size"] >= SUPERSCRIPT * body and c["text"].isdigit()
                  and abs(c["bottom"] - host["bottom"]) < 1 and 0 <= x0 - c["x1"] <= 0.6 * body]
        if before:
            num[0]["after_number"] = True            # "2 1/2", never "21/2"
        joined += 1
    return joined


def spelled(chars: list[dict]) -> tuple[list[dict], int]:
    """Each glyph fraction as its digits ("½" -> "1", "/", "2", sharing its box; after a digit, written "2 1/2"), each
    ligature as its letters. Returns the characters and how many fractions were written in digits."""
    out, written = [], 0
    for c in chars:
        spell = GLYPHS.get(c["text"]) or LIGATURES.get(c["text"]) or (c["text"] if len(c["text"]) > 1 else None)
        if not spell:
            out.append(c)
            continue
        width = (c["x1"] - c["x0"]) / len(spell)
        for k, letter in enumerate(spell):
            out.append(c | {"text": letter, "x0": c["x0"] + k * width, "x1": c["x0"] + (k + 1) * width})
        if c["text"] in GLYPHS:
            written += 1
            if len(out) > len(spell) and out[-len(spell) - 1]["text"].isdigit() \
                    and abs(out[-len(spell) - 1]["top"] - c["top"]) < LINE_GAP * c["size"]:
                out[-len(spell)]["after_number"] = True          # "2 1/2", never "21/2"
    return out, written


def read_in_columns(chars: list[dict], width: float, body: float) -> list[dict]:
    """The lines of one page in reading order: bands from the top, a line across the gutter a band of its own, and
    between such lines the left column's lines, then the right column's. A row of letters all more than TALL times
    the page's normal size (NFPA's licence number, stamped large across the middle of every page) is no band: it
    would part the columns where the book doesn't, so it is read last, a line of its own."""
    rows = _rows(chars)
    gutter = find_gutter(chars, width)
    stamps = [r for r in rows if min(c["size"] for c in r) > TALL * body]
    out: list[dict] = []
    left: list[list[dict]] = []
    right: list[list[dict]] = []
    for row in rows:
        if any(row is s for s in stamps):
            continue
        parts = _split(row, gutter)
        if parts is None:                    # runs across the gutter: a band of its own
            out += [_line(r) for r in _sublines(left) + _sublines(right)] + [_line(row)]
            left, right = [], []
        else:
            if parts[0]:
                left.append(parts[0])
            if parts[1]:
                right.append(parts[1])
    out += [_line(r) for r in _sublines(left) + _sublines(right)]
    return out + [_line(r) for r in stamps]


def find_gutter(chars: list[dict], width: float) -> float | None:
    """The x of the page's gutter: the middle of the widest run of the page's middle crossed by the fewest characters,
    give or take SLACK (a running head, a wide table or NFPA's licence number crosses it, a column never does). None
    when even that run is narrower than GUTTER_MIN (a page in one column, or a whole-page table)."""
    lo, hi = int(MIDDLE[0] * width * 2), int(MIDDLE[1] * width * 2)
    steps = [0] * (hi - lo + 1)          # how many characters cross each half point, counted by where they start and end
    for c in chars:
        a, b = max(lo, math.floor(c["x0"] * 2) + 1), min(hi, math.ceil(c["x1"] * 2))   # half points strictly inside
        if a < b:
            steps[a - lo] += 1
            steps[b - lo] -= 1
    crossing, n = [], 0
    for k in range(hi - lo):
        n += steps[k]
        crossing.append(n)
    if not crossing:
        return None
    few = min(crossing) + SLACK
    best, start = None, None
    for k, n in enumerate(crossing + [few + 1]):
        if n <= few and start is None:
            start = k
        elif n > few and start is not None:
            if best is None or k - start > best[1] - best[0]:
                best = (start, k)
            start = None
    a, b = (lo + best[0]) / 2, (lo + best[1]) / 2
    return (a + b) / 2 if b - a >= GUTTER_MIN else None


def _rows(chars: list[dict]) -> list[list[dict]]:
    """Characters in rows across the page, top to bottom: a character joins the row whose foot (baseline) is within
    LINE_GAP of the smaller of their sizes; a smaller character raised within the row's height (a footnote marker)
    joins it too. Each row is measured by its first full-size character, so a tall mark down the margin (the scan's
    OCR reads ICC's change bars as a tall "I") is a row of its own and never pulls the lines beside it into one."""
    rows: list[dict] = []
    for c in sorted(chars, key=lambda c: (c["bottom"], c["x0"])):
        for row in reversed(rows[-8:]):
            if abs(c["bottom"] - row["bottom"]) <= LINE_GAP * min(c["size"], row["size"]) \
                    and max(c["size"], row["size"]) <= TALL * min(c["size"], row["size"]) or \
                    (c["size"] < SUPERSCRIPT * row["size"] and c["bottom"] < row["bottom"]
                     and c["top"] >= row["bottom"] - 1.3 * row["size"]):
                row["chars"].append(c)
                if row["size"] < SUPERSCRIPT * c["size"]:        # the row was begun by a small character
                    row.update(bottom=c["bottom"], size=c["size"])
                break
        else:
            rows.append({"bottom": c["bottom"], "size": c["size"], "chars": [c]})
    return [sorted(r["chars"], key=lambda c: c["x0"]) for r in sorted(rows, key=lambda r: r["bottom"])]


def _split(row: list[dict], gutter: float | None) -> tuple[list[dict], list[dict]] | None:
    """A row's characters left and right of the gutter, or None when the row runs across it (a character crosses it,
    or the gap at it is narrower than GUTTER_MIN)."""
    if gutter is None:
        return None
    left = [c for c in row if c["x1"] <= gutter]
    right = [c for c in row if c["x0"] >= gutter]
    if len(left) + len(right) < len(row):
        return None
    if left and right and right[0]["x0"] - left[-1]["x1"] < GUTTER_MIN:
        return None
    return left, right


def _sublines(rows: list[list[dict]]) -> list[list[dict]]:
    """One column's rows, as they are (each already one line of that column), top to bottom by their middle
    character's foot."""
    return sorted(rows, key=lambda r: sorted(c["bottom"] for c in r)[len(r) // 2])


def _line(chars: list[dict]) -> dict:
    """One line: its characters left to right, its text with a space at each gap wider than WORD_GAP of the letters'
    size, and its box."""
    chars = sorted(chars, key=lambda c: c["x0"])
    text = []
    for k, c in enumerate(chars):
        if k and c["x0"] - chars[k - 1]["x1"] > WORD_GAP * max(c["size"], chars[k - 1]["size"]) \
                and not c.get("after_number") and not (c.get("in_fraction") and chars[k - 1].get("in_fraction")):
            text.append(" ")
        text.append(c["text"])
    return {"text": "".join(text), "chars": chars, "x0": min(c["x0"] for c in chars), "top": min(c["top"] for c in chars),
            "x1": max(c["x1"] for c in chars), "bottom": max(c["bottom"] for c in chars)}
