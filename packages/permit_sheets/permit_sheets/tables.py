"""The two tables the sheets print, as rows of plain values with where each came from: the code analysis (G-001)
and the escape-window schedule (A-601). Plain code, no AI; display only (every result is the check's).
"""

import json
import re

from design_checker import egress, grouping, present

from . import words
from .words import NOT_MEASURED, result_words, worst

OPENING = "emergency_escape_opening"
NOT_READ = "escape openings not read"          # a room's line when the drawing's openings weren't read (never "none")
# the schedule's measured columns: the measure each shows, and its heading
COLUMNS = (("opening_net_clear_width", "Net clear width", "Width"), ("opening_net_clear_height", "Net clear height", "Height"),
           ("opening_net_clear_area", "Net clear area", "Area"), ("opening_sill_height", "Sill height", "Sill"))
GRADE = "opening_at_grade"
OPERATION = {"casement": "Casement", "side_hinged_door": "Side-hinged door", "double_hung": "Double-hung",
             "single_hung": "Single-hung", "horizontal_slider": "Horizontal slider", "sliding_door": "Sliding door",
             "fixed": "Fixed", "awning": "Awning", "hopper": "Hopper", "pivot": "Pivot", "tilt_turn": "Tilt-turn",
             "other": "Other"}

CODE_HEADERS = ["Line", "Item", "Requirement", "Required", "Proposed", "Result", "Code section", "Why / what to change",
                "Shown on G-001 as", "Rule id", "Item id", "Part kind", "Part id", "In part", "Measures (as checked)", "Citation",
                "Code's words", "Law", "Rulebook", "Rulebook sha256", "Rules fingerprint", "Code fingerprint",
                "Interior sha256"]
SCHEDULE_HEADERS = ["Mark", "Opening", "Room", "Type", "Net clear width", "Net clear height", "Net clear area",
                    "Sill height", "Grade floor", "Result", "Code sections", "Why", "Width result", "Height result",
                    "Area result", "Sill result", "Required width", "Required height", "Required area",
                    "Required sill", "Rows (rule id: result)", "Part id", "Room id", "Interior sha256"]


def _natural(text: str) -> list:
    """R319.2.2 before R319.10: numbers in a section compared as numbers."""
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"(\d+)", text)]


def _split(item: dict, rule: dict | None) -> tuple[str, str]:
    """(the part, the requirement): the item's name is "<part> · <rule title>" for a rule's row."""
    name = item.get("name") or ""
    title = rule.get("title") if rule and isinstance(rule.get("title"), str) else None
    if title and name.endswith(" · " + title):
        return name[: -len(" · " + title)], title
    return name, ""


def law_lines(law: dict) -> dict | None:
    """The law's results grouped as the panel groups them (design_checker/grouping.py): {tier: [line]}, or None for
    a law still waiting for rooms (printed as it always was, its waiting row and banner)."""
    if law["state"] == egress.WAITING:
        return None
    return grouping.lines([x["item"] for x in law["items"]])


def shown_as(got: dict) -> dict:
    """{item id: where G-001 shows it}: "<tier> › <line>" ("Needs review › Main stair: 16 need review: …"), so
    every rule's own row in the CSV leads to its line on the sheet and back."""
    out = {}
    for law in got["laws"]:
        lines = law_lines(law)
        if lines is None:
            out.update({x["item"]["id"]: "Waiting › " + (x["item"].get("name") or "") for x in law["items"]})
            continue
        named = {x["item"]["id"]: x["item"].get("name") or "" for x in law["items"]}
        for t, mine in lines.items():
            for ln in mine:
                if t == grouping.FAILS_T:        # G-001 prints each failing rule on its own row, under its name
                    out.update({i: f"{grouping.TITLES[t]} › {named.get(i, '')} (its own row)" for i in ln["items"]})
                    continue
                for c in ln.get("causes") or [{"words": ln["title"], "items": ln["items"]}]:
                    title = ln["title"] if not ln.get("causes") else \
                        ln["title"].split(": ")[0] + ": " + c["words"]
                    out.update({i: f"{grouping.TITLES[t]} › {title}" for i in c["items"]})
    return out


def code_rows(got: dict) -> list[dict]:
    """One row per egress item, every law in turn, in the check's order: the full per-rule table (the CSV and the
    XLSX), each row saying where G-001 shows it."""
    out = []
    shown = shown_as(got)
    for law in got["laws"]:
        for x in law["items"]:
            item, row, rule = x["item"], x["row"], x["rule"]
            where, requirement = _split(item, rule)
            required = proposed = ""
            if row is not None and rule is not None:
                required, proposed = words.required_and_proposed(rule, row.get("values") or {})
            why = "" if x["status"] == present.COMPLIES else (item.get("reason") or "")
            part = item.get("part") or {}
            within = part.get("within") or {}
            out.append({
                "Line": len(out) + 1, "Item": where, "Requirement": requirement,
                "Required": required, "Proposed": proposed, "Result": x["result"], "status": x["status"],
                "Code section": (item.get("code") or {}).get("section") or "", "Why / what to change": why,
                "Shown on G-001 as": shown.get(item.get("id"), ""),
                "Rule id": item.get("rule") or "", "Item id": item.get("id") or "", "Part kind": part.get("part") or "",
                "Part id": part.get("id") or "", "In part": within.get("id") or "" if isinstance(within, dict) else "",
                "Measures (as checked)": json.dumps(row.get("values"), sort_keys=True) if row else "",
                "Citation": (item.get("detail") or {}).get("citation") or "",
                "Code's words": (item.get("code") or {}).get("quote") or "",
                "Law": law["title"], "Rulebook": law["rulebook"], "Rulebook sha256": law["rulebook_sha256"],
                "Rules fingerprint": "; ".join(f"{k} {v}" for k, v in sorted(law["fingerprints"].items())),
                "Code fingerprint": got.get("worker_fingerprint") or "",
                "Interior sha256": got["interior_sha256"] or ""})
    return out


def _rows_for(got: dict, pid=None, within=None) -> list[dict]:
    """Every item (with its row) about one opening (by its id), or about a room's openings as a whole (id None,
    within the room)."""
    out = []
    for law in got["laws"]:
        for x in law["items"]:
            part = x["item"].get("part")
            if not part or part.get("part") != OPENING:
                continue
            w = (part.get("within") or {}).get("id") if isinstance(part.get("within"), dict) else None
            if pid is not None and part.get("id") == pid:
                out.append(x)
            elif pid is None and part.get("id") is None and w == within:
                out.append(x)
    return out


def _cell(xs: list[dict], m: str):
    """(value, required, status, rule ids) for one measured column: from the rows of the rules that compare this
    measure. No such row: the value isn't checked here, so NEEDS REVIEW."""
    mine = [x for x in xs if x["rule"] and m in words.compared(x["rule"].get("check"))]
    if not mine:
        return None, "", present.REVIEW, []
    unit = words.unit_of(OPENING, m)
    status = worst(x["status"] for x in mine)
    vals = [(x["row"].get("values") or {}).get(m) for x in mine]
    v = vals[0]
    req = []
    for x in mine:
        r, _ = words.required_and_proposed(x["rule"], x["row"].get("values") or {})
        req.append(r)
    # the value as the strictest of its rules would round it: a minimum rounds down, a maximum up
    signs = [op for x in mine for c in (words._comparisons(x["rule"]["check"]) or []) if c and c[0] == m
             for op in [c[1]]]
    direction = words.toward(signs[0], True) if signs and signs[0] not in ("yes", "no") else "nearest"
    return (words.value(v, unit, direction) if v is not None else NOT_MEASURED,
            "; ".join(dict.fromkeys(req)), status, [x["item"]["rule"] for x in mine])


def schedule_rows(got: dict) -> tuple[list[dict], list[str]]:
    """The escape-window schedule: each sleeping room's escape openings, a room with none marked, and each opening
    marked but not checked; and the notes the schedule must carry (what wasn't read)."""
    measured, interior = got["measured"], got["interior"] or {}
    notes, out = [], []
    if measured is None:            # no interior checked: one line saying so, never an empty schedule
        from .source import overall
        status, waiting = overall(got)
        why = "no escape openings to schedule yet" if waiting else \
            "no interior was checked: see the code analysis"
        return [statement(got, status, why, waiting)], []
    given = {o.get("id"): o for o in interior.get("openings") or [] if isinstance(o, dict)}
    parts = measured.get("parts") or {}
    rooms, openings = parts.get("sleeping_room"), parts.get(OPENING)
    if rooms is None:
        notes.append("sleeping rooms not read from the drawing: every escape-opening rule needs review")
    if openings is None:
        notes.append("escape openings not read from the drawing")
    openings_read = openings is not None
    rooms, openings = rooms or [], openings or []
    room_name = {r["id"]: r.get("name") or r["id"] for r in rooms}

    lines = {r["Item id"]: r["Line"] for r in code_rows(got)}

    def section(x):
        return (x["item"].get("code") or {}).get("section") or ""

    def line(o, room_id, xs):
        cells = {m: _cell(xs, m) for m, _, _ in COLUMNS}
        status = worst(x["status"] for x in xs)
        # grade floor as the check read it: the value a rule's row carries (the net clear area's limit depends on it)
        grade = next(((x["row"].get("values") or {})[GRADE] for x in xs
                      if x["row"] and GRADE in (x["row"].get("values") or {})), None)
        fails = [x["item"].get("reason") or x["item"].get("name") for x in xs if x["status"] == present.FAILS]
        review = [lines[x["item"]["id"]] for x in xs if x["status"] == present.REVIEW]
        why = list(dict.fromkeys(fails))
        if review:
            why.append(f"{len(review)} rule{'s' if len(review) != 1 else ''} need{'s' if len(review) == 1 else ''} "
                       f"review: code analysis lines {', '.join(str(n) for n in review)}")
        if not o and not openings_read:
            why.append("escape openings not read from the drawing")
        elif not xs:
            why.append("the check gave no row for this opening")
        shown = [x for m, _, _ in COLUMNS for x in xs if x["item"].get("rule") in cells[m][3]]
        src = given.get(o["id"]) if o else None
        return {
            "Mark": (str(o["id"]).upper() if o else "-"), "Opening": (o.get("name") or o["id"]) if o else
            "none marked" if openings_read else NOT_READ,
            "Room": room_name.get(room_id, room_id or ""), "Type": OPERATION.get((src or {}).get("operation"),
                                                                                 (src or {}).get("operation") or ""),
            **{h: cells[m][0] for m, h, _ in COLUMNS},
            "Grade floor": words.value(grade, "yes_no") if o else "",
            "Result": result_words(status), "status": status,
            "Code sections": ", ".join(sorted({section(x) for x in shown + [x for x in xs
                                                                          if x["status"] == present.FAILS]
                                               if section(x)}, key=_natural)),
            "Why": "; ".join(why),
            **{f"{s} result": result_words(cells[m][2]) for m, _, s in COLUMNS},
            **{f"Required {s.lower()}": cells[m][1] for m, _, s in COLUMNS},
            "Rows (rule id: result)": "; ".join(f"{x['item']['rule']}: {x['result']}" for x in xs),
            "Part id": o["id"] if o else "", "Room id": room_id or "", "Interior sha256": got["interior_sha256"] or "",
            "cell_status": {h: cells[m][2] for m, h, _ in COLUMNS}}

    for room in rooms:
        mine = [o for o in openings if o.get("within") == room["id"]]
        for o in mine:
            out.append(line(o, room["id"], _rows_for(got, pid=o["id"])))
        if not mine:
            out.append(line(None, room["id"], _rows_for(got, within=room["id"])))
    placed = {o.get("id") for r in rooms for o in openings if o.get("within") == r["id"]}
    for o in openings:                      # an opening within something other than a sleeping room the check read
        if o.get("id") not in placed:
            out.append(line(o, o.get("within"), _rows_for(got, pid=o["id"])))
    skipped = [x for law in got["laws"] for x in law["items"] if ".skipped#" in (x["item"].get("id") or "")]
    for n, s in enumerate(measured.get("not_checked") or []):
        why = skipped[n]["item"].get("reason") if n < len(skipped) else f"marked as an escape opening but not checked: {s.get('why')}"
        src = given.get(s.get("id")) or {}
        out.append({**{h: "" for h in SCHEDULE_HEADERS},
                    "Mark": str(s.get("id") or "").upper(), "Opening": s.get("name") or s.get("id") or "",
                    "Room": next((r.get("name") or r.get("id") for r in interior.get("rooms") or []
                                  if isinstance(r, dict) and r.get("id") == src.get("room")), src.get("room") or ""),
                    "Type": OPERATION.get(src.get("operation"), src.get("operation") or ""),
                    **{h: "not checked" for _, h, _ in COLUMNS}, "Grade floor": "",
                    "Result": result_words(present.REVIEW), "status": present.REVIEW, "Why": why,
                    **{f"{s} result": result_words(present.REVIEW) for _, _, s in COLUMNS},
                    "Part id": s.get("id") or "", "Room id": src.get("room") or "",
                    "Interior sha256": got["interior_sha256"] or "",
                    "cell_status": {h: present.REVIEW for _, h, _ in COLUMNS}})
    out = [statement(got, present.REVIEW, n) for n in notes] + out
    if not out:
        out.append(statement(got, present.REVIEW, "no sleeping room and no escape opening in the drawing"))
    return out, notes


def statement(got: dict, status: str, why: str, waiting: str | None = None) -> dict:
    """A schedule line that is no opening's: what wasn't read, or why there is nothing to schedule, with its result
    (never complies), so the schedule is never an empty table."""
    words = result_words(status, waiting)
    return {**{h: "" for h in SCHEDULE_HEADERS}, "Mark": "-", "Result": words, "status": status, "Why": why,
            **{f"{s} result": words for _, _, s in COLUMNS}, "Interior sha256": got["interior_sha256"] or "",
            "cell_status": {h: status for _, h, _ in COLUMNS}, "statement": True}


def plain_rows(rows: list[dict], headers: list[str]) -> list[list]:
    """The rows as the CSV and XLSX carry them: the headers' values, in order."""
    return [[r.get(h, "") for h in headers] for r in rows]

