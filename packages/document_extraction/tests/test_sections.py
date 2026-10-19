"""The section splitter, on the real Chapter 325 text and on small made-up pages for each rule."""

import re
from collections import Counter
from pathlib import Path

import pytest

from document_extraction import sections
from document_extraction.sections import piece_keys, piece_text, split

REPO = Path(__file__).resolve().parents[3]
TEXT = REPO / "regulations/jurisdictions/new_york/ithaca_city/2_extracted_text"
LAW = TEXT / "chapter_325_zoning_2026-10.jsonl"


@pytest.fixture(scope="module")
def law():
    rows = sections.load_rows(LAW)
    return rows, split(rows)


def pieces_by_id(result):
    return {p["id"]: p for p in result["pieces"]}


def test_every_line_is_in_exactly_one_piece_or_furniture(law):
    rows, result = law
    owners = Counter(k for p in result["pieces"] for k in piece_keys(p)) + Counter(map(tuple, result["furniture"]))
    assert {(r["page"], r["line"]) for r in rows[1:]} == set(owners) and set(owners.values()) == {1}


def test_saved_sections_file_matches_a_fresh_split(law):
    rows, result = law
    assert (TEXT / "chapter_325_zoning_2026-10.sections.jsonl").read_text(encoding="utf-8") == \
        sections.to_jsonl(result, rows[0])


def test_every_section_in_the_table_of_contents_is_a_piece(law):
    rows, result = law
    by_id = pieces_by_id(result)
    toc = set(re.findall(r"§ 325-(\d+(?:\.\d+)*)\.", piece_text(rows, by_id["front_matter"])))
    found = {p["id"].removeprefix("325-") for p in result["pieces"] if p["kind"] == "section"}
    assert toc == found | {"31"}            # "§ 325-30. through § 325-31. (Reserved)" is one heading


@pytest.mark.parametrize("pid, starts", [
    ("325-16C", "C. Height and open space."),
    ("325-16B", "B. Ornamental and architectural features."),
    ("325-18A", "A. Porches and structures."),
    ("325-18B", "B. Projecting architectural features."),
    ("325-9B", "B. Applicability."),
    ("325-8A", "A. The District Regulations Chart is hereby made a part of this chapter."),
    ("325-19C", "C. Corner lot transition."),
    ("325-3B:height_of_building", "HEIGHT OF BUILDING — he vertical distance"),
    ("325-3B:grade_plane", "GRADE PLANE — A reference plane"),
    ("325-3B:story", "STORY — The portion of a building"),
    ("325-3B:basement", "BASEMENT — "),
    ("325-3B:cellar", "CELLAR — "),
    ("325-3B:building_area", "BUILDING AREA — "),
    ("325-3B:lot", "LOT — A portion or parcel of land"),
    ("325-3B:front_yard", "(1) FRONT YARD — "),
    ("325-3B:side_yard", "(2) SIDE YARD — "),
    ("325-3B:rear_yard", "(3) REAR YARD — "),
    ("325-3B:home_occupation", "HOME OCCUPATION —"),     # the term ends its line
])
def test_known_pieces_start_where_the_law_does(law, pid, starts):
    rows, result = law
    assert piece_text(rows, pieces_by_id(result)[pid]).startswith(starts)


def test_definitions_end_where_the_next_term_starts(law):
    rows, result = law
    assert "HOME OCCUPATION" not in piece_text(rows, pieces_by_id(result)["325-3B:height_of_building"])


def test_running_headers_are_furniture_not_law(law):
    rows, result = law
    assert not any(re.search(r"^§ 325-[\d.]+ (ZONING|ITHACA CODE) § ", piece_text(rows, p), re.M)
                   for p in result["pieces"])


# Small made-up documents: page 1 is a table of contents, the law starts on page 2.
def doc(*pages):
    """Made-up pages. Headings ("§ 9-2. ...", "A. ...") start at the 72-point margin and other lines at 96,
    as in the real code; a line given as (text, x0) sits where it says (e.g. a wrapped heading look-alike)."""
    rows = [{"file": "x.pdf", "sha256": "s"}]
    for n, lines in enumerate(pages, start=1):
        body = ["City of Ithaca, NY", f"§ 9-1 ZONING § 9-{n}", *lines, "Downloaded from https://ecode360.com/X on 2026-10-19"]
        for i, line in enumerate(body, start=1):
            text, x0 = line if isinstance(line, tuple) else (line, 72 if re.match(r"(§ |[A-Z]\. )", line) else 96)
            rows.append({"page": n, "line": i, "text": text, "x0": x0})
    return rows


TOC = ["Chapter 9", "§ 9-1. Title. § 9-2. Heights."]
START = ["ARTICLE I", "General", "§ 9-1. Title.", "This chapter is the Zoning law."]


def ids(rows):
    return [p["id"] for p in split(rows)["pieces"]]


def test_furniture_is_found_on_every_page():
    result = split(doc(TOC, START))
    assert result["furniture"] == [[1, 1], [1, 2], [1, 5], [2, 1], [2, 2], [2, 7]]


def test_a_wrapped_cross_reference_does_not_start_a_section():
    rows = doc(TOC, START + ["§ 9-2. Heights.", "A. Limit. As required by", "§ 9-1. above, no building may exceed 35 ft."])
    assert ids(rows) == ["front_matter", "9-1", "9-2", "9-2A"]


def test_wrapped_body_text_that_looks_like_a_heading_starts_nothing():
    rows = doc(TOC + ["§ 9-3. Fees."], START + ["§ 9-2. Heights.", "A. Limit. Fees are set in",
                                                ("§ 9-3. below, and no building may exceed 35 ft.", 96),
                                                ("B. below the eaves, a dormer may rise.", 96), "B. Yards.", "§ 9-3. Fees."])
    assert ids(rows) == ["front_matter", "9-1", "9-2", "9-2A", "9-2B", "9-3"]


def test_sections_missing_from_or_added_to_the_table_of_contents_are_reported():
    assert split(doc(TOC, START + ["§ 9-2. Heights."]))["problems"] == []
    assert split(doc(TOC + ["§ 9-4. Fees."], START + ["§ 9-2. Heights.", "§ 9-3. Yards."]))["problems"] == [
        "§ 9-4 is in the table of contents but no section starts with it",
        "§ 9-3 starts a section but isn't in the table of contents"]


def test_terms_may_have_lowercase_joining_words_dashes_and_asides(law):
    rows, result = law
    by_id = pieces_by_id(result)
    assert piece_text(rows, by_id["325-29.5B:significant_gap_in_coverage_or_significant_coverage_gap"]).startswith(
        "SIGNIFICANT GAP IN COVERAGE or SIGNIFICANT COVERAGE GAP — ")
    assert by_id["325-29.5B:type_i_iv_applications"]["title"] == "TYPE I – IV APPLICATIONS"
    assert "SIGNIFICANT GAP" not in piece_text(rows, by_id["325-29.5B:shot_clock"])


def test_the_real_law_matches_its_table_of_contents(law):
    assert law[1]["problems"] == []


def test_subsection_letters_must_come_in_order_and_breaks_are_reported():
    rows = doc(TOC, START + ["§ 9-2. Heights.", "B. Not a heading.", "A. Limit.", "C. Skipped B.", "B. Second."])
    result = split(rows)
    assert [p["id"] for p in result["pieces"]] == ["front_matter", "9-1", "9-2", "9-2A", "9-2B"]
    assert result["problems"] == [
        "p.2 line 8: looks like subsection B of 9-2 but A was expected; check how this part was cut",
        "p.2 line 10: looks like subsection C of 9-2 but B was expected; check how this part was cut"]


def test_a_false_subsection_at_the_margin_is_reported_through_the_real_one():
    # A section's own text sits at the margin; its wrapped line starting "A. " opens a false subsection,
    # so the real "A." after it is out of order, and reported.
    rows = doc(TOC, START + ["§ 9-2. Heights. No building may exceed the limit in Subsection", "A. below.", "A. Limit."])
    assert split(rows)["problems"] == ["p.2 line 9: looks like subsection A of 9-2 but B was expected; check how this part was cut"]


def test_a_section_heading_out_of_order_is_reported():
    rows = doc(TOC, START + ["§ 9-2. Heights.", "§ 9-1. Title, again."])
    assert split(rows)["problems"][0] == "p.2 line 8: looks like a section heading but doesn't follow 9-2; check how this part was cut"


def test_editors_notes_are_cut_out_of_the_section_around_them():
    rows = doc(TOC, START + ["1. Editor's Note: See Ch. 210."], ["more of section 1"])
    result = pieces_by_id(split(rows))
    assert result["9-1"]["lines"] == [[2, 3, 6], [3, 3, 3]] and result["editors_note_1"]["lines"] == [[2, 7, 7]]


def test_terms_start_pieces_only_in_a_definitions_section():
    rows = doc(TOC, START + ["§ 9-2. Definitions.", "ALLEY — A narrow way.", "§ 9-3. Heights.", "ALLEY — not a definition here."])
    assert ids(rows) == ["front_matter", "9-1", "9-2", "9-2:alley", "9-3"]


def test_a_sentence_with_a_dash_is_not_a_term():
    rows = doc(TOC, START + ["§ 9-2. Definitions.", "ALLEY — A narrow way.", "Such ways — if paved — are alleys.",
                             "DOORS and ENTRIES — Openings."])
    assert ids(rows) == ["front_matter", "9-1", "9-2", "9-2:alley", "9-2:doors_and_entries"]


def test_an_article_heading_joins_the_section_after_it():
    rows = doc(TOC, START + ["ARTICLE II", "Heights", "§ 9-2. Heights."])
    assert pieces_by_id(split(rows))["9-2"]["lines"] == [[2, 7, 9]]
