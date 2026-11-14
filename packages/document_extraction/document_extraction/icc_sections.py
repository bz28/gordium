"""Cut the brought-in parts of an ICC code book (layout: icc in sources.yaml) into pieces at the book's own headings,
so each piece can be labeled. Written for the 2025 Residential Code of New York State; another ICC book (the
Building Code of New York State) prints the same way.

Plain code, no AI: the same extracted text and the same sources.yaml `brought_in` always give the same pieces.

What is brought in (sources.yaml `brought_in`): the pages read (`pages`), the sections (`sections`: a whole
section "R318", or one numbered part of one "R325.6", with everything under it), the italic words Section R202
doesn't define, by piece, each with why (`italic_not_defined`; any other is a problem), and the definitions: every
definition in Section R202 that a brought-in section or a brought-in definition uses. The book prints a defined
term in italics wherever it is used (R201.1: "the words and terms provided in italics shall ... have the meanings
indicated in this chapter"), so the italics, read by code, say which definitions are used; none is picked by hand.

Every line of every page read ends up in exactly one place: a piece (brought in), page furniture (the number
stamped at the top of every page of this copy, the running head, the "2025 RESIDENTIAL CODE OF NEW YORK STATE"
footer with its page number, the lone "." under it), or a part of the book that is not brought in (recorded by
name in the header's `outside`: the end of R317 above R318 on page 99, the definitions no brought-in section
uses...). The coverage report (python -m section_labeling coverage) recounts this from the line counts.

Where a piece starts: a line that starts in bold, with
  - "SECTION R318—MEANS OF EGRESS": a section heading (piece "R318")
  - "[NY] R318.7.5.1 Risers.": a numbered part (piece "R318.7.5.1"), its title up to the first period; an
    optional tag in brackets ([NY] marks New York's own change to the model code)
  - an appendix's sections and parts the same way, with the appendix's letters: "SECTION BO105—ALTERATIONS",
    "[NY] BO105.10.4 Stair treads and risers."
  - in a section of definitions (titled DEFINITIONS: R202, or an appendix's own, BO103; or DEFINITION, BF102), or
    under a numbered part titled "Definition" or "Definitions" (BF106.2), "[RB] STAIRWAY.": a defined term in
    capitals (piece "R202:stairway", "BO103:work_area", "BF102:patio_cover"; under a part, by the part: "BF106.2:screen_enclosure", so
    the part that says where it applies comes in with it, and not the rest of its section). An appendix's own definitions apply in
    that appendix only (R201.1: "as defined within the chapter or appendix where the word or term is found"). A bold entry in
    lower case printed under a term ("[NY] Building permit." under PERMIT, "[NY] Building, existing. See ..." under
    BUILDING) is New York's addition to that term, and stays in its piece
A bold line start is the book's own heading style: a wrapped line of body text that happens to begin "R318.7. ..."
is not bold, so it is never a heading. And a numbered part must come in order (the child .1 of the part above, or
the next number at some level above): one out of order is reported as a problem, never silently skipped, as is a
definition out of alphabetical order, and a numbered part printed inside another section. Where the book's own
numbering is out of order, sources.yaml's `brought_in.printed_out_of_order` names the line with why, and only then is it
cut where printed; where New York's rules amend a term the book prints, `brought_in.amended_by_law` names the line, and
it is cut under the law's term. A name that matches nothing is a problem too. `brought_in.alone` brings in a part
without the parts under it. Problems go in the sections file's header and fail CI.

Each piece: {id, title, kind, lines: [[page, first, last], ...], text_sha256, uses: [definition piece ids],
italic_not_defined_here: [the piece's italic words that Section R202 doesn't define: R201.3 gives them the meaning
another New York code gives them, which is not brought in], defined_terms_in_roman: [definitions whose term the
piece prints in roman type: brought in too]}; kind is "section_heading", "section" or "definition". text_sha256 fingerprints the piece's words, so a machine with the
book can prove the committed pieces were cut from this text; the words themselves are never in the repo.
"""

import hashlib
import json
import re

SPLITTER = "document_extraction.icc_sections v9"   # bump when the cutting rules change
STAMP = re.compile(r"^\d{9}$")                      # the number stamped at the top of every page of this copy
FOOTER = re.compile(r"^(?:\d+ )?2025 RESIDENTIAL CODE OF NEW YORK STATE(?: \d+)?$")
DOT = "."                                           # a lone "." printed under the footer
# A section of the code (R318) or of an appendix (BO105: the appendix's letters, then its number)
SECTION = re.compile(r"^(?:\[[A-Z]{2}\] )?SECTION ([A-Z]{1,2}\d{3})\s*[—–-]\s*(\S.*)$")
NUMBERED = re.compile(r"^(?:\[[A-Z]{2}\] )?([A-Z]{1,2}\d{3}(?:\.\d+)+) (\S.*)$")
TERM = re.compile(r"^(?:\[[A-Z]{2}\] )?([A-Z0-9](?:[^.(]|\([^)]*\))*?)\.(?: |$)")   # "(d.f.u.)" inside
CHAPTER_OPENING = re.compile(r"^(?:Part [IVXLC]+\s*—.*|CHAPTER|APPENDIX)$")   # a chapter's or appendix's first page
# Words that join defined terms inside one italic phrase ("dwelling(s) or townhouse(s)": the "s" of a bracketed
# plural too): never an undefined italic word themselves.
JOINING = {"and", "or", "of", "the", "a", "an", "s", "es"}
LOOSE_FRACTION = re.compile(r"\[fn\d+\]\s*/|/\s*$|^\d+\s*$")    # a numerator left raised, or a denominator alone


def parse_pages(spec: str) -> list[int]:
    """'34-56, 99-105' -> [34, ..., 56, 99, ..., 105]."""
    out = []
    for part in str(spec).split(","):
        a, _, b = part.strip().partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def number(code: str) -> tuple:
    """'R318.7.5' -> (318, 7, 5); 'BO105.10' -> (105, 10)."""
    return tuple(int(x) for x in re.sub(r"^[A-Z]+", "", code).split("."))


def letters(code: str) -> str:
    """The letters a section number starts with: 'R318.7' -> 'R'; 'BO105.8' -> 'BO' (an appendix);
    'BO103:work_area' -> 'BO'."""
    return re.match(r"[A-Z]*", code)[0]


def slug(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")


def _bold_start(r: dict) -> str | None:
    """The bold text a line starts with, or None."""
    runs = r.get("bold") or []
    return r["text"][runs[0][0]:runs[0][1]] if runs and runs[0][0] == 0 else None


def furniture(rows_on_page: list[dict], heads: set[str]) -> set[int]:
    """Line numbers on one page that are page furniture, not law. `heads`: the running heads (the chapter's title,
    printed as the second line of most pages)."""
    out = set()
    for r in rows_on_page:
        if r["line"] == 1 and STAMP.match(r["text"]) or r["line"] == 2 and r["text"] in heads \
                or FOOTER.match(r["text"]) or r["text"] == DOT and r is rows_on_page[-1]:
            out.add(r["line"])
    return out


def split(rows: list[dict], brought_in: dict) -> dict:
    """rows: the extracted text (header row first) of the pages read. brought_in: sources.yaml's.
    Returns {"pieces", "furniture", "outside", "line_counts", "problems"}."""
    pages: dict[int, list[dict]] = {}
    for r in rows[1:]:
        pages.setdefault(r["page"], []).append(r)
    problems: list[str] = []
    wanted = parse_pages(brought_in["pages"])
    if sorted(pages) != wanted:
        problems.append(f"the extracted text has pages {sorted(pages)}, not the pages brought in ({brought_in['pages']})")
    seconds = {}
    for p in pages.values():
        second = next((r["text"] for r in p if r["line"] == 2), None)
        seconds[second] = seconds.get(second, 0) + 1
    heads = {t for t, n in seconds.items() if t and n >= 2 and t.isupper()}   # on two pages or more
    furn, body = [], []
    for page in sorted(pages):
        skip = furniture(pages[page], heads)
        furn += [[page, n] for n in sorted(skip)]
        body += [r for r in pages[page] if r["line"] not in skip]

    # Cut every body line into units, heading to heading: each unit is then brought in (a piece) or not (outside).
    units: list[dict] = []
    section = None                       # the current SECTION, e.g. "R318"
    last: tuple = ()                     # the last numbered part's number
    last_letter = ""                     # the last definition's first letter
    page_before = None
    definitions: set[str] = set()        # the sections of definitions: R202, and an appendix's own (BO103, BF102)
    defining_part = None                 # the numbered part titled "Definition(s)" (BF106.2) the terms are under, if any
    out_of_order = brought_in.get("printed_out_of_order") or {}   # "p.973 line 54": why the book prints it so
    amended = brought_in.get("amended_by_law") or {}               # "p.966 line 38": {term, why}
    used_names: set[str] = set()
    before_gap: list[tuple[int, int]] = []   # (the unit a gap in the pages read follows, the page before the gap)
    for r in body:
        if page_before is not None and any(n not in pages for n in range(page_before + 1, r["page"])):
            # A page after a gap in the pages read: what it starts with continues a part on a page not read.
            before_gap.append((len(units) - 1, page_before))
            section, last, last_letter, defining_part = None, (), "", None
            units.append({"id": f"before the first heading on p.{r['page']}", "title": "", "kind": "before",
                          "members": []})
        page_before = r["page"]
        bold = _bold_start(r)
        head = None
        opening = f"chapter opening on p.{r['page']}"
        where = f"p.{r['page']} line {r['line']}"
        if CHAPTER_OPENING.match(r["text"]) and (bold or r["text"] in ("CHAPTER", "APPENDIX")) \
                and not (units and units[-1]["id"] == opening):
            # A new chapter: its title and ICC's user notes are not law, and end the section before (never part
            # of the last definition, nor of the first section after).
            section, last, last_letter, defining_part = None, (), "", None
            head = {"id": opening, "title": "", "kind": "before"}
        elif bold and (m := SECTION.match(r["text"])):
            section, last, last_letter = m[1], (), ""
            head = {"id": m[1], "title": m[2].strip(), "kind": "section_heading"}
            if m[2].strip() in ("DEFINITIONS", "DEFINITION"):   # Appendix BF prints the singular (BF102)
                definitions.add(m[1])
        elif bold and (m := NUMBERED.match(bold)):
            code = m[1]
            n = number(code)
            if section is not None and code.split(".")[0] != section:
                # A heading numbered in another section than the one it is printed in: cut where printed if sources.yaml
                # says why (the numbering of the parts after it goes on from the part before it), else a problem
                if _printed(out_of_order, where, code, problems):
                    used_names.add(where)
                    head = {"id": code, "title": m[2].strip().rstrip("."), "kind": "section"}
                else:
                    problems.append(f"{where}: {code} is printed inside Section {section}; not cut there")
            elif section is None:          # the first heading after a gap: its order can't be checked against unread text
                section, last = code.split(".")[0], n
                head = {"id": code, "title": m[2].strip().rstrip("."), "kind": "section"}
            elif not _in_order(last, n, number(section)) and _printed(out_of_order, where, code, problems):
                # The book's own numbering is out of order here, and sources.yaml says why: cut where it is printed
                used_names.add(where)
                last = n
                head = {"id": code, "title": m[2].strip().rstrip("."), "kind": "section"}
            elif not _in_order(last, n, number(section)):
                problems.append(f"{where}: {code} is out of order after "
                                f"{letters(section) + '.'.join(map(str, last)) if last else section}; not cut there")
            else:
                last = n
                head = {"id": code, "title": m[2].strip().rstrip("."), "kind": "section"}
        elif bold and (section in definitions or defining_part) and (m := TERM.match(bold)) and _is_term(m[1]):
            term = m[1].strip()
            if _printed(amended, where, term, problems):
                # New York's rules amend the term the book prints here (19 NYCRR Part 1220): cut under the law's term
                used_names.add(where)
                term = str(amended[where]["term"])
            if term[0] < last_letter:
                problems.append(f"p.{r['page']} line {r['line']}: definition {term!r} is out of alphabetical order "
                                f"(after a term starting {last_letter!r}); not cut there")
            else:
                last_letter = term[0]
                head = {"id": f"{defining_part or section}:{slug(term)}", "title": term, "kind": "definition"}
        elif bold and (section in definitions or defining_part) and _is_term(bold.split(". ")[0]) \
                and bold.rstrip().endswith("."):
            # Bold capitals ending in a period look like a defined term the cutter couldn't read: never let it
            # fall silently into the definition above it.
            problems.append(f"p.{r['page']} line {r['line']}: {bold!r} looks like a defined term but was not cut")
        if head and head["kind"] != "definition":
            # A numbered part titled "Definition(s)" ("BF106.2 Definition. The following word and term shall, for the
            # purposes of this appendix, ..."): the bold terms under it are definitions, up to the next heading
            # (only outside a section of definitions: "BJ102.1 Definitions." under "SECTION BJ102—DEFINITIONS" leaves its
            # terms named by the section, BJ102:term, with the section's heading brought in)
            defining_part = head["id"] if head["kind"] == "section" and section not in definitions \
                and head["title"] in ("Definition", "Definitions") else None
            if defining_part:
                last_letter = ""
        if head:
            units.append(head | {"members": []})
        elif not units:
            units.append({"id": f"before the first heading on p.{r['page']}", "title": "", "kind": "before",
                          "members": []})
        units[-1]["members"].append(r)
        if LOOSE_FRACTION.search(r["text"]) and units[-1]["kind"] != "before":
            problems.append(f"p.{r['page']} line {r['line']}: a fraction may not have been put back together: "
                            f"{_numbers_only(r['text'])!r}")

    ids = [u["id"] for u in units]
    problems += [f"{i} is cut twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    problems += [f"brought_in names {w} ({kind}), where the book prints no such heading" for kind, named in
                 (("printed_out_of_order", out_of_order), ("amended_by_law", amended)) for w in named if w not in used_names]
    sections = list(brought_in.get("sections") or [])
    alone = list(brought_in.get("alone") or [])      # parts brought in without the parts under them
    for code in sections + alone:
        if code not in ids:
            problems.append(f"{code}: brought in, but no such heading on the pages read")

    def in_sections(u):
        if u["kind"] == "definition":
            return False
        return u["id"] in alone or any(u["id"] == c or u["id"].startswith(c + ".") for c in sections)

    # A brought-in part must end where the book's next part begins, on a page read: else it may run on unread.
    for code in sections + alone:
        if code in ids:
            after = [u for u in units[ids.index(code) + 1:] if not in_sections(u)]
            if not after:
                problems.append(f"{code}: its end is not on the pages read (read one more page)")

    terms = {u["id"]: u for u in units if u["kind"] == "definition"}
    used, undefined = {}, {}
    for u in units:
        used[u["id"]], undefined[u["id"]] = _uses(u, _in_scope(u["id"], terms))
    keep = {u["id"] for u in units if in_sections(u)}
    # A defined term printed in roman type in a brought-in section: R201.1 gives the defined meaning to italic words
    # only, so it doesn't strictly apply there, but it is brought in too, so the reader sees both (never fewer).
    roman = {u["id"]: sorted(_roman(u, _in_scope(u["id"], terms)) - used[u["id"]] - {u["id"]}) for u in units}
    todo = [d for i in keep for d in used[i]] + [d for i in keep for d in roman[i]]
    while todo:                                      # each brought-in definition's own defined words, and theirs
        d = todo.pop()
        if d not in keep:
            keep.add(d)
            todo += used[d]
    # Every definition a kept piece uses is kept too: never a piece that names one the reader can't see. The loop
    # above makes this so today; this line keeps it so if the loop is ever changed.
    problems += [f"{i}: uses {d}, which is not brought in" for i in sorted(keep) for d in used.get(i, ()) if d not in keep]
    # The heading the definitions sit under, and the section's own numbered parts above them ("BO103.1 General. The
    # terms used in this appendix ... are defined as follows"), which say where its definitions apply
    for s in {i.split(":")[0] for i in keep if ":" in i}:
        keep |= {u["id"] for u in units if u["kind"] != "definition" and (u["id"] == s or u["id"].startswith(s + "."))}
    # A brought-in part that is the last before a gap in the pages read, or the last of all, may run on onto a
    # page not read (a page left out of `pages` would silently drop the law on it): never cut short silently.
    for i, page in before_gap + [(len(units) - 1, body[-1]["page"] if body else 0)]:
        if i >= 0 and units[i]["id"] in keep:
            problems.append(f"{units[i]['id']}: the last part on p.{page} before a page not read; it may run on "
                            "there (read the next page)")
    # An italic word Section R202 doesn't define takes another code's meaning (R201.3), which is not brought in: each
    # must be named in brought_in.italic_not_defined under its piece, with why, or a new one would pass unseen; a name
    # no piece needs any more is reported too, so the list never covers more than it says.
    known = brought_in.get("italic_not_defined") or {}
    for u in units:
        if u["id"] in keep:
            problems += [f"{u['id']}: italic {w!r} is not defined in Section R202"
                         f"{'' if letters(u['id']) == 'R' else ' or its appendix'}; name it in brought_in."
                         f"italic_not_defined under {u['id']}, with why" for w in sorted(undefined[u["id"]])
                         if w not in (known.get(u["id"]) or {})]
    problems += [f"brought_in.italic_not_defined names {w!r} under {pid}, which has no such italic word"
                 for pid, words in known.items() for w in (words or {})
                 if pid not in keep or w not in undefined.get(pid, ())]
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


def _printed(named: dict, where: str, printed: str, problems: list[str]) -> bool:
    """Is the line `where` named in sources.yaml (printed_out_of_order, amended_by_law), and does the book print there what
    the entry says (its `printed`)? A name whose line prints something else is a problem, never applied: a stale line
    number must not rename or cut whatever happens to be printed there now."""
    if where not in named:
        return False
    if (named[where] or {}).get("printed") != printed:
        problems.append(f"brought_in names {where} as printing {(named[where] or {}).get('printed')!r}, but the book "
                        f"prints {printed!r} there; not applied")
        return False
    return True


def _in_scope(uid: str, terms: dict[str, dict]) -> dict[str, dict]:
    """The definitions that apply in a unit: Chapter 2's everywhere; an appendix's own (BO103's) only in that appendix
    (R201.1: "the meanings indicated in this chapter or as defined within the chapter or appendix where the word or
    term is found"; BO103.1: "The terms used in this appendix")."""
    mine = letters(uid)
    return {pid: t for pid, t in terms.items() if letters(pid) in ("R", mine)}


def _in_order(last: tuple, n: tuple, section: tuple) -> bool:
    """Is part `n` the next one after `last` (its first child .1, or the next number at its level or above)?"""
    if not last:
        return n == section + (1,)
    if n == last + (1,):
        return True
    return any(n == last[:k] + (last[k] + 1,) for k in range(len(section), len(last)))


def _is_term(term: str) -> bool:
    """A defined term is written in capitals ("STAIRWAY, SPIRAL"); a part title or a sentence is not."""
    letters = [c for c in re.sub(r"\([^)]*\)", "", term) if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) >= 0.9 * len(letters)


def _alphabetic(term: str) -> str:
    """How the book orders its definitions: by the letters alone ("AIR, OUTDOOR" before "AIR ADMITTANCE VALVE"
    is not alphabetical by letters, so only a term clearly earlier by its first word is out of order)."""
    return re.split(r"[^A-Z0-9]", term.upper())[0]


def _runs_of(members: list[dict]) -> list[list[int]]:
    runs: list[list[int]] = []
    for r in members:
        if runs and runs[-1][0] == r["page"] and runs[-1][2] == r["line"] - 1:
            runs[-1][2] = r["line"]
        else:
            runs.append([r["page"], r["line"], r["line"]])
    return runs


def text_fingerprint(members: list[dict]) -> str:
    """The piece's words, fingerprinted: its lines' (page, line, text), in order."""
    return hashlib.sha256(json.dumps([[r["page"], r["line"], r["text"]] for r in members],
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def italic_phrases(members: list[dict]) -> list[str]:
    """The italic phrases of a piece, one per use, with a phrase broken across two lines joined ("open-" + "ings")."""
    out: list[str] = []
    carry = None
    for r in members:
        runs = r.get("italic") or []
        for k, (a, b) in enumerate(runs):
            piece = r["text"][a:b]
            if carry is not None and k == 0 and a == 0:
                piece = (carry[:-1] if carry.endswith("-") else carry + " ") + piece
                carry = None
            elif carry is not None:
                out.append(carry)
                carry = None
            if b == len(r["text"]) and k == len(runs) - 1:
                carry = piece
            else:
                out.append(piece)
        if carry is not None and not runs:
            out.append(carry)
            carry = None
    if carry is not None:
        out.append(carry)
    return out


def _uses(unit: dict, terms: dict[str, dict]) -> tuple[set[str], set[str]]:
    """(the definitions (piece ids) a unit's italic words name, the italic words no definition names). A defined
    word is used in its plural or with a capital ("Stairways"); a phrase may hold several defined words ("Emergency
    escape and rescue openings"), so the whole phrase is matched first, then its parts. A phrase no definition names
    is undefined whole ("accessed"); in a phrase that does hold a defined word, each other word is undefined on its
    own ("nonhabitable" in "nonhabitable attics"), but a joining word ("or" in "dwelling(s) or townhouse(s)") is not."""
    by_slug: dict[str, list[str]] = {}
    for pid, u in terms.items():
        for form in _forms(u["title"]):
            by_slug.setdefault(slug(form), []).append(pid)
    out, undefined = set(), set()
    for phrase in italic_phrases(unit["members"]):
        words = re.sub(r"[^\w/’'-]+", " ", phrase.lower()).split()
        matches, left = _defined(words, by_slug)
        found = [pid for ids in matches for pid in ids]
        out |= set(found) - {unit["id"]}
        if not found and words:
            undefined.add(" ".join(words))
        elif found:
            undefined |= {w for w in left if w not in JOINING}
    return out, undefined


def _roman(unit: dict, terms: dict[str, dict]) -> set[str]:
    """The definitions whose term the unit's text names anywhere (in any type, as a whole word or phrase, plural
    too, "stories" for STORY; "STAIRWAY, SPIRAL" also as "spiral stairway")."""
    text = " ".join(r["text"] for r in unit["members"]).lower()
    text = re.sub(r"-\s", "", text)            # a word broken across two lines ("open- ings")
    out = set()
    for pid, u in terms.items():
        for f in _forms(u["title"]):
            f = f.lower()
            plural = re.escape(f) + r"(?:s|es)?" + (f"|{re.escape(f[:-1])}ies" if f.endswith("y") else "")
            parts = f.split(" ")
            for k in range(len(parts) - 1):        # a word inside in its plural: "changes of occupancy", "stories
                w = re.escape(parts[k]) + r"(?:s|es)"   # above grade plane"
                if parts[k].endswith("y"):
                    w = f"(?:{w}|{re.escape(parts[k][:-1])}ies)"
                plural += "|" + re.escape(" ".join(parts[:k])) + (" " if k else "") + w + \
                    re.escape(" " + " ".join(parts[k + 1:]))
            if f and re.search(r"(?<![\w-])(?:" + plural + r")(?!\w)", text):   # "owner-occupied", "stories" too
                out.add(pid)
    return out


def _forms(title: str) -> list[str]:
    """How a defined term may be written where it is used: as defined ("ACCESS (TO)"), without its parenthesis
    ("RISER (STAIR)": "riser"), and an inverted term the right way round ("STAIRWAY, SPIRAL": "spiral stairway")."""
    bare = re.sub(r"\s*\([^)]*\)", "", title).strip()
    out = [title, bare]
    if "," in bare:
        head, _, tail = bare.partition(",")
        out.append(f"{tail.strip()} {head.strip()}")
    return list(dict.fromkeys(f for f in out if f))


def _defined(words: list[str], by_slug: dict[str, list[str]]) -> tuple[list[list[str]], list[str]]:
    """Longest defined terms first, left to right, over the words of one italic phrase: (the matches, the words no
    match covers). Each match is every definition with that term: "risers" is RISER (PLUMBING) and RISER (STAIR),
    both brought in (never fewer)."""
    out, left, i = [], [], 0
    while i < len(words):
        for j in range(len(words), i, -1):
            pid = _lookup(words[i:j], by_slug)
            if pid:
                out.append(pid)
                i = j
                break
        else:
            left.append(words[i])
            i += 1
    return out, left


def _lookup(words: list[str], by_slug: dict[str, list[str]]) -> list[str] | None:
    """The definitions a run of words names, as written or with one word in its plural: the last ("risers") or
    another ("changes of occupancy": CHANGE OF OCCUPANCY)."""
    key = slug(" ".join(words))
    if key in by_slug:
        return by_slug[key]
    for k in [len(words) - 1, *range(len(words) - 1)]:
        w = words[k]
        for one in (w[:-1] if w.endswith("s") else None, w[:-2] if w.endswith("es") else None,
                    w[:-3] + "y" if w.endswith("ies") else None):
            if one:
                key = slug(" ".join(words[:k] + [one] + words[k + 1:]))
                if key in by_slug:
                    return by_slug[key]
    return None


def _numbers_only(text: str) -> str:
    """A line shown in a problem message by its numbers alone (the words of the book stay out of the repo)."""
    return " ".join(re.findall(r"\[fn\d+\]|\d+(?:[./]\d+)*|/", text))


def to_jsonl(result: dict, header: dict) -> str:
    """A header naming the extracted text it came from (file and PDF fingerprint), then one piece per line. No words
    of the book but its section numbers, titles and defined terms."""
    head = {"file": header["file"], "sha256": header["sha256"], "splitter": SPLITTER, "extractor": header["extractor"],
            "pieces": len(result["pieces"]), "problems": result["problems"], "line_counts": result["line_counts"],
            "furniture": result["furniture"], "outside": result["outside"]}
    return "\n".join(json.dumps(x, ensure_ascii=False) for x in [head, *result["pieces"]]) + "\n"
