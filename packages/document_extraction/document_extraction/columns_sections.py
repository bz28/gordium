"""Cut the brought-in parts of a two-column code book (layout: two_column in sources.yaml) into pieces at the book's
own headings, so each piece can be labeled: the 2009 International Building Code (style ibc_2009, a scan read by
OCR) and NFPA 101, Life Safety Code, 2012 edition (style nfpa_101_2012). icc_sections.py does this for the 2025
Residential Code of New York State; this module keeps its rules and its output (the same sections file), with each
book's own headings, furniture and definitions.

Plain code, no AI: the same extracted text and the same sources.yaml `brought_in` always give the same pieces.

What is brought in (sources.yaml `brought_in`): the pages read (`pages`); the sections and numbered parts
(`sections`, each with everything under it; `alone`, without the parts under it); and the definitions, found by code,
never picked by hand: every definition a brought-in piece uses, then the definitions those use.
- **IBC 2009:** "Selected terms set forth in Chapter 2, Definitions, are italicized where they appear in code text"
  (the book's preface, "Italicized Terms"), and 201.1 gives Chapter 2's meanings to "the following words and terms";
  so a piece's italic words name the definitions it uses, as in New York's book. Chapter 2 points many terms to the
  section that defines them ("EXIT ACCESS. See Section 1002.1."): both the pointer and the definition it points to
  are brought in (the italic word names both). A defined term printed in roman type comes in too (never fewer). An
  italic word no definition on the pages read names is a problem unless `italic_not_defined` names it, with why.
- **NFPA 101 2012:** the book marks no defined word (no italics); 3.1 gives Chapter 3's definitions to "the terms
  used in this Code". So every definition whose term a brought-in piece prints is used, and so are those its own
  text prints.

Where a piece starts:
- IBC 2009, a scan with no bold in its text layer: a line that starts with a section heading ("SECTION 1015"), a
  numbered part in order with its title ("1015.2.1 Two exits or exit access doorways."), or, in a section or part of
  definitions (202 DEFINITIONS; "1002.1 Definitions."), a term in capitals followed by a period ("EXIT ACCESS.").
  Without bold, a wrapped line of body text can look like a heading ("1015.2.1 and 1015.2.2."): a numbered part
  must be the next in order (icc_sections._in_order) and its title must start with a capital, and a line that
  looks like a numbered part but is out of order is a problem, never silently skipped, unless
  `not_headings` names its line with why (each checked on the page image).
- NFPA 101 2012: a line that starts in bold, with a chapter ("Chapter 16 New Day-Care Occupancies") or a numbered
  part ("16.2.5.3", "16.2.2.2.4* Door Latches.": the asterisk points to the annex, which is no law); a numbered part
  of section 3.3 is a definition, its title the term ("3.3.31 Common Path of Travel.").

Every line of every page read ends up in exactly one place: a piece, page furniture, or a part not brought in
(the header's `outside`). Problems go in the sections file's header and fail CI.
"""

import json
import re
from dataclasses import dataclass

from . import icc_sections
from .icc_sections import (LOOSE_FRACTION, _forms, _in_order, _roman, _runs_of, italic_phrases, parse_pages,
                           slug, text_fingerprint)

SPLITTER = "document_extraction.columns_sections v1"   # bump when the cutting rules change
__all__ = ["split", "to_jsonl", "parse_pages", "STYLES", "SPLITTER"]


@dataclass(frozen=True)
class Style:
    """One book's printing: its furniture, its headings and how it marks its defined words."""
    furniture: tuple                 # patterns of whole lines that are page furniture (each in reading order on a page)
    section: re.Pattern | None       # a section's or chapter's heading: group 1 its number, group 2 its title (if any)
    numbered: re.Pattern             # a numbered part's heading: group 1 its number, group 2 its title and text
    bold_headings: bool              # headings are printed in bold, and the text layer says so
    italic_terms: bool               # the book prints its defined words in italics
    term: re.Pattern | None          # a defined term in capitals at a line's start (books that define so)
    definitions_titles: tuple        # the titles of a section or numbered part of definitions
    numbered_definitions: str | None  # the numbered section whose parts are definitions, their title the term ("3.3")
    running_head: re.Pattern | None  # a running head, wherever on the page reading order puts it
    table: re.Pattern | None = None  # a table's title line (in bold, where headings are)


STYLES = {
    "ibc_2009": Style(
        furniture=(re.compile(r"^(?:\d{1,3} )?2009 INTERNATIONAL BUILDING CODE\W?(?: \d{1,3})?$"),
                   re.compile(r"^\d{1,3}$"),                 # the page number, printed apart from the footer
                   re.compile(r"^[Il|](?: [Il|])*$")),    # change bars in the margin, read by the OCR as letters
        section=re.compile(r"^SECTION (\d{3,4})(?: (\S.*))?$"),
        numbered=re.compile(r"^(\d{3,4}(?:\.\d+)+) ([A-Z].*)$"),
        bold_headings=False, italic_terms=True,
        # (a change bar in the margin, which the OCR reads as "I" and joins to the line: "I FLIGHT. See Section
        # 1002.1.", is no part of the term)
        term=re.compile(r"^(?:[Il|] )?(?:\[[A-Z]{1,2}\] )?([A-Z0-9](?:[^.(]|\([^)]*\))*?)\.(?: |$)"),
        definitions_titles=("DEFINITIONS", "Definitions", "Definition"),
        numbered_definitions=None,
        running_head=None,
        table=re.compile(r"^TABLE \d{3,4}(?:\.\d+)+$")),
    "nfpa_101_2012": Style(
        furniture=(re.compile(r"^Posted by Public\.Resource\.Org\. Not affiliated with NFPA$"),
                   re.compile(r"^\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}$"),   # licence number
                   re.compile(r"^2012 Edition$"),
                   re.compile(r"^101\W\d{1,3}$")),            # a page number printed on its own (a page of tables)
        section=re.compile(r"^Chapter (\d{1,2}) (\S.*)$"),
        numbered=re.compile(r"^(\d{1,2}(?:\.\d+)+)\*? ?(.*)$"),
        bold_headings=True, italic_terms=False, term=None,
        definitions_titles=(),
        numbered_definitions="3.3",
        running_head=re.compile(r"^(?:101\W\d{1,3} [A-Z][A-Z ,;&–—-]+|[A-Z][A-Z ,;&–—-]+ 101\W\d{1,3})$"),
        table=re.compile(r"^Table \d+(?:\.\d+)+(?:\([a-z]\))? [A-Z]")),
}


def number(code: str) -> tuple:
    """'1015.2.1' -> (1015, 2, 1); '16.2.5.3' -> (16, 2, 5, 3)."""
    return tuple(int(x) for x in code.split("."))


def _bold_start(r: dict) -> str | None:
    runs = r.get("bold") or []
    return r["text"][runs[0][0]:runs[0][1]] if runs and runs[0][0] == 0 else None


def _title(rest: str) -> str:
    """A numbered part's title: its words up to the first period ("Two exits or exit access doorways")."""
    return rest.split(". ")[0].rstrip(".").strip()


def furniture(rows_on_page: list[dict], style: Style, heads: set[str]) -> set[int]:
    """Line numbers on one page that are page furniture, not law. A line that reads as a running head right under a
    section's heading is that section's title ("SECTION 202" then "DEFINITIONS", the running head of the pages
    after it), never furniture."""
    out = set()
    before = ""
    for r in rows_on_page:
        t = r["text"]
        title = style.section is not None and bool(style.section.match(before))
        if any(p.match(t) for p in style.furniture) or (t in heads and not title) \
                or (style.running_head is not None and style.running_head.match(t)):
            out.add(r["line"])
        before = t
    return out


def split(rows: list[dict], brought_in: dict, style_name: str) -> dict:
    """rows: the extracted text (header row first) of the pages read, the OCR's misreads put right
    (book_text.as_printed). brought_in: sources.yaml's. Returns {"pieces", "furniture", "outside", "line_counts",
    "problems"}, as icc_sections.split."""
    style = STYLES[style_name]
    pages: dict[int, list[dict]] = {}
    for r in rows[1:]:
        pages.setdefault(r["page"], []).append(r)
    problems: list[str] = []
    wanted = parse_pages(brought_in["pages"])
    if sorted(pages) != wanted:
        problems.append(f"the extracted text has pages {sorted(pages)}, not the pages brought in ({brought_in['pages']})")
    # A running head: an all-capitals line printed on two pages or more (the chapter's title, IBC)
    # (the first line of two pages or more: in the text's order the head may also fall at the top of the right column)
    seen: dict[str, int] = {}
    for p in pages.values():
        for t in {r["text"] for r in p if r["line"] == 1}:
            seen[t] = seen.get(t, 0) + 1
    heads = {t for t, n in seen.items() if n >= 2 and t.isupper() and not style.section.match(t)
             and not style.numbered.match(t) and len(t.split()) <= 8} if style.running_head is None else set()
    furn, body = [], []
    for page in sorted(pages):
        skip = furniture(pages[page], style, heads)
        furn += [[page, n] for n in sorted(skip)]
        body += [r for r in pages[page] if r["line"] not in skip]

    not_headings = brought_in.get("not_headings") or {}     # "p.266 line 34": why the line is no heading
    used_names: set[str] = set()
    # A table's lines, named in sources.yaml (`tables`: "Table 1016.1": "p.267 lines 56-104", each checked on the page
    # image): the text layer doesn't say where a table ends, and the book prints a table where it fits, with the
    # text around it running on past it. So a table is a piece of its own, its lines exactly those named, and the
    # lines after it go on with the part the table interrupts.
    in_table: dict[tuple[int, int], str] = {}
    for tid, spec in (brought_in.get("tables") or {}).items():
        # "p.267 lines 56-104", or where the text runs between a table's title and its rows, or a table runs on
        # over a page: "p.180 lines 21, 39-103; p.181 lines 1-12"
        parts = [re.fullmatch(r"p\.(\d+) lines (\d+(?:-\d+)?(?:, \d+(?:-\d+)?)*)", s.strip())
                 for s in str(spec).split(";")]
        if not all(parts) or not str(tid).startswith("Table "):
            problems.append(f"brought_in.tables: {tid}: {spec!r} must read 'p.<page> lines <first>-<last>'")
            continue
        for m in parts:
            for k in parse_pages(m[2]):
                in_table[(int(m[1]), k)] = str(tid)
    units: list[dict] = []
    current = -1                         # the unit lines go to: never a table
    section = None
    last: tuple = ()
    last_letter = ""
    page_before = None
    definitions: set[str] = set()
    defining_part = None
    before_gap: list[tuple[int, int]] = []
    previous = ""                        # the body line before this one
    for r in body:
        where = f"p.{r['page']} line {r['line']}"
        text = r["text"]
        if (r["page"], r["line"]) in in_table:
            tid = in_table[(r["page"], r["line"])]
            table = next((u for u in units if u["id"] == tid and u["kind"] == "table"), None)
            if table is None:                  # (a table's lines named in two runs are one piece)
                table = {"id": tid, "title": "", "kind": "table", "members": []}   # titled once read
                units.append(table)
            table["members"].append(r)
            continue
        if style.table and style.table.match(text) and (not style.bold_headings or _bold_start(r)):
            problems.append(f"{where}: a table's title, but brought_in.tables names no lines for it")
        if page_before is not None and any(n not in pages for n in range(page_before + 1, r["page"])):
            before_gap.append((current, page_before))
            section, last, last_letter, defining_part = None, (), "", None
            units.append({"id": f"before the first heading on p.{r['page']}", "title": "", "kind": "before",
                          "members": []})
            current = len(units) - 1
        page_before = r["page"]
        lead = _bold_start(r) if style.bold_headings else text
        head = None
        if where in not_headings:
            used_names.add(where)
        elif lead is not None and style.section and (m := style.section.match(text)) \
                and (not style.bold_headings or lead.startswith(m[0].split()[0])):
            section, last, last_letter, defining_part = m[1], (), "", None
            head = {"id": m[1], "title": (m[2] or "").strip(), "kind": "section_heading"}
        elif lead is not None and (m := style.numbered.match(lead if style.bold_headings else text)) \
                and (style.bold_headings or (m[2][:1].isupper() and m[2] != m[2].upper())):
            code = m[1]
            title = _title(style.numbered.match(text)[2])
            n = number(code)
            top = (n[0],)
            if section is None:                # the first heading after a gap: its order can't be checked
                section, last = str(n[0]), n
                head = {"id": code, "title": title, "kind": "section"}
            elif number(section) != top:
                problems.append(f"{where}: {code} looks like a heading but is printed inside Section {section}; "
                                "not cut there (name it in not_headings with why, if it is body text)")
            elif _in_order(last, n, top):
                last = n
                head = {"id": code, "title": title, "kind": "section"}
            else:
                problems.append(f"{where}: {code} is out of order after "
                                f"{'.'.join(map(str, last)) if last else section}; not cut there (name it in "
                                "not_headings with why, if it is body text)")
            if head and style.numbered_definitions and code.startswith(style.numbered_definitions + ".") \
                    and len(n) > len(number(style.numbered_definitions)):
                head["kind"] = "definition"           # NFPA 3.3.31: the part's title is the term
        elif style.term and (section in definitions or defining_part) and (m := style.term.match(text)) \
                and _is_term(m[1]):
            term = m[1].strip()
            carried = None
            if (o := OPEN_TERM.match(previous)) and units[current]["kind"] == "definition" \
                    and units[current]["members"][-1]["text"] == previous:
                # A term printed across two lines ("SPECIFIED COMPRESSIVE STRENGTH OF" / "MASONRY (f'm). See ...";
                # "[F] EMERGENCY VOICE/ALARM COMMUNICA" / "TIONS. See ..."): the term starts on the line above, which
                # the definition before it does not take. (A word broken at the line's end reads as two here.)
                carried = units[current]["members"].pop()
                term = re.sub(r"^(?:[Il|] )?(?:\[[A-Z]{1,2}\] )?", "", previous) + " " + term
            if term[0] < last_letter:
                problems.append(f"{where}: definition {term!r} is out of alphabetical order (after a term starting "
                                f"{last_letter!r}); not cut there")
            else:
                last_letter = term[0]
                head = {"id": f"{defining_part or section}:{slug(term)}", "title": term, "kind": "definition"}
                if carried is not None:
                    head["carried"] = carried
            if carried is not None and head is None:
                units[current]["members"].append(carried)      # not cut there: the line stays where it was
        if head and head["kind"] == "section_heading" and not head["title"]:
            head["title_next_line"] = True
        elif not head and current >= 0 and units[current].get("title_next_line") \
                and len(units[current]["members"]) == 1 and text.isupper():
            units[current]["title"] = text                 # "SECTION 1015" then, a line below, its title
            units[current].pop("title_next_line")
            if text in style.definitions_titles:
                definitions.add(units[current]["id"])
        if head and head["kind"] == "section_heading" and head["title"] in style.definitions_titles:
            definitions.add(head["id"])
        if head and head["kind"] == "section":
            defining_part = head["id"] if section not in definitions and head["title"] in style.definitions_titles \
                else None
            if defining_part:
                last_letter = ""
        if head or current < 0:
            carried = head.pop("carried", None) if head else None
            units.append(head | {"members": [carried] if carried else []} if head else
                         {"id": f"before the first heading on p.{r['page']}", "title": "", "kind": "before",
                          "members": []})
            current = len(units) - 1
        units[current]["members"].append(r)
        previous = text
        if LOOSE_FRACTION.search(text) or STACKED_APART.fullmatch(text):   # reported below, if its piece is kept
            units[current].setdefault("loose", []).append(f"{where}: a fraction may not have been put back "
                                                          f"together: {_numbers_only(text)!r} (name it in misread)")
    for u in units:
        u.pop("title_next_line", None)
    problems += [f"brought_in.tables names {tid}, whose lines are not on the pages read" for tid in
                 sorted(set(in_table.values())) if tid not in {u["id"] for u in units}]

    ids = [u["id"] for u in units]
    problems += [f"{i} is cut twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    problems += [f"brought_in.not_headings names {w}, which is not a line read" for w in not_headings
                 if w not in used_names]
    sections = list(brought_in.get("sections") or [])
    alone = list(brought_in.get("alone") or [])
    for code in sections + alone:
        if code not in ids:
            problems.append(f"{code}: brought in, but no such heading on the pages read")

    def in_sections(u):
        if u["kind"] == "definition":
            return False
        return u["id"] in alone or any(u["id"] == c or u["id"].startswith(c + ".") for c in sections)

    for code in sections + alone:
        if code in ids and not [u for u in units[ids.index(code) + 1:] if not in_sections(u)]:
            problems.append(f"{code}: its end is not on the pages read (read one more page)")

    terms = {u["id"]: u for u in units if u["kind"] == "definition"}
    used, undefined = {}, {}
    for u in units:
        if style.italic_terms:
            used[u["id"]], undefined[u["id"]] = _uses(u, terms)
        else:                                          # NFPA: the book marks no defined word; every term printed
            used[u["id"]], undefined[u["id"]] = _roman(u, terms) - {u["id"]}, set()
    keep = {u["id"] for u in units if in_sections(u)}
    roman = {u["id"]: sorted(_roman(u, terms) - used[u["id"]] - {u["id"]}) for u in units}
    todo = [d for i in keep for d in used[i]] + [d for i in keep for d in roman[i]]
    while todo:
        d = todo.pop()
        if d not in keep:
            keep.add(d)
            todo += used[d]
    problems += [f"{i}: uses {d}, which is not brought in" for i in sorted(keep) for d in used.get(i, ()) if d not in keep]
    # The heading the definitions sit under, and the part that says where they apply ("1002.1 Definitions. The
    # following words and terms shall ... have the meanings shown herein.")
    for s in {i.split(":")[0] for i in keep if ":" in i}:
        keep |= {u["id"] for u in units if u["kind"] != "definition" and (u["id"] == s or u["id"] == s.split(".")[0])}
    if style.numbered_definitions and any(terms.get(i) for i in keep):
        keep |= {u["id"] for u in units if u["kind"] != "definition" and
                 style.numbered_definitions.startswith(u["id"]) and u["id"] != style.numbered_definitions.split(".")[0]}
    for i, page in before_gap + [(current, body[-1]["page"] if body else 0)]:
        if i >= 0 and units[i]["id"] in keep:
            problems.append(f"{units[i]['id']}: the last part on p.{page} before a page not read; it may run on "
                            "there (read the next page)")
    known = brought_in.get("italic_not_defined") or {}
    for u in units:
        if u["id"] in keep:
            problems += [f"{u['id']}: italic {w!r} is defined on no page read; name it in brought_in."
                         f"italic_not_defined under {u['id']}, with why" for w in sorted(undefined[u["id"]])
                         if w not in (known.get(u["id"]) or {})]
    problems += [f"brought_in.italic_not_defined names {w!r} under {pid}, which has no such italic word"
                 for pid, words in known.items() for w in (words or {})
                 if pid not in keep or w not in undefined.get(pid, ())]
    problems += [p for u in units if u["id"] in keep for p in u.get("loose", [])]
    for u in units:
        if u["kind"] == "table":         # its title, from all the lines it is printed on
            u["title"] = icc_sections.joined_title(icc_sections.table_title_lines(
                u["members"], style.table or re.compile(r"$^")))
    pieces, outside = [], []
    for u in units:
        if u["id"] in keep:
            pieces.append({"id": u["id"], "title": u["title"], "kind": u["kind"], "lines": _runs_of(u["members"]),
                           "text_sha256": text_fingerprint(u["members"]), "uses": sorted(used[u["id"]]),
                           "italic_not_defined_here": sorted(undefined[u["id"]]),
                           "defined_terms_in_roman": roman[u["id"]]})
        else:
            outside += [[*run, u["id"]] for run in _runs_of(u["members"])]
    return {"pieces": pieces, "furniture": furn, "outside": outside, "problems": problems,
            "line_counts": {str(p): len(pages[p]) for p in sorted(pages)}}


JOINING = {"and", "or", "of", "the", "a", "an", "s", "es"}
STACKED_APART = re.compile(r"\d(?: \d)+")   # a line of a stacked fraction's numerator and denominator alone ("1 2")
OPEN_TERM = re.compile(r"^(?:\[[A-Z]{1,2}\] )?[A-Z][A-Z0-9 ,/()'-]*[A-Z]$")   # a term in capitals not yet closed
                                                                            # by its period


def _uses(unit: dict, terms: dict[str, dict]) -> tuple[set[str], set[str]]:
    """As icc_sections._uses: the definitions a unit's italic phrases name, and the italic words no definition names.
    Punctuation the OCR reads as italic (a trailing comma or period) is no word. Terms are matched by their letters
    alone, so a phrase the scan's OCR runs together ("means ofegress", "exitaccess doorways") or breaks at a line's
    end without its hyphen ("horizon tal assembly") still names its definition; a word the OCR runs into a term
    ("approvedby") names the term, and the rest of it ("by") is left over, as an undefined italic word is."""
    by_compact: dict[str, list[str]] = {}
    for pid, u in terms.items():
        for form in _forms(u["title"]):
            by_compact.setdefault(_compact(form), []).append(pid)
    out, undefined = set(), set()
    for phrase in italic_phrases(unit["members"]):
        words = re.sub(r"[^\w/’'-]+", " ", phrase.lower()).split()
        words = [w for w in words if not re.fullmatch(r"[\d.]+", w)]       # a list item's number the OCR slanted
        matches, left = _defined_compact(words, by_compact)
        found = [pid for ids in matches for pid in ids]
        out |= set(found) - {unit["id"]}
        if not found and words:
            undefined.add(" ".join(words))
        elif found:
            undefined |= {w for w in left if w not in JOINING}
    return out, undefined


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _singular(key: str) -> list[str]:
    """A compacted run of words as written, then with its last word's plural taken off ("exits", "stories")."""
    out = [key]
    if key.endswith("ies"):
        out.append(key[:-3] + "y")
    if key.endswith("es"):
        out.append(key[:-2])
    if key.endswith("s"):
        out.append(key[:-1])
    return out


def _defined_compact(words: list[str], by_compact: dict[str, list[str]]) -> tuple[list[list[str]], list[str]]:
    """Longest defined terms first, left to right, matched by their letters alone: (the matches, the words no match
    covers). A single word holding a term and more ("approvedby") is the term, the rest left over."""
    out, left, i = [], [], 0
    while i < len(words):
        for j in range(len(words), i, -1):
            hit = next((by_compact[k] for k in _singular(_compact("".join(words[i:j]))) if k in by_compact), None)
            if hit:
                out.append(hit)
                i = j
                break
        else:
            w = _compact(words[i])
            head = next((w[:k] for k in range(len(w) - 1, 2, -1) if w[:k] in by_compact), None)
            if head:
                out.append(by_compact[head])
                left.append(w[len(head):])
            else:
                left.append(words[i])
            i += 1
    return out, left


def _is_term(term: str) -> bool:
    letters = [c for c in re.sub(r"\([^)]*\)", "", term) if c.isalpha()]
    return len(letters) >= 2 and sum(c.isupper() for c in letters) >= 0.9 * len(letters)


def _numbers_only(text: str) -> str:
    return " ".join(re.findall(r"\[fn\d+\]|\d+(?:[./]\d+)*|/", text))


def to_jsonl(result: dict, header: dict) -> str:
    """icc_sections.to_jsonl, the header naming this splitter."""
    head, rest = icc_sections.to_jsonl(result, header).split("\n", 1)
    return json.dumps(json.loads(head) | {"splitter": SPLITTER}, ensure_ascii=False) + "\n" + rest
