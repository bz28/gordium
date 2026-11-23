"""Each law's contents list, read from the law itself, never typed in: every chapter (or article) and section with
its title as printed, its printed page, and where it was read (PDF page and line), so a results panel can show the
whole book, greyed where Gordium has no rules, and anyone can find each entry again.

    python -m document_extraction contents <jurisdiction folder>           writes 2_extracted_text/<stem>.contents.jsonl
    python -m document_extraction contents <jurisdiction folder> --check   compares with the committed file

Two kinds of source:

- An ICC code book kept outside the repo (layout: icc; the 2025 Building and Residential Codes of New York State):
  its CONTENTS pages, read from the PDF in the code cache with pdfplumber's words. Those pages print two columns of
  entries ("1006 Number of Exits and Exit Access Doorways . . . . 315"); the columns are split at the vertical gap
  no word crosses near the middle of the page (it shifts between odd and even pages), each column read top to
  bottom, and an entry wrapped over two lines joined until its dot leader and printed page end it. Where the cache
  doesn't have the book (CI), it is skipped and says so.
- An ecode360 chapter kept in the repo (Ithaca's Chapter 325): its articles from the body's own headings in the
  extracted text ("ARTICLE II" then its title line), and its sections from the sections file, each in the article
  whose heading comes before it.

Checks, each failure a problem that stops the file being written (never a silent guess): the chapters (or articles)
in sequence; each ICC section's number starts with its chapter's ("1006" in Chapter 10, "R301" in Chapter 3,
"A101" in Appendix A); the printed pages never go down in reading order; and every section the folder's sections
file brings in ("1006.2.1" is in 1006) is in the contents.

Plain code, no AI, no judgment: the same PDF always gives the same file.
"""

import json
import re
from pathlib import Path

import pdfplumber

MADE_BY = "document_extraction.contents v1"
LINE_TOL = 2.0                         # points: words this close in height are on one line
GUTTER_SPAN = (200.0, 412.0)           # where on a 612-point page the gap between the two columns is looked for
STAMP = re.compile(r"^\d{6,}$")        # the per-copy number stamped at the top of every page
FOOT = re.compile(r"^(?:\d{4} [A-Z ]+CODE OF NEW YORK STATE [IVXLC]+|[IVXLC]+ \d{4} [A-Z ]+CODE OF NEW YORK STATE)$")
LEADER = re.compile(r"^(.*?)[\s.]*?(\d+)$")      # an entry's end: its title, then dots, then the printed page
DASH = r"\s*[—–-]?\s*"                   # "R101—Scope", "APPENDIX A— EMPLOYEE", "1006 Number of"
CHAPTER = re.compile(r"^CHAPTER (\d+)" + DASH + r"(.*)$")
APPENDIX = re.compile(r"^APPENDIX ([A-Z]{1,2})(?![A-Za-z])" + DASH + r"(.*)$")
PART = re.compile(r"^PART ([IVXLC]+)(?![A-Za-z])" + DASH + r"(.*)$", re.IGNORECASE)
RESOURCE = re.compile(r"^RESOURCE ([A-Z])(?![A-Za-z])" + DASH + r"(.*)$")
SECTION = re.compile(r"^([A-Z]{0,2}\d{3,4})(?![\d.])" + DASH + r"(.*)$")
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


# ---- an ICC book's CONTENTS pages ----------------------------------------------------------------------------------

def _roman(s: str) -> int:
    total = 0
    for a, b in zip(s, s[1:] + " "):
        v = ROMAN[a]
        total += -v if b != " " and ROMAN.get(b, 0) > v else v
    return total


def gutter(words: list[dict], span: tuple = GUTTER_SPAN) -> float | None:
    """The x of the gap between the two columns: the middle of the widest stretch within `span` that no word
    crosses, or None when every point of it is crossed (one column, or words across the middle)."""
    covered = sorted((w["x0"], w["x1"]) for w in words if w["x1"] > span[0] and w["x0"] < span[1])
    best, at, x = 0.0, None, span[0]
    for a, b in covered + [(span[1], span[1])]:
        if a > x and a - x > best:
            best, at = a - x, (x + a) / 2
        x = max(x, b)
    return at if best >= 4.0 else None


def column_lines(words: list[dict]) -> list[dict]:
    """The words as lines, top to bottom: {text, top}."""
    lines = []
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        if lines and abs(lines[-1]["top"] - w["top"]) <= LINE_TOL:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    return [{"top": ln["top"], "text": " ".join(x["text"] for x in sorted(ln["words"], key=lambda w: w["x0"]))}
            for ln in lines]


def _start(text: str):
    """(kind, number, rest) when a line starts an entry, else None."""
    for kind, rx in (("chapter", CHAPTER), ("appendix", APPENDIX), ("part", PART), ("resource", RESOURCE)):
        if m := rx.match(text):
            return kind, m.group(1).upper() if kind == "part" else m.group(1), m.group(2)
    if text == "INDEX" or text.startswith("INDEX "):
        return "index", "INDEX", text[5:].strip()
    if (m := SECTION.match(text)) and m.group(2).strip(" ."):    # a page number alone ("395") ends an entry
        return "section", m.group(1), m.group(2)
    return None


def _end(text: str):
    """(title, printed page) when the text ends an entry (its dot leader and page), else None."""
    m = LEADER.match(text)
    if not m:
        return None
    return " ".join(m.group(1).rstrip(" .").split()), int(m.group(2))


def entries(lines: list[dict]) -> tuple[list[dict], list[str]]:
    """The entries of the lines in reading order ({page, line, text} each), and the problems: each entry from the
    line that starts it to the line its printed page ends it on (a wrapped title joined with a space). A part heading
    has no page; any other entry that never ends is a problem."""
    out, problems, open_ = [], [], None

    def close(title=None, page=None):
        nonlocal open_
        e = open_
        if title is None:
            title = " ".join(e["text"].split())
            if e["kind"] not in ("part",):
                problems.append(f"p.{e['page']} line {e['line']}: {e['kind']} {e['number']} has no printed page "
                                f"(“{title[:60]}”)")
        out.append({"kind": e["kind"], "number": e["number"], "title": title, "book_page": page,
                    "page": e["page"], "line": e["line"]})
        open_ = None
    for ln in lines:
        text = ln["text"].strip()
        started = _start(text)
        if started and open_ is not None:
            close()
        if started:
            kind, number, rest = started
            open_ = {"kind": kind, "number": number, "text": rest, "page": ln["page"], "line": ln["line"]}
        elif open_ is not None:
            open_["text"] += " " + text
        else:
            problems.append(f"p.{ln['page']} line {ln['line']}: “{text[:60]}” starts no entry and follows none")
            continue
        if (ended := _end(open_["text"])) and (ended[0] or open_["kind"] == "index"):
            close(ended[0] or "INDEX", ended[1])
    if open_ is not None:
        close()
    return out, problems


def _numbered(rows: list[dict]) -> list[dict]:
    """Each section in its chapter (or appendix): `chapter` set to the one before it."""
    chapter = None
    for r in rows:
        if r["kind"] in ("chapter", "appendix"):
            chapter = r["number"]
        elif r["kind"] == "section":
            r["chapter"] = chapter
    return rows


def contents_pages(pdf) -> list[int]:
    """The pages (1-based) headed CONTENTS (the first word under the stamp)."""
    found = []
    for n, page in enumerate(pdf.pages, 1):
        if n > 60 and found:
            break
        words = [w for w in page.extract_words() if not STAMP.match(w["text"])][:1]
        if words and words[0]["text"] == "CONTENTS":
            found.append(n)
        page.close()
    return found


def _page_lines(page, number: int, numbered: list[dict]) -> tuple[list[dict], list[str]]:
    """A CONTENTS page's lines, left column then right, furniture left out, each with the PDF line (of the book's
    own line numbering, icc.extract_icc's) it is on."""
    words = page.dedupe_chars().extract_words()
    words = [w for w in words if not STAMP.match(w["text"])]
    lines = column_lines(words)
    drop = {round(ln["top"], 1) for ln in lines if FOOT.match(ln["text"]) or ln["text"] in ("CONTENTS", ".")}
    words = [w for w in words if not any(abs(w["top"] - t) <= LINE_TOL for t in drop)]
    x = gutter(words)
    if x is None:
        return [], [f"p.{number}: no gap between two columns found"]
    out = []
    for side in ([w for w in words if w["x1"] <= x], [w for w in words if w["x0"] >= x]):
        for ln in column_lines(side):
            near = min(numbered, key=lambda r: abs(r["top"] - ln["top"])) if numbered else None
            out.append({"page": number, "line": near["line"] if near else None, "text": ln["text"]})
    return out, []


def read_icc(pdf_path: Path) -> tuple[list[int], list[dict], list[str]]:
    """(the CONTENTS pages, their entries, the problems)."""
    from .icc import extract_icc
    with pdfplumber.open(pdf_path) as pdf:
        pages = contents_pages(pdf)
    if not pages:
        return [], [], ["no page headed CONTENTS"]
    numbered = extract_icc(pdf_path, pages)[1:]
    lines, problems = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for n in pages:
            got, bad = _page_lines(pdf.pages[n - 1], n, [r for r in numbered if r["page"] == n])
            lines += got
            problems += bad
    rows, bad = entries(lines)
    return pages, _numbered(rows), problems + bad


def checks_icc(rows: list[dict], sections: list[str]) -> list[str]:
    """The checks on an ICC book's entries (the module's note)."""
    problems = []
    chapters = [int(r["number"]) for r in rows if r["kind"] == "chapter"]
    if chapters != list(range(1, len(chapters) + 1)):
        problems.append(f"the chapters aren't 1 to {len(chapters)} in order: {chapters}")
    for r in rows:
        if r["kind"] != "section":
            continue
        letters, digits = re.match(r"([A-Z]*)(\d+)", r["number"]).groups()
        ch = r.get("chapter")
        ok = (ch is not None and (digits[:-2] == ch if ch.isdigit() else letters == ch))
        if not ok:
            problems.append(f"p.{r['page']} line {r['line']}: section {r['number']} isn't in its chapter ({ch})")
    problems += _pages_rise(rows) + _all_listed(rows, sections)
    return problems


def _pages_rise(rows: list[dict]) -> list[str]:
    """Printed pages never go down in reading order. A part heading's page isn't held to it: its row says so instead
    (`note`), the page kept as printed (the RCNYS prints Part III at page 535, its Chapter 3 at 35)."""
    problems, last = [], None
    for k, r in enumerate(rows):
        if r["book_page"] is None:
            continue
        if r["kind"] == "part":
            after = next((x for x in rows[k + 1:] if x["book_page"] is not None), None)
            if after is not None and after["book_page"] < r["book_page"]:
                r["note"] = (f"printed as page {r['book_page']}, after the page of the {after['kind']} it heads "
                             f"({after['number']}, page {after['book_page']}): kept as printed")
            continue
        if last is not None and r["book_page"] < last[0]:
            problems.append(f"p.{r['page']} line {r['line']}: {r['kind']} {r['number']} prints page {r['book_page']}, "
                            f"before page {last[0]} of {last[1]}")
        last = (r["book_page"], r["number"])
    return problems


def section_of(piece_id: str) -> str | None:
    """The contents section a sections-file piece is in (rule_format.labels.contents_section: the one rule)."""
    from rule_format.labels import contents_section
    return contents_section(piece_id)


def _all_listed(rows: list[dict], sections: list[str]) -> list[str]:
    have = {r["number"] for r in rows if r["kind"] == "section"}
    missing = sorted({s for s in (section_of(p) for p in sections) if s and s not in have})
    return [f"section {s} is brought in (2_extracted_text's sections file) but not in the contents" for s in missing]


# ---- an ecode360 chapter kept in the repo (Chapter 325) ------------------------------------------------------------

ARTICLE = re.compile(r"^ARTICLE ([IVXLC]+A?)$")
# a section heading's footnote mark ("[fn24]") and its history note ("[Added 5-7-2025 by Ord. No. 2025-04]", cut off
# where the heading line ends: "[Added 10-6-2021 by Ord."), neither part of its title
NOTE_MARK = re.compile(r"\[fn\d+\]")
HISTORY = re.compile(r"\s*\[(?:Added|Amended) .*$")


def heading(printed: str) -> str:
    """A zoning section's title from its heading line: "Accessory Dwelling Units (ADUs)." from "Accessory Dwelling
    Units (ADUs).[fn24] [Added 5-7-2025 by Ord. No. 2025-04]"."""
    return " ".join(NOTE_MARK.sub("", HISTORY.sub("", printed)).split())


def read_ecode360(text_rows: list[dict], pieces: list[dict]) -> tuple[list[int], list[dict], list[str]]:
    """(the pages the articles' headings are on, the entries, the problems): each article heading in the body
    (after the front matter's own contents pages), its title the next line, and the sections file's sections in
    book order, each in the article whose heading comes before its first line."""
    body = [r for r in text_rows if r["page"] > 2]
    articles = []
    for a, b in zip(body, body[1:]):
        if m := ARTICLE.match(a["text"].strip()):
            articles.append({"kind": "article", "number": m.group(1), "title": " ".join(b["text"].split()),
                             "book_page": None, "page": a["page"], "line": a["line"]})
    rows, problems = [], []
    secs = [p for p in pieces if p.get("kind") == "section"]
    k = 0
    for s in secs:
        page, line = s["lines"][0][0], s["lines"][0][1]
        while k < len(articles) and (articles[k]["page"], articles[k]["line"]) <= (page, line):
            rows.append(articles[k])
            k += 1
        if not rows or not any(r["kind"] == "article" for r in rows):
            problems.append(f"§{s['id']} comes before any article")
        art = next((r["number"] for r in reversed(rows) if r["kind"] == "article"), None)
        printed = " ".join(s["title"].split())
        row = {"kind": "section", "number": s["id"], "title": heading(printed), "chapter": art, "book_page": None,
               "page": page, "line": line}
        if row["title"] != printed:
            row["printed"] = printed       # the heading line whole, its footnote mark and history note in it
        rows.append(row)
    rows += articles[k:]
    order = [_roman(a["number"].rstrip("A")) + (0.5 if a["number"].endswith("A") else 0) for a in articles]
    if order != sorted(order) or len(set(order)) != len(order):
        problems.append(f"the articles aren't in order: {[a['number'] for a in articles]}")
    for s in rows:
        if s["kind"] == "section" and not re.match(r"325-\d+", s["number"]):
            problems.append(f"section {s['number']} isn't a section of Chapter 325")
    return sorted({a["page"] for a in articles}), rows, problems


# ---- one folder ---------------------------------------------------------------------------------------------------

def to_jsonl(header: dict, rows: list[dict]) -> str:
    return "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in [header, *rows])


def build(jurisdiction: Path) -> tuple[Path | None, str | None, list[str], str | None]:
    """(the contents file's path, its text, the problems, why it was skipped): for the folder's one code book, or
    its ecode360 chapter."""
    import yaml
    from rule_format.rulebook import cached, read_jsonl

    from .extract import sha256
    docs = yaml.safe_load((jurisdiction / "1_source_documents" / "sources.yaml").read_text(encoding="utf-8"))["documents"]
    doc = next((d for d in docs if d.get("layout") == "icc" and d.get("kept_outside_repo") is True), None) or \
        next((d for d in docs if d.get("layout") == "ecode360"), None)
    if doc is None:
        return None, None, [], "no ICC book or ecode360 chapter in its sources.yaml"
    stem = Path(doc["file"]).stem
    out_dir = jurisdiction / "2_extracted_text"
    path = out_dir / f"{stem}.contents.jsonl"
    sections_file = out_dir / f"{stem}.sections.jsonl"
    pieces = read_jsonl(sections_file)[1:] \
        if sections_file.exists() else []
    if doc.get("layout") == "icc":
        pdf = cached(doc)
        if not pdf.exists():
            return path, None, [], "kept outside the repo and not in the code cache here"
        if sha256(pdf) != doc["sha256"]:
            return path, None, ["the cached copy's fingerprint doesn't match sources.yaml"], None
        pages, rows, problems = read_icc(pdf)
        problems += checks_icc(rows, [p["id"] for p in pieces if p.get("kind") in ("section", "table",
                                                                                  "section_heading")])
        source = "pdf"
    else:
        text = out_dir / f"{stem}.jsonl"
        text_rows = read_jsonl(text)[1:]
        pages, rows, problems = read_ecode360(text_rows, pieces)
        source = f"2_extracted_text/{text.name} + {sections_file.name}"
    header = {"file": doc["file"], "sha256": doc["sha256"], "made_by": MADE_BY, "pages": pages, "source": source,
              "chapters": sum(r["kind"] in ("chapter", "article") for r in rows),
              "sections": sum(r["kind"] == "section" for r in rows), "problems": problems}
    return path, to_jsonl(header, rows), problems, None


def main(argv: list[str], repo: Path) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python -m document_extraction contents")
    parser.add_argument("folder", help="a jurisdiction folder (regulations/jurisdictions/<state>/<place>)")
    parser.add_argument("--check", action="store_true", help="compare with the committed file; write nothing")
    args = parser.parse_args(argv)
    folder = Path(args.folder)
    folder = folder if folder.is_absolute() else (Path.cwd() / folder)
    path, text, problems, skipped = build(folder.resolve())
    label = path.relative_to(repo).as_posix() if path is not None and path.is_relative_to(repo) else str(path)
    if skipped:
        print(f"– {label}: {skipped}; not made or checked (checked where it can be)")
        return 0
    if problems:
        for p in problems:
            print(f"✗ {p}")
        return 1
    if args.check:
        same = path.exists() and path.read_text(encoding="utf-8") == text
        print(f"{'✓' if same else '✗'} {label}{'' if same else ': differs from a fresh reading'}")
        return 0 if same else 1
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {label} ({text.count(chr(10)) - 1} entries)")
    return 0
