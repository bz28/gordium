"""The files an architect attaches: one SVG per sheet, all sheets in one PDF, and the two tables as CSV and XLSX.

    out = files(got, project)        # {file name: bytes}, the same bytes for the same check (no clock)
    wb = workbook(got, project)      # the two tables as one Excel workbook (compared by content: Excel stamps a time)
"""

import csv
import io
import re

from openpyxl import Workbook

from rule_export.workbook import title as sheet_title, write_block

from . import sheets as sheets_mod
from .draw import pdf, svg
from .tables import CODE_HEADERS, SCHEDULE_HEADERS, code_rows, plain_rows, schedule_rows

PROJECT_KEYS = {"title", "address", "date"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def project_problems(project) -> list[str]:
    """What's wrong with a project file: it gives the title block's project name, address (optional) and date."""
    if not isinstance(project, dict):
        return ["the project file must be a mapping with title, address and date"]
    out = [f"unknown key {k!r} (allowed: {', '.join(sorted(PROJECT_KEYS))})" for k in project if k not in PROJECT_KEYS]
    if not isinstance(project.get("title"), str) or not project["title"].strip():
        out.append("title: the project's name, as text")
    if not isinstance(project.get("date"), str) or not DATE.match(project["date"]):
        out.append("date: the sheets' date, YYYY-MM-DD (the sheets never read the clock)")
    if "address" in project and not isinstance(project["address"], str):
        out.append("address: text")
    return out


def _csv(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def files(got: dict, project: dict) -> dict[str, bytes]:
    pages = sheets_mod.sheets(got, project)
    name = f"{project['title']}: egress permit sheets"
    out = {f"{number}.svg": svg(page, f"{number} {title} · {project['title']}").encode("utf-8")
           for number, title, page in pages}
    out["permit_sheets.pdf"] = pdf([page for _, _, page in pages], name)
    out["code_analysis.csv"] = _csv(CODE_HEADERS, plain_rows(code_rows(got), CODE_HEADERS))
    out["escape_window_schedule.csv"] = _csv(SCHEDULE_HEADERS, plain_rows(schedule_rows(got)[0], SCHEDULE_HEADERS))
    return out


def workbook(got: dict, project: dict) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "Gordium (generated: python -m permit_sheets)"
    for tab, heading, headers, rows in (
            ("Code analysis", "G-001 Code analysis: egress", CODE_HEADERS, plain_rows(code_rows(got), CODE_HEADERS)),
            ("Escape-window schedule", "A-601 Escape-window schedule", SCHEDULE_HEADERS,
             plain_rows(schedule_rows(got)[0], SCHEDULE_HEADERS))):
        ws = wb.create_sheet(tab)
        sheet_title(ws, f"{heading} · {project['title']} · {project['date']} · {sheets_mod.DISCLAIMER}")
        write_block(ws, 2, [(h, 18) for h in headers], rows)
        ws.freeze_panes = "A3"
    return wb
