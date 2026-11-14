"""Drafting a state's building code (egress step 3): the same recorded, code-checked drafting as zoning, for a book
kept outside the repo (New York's 2025 Residential Code) and its rules for each part (bedrooms, escape openings,
stairs, handrails, guards).

    python -m rule_drafting draft --state new_york/new_york_state --all --yes

What differs from zoning (Inputs in __main__.py):
- The units are the pieces of the book labeled rule (3_section_labels/) that this step drafts (SCOPE): R318.2's exit
  door, R318.7's stairs, R319's escape openings, R320's handrails, R321's guards, R315's sleeping lofts and BF103.2's
  patio covers. Every other labeled piece waits for a later step (Appendix BO stays flags, in the labels).
- There is no chart and no district: no slots; every number is typed, from a sentence of the piece being drafted, and
  must be one of that piece's second-reading numbers (text_verification.yaml; rule_format/code_numbers.py), which the
  message shows with each number's comparison and any flag.
- The answer may hold rules for each part (drafter.output_schema's for_parts), with the part kinds of
  rule_format/parts.yaml.
- Drafts go to <state folder>/5_building_code_rules/drafted/general.yaml, records beside them, as zoning's do.

The answer key (test_data/answer_keys/<state>/<folder>/) is never read here: it is what the drafts are graded on.
"""

import re
from pathlib import Path

from document_extraction.sections import piece_text
from rule_format.labels import load_pieces
from rule_format.rulebook import REPO, Context, kept_text, load, rules_folder
from section_labeling.labeler import numbered_lines

from . import drafter

PLACES = REPO / "regulations/jurisdictions"
# The pieces egress step 3 drafts (houses, 2025 RCNYS): every one is labeled rule. Lofts (R315) only for a space the
# architect marks a sleeping loft (parts.yaml sleeping_loft); Appendix BO's allowances stay flags (the labels).
SCOPE = ("R318.2", "R318.7.1", "R318.7.2", "R318.7.5.1", "R318.7.5.2", "R318.7.8",
         "R319.1", "R319.2.1", "R319.2.2", "R319.2.3", "R319.2.4", "R319.3", "R319.4", "R319.4.1", "R319.4.2",
         "BF103.2", "R320.2", "R320.4", "R321.1.1", "R321.1.2", "R321.1.3",
         "R315.2", "R315.3", "R315.5.2.1", "R315.5.2.2")
CONTEXT_LIMIT = 20_000          # characters of the sections a piece points to
RELATED_LIMIT = 12_000          # characters of the sections that point to it (background only)
DEFINITIONS_LIMIT = 12_000      # characters of the definitions it uses
REF = re.compile(r"\b((?:R|BF|BO)\d{3}(?:\.\d+)*)(?:\s+through\s+(?:Section\s+)?((?:R|BF|BO)\d{3}(?:\.\d+)*))?")

BOOK_NOTE = """\
## This run: a state building code, not a zoning chart

The text you draft from is New York's 2025 Residential Code (one- and two-family dwellings and townhouses), not a
city's zoning law. Read the instructions above with these changes:
- There is no zoning chart and there are no districts: the answer's shape has no slots, a quote is {piece, text}
  (always the law, by piece id) and a number is {value, quote: its index in quotes} (always a sentence of the piece
  being drafted). Never test `district` or `use`; read "the residential districts" as "the dwellings this code
  covers". Every rule is for every house (its id is "general." plus id_suffix). topic: means_of_egress.
- Every number you type comes from a sentence of the piece being drafted (numbers: from "law_quote"), and must be
  one of the numbers the SECOND READING of that piece lists (given with the piece: a reading of the page images
  independent of the extracted text, with what the printed sentence says of each number: >=, <=, >, <, between,
  none). Use it with that comparison: "not more than 8 1/4 inches" is `<= 8.25`, never `< 8.25` or `> 8.25`. A
  number read "none" is no limit (a metric conversion, a count, a permission to exceed): never compare with it.
  Where the second reading flags a number, the flag says which reading is right.
- Write each length in the unit of the measure it is compared with: inches for a measure in inches (8 1/4 inches is
  8.25; 31 1/2 inches is 31.5; 6 feet 8 inches is 80), square feet for one in square feet (5.7). Never type a
  millimetre, metre or radian number: they are the book's conversions.
- A limit stands as the law's own comparison where it must hold (`stair_riser_height <= 8.25`, not
  `not (stair_riser_height > 8.25)`); a condition the law sets for when a requirement applies ("more than 30
  inches", "four or more risers") goes in applies_when when the rule's when_none is "not_applicable".
- An exception that sends a part to another section (spiral stairways to R318.7.11.1) is not drafted here: make
  that part need review (review_when), never a pass by this rule's numbers and never not applicable (until that
  section is drafted, nothing else checks it).
- A sleeping loft is not a sleeping room: its escape opening is in the room it is open to (R319.1), a loft_room part.
- Most rules here are rules for each part (below). A rule for each part reads only its own part kind's measures and
  the building's. Use `within` only where the law ties the requirement to the part it sits in ("every sleeping room
  shall have" one); a requirement the law sets on every part of a kind ("emergency escape and rescue openings shall
  have ...") is for each part of that kind wherever it sits, with no `within` and when_none "not_applicable".
- A requirement or doubt about one kind of part is a rule or flag for each part of that kind (for_each, with
  applies_when saying which parts it is about), never a whole-building flag: a whole-building flag makes every
  house need review, even one without such a part.
- The related sections shown with a piece are, for this code, the sections labeled rule or flag that name it or a
  section above it: they may modify it. They are drafted from their own text; where one lets a part follow other
  limits instead (a sleeping loft's stair, R315.5), leave that part out of this rule (applies_when) or make it needs
  review (review_when), so this rule never fails a part the code lets follow the other limits.
- Architects' approval of rules is deferred: never write that an architect (or architects) should confirm, check,
  review or approve something. Write a review reason or open question as the doubt itself, or as "a person checks
  ...".
- Where the law sets a formula a measure must equal ("riser height shall be 15 inches minus three-fourths of the
  tread depth"), never write `==`: a measured length never equals a number exactly. Make it a flag for each part it
  is about, naming the formula, for a person to check.
"""


class BookInputs:
    """Everything drafting reads for a state law folder's building code (drafter and __main__ read the same names
    as Inputs: j, drafted, records, ctx, law, columns, cells, notes, for_parts, system(), units(), context())."""

    for_parts = True
    book = True
    settings = drafter.SETTINGS | {"max_tokens": drafter.SETTINGS["book_max_tokens"]}

    def __init__(self, folder: Path):
        self.j = Path(folder)
        self.drafted = rules_folder(self.j) / "drafted"
        self.records = self.drafted / "records"
        self.ctx = Context.for_jurisdiction(self.j)
        settings = load(self.j / "state.yaml")
        name = settings["law"]["residential_code"]
        entry = self.ctx.sources[name]
        header, pieces = load_pieces(self.j / f"2_extracted_text/{Path(name).stem}.sections.jsonl")
        self.rows = kept_text(entry)               # the cached book's text, the brought-in pages (header first)
        self.title = entry["title"]
        labels_file = self.j / f"3_section_labels/{Path(name).stem}.yaml"
        self.labels = (load(labels_file) or {}).get("labels", {})
        self.law = {"file": name, "chart": "", "pieces": pieces, "rows": self.rows, "terms": None,
                    "requires": {p for p, label in self.labels.items() if label.get("label") in ("rule", "flag")}}
        self.verification = self.ctx.verification.get(name, {}).get("pieces", {})
        self.columns, self.cells, self.notes = [], {}, {}

    def system(self) -> str:
        return drafter.system_prompt(self.ctx, {}, [], "", {}, for_parts=True) + "\n" + BOOK_NOTE

    def units(self) -> list[dict]:
        out = []
        for pid in SCOPE:
            label, piece = self.labels.get(pid), self.law["pieces"].get(pid)
            if label is None or piece is None or label.get("label") != "rule":
                raise ValueError(f"{pid}: in SCOPE but not a piece labeled rule")
            readings = second_reading_text(self.verification.get(pid) or {})
            notes = label.get("notes", "")
            notes = "" if notes.startswith("Drafted by hand") and len(notes) < 100 else notes
            out.append({"id": pid, "piece": pid, "prefix": f"{_slug(pid)}_",
                        "intro": (f"Piece {pid} of the {self.title} (document \"law\", piece id {pid}): "
                                  f"{piece['title']}. It was labeled rule: {label['reason']}"
                                  + (f" The label's notes: {notes}" if notes else "")
                                  + "".join(f" Open question (for the architects; never settle it in a formula): {q}"
                                            for q in label.get("open_questions") or [])
                                  + " Draft the rules it sets for the dwellings this code covers.\n\n"
                                  + readings),
                        "text": piece_text(self.rows, piece),
                        "lines": numbered_lines(self.rows, piece),
                        "requirements": [s for s in label.get("sources", []) if s.get("file") == self.law["file"]]})
        return out

    def context(self, unit: dict) -> dict:
        return book_context(unit, self.law)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def second_reading_text(entry: dict) -> str:
    """The second reading of a piece's numbers, as the drafter is shown it."""
    numbers, comps = entry.get("second_reading_numbers") or [], entry.get("second_reading_comparisons") or []
    if not numbers:
        return "The second reading found no numbers in this piece."
    lines = [f"- {n!r}: {c}" for n, c in zip(numbers, comps)]
    flags = [f"- {f}" for f in entry.get("flags") or []]
    return ("Its numbers, as the second reading read them from the page images (with what the printed sentence says "
            "of each):\n" + "\n".join(lines) + ("\nFlags on them:\n" + "\n".join(flags) if flags else ""))


def references(text: str, pieces: dict) -> tuple[list[str], list[str]]:
    """The pieces a text points to ("Section R318.7.11.1", "Sections R319.4.1 through R319.4.4", "Section BF101"),
    in order, once each; and the references that match no piece. A whole section ("R318") is its heading piece only."""
    order = list(pieces)
    out, unfound = [], []
    for first, last in REF.findall(text):
        if last and first in pieces and last in pieces:
            found = order[order.index(first):order.index(last) + 1]
            found += [p for p in order if p.startswith(last + ".")]
        else:
            found = [first] if first in pieces else []
        if not found:
            unfound.append(first)
        out += [p for p in found if p not in out]
    return out, list(dict.fromkeys(unfound))


def book_context(unit: dict, law: dict) -> dict:
    """What a piece points to (the sections it names), the pieces labeled rule or flag that point to it or to a
    section above it (as related background: R315.5.2 lets a loft's stair follow other limits than R318.7's), and the
    definitions it uses (its sections-file `uses` and roman-type terms), each as the book's own text. Appendix BO's
    pieces are left out of the related ones (existing buildings: flags, in the labels). A law quote must be from the
    unit's piece or a piece it points to; numbers only from the unit's own piece."""
    piece = law["pieces"][unit["piece"]]
    refs, unfound = references(unit["text"], law["pieces"])
    pieces, dropped, size = [], [], 0
    for pid in refs:
        if pid == unit["piece"]:
            continue
        body = piece_text(law["rows"], law["pieces"][pid])
        if size + len(body) > CONTEXT_LIMIT:
            dropped.append(pid)
            continue
        pieces.append({"id": pid, "title": law["pieces"][pid]["title"], "text": body})
        size += len(body)
    pointing, pointing_dropped, size = [], [], 0   # pieces whose text names this piece or a section above it
    above = {unit["piece"]} | {unit["piece"].rsplit(".", k)[0] for k in range(1, unit["piece"].count(".") + 1)}
    for pid, other in law["pieces"].items():
        if (pid == unit["piece"] or pid in refs or other.get("kind") == "definition" or pid.startswith("BO")
                or pid not in law.get("requires", ())):           # Appendix BO (existing buildings) stays flags
            continue
        body = piece_text(law["rows"], other)
        if set(references(body, law["pieces"])[0] + references(body, {p: {} for p in above})[0]) & above:
            if size + len(body) <= RELATED_LIMIT:
                pointing.append({"id": pid, "title": other["title"], "text": body})
                size += len(body)
            else:
                pointing_dropped.append(pid)                  # named to the drafter and in the record
    definitions, size = [], 0
    for did in list(dict.fromkeys(piece.get("uses", []) + piece.get("defined_terms_in_roman", []))):
        if did in law["pieces"]:
            body = " ".join(piece_text(law["rows"], law["pieces"][did]).split())
            if size + len(body) <= DEFINITIONS_LIMIT:
                definitions.append(body)
                size += len(body)
    return {"notes": [], "pieces": pieces, "dropped": dropped, "unfound": unfound, "definitions": definitions,
            "related": pointing, "related_dropped": pointing_dropped}


def state_folder(name: str) -> Path:
    """regulations/jurisdictions/<name>, which must be a state law folder (with a state.yaml)."""
    folder = PLACES / name
    if not (folder / "state.yaml").is_file():
        raise SystemExit(f"{name}: not a state law folder (regulations/jurisdictions/<state>/<name> with a state.yaml)")
    return folder
