"""Section labels (3_section_labels/<document>.yaml): what kind of text each piece of a law is.

The law is cut into pieces by code (document_extraction/sections.py, saved as
2_extracted_text/<document>.sections.jsonl). Each label says what the system does with one piece:

    325-16C:
      label: rule                   # rule · flag · reference · not_for_checking (vocabulary.yaml)
      topic: dimensions             # from vocabulary.yaml
      reason: Sets when a building may exceed the district height limit.
      sources:                      # the exact words that justify the label, checked like any rule source
        - {file: chapter_325_zoning_2026-10.pdf, page: 47, lines: [6, 7], quote: "..."}
      piece_sha256: ...             # fingerprint of the piece as labeled (its lines + the PDF version)
      run: 3_section_labels/runs/2026-10-20_claude-haiku-5-5.jsonl   # the recorded AI call, if AI drafted it
      drafted_by: section_labeling/claude-haiku-5-5
      status: draft                 # approval (deferred for now) works exactly as for rules

A label stays a draft; approval (deferred for now, decided 2026-10-19) works exactly as for rules and definitions.
A reviewer who doubts a label adds `open_questions` (which block approval); the architect records the
`answers` (question, answer, answered_by, answered_on) and approves. Both are the same fields rules use.
A reviewer who corrects a label records it in `revised`: [{from: <old label>, by, date, why}], so the
AI's original answer stays visible (and in the run record) and every change is traceable.
"""

import datetime
import hashlib
import json
from pathlib import Path

from .rulebook import (APPROVAL_FIELDS, VOCABULARY_FILE, Context, _approval_problems, _list_of_dicts,
                       _source_problems, load, read_jsonl)

# A reviewer's doubt goes in open_questions (blocks approval); the architect's answer in answers, as for rules.
LABEL_FIELDS = {"label", "topic", "reason", "sources", "piece_sha256", "run", "notes", "open_questions", "answers",
                "revised"}
LABEL_APPROVED = ("id", "label", "topic", "reason", "sources", "piece_sha256", "answers", "revised")
LABEL_KINDS = tuple(load(VOCABULARY_FILE)["label_kinds"])


def piece_fingerprint(piece: dict, pdf_sha256: str) -> str:
    """A piece's identity: which lines of which PDF version. Re-cutting or a new PDF changes it."""
    return hashlib.sha256(json.dumps({"id": piece["id"], "lines": piece["lines"], "pdf": pdf_sha256},
                                     sort_keys=True).encode()).hexdigest()


def load_pieces(path: Path) -> tuple[dict, dict[str, dict]]:
    """The sections file: (header, {piece id: piece})."""
    rows = read_jsonl(path)
    return rows[0], {p["id"]: p for p in rows[1:]}


def validate_labels(book, ctx: Context, header: dict, pieces: dict[str, dict]) -> list[str]:
    """Problems with one document's label file. An empty list means valid."""
    if not (isinstance(book, dict) and book.keys() == {"document", "labels"} and isinstance(book["labels"], dict)):
        return ["file must have exactly 'document' and 'labels' (a mapping of piece id -> label)"]
    name = book["document"]
    if name != header.get("file"):
        return [f"document {name!r} doesn't match the sections file ({header.get('file')!r})"]
    if header.get("sha256") != ctx.sources.get(name, {}).get("sha256"):
        return [f"the sections file was cut from a different version of {name}; re-run python -m document_extraction"]
    problems = []
    for key, entry in book["labels"].items():
        p = _label_problems(key, entry, ctx, pieces, header["sha256"], name)
        problems += [f"{key}: {x}" for x in p]
    return problems


def _label_problems(key, entry, ctx: Context, pieces: dict[str, dict], pdf_sha: str, document: str) -> list[str]:
    if key not in pieces:
        return ["no such piece in the sections file"]
    if not isinstance(entry, dict):
        return ["must be a mapping"]
    p = [f"unknown field '{k}'" for k in entry.keys() - LABEL_FIELDS - APPROVAL_FIELDS]
    p += [f"'{k}' must be text" for k in ("label", "topic", "reason", "run", "drafted_by", "status", "approved_by")
          if k in entry and not isinstance(entry[k], str)]
    if p:
        return p
    if entry.get("label") not in LABEL_KINDS:
        p.append(f"label must be one of {LABEL_KINDS}")
    if entry.get("topic") not in ctx.topics:
        p.append(f"unknown topic {entry.get('topic')!r}")
    if not (entry.get("reason") or "").strip():
        p.append("missing 'reason'")
    if entry.get("piece_sha256") != piece_fingerprint(pieces[key], pdf_sha):
        p.append("the piece changed since it was labeled (re-cut, or a new PDF version); label it again")
    sources = _list_of_dicts(entry, "sources")
    if sources is None:
        p.append("'sources' must be a list of mappings")
    else:
        p += _source_problems(sources, ctx)
        owned = {(pg, n) for pg, first, last in pieces[key]["lines"] for n in range(first, last + 1)}
        for s in sources:
            lines, page = s.get("lines"), s.get("page")
            if s.get("file") != document:
                p.append(f"quote must come from {document}, the document this piece is cut from")
            elif isinstance(lines, list) and len(lines) == 2 and all(type(n) is int for n in lines) \
                    and not {(page, lines[0]), (page, lines[1])} <= owned:
                p.append(f"quote on p.{page} lines {lines} is outside this piece")
    p += _revision_problems(entry.get("revised", []), entry.get("label"))
    return p + _approval_problems(entry | {"id": key}, ctx, LABEL_APPROVED)


def _revision_problems(revised, label) -> list[str]:
    """Changes made after the AI's answer, oldest first. A label change is {from, by, date, why} (the current
    label is the latest); a change to the sources is {field: sources, by, date, why}. The AI's own answer
    stays in the run record, so every difference from it is explained here."""
    if not (isinstance(revised, list) and all(isinstance(r, dict) for r in revised)):
        return ["'revised' must be a list of {from, by, date, why} or {field: sources, by, date, why}"]
    p = []
    for r in revised:
        kind = {"from", "by", "date", "why"} if "from" in r else {"field", "by", "date", "why"}
        if r.keys() != kind:
            p.append("each revision needs exactly from, by, date, why (or field: sources, by, date, why)")
        elif "from" in r and r["from"] not in LABEL_KINDS:
            p.append(f"revised from {r['from']!r}: not a label")
        elif "field" in r and r["field"] != "sources":
            p.append(f"a revision can change the label or the sources, not {r['field']!r}")
        elif not all(isinstance(r[k], str) and r[k].strip() for k in ("by", "why")):
            p.append("a revision's by and why must be text")
        elif not isinstance(r["date"], datetime.date):
            p.append("a revision's date must be a date (YYYY-MM-DD)")
    if not p:                                    # each label change goes from[i] -> the next from, the last -> label
        changes = [r for r in revised if "from" in r]
        targets = [r["from"] for r in changes[1:]] + [label]
        p += [f"revision {i + 1} is from {r['from']!r} to the same label: a revision must change it"
              for i, (r, to) in enumerate(zip(changes, targets)) if r["from"] == to]
    return p