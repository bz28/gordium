"""Cut a city code chapter's extracted text into pieces at the code's own headings, so each piece can
be labeled. Written for the eCode360 layout (layout: ecode360 in sources.yaml), which most US city
codes use; another layout needs its own rules.

Plain code, no AI: the same extracted text always gives the same pieces. Every line ends up in
exactly one place: a piece, or page furniture (the line repeated at the top of every page, e.g.
"City of Ithaca, NY"; the running header "§ 325-3 ZONING § 325-3"; the "Downloaded from ..." footer),
which carries no law.

Pieces, in reading order:
  - front matter: everything before the first article heading followed by section 1 (the table of
    contents and history)
  - one piece per section ("§ 325-16. Height regulations."), with an article heading ("ARTICLE V",
    its title and amendment history) attached to the section that follows it
  - a section with lettered subsections is cut at each one (325-16A, 325-16B, ...)
  - in a section titled "Definitions...", each defined term ("ALLEY — ...") starts a piece: 325-3B:alley
  - editor's notes (page-bottom footnotes "2. Editor's Note: ...") are pieces of their own

Guards against false headings (body text that happens to look like one):
  - a section or subsection heading starts at the headings' margin (the left edge every real heading
    shares, measured from the document). Text inside a subsection is indented further, so a wrapped
    line there that starts "§ 325-45. ..." or "B. below ..." can't be a heading
  - a subsection's own text is indented past the margin, while a section's own text keeps wrapping at
    the margin: so a subsection heading must be followed by an indented line or another heading. A
    margin line "A. ..." followed by more margin text is a section's wrapped sentence, and is reported
  - section numbers must increase, and subsection letters must come in order (A, then B, ...)
  - a line at the margin that looks like a heading but breaks that order is reported as a problem, never
    silently skipped: if a wrapped "A. ..." had opened a false subsection, the real "A." after it is
    the one reported
  - a defined term is mostly capitals before its dash ("DOORS and ENTRIES —"), inside a Definitions section
  - every section listed in the document's own table of contents must be found, and no other
All problems go in the sections file's header and fail CI (python -m section_labeling coverage --check).

Each piece: {id, title, kind, lines: [[page, first, last], ...]}; kind is "front_matter", "section",
"subsection", "definition" or "editors_note". `lines` lists the runs of lines the piece owns (an editor's
note at a page bottom is cut out of the section around it). Furniture lines are listed in the header.
"""

import json
import re
from collections import Counter
from pathlib import Path

HEADER = re.compile(r"^§ \d+-[\d.]+ [A-Z][A-Z ]+ § \d+-[\d.]+$")
FOOTER = re.compile(r"^Downloaded from https://ecode360\.com/")
ARTICLE = re.compile(r"^ARTICLE [IVXL]+[A-Z]?$")
SECTION = re.compile(r"^§ (\d+)-(\d+(?:\.\d+)*)\. (\S.*)$")
SUBSECTION = re.compile(r"^([A-Z])\. (.*)$")
TERM = re.compile(r"^(?:\(\d+\) )?([A-Z][^—]*?) —( |$)")   # then _is_term() checks it's mostly capitals
TOC_ENTRY = re.compile(r"§ (\d+)-(\d+(?:\.\d+)*)\.( through § \d+-(\d+(?:\.\d+)*)\.)?")
SPLITTER = "document_extraction.sections v2"   # bump when the cutting rules change
MARGIN = 1.0   # points: how far a heading may sit from the headings' margin
NOTE = re.compile(r"^(\d+)\. Editor['’]s Note:")


def _furniture(rows_on_page: list[dict], top: str) -> set[int]:
    """Line numbers on one page that are repeated page furniture, not law. `top` is the line printed
    first on most pages (the municipality's name)."""
    return {r["line"] for r in rows_on_page if r["line"] == 1 and r["text"] == top
            or r["line"] == 2 and HEADER.match(r["text"]) or FOOTER.match(r["text"])}


def _slug(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _bare(term).lower()).strip("_")


def _bare(term: str) -> str:
    """A term without its parenthetical asides: "TYPE I – IV APPLICATIONS (see, e.g., ...)" -> "TYPE I – IV APPLICATIONS"."""
    return re.sub(r"\s*\([^)]*\)", "", term).strip()


def _is_term(term: str) -> bool:
    """A defined term is written in capitals, allowing short lowercase joining words ("DOORS and ENTRIES")."""
    letters = [c for c in _bare(term) if c.isalpha()]
    first = _bare(term).split()[0] if _bare(term) else ""
    return bool(letters) and first.isupper() and sum(c.isupper() for c in letters) >= 0.7 * len(letters)


def split(rows: list[dict]) -> dict:
    """rows: the extracted text (header row first).
    Returns {"pieces": [...], "furniture": [[page, line], ...], "problems": [...]}."""
    body, furniture = [], []
    pages: dict[int, list[dict]] = {}
    for r in rows[1:]:
        pages.setdefault(r["page"], []).append(r)
    firsts = Counter(pages[p][0]["text"] for p in pages if pages[p][0]["line"] == 1)
    top, count = firsts.most_common(1)[0]
    top = top if count > len(pages) / 2 else None          # only a line on most pages is furniture
    for page in sorted(pages):
        skip = _furniture(pages[page], top)
        furniture += [[page, n] for n in sorted(skip)]
        body += [r for r in pages[page] if r["line"] not in skip]

    # Editor's notes sit at the bottom of a page: from the note's first line to the page's last body line.
    in_note, note_of = None, {}
    for r in body:
        if NOTE.match(r["text"]):
            in_note = (r["page"], NOTE.match(r["text"])[1])
        elif in_note and in_note[0] != r["page"]:
            in_note = None
        if in_note:
            note_of[(r["page"], r["line"])] = in_note

    # The law starts at the first ARTICLE heading followed (within a few lines) by section 1
    # ("§ 325-1. Title."): everything before is the table of contents and history.
    def section_one(x):
        m = SECTION.match(x["text"])
        return m and m[2] == "1"
    start = next(i for i, r in enumerate(body) if ARTICLE.match(r["text"]) and any(map(section_one, body[i:i + 4])))
    chapter = next(SECTION.match(x["text"])[1] for x in body[start:] if section_one(x))
    # The headings' margin: where the section and subsection headings start (most of them, by far).
    margin = Counter(round(r["x0"], 1) for r in body[start:]
                     if SECTION.match(r["text"]) or SUBSECTION.match(r["text"])).most_common(1)[0][0]
    at_margin = lambda r: abs(r["x0"] - margin) <= MARGIN

    pieces: list[dict] = []
    def open_piece(pid, title, kind):
        pieces.append({"id": pid, "title": title, "kind": kind, "members": []})

    notes: dict[tuple, dict] = {}
    problems: list[str] = []
    open_piece("front_matter", "Table of contents and history", "front_matter")
    section = letter = None
    definitions = False
    number: tuple = ()                            # the current section's number, e.g. (29, 10, 2)
    pending: list[tuple] = []                     # article heading lines waiting for their section
    for i, r in enumerate(body):
        key = (r["page"], r["line"])
        if i < start:
            pieces[-1]["members"].append(key)
            continue
        if key in note_of:
            note_no = note_of[key][1]
            notes.setdefault(note_of[key], {"id": f"editors_note_{note_no}", "title": f"Editor's Note {note_no}",
                                            "kind": "editors_note", "members": []})["members"].append(key)
            continue
        text = r["text"]
        m = SECTION.match(text) if at_margin(r) else None
        # A real heading numbers above the section before it.
        if m and (m[1] != chapter or tuple(int(x) for x in m[2].split(".")) <= number):
            problems.append(f"p.{r['page']} line {r['line']}: looks like a section heading but doesn't follow "
                            f"{section}; check how this part was cut")
            m = None
        if ARTICLE.match(text) or (pending and not m):
            pending.append(key)
            continue
        if m:
            number = tuple(int(x) for x in m[2].split("."))
            section, letter, definitions = f"{chapter}-{m[2]}", None, m[3].startswith("Definitions")
            open_piece(section, re.sub(r"\s*\[Amended.*$", "", m[3]).strip(), "section")   # title without history
            pieces[-1]["members"] += pending
            pending = []
        elif (s := SUBSECTION.match(text)) and section and at_margin(r):
            expected = "A" if letter is None else chr(ord(letter) + 1)
            nxt = body[i + 1] if i + 1 < len(body) else None
            if nxt and at_margin(nxt) and not any(p.match(nxt["text"]) for p in (SECTION, SUBSECTION, ARTICLE, NOTE)):
                problems.append(f"p.{r['page']} line {r['line']}: looks like subsection {s[1]} of {section} but the "
                                "text after it isn't indented like a subsection's; check how this part was cut")
            elif s[1] == expected:
                letter = s[1]
                open_piece(f"{section}{letter}", s[2].split(".")[0].strip(), "subsection")
            else:
                problems.append(f"p.{r['page']} line {r['line']}: looks like subsection {s[1]} of {section} but "
                                f"{expected} was expected; check how this part was cut")
        elif definitions and (t := TERM.match(text)) and _is_term(t[1]):
            open_piece(f"{section}{letter or ''}:{_slug(t[1])}", _bare(t[1]), "definition")
        pieces[-1]["members"].append(key)
    pieces[-1]["members"] += pending              # an article heading with no section after it stays inside
    pieces += sorted(notes.values(), key=lambda n: (n["members"][0], n["id"]))
    _dedupe_ids(pieces)
    for p in pieces:
        p["lines"] = _ranges(p.pop("members"))
    return {"pieces": pieces, "furniture": furniture, "problems": problems + _toc_problems(body[:start], pieces, chapter)}


def _toc_problems(front: list[dict], pieces: list[dict], chapter: str) -> list[str]:
    """Sections the table of contents lists but no piece starts, and the reverse. A reserved range
    ("§ 325-30. through § 325-31. (Reserved)") is one heading."""
    listed, covered = set(), set()
    for m in TOC_ENTRY.finditer(" ".join(r["text"] for r in front)):
        if m[1] == chapter:
            listed.add(m[2])
            if m[4]:
                covered.add(m[4])
    found = {p["id"].removeprefix(f"{chapter}-") for p in pieces if p["kind"] == "section"}
    return ([f"§ {chapter}-{n} is in the table of contents but no section starts with it" for n in sorted(listed - found - covered)]
            + [f"§ {chapter}-{n} starts a section but isn't in the table of contents" for n in sorted(found - listed)])


def _ranges(members: list[tuple]) -> list[list[int]]:
    """[(page, line), ...] in reading order -> [[page, first, last], ...]: one run of consecutive lines per entry."""
    out: list[list[int]] = []
    for page, line in members:
        if out and out[-1][0] == page and out[-1][2] == line - 1:
            out[-1][2] = line
        else:
            out.append([page, line, line])
    return out


def _dedupe_ids(pieces: list[dict]) -> None:
    """Ids must be unique; a repeated id (an editor's note number reused, a term defined twice) gets :2, :3."""
    seen: dict[str, int] = {}
    for p in pieces:
        seen[p["id"]] = seen.get(p["id"], 0) + 1
        if seen[p["id"]] > 1:
            p["id"] = f"{p['id']}:{seen[p['id']]}"


def piece_keys(piece: dict) -> list[tuple[int, int]]:
    """Every (page, line) of a piece, in reading order."""
    return [(page, n) for page, first, last in piece["lines"] for n in range(first, last + 1)]


def piece_text(rows: list[dict], piece: dict) -> str:
    """A piece's text, one extracted line per line, with a marker at each page break."""
    text = {(r["page"], r["line"]): r["text"] for r in rows[1:]}
    out, page = [], None
    for key in piece_keys(piece):
        if page is not None and key[0] != page:
            out.append(f"[page {key[0]}]")
        page = key[0]
        out.append(text[key])
    return "\n".join(out)


def to_jsonl(result: dict, header: dict) -> str:
    """A header naming the extracted text it came from (file and PDF fingerprint), then one piece per line."""
    head = {"file": header["file"], "sha256": header["sha256"], "splitter": SPLITTER,
            "pieces": len(result["pieces"]), "problems": result["problems"], "furniture": result["furniture"]}
    return "\n".join(json.dumps(x, ensure_ascii=False) for x in [head, *result["pieces"]]) + "\n"

