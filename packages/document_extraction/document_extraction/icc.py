"""Pull every line of text out of an ICC-published code book (layout: icc in sources.yaml), such as the 2025
Residential Code of New York State, with its page and position. The output has the same shape as extract.py's
(a header row, then one {"page", "line", "text", x0, top, x1, bottom} per line), so quotes are checked the same way.

What is different from extract.py: ICC books print a fraction as a small raised numerator, a full-size slash and a
small lowered denominator (9/16 inch). Read line by line, the denominator falls onto a line of its own ("... than 9/"
then "16"), and the numerator looks like a footnote marker ("[fn9]/"): a quote would then read "not greater than 9"
where the book says nine-sixteenths. So, before lines are formed, each such fraction is put back together on its
line: numerator, slash and denominator become one word "9/16". A fraction right after a whole number is written
with a space ("1 1/4": one and a quarter), so it can never read as "11/4". Any small raised character that is not
part of a fraction is a footnote marker, as in extract.py ("[fna]").

Plain code, no AI, no judgment: the same PDF always gives the same file.
"""

from importlib.metadata import version
from pathlib import Path

import pdfplumber

from .extract import POSITION, SUPERSCRIPT, _body_size, _level, footnote_marks, sha256

EXTRACTOR = (f"pdfplumber {version('pdfplumber')} + pdfminer.six {version('pdfminer.six')} "
             "(icc layout: dedupe_chars, level text only, stacked fractions joined, extract_text_lines, "
             "footnotes as [fnN])")
TOUCH = 0.8          # points: how close a numerator or denominator must sit to its slash


def extract_icc(pdf_path: Path, pages: list[int] | None = None) -> list[dict]:
    """The header row, then one row per line of text, page by page, top to bottom. `pages`: only these pages
    (1-based), for a book whose brought-in sections are a small part of it; None reads every page. Each page's
    cached objects are dropped once it is read, so a 1,000-page book is read in little memory."""
    rows, rotated, fractions = [], 0, 0
    with pdfplumber.open(pdf_path) as pdf:
        wanted = range(1, len(pdf.pages) + 1) if pages is None else pages
        for page_number in wanted:
            page = pdf.pages[page_number - 1]
            rotated += sum(not _level(c) for c in page.chars)
            lines, body, joined = icc_page_lines(page)
            fractions += joined
            for n, line in enumerate(lines, 1):
                text, styles = line_text(line, body)
                rows.append({"page": page_number, "line": n, "text": text,
                             **{k: round(line[k], 1) for k in POSITION}, **{k: v for k, v in styles.items() if v}})
            page.close()
        header = {"file": pdf_path.name, "sha256": sha256(pdf_path), "pages": len(pdf.pages),
                  "extractor": EXTRACTOR, "rotated_chars_skipped": rotated, "fractions_joined": fractions,
                  "pages_read": "all" if pages is None else list(pages)}
    return [header, *rows]


def icc_page_lines(page) -> tuple[list[dict], float, int]:
    """A page's lines of level text, its normal text size, and how many stacked fractions were joined."""
    level = page.dedupe_chars().filter(lambda o: o.get("object_type") != "char" or _level(o))
    body = _body_size(level)
    chars = [dict(c) for c in level.chars]
    joined = join_fractions(chars, body)
    textmap = pdfplumber.utils.chars_to_textmap(chars, layout_bbox=page.bbox, layout_width=page.width,
                                                layout_height=page.height)
    return textmap.extract_text_lines(strip=True, return_chars=True), body, joined


def line_text(line: dict, body: float) -> tuple[str, dict[str, list[list[int]]]]:
    """A line's text, with each footnote marker sealed ("[fna]", as extract.py does) and a space put before a
    fraction that follows a whole number ("1 1/4"); and where the text is in italics and in bold, as [start, end]
    offsets into it ({"italic": [...], "bold": [...]}). The book prints its defined terms in italics (R201.1), so the
    italics say which definitions a section uses; it prints each section's number and title, and each defined term
    where it is defined, in bold, so the bold says where a section or a definition starts."""
    out, in_run, i = [], False, 0
    slanted: list[bool] = []                     # one per character of `out`
    heavy: list[bool] = []
    chars = line["chars"]
    for t, mark in zip(line["text"], footnote_marks(line, body)):
        if mark != in_run:  # a space is never marked, so a run always closes before it
            out.append("[fn" if mark else "]")
            slanted += [False] * len(out[-1])          # one entry per character, so the offsets are the text's
            heavy += [False] * len(out[-1])
            in_run = mark
        if t != " ":
            if chars[i].get("after_number") and out and out[-1] != " ":
                out.append(" ")
                slanted.append(False)
                heavy.append(False)
            slanted.append(_italic(chars[i]))
            heavy.append(_bold(chars[i]))
            i += 1
        else:                                    # a space inside a run of italic words is italic too
            slanted.append(None)
            heavy.append(None)
        out.append(t)
    if in_run:
        out.append("]")
        slanted.append(False)
        heavy.append(False)
    return "".join(out), {"italic": _runs(slanted), "bold": _runs(heavy)}


def _italic(char: dict) -> bool:
    name = char.get("fontname", "").split("+")[-1]
    return "-It" in name or "Italic" in name or "Oblique" in name


def _bold(char: dict) -> bool:
    return "Bold" in char.get("fontname", "").split("+")[-1]


def _runs(slanted: list) -> list[list[int]]:
    """[start, end] (end exclusive) of each run of italic characters; a space joins two italic words."""
    runs, start = [], None
    for k, v in enumerate(slanted + [False]):
        if v is None:
            following = next((w for w in slanted[k + 1:] if w is not None), False)
            v = start is not None and following
        if v and start is None:
            start = k
        elif not v and start is not None:
            runs.append([start, k])
            start = None
    return runs


def join_fractions(chars: list[dict], body: float) -> int:
    """Put each stacked fraction back on its line, in place: a full-size "/" with small digits touching it on
    the left, raised (the numerator), and small digits touching it on the right, lowered (the denominator).
    The digits take the slash's height and size, so they read as one word with it; a fraction right after a
    digit gets a space before it ("1 1/4"). Returns how many fractions were joined."""
    small = lambda c: c["size"] < SUPERSCRIPT * body and c["text"].isdigit()
    joined = 0
    for slash in chars:
        if slash["text"] != "/" or slash["size"] < SUPERSCRIPT * body:
            continue
        numerator = _run(chars, slash, small, left=True)
        denominator = _run(chars, slash, small, left=False)
        if not numerator or not denominator:
            continue
        if not (all(chars[i]["bottom"] < slash["bottom"] - 1 for i in numerator)
                and all(chars[i]["bottom"] > slash["bottom"] for i in denominator)):
            continue
        for i in numerator + denominator:
            chars[i].update(top=slash["top"], bottom=slash["bottom"], size=slash["size"],
                            y0=slash["y0"], y1=slash["y1"], doctop=slash["doctop"])
        before = [c for c in chars if c is not slash and abs(c["top"] - slash["top"]) < 1
                  and c["size"] >= SUPERSCRIPT * body and abs(c["x1"] - chars[numerator[0]]["x0"]) <= TOUCH]
        if before and before[0]["text"].isdigit():
            chars[numerator[0]]["after_number"] = True     # written "1 1/4", never "11/4"
        joined += 1
    return joined


def _run(chars: list[dict], slash: dict, small, left: bool) -> list[int]:
    """The small digits touching `slash` on one side, in reading order: indexes into `chars`."""
    run, edge = [], slash["x0"] if left else slash["x1"]
    while True:
        near = [i for i, c in enumerate(chars) if small(c) and i not in run
                and abs((c["x1"] if left else c["x0"]) - edge) <= TOUCH
                and abs(c["top"] - slash["top"]) < slash["size"]]
        if not near:
            break
        i = near[0]
        run.append(i)
        edge = chars[i]["x0"] if left else chars[i]["x1"]
    return run[::-1] if left else run
