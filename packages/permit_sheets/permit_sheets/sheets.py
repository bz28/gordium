"""The three egress sheets laid out on 11 x 17 in (ANSI B, landscape), US permit-set style: a title block down the
right edge, the drawing or table in the rest. Plain code, no AI; every word and number comes from source.gather and
tables (the check's), placed here.

    pages = sheets(got, project)                # [(sheet number, sheet title, draw.Page)], in set order
"""

import math

from design_checker import egress, present

from . import plan as plan_mod
from .draw import PT, Page, width, wrap
from .tables import COLUMNS, code_rows, schedule_rows
from .words import WAITING, result_words

W_IN, H_IN = 17.0, 11.0
LEFT, EDGE = 0.75 * PT, 0.3 * PT                # binding margin on the left, as on a bound permit set
TB_W = 2.7 * PT                                 # the title block's strip
INK, GRID, HEAD, MUTED = "#1a1a1a", "#8c8c8c", "#e6e6e6", "#5a5a5a"
LOOK = {present.FAILS: ("#b3261e", "#fbe3e1"), present.REVIEW: ("#8a5300", "#fff1d6"),
        present.NOT_CHECKED: ("#4a4a4a", "#ececec"), present.COMPLIES: ("#1e6b34", "#e3f2e6"), None: (INK, None)}
DISCLAIMER = "Prepared with Gordium: draft rules, verify before submission"
SCALES = [(1 / 2, '1/2" = 1\'-0"'), (3 / 8, '3/8" = 1\'-0"'), (1 / 4, '1/4" = 1\'-0"'), (3 / 16, '3/16" = 1\'-0"'),
          (1 / 8, '1/8" = 1\'-0"'), (3 / 32, '3/32" = 1\'-0"'), (1 / 16, '1/16" = 1\'-0"')]


def _status_of_words(words: str) -> str:
    return next((s for s, w in [(present.FAILS, "DOES NOT COMPLY"), (present.REVIEW, "NEEDS REVIEW"),
                                (present.COMPLIES, "COMPLIES")] if words == w),
                present.NOT_CHECKED if words.startswith(WAITING) else None)


# ---- the frame and title block --------------------------------------------------------------------------------------

def _frame(page: Page, info: dict, number: str, title: str, n: int, of: int) -> None:
    w, h = page.w, page.h
    page.rect(LEFT, EDGE, w - LEFT - EDGE, h - 2 * EDGE, stroke=INK, lw=1.2)
    x0 = w - EDGE - TB_W
    page.line(x0, EDGE, x0, h - EDGE, stroke=INK, lw=1.2)
    pad, x, y = 8, x0 + 8, EDGE + 8
    room = TB_W - 2 * pad
    # the warning first, boxed: the rules are drafts (approval deferred, CLAUDE.md principle 2)
    lines = wrap(DISCLAIMER, 9, room - 8, bold=True)
    box_h = 12 + 11 * len(lines)
    page.rect(x, y, room, box_h, stroke="#b3261e", fill="#fbe3e1", lw=1.0)
    for i, ln in enumerate(lines):
        page.text(x + 4, y + 14 + 11 * i, ln, size=9, bold=True, fill="#b3261e")
    y += box_h + 12

    def field(label, value, size=7.5, bold=False, mono_wrap=False):
        nonlocal y
        page.text(x, y, label.upper(), size=5.5, fill=MUTED)
        y += 9
        for ln in wrap(value, size, room, bold):
            page.text(x, y, ln, size=size, bold=bold, fill=INK)
            y += size + 2.5
        y += 4
        page.line(x0, y - 2, w - EDGE, y - 2, stroke=GRID, lw=0.3)
        y += 6

    field("Project", info["project"], size=9, bold=True)
    if info.get("address"):
        field("Address", info["address"])
    field("Code checked", info["laws"])
    field("Egress result (Gordium's check)", info["headline"], size=8, bold=True)
    field("Date", info["date"])
    field("Rulebook", f"{info['rulebook']} · status: draft · sha256 {info['rulebook_sha256']}", size=5.5)
    field("Rules fingerprint at check", info["fingerprints"], size=5.5)
    field("Gordium code fingerprint at check", info["worker"], size=5.5)
    field("Interior drawing checked", info["interior"], size=5.5)
    # the architect's stamp: left blank for them
    stamp_top, stamp_h = y, 1.35 * PT
    page.rect(x, stamp_top, room, stamp_h, stroke=GRID, lw=0.5, dash=(2, 2))
    page.text(x + room / 2, stamp_top + stamp_h / 2 + 2, "ARCHITECT'S STAMP AND SIGNATURE", size=5.5,
              anchor="middle", fill=MUTED)
    # sheet title and number at the foot, where a reviewer looks for them
    yb = h - EDGE - 1.15 * PT
    page.line(x0, yb, w - EDGE, yb, stroke=INK, lw=1.0)
    for i, ln in enumerate(wrap(title.upper(), 8.5, room, bold=True)[:3]):
        page.text(x, yb + 14 + 11 * i, ln, size=8.5, bold=True)
    page.text(x, h - EDGE - 10, f"SHEET {n} OF {of}", size=6, fill=MUTED)
    page.text(w - EDGE - pad, h - EDGE - 10, number, size=22, bold=True, anchor="end")


def _info(got: dict, project: dict, headline: str) -> dict:
    laws = got["laws"]
    fps = {k: v for law in laws for k, v in law["fingerprints"].items()}
    return {"project": project["title"], "address": project.get("address") or "", "date": project["date"],
            "laws": "; ".join(law["title"] for law in laws), "headline": headline,
            "rulebook": "; ".join(law["rulebook"] for law in laws),
            "rulebook_sha256": "; ".join(law["rulebook_sha256"] for law in laws),
            "fingerprints": "; ".join(f"{k} {v}" for k, v in sorted(fps.items())) or "none",
            "worker": got.get("worker_fingerprint") or "not given",
            "interior": (f"fingerprint {got['interior_sha256']} (sha256 of the description as sorted-key JSON, "
                         "the check's own)") if got["interior_sha256"] else "none drawn yet"}


def _heading(page: Page, title: str, lines: list[tuple[str, str | None]]) -> float:
    """The sheet's own heading, top left, and its lines (text, status for colour); the y below it."""
    x, y = LEFT + 14, EDGE + 26
    page.text(x, y, title, size=14, bold=True)
    y += 16
    for text, status in lines:
        for ln in wrap(text, 7.5, page.w - LEFT - EDGE - TB_W - 28, bold=status is not None):
            page.text(x, y, ln, size=7.5, bold=status is not None, fill=LOOK[status][0])
            y += 10
    return y + 6


# ---- tables -----------------------------------------------------------------------------------------------------------

def _table_pages(columns, rows, make_page, size=7.0):
    """Lay `rows` (each a list of cells: text, or (text, status) for a result) under a header, page after page;
    `make_page()` gives a fresh page and the y its table starts at."""
    lead = size + 2
    x_left = LEFT + 14
    total = sum(wd for _, wd in columns)
    scale = (W_IN * PT - LEFT - EDGE - TB_W - 28) / total
    widths = [wd * scale for _, wd in columns]

    def header(page, y):
        cells = [wrap(name, size, wd - 6, bold=True) for (name, _), wd in zip(columns, widths)]
        hh = 6 + lead * max(len(c) for c in cells)
        page.rect(x_left, y, sum(widths), hh, stroke=INK, fill=HEAD, lw=0.6)
        cx = x_left
        for c, wd in zip(cells, widths):
            for i, ln in enumerate(c):
                page.text(cx + 3, y + 3 + lead * (i + 1) - 2, ln, size=size, bold=True)
            cx += wd
        return y + hh

    pages = []
    page, y = make_page()
    y = header(page, y)
    bottom = page.h - EDGE - 14
    for row in rows:
        if row and row[0] == "__banner__":            # a whole-width line in its result's colours (waiting…)
            text, status = row[1], row[2]
            lines = wrap(text, size + 3, sum(widths) - 16, bold=True)
            hh = (size + 6) * len(lines) + 12
            if y + hh > bottom:
                pages.append(page)
                page, y = make_page()
                y = header(page, y)
            page.rect(x_left, y, sum(widths), hh, stroke=INK, fill=LOOK[status][1], lw=0.6)
            for i, ln in enumerate(lines):
                page.text(x_left + sum(widths) / 2, y + 8 + (size + 6) * (i + 1) - 3, ln, size=size + 3, bold=True,
                          anchor="middle", fill=LOOK[status][0])
            y += hh
            continue
        if row and row[0] == "__group__":
            hh = lead + 6
            if y + hh + lead * 2 > bottom:
                pages.append(page)
                page, y = make_page()
                y = header(page, y)
            page.rect(x_left, y, sum(widths), hh, stroke=INK, fill="#f5f5f5", lw=0.4)
            page.text(x_left + 3, y + lead + 1, row[1], size=size + 0.5, bold=True)
            y += hh
            continue
        cells = []
        for cell, wd in zip(row, widths):
            text, status, small = (tuple(cell) + (None,) * (3 - len(cell))) if isinstance(cell, tuple) \
                else (cell, None, None)
            lines = wrap(text, size, wd - 6, bold=status is not None)
            sm = wrap(small, size - 1.5, wd - 6) if small else []
            cells.append((lines, status, sm))
        hh = 4 + max(lead * len(ln) + (size + 0.5) * len(sm) for ln, _, sm in cells)
        if y + hh > bottom:
            pages.append(page)
            page, y = make_page()
            y = header(page, y)
        cx = x_left
        for (lines, status, sm), wd in zip(cells, widths):
            if status is not None:
                page.rect(cx, y, wd, hh, stroke=None, fill=LOOK[status][1])
            for i, ln in enumerate(lines):
                page.text(cx + 3, y + 2 + lead * (i + 1) - 2, ln, size=size, bold=status is not None,
                          fill=LOOK[status][0])
            for j, ln in enumerate(sm):
                page.text(cx + 3, y + 2 + lead * len(lines) + (size + 0.5) * (j + 1) - 1, ln, size=size - 1.5,
                          fill=MUTED)
            cx += wd
        page.line(x_left, y + hh, x_left + sum(widths), y + hh, stroke=GRID, lw=0.3)
        cx = x_left
        for wd in widths[:-1]:
            cx += wd
            page.line(cx, y, cx, y + hh, stroke=GRID, lw=0.3)
        page.line(x_left, y, x_left, y + hh, stroke=INK, lw=0.6)
        page.line(x_left + sum(widths), y, x_left + sum(widths), y + hh, stroke=INK, lw=0.6)
        y += hh
    page.line(x_left, y, x_left + sum(widths), y, stroke=INK, lw=0.6)
    pages.append(page)
    return pages, y


CODE_COLUMNS = [("#", 0.35), ("Item", 1.7), ("Requirement (rule id below)", 2.9), ("Required", 1.45),
                ("Proposed (as measured)", 1.45), ("Result", 1.2), ("Code section", 0.85),
                ("Why / what to change", 3.7)]


NOT_YET_ITEM = "Not checked yet by Gordium"
NOT_YET_WHY = "{n} code sections Gordium doesn't check yet: check each by hand (listed below; by name in the CSV)"
NOT_YET_BANNER = "{result}: not checked yet by Gordium, check these {n} code sections by hand: {sections}"
WAITING_WHY_SHORT = "{why}. Not checked yet by Gordium, even once the rooms are drawn: {n} code sections (listed below)"


def not_checked_yet(r: dict) -> list[str]:
    """The code sections a row says Gordium doesn't check yet: the egress not-checked-yet line's, or the waiting
    row's (design_checker/egress.py, each item's detail citation); [] for any other row."""
    if not (r["Item id"].endswith("." + egress.NOT_YET_ID) or r["Item id"].endswith(".waiting")):
        return []
    return [s for s in r["Citation"].split(", ") if s]


def code_analysis(got: dict, headline_lines) -> list[tuple[str, Page]]:
    rows, last = [], None
    for r in code_rows(got):
        if r["Law"] != last:
            rows.append(["__group__", r["Law"]])
            last = r["Law"]
        missing = not_checked_yet(r)
        item, requirement, why = r["Item"], r["Requirement"] or r["Item"], r["Why / what to change"]
        if missing and r["Item id"].endswith("." + egress.NOT_YET_ID):       # one line; the sections in a banner
            item, why = NOT_YET_ITEM, NOT_YET_WHY.format(n=len(missing))
        elif missing:                                                         # waiting: its own words, then them
            why = WAITING_WHY_SHORT.format(why=egress.WAITING_WHY, n=len(missing))
        rows.append([str(r["Line"]), item, (requirement, None, r["Rule id"] or None),
                     r["Required"], r["Proposed"], (r["Result"], r["status"]), r["Code section"], why])
        if missing:
            rows.append(["__banner__", NOT_YET_BANNER.format(result=r["Result"], n=len(missing),
                                                             sections=", ".join(missing)), r["status"]])
    made = []

    def page():
        p = Page(W_IN, H_IN)
        y = _heading(p, "CODE ANALYSIS: EGRESS" + (" (CONTINUED)" if made else ""), headline_lines if not made
                     else [])
        made.append(p)
        return p, y
    pages, y = _table_pages(CODE_COLUMNS, rows, page)
    note = ("Every row is a result of Gordium's check, in its order, with the check's own result. Required and "
            "Proposed are shown for reading: worked out from the rule's formula and the measured values, never "
            "rounded toward compliance; they never decide a result. Rows that don't apply are not listed. The CSV "
            "beside this sheet carries each row's rule id, part, measured values, citation and the code's words.")
    last_page = pages[-1]
    for i, ln in enumerate(wrap(note, 6, last_page.w - LEFT - EDGE - TB_W - 28)):
        if y + 14 + 8 * i < last_page.h - EDGE - 6:
            last_page.text(LEFT + 14, y + 14 + 8 * i, ln, size=6, fill=MUTED)
    return pages


SCHEDULE_COLUMNS = [("Mark", 0.5), ("Opening", 1.55), ("Room", 1.15), ("Type", 0.95), ("Net clear width", 1.15),
                    ("Net clear height", 1.15), ("Net clear area", 1.15), ("Sill height (above floor)", 1.15),
                    ("Grade floor", 0.6), ("Result (all its rules)", 1.25), ("Code sections", 1.2), ("Why", 2.0)]


def schedule(got: dict, headline_lines) -> list[Page]:
    rows_, _ = schedule_rows(got)
    rows = []
    for r in rows_:
        if r.get("statement"):          # what wasn't read, or nothing to schedule: a whole-width line, never blank
            rows.append(["__banner__", f"{r['Result']}: {r['Why']}", r["status"]])
            continue
        cells = []
        for m, h, s in COLUMNS:
            st = r["cell_status"][h]
            req = r.get(f"Required {s.lower()}") or ""
            cells.append((r[h], None, f"{req + ' · ' if req else ''}{result_words(st)}"))
        rows.append([r["Mark"], r["Opening"], r["Room"], r["Type"], *cells, r["Grade floor"],
                     (r["Result"], r["status"]), r["Code sections"], r["Why"]])
    lines = list(headline_lines)
    made = []

    def page():
        p = Page(W_IN, H_IN)
        y = _heading(p, "ESCAPE-WINDOW SCHEDULE" + (" (CONTINUED)" if made else ""), lines if not made else [])
        made.append(p)
        return p, y
    pages, y = _table_pages(SCHEDULE_COLUMNS, rows, page)
    note = ("Each measured cell shows the opening's value, the code's limit and that rule's result; the opening's "
            "Result is the most cautious of every rule Gordium checked for it (see the code analysis for each). An "
            "opening the check gave no row for, or marked but not checked, is NEEDS REVIEW, never complies. Net clear "
            "sizes are with the sash fully open by its normal operation; values never rounded toward compliance.")
    for i, ln in enumerate(wrap(note, 6, pages[-1].w - LEFT - EDGE - TB_W - 28)):
        pages[-1].text(LEFT + 14, y + 14 + 8 * i, ln, size=6, fill=MUTED)
    return pages


# ---- the life-safety plan ---------------------------------------------------------------------------------------------

def _legend_box(page, x, y, wd, title, items):
    page.text(x, y, title, size=7, bold=True)
    y += 10
    for text, status in items:
        for ln in wrap(text, 6.5, wd, bold=status is not None):
            page.text(x, y, ln, size=6.5, bold=status is not None, fill=LOOK[status][0])
            y += 8.5
        y += 2
    return y + 6


def _tag(page, x, y, text, status):
    wd = width(text, 6, True) + 8
    page.rect(x, y - 7.5, wd, 10, stroke=LOOK[status][0], fill=LOOK[status][1], lw=0.7)
    page.text(x + 4, y, text, size=6, bold=True, fill=LOOK[status][0])
    return wd


def life_safety(got: dict, headline_lines) -> list[Page]:
    sched, _ = schedule_rows(got)
    lv = plan_mod.levels(got, sched) if not got["waiting"] else {"levels": [], "undrawn": [], "notes": [],
                                                                 "doors": [], "rooms_read": True}
    side_w = 3.3 * PT
    area_x0, area_x1 = LEFT + 14, W_IN * PT - EDGE - TB_W - side_w - 18
    pages = []
    levels = lv["levels"] or [None]
    for n, level in enumerate(levels):
        p = Page(W_IN, H_IN)
        name = "LIFE-SAFETY PLAN" + (f": FLOOR AT {_elev(level['elevation'])}" if level else "")
        y0 = _heading(p, name, headline_lines)
        sx = area_x1 + 14
        y = y0
        if got["waiting"]:              # no interior checked: the check's own answer for it (waiting, or why not)
            from .source import overall
            status, waiting = overall(got)
            words = result_words(status, waiting) + ("" if waiting else ": no interior was checked")
            p.text((area_x0 + area_x1) / 2, (y0 + p.h) / 2, words, size=16, bold=True, anchor="middle",
                   fill=LOOK[status][0])
        elif level:
            _draw_level(p, level, area_x0, y0 + 10, area_x1, p.h - EDGE - 40)
        elif not lv["undrawn"]:
            words, st = ("No rooms drawn", None) if lv["rooms_read"] else \
                ("Rooms not read from the drawing: " + result_words(present.REVIEW), present.REVIEW)
            p.text((area_x0 + area_x1) / 2, (y0 + p.h) / 2, words, size=14, bold=True, anchor="middle",
                   fill=LOOK[st][0])
        # the right column: legend, exits, notes, the schematic way out
        y = _legend_box(p, sx, y, side_w, "LEGEND", [
            ("Heavy outline, tinted: sleeping room (each needs an escape opening, R319.1)", None),
            ("Tag: escape opening marked by the architect, with Gordium's result for it", None),
            ("Stair: treads from the nosings drawn; arrow UP or DN from this floor", None),
            ("Results: COMPLIES · DOES NOT COMPLY · NEEDS REVIEW · WAITING (word always printed)", None)])
        y = _legend_box(p, sx, y, side_w, "EXITS", [(f"{d['text']}: {result_words(d['status'])}", d["status"])
                                                    for d in lv["doors"]] or [("-", None)])
        notes = [(x["text"] if x.get("tag") else x["text"] + (f": {result_words(x['status'])}" if x["status"] else ""),
                  x["status"]) for x in lv["notes"]]
        if level and level["apart"]:
            notes.append(("Rooms are drawn apart: the drawing gives each room from its own corner, not its place in "
                          "the house. Each room is to scale; their positions are not.", None))
        notes.append(("Windows and doors have no position in the plan in the interior drawing: escape openings are "
                      "tagged inside their room, the exit door is named above.", None))
        if level is None or n == len(levels) - 1:
            for r in lv["undrawn"]:
                tags = "; ".join(plan_mod.tag_words(t) for t in r["tags"]) or "no escape opening marked"
                notes.append((f"{r['name']}: not drawn (no outline or floor level in the drawing): {tags}",
                              present.REVIEW if r["tags"] or r["sleeping"] else None))
        y = _legend_box(p, sx, y, side_w, "NOTES", notes)
        y = _route(p, sx, y, side_w, got, lv, level)
        pages.append(p)
    return pages


def _elev(inches: float) -> str:
    from .words import length
    return ("-" if inches < 0 else "") + length(abs(inches)) if inches else "0'-0\""


def _route(p, x, y, wd, got, lv, level):
    """The way out, as a schematic: each sleeping room on this floor → stair → exit door → outside. No rule checks
    it, so it has no result, and says so."""
    p.text(x, y, "WAY OUT (SCHEMATIC, NOT CHECKED BY GORDIUM)", size=7, bold=True)
    y += 12
    if level is None:
        return y
    rooms = [r["name"] for r in level["rooms"] if r["sleeping"]]
    steps = [", ".join(rooms) or "Rooms on this floor"]
    if level["stairs"]:
        steps.append(" / ".join(f"{s['name']} ({s['way']})" for s in level["stairs"]))
    elif any("Stairs: not read" in n["text"] for n in lv["notes"]):
        steps.append("stairs not read")
    steps.append(lv["doors"][0]["text"].split(" (")[0] if lv["doors"] else "exit door")
    steps.append("Outside")
    for i, s in enumerate(steps):
        ln = wrap(s, 6, wd - 10)[:2]
        h = 6 + 8 * len(ln)
        p.rect(x, y, wd, h, stroke=INK, lw=0.5)
        for j, t in enumerate(ln):
            p.text(x + 5, y + 9 + 8 * j, t, size=6)
        y += h
        if i < len(steps) - 1:
            p.line(x + 14, y, x + 14, y + 8, stroke=INK, lw=0.6)
            p.shape([(x + 11, y + 5), (x + 17, y + 5), (x + 14, y + 9)], stroke=None, fill=INK)
            y += 9
    return y + 6


def _grid(rooms, aspect: float, gap: float = 60.0) -> list:
    """Rooms that have no place in the house laid out in rows, the number of columns that best fills a drawing area
    of this width/height: [(room, dx, dy)], dy putting the first row at the top (the model's y runs up)."""
    best = None
    for cols in range(1, len(rooms) + 1):
        rows = [rooms[i:i + cols] for i in range(0, len(rooms), cols)]
        widths = [sum(r["poly"].bounds[2] - r["poly"].bounds[0] for r in row) + gap * (len(row) - 1) for row in rows]
        heights = [max(r["poly"].bounds[3] - r["poly"].bounds[1] for r in row) for row in rows]
        w, h = max(widths), sum(heights) + gap * (len(rows) - 1)
        fit = min(1 / w, 1 / (h * aspect))            # the larger, the bigger the plan can be drawn
        if best is None or fit > best[0] + 1e-12:
            best = (fit, rows, heights)
    _, rows, heights = best
    out, top = [], 0.0
    for row, h in zip(rows, heights):
        x = 0.0
        for r in row:
            minx, miny, maxx, maxy = r["poly"].bounds
            out.append((r, x - minx, -top - maxy))
            x += (maxx - minx) + gap
        top += h + gap
    return out


def _draw_level(p, level, x0, y0, x1, y1):
    rooms = level["rooms"]
    if level["apart"]:              # each room from its own corner: laid out in rows, each to scale
        placed = _grid(rooms, (x1 - x0) / (y1 - y0 - 20))
        stairs = []
    else:
        placed = [(r, 0.0, 0.0) for r in rooms]
        stairs = level["stairs"]
    xs, ys = [], []
    for r, dx, dy in placed:
        for px, py in r["poly"].exterior.coords:
            xs.append(px + dx)
            ys.append(py + dy)
    for s in stairs:
        for a, b in s["nosings"]:
            xs += [a[0], b[0]]
            ys += [a[1], b[1]]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span_x, span_y = max(maxx - minx, 1.0), max(maxy - miny, 1.0)       # inches
    room_w, room_h = (x1 - x0) / PT, (y1 - y0 - 20) / PT                 # paper inches
    scale, label = SCALES[-1]
    for s, lab in SCALES:
        if span_x / 12 * s <= room_w and span_y / 12 * s <= room_h:
            scale, label = s, lab
            break
    k = scale / 12 * PT                                                   # points per model inch
    left = x0 + ((x1 - x0) - span_x * k) / 2
    top = y0 + 10

    def at(px, py):                     # the model's y runs up (north), the paper's down
        return left + (px - minx) * k, top + (maxy - py) * k

    for r, dx, dy in placed:
        pts = [at(px + dx, py + dy) for px, py in r["poly"].exterior.coords[:-1]]
        p.shape(pts, stroke=INK, fill="#eef3fb" if r["sleeping"] else None, lw=1.6 if r["sleeping"] else 0.8)
        c = r["poly"].representative_point()
        cx, cy = at(c.x + dx, c.y + dy)
        p.text(cx, cy - 4, r["name"].upper(), size=7, bold=True, anchor="middle")
        if r["sleeping"]:
            p.text(cx, cy + 5, "SLEEPING ROOM", size=5.5, anchor="middle", fill=MUTED)
        ty = cy + 16
        for t in r["tags"]:
            words = plan_mod.tag_words(t, short=True)
            tw = width(words, 6, True) + 8
            _tag(p, cx - tw / 2, ty, words, t["status"])
            ty += 12
    for s in stairs:
        nos = s["nosings"]
        a0, b0 = nos[0]
        an, bn = nos[-1]
        p.shape([at(a0[0], a0[1]), at(b0[0], b0[1]), at(bn[0], bn[1]), at(an[0], an[1])], stroke=INK,
                fill="#ffffff", lw=0.9)
        for a, b in nos[1:-1]:
            p.line(*at(a[0], a[1]), *at(b[0], b[1]), stroke=INK, lw=0.4)
        m0 = at((a0[0] + b0[0]) / 2, (a0[1] + b0[1]) / 2)
        m1 = at((an[0] + bn[0]) / 2, (an[1] + bn[1]) / 2)
        start, end = (m0, m1) if s["way"] == "UP" else (m1, m0)
        p.line(*start, *end, stroke=INK, lw=0.8)
        ang = math.atan2(end[1] - start[1], end[0] - start[0])
        head = [end, (end[0] - 6 * math.cos(ang - 0.4), end[1] - 6 * math.sin(ang - 0.4)),
                (end[0] - 6 * math.cos(ang + 0.4), end[1] - 6 * math.sin(ang + 0.4))]
        p.shape(head, stroke=None, fill=INK)
        p.text(start[0], start[1] + 9, s["way"], size=6, bold=True, anchor="middle")
        words = f"{s['name']}: {result_words(s['status'])}"
        _tag(p, (m0[0] + m1[0]) / 2 - (width(words, 6, True) + 8) / 2, (m0[1] + m1[1]) / 2 - 8, words, s["status"])
    p.text(x0, y1 + 16, f"SCALE: {label}" + ("  (each room; positions not to scale)" if level["apart"] else ""),
           size=7, bold=True)
    # a north-less scale bar: 0, 4, 8 ft
    bx, by = x0 + 200, y1 + 13
    for i in range(2):
        p.rect(bx + i * 48 * k, by, 48 * k, 3, stroke=INK, fill=INK if i == 0 else "#ffffff", lw=0.5)
    for i, t in enumerate(("0", "4'", "8'")):
        p.text(bx + i * 48 * k, by + 11, t, size=5.5, anchor="middle")


# ---- the set ----------------------------------------------------------------------------------------------------------

def sheets(got: dict, project: dict) -> list[tuple[str, str, Page]]:
    """Every page of the set, numbered: G-001…, LS-101…, A-601…; each with its title block."""
    from .source import overall
    status, waiting = overall(got)
    headline = result_words(status, waiting)
    lines = [(f"Egress result: {headline}", status)] + [
        (f"{law['title']}: {law['summary']} (the check's own count)", None) for law in got["laws"]]
    # never a set that reads as complete: the sections Gordium doesn't check yet, said under the result
    for r in code_rows(got):
        if missing := not_checked_yet(r):
            lines.append((f"Not checked yet by Gordium: {len(missing)} code sections, check them by hand (code "
                          f"analysis line {r['Line']})", present.REVIEW if r["status"] != present.NOT_CHECKED
                          else None))
    groups = [("G", "Code analysis: egress", code_analysis(got, lines)),
              ("LS", "Life-safety plan", life_safety(got, lines)),
              ("A", "Escape-window schedule", schedule(got, lines))]
    start = {"G": 1, "LS": 101, "A": 601}
    out = []
    for prefix, title, pages in groups:
        for i, pg in enumerate(pages):
            out.append((f"{prefix}-{start[prefix] + i:03d}", title + (f" ({i + 1} of {len(pages)})" if len(pages) > 1
                                                                      else ""), pg))
    info = _info(got, project, headline)
    for n, (number, title, pg) in enumerate(out, 1):
        _frame(pg, info, number, title, n, len(out))
    return out
