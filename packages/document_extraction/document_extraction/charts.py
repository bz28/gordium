"""Read the zoning chart tables into cells: which value sits in which row, under which district.

Output (one JSON object per line, "<pdf name>.cells.jsonl"):
    {"file": ..., "sha256": ..., "pages": [2, 3, 14], "reader": ...}                       <- header
    {"page": 3, "label": {..}, "columns": [{"name": "R-1B", "x0": .., "x1": .., "headers": [...]}, ...],
     "top": .., "bottom": ..}                                                            <- per page
    {"page": 3, "section": "Yard Dimensions", "row": "Front (minimum)", "heading": false, "row_lines": [37],
     "column": "R-1B", "value": "25 ft", "lines": [37], "spans": ["R-1B"], "x0": .., "top": .., ...}
    {"page": 3, "unresolved": "why", "text": "...", "lines": [..], ...}

How the table is found, using only what the PDF draws (plain code, no AI, no judgment):
- The chart is drawn as filled rectangles: the header cells, and every other (shaded) body row. A
  white row is the gap between two shaded rows; the last white row is the lines right after the
  last shaded row that are close together and fit the columns. Lines there that don't fit (the notes
  below a chart run across the columns) are reported as unresolved, so nothing is silently dropped.
- Columns come from the header rectangles whose text is a district name (R-1A … R-3B, RU) and that
  have no other district name under them ("R-1" groups R-1A and R-1B), plus any other header column
  beside them (e.g. "Additional Regulations"). The row label is left of them.
- In each row, a drawn rectangle, or a gap between drawn vertical borders, that covers several
  columns is one merged cell ("1 space per dwelling unit" for every district); elsewhere each column
  is its own cell. A row whose cells are all empty is a heading ("Yard Dimensions") for the rows below.
- Each word is placed in the cell that contains it. A word that crosses a cell edge, a drawn cell
  reaching from the label into the columns, a cell that covers part of a column, a label area that
  isn't exactly one cell, a column left without a cell, values with no row label, and a row that
  looks like two rows, or a column covered by two cells make the whole row unresolved: none of its
  values are written, and it can't become a heading. District names at different heights, any drawn
  rectangle or border dividing the label area (a column left of the districts, named or not), and a
  table with no drawn body rows make the page unresolved.
  Nothing is guessed.
Lines and footnote markers ([fn11]) come from the text extractor, so line numbers match
2_extracted_text and a cited line can be traced to its cells.
"""

import re
import statistics
from dataclasses import dataclass, field

import pdfplumber

from .extract import EXTRACTOR, footnote_marks, page_lines, sha256

READER = f"{EXTRACTOR}; cells from drawn rectangles (charts.py)"
DISTRICT = re.compile(r"(R-\d[A-Z]*|RU)")      # a district column's name, as the chart prints it
EDGE = 1.0          # points: a word or cell may overhang an edge by this much (drawing rounding)
ROW_GAP = 0.75      # lines of one row are closer than this share of the normal row height


@dataclass
class Token:
    """A word (or footnote marker) on a line, with its place on the page."""
    text: str
    line: int
    x0: float
    x1: float
    top: float
    bottom: float
    space_before: bool


@dataclass
class Band:
    """One table row's vertical extent, and the drawn rectangles in it."""
    top: float
    bottom: float
    rects: list = field(default_factory=list)


def line_tokens(line: dict, number: int, body: float) -> list[Token]:
    """The line's words in reading order. A footnote marker is its own token "[fnN]", so a cell
    value reads exactly like the extracted text ("2,500 sf [fn4]", "•[fn5]")."""
    tokens, current, space, i = [], None, False, 0
    for t, mark in zip(line["text"], footnote_marks(line, body)):
        if t == " ":
            current, space = None, True
            continue
        c = line["chars"][i]
        i += 1
        if current is None or current["mark"] != mark:
            current = {"mark": mark, "chars": [], "space": space and bool(tokens)}
            tokens.append(current)
            space = False
        current["chars"].append((t, c))
    out = []
    for tok in tokens:
        text = "".join(t for t, _ in tok["chars"])
        cs = [c for _, c in tok["chars"]]
        out.append(Token(f"[fn{text}]" if tok["mark"] else text, number, min(c["x0"] for c in cs),
                         max(c["x1"] for c in cs), min(c["top"] for c in cs), max(c["bottom"] for c in cs),
                         tok["space"]))
    return out


def render(tokens: list[Token]) -> str:
    """Tokens back to text, keeping the spacing of each line; lines are joined by a space."""
    out = []
    for n, tok in enumerate(tokens):
        if n and (tok.space_before or tok.line != tokens[n - 1].line):
            out.append(" ")
        out.append(tok.text)
    return "".join(out)


def _strip_footnotes(text: str) -> str:
    return re.sub(r"\s*\[fn[^\]]*\]", "", text).strip()


def _within(inner_x0, inner_x1, outer_x0, outer_x1) -> bool:
    return inner_x0 >= outer_x0 - EDGE and inner_x1 <= outer_x1 + EDGE


def read_page(page, page_number: int) -> list[dict]:
    """The page's column record, then one record per cell (or unresolved piece)."""
    lines, body = page_lines(page)
    tokens = {n: line_tokens(line, n, body) for n, line in enumerate(lines, 1)}
    rects = [r for r in page.rects if r["width"] > EDGE and r["height"] > EDGE]
    verticals = [v for v in page.lines if abs(v["x0"] - v["x1"]) < EDGE]
    if not rects:
        return [{"page": page_number, "unresolved": "no table drawn on this page"}]

    def text_in(r):
        return render([t for n in tokens for t in tokens[n]
                       if _within(t.x0, t.x1, r["x0"], r["x1"]) and t.top >= r["top"] - EDGE
                       and t.bottom <= r["bottom"] + EDGE])

    # Columns: header rectangles named like a district, then any other header column beside them.
    named = [(r, _strip_footnotes(text_in(r))) for r in rects]
    labelled = [(r, n) for r, n in named if DISTRICT.fullmatch(n)]
    # A district is a named header with no other named header under it ("R-1" groups R-1A and R-1B).
    districts = sorted([(r, n) for r, n in labelled
                        if not any(o is not r and _within(o["x0"], o["x1"], r["x0"], r["x1"]) and o["top"] > r["top"]
                                   for o, _ in labelled)], key=lambda rn: rn[0]["x0"])
    if not districts:
        return [{"page": page_number, "unresolved": "no district header found"}]
    # The district headers are one header line: a district name lower down is a body cell's text, and
    # choosing between them would be a guess.
    if max(r["bottom"] for r, _ in districts) - min(r["bottom"] for r, _ in districts) > EDGE:
        return [{"page": page_number, "unresolved": "district names at different heights; can't tell the header",
                 "text": ", ".join(n for _, n in districts)}]
    header_bottom = max(r["bottom"] for r, _ in districts)
    left = min(r["x0"] for r in rects)
    label_x1 = min(r["x0"] for r, _ in districts)
    # The label area must be one undivided column on the whole page: any drawn rectangle or border
    # inside it (named or not, header or body) could be a column whose values would be read as label.
    stray = [n or "(unnamed)" for r, n in named if r["x0"] > left + EDGE and r["x1"] <= label_x1 + EDGE]
    stray += ["(border)" for v in verticals if left + EDGE < v["x0"] < label_x1 - EDGE]
    if stray:
        return [{"page": page_number, "unresolved": "the label area is divided: a column left of the districts?",
                 "text": ", ".join(stray)}]
    columns = [{"name": n, "x0": r["x0"], "x1": r["x1"]} for r, n in districts]
    for r, n in named:
        if (r["top"] < header_bottom - EDGE and n and r["x0"] >= label_x1 - EDGE
                and not any(r["x0"] < c["x1"] - EDGE and r["x1"] > c["x0"] + EDGE for c in columns)):
            columns.append({"name": n, "x0": r["x0"], "x1": r["x1"]})
    columns.sort(key=lambda c: c["x0"])
    for c in columns:   # every header cell above a column, top to bottom ("R-1 [fn1,2]", "R-1B")
        c["headers"] = [text_in(r) for r in sorted(rects, key=lambda r: r["top"])
                        if r["bottom"] <= header_bottom + EDGE and r["x0"] <= c["x0"] + EDGE
                        and r["x1"] >= c["x1"] - EDGE and text_in(r)]
    grid = [(left, label_x1)] + [(c["x0"], c["x1"]) for c in columns]

    def cells_for(top, bottom, drawn):
        """A row's cells: drawn rectangles, then the gaps between drawn vertical borders that run the
        row's full height, then the label and one cell per column for the rest of the width."""
        cells = [(r["x0"], r["x1"]) for r in drawn]
        edges = sorted({round(v["x0"], 1) for v in verticals if v["top"] <= top + EDGE and v["bottom"] >= bottom - EDGE})
        for between in zip(edges, edges[1:]):
            if not any(between[0] < x1 - EDGE and between[1] > x0 + EDGE for x0, x1 in cells):
                cells.append(between)
        cells += [g for g in grid if not any(g[0] < x1 - EDGE and g[1] > x0 + EDGE for x0, x1 in cells)]
        return sorted(set(cells))   # a cell drawn twice is still one cell

    out = [{"page": page_number, "label": {"x0": round(left, 1), "x1": round(label_x1, 1)},
            "columns": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in c.items()} for c in columns]}]

    # Rows: shaded bands from the drawn rectangles; white rows are the gaps between them.
    shaded = {}
    for r in rects:
        if r["top"] >= header_bottom - EDGE:
            shaded.setdefault((round(r["top"], 1), round(r["bottom"], 1)), []).append(r)
    bands = [Band(t, b, rs) for (t, b), rs in sorted(shaded.items())]
    merged = []
    for band in bands:   # one row can be drawn as several rectangles of different heights
        if merged and band.top < merged[-1].bottom - EDGE:
            merged[-1].bottom = max(merged[-1].bottom, band.bottom)
            merged[-1].rects += band.rects
        else:
            merged.append(band)
    bands = []
    edge = header_bottom
    for band in merged:
        if band.top > edge + EDGE:
            bands.append(Band(edge, band.top))
        bands.append(band)
        edge = band.bottom
    if not merged:
        return out + [{"page": page_number, "unresolved": "no body rows drawn under the header"}]
    row_height = statistics.median(b.bottom - b.top for b in bands)
    # The last white row: the lines right after the last shaded row that are close together. It's a
    # row if every word fits its cells; if not, it's what follows the table (the notes run across the
    # columns), and it's reported as unresolved so a row the reader can't split is never just lost.
    after = [n for n in sorted(tokens) if lines[n - 1]["top"] >= edge - EDGE]
    if after and lines[after[0] - 1]["top"] < edge + row_height:
        last = [after[0]]
        for n in after[1:]:
            if lines[n - 1]["top"] - lines[last[-1] - 1]["top"] >= ROW_GAP * row_height:
                break
            last.append(n)
        bottom = max(lines[n - 1]["bottom"] for n in last)
        cells = cells_for(edge, bottom, [])
        if all(any(_within(t.x0, t.x1, *cell) for cell in cells) for n in last for t in tokens[n]):
            bands.append(Band(edge, bottom))
        else:
            out.append({"page": page_number, "unresolved": "lines right after the table don't fit its columns",
                        "text": render([t for n in last for t in tokens[n]]), "lines": last})
    table_top, table_bottom = header_bottom, bands[-1].bottom if bands else header_bottom

    section = None
    placed = set()
    for band in bands:
        in_band = [n for n in sorted(tokens) if band.top - EDGE <= (lines[n - 1]["top"] + lines[n - 1]["bottom"]) / 2
                   <= band.bottom + EDGE and n not in placed]
        placed.update(in_band)
        if not in_band:
            continue
        tops = [lines[n - 1]["top"] for n in in_band]
        if any(b - a >= ROW_GAP * row_height for a, b in zip(tops, tops[1:])):
            out.append({"page": page_number, "unresolved": "band looks like more than one row",
                        "text": render([t for n in in_band for t in tokens[n]]), "lines": in_band})
            continue
        cells = cells_for(band.top, band.bottom, band.rects)
        contents = {cell: [] for cell in cells}
        problems = []   # anything uncertain makes the whole row unresolved: no partial row is written

        def problem(why, toks):
            toks = sorted(toks, key=lambda t: (t.line, t.x0))
            problems.append({"page": page_number, "unresolved": why, "text": render(toks),
                             "lines": sorted({t.line for t in toks}) or in_band})

        for n in in_band:
            for tok in tokens[n]:
                home = [cell for cell in cells if _within(tok.x0, tok.x1, *cell)]
                if len(home) == 1:
                    contents[home[0]].append(tok)
                else:
                    problem("word crosses a cell edge", [tok])
        label_cells, values = [], {}
        for cell in cells:
            covered = [c["name"] for c in columns if _within(c["x0"], c["x1"], *cell)]
            if _within(cell[0], cell[1], left, label_x1):
                label_cells.append(cell)
            elif cell[0] < label_x1 - EDGE:
                # A drawn cell reaching from the label into the columns (a whole-row stripe, an outer
                # border) can't say which words are the label and which are values.
                problem("cell covers the label and a column", contents[cell])
            elif any(c["x0"] < cell[1] - EDGE and c["x1"] > cell[0] + EDGE and c["name"] not in covered
                     for c in columns):
                problem("cell covers part of a column", contents[cell])
            elif not covered:
                if contents[cell]:
                    problem("cell under no column", contents[cell])
            elif any(name in values for name in covered):
                problem("column covered by more than one cell",
                        contents[cell] + [t for name in covered if name in values for t in values[name][4]])
            else:
                toks = sorted(contents[cell], key=lambda t: (t.line, t.x0))
                for name in covered:
                    values[name] = (render(toks), sorted({t.line for t in toks}), covered, cell, toks)
        # Every row is one label cell and one cell per column, or it isn't read.
        if len(label_cells) != 1:
            problem("label area is split into cells" if label_cells else "row has no label cell",
                    [t for cell in label_cells for t in contents[cell]])
        missing = [c["name"] for c in columns if c["name"] not in values]
        if missing and not problems:
            problem(f"no cell for {', '.join(missing)}", [t for cell in cells for t in contents[cell]])
        row = render(sorted((t for cell in label_cells for t in contents[cell]), key=lambda t: (t.line, t.x0)))
        if not row and any(v[0] for v in values.values()):
            problem("values with no row label", [t for cell in cells for t in contents[cell]])
        if problems:
            out += problems
            continue
        is_heading = row and not any(v[0] for v in values.values())
        if is_heading:
            section = row
        for c in columns:
            if c["name"] not in values:
                continue
            value, value_lines, spans, cell, _ = values[c["name"]]
            out.append({"page": page_number, "section": section if not is_heading else None, "row": row,
                        "heading": bool(is_heading), "row_lines": in_band, "column": c["name"], "value": value,
                        "lines": value_lines, "spans": spans, "x0": round(cell[0], 1), "top": round(band.top, 1),
                        "x1": round(cell[1], 1), "bottom": round(band.bottom, 1)})
    out[0] |= {"top": round(table_top, 1), "bottom": round(table_bottom, 1)}
    return out


def read_charts(pdf_path, pages: list[int]) -> list[dict]:
    """The header, then each listed page's columns and cells."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for n in pages:
            rows += read_page(pdf.pages[n - 1], n)
    return [{"file": pdf_path.name, "sha256": sha256(pdf_path), "pages": pages, "reader": READER}, *rows]
