"""Each law's contents with Gordium's coverage (C7), and where a row's rule is in its document (C6): the "By code"
view's data (ui_data.py; docs/revit/checker_ui_data.md). Plain code, no AI, words and data only: nothing here reads or
changes a status.

Read from generated files only, never a list kept in code: the document's contents (2_extracted_text/
<doc>.contents.jsonl, made by `python -m document_extraction contents` from the book's own contents pages, or from
the zoning chapter's own article headings), its pieces (2_extracted_text/<doc>.sections.jsonl), their labels
(3_section_labels/<doc>.yaml), and which pieces have rules (an ICC book's 6_coverage_report/<doc>.rules.yaml; for the
zoning chapter, the pieces the district's rules cite).

A piece's coverage: "rules" (rules check it), "flag" (only flag rules raise it, for a person), "not_checked_yet"
(labeled rule or flag, with no rules a check uses), "not_for_checking" (brought in: a definition, a reference, nothing
to check). A section's or chapter's: "not_brought_in" when none of it was extracted (Gordium hasn't read it), else
the most telling of its pieces' (rules > flag > not_checked_yet > not_for_checking), with `counts` of each, and
`whole` false where only some of a section was brought in (the rest is not brought in).
"""

import re
from pathlib import Path

from rule_format.labels import contents_section, load_pieces
from rule_format.rulebook import load, read_jsonl

RULES, FLAG, NOT_YET, NOT_FOR, NOT_IN = "rules", "flag", "not_checked_yet", "not_for_checking", "not_brought_in"
ORDER = (RULES, FLAG, NOT_YET, NOT_FOR)
CONTAINERS = ("chapter", "article", "appendix")   # what a section is in (a part of the RCNYS only groups chapters)
CHART = "zoning_charts"                     # the District Regulations Chart is part of §325-8 (§325-8A, p.24)


_READ = {}     # (path, how) -> (its size and time, what was read): each file read again only once it changes


def _read(path: Path, how: str):
    """A file's contents (`how`: "jsonl", "pieces" or "yaml"), read once and kept until the file changes (a check
    runs on every edit; the files change only when made again). Never changed by a caller."""
    stat = path.stat()
    key, mark = (str(path), how), (stat.st_size, stat.st_mtime_ns)
    if key not in _READ or _READ[key][0] != mark:
        got = read_jsonl(path) if how == "jsonl" else load_pieces(path)[1] if how == "pieces" else load(path)
        _READ[key] = (mark, got)
    return _READ[key][1]


def _rows(path: Path) -> tuple[dict, list[dict]]:
    lines = _read(path, "jsonl")
    return (lines[0], lines[1:]) if lines else ({}, [])


def section_of_piece(piece: str) -> str | None:
    """The contents section a piece is in (rule_format.labels.contents_section: the one rule, the extraction's too)."""
    return contents_section(piece)


def _folder_books(folder: Path, key: str, documents: dict) -> list[dict]:
    out = []
    for path in sorted((folder / "2_extracted_text").glob("*.contents.jsonl")):
        header, rows = _rows(path)
        file = header.get("file")
        sections_file = folder / "2_extracted_text" / (path.name[:-len(".contents.jsonl")] + ".sections.jsonl")
        pieces = _read(sections_file, "pieces") if sections_file.is_file() else {}
        labels_file = folder / "3_section_labels" / (path.name[:-len(".contents.jsonl")] + ".yaml")
        labels = (_read(labels_file, "yaml") or {}).get("labels") or {} if labels_file.is_file() else {}
        out.append({"key": key, "folder": folder, "file": file,
                    "document": (documents.get(file) or {}).get("title") or file,
                    "header": header, "rows": rows, "pieces": pieces, "labels": labels,
                    "brought_in": ((documents.get(file) or {}).get("brought_in") or {})})
    return out


def books(laws: list[dict], place_folder, documents: dict | None) -> dict:
    """{law key: [book]}: "zoning" (the place's own documents) and each inherited law's key, each book its contents
    rows, pieces, labels and documents entry."""
    out = {}
    if place_folder is not None:
        out["zoning"] = _folder_books(Path(place_folder), "zoning", documents or {})
    for law in laws:
        out[law["key"]] = _folder_books(Path(law["folder"]), law["key"], law.get("documents") or {})
    return out


def _book_for(books: dict, item: dict, file: str | None) -> dict | None:
    key = item.get("law_key") if item.get("group") == "law" else "zoning"
    found = books.get(key) or []
    return next((b for b in found if b["file"] == file), None) or (found[0] if found else None)


def _piece_at(book: dict, page, line) -> str | None:
    for pid, piece in book["pieces"].items():
        for pg, a, b in piece.get("lines") or []:
            if pg == page and a <= line <= b:
                return pid
    return None


def in_code(item: dict, rule: dict | None, books: dict) -> dict | None:
    """Where a row's rule is in its document: {document, file, chapter, chapter_title, section, section_title,
    piece, piece_title}, from the rule's first quote (the place in the book its row is shown by), each part from the
    contents and sections files; a part not found is None. None for a row of no rule."""
    if not item.get("rule") or not isinstance(rule, dict):
        return None
    sources = [s for s in rule.get("sources") or [] if isinstance(s, dict) and s.get("file")]
    if not sources:
        return None
    first = sources[0]
    chart = CHART in str(first.get("file"))
    if chart:      # the chart is §325-8's (its own words: "made a part of this chapter"); its book is the chapter
        first = next((s for s in sources if CHART not in str(s.get("file"))), first)
    book = _book_for(books, item, None if chart and CHART in str(first.get("file")) else first.get("file"))
    if book is None:
        return None
    lines = first.get("lines") if isinstance(first.get("lines"), list) else []
    if chart:
        piece, piece_title = "325-8", "District Regulations Chart"
    else:
        piece = _piece_at(book, first.get("page"), lines[0]) if lines else None
        piece_title = (book["pieces"].get(piece) or {}).get("title") if piece else None
    section = section_of_piece(piece) if piece else None
    rows = {r.get("number"): r for r in book["rows"] if r.get("kind") == "section"}
    chapters = {r.get("number"): r for r in book["rows"] if r.get("kind") in CONTAINERS}
    row = rows.get(section) or {}
    chapter = row.get("chapter")
    return {"document": book["document"], "file": book["file"], "chapter": chapter,
            "chapter_title": (chapters.get(chapter) or {}).get("title"), "section": section,
            "section_title": row.get("title") or (book["pieces"].get(section) or {}).get("title"),
            "piece": piece, "piece_title": " ".join(str(piece_title).split()) if piece_title else None}


# ---- coverage -------------------------------------------------------------------------------------------------

def _coverage(book: dict, rules: list[dict]) -> dict:
    """{piece id: (coverage, [rule ids])} for every piece of the book that was brought in."""
    folder = book["folder"]
    report = folder / "6_coverage_report" / (str(book["file"]).rsplit(".", 1)[0] + ".rules.yaml")
    out = {}
    loaded = {r.get("id") for r in rules if isinstance(r, dict)}
    if report.is_file():                    # an ICC book: the generated list of pieces with rules
        data = _read(report, "yaml") or {}
        listed = {str(p) for p in data.get("not_checked_yet") or []}
        for pid, entry in (data.get("pieces") or {}).items():
            ids = [i for i in entry.get("rules") or [] if i in loaded]
            if not ids or str(pid) in listed or not set(entry.get("rules") or []) <= loaded:
                out[str(pid)] = (NOT_YET, ids)
            else:
                out[str(pid)] = (FLAG if entry.get("label") == "flag" else RULES, ids)
    else:                                   # the zoning chapter: the pieces the district's rules cite
        cited = {}
        for r in rules:
            for s in r.get("sources") or []:
                lines = s.get("lines") if isinstance(s, dict) and isinstance(s.get("lines"), list) else []
                if isinstance(s, dict) and s.get("file") == book["file"] and lines:
                    pid = _piece_at(book, s.get("page"), lines[0])
                    if pid:
                        cited.setdefault(pid, []).append(r)
            if any(isinstance(s, dict) and CHART in str(s.get("file")) for s in r.get("sources") or []):
                cited.setdefault("325-8", []).append(r)
        for pid, label in book["labels"].items():
            lab = label.get("label") if isinstance(label, dict) else None
            if lab not in ("rule", "flag"):
                continue
            mine = cited.get(pid) or []
            ids = list(dict.fromkeys(r.get("id") for r in mine))
            out[pid] = ((FLAG if all(r.get("kind") == "flag" for r in mine) else RULES) if mine else NOT_YET, ids)
        for pid, mine in cited.items():     # a piece labeled otherwise that rules cite still has rules
            if pid not in out:
                out[pid] = (FLAG if all(r.get("kind") == "flag" for r in mine) else RULES,
                            list(dict.fromkeys(r.get("id") for r in mine)))
    for pid in book["pieces"]:
        out.setdefault(pid, (NOT_FOR, []))
    return out


def _sum(coverages: list[str]) -> str:
    return next((c for c in ORDER if c in coverages), NOT_FOR) if coverages else NOT_IN


def _whole(book: dict, section: str) -> bool | None:
    """Whether the whole section was brought in: always for a document extracted whole (no brought_in.sections),
    else whether its own number is among the sections (or `alone` ones) brought in."""
    listed = book["brought_in"].get("sections") if isinstance(book["brought_in"], dict) else None
    if not listed:
        return True
    return section in {str(s) for s in listed}


def listing(books: dict, items: list[dict], rules_for=None) -> list[dict]:
    """The view's `contents`: one entry per document (zoning first), every chapter and section with its coverage."""
    out = []
    for key, found in books.items():
        for book in found:
            rules = _rules_of(key, items, rules_for)
            cov = _coverage(book, rules)
            by_section = {}
            for pid, (c, ids) in cov.items():
                by_section.setdefault(section_of_piece(pid), []).append(
                    {"id": pid, "title": " ".join(str((book["pieces"].get(pid) or {}).get("title") or pid).split()),
                     "coverage": c, "rules": ids})
            chapters, by_number = [], {}
            for r in book["rows"]:
                if r.get("kind") in CONTAINERS:
                    by_number[r.get("number")] = {"number": r.get("number"), "kind": r.get("kind"),
                                                  "title": r.get("title"), "book_page": r.get("book_page"),
                                                  "sections": []}
                    chapters.append(by_number[r.get("number")])
                elif r.get("kind") == "section" and r.get("chapter") in by_number:
                    pieces = by_section.get(r.get("number")) or []
                    covs = [p["coverage"] for p in pieces]
                    by_number[r["chapter"]]["sections"].append({
                        "number": r.get("number"), "title": r.get("title"), "book_page": r.get("book_page"),
                        "coverage": _sum(covs), "whole": _whole(book, r.get("number")) if pieces else False,
                        "counts": {c: covs.count(c) for c in ORDER if c in covs}, "pieces": pieces})
            for ch in chapters:
                covs = [s["coverage"] for s in ch["sections"]]
                ch["coverage"] = next((c for c in ORDER if c in covs), NOT_FOR if any(c != NOT_IN for c in covs)
                                      else NOT_IN)
                ch["counts"] = {c: covs.count(c) for c in ORDER + (NOT_IN,) if c in covs}
            out.append({"key": key, "document": book["document"], "file": book["file"], "chapters": chapters})
    return out


def _rules_of(key: str, items: list[dict], rules_for) -> list[dict]:
    return rules_for(key) if rules_for else []
