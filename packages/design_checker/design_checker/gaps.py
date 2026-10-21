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


def chart_gaps(j: Path, zone: str, rules: list[dict]) -> list[dict]:
    """One entry per chart row of the zone's column that states something no rule cites."""
    sources = [s for r in rules for s in r.get("sources") or [] if isinstance(s, dict)]
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


def drafting_gaps(j: Path, zone: str) -> list[dict]:
    """For an AI-drafted zone: the law pieces the drafting run couldn't draft (failed, or no rule with a reason), and
    the drafting log's entries for a person about this district that aren't a chart cell (those are chart_gaps)."""
    log_file = j / "5_zoning_rules/drafted/records/drafting_log.yaml"
    if not (is_ai_drafted(j, zone) and log_file.is_file()):
        return []
    units = (load(log_file) or {}).get("units") or {}
    out = []
    for unit, e in units.items():
        if unit.startswith("chart-"):
            continue                                    # chart rows: chart_gaps, from the cells themselves
        if e.get("failed"):
            out.append({"id": f"drafting.{unit}", "section": f"§{unit}", "name": "not drafted",
                        "why": f"The AI draft failed ({e['failed']}): check by hand"})
        elif not e.get("rules") and e.get("reason"):
            out.append({"id": f"drafting.{unit}", "section": f"§{unit}", "name": "no rule drafted",
                        "why": " ".join(str(e["reason"]).split()) + " Check by hand."})
        for n, x in enumerate(e.get("unresolved") or []):
            if str(x.get("rule", "")).startswith(f"{zone}.") and "cells" not in x \
                    and not str(x.get("why", "")).startswith("chart page"):
                out.append({"id": f"drafting.{unit}.{n}", "section": f"§{unit}", "name": x["rule"],
                            "why": " ".join(str(x.get("why", "")).split())})
    return out


def zone_gaps(j: Path, zone: str, rules: list[dict]) -> list[dict]:
    return chart_gaps(j, zone, rules) + drafting_gaps(j, zone)
