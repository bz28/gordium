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
# and 705.9.5's exceptions), an ambulatory care facility (709.5.1)
NARROWED_BY = {"corridor_fire_rating_hours", "sprinklered_903_3_1_1", "sprinklered_903_3_1_2", "occupancy_group",
               "ambulatory_care_facility"}


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


# lines brought_in.misread empties (a stacked fraction's denominator put back on the line above: p.190 line 45,
# 716.3.4's "1/2"; p.182 line 12, 714.5.2's "1/8"): nothing on them to quote
EMPTIED = {(int(w.split()[0][2:]), int(w.split()[2]))
           for w, fixes in load(NY / "1_source_documents/sources.yaml")["documents"][0]["brought_in"]["misread"].items()
           if any(f.get("printed") == "" for f in fixes)}


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
        quoted |= EMPTIED                       # a line the misreads empty holds nothing to quote
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
    assert sorted(narrowed) == ["general.bc_705_9_5_vertical_separation", "general.bc_709_5_1_i2_smoke_barrier_doors", "general.bc_710_5_3_i2_pass_through_openings",
                                "general.bc_716_2_2_3_exit_enclosure_door_temperature_rise",
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
    sit together after 508's and before Chapter 10's first rule (1004.7), Chapter 9's block between them
    (test_ny_building_chapter_9.py, 2026-11-27)."""
    ids = [r["id"] for r in book]
    seven = [i for i, rid in enumerate(ids) if re.match(r"general\.bc_(table_)?7\d\d_", rid)]
    assert seven == list(range(seven[0], seven[-1] + 1))
    after = ids[seven[-1] + 1]
    assert after == "general.bc_1004_7_outdoor_areas" or re.match(r"general\.bc_(table_)?9\d\d_", after)
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


def test_part_cs_group_i2_flags_never_set_aside_an_i2_or_unstated_building(book, ctx):
    """709.5.1 (Groups I-1 and I-2 and ambulatory care smoke barrier doors) and 710.5.3 (Group I-2 Condition 2 pass-through
    openings) are set aside only where the stated group rules them out: Group I-2, a building of two or more groups,
    no group stated, or (709.5.1) an ambulatory care facility stated or not ruled out, all need review."""
    allowed = ctx.allowed()
    doors, passes = ([r for r in book if r["id"] == i][0] for i in
                     ("general.bc_709_5_1_i2_smoke_barrier_doors", "general.bc_710_5_3_i2_pass_through_openings"))
    for given in ({}, {"occupancy_group": "I-2"}, {"occupancy_group": "mixed"}):
        assert outcome(doors, given, allowed) == "needs_review" and outcome(passes, given, allowed) == "needs_review"
    for group in ("B", "R-2", "A-3"):
        assert outcome(doors, {"occupancy_group": group}, allowed) == "needs_review", group      # ambulatory unstated
        assert outcome(doors, {"occupancy_group": group, "ambulatory_care_facility": True}, allowed) == "needs_review"
        assert outcome(doors, {"occupancy_group": group, "ambulatory_care_facility": False}, allowed) == "not_applicable"
        assert outcome(passes, {"occupancy_group": group}, allowed) == "not_applicable"


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
        ("in such an enclosure rated 1 hour", ["exit access stairway or ramp enclosure", "exit passageway's walls rated 1 hour",
                                               "at least 1 hour"]),
        ("A vision panel", ["at most 100 square inches (note b: a marking's W is the glazing's fire-resistance rating, not the frame's)", "D-H-T-W-90 (2 hours)", "D-H-T-W-60 (1 hour)",
                            "D-H-90 or D-H-60 up to 100 square inches"]),
        ("sidelights and transoms", ["fire-resistance-rated glazing only (W-120 or W-60)", "fire-protection-rated glazing is not permitted"]),
        ("note a allows", ["per 716.1.2.3 in the maximum size tested", "note c the markings of 716.1.2.2.1"])],
    "general.bc_table_716_1_2__corridors": [
        ("a door in a corridor wall rated 1 hour or 1/2 hour", ["at least 1/3 hour (20 minutes)", "D-20 to the maximum size tested", "3/4 hour (D-H-OH-45) in a 1-hour wall",
                                                               "1/3 hour (D-H-OH-20) in a 1/2-hour wall"]),
        ("note a allows", ["per 716.1.2.3 in the maximum size tested", "note c the markings of 716.1.2.2.1",
                           "not the frame's"])],
    "general.bc_table_716_1_2__smoke_barriers": [
        ("smoke barriers rated 1 hour", ["at least 1/3 hour (20 minutes)", "D-20 to the maximum size tested",
                                          "3/4 hour (D-H-OH-45)"]),
        ("note a allows", ["per 716.1.2.3 in the maximum size tested", "note c the markings of 716.1.2.2.1",
                           "not the frame's"])],
    "general.bc_table_716_1_2__other_assemblies": [
        ("fire walls and fire barriers rated 4 hours", ["a door rated 3 hours", "fire-resistance-rated glazing only (D-H-W-240, note a)",
                                                        "sidelights fire-resistance-rated only (W-240)"]),
        ("fire walls and fire barriers rated 3 hours", ["a door rated 3 hours", "two 1 1/2-hour doors", "in a fire wall count as one", "note d", "D-H-W-180 only (note a)",
                                                        "sidelights W-180 only"]),
        ("fire walls and fire barriers rated 2 hours", ["a door rated 1 1/2 hours", "D-H-90 up to 100 square inches or D-H-W-90 over",
                                                        "W-120 only"]),
        ("fire walls and fire barriers rated 1 1/2 hours", ["a door rated 1 1/2 hours",
                                                            "D-H-90 up to 100 square inches or D-H-W-90 over", "W-90 only"]),
        ("of 4 hours with each wall 3,", ["a door rated 3 hours", "D-H-W-180 only (note a)", "sidelights W-180 only"]),
        ("double fire walls per NFPA 221", ["note e, 706.4", "note f, NFPA 221's 4.6"]),
        ("double fire walls of 3 hours with each wall 2,", ["a door rated 1 1/2 hours",
                                                            "D-H-90 up to 100 square inches or D-H-W-90 over", "W-120 only"]),
        ("double fire walls of 2 hours with each wall 1,", ["a door rated 1 hour", "D-H-60 up to 100 square inches or D-H-W-60 over",
                                                            "W-60 only"]),
        ("horizontal exits in fire walls (note g", ["rated 4 hours, a door rated 3 hours",
                                                    "D-H-180 up to 100 square inches or D-H-W-240 over", "W-240 only"]),
        ("horizontal exits in fire walls rated 3 hours", ["a door rated 3 hours (note d)",
                                                          "D-H-180 up to 100 square inches or D-H-W-180 over", "W-180 only"]),
        ("other fire barriers rated 1 hour", ["a door rated 3/4 hour", "vision panel D-H-45 to the maximum size tested",
                                              "rated 3/4 hour (D-H-45, note h)"]),
        ("other fire partitions rated 1 hour", ["a door rated 3/4 hour", "two 20-minute doors", "one 45-minute door", "note i", "vision panel D-H-45 to the maximum size tested",
                                                "rated 3/4 hour (D-H-45)"]),
        ("other fire partitions rated 1/2 hour", ["a door rated 1/3 hour", "vision panel D-H-20 to the maximum size tested",
                                                  "rated 1/3 hour (D-H-20)"]),
        ("exterior walls rated 3 hours", ["a door rated 1 1/2 hours", "D-H-90 up to 100 square inches or D-H-W-90 over",
                                          "W-180 only"]),
        ("exterior walls rated 2 hours", ["a door rated 1 1/2 hours", "D-H-90 or D-H-W-90 to the maximum size tested",
                                          "fire-protection-rated 1 1/2 hours (D-H-OH-90, note h)",
                                          "fire-resistance-rated 2 hours (W-120)"]),
        ("exterior walls rated 1 hour", ["a door rated 3/4 hour", "vision panel D-H-45 to the maximum size tested",
                                         "rated 3/4 hour (D-H-45, note h)"]),
        ("Note a:", ["ASTM E119 per 716.1.2.3, in the maximum size tested"]),
        ("Note b:", ["W is the glazing's fire-resistance rating, not the frame's"]),
        ("note c: the markings", ["716.1.2.2.1 and Table 716.1(1) are permitted"]),
        ("Where sidelights are fire-resistance-rated only", ["fire-protection-rated glazing is not permitted"])],
    "general.bc_table_716_1_3__fire_windows": [
        ("a fire window in a fire wall or a fire barrier", ["is not permitted", "W with the wall's own rating", "(notes a, b)"]),
        ("in atrium separations", ["(707.3.6)", "(707.3.7)", "(707.3.9) rated 1 hour, 3/4 hour (OH-45, not where the Fire Code's 1207 encloses energy storage systems, note c, or W-60)"]),
        ("in fire partitions", ["rated 1 hour, 3/4 hour (OH-45 or W-60)", "rated 1/2 hour, 1/3 hour (OH-20 or W-30)"]),
        ("in smoke barriers", ["rated 1 hour, 3/4 hour (OH-45 or W-60)"]),
        ("in exterior walls", ["1 1/2 hours (OH-90, or W with the wall's rating) where rated over 1 hour",
                               "3/4 hour (OH-45 or W-60) where 1 hour", "1/3 hour (OH-20 or W-30) where 1/2 hour"]),
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
               (other, "sidelights fire-resistance-rated only (W-240)", "sidelights fire-resistance-rated only (W-180)"),
               (other, "note a), sidelights W-180 only; fire walls and fire barriers rated 2",
                "note a), sidelights W-120 only; fire walls and fire barriers rated 2"),
               (other, "each wall 3, a door rated 3 hours, vision panel D-H-W-180 only (note a), sidelights W-180 only",
                "each wall 3, a door rated 3 hours, vision panel D-H-W-180 only (note a), sidelights W-120 only"),
               (other, "a door rated 3/4 hour, vision panel D-H-45 to the maximum", "a door rated 3/4 hour, vision panel D-H-20 to the maximum"),
               (other, "note i), vision panel D-H-45", "note i), vision panel D-H-20"),
               (other, "a door rated 1/3 hour, vision panel D-H-20", "a door rated 1/3 hour, vision panel D-H-45"),
               (other, "exterior walls rated 1 hour, a door rated 3/4 hour, vision panel D-H-45",
                "exterior walls rated 1 hour, a door rated 3/4 hour, vision panel D-H-20"),
               (other, "note e, 706.4", "note f, 706.4"),
               (exits, "exit passageway's walls rated 1 hour", "exit passageway's walls rated 2 hours"),
               (exits, "square inches (note b:", "square inches (note c:"),
               ("general.bc_table_716_1_2__smoke_barriers", "not the frame's", "not the glazing's"),
               (other, "Note b: a vision panel marking's W is the glazing's", "Note b: a vision panel marking's W is the frame's"),
               ("general.bc_table_716_1_2__corridors", "D-20 to the maximum size tested", "D-20 up to 100 square inches"),
               ("general.bc_table_716_1_2__smoke_barriers", "D-20 to the maximum size tested", "D-20 up to 100 square inches"),
               (other, "vision panel D-H-45 to the maximum size tested", "vision panel D-H-45 up to 100 square inches"),
               (other, "with each wall 2, a door", "with each wall 2 1/2, a door"),
               (windows, "(notes a, b)", "(notes a, c)"),
               (windows, "OH-45, not where", "OH-45, where"),
               (exits, "fire-resistance-rated glazing only (W-120", "fire-protection-rated glazing only (W-120"),
               (other, "two 1 1/2-hour doors", "two 1-hour doors"),
               (other, "two 20-minute doors", "two 30-minute doors"),
               (windows, "(OH-20 or W-30) where 1/2 hour", "(OH-20 or W-20) where 1/2 hour"),
               (exits, "note a allows", "note b allows"),
               (exits, "per 716.1.2.3 in the maximum size tested,", "per 716.1.2.3,"),
               (other, "in a fire wall count as one", "count as one"),
               (other, "note i), vision panel D-H-45 to the maximum size tested", "note i), vision panel D-H-45"),
               (other, "Note a: fire-resistance-rated glazing tested to ASTM E119 per 716.1.2.3, in the maximum size tested",
                "Note a: fire-resistance-rated glazing tested to ASTM E119 per 716.1.2.3"),
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


def test_709_5_1_reaches_group_i1_through_709_5s_exception(book, ctx):
    """Part c review round 1 (P1): 709.5 exception 1 sends Group I-1 Condition 2's pair of corridor doors to 709.5.1, and
    Condition 2 isn't a stated fact, so a stated Group I-1 never sets 709.5.1 aside."""
    doors = [r for r in book if r["id"] == "general.bc_709_5_1_i2_smoke_barrier_doors"][0]
    assert outcome(doors, {"occupancy_group": "I-1", "ambulatory_care_facility": False}, ctx.allowed()) == "needs_review"


def test_part_c_review_round_2s_wording(book):
    """Part c review round 2: 709.5.1's title keeps ambulatory care facilities (an R-2 or B building sees it only for
    them); 709.4's support exception reads 'except in' Types IIB, IIIB and VB (not 'only in'); 708.6's and 709.5's
    openings name Table 716.1(3)'s windows as well as Table 716.1(2)'s doors."""
    rules = {r["id"]: r for r in book}
    assert "ambulatory care" in rules["general.bc_709_5_1_i2_smoke_barrier_doors"]["title"]
    assert "except in buildings of Types IIB, IIIB and VB" in _shown_note(rules["general.bc_709_4_smoke_barrier_continuity"])
    for rid in ("general.bc_708_6_fire_partition_openings", "general.bc_709_5_smoke_barrier_openings"):
        assert "OH-45" in " ".join(_shown_note(rules[rid]).split()), rid
    labels = load(LABELS)["labels"]                                     # review round 3: the labels and the note's end
    for pid in ("708.6", "709.5"):
        assert "OH-45" in " ".join(labels[pid]["reason"].split()), pid
    assert "windows' ratings" in _shown_note(rules["general.bc_709_5_smoke_barrier_openings"])
    assert "1/3 hour (D-H-20) in a 1/2-hour one" in " ".join(_shown_note(rules["general.bc_708_6_fire_partition_openings"]).split())


def test_no_chapter_7_note_calls_a_brought_in_section_not_brought_in(book):
    """Part d review round 1's class: a Chapter 7 rule's notes never say a section "isn't" or "aren't brought in" once
    the folder brings it in (or brings in parts of it: "711 isn't brought in" after 711.2.2 is), so the record a person
    reads stays true as later parts land."""
    rows = [json.loads(line) for line in SECTIONS.read_text(encoding="utf-8").splitlines()]
    pieces_all = {p["id"] for p in rows[1:]}
    bad = []
    for r in book:
        if not re.match(r"general\.bc_(table_)?7\d\d_", r["id"]):
            continue
        for clause in re.split(r"[;.] ", " ".join(str(r.get("notes", "")).split())):
            if re.search(r"\b(?:isn't|aren't) brought in", clause):
                said = clause.split(" brought in")[0]
                bad += [(r["id"], t) for t in _named(said) if _brought_in(t, pieces_all)]
    assert not bad, bad


def test_part_d_review_round_1s_notes(book, labels):
    """Part d review round 1: 714.4.1's concrete fill may be the thickness that keeps the rating; 714.4.2 exception 4
    keeps its 0.01 inch of water and its listing; 714.4.1.1 and 714.4.1.2 each name the other, two ways to comply; rated
    floors' penetrations (714.5 to 714.5.4) are brought in as flags, since rated floors top and bottom exit enclosures."""
    rules = {r["id"]: r for r in book}
    assert "thickness that keeps its rating" in _shown_note(rules["general.bc_714_4_1_through_penetrations"])
    membrane = " ".join(_shown_note(rules["general.bc_714_4_2_membrane_penetrations"]).split())
    assert "positive pressure differential of at least 0.01 inch of water" in membrane and "installed per their listing" in membrane
    one, two = (_shown_note(rules[i]) for i in ("general.bc_714_4_1_1_tested_assembly_penetrations",
                                                 "general.bc_714_4_1_2_through_penetration_firestop"))
    assert "714.4.1.2" in one and "714.4.1.1" in two and not two.startswith("Or")
    for pid in ("714.5", "714.5.1", "714.5.1.1", "714.5.1.2", "714.5.2", "714.5.3", "714.5.4"):
        assert labels[pid]["label"] == "flag" and _flags(book, pid), pid


def test_part_d_review_round_2s_notes(book):
    """Part d review round 2: 714.5.1's exception 2 and 714.5.1.2's exception 4 name only steel, ferrous or copper
    conduits, pipes, tubes or vents (never concrete or masonry items); switchgear penetrated directly; 714.5.2's and
    714.4.2's listed boxes and luminaires installed per their listing; 714.4.1's positive pressure."""
    rules = {r["id"]: r for r in book}
    def shown(rid):
        return " ".join(_shown_note(rules[rid]).split())
    floor = shown("general.bc_714_5_1_floor_through_penetrations")
    assert "such items at most" not in floor and "copper conduits, pipes, tubes or vents at most 6 inches through a single" in floor
    firestop = shown("general.bc_714_5_1_2_floor_firestop_systems")
    assert "penetrating directly into metal-enclosed electrical power switchgear" in firestop
    assert "copper conduits, pipes, tubes or vents at most 6 inches through a single concrete floor" in firestop
    membrane = shown("general.bc_714_5_2_floor_membrane_penetrations")
    assert "protected with listed materials" in membrane and membrane.count("installed per their listing") >= 2
    assert "wall opening protective material system for use in fire-resistance-rated assemblies, installed per their listing" \
        in shown("general.bc_714_4_2_membrane_penetrations")
    assert "positive pressure differential" in shown("general.bc_714_4_1_through_penetrations")


def test_part_d_review_round_3s_notes_and_labels(book, labels):
    """Part d review round 3: 714.4.2's exceptions 2 and 6 keep "tested for use in fire-resistance-rated assemblies",
    "unless listed otherwise" and "installed per the listing"; the firestop systems are installed as tested; and, the
    class, each part d flag's label reason says what its note says (a label lagged its note twice)."""
    rules = {r["id"]: r for r in book}
    def shown(rid):
        return " ".join(_shown_note(rules[rid]).split())
    membrane = shown("general.bc_714_4_2_membrane_penetrations")
    assert "tested for use in fire-resistance-rated assemblies, installed per their listing (1/8 inch unless listed otherwise" in membrane
    assert "other listed materials and methods, installed per the listing" in membrane
    assert "installed as tested per ASTM E814" in shown("general.bc_714_4_1_2_through_penetration_firestop")
    for rid in ("general.bc_714_5_1_2_floor_firestop_systems", "general.bc_714_5_4_smoke_barrier_penetrations"):
        assert "installed and tested per" in shown(rid), rid
    for pid, v in labels.items():
        if v["label"] == "flag" and re.match(r"71[124]\.", pid):
            rid = re.search(r"\((general\.bc_[a-z0-9_]+)\)\.?$", " ".join(v["reason"].split())).group(1)
            head = " ".join(v["reason"].split()).rsplit(": a person's check", 1)[0]
            assert shown(rid).startswith(head), pid


def test_part_d_review_round_4s_notes(book):
    """Part d review round 4, as a class over 714's notes: every firestop system is approved and installed as (or and)
    tested; every escutcheon is a metal escutcheon plate; every listed electrical box is tested for use in
    fire-resistance-rated assemblies and installed per its listing."""
    for r in book:
        if not re.match(r"general\.bc_714_", r["id"]):
            continue
        note = " ".join(_shown_note(r).split())
        assert not re.search(r"(?<!installed as )(?<!installed and )tested per (?:ASTM E814|UL 1479)", note), r["id"]
        assert "escutcheon" not in note or "metal escutcheon plate" in note, r["id"]
        assert "listed electrical boxes tested for rated assemblies" not in note, r["id"]
        assert not re.search(r"(?<!listed )putty pads", note), r["id"]                      # review round 5
        assert "cellulose" not in note or "cellulose loose-fill" in note, r["id"]
        assert not re.search(r"(?<!solid )fireblock", note), r["id"]


# Tables 705.5 and 705.9, typed row by row from the page images (PDF pp.165-167; never from the rules or the extracted
# text): each row's own words in the flag's note (an anchor that starts the row's clause) and what the page prints for
# that row, each looked for only inside the row's own clause, as CHART_716
CHART_705 = {
    "general.bc_table_705_2_projection_distances": [
        ("0 to less than 2", ["projections not permitted"]),
        ("2 to less than 3", ["24 inches"]),
        ("3 to less than 5", ["two-thirds of the FSD"]),
        ("5 or greater", ["40 inches"])],
    "general.bc_table_705_5_exterior_wall_ratings": [
        ("in three columns", ["Group H (note e)", "Groups F-1, M and S-1 (note f)",
                              "Groups A, B, E, F-2, I, R (note i), S-2 and U (note h)"]),
        ("X less than 5 (note b)", ["every type 3, 2 and 1"]),
        ("X 5 or more and less than 10", ["Types IA and IVA 3, 2 and 1", "other types 2, 1 and 1"]),
        ("X 10 or more and less than 30", ["Types IA, IB, IVA and IVB 2, 1 and 1 (note c)", "Types IIB and VB 1, 0 and 0",
                                           "other types 1, 1 and 1 (note c)"]),
        ("X 30 or more", ["every type 0, 0 and 0"]),
        ("Note a:", ["load-bearing exterior walls also meet Table 601"]),
        ("Note c:", ["open parking garages complying with 406 need no rating"]),
        ("Note g:", ["unlimited unprotected openings, the rating is 0 hours"]),
        ("Note h:", ["only a Group U private garage or carport", "5 feet or more"]),
        ("Note i:", ["Group R-3 building of Type II-B or V-B", "5 feet or more"])],
    "general.bc_table_705_9_exterior_wall_openings": [
        ("unprotected in a building not sprinklered", ["903.3.1.1 (UP, NS)"]),
        ("unprotected in a building sprinklered", ["903.3.1.1 (UP, S, note i: not for Groups H-1, H-2 and H-3",
                                                  "an NFPA 13R or 13D system is not 903.3.1.1's"]),
        ("0 to less than 3 (notes b, c, k)", ["UP, NS, UP, S and P all not permitted (note k)"]),
        ("3 to less than 5 (notes d, e)", ["UP, NS not permitted", "UP, S 15%", "P 15%"]),
        ("5 to less than 10 (notes e, f, j)", ["UP, NS 10% (note h)", "UP, S 25%", "P 25%"]),
        ("10 to less than 15 (notes e, f, g, j)", ["UP, NS 15% (note h)", "UP, S 45%", "P 45%"]),
        ("15 to less than 20 (notes f, g, j)", ["UP, NS 25%", "UP, S 75%", "P 75%"]),
        ("20 to less than 25 (notes f, g, j)", ["UP, NS 45%", "UP, S no limit", "P no limit"]),
        ("25 to less than 30 (notes f, g, j)", ["UP, NS 70%", "UP, S no limit", "P no limit"]),
        ("30 or greater", ["no limit for each"]),
        ("Note d:", ["at most 25 percent", "Group R-3"]),
        ("Note e:", ["less than 15 feet for Group H-2 and H-3"]),
        ("Note f:", ["no limit", "Group R-3", "5 feet or more"]),
        ("Note g:", ["open parking garage per 406.5", "10 feet or more"]),
        ("Note j:", ["only a Group U private garage or carport", "5 feet or more"]),
        ("Note k:", ["705.3 exception 2"])],
}


def _chart_705_misses(notes: dict) -> list:
    out = []
    for rid, rows in CHART_705.items():
        note = " ".join(notes[rid].split())
        for anchor, values in rows:
            if anchor not in note:
                out.append((rid, anchor))
                continue
            clause = _clause(note, anchor)
            out += [(rid, anchor, v) for v in values if v not in clause]
    return out


def test_table_705s_flags_chart_match_the_page(book):
    """Part e1: each row of Tables 705.5 and 705.9, typed from the page images, is in its flag's shown note with the
    hours or percentages the page prints, inside that row's own clause; Table 705.9's sprinklered column is
    903.3.1.1's alone (its UP, S key), so the note says an NFPA 13R system is not one."""
    notes = {rid: _shown_note([r for r in book if r["id"] == rid][0]) for rid in CHART_705}
    assert _chart_705_misses(notes) == []


def test_the_705_chart_catches_a_row_changed(book):
    """The pin: a cell, a note letter or a column changed in a copy of the notes is caught."""
    notes = {rid: " ".join(_shown_note([r for r in book if r["id"] == rid][0]).split()) for rid in CHART_705}
    ratings, openings = "general.bc_table_705_5_exterior_wall_ratings", "general.bc_table_705_9_exterior_wall_openings"
    changes = [(ratings, "Types IA and IVA 3, 2 and 1", "Types IA and IVA 2, 2 and 1"),
               (ratings, "other types 2, 1 and 1;", "other types 1, 1 and 1;"),
               (ratings, "Types IIB and VB 1, 0 and 0", "Types IIB and VB 1, 1 and 0"),
               (ratings, "IVB 2, 1 and 1 (note c)", "IVB 2, 1 and 1"),
               (ratings, "every type 3, 2 and 1", "every type 2, 2 and 1"),
               (ratings, "every type 0, 0 and 0", "every type 1, 0 and 0"),
               (ratings, "R (note i), S-2", "R, S-2"),
               (openings, "UP, NS 10% (note h)", "UP, NS 15% (note h)"),
               (openings, "UP, S 45%, P 45%", "UP, S 45%, P 75%"),
               (openings, "UP, NS 70%", "UP, NS 45%"),
               (openings, "UP, NS not permitted, UP, S 15%", "UP, NS 15%, UP, S 15%"),
               (openings, "UP, S 75%", "UP, S no limit"),
               (openings, "an NFPA 13R or 13D system is not 903.3.1.1's", "an NFPA 13D system is not 903.3.1.1's"),
               ("general.bc_table_705_2_projection_distances", "5 or greater, 40 inches", "5 or greater, 24 inches"),
               ("general.bc_table_705_2_projection_distances", "2 to less than 3, 24 inches", "2 to less than 3, 40 inches")]
    for rid, a, b in changes:
        assert a in notes[rid], a
        assert _chart_705_misses({**notes, rid: notes[rid].replace(a, b, 1)}), (rid, a)


def test_705_9_5s_exceptions_need_a_stated_fact(book, ctx):
    """705.9.5's vertical separation is set aside only where the architect states a sprinkler system throughout per
    903.3.1.1, or per 903.3.1.2 in Group R (an NFPA 13R system counts only where 903.3.1.2 allows it); a 13R system in
    another group or a building of two or more groups, no system, or nothing stated, leave it a person's check, never
    not applicable. Exception 1 (three stories or less) stays in the flag's words: the stories set nothing aside."""
    [r] = [r for r in book if r["id"] == "general.bc_705_9_5_vertical_separation"]
    allowed = ctx.allowed()
    for group in ("R-1", "R-2", "R-3", "R-4"):
        assert outcome(r, {"sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": True, "occupancy_group": group},
                       allowed) == "not_applicable", group
    for group in ("B", "M", "I-2", "mixed"):
        assert outcome(r, {"sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": True, "occupancy_group": group},
                       allowed) == "needs_review", group
        assert outcome(r, {"sprinklered_903_3_1_1": True, "occupancy_group": group}, allowed) == "not_applicable", group
    for given in ({}, {"occupancy_group": "R-2"}, {"sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": False,
                                                   "occupancy_group": "R-2"}, {"sprinklered_903_3_1_2": True},
                  {"sprinklered_903_3_1_1": False, "occupancy_group": "B", "stories_above_grade_plane": 2}):
        assert outcome(r, given, allowed) == "needs_review", given
    note = " ".join(_shown_note(r).split())
    assert "three stories or less above grade plane" in note and "open parking garages" in note


def test_705_2s_projections_reach_egress_balconies_and_exterior_exit_stairways(book, labels):
    """Review round 1 of part e1: exterior egress balconies and exterior exit stairways are projections (705.2 adds 1021
    and 1027 to its own requirements, never replaces them), so 705.2 to 705.2.3.1 and Table 705.2 are brought in as
    flags; 705.2.3.1's note keeps the balconies' 50 percent of the perimeter and the fire-retardant-treated wood
    allowance only for exterior stairways "not used as required exits"."""
    rules = {r["id"]: r for r in book}
    for pid in ("705.2", "Table 705.2", "705.2.1", "705.2.2", "705.2.3", "705.2.3.1"):
        assert labels[pid]["label"] == "flag" and _flags(book, pid), pid
    balconies = " ".join(_shown_note(rules["general.bc_705_2_3_1_balconies"]).split())
    assert "50 percent of the building's perimeter on each floor" in balconies
    assert "exterior stairways not used as required exits" in balconies
    assert "1021 and 1027" in _shown_note(rules["general.bc_705_2_projections"])


def test_the_readmes_rule_count_is_the_rulebooks():
    """Review round 1 of part e1: the README's count of hand-drafted rules and flags is the rulebook's own."""
    rules = load(RULEBOOK)["rules"]
    flags = sum(r["kind"] == "flag" for r in rules)
    readme = " ".join((NY / "README.md").read_text(encoding="utf-8").split())
    assert f"{len(rules)} hand-drafted (drafts: approval is deferred): {len(rules) - flags} rules and {flags} flags" in readme


def test_part_e2s_notes_keep_the_laws_limits(book, labels):
    """Part e2: the rest of Section 716 as egress doors and windows use it. Each piece of 716.2.5 to 716.4 brought in is
    labeled, its flags' notes keep the numbers and conditions the page prints (100 square inches, 20 minutes, 3/4 hour,
    the 10-second delay, 25 percent, 12 feet, 716.3.4's 1/2-hour partitions read through its stacked fraction), and
    716.2.6.1's exception 1 stays Group R-1's alone; the parts left out are named in the README's list."""
    rules = {r["id"]: r for r in book}
    def shown(rid):
        return " ".join(_shown_note(rules[rid]).split())
    want = {"general.bc_716_2_5_1_2_1_horizontal_exit_vision_panels": ["self-closing swinging", "limited to 100 square inches"],
            "general.bc_716_2_5_1_2_2_fire_barrier_door_glazing": ["1 1/2-hour fire protection rating", "limited to 100 square inches"],
            "general.bc_716_2_5_3_corridor_door_glazing": ["at least 20 minutes", "exempt from the hose stream test"],
            "general.bc_716_2_5_4_transoms_and_sidelights": ["3/4 hour or less", "2-hour fire-resistance-rated exterior walls",
                                                              "more than 3/4 hour"],
            "general.bc_716_2_6_1_door_closing": ["latching and self-closing or automatic-closing",
                                                  "dwelling units or sleeping units in Group R-1"],
            "general.bc_716_2_6_6_smoke_activated_doors": ["no more than 10 seconds", "loss of power"],
            "general.bc_716_3_2_1_2_fire_window_area": ["at most 25 percent of the area of a common wall"],
            "general.bc_716_3_3_1_window_mullions": ["more than 12 feet"],
            "general.bc_716_3_4_fire_window_glazing": ["at least 3/4 hour", "1/2-hour fire-resistance-rated partitions may have a 20-minute"]}
    for rid, words in want.items():
        for w in words:
            assert w in shown(rid), (rid, w)
    for pid in ("716.2.5.1.2.1", "716.2.6.1", "716.2.6.6", "716.2.9.1", "716.3.4", "716.4.3"):
        assert labels[pid]["label"] == "flag" and _flags(book, pid), pid
    readme = (NY / "README.md").read_text(encoding="utf-8")
    left_out = readme.split("## References in the brought-in sections that are not brought in", 1)[1]
    assert "716.2.5.4.1, 716.2.6.3, 716.2.7, 716.2.8 and 716.3.2.1.1.1" in left_out
