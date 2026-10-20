"""The rules workbook: every rule, definition, use name, open question and section label of one
jurisdiction, as a spreadsheet people can read and check, each row with the city's exact words and a link
to the city's page.

Plain code, no AI. The workbook is generated from the rule files and never edited by hand; `--check`
(see __main__) confirms the committed copy says the same as a fresh build.

The tables are built as plain rows first (`tables(j)`), so tests check the content without Excel; `build()`
only lays them out. Which fields of each format are shown, and which are deliberately left out, is declared
in SHOWN and HIDDEN, and a test holds them to the formats' own field lists.
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font

from rule_format.labels import LABEL_FIELDS, load_pieces, revision_steps
from rule_format.rulebook import APPROVAL_FIELDS, REPO, RULE_FIELDS, TERM_SCHEMAS, load, rulebook_paths

FONT = "Arial"                                   # like the architects' spreadsheet: 16 title, 12 headers, 11 body
REPO_BLOB = "https://github.com/bz28/gordium/blob/main"

# Every field of every format is either shown in the workbook or left out on purpose, with the reason.
SHOWN = {
    "rule": {"id", "kind", "topic", "title", "applies_when", "check", "review_when", "sources", "examples",
             "notes", "open_questions", "answers", "drafted_by", "status"},
    "definitions": {"term", "measures", "sources", "open_questions", "answers", "notes", "drafted_by", "status"},
    "uses": {"name", "sources", "notes", "drafted_by", "status"},
    "label": {"label", "topic", "reason", "sources", "notes", "open_questions", "answers", "revised", "drafted_by",
              "status"},
}
HIDDEN = {
    "approved_by": "human approval is deferred; no one approves yet",
    "approved_on": "human approval is deferred",
    "approved_hash": "a fingerprint for code, not for reading",
    "piece_sha256": "a fingerprint for code, not for reading",
    "run": "the file of recorded AI calls; for auditing, not reading",
}
FIELDS = {"rule": RULE_FIELDS, "definitions": TERM_SCHEMAS["definitions"]["fields"] | APPROVAL_FIELDS,
          "uses": TERM_SCHEMAS["uses"]["fields"] | APPROVAL_FIELDS, "label": LABEL_FIELDS | APPROVAL_FIELDS}


# ---- links ---------------------------------------------------------------------------------------------

def pdf_url(j: Path, documents: dict[str, dict], file: str) -> str:
    """Where a reader can open this exact document. The city's own URL when it serves the PDF itself (a
    .pdf address, or a city DocumentCenter file); otherwise the fingerprinted copy in this repository
    (Chapter 325's official page is HTML, where our page numbers mean nothing). The repository is private,
    so its links work only for people with access."""
    url = (documents.get(file) or {}).get("url", "")
    if url.lower().endswith(".pdf") or "/DocumentCenter/View/" in url:
        return url
    return f"{REPO_BLOB}/{(j / '1_source_documents' / file).relative_to(REPO).as_posix()}"


def page_link(j: Path, documents: dict[str, dict], file: str, page) -> str:
    """A link that opens the PDF at the page (browsers' PDF viewers honor #page=N; GitHub's viewer may not)."""
    return f"{pdf_url(j, documents, file)}#page={page}" if isinstance(page, int) else pdf_url(j, documents, file)


# ---- cell text -----------------------------------------------------------------------------------------

def _lines(source: dict) -> str:
    lines = source.get("lines") or []
    return f"{lines[0]}–{lines[1]}" if len(lines) == 2 and lines[0] != lines[1] else str(lines[0]) if lines else ""


def _bullets(items) -> str:
    return "\n".join(f"• {' '.join(str(i).split())}" for i in items or [])


def _answers(answers) -> str:
    return _bullets(f"{a.get('question')} → {a.get('answer')} ({a.get('answered_by')}, {a.get('answered_on')})"
                    for a in answers or [])


def _examples(examples) -> str:
    return _bullets(f"{', '.join(f'{k} = {v}' for k, v in (e.get('given') or {}).items())} → {e.get('expect')}"
                    + (f" ({e['note']})" if e.get("note") else "") for e in examples or [])


def _revisions(revised, label) -> str:
    """Each change after the AI's answer, as it happened: from → to, who, when, why (a chain reads in order)."""
    return _bullets((f"{r['from']} → {to}" if "from" in r else "sources changed")
                    + f" ({r.get('by')}, {r.get('date')}): {r.get('why')}" for r, to in revision_steps(revised or [], label))


# ---- the tables ----------------------------------------------------------------------------------------

def rulebooks(j: Path) -> list[tuple[str, dict]]:
    """(path within 5_zoning_rules, rulebook) for every rulebook there: the validator's own list of files."""
    folder = j / "5_zoning_rules"
    return [(p.relative_to(folder).as_posix(), load(p) or {}) for p in rulebook_paths(folder)]


def _source_rows(entry: dict, link) -> list[tuple[int, dict, str | None]]:
    sources = entry.get("sources") or [{}]
    return [(n, s, link(s) if s.get("file") else None) for n, s in enumerate(sources)]


def tables(j: Path) -> dict[str, dict]:
    """{tab: {"title", "columns": [(header, width)], "rows": [[cell, ...]], "links": {header: [url per row]}}}.
    A link cell holds its display text; its URL is in "links"."""
    documents = {d["file"]: d for d in load(j / "1_source_documents/sources.yaml")["documents"]}
    link = lambda s: page_link(j, documents, s.get("file", ""), s.get("page"))
    shown = lambda s: f"Open p.{s.get('page')}" if s.get("file") else ""
    out = {}

    # Rules: one row per source, so each quote sits next to its page and link. Rows that identify the rule
    # (zone, rulebook, id, title, status, who drafted it) repeat on every row, so sorting and filtering keep
    # a rule together; the long fields are on the rule's first row only.
    rows, links = [], []
    for book_path, book in rulebooks(j):
        for rule in book.get("rules") or []:
            for n, s, url in _source_rows(rule, link):
                first, total = n == 0, len(rule.get("sources") or [{}])
                rows.append([
                    book.get("district", ""), book_path, rule.get("id", ""), rule.get("title", ""),
                    rule.get("status", ""), rule.get("drafted_by", ""),
                    rule.get("kind", "") if first else "", rule.get("topic", "") if first else "",
                    rule.get("check", "") if first else "", rule.get("applies_when", "") if first else "",
                    _bullets(f"{r.get('when')}: {r.get('reason')}" for r in rule.get("review_when") or []) if first else "",
                    _examples(rule.get("examples")) if first else "",
                    f"{n + 1} of {total}", s.get("file", ""), s.get("page", ""), _lines(s), s.get("quote", ""), shown(s),
                    _bullets(rule.get("open_questions")) if first else "", _answers(rule.get("answers")) if first else "",
                    " ".join(str(rule.get("notes", "")).split()) if first else ""])
                links.append(url)
    out["Rules"] = {"title": "GORDIUM | Zoning rules (drafts, checked by code)", "rows": rows, "links": {"Link": links},
                    "columns": [("Zone", 9), ("Rulebook", 18), ("Rule id", 28), ("Title", 34), ("Status", 8),
                                ("Drafted by", 18), ("Kind", 7), ("Topic", 14), ("Check (formula)", 40),
                                ("Applies when", 26), ("Needs review when", 34), ("Worked examples", 40), ("Source", 8),
                                ("Document", 26), ("Page", 6), ("Lines", 7), ("City's exact words", 60), ("Link", 10),
                                ("Open questions", 50), ("Answers", 40), ("Notes", 40)]}

    # Definitions and use names: one row per source, like rules.
    terms = {schema: load(j / f"4_term_definitions/{schema}.yaml") or {} for schema in TERM_SCHEMAS
             if (j / f"4_term_definitions/{schema}.yaml").exists()}
    rows, links = [], []
    for key, d in terms.get("definitions", {}).items():
        for n, s, url in _source_rows(d, link):
            first = n == 0
            rows.append([key, d.get("term", ""), d.get("status", ""), d.get("drafted_by", ""),
                         ", ".join(d.get("measures") or []) if first else "",
                         f"{n + 1} of {len(d.get('sources') or [{}])}", s.get("file", ""), s.get("page", ""), _lines(s),
                         s.get("quote", ""), shown(s), _bullets(d.get("open_questions")) if first else "",
                         _answers(d.get("answers")) if first else "", " ".join(str(d.get("notes", "")).split()) if first else ""])
            links.append(url)
    out["Definitions"] = {"title": "GORDIUM | Definitions (the city's own words)", "rows": rows, "links": {"Link": links},
                          "columns": [("Id", 24), ("Term", 26), ("Status", 8), ("Drafted by", 14), ("Measures", 22),
                                      ("Source", 8), ("Document", 26), ("Page", 6), ("Lines", 7), ("City's exact words", 70),
                                      ("Link", 10), ("Open questions", 50), ("Answers", 40), ("Notes", 40)]}
    rows, links = [], []
    for key, u in terms.get("uses", {}).items():
        for n, s, url in _source_rows(u, link):
            rows.append([key, u.get("name", ""), u.get("status", ""), u.get("drafted_by", ""),
                         f"{n + 1} of {len(u.get('sources') or [{}])}", s.get("file", ""), s.get("page", ""), _lines(s),
                         s.get("quote", ""), shown(s), " ".join(str(u.get("notes", "")).split()) if n == 0 else ""])
            links.append(url)
    out["Uses"] = {"title": "GORDIUM | Use names (the only values a rule's `use` may take)", "rows": rows,
                   "links": {"Link": links},
                   "columns": [("Id", 30), ("Name", 40), ("Status", 8), ("Drafted by", 14), ("Source", 8),
                               ("Document", 26), ("Page", 6), ("Lines", 7), ("City's exact words", 50), ("Link", 10),
                               ("Notes", 40)]}

    # Section labels, for the Questions and Coverage tabs.
    labels_by_doc = {}
    for path in sorted((j / "3_section_labels").glob("*.yaml")):
        book = load(path)
        if isinstance(book, dict) and "labels" in book:
            labels_by_doc[book["document"]] = book["labels"]

    # Questions: every open question anywhere, one row each, with where it was asked.
    rows, links = [], []
    def ask(kind, where, ident, questions, sources):
        s = (sources or [{}])[0]
        for q in questions or []:
            rows.append([kind, where, ident, " ".join(str(q).split()), s.get("file", ""), s.get("page", ""), shown(s)])
            links.append(link(s) if s.get("file") else None)
    for book_path, book in rulebooks(j):
        for rule in book.get("rules") or []:
            ask("Rule", f"5_zoning_rules/{book_path}", rule.get("id", ""), rule.get("open_questions"), rule.get("sources"))
    for schema, entries in terms.items():
        for key, d in entries.items():
            ask(schema.rstrip("s").capitalize(), f"4_term_definitions/{schema}.yaml", key, d.get("open_questions"),
                d.get("sources"))
    for document, labels in labels_by_doc.items():
        for pid, e in labels.items():
            ask("Section label", document, pid, e.get("open_questions"), e.get("sources"))
    out["Questions"] = {"title": "GORDIUM | Open questions", "rows": rows, "links": {"Link": links},
                        "columns": [("About", 14), ("In", 34), ("Id", 30), ("Question", 90), ("Document", 26),
                                    ("Page", 6), ("Link", 10)]}

    # Coverage: every piece of every cut document, in the law's order, with its label.
    rows, links = [], []
    for sections in sorted((j / "2_extracted_text").glob("*.sections.jsonl")):
        header, pieces = load_pieces(sections)
        labels = labels_by_doc.get(header["file"], {})
        for pid, piece in pieces.items():
            e = labels.get(pid, {})
            pages = sorted({p for p, _, _ in piece["lines"]})
            first_page = piece["lines"][0][0]
            rows.append([header["file"], pid, piece["title"], str(pages[0]) if len(pages) == 1 else f"{pages[0]}–{pages[-1]}",
                         e.get("label", "unlabeled"), e.get("topic", ""), " ".join(str(e.get("reason", "")).split()),
                         _bullets(s.get("quote") for s in e.get("sources") or []), f"Open p.{first_page}",
                         e.get("status", ""), e.get("drafted_by", ""), _revisions(e.get("revised"), e.get("label")),
                         _bullets(e.get("open_questions")), _answers(e.get("answers")),
                         " ".join(str(e.get("notes", "")).split())])
            links.append(page_link(j, documents, header["file"], first_page))
    out["Coverage"] = {"title": "GORDIUM | Every part of the law, and what it is", "rows": rows, "links": {"Link": links},
                       "columns": [("Document", 26), ("Piece", 22), ("Title", 40), ("Pages", 8), ("Label", 16),
                                   ("Topic", 14), ("Reason", 60), ("Quote(s)", 60), ("Link", 10), ("Status", 8),
                                   ("Drafted by", 22), ("Changed after the AI", 60), ("Open questions", 50),
                                   ("Answers", 40), ("Notes", 40)]}

    # Sources: the documents themselves.
    rows, links = [], []
    for d in documents.values():
        rows.append([d.get("file", ""), d.get("title", ""), d.get("publisher", ""), d.get("url", ""),
                     str(d.get("downloaded_on", "")), d.get("pages", ""), d.get("sha256", ""),
                     "no" if d.get("quotable") is False else "yes", " ".join(str(d.get("not_quotable_because", "")).split())])
        links.append(d.get("url") or None)
    out["Sources"] = {"title": "GORDIUM | Source documents (fingerprinted)", "rows": rows, "links": {"Official URL": links},
                      "columns": [("File", 34), ("Title", 44), ("Publisher", 22), ("Official URL", 50),
                                  ("Downloaded", 12), ("Pages", 7), ("Fingerprint (SHA-256)", 30), ("Quotable", 9),
                                  ("Why not quotable", 50)]}
    return out


# ---- layout --------------------------------------------------------------------------------------------

def _cell_text(value):
    """Text is stored as text, never a formula (a quote or an AI-written note starting with '=' must not run),
    and characters Excel can't hold are shown as '�' rather than crashing the export."""
    return ILLEGAL_CHARACTERS_RE.sub("�", value) if isinstance(value, str) else value


def build(data: dict[str, dict]) -> Workbook:
    """Lay the tables out like the architects' sheet: a bold title in row 1, headers in row 2 (frozen),
    Arial, wrapped text, links as clickable cells."""
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "Gordium (generated: python -m rule_export)"
    for name, t in data.items():
        ws = wb.create_sheet(name)
        ws["A1"] = t["title"]
        ws["A1"].font = Font(name=FONT, size=16, bold=True)
        headers = [h for h, _ in t["columns"]]
        for c, (header, width) in enumerate(t["columns"], 1):
            cell = ws.cell(row=2, column=c, value=header)
            cell.font = Font(name=FONT, size=12, bold=True)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws.column_dimensions[cell.column_letter].width = width
        for r, row in enumerate(t["rows"], 3):
            for c, value in enumerate(row, 1):
                cell = ws.cell(row=r, column=c, value=_cell_text(value))
                if isinstance(value, str):
                    cell.data_type = "s"
                cell.font = Font(name=FONT, size=11)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        for header, urls in t["links"].items():           # links name their column by its header
            c = headers.index(header) + 1
            for r, url in enumerate(urls, 3):
                if url:
                    cell = ws.cell(row=r, column=c)
                    cell.hyperlink = url
                    cell.font = Font(name=FONT, size=11, color="0563C1", underline="single")
        ws.freeze_panes = "A3"
    return wb


def contents(wb) -> list:
    """What a workbook says (sheet names, cell values, links), for comparing a fresh build with a saved file.
    Content, not bytes: Excel files carry a save timestamp."""
    value = lambda v: None if v == "" else v                  # a saved empty cell reads back as None
    return [(ws.title, [[(value(c.value), c.hyperlink.target if c.hyperlink else None) for c in row]
                        for row in ws.iter_rows()]) for ws in wb.worksheets]


def output_path(j: Path) -> Path:
    return j / f"{j.name}_rules.xlsx"
