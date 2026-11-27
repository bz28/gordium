"""New York's Building Code Chapter 7 (fire and smoke protection features), the parts that build and protect the
means of egress (docs/decisions/2026-11-26_ny_building_chapter_7.md): what Chapter 10 sends to it (exit stairway and
passageway enclosures as fire barriers, shaft enclosures, their openings and penetrations). Nothing in these
sections is in the model yet (an enclosure's rating, its walls' construction, penetrations, joints), so each piece
labeled a flag is a person's check, never a pass or a fail. Needs no code cache (the quotes are checked word for
word by `python -m rule_format` where the cache is)."""

import json
import re

import pytest

from rule_format.rulebook import REPO, Context, load, outcome

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
SECTIONS = NY / "2_extracted_text/gov.ny.building.2025.sections.jsonl"
LABELS = NY / "3_section_labels/gov.ny.building.2025.yaml"
CHAPTER_7 = re.compile(r"(Table )?7\d\d(\.\d+)*(\(\d\))?$")       # 707.6, Table 716.1(2)
# The only facts a Chapter 7 flag may be narrowed by, each one the architect states (never a fact the model could get
# wrong): a corridor's stated rating (Table 716.1(2)'s corridor row), the sprinkler system and group (716.2.2.3's
# exception)
NARROWED_BY = {"corridor_fire_rating_hours", "sprinklered_903_3_1_1", "sprinklered_903_3_1_2", "occupancy_group"}


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(NY)


@pytest.fixture(scope="module")
def book():
    return load(RULEBOOK)["rules"]


@pytest.fixture(scope="module")
def pieces():
    rows = [json.loads(line) for line in SECTIONS.read_text(encoding="utf-8").splitlines()]
    return {p["id"]: p for p in rows[1:] if CHAPTER_7.match(p["id"])}


@pytest.fixture(scope="module")
def labels(pieces):
    return {k: v for k, v in load(LABELS)["labels"].items() if k in pieces}


def _rid(pid: str) -> str:
    """The id prefix the coverage report reads as naming a piece (section_labeling.coverage: the piece's slug, every
    character not a letter or digit an underscore, then "_"): general.bc_716_1_ for 716.1, general.bc_table_716_1_2__
    for Table 716.1(2) (its closing bracket an underscore too)."""
    return "general.bc_" + "".join(c if c.isalnum() else "_" for c in pid.lower()) + "_"


def _flags(book, pid):
    """The rules naming the piece itself: 716.1's, never 716.1.2.1's (the next word after the number is a word)."""
    return [r for r in book if re.match(re.escape(_rid(pid)) + "[a-z]", r["id"])]


def test_every_chapter_7_piece_brought_in_is_labeled_and_every_flag_has_its_own(pieces, labels, book):
    """Each piece is labeled, and each one labeled a flag has a flag whose id names it (the coverage report's own
    rule), so no requirement of these sections is left without a line in the check."""
    assert pieces and set(labels) == set(pieces)
    flagged = [p for p, v in labels.items() if v["label"] in ("flag", "rule")]
    assert len(flagged) >= 27
    for pid in flagged:
        assert _flags(book, pid), pid


def test_every_chapter_7_flag_quotes_every_line_of_its_piece(pieces, labels, book):
    """The flag quotes its whole piece, every exception with it (an exception that tightens, or a section named only
    there, can't go unseen); a table's flags, its every row, heading and note between them."""
    for pid, v in labels.items():
        if v["label"] not in ("flag", "rule"):
            continue
        quoted = {(s["page"], n) for r in _flags(book, pid) for s in r["sources"]
                  for n in range(s["lines"][0], s["lines"][1] + 1)}
        for page, a, b in pieces[pid]["lines"]:
            for n in range(a, b + 1):
                if (page, n) in quoted:
                    continue
                text = " ".join(s["quote"] for r in book for s in r.get("sources", [])
                                if s["page"] == page and s["lines"][0] <= n <= s["lines"][1])
                assert False, (pid, page, n, text[:80])




def _refs(text: str) -> set[str]:
    out = set()
    for m in re.finditer(r"(?:Sections?|Tables?) ((?:\d{3,4}(?:\.\d+)*(?:\(\d\))?(?:, | and | or | through )?)+)", text):
        out |= set(re.findall(r"\d{3,4}(?:\.\d+)*(?:\(\d\))?", m.group(1)))
    out |= set(re.findall(r"Chapter \d+", text))                       # another chapter (713.14's Chapter 30)
    out |= set(re.findall(r"\b(?:ASTM [A-Z]\d+|UL \d+[A-Z]?|NFPA \d+)", text))     # a standard (703.2.1.1's tests)
    return out


# a section number, never a glazing marking's minutes ("W-120", "D-H-90": Table 716.1(2))
TOKEN = re.compile(r"(?<![\d.-])\d{3,4}(?:\.\d+)*(?:\(\d\))?(?![\d.]*\d)|Chapter \d+|ASTM [A-Z]\d+|UL \d+[A-Z]?|NFPA \d+")


def _named(note: str) -> set[str]:
    """The sections, tables, chapters and standards a note names, each a whole token: "713.7" names 713.7, never
    713 (review round 1: a substring match let a note drop "Section 713" and still pass)."""
    return {m.group(0).rstrip(".") for m in TOKEN.finditer(note)}


def _shown_note(rule: dict) -> str:
    """The note a flag's result shows, as design_checker/egress.py's _flag_item picks it: the first example with a
    note that needs review."""
    return next((e["note"] for e in rule.get("examples") or [] if e.get("note") and e.get("expect") == "needs_review"),
                "")


def test_the_note_shown_is_the_first_that_needs_review():
    """Review round 2's pin: a second example's note never stands in for the one shown."""
    rule = {"examples": [{"expect": "needs_review", "note": "per 713.7"}, {"expect": "needs_review", "note": "per 716"}]}
    assert _named(_shown_note(rule)) == {"713.7"}


def test_every_section_a_chapter_7_piece_names_is_named_in_its_flags_words(labels, book):
    """Review class (2026-11-26): every section, table or other code a flagged piece sends to is named in what the
    architect reads on its flag (the note the checker shows: the first example's that needs review, egress._flag_item;
    never the rule's own notes, nor a second example's), each as a
    whole token, so a person's check never leaves out a section the law joins to it; the piece's own number aside."""
    for pid, v in labels.items():
        if v["label"] not in ("flag", "rule"):
            continue
        for r in _flags(book, pid):
            quote = " ".join(s["quote"] for s in r["sources"])
            shown = _named(_shown_note(r))
            missing = sorted(x for x in _refs(quote) - {pid} if x not in shown)
            assert not missing, (r["id"], missing)


def test_a_note_naming_only_a_longer_section_doesnt_name_the_shorter():
    """The pin for the whole-token match: "713.7" and "716.2.6.6" don't name 713 or 716."""
    assert _named("Openings per 713.7 and 716.2.6.6 (Chapter 30, ASTM E119).") == \
        {"713.7", "716.2.6.6", "Chapter 30", "ASTM E119"}
    assert "713" not in _named("per 713.7") and "713" in _named("per 713 and 713.7")
    assert _named("marked D-H-90 or W-120 (716.1.2.3)") == {"716.1.2.3"}        # a marking's minutes, no section


def test_every_chapter_7_flag_is_a_persons_check_for_every_building(labels, book, ctx):
    """Nothing these sections ask is in the model (an enclosure's rating, the stories it connects, its construction,
    its penetrations, a door's rating): each flag needs review for every building, whatever its group or sprinkler
    system, and never passes; a flag narrowed at all is narrowed only by a fact the architect states (NARROWED_BY),
    and needs review while that fact isn't stated."""
    from rule_format import formula, parts
    allowed = ctx.allowed()
    narrowed = []
    for pid, v in labels.items():
        if v["label"] != "flag":
            continue
        for r in _flags(book, pid):
            assert r["kind"] == "flag" and "check" not in r, r["id"]
            if "applies_when" not in r:
                for given in ({}, {"occupancy_group": "R-2", "sprinklered_903_3_1_1": False},
                              {"occupancy_group": "mixed", "sprinklered_903_3_1_1": True}):
                    assert outcome(r, given, allowed) == "needs_review", (r["id"], given)
                continue
            narrowed.append(r["id"])
            assert formula.names(r["applies_when"]) <= NARROWED_BY, r["id"]
            if "for_each" in r:
                [row] = parts.rows(r, {r["for_each"]: [{"id": "p1", "name": "Not stated", "measures": {}}]}, {}, allowed)
                assert row["outcome"] == "needs_review", r["id"]
            else:
                assert outcome(r, {}, allowed) == "needs_review", r["id"]
    assert sorted(narrowed) == ["general.bc_716_2_2_3_exit_enclosure_door_temperature_rise",
                                "general.bc_table_716_1_2__corridors"]


def test_716_2_2_3s_exception_needs_a_sprinkler_system_903_3_1_2_allows(book, ctx):
    """716.2.2.3's temperature rise is lifted only in a building stated sprinklered throughout per 903.3.1.1, or per
    903.3.1.2 in Group R (where 903.3.1.2 allows an NFPA 13R system): a 13R system stated for another group, or for a
    building of two or more groups, leaves it a person's check, never not applicable."""
    [r] = [r for r in book if r["id"] == "general.bc_716_2_2_3_exit_enclosure_door_temperature_rise"]
    allowed = ctx.allowed()
    for group in ("R-1", "R-2", "R-3", "R-4"):
        assert outcome(r, {"sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": True, "occupancy_group": group},
                       allowed) == "not_applicable", group
    for group in ("B", "A-2", "E", "I-2", "mixed"):
        assert outcome(r, {"sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": True, "occupancy_group": group},
                       allowed) == "needs_review", group
        assert outcome(r, {"sprinklered_903_3_1_1": True, "occupancy_group": group}, allowed) == "not_applicable"
    assert outcome(r, {"sprinklered_903_3_1_2": True}, allowed) == "needs_review"   # 903.3.1.1 and the group unstated


def test_chapter_7_rules_sit_in_book_order_before_chapter_10(book):
    """The convention that keeps parallel chapters' rules from colliding when merged (PR notes, 2026-11-26): one
    rulebook per law folder (rulebook.building_code_rulebook), each chapter a block in book order. Chapter 7's flags
    sit together after 508's and before Chapter 10's first rule (1004.7)."""
    ids = [r["id"] for r in book]
    seven = [i for i, rid in enumerate(ids) if re.match(r"general\.bc_(table_)?7\d\d_", rid)]
    assert seven == list(range(seven[0], seven[-1] + 1))
    assert ids[seven[-1] + 1] == "general.bc_1004_7_outdoor_areas"
    assert ids[seven[0] - 1].startswith("general.bc_508_")


def _note(book, rid):
    [r] = [r for r in book if r["id"] == rid]
    return " ".join(e.get("note", "") for e in r["examples"])


def test_review_round_1s_notes_say_what_the_law_says(book, labels):
    """Review round 1 (2026-11-26), each confirmed: a note told an architect less than the law asks. 707.3.2's names
    1023.2's floor-assembly minimum, mezzanines and three exceptions; a cap is "need not be more than", never "never
    more than" (a ban the law doesn't make); 707.3.5's gives the rating from 1026.2, not 1026.1 (which has none);
    713.11's exceptions each lift what they lift (a chute shaft used for nothing else); 707.5.1's exception 2 keeps
    its "unless"; 713.1's "shall be enclosed in accordance with Section 1023" is a flag of its own."""
    stair = _note(book, "general.bc_707_3_2_exit_stairway_fire_barriers")
    for word in ("floor assembly", "mezzanines", "408.3.8", "404.6", "510.2", "need not be more than 2 hours"):
        assert word in stair, word
    for r in book:
        if re.match(r"general\.bc_7\d\d_", r["id"]):
            assert "never more than" not in _note(book, r["id"]), r["id"]
    horizontal = _note(book, "general.bc_707_3_5_horizontal_exit_separation")
    assert "1026.2" in horizontal and "at least 2 hours" in horizontal and "above-grade pedestrian walkway" in horizontal
    enclosed = _note(book, "general.bc_713_1_shafts_and_exit_stairways")
    assert all(s in enclosed for s in ("1023.2", "1023.3.1", "1023.8", "1023.12", "among other things"))
    assert "rating 1026.1 asks" not in labels["707.3.5"]["reason"]
    bottom = _note(book, "general.bc_713_11_shaft_bottom")
    assert "used for nothing else" in bottom and "needs no rated separation" in bottom
    assert "unless another section" in _note(book, "general.bc_707_5_1_supporting_construction")
    assert "permanently" in _note(book, "general.bc_703_5_marking")                  # review round 3
    assert "adjoining floor areas" in _note(book, "general.bc_707_6_openings")         # review round 5
    assert "need not exceed 2 hours" in labels["713.4"]["reason"] and "403.2.1.2" in labels["713.4"]["reason"]
    assert labels["713.1"]["label"] == "flag" and _flags(book, "713.1")


UNIT_NUMBER = re.compile(r"\b\d[\d,.]*(?= (?:square|feet|foot|inch|inches|percent|hours?|minutes|degrees|pounds?|cubic|stories))")


def _ranges(note: str) -> set[str]:
    """The sections inside a range a note names, "1023.4 to 1023.7" naming 1023.5 and 1023.6 too (review round 4: the
    README's list missed 1023.6, inside 713.1's range)."""
    out = set()
    for a, b in re.findall(r"(\d{3,4}(?:\.\d+)+) to (\d{3,4}(?:\.\d+)+)", note):
        head_a, last_a = a.rsplit(".", 1)
        head_b, last_b = b.rsplit(".", 1)
        if head_a == head_b:
            out |= {f"{head_a}.{n}" for n in range(int(last_a), int(last_b) + 1)}
    return out


def test_a_range_names_every_section_inside_it():
    want = {"1023.4", "1023.5", "1023.6", "1023.7", "716.2.1.1", "716.2.1.2", "716.2.1.3", "716.2.1.4"}
    assert _ranges("per 1023.4 to 1023.7, and 716.2.1.1 to 716.2.1.4") == want


def _brought_in(token: str, pieces_all: set[str]) -> bool:
    """A section the folder brings in: a piece of that number, or one under it (716 is brought in where 716.1 is)."""
    return any(p == token or p.startswith(token + ".") or p == "Table " + token for p in pieces_all)


def test_every_section_a_chapter_7_note_names_is_brought_in_or_in_the_readmes_list():
    """Review round 3 (2026-11-26), the class: a section, chapter or standard a Chapter 7 flag's shown note sends the
    architect to is either brought in or named in the README's list of references not brought in, so that list never
    lags behind what the notes cite."""
    rows = [json.loads(line) for line in SECTIONS.read_text(encoding="utf-8").splitlines()]
    pieces_all = {p["id"] for p in rows[1:]}
    readme = (NY / "README.md").read_text(encoding="utf-8")
    listed = _named(readme.split("## References in the brought-in sections that are not brought in", 1)[1])
    missing = {}
    for r in load(RULEBOOK)["rules"]:
        if re.match(r"general\.bc_(table_)?7\d\d_", r["id"]):
            note = UNIT_NUMBER.sub("", _shown_note(r))           # "156 square feet" is a size, not a section
            gone = sorted(t for t in _named(note) | _ranges(note) if not _brought_in(t, pieces_all) and t not in listed)
            if gone:
                missing[r["id"]] = gone
    assert not missing, missing


def test_part_b_review_round_1s_notes_say_what_the_tables_say(book):
    """Part b review round 1 (2026-11-26), read on the page images of Tables 716.1(2) and 716.1(3): double fire walls'
    doors are 3, 1 1/2 and 1 hours (not the walls' 3, 2 and 1); a window in a 1-hour fire partition is 3/4 hour; 716.1's
    note names 1020.2.1 for elevator hoistway doors, not corridors."""
    other = _shown_note([r for r in book if r["id"] == "general.bc_table_716_1_2__other_assemblies"][0])
    assert "double fire walls of 3 hours with each wall 2, a door rated 1 1/2 hours" in " ".join(other.split())
    windows = _shown_note([r for r in book if r["id"] == "general.bc_table_716_1_3__fire_windows"][0])
    assert "fire partitions rated 1 hour, 3/4 hour" in " ".join(windows.split())
    general = _shown_note([r for r in book if r["id"] == "general.bc_716_1_opening_protectives_general"][0])
    assert "elevator hoistway doors 1020.2.1" in general and "rated corridors 1020.2.1" not in general


# Tables 716.1(2) and 716.1(3), typed row by row from the page images (PDF pp.184-186; never from the rules or the
# extracted text, which loses the stacked fractions): for each flag, each row's own words in the note (an anchor that
# starts the row's clause) and what the page prints for that row, each looked for only inside the row's own clause
# (up to the next ";" or sentence end outside brackets), so one row's numbers can't stand in for another's
CHART_716 = {
    "general.bc_table_716_1_2__exit_enclosures": [
        ("an interior exit ramp rated 2 hours", ["at least 1 1/2 hours"]),
        ("in such an enclosure rated 1 hour", ["exit access stairway or ramp enclosure", "exit passageway", "at least 1 hour"]),
        ("A vision panel", ["at most 100 square inches", "D-H-T-W-90 (2 hours)", "D-H-T-W-60 (1 hour)",
                            "D-H-90 or D-H-60 up to 100 square inches"]),
        ("sidelights and transoms", ["W-120", "W-60", "fire-protection-rated glazing is not permitted"])],
    "general.bc_table_716_1_2__corridors": [
        ("a door in a corridor wall rated 1 hour or 1/2 hour", ["at least 1/3 hour (20 minutes)", "D-20", "3/4 hour (D-H-OH-45) in a 1-hour wall",
                                                               "1/3 hour (D-H-OH-20) in a 1/2-hour wall"])],
    "general.bc_table_716_1_2__smoke_barriers": [
        ("smoke barriers rated 1 hour", ["at least 1/3 hour (20 minutes)", "D-20", "3/4 hour (D-H-OH-45)"])],
    "general.bc_table_716_1_2__other_assemblies": [
        ("fire walls and fire barriers rated 4 hours", ["a door rated 3 hours", "D-H-W-240, note a", "W-240"]),
        ("fire walls and fire barriers rated 3 hours", ["a door rated 3 hours", "note d", "D-H-W-180 only (note a)", "W-180 only"]),
        ("fire walls and fire barriers rated 2 hours", ["a door rated 1 1/2 hours", "D-H-90 up to 100 square inches or D-H-W-90 over",
                                                        "W-120 only"]),
        ("fire walls and fire barriers rated 1 1/2 hours", ["a door rated 1 1/2 hours",
                                                            "D-H-90 up to 100 square inches or D-H-W-90 over", "W-90 only"]),
        ("of 4 hours with each wall 3", ["a door rated 3 hours", "D-H-W-180 only (note a)", "W-180 only"]),
        ("double fire walls of 3 hours with each wall 2", ["a door rated 1 1/2 hours",
                                                            "D-H-90 up to 100 square inches or D-H-W-90 over", "W-120 only"]),
        ("double fire walls of 2 hours with each wall 1", ["a door rated 1 hour", "D-H-60 up to 100 square inches or D-H-W-60 over",
                                                            "W-60 only"]),
        ("horizontal exits in fire walls (note g", ["rated 4 hours, a door rated 3 hours",
                                                    "D-H-180 up to 100 square inches or D-H-W-240 over", "W-240 only"]),
        ("horizontal exits in fire walls rated 3 hours", ["a door rated 3 hours (note d)",
                                                          "D-H-180 up to 100 square inches or D-H-W-180 over", "W-180 only"]),
        ("other fire barriers rated 1 hour", ["a door rated 3/4 hour", "D-H-45", "rated 3/4 hour (D-H-45, note h)"]),
        ("other fire partitions rated 1 hour", ["a door rated 3/4 hour", "note i", "D-H-45", "rated 3/4 hour (D-H-45)"]),
        ("other fire partitions rated 1/2 hour", ["a door rated 1/3 hour", "D-H-20", "rated 1/3 hour (D-H-20)"]),
        ("exterior walls rated 3 hours", ["a door rated 1 1/2 hours", "D-H-90 up to 100 square inches or D-H-W-90 over",
                                          "W-180 only"]),
        ("exterior walls rated 2 hours", ["a door rated 1 1/2 hours", "D-H-90 or D-H-W-90 to the maximum size tested",
                                          "fire-protection-rated 1 1/2 hours (D-H-OH-90, note h)",
                                          "fire-resistance-rated 2 hours (W-120)"]),
        ("exterior walls rated 1 hour", ["a door rated 3/4 hour", "D-H-45", "rated 3/4 hour (D-H-45, note h)"]),
        ("Where sidelights are fire-resistance-rated only", ["fire-protection-rated glazing is not permitted"])],
    "general.bc_table_716_1_3__fire_windows": [
        ("a fire window in a fire wall or a fire barrier", ["is not permitted", "W with the wall's own rating"]),
        ("in atrium separations", ["(707.3.6)", "(707.3.7)", "(707.3.9) rated 1 hour, 3/4 hour (OH-45", "or W-60)"]),
        ("in fire partitions", ["rated 1 hour, 3/4 hour (OH-45 or W-60)", "rated 1/2 hour, 1/3 hour (OH-20 or W-30)"]),
        ("in smoke barriers", ["rated 1 hour, 3/4 hour (OH-45 or W-60)"]),
        ("in exterior walls", ["1 1/2 hours where rated over 1 hour", "3/4 hour where 1 hour", "1/3 hour where 1/2 hour"]),
        ("never in a party wall", [])],
}


def _clause(note: str, anchor: str) -> str:
    """The note's words from `anchor` to the end of its clause: the next ";" or ". " outside brackets."""
    i = note.index(anchor)
    depth = 0
    for j in range(i, len(note)):
        c = note[j]
        depth += (c == "(") - (c == ")")
        if depth == 0 and (c == ";" or note.startswith(". ", j)):
            return note[i:j]
    return note[i:]


def _chart_misses(notes: dict) -> list:
    out = []
    for rid, rows in CHART_716.items():
        note = " ".join(notes[rid].split())
        for anchor, values in rows:
            if anchor not in note:
                out.append((rid, anchor))
                continue
            clause = _clause(note, anchor)
            out += [(rid, anchor, v) for v in values if v not in clause]
    return out


def test_table_716s_flags_chart_match_the_page(book):
    """Part b review rounds 1 and 2's class: each row of Tables 716.1(2) and 716.1(3), typed from the page image, is in
    its flag's shown note with the rating and markings the page prints, inside that row's own clause (two rows had been
    read off the jumbled extracted text, and a first chart let one row's numbers stand in for another's)."""
    notes = {rid: _shown_note([r for r in book if r["id"] == rid][0]) for rid in CHART_716}
    assert _chart_misses(notes) == []


def test_the_chart_catches_a_row_changed(book):
    """The pin: each change review round 2 tried, made to a copy of the notes, is caught."""
    notes = {rid: " ".join(_shown_note([r for r in book if r["id"] == rid][0]).split()) for rid in CHART_716}
    other, windows, exits = ("general.bc_table_716_1_2__other_assemblies", "general.bc_table_716_1_3__fire_windows",
                             "general.bc_table_716_1_2__exit_enclosures")
    changes = [(other, "other fire partitions rated 1 hour, a door rated 3/4 hour", "other fire partitions rated 1 hour, a door rated 1/3 hour"),
               (windows, "(707.3.9) rated 1 hour, 3/4 hour", "(707.3.9) rated 1 hour, 1/3 hour"),
               (windows, "fire barrier is not permitted", "fire barrier is permitted"),
               (other, "of 4 hours with each wall 3, a door rated 3 hours, vision panel D-H-W-180 only", "of 4 hours with each wall 3, a door rated 3 hours, vision panel D-H-180"),
               (exits, "D-H-T-W-90", "D-H-W-90"),
               (other, "double fire walls of 2 hours with each wall 1, a door rated 1 hour, vision panel D-H-60", "double fire walls of 2 hours with each wall 1, a door rated 1 hour, vision panel D-H-90"),
               (exits, "D-H-T-W-90 (2 hours) or D-H-T-W-60 (1 hour)", "D-H-T-W-90 (1 hour) or D-H-T-W-60 (2 hours)"),
               (exits, "D-H-60 up to 100 square inches", "D-H-60 up to 200 square inches"),
               (other, "W-120 only; fire walls and fire barriers rated 1 1/2", "W-120; fire walls and fire barriers rated 1 1/2"),
               (other, "D-H-180 up to 100 square inches or D-H-W-240 over", "D-H-180 up to 100 square inches or D-H-W-180 over"),
               (other, "vision panel D-H-90 or D-H-W-90 to the maximum size tested", "vision panel to the maximum size tested"),
               ("general.bc_table_716_1_2__corridors", "(20 minutes)", "(45 minutes)")]
    for rid, a, b in changes:
        assert a in notes[rid], a
        assert _chart_misses({**notes, rid: notes[rid].replace(a, b)}), (rid, a)




def test_part_b_review_round_2s_notes_keep_their_sections_scope(book):
    """Part b review round 2: 716.2.1.3 is about corridor and smoke barrier door assemblies (its heading), and
    716.2.1.4's corridor and smoke barrier doors are examples, not the whole list (elevator lobby doors, 3006.3)."""
    glazing = _shown_note([r for r in book if r["id"] == "general.bc_716_2_1_3_transom_sidelight_glazing"][0])
    assert "in a corridor or a smoke barrier" in glazing
    smoke = _shown_note([r for r in book if r["id"] == "general.bc_716_2_1_4_smoke_draft_control_test"][0])
    assert "for one" in smoke and "3006.3" in smoke
