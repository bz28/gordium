"""The rules workbook: every rule, definition, use name, open question and section label of one
jurisdiction, as a spreadsheet people can read and check, each row with the city's exact words and a link
to the city's page.

Plain code, no AI. The workbook is generated from the rule files and never edited by hand; `--check`
(see __main__) confirms the committed copy says the same as a fresh build.

The tables are built as plain rows first (`tables(j)`), so tests check the content without Excel; `build()`
only lays them out. Each tab's columns are declared once (Col): header, width, the format fields it shows
and how to fill it. The fields shown plus the ones in HIDDEN (left out on purpose) are held by a test to the
formats' own field lists, and each column is tested to show its field, so nothing goes missing silently.
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill

from document_extraction.sections import piece_text
from rule_format.labels import LABEL_FIELDS, load_pieces, revision_steps
from rule_format.rulebook import (APPROVAL_FIELDS, REPO, RULE_FIELDS, SOURCE_FIELDS, TERM_SCHEMAS, Context, _cell, load,
                                  read_jsonl, rulebook_paths)
from section_labeling.term_index import INDEX_NAME, related

FONT = "Arial"                                   # like the architects' spreadsheet: 16 title, 12 headers, 11 body
INK = "243746"                                   # their text color, on every cell they wrote
REPO_BLOB = "https://github.com/bz28/gordium/blob/main"

# Fields left out of the workbook on purpose, with the reason. Every other field is shown by a column.
HIDDEN = {
    "approved_by": "human approval is deferred; no one approves yet",
    "approved_on": "human approval is deferred",
    "approved_hash": "a fingerprint for code, not for reading",
    "piece_sha256": "a fingerprint for code, not for reading",
    "run": "the file of recorded AI calls; for auditing, not reading",
    "layout": "tells the code how to cut a document into pieces; not for reading",
    "style": "tells the code how a two-column book prints its headings (with layout); not for reading",
    # A code book kept outside the repo (a state law folder's: New York's Residential Code). The workbook lists a
    # place's own documents; a state's book is not in it until its rules are (egress step 3), which shows these.
    "kept_outside_repo": "only a state code book kept outside the repo has it; not in a place's workbook yet",
    "copy": "only a state code book kept outside the repo has it; not in a place's workbook yet",
    "terms": "only a state code book kept outside the repo has it; not in a place's workbook yet",
    "edition": "only a state code book kept outside the repo has it; not in a place's workbook yet",
    "in_force": "only a state code book kept outside the repo has it; not in a place's workbook yet",
    "brought_in": "tells the code which pages and sections of a book to read; not for reading",
}
NOT_DOWNLOADED_FIELDS = {"title", "url", "why_missing"}   # sources.yaml `not_yet_downloaded` entries
# The "City's exact words" for a cited chart cell the chart reader can't confirm (never a blank).
NOT_VERIFIED = "(not verified: the chart reader has no such cell; run python -m rule_format)"
FIELDS = {"rule": RULE_FIELDS, "definitions": TERM_SCHEMAS["definitions"]["fields"] | APPROVAL_FIELDS,
          "uses": TERM_SCHEMAS["uses"]["fields"] | APPROVAL_FIELDS, "label": LABEL_FIELDS | APPROVAL_FIELDS,
          "source": SOURCE_FIELDS | NOT_DOWNLOADED_FIELDS}   # documents and the ones still to get share a tab


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


# ---- citations -----------------------------------------------------------------------------------------

def sections_lookup(j: Path):
    """section(file, page, line): the section a line of a document cut into pieces is in ("§325-8A", "§325-3B
    (KITCHEN)", a title for front matter), or "". The one lookup, for citations here and in the Rhino panel."""
    sections = {}                                  # file -> [(page, first, last, piece id, title)]
    for path in sorted((j / "2_extracted_text").glob("*.sections.jsonl")):
        header, pieces = load_pieces(path)
        sections[header["file"]] = [(pg, a, b, pid, piece["title"]) for pid, piece in pieces.items()
                                    for pg, a, b in piece["lines"]]

    def section(file, page, line):
        for pg, a, b, pid, piece_title in sections.get(file, ()):
            if pg == page and a <= line <= b:
                if not pid[:1].isdigit():                       # front matter, an editor's note
                    return piece_title
                number, _, term = pid.partition(":")            # 325-3B:kitchen is the definition of KITCHEN
                return f"§{number}" + (f" ({piece_title})" if term else "")
        return ""
    return section


def citer(j: Path, documents: dict[str, dict]):
    """citation(source): where a quote is, in words a reader can follow, e.g. "City of Ithaca Code, Chapter 325
    Zoning (full text), §325-8A, p.24, lines 15–16". The document by its title in sources.yaml; for a document
    cut into pieces (2_extracted_text/<doc>.sections.jsonl), the section the first cited line is in; then page
    and lines. A chart cell is cited by its section, row and district column, e.g. "City of Ithaca Zoning
    Charts, p.3, Yard Dimensions · Rear · R-1B". The exact words go in their own column, and the link opens
    the page."""
    section = sections_lookup(j)

    def citation(s: dict) -> str:
        if not s.get("file"):
            return ""
        lines = s.get("lines") or []
        if isinstance(s.get("cell"), dict):              # a chart cell: section · row · district column
            c = s["cell"]
            return ", ".join(p for p in [(documents.get(s["file"]) or {}).get("title") or s["file"],
                                         f"p.{s['page']}" if s.get("page") is not None else "",
                                         " · ".join(str(c.get(k, "")) for k in ("section", "row", "column"))] if p)
        parts = [(documents.get(s["file"]) or {}).get("title") or s["file"],
                 section(s["file"], s.get("page"), lines[0]) if lines else "",
                 f"p.{s['page']}" if s.get("page") is not None else "",
                 (f"line {lines[0]}" if lines[0] == lines[1] else f"lines {lines[0]}–{lines[1]}") if len(lines) == 2 else ""]
        return ", ".join(p for p in parts if p)
    return citation


# ---- cell text -----------------------------------------------------------------------------------------

def _lines(source: dict) -> str:
    lines = source.get("lines") or []
    return f"{lines[0]}–{lines[1]}" if len(lines) == 2 and lines[0] != lines[1] else str(lines[0]) if lines else ""


def _bullets(items) -> str:
    return "\n".join(f"• {' '.join(str(i).split())}" for i in items or [])


def _answers(answers) -> str:
    return _bullets(f"{a.get('question')} → {a.get('answer')} ({a.get('answered_by')}, {a.get('answered_on')})"
                    for a in answers or [])


def _readings(readings) -> str:
    return " / ".join(f"{g.get('id')}: {g.get('reading')}" for g in readings or [])


def _research(research) -> str:
    """Why each open question is still open: what was searched, why it's unsettled, the readings in play."""
    return _bullets(f"{_text(x.get('question'))} — searched: {', '.join(x.get('searched') or []) or 'nothing yet'}. "
                    f"{_text(x.get('why_open'))}" + (f" Readings: {_readings(x.get('readings'))}." if x.get("readings")
                                                     else "") + (f" ({x['report']})" if x.get("report") else "")
                    for x in research or [])


def finding_text(f: dict) -> str:
    """A finding as the architects see it: the law's own answer, or Gordium's reading and who should confirm it
    (an architect's or the City's answer, in `answers`, outranks a reading)."""
    head = ("The law" if f.get("kind") == "law" else
            f"Gordium's reading ({str(f.get('strength', '')).replace('_', ' ')}) · confirm with {f.get('confirm_with')}")
    still = f" Still open: {', '.join(f['still_open'])}." if f.get("still_open") else ""
    return f"{head}: {_text(f.get('answer'))}{still}"


def _source_text(s: dict) -> str:
    if "file" in s:
        return f"{s['file']} p.{s.get('page')} l.{_lines(s)}: {s.get('quote')}"
    return f"rank {s.get('rank')}: {s.get('cite')}" + (f" ({s['url']})" if s.get("url") else "") + \
        (f": \"{s['quote']}\"" if s.get("quote") else "")


def _findings(findings) -> str:
    return _bullets(f"{_text(f.get('question'))} → {finding_text(f)}" + (f" ({f['report']})" if f.get("report") else "")
                    for f in findings or [])


def _examples(examples) -> str:
    return _bullets(f"{', '.join(f'{k} = {v}' for k, v in (e.get('given') or {}).items())}{_example_parts(e)} → "
                    f"{e.get('expect')}" + (f" ({e['note']})" if e.get("note") else "") for e in examples or [])


def _example_parts(e: dict) -> str:
    """A rule for each part's example (rule_format/parts.py): its parts and the rows it expects; "" for any other."""
    if "parts" not in e and "rows" not in e:
        return ""
    given = e.get("parts") if isinstance(e.get("parts"), dict) else {}
    listed = "; ".join(f"{kind} {p.get('id')}" + (f" in {p['within']}" if p.get("within") else "")
                       + (f" ({', '.join(f'{k} = {v}' for k, v in p['measures'].items())})"
                          if isinstance(p.get("measures"), dict) and p["measures"] else "")
                       for kind, ps in given.items() for p in (ps if isinstance(ps, list) else []) if isinstance(p, dict))
    rows = "; ".join(f"{r.get('outcome')}" + (f" for {r['part']}" if r.get("part") else "")
                     + (f" in {r['within']}" if r.get("within") else "")
                     for r in (e.get("rows") if isinstance(e.get("rows"), list) else []) if isinstance(r, dict))
    return f" · parts: {listed or 'none'} · rows: {rows or 'none'}"


def _revisions(revised, label) -> str:
    """Each change after the AI's answer, as it happened: from → to, who, when, why (a chain reads in order)."""
    return _bullets((f"{r['from']} → {to}" if "from" in r else "rule added" if r.get("field") == "rule"
                     else f"{r.get('field')} changed")
                    + f" ({r.get('by')}, {r.get('date')}): {r.get('why')}" for r, to in revision_steps(revised or [], label))


# ---- the tables ----------------------------------------------------------------------------------------

def rulebooks(j: Path) -> list[tuple[str, dict]]:
    """(path within 5_zoning_rules, rulebook) for every rulebook there: the validator's own list of files."""
    folder = j / "5_zoning_rules"
    return [(p.relative_to(folder).as_posix(), load(p) or {}) for p in rulebook_paths(folder)]


def _text(value) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""


def _quotes(sources) -> str:
    return _bullets(f"p.{s.get('page')} l.{_lines(s)}: {s.get('quote')}" for s in sources or [])


class Col:
    """One column: header, width, the format fields it shows (none for a column filled per tab, like Zone or
    Link) and value(entry, source, n, total) for one row. every=False puts it on an entry's first source row
    only (long text); identifying and short filterable columns repeat, so sorting and filtering keep an
    entry together."""
    def __init__(self, header, width, fields=(), value=None, every=True):
        self.header, self.width, self.every, self.value = header, width, every, value
        self.fields = {fields} if isinstance(fields, str) else set(fields)


def shown(cols: list[Col]) -> set[str]:
    return set().union(*(c.fields for c in cols))


def _get(field, fmt=lambda v: v if v is not None else ""):
    return lambda e, s, n, t: fmt(e.get(field))


def _source_cols(quote_width):
    """The columns every one-row-per-source tab shares: which source, where it is (a citation people can
    read, filled per tab; and the page, to sort by), the words, the link."""
    return [Col("Source", 8, "sources", lambda e, s, n, t: f"{n + 1} of {t}" if e.get("sources") else ""),
            Col("Citation", 34),
            Col("Page", 6, "sources", lambda e, s, n, t: s.get("page", "")),
            Col("City's exact words", quote_width),          # a quote, or a chart cell's value (filled per tab)
            Col("Link", 10, "sources", lambda e, s, n, t: f"Open p.{s.get('page')}" if s.get("file") else "")]


_QUESTIONS = [Col("Open questions", 50, "open_questions", _get("open_questions", _bullets), every=False),
              Col("Research (why still open)", 60, "research", _get("research", _research), every=False),
              Col("Findings (research settled)", 60, "findings", _get("findings", _findings), every=False),
              Col("Answers", 40, "answers", _get("answers", _answers), every=False)]
_RELATED = Col("Related sections", 30)          # by the term index: the requirement sections that use its words
_NOTES = Col("Notes", 40, "notes", _get("notes", _text), every=False)
_WHO = [Col("Status", 8, "status", _get("status")), Col("Drafted by", 18, "drafted_by", _get("drafted_by"))]

def _for_each(e: dict) -> str:
    """"for each emergency escape opening · within each sleeping room · if none: fail"; empty for a whole-lot rule."""
    words = [f"{label}{e[k]}".replace("_", " ") for k, label in
             (("for_each", "for each "), ("within", "within each "), ("when_none", "if none: ")) if e.get(k)]
    return " · ".join(words)


COLUMNS = {
    "rule": [Col("Zone", 9), Col("Rulebook", 18), Col("Rule id", 28, "id", _get("id")),
             Col("Title", 34, "title", _get("title")), *_WHO,
             Col("Kind", 7, "kind", _get("kind")), Col("Topic", 14, "topic", _get("topic")),
             # a rule for each part (rule_format/parts.py): what it repeats over, and what "none" means
             Col("For each part", 26, ("for_each", "within", "when_none"), lambda e, s, n, t: _for_each(e)),
             # section group 8d: a part's own requirement, apart from whether the law asks it of this part
             Col("Part's own limit (formula)", 36, "limit", _get("limit"), every=False),
             Col("Check (formula)", 40, "check", _get("check"), every=False),
             Col("Applies when", 26, "applies_when", _get("applies_when"), every=False),
             Col("Needs review when", 34, "review_when", _get("review_when", lambda v: _bullets(
                 f"{r.get('when')}: {r.get('reason')}" for r in v or [])), every=False),
             Col("Worked examples", 40, "examples", _get("examples", _examples), every=False),
             *_source_cols(60), _RELATED,
             Col("Changed after the AI", 60, "revised", lambda e, s, n, t: _revisions(e.get("revised"), None),
                 every=False),
             *_QUESTIONS, _NOTES],
    "definitions": [Col("Id", 24), Col("Term", 26, "term", _get("term")), *_WHO,
                    Col("Measures", 22, "measures", _get("measures", lambda v: ", ".join(v or [])), every=False),
                    *_source_cols(70), _RELATED, *_QUESTIONS, _NOTES],
    "uses": [Col("Id", 30), Col("Name", 40, "name", _get("name")), *_WHO, *_source_cols(50), _NOTES],
    # One row per piece of the law (so the tab proves nothing was skipped); each quote says its own page.
    "label": [Col("Document", 26), Col("Piece", 22), Col("Title", 40), Col("Pages", 8),
              Col("Label", 16, "label", _get("label", lambda v: v or "unlabeled")),
              Col("Topic", 14, "topic", _get("topic")), Col("Reason", 60, "reason", _get("reason", _text)),
              Col("Quote(s)", 60, "sources", _get("sources", _quotes)), Col("Link", 10), *_WHO,
              Col("Changed after the AI", 60, "revised",
                  lambda e, s, n, t: _revisions(e.get("revised"), e.get("label"))),
              *_QUESTIONS, _NOTES],
    "source": [Col("File", 34, "file", _get("file")), Col("Title", 44, "title", _get("title")),
               Col("Publisher", 22, "publisher", _get("publisher")), Col("Official URL", 50, "url", _get("url")),
               Col("Downloaded", 12, "downloaded_on", _get("downloaded_on", _text)),
               Col("Adopted", 12, "adopted_on", _get("adopted_on", _text)),
               Col("Created", 12, "created_on", _get("created_on", _text)), Col("Pages", 7, "pages", _get("pages")),
               Col("Chart pages", 10, "chart_pages", _get("chart_pages", lambda v: ", ".join(map(str, v)) if v else "")),
               Col("Fingerprint (SHA-256)", 30, "sha256", _get("sha256")),
               Col("Quotable", 9, "quotable", lambda e, s, n, t: "not downloaded" if "why_missing" in e
                   else "no" if e.get("quotable") is False else "yes"),
               Col("Why not quotable / not downloaded", 50, ("not_quotable_because", "why_missing"),
                   lambda e, s, n, t: _text(e.get("not_quotable_because") or e.get("why_missing"))),
               Col("Contents", 50, "contents", _get("contents", _text)),
               Col("Notes", 50, "notes", _get("notes", _text))],
}


def entry_rows(entry: dict, cols: list[Col], fixed: dict, per_source=True) -> list[list]:
    """An entry's rows: one per source (or one in all), each cell from its column; `fixed` fills the columns
    that show no field of the entry (Zone, Id, Link...)."""
    sources = (entry.get("sources") or [{}]) if per_source else [{}]
    cell = lambda c, s, n: (fixed[c.header](s) if callable(fixed[c.header]) else fixed[c.header]) if c.value is None \
        else c.value(entry, s, n, len(sources)) if c.every or n == 0 else ""
    return [[cell(c, s, n) for c in cols] for n, s in enumerate(sources)]


def _tab(title, cols, rows, links, link_header="Link") -> dict:
    return {"title": title, "columns": [(c.header, c.width) for c in cols], "rows": rows,
            "links": {link_header: links}}


def tables(j: Path) -> dict[str, dict]:
    """{tab: {"title", "columns": [(header, width)], "rows": [[cell, ...]], "links": {header: [url per row]}}}.
    A link cell holds its display text; its URL is in "links"."""
    sources_file = load(j / "1_source_documents/sources.yaml")
    documents = {d["file"]: d for d in sources_file["documents"]}
    link = lambda s: page_link(j, documents, s["file"], s.get("page")) if s.get("file") else None
    cite = citer(j, documents)
    ctx = Context.for_jurisdiction(j)          # the chart cells as the checker reads them (only verified ones)
    def words(s):                              # the city's exact words: a quote, or the cited cell's value
        if "quote" in s:
            return s["quote"]
        cell = _cell(s, ctx) if isinstance(s.get("cell"), dict) else None
        if cell:
            return cell["value"]
        return NOT_VERIFIED if s.get("file") else ""       # never a blank that looks like an empty cell
    out = {}

    # Related sections, by the term index: for a definition, every piece that uses its term; for a rule, the
    # requirement sections (labeled rule or flag) that use the words it quotes, densest first, less its own.
    index_file = j / "4_term_definitions" / INDEX_NAME
    index = load(index_file) if index_file.exists() else None
    label_files = [load(p) for p in sorted((j / "3_section_labels").glob("*.yaml"))]
    requires = {pid for b in label_files if isinstance(b, dict) for pid, e in (b.get("labels") or {}).items()
                if e.get("label") in ("rule", "flag")}
    texts, where = {}, {}                          # where: (file, page, line) -> the piece that line is in
    for sections in sorted((j / "2_extracted_text").glob("*.sections.jsonl")):
        header, pieces = load_pieces(sections)
        law_rows = read_jsonl(sections.with_name(sections.name.removesuffix(".sections.jsonl") + ".jsonl"))
        texts |= {pid: piece_text(law_rows, piece) for pid, piece in pieces.items() if pid in requires}
        where |= {(header["file"], pg, n): pid for pid, piece in pieces.items() for pg, a, b in piece["lines"]
                  for n in range(a, b + 1)}
    def first_row(e):
        first = (e.get("sources") or [{}])[0]
        return lambda s: s is first
    def related_to_rule(e):
        if not index:
            return ""
        words = " ".join([e.get("title") or ""] + [s.get("quote", "") for s in e.get("sources") or []])
        own = {where.get((s["file"], s["page"], s["lines"][0])) for s in e.get("sources") or []
               if s.get("file") and s.get("lines")}
        return ", ".join(p for p in related(index, words, texts) if p not in own)
    def related_to_term(key):
        return ", ".join(p["piece"] for p in index["terms"].get(key, {}).get("pieces", [])) if index else ""
    def once(e, value):                              # on an entry's first source row only (long text)
        if not e.get("sources"):
            return lambda s: value                   # one row in all
        is_first = first_row(e)
        return lambda s: value if is_first(s) else ""

    def per_source(entries, cols):                  # [(entry, fixed)] -> rows, links: one row per source
        rows, links = [], []
        for e, fixed in entries:
            rows += entry_rows(e, cols, fixed)
            links += [link(s) for s in e.get("sources") or [{}]]
        return rows, links

    out["Rules"] = _tab("GORDIUM | Zoning rules (drafts, checked by code)", COLUMNS["rule"], *per_source(
        [(r, {"Zone": book.get("district", ""), "Rulebook": path, "Citation": cite, "City's exact words": words,
              "Related sections": once(r, related_to_rule(r))})
         for path, book in rulebooks(j) for r in book.get("rules") or []], COLUMNS["rule"]))

    terms = {schema: load(j / f"4_term_definitions/{schema}.yaml") or {} for schema in TERM_SCHEMAS
             if (j / f"4_term_definitions/{schema}.yaml").exists()}
    for schema, tab, title in [("definitions", "Definitions", "GORDIUM | Definitions (the city's own words)"),
                               ("uses", "Uses", "GORDIUM | Use names (the only values a rule's `use` may take)")]:
        out[tab] = _tab(title, COLUMNS[schema], *per_source(
            [(e, {"Id": key, "Citation": cite, "City's exact words": words,
                  "Related sections": once(e, related_to_term(key))})
             for key, e in terms.get(schema, {}).items()], COLUMNS[schema]))

    labels_by_doc = {}                                 # document -> (its labels file, the labels)
    for path in sorted((j / "3_section_labels").glob("*.yaml")):
        book = load(path)
        if isinstance(book, dict) and "labels" in book:
            labels_by_doc[book["document"]] = (path.relative_to(j).as_posix(), book["labels"])

    # Questions: every open question anywhere, one row each, with the file it is written in.
    # With each: what was searched, why it's still open, and the readings still in play (the design is checked
    # under every one). Findings: what research settled, with its sources, one row each.
    rows, links, found, found_links = [], [], [], []
    def ask(kind, where, ident, entry):
        s = (entry.get("sources") or [{}])[0]
        research = {x.get("question"): x for x in entry.get("research") or []}
        for q in entry.get("open_questions") or []:
            x = research.get(q, {})
            rows.append([kind, where, ident, _text(q), ", ".join(x.get("searched") or []), _text(x.get("why_open")),
                         _readings(x.get("readings")), x.get("report", ""), cite(s), s.get("page", ""),
                         f"Open p.{s.get('page')}" if s.get("file") else ""])
            links.append(link(s))
        for f in entry.get("findings") or []:
            code = next((c for c in f.get("sources") or [] if c.get("file")), {})
            found.append([kind, where, ident, f.get("id", ""), f.get("kind", ""), f.get("strength", ""),
                          f.get("confirm_with", ""), _text(f.get("question")), finding_text(f),
                          ", ".join(f.get("still_open") or []),
                          _bullets(_source_text(c) for c in f.get("sources") or []), f.get("report", ""),
                          f"Open p.{code.get('page')}" if code else ""])
            found_links.append(link(code) if code else None)
    for path, book in rulebooks(j):
        for rule in book.get("rules") or []:
            ask("Rule", f"5_zoning_rules/{path}", rule.get("id", ""), rule)
    for schema, entries in terms.items():
        for key, e in entries.items():
            ask(schema.rstrip("s").capitalize(), f"4_term_definitions/{schema}.yaml", key, e)
    for labels_path, labels in labels_by_doc.values():
        for pid, e in labels.items():
            ask("Section label", labels_path, pid, e)
    out["Questions"] = {"title": "GORDIUM | Open questions (researched first: what was searched, why still open)",
                        "rows": rows, "links": {"Link": links},
                        "columns": [("About", 14), ("In", 40), ("Id", 30), ("Question", 90), ("Searched", 30),
                                    ("Why still open", 60), ("Readings in play", 50), ("Research report", 30),
                                    ("Citation", 34), ("Page", 6), ("Link", 10)]}
    out["Findings"] = {"title": "GORDIUM | What research settled (the law's answer, or Gordium's reading to confirm)",
                       "rows": found, "links": {"Link": found_links},
                       "columns": [("About", 14), ("In", 40), ("Id", 30), ("Finding", 28), ("Kind", 9),
                                   ("Strength", 13), ("Confirm with", 30), ("Question", 60), ("Answer", 80),
                                   ("Still open", 24), ("Sources", 80), ("Research report", 30), ("Link", 10)]}

    # Coverage: every piece of every cut document, in the law's order, with its label. The link opens the
    # page of the label's first quote (where its reason points), else the piece's first page.
    rows, links = [], []
    for sections in sorted((j / "2_extracted_text").glob("*.sections.jsonl")):
        header, pieces = load_pieces(sections)
        labels = labels_by_doc.get(header["file"], ("", {}))[1]
        for pid, piece in pieces.items():
            e = labels.get(pid, {})
            pages = sorted({p for p, _, _ in piece["lines"]})
            page = (e.get("sources") or [{}])[0].get("page") or piece["lines"][0][0]
            rows += entry_rows(e, COLUMNS["label"], {
                "Document": header["file"], "Piece": pid, "Title": piece["title"], "Link": f"Open p.{page}",
                "Pages": str(pages[0]) if len(pages) == 1 else f"{pages[0]}–{pages[-1]}"}, per_source=False)
            links.append(page_link(j, documents, header["file"], page))
    out["Coverage"] = _tab("GORDIUM | Every part of the law, and what it is", COLUMNS["label"], rows, links)

    # Sources: the documents, then the ones not yet downloaded (and why).
    entries = list(documents.values()) + list(sources_file.get("not_yet_downloaded") or [])
    out["Sources"] = _tab("GORDIUM | Source documents (fingerprinted)", COLUMNS["source"],
                          [entry_rows(d, COLUMNS["source"], {}, per_source=False)[0] for d in entries],
                          [d.get("url") or None for d in entries], "Official URL")
    return out


# ---- layout --------------------------------------------------------------------------------------------

def _cell_text(value):
    """Text is stored as text, never a formula (a quote or an AI-written note starting with '=' must not run),
    and characters Excel can't hold are shown as '�' rather than crashing the export."""
    return ILLEGAL_CHARACTERS_RE.sub("�", value) if isinstance(value, str) else value


def write_block(ws, top: int, columns: list[tuple[str, float]], rows: list[list], links: dict[str, list] | None = None,
                fills: dict[str, list] | None = None) -> int:
    """One table on a sheet, in the architects' style: Arial in their ink color, bold 12-pt headers on row
    `top`, 11-pt wrapped rows under it, links as clickable cells (named by their column's header), optional
    cell fills (same naming: {header: [hex color or None per row]}). A column's width is set where given (None
    keeps the width an earlier block set). Returns the first row after the block."""
    headers = [h for h, _ in columns]
    for c, (header, width) in enumerate(columns, 1):
        cell = ws.cell(row=top, column=c, value=header)
        cell.font = Font(name=FONT, size=12, bold=True, color=INK)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if width:                                     # a later block on the sheet passes None to keep them
            ws.column_dimensions[cell.column_letter].width = width
    for r, row in enumerate(rows, top + 1):
        for c, value in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=_cell_text(value))
            if isinstance(value, str):
                cell.data_type = "s"
            cell.font = Font(name=FONT, size=11, color=INK)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for header, urls in (links or {}).items():
        c = headers.index(header) + 1
        for r, url in enumerate(urls, top + 1):
            if url:
                cell = ws.cell(row=r, column=c)
                cell.hyperlink = url
                cell.font = Font(name=FONT, size=11, color="0563C1", underline="single")
    for header, colors in (fills or {}).items():
        c = headers.index(header) + 1
        for r, color in enumerate(colors, top + 1):
            if color:
                ws.cell(row=r, column=c).fill = PatternFill("solid", fgColor=color)
    return top + 1 + len(rows)


def title(ws, text: str) -> None:
    """The sheet's title in A1: Arial 16 bold in their ink color, like the architects' sheet."""
    ws["A1"] = text
    ws["A1"].font = Font(name=FONT, size=16, bold=True, color=INK)


def build(data: dict[str, dict]) -> Workbook:
    """Lay the tables out like the architects' sheet: a bold title in row 1, headers in row 2 (frozen),
    Arial in their ink color, wrapped text, links as clickable cells."""
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "Gordium (generated: python -m rule_export)"
    for name, t in data.items():
        ws = wb.create_sheet(name)
        title(ws, t["title"])
        write_block(ws, 2, t["columns"], t["rows"], t["links"])
        ws.freeze_panes = "A3"
    return wb


def _look(c) -> tuple:
    """How a cell looks: font, fill, left border and alignment (what makes a sheet read like the architects')."""
    f, color = c.font, lambda x: x.rgb if x is not None and x.type == "rgb" else None
    return (f.name, f.sz, bool(f.b), bool(f.i), f.u, color(f.color),
            color(c.fill.fgColor) if c.fill.fill_type else None, c.border.left.style,
            c.alignment.wrap_text, c.alignment.vertical)


def contents(wb) -> list:
    """What a workbook says and how it looks (sheet names; each cell's value, link and look; column widths;
    frozen panes), for comparing a fresh build with a saved file. Content, not bytes: Excel files carry a save
    timestamp."""
    value = lambda v: None if v == "" else v                  # a saved empty cell reads back as None
    return [(ws.title, ws.freeze_panes,
             {k: d.width for k, d in sorted(ws.column_dimensions.items()) if d.customWidth},
             [[(value(c.value), c.hyperlink.target if c.hyperlink else None, _look(c)) for c in row]
              for row in ws.iter_rows()]) for ws in wb.worksheets]


def output_path(j: Path) -> Path:
    return j / f"{j.name}_rules.xlsx"
