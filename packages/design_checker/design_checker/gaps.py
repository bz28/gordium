"""What a zone's rulebook doesn't check, so a missing rule is never silently absent (a list of items that comply
must never read as a full check).

Two kinds, each shown as a "not checked" item (the panel's "Not covered by this rulebook" group, out of the counts):
- a chart row: every cell of the zone's own chart column that states something (anything but "-" or empty) that
  no rule of the zone cites, by its cell or its lines (minimum lot width when it wasn't drafted, loading);
- for a zone with only AI-drafted rules: what the drafting log sends to a person for it or couldn't draft at all
  (a law piece whose answer was cut off, a rule for this district a template couldn't fill).
Plain code, no AI: read from the chart reader's cells and the drafting log."""

import re
from pathlib import Path

from rule_format.rulebook import district_name, is_ai_drafted, load, read_jsonl

EMPTY = {"", "-", "–", "—"}


def _cells(j: Path) -> list[dict]:
    out = []
    for f in sorted((j / "2_extracted_text").glob("*.cells.jsonl")):
        rows = read_jsonl(f)
        name = rows[0].get("file") if rows else None
        out += [dict(r, file=name) for r in rows[1:] if "column" in r and "value" in r and not r.get("heading")]
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s*\[fn[\d,]+\]", "", " ".join(str(text).split())).strip()


def _cites(source: dict, cell: dict) -> bool:
    if source.get("file") != cell["file"] or source.get("page") != cell["page"]:
        return False
    want = source.get("cell")
    if isinstance(want, dict):
        return (district_name(str(want.get("column", ""))) == district_name(cell["column"])
                and _clean(want.get("section", "")) == _clean(cell.get("section", ""))
                and _clean(want.get("row", "")) == _clean(cell["row"]))
    lines = source.get("lines") or []
    return len(lines) == 2 and any(lines[0] <= n <= lines[1] for n in cell.get("row_lines") or [])


def law_rule_ids(j: Path, zone: str) -> set[str]:
    """For an AI-drafted zone, the rules drafted from a piece of the law, not from the chart (the drafting log): they
    cite chart cells as inputs (the height bonus cites the side-yard minimums it enlarges), so citing a cell doesn't
    mean they check it."""
    log_file = j / "5_zoning_rules/drafted/records/drafting_log.yaml"
    if not (is_ai_drafted(j, zone) and log_file.is_file()):
        return set()
    units = (load(log_file) or {}).get("units") or {}
    return {rid for unit, e in units.items() if not unit.startswith("chart-") for rid in e.get("rules") or []}


def chart_gaps(j: Path, zone: str, rules: list[dict]) -> list[dict]:
    """One entry per chart row of the zone's column that states something no rule checks: every cell ends as a rule
    citing it, or a visible not-checked item, never silent. In an AI-drafted zone only a rule drafted from the chart
    counts; a law piece's rule citing the cell as an input doesn't (R-2c's side yards, which no chart rule checks,
    stay listed whatever §325-16C's height bonus cites)."""
    inputs_only = law_rule_ids(j, zone)
    sources = [s for r in rules if r.get("id") not in inputs_only for s in r.get("sources") or [] if isinstance(s, dict)]
    out, seen = [], set()
    for c in _cells(j):
        if district_name(c["column"]) != zone or str(c.get("value") or "").strip() in EMPTY:
            continue
        key = (c["page"], _clean(c.get("section", "")), _clean(c["row"]))
        if key in seen or any(_cites(s, c) for s in sources):
            continue
        seen.add(key)
        slug = re.sub(r"[^a-z0-9]+", "_", f"{key[1]} {key[2]}".lower()).strip("_")
        out.append({"id": f"chart.p{c['page']}.{slug}", "row": key, "section": f"Chart p.{c['page']}",
                    "name": f"{key[1]}: {key[2]} ({_clean(c['value'])})",
                    "why": f"No rule checks this chart row for {zone} yet: check by hand"})
    return out


def chart_section(unit: str) -> str:
    """A chart drafting unit's id as an architect looks it up, the form chart_gaps uses: "chart-p3-yard_dimensions"
    -> "Chart p.3: Yard dimensions" (#21 review round 13: the raw id went into "Check this by hand for now: …")."""
    m = re.match(r"chart-p(\d+)-(.+)$", unit)
    return f"Chart p.{m.group(1)}: {m.group(2).replace('_', ' ').capitalize()}" if m else unit


LEFT_OUT = re.compile(r"^it points to (\S+), which was left out of the drafter's input for length")


def drafting_gaps(j: Path, zone: str, rules: list[dict] | None = None) -> list[dict]:
    """For an AI-drafted zone: one item per drafting unit that leaves something for a person here, so the list stays
    readable (it grew to 134 near-identical lines) and nothing drops out. In each: the unit couldn't be drafted
    (failed, or no rule with a reason); and the drafting log's entries for a person about this zone (its district,
    every district, or the unit as a whole), with the sections left out of the drafter's input for length named once.
    A law piece that names its own districts (the log's scope) lists nothing outside them. A chart unit's entry about
    a cell that a rule of the same unit cites is a template that didn't fit where a sibling did: left out. A law
    piece's entry about a cited cell is kept (§325-19E's 75% of the coverage the chart rule checks is its own
    requirement). An entry about cells no rule cites is chart_gaps' item."""
    log_file = j / "5_zoning_rules/drafted/records/drafting_log.yaml"
    if not (is_ai_drafted(j, zone) and log_file.is_file()):
        return []
    units = (load(log_file) or {}).get("units") or {}
    sources = [(r["id"], s) for r in rules or [] for s in r.get("sources") or [] if isinstance(s, dict) and "cell" in s]

    def cited(cell, by=None):
        c = {"file": "zoning_charts_2026-04.pdf", "page": cell[0], "section": cell[1], "row": cell[2], "column": cell[3],
             "row_lines": []}
        return any(_cites(s, c) for rid, s in sources if by is None or rid in by)
    out = []
    for unit, e in units.items():
        if e.get("scope") and zone not in e["scope"]:
            continue                                    # the law piece doesn't reach this district
        chart = unit.startswith("chart-")
        lines, left_out, seen = [], [], set()
        if not chart and e.get("failed"):
            lines.append(f"The AI draft failed ({e['failed']}): check by hand.")
        elif not chart and not e.get("rules") and e.get("reason"):
            lines.append("No rule drafted: " + " ".join(str(e["reason"]).split()) + " Check by hand.")
        for x in e.get("unresolved") or []:
            rule, why = str(x.get("rule", "")), " ".join(str(x.get("why", "")).split())
            if not (rule.split(".")[0] in (zone, "general") or rule == unit or rule.startswith(f"{unit}.")):
                continue
            if why.startswith("chart page"):
                continue                                # an uncited cell: chart_gaps lists it while it is uncited
            cells = [c for c in x.get("cells") or [] if district_name(str(c[3])) == zone]
            if cells and not any(cited(c) for c in cells):
                continue                                # every cell uncited: chart_gaps lists them
            if cells and chart and any(cited(c, set(e.get("rules") or [])) for c in cells):
                continue                                # a sibling template of the same chart unit checks the cell
            if m := LEFT_OUT.match(why):
                left_out.append(m.group(1))
                continue
            if (rule, why) not in seen:
                seen.add((rule, why))
                lines.append(f"{rule}: {why}")
        # the name says, in an architect's words, what is counted: "97 linked sections the AI drafter didn't read (too
        # long): check by hand", "2 notes to check by hand", or both
        n = len(set(left_out))
        parts = [f"{n} linked section{'s' if n != 1 else ''} the AI drafter didn't read (too long)"] if n else []
        parts += [f"{len(lines)} note{'s' if len(lines) != 1 else ''}"] if lines else []
        if n:
            lines.append(f"It links to {n} section{'s' if n != 1 else ''} the AI drafter didn't read because they were "
                         f"too long; check them by hand: {', '.join(sorted(set(left_out)))}.")
        if lines:
            out.append({"id": f"drafting.{unit}", "section": chart_section(unit) if chart else f"§{unit}",
                        "name": " and ".join(parts) + (": check by hand" if n else " to check by hand"),
                        "why": " · ".join(lines)})
    return out


def zone_gaps(j: Path, zone: str, rules: list[dict]) -> list[dict]:
    return chart_gaps(j, zone, rules) + drafting_gaps(j, zone, rules)
