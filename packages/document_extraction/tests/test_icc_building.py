"""The 2025 Building Code of New York State cut as ICC prints it (icc_sections.py, style bcnys_2025): sections without
letters (1017), tags of one letter ([F]), "CHAPTER" alone as a chapter's first line, tables printed where they fit
(their lines named in sources.yaml), a subscript or a unit's powers that look like a fraction left apart, two terms the
text reads alike, and a raised footnote letter the text runs into a table's cell (book_text.as_printed). Built lines,
so each safeguard is tested on its own, without the copyrighted book. Decided:
docs/decisions/2026-11-21_ny_building_code.md."""

from document_extraction import icc_sections
from document_extraction.book_text import as_printed
from document_extraction.numbers import shown, statements

STYLE = "bcnys_2025"


def _row(page, line, text, bold=None, italic=()):
    r = {"page": page, "line": line, "text": text}
    if bold:
        r["bold"] = [[0, len(bold)]]
    if italic:
        r["italic"] = [[text.index(w), text.index(w) + len(w)] for w in italic]
    return r


def _book(extra_p1=(), extra_p2=()):
    """Two pages of a made-up Building Code: Chapter 2's definitions on p.1, then Chapter 10 on p.2 with a table
    printed inside 1017.2.1, the text of which runs on after it."""
    return [{"file": "book.pdf", "sha256": "x", "extractor": "test"},
            _row(1, 1, "102102166"), _row(1, 2, "CHAPTER"), _row(1, 3, "2", bold="2"),
            _row(1, 4, "DEFINITIONS", bold="DEFINITIONS"),
            _row(1, 5, "SECTION 202—DEFINITIONS", bold="SECTION 202—DEFINITIONS"),
            _row(1, 6, "[BE] EXIT ACCESS. That portion of a means of egress.", bold="[BE] EXIT ACCESS."),
            _row(1, 7, "[BG] STORY. That portion of a building.", bold="[BG] STORY."),
            *extra_p1,
            _row(1, 20, "10 2025 BUILDING CODE OF NEW YORK STATE", bold="10 2025 BUILDING CODE OF NEW YORK STATE"),
            _row(2, 1, "102102166"), _row(2, 2, "CHAPTER"), _row(2, 3, "10", bold="10"),
            _row(2, 4, "MEANS OF EGRESS", bold="MEANS OF EGRESS"),
            _row(2, 5, "SECTION 1017—EXIT ACCESS TRAVEL DISTANCE", bold="SECTION 1017—EXIT ACCESS TRAVEL DISTANCE"),
            _row(2, 6, "1017.1 General. Travel within the exit access.", bold="1017.1 General.", italic=["exit access"]),
            _row(2, 7, "1017.2 Limitations. Not more than Table 1017.2.", bold="1017.2 Limitations."),
            _row(2, 8, "[F] 1017.2.1 Balcony increase. Increased up to an", bold="[F] 1017.2.1 Balcony increase."),
            _row(2, 9, "TABLE 1017.2—EXIT ACCESS TRAVEL DISTANCE[fna]", bold="TABLE 1017.2—EXIT ACCESS TRAVEL DISTANCE"),
            _row(2, 10, "I-4 150 200c"),
            _row(2, 11, "additional 100 feet on each story."),
            *extra_p2,
            _row(2, 30, "SECTION 1018—AISLES", bold="SECTION 1018—AISLES"),
            _row(2, 31, "1018.1 General. Not brought in.", bold="1018.1 General."),
            _row(2, 32, "2025 BUILDING CODE OF NEW YORK STATE 11", bold="2025 BUILDING CODE OF NEW YORK STATE 11"),
            _row(2, 33, ".")]


BROUGHT_IN = {"pages": "1-2", "sections": ["1017", "Table 1017.2"], "tables": {"Table 1017.2": "p.2 lines 9-10"}}


def _pieces(cut):
    return {p["id"]: p for p in cut["pieces"]}


def test_sections_without_letters_and_one_letter_tags_are_cut_and_the_footer_is_furniture():
    cut = icc_sections.split(_book(), BROUGHT_IN, STYLE)
    assert cut["problems"] == []
    got = _pieces(cut)
    assert {"1017", "1017.1", "1017.2", "1017.2.1", "Table 1017.2", "202:exit_access"} <= set(got)
    assert [2, 32] in cut["furniture"] and [1, 20] in cut["furniture"]


def test_a_table_is_its_own_piece_and_the_part_it_interrupts_runs_on_after_it():
    got = _pieces(icc_sections.split(_book(), BROUGHT_IN, STYLE))
    assert got["Table 1017.2"]["lines"] == [[2, 9, 10]] and got["Table 1017.2"]["kind"] == "table"
    assert got["Table 1017.2"]["title"] == "EXIT ACCESS TRAVEL DISTANCE"
    assert got["1017.2.1"]["lines"] == [[2, 8, 8], [2, 11, 11]]      # the line after the table is still 1017.2.1's


def test_a_tables_title_whose_lines_are_not_named_is_a_problem():
    problems = icc_sections.split(_book(), {**BROUGHT_IN, "tables": {}}, STYLE)["problems"]
    assert any("p.2 line 9: a table's title, but brought_in.tables names no lines" in p for p in problems)


def test_chapter_alone_on_every_chapters_first_page_is_an_opening_never_a_running_head():
    cut = icc_sections.split(_book(), BROUGHT_IN, STYLE)
    assert [2, 2] not in cut["furniture"]
    assert [2, 2, 4, "chapter opening on p.2"] in cut["outside"]   # never the last definition's
    # The house code's style keeps its own reading (a line printed second on two pages is a running head)
    assert [2, 2] in icc_sections.split(_book(), {"pages": "1-2", "sections": []}, None)["furniture"]


def test_a_subscript_under_its_line_is_a_problem_unless_named_with_why():
    extra = [_row(1, 8, "[F] TOXIC. A median lethal dose (LD ) of 50 milligrams", bold="[F] TOXIC."),
             _row(1, 9, "50")]
    brought = {**BROUGHT_IN, "sections": [*BROUGHT_IN["sections"]]}
    problems = icc_sections.split(_book(extra), brought, STYLE)["problems"]
    assert any("p.1 line 9: a fraction may not have been put back together" in p for p in problems)
    named = {**brought, "not_fractions": {"p.1 line 9": "The subscript 50 of LD50."}}
    assert icc_sections.split(_book(extra), named, STYLE)["problems"] == []
    stale = {**brought, "not_fractions": {"p.1 line 8": "No such line."}}
    assert any("brought_in names p.1 line 8 (not_fractions)" in p
               for p in icc_sections.split(_book(extra), stale, STYLE)["problems"])


def test_two_terms_the_text_reads_alike_are_cut_twice_unless_the_second_is_named():
    extra = [_row(1, 8, "[BS] WIND SNOW LOAD, p . Design snow loads.", bold="[BS] WIND SNOW LOAD, p ."),
             _row(1, 9, "[BS] WIND SNOW LOAD, p . Allowable snow loads.", bold="[BS] WIND SNOW LOAD, p .")]
    assert "202:wind_snow_load_p is cut twice" in icc_sections.split(_book(extra), BROUGHT_IN, STYLE)["problems"]
    named = {**BROUGHT_IN, "subscript_terms": {"p.1 line 9": {"printed": "WIND SNOW LOAD, p", "term": "WIND SNOW LOAD, p (asd)",
                                                              "why": "Subscripts on lines of their own."}}}
    cut = icc_sections.split(_book(extra), named, STYLE)
    assert cut["problems"] == [] and "202:wind_snow_load_p_asd" in {o[3] for o in cut["outside"]}


def test_a_raised_footnote_letter_run_into_a_cell_is_put_right_by_line_and_read_as_the_number():
    rows = _book()
    assert [shown(s) for s in statements("I-4 150 200c")] == ["150"]       # the 200 is lost as the text has it
    printed, problems = as_printed(rows, {"p.2 line 10": [{"ocr": "200c", "printed": "200[fnc]", "why": "Raised c."}]})
    assert problems == []
    line = next(r["text"] for r in printed[1:] if (r["page"], r["line"]) == (2, 10))
    assert line == "I-4 150 200[fnc]" and [shown(s) for s in statements(line)] == ["150", "200"]
    _, bad = as_printed(rows, {"p.2 line 10": [{"ocr": "300c", "printed": "300[fnc]", "why": "Not there."}]})
    assert bad                                                             # a stale line never rewrites another


def test_a_terms_tag_bracket_printed_in_roman_does_not_hide_the_term():
    # "[BG" bold, "] " roman, "OCCUPIABLE ROOF." bold (the book's p.55, line 23): still a term of its own
    row = {"page": 1, "line": 8, "text": "[BG] TOXIC ROOF. An exterior space.", "bold": [[0, 3], [5, 16]]}
    cut = icc_sections.split(_book([row]), BROUGHT_IN, STYLE)
    assert cut["problems"] == [] and "202:toxic_roof" in {o[3] for o in cut["outside"]}
    assert "202:toxic_roof" not in {o[3] for o in icc_sections.split(_book([row]), BROUGHT_IN, None)["outside"]}


def test_a_definition_brought_in_by_name_comes_in_with_why_and_a_stale_name_is_a_problem():
    # 508.2.3 prints "floor area" in roman: FLOOR AREA, GROSS and NET come in only by name (brought_in.definitions)
    yard = [_row(1, 8, "[BG] YARD. An open space.", bold="[BG] YARD.")]
    assert "202:yard" not in {p["id"] for p in icc_sections.split(_book(yard), BROUGHT_IN, STYLE)["pieces"]}
    named = {**BROUGHT_IN, "definitions": {"202:yard": "A rule measures with it."}}
    cut = icc_sections.split(_book(yard), named, STYLE)
    assert cut["problems"] == [] and "202:yard" in {p["id"] for p in cut["pieces"]}
    stale = {**BROUGHT_IN, "definitions": {"202:floor_area_net": "No such term on these pages."}}
    assert any("brought_in.definitions names 202:floor_area_net" in p
               for p in icc_sections.split(_book(), stale, STYLE)["problems"])


def test_a_raised_letter_before_a_slash_ends_a_cell_so_both_numbers_are_read():
    """Section group 4b: Table 1020.2 prints "0.5[fnc]/1[fnd]" (p.344 line 10: 0.5 hour with note c, 1 hour with note
    d). Read as one fraction "0.5/1" it was neither number; the mark before the slash ends the first cell."""
    assert [shown(s) for s in statements("R Greater than 10 Not Permitted 0.5[fnc]/1[fnd]")] == [
        "greater than 10", "0.5", "1"]
    assert [shown(s) for s in statements("a ratio of 1/2 and 3[fn2] m")] == ["1/2", "and 3 m"]   # a fraction stays one
    # review round 1 of group 4b: only a note letter's mark ends a cell; a raised digit before a slash is a stacked
    # fraction's top, read as before (Table 716.1's "2 1[fn1]/ 2" hours, a drawing's "[fn5]/8 IN.")
    assert "1" not in [shown(s) for s in statements("2 1[fn1]/ 2 W-120")]
    assert "8 inch" not in [shown(s) for s in statements("[fn5]/8 IN. MIN. TO EDGE")]


def _at(row, x0, top, x1, bottom):
    """A built line with its place on the page (points), as the text layer gives it."""
    return {**row, "x0": x0, "top": top, "x1": x1, "bottom": bottom}


# Table 1010.2.4 as p.325 prints it (each line's place read from the book's text layer): a title on two lines, in the
# title's type (9 points), centred; then its column headings, smaller (8.4 points), and further below
TITLE_1010_2_4 = [
    _at(_row(2, 9, "TABLE 1010.2.4—MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND",
             bold="TABLE 1010.2.4—MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND"), 168.8, 458.2, 425.2, 467.2),
    _at(_row(2, 10, "CONSTANT LATCHING BOLTS ON THE INACTIVE LEAF OF A PAIR OF DOORS",
             bold="CONSTANT LATCHING BOLTS ON THE INACTIVE LEAF OF A PAIR OF DOORS"), 151.9, 468.2, 440.1, 477.2),
    _at(_row(2, 11, "PERMITTED USES OF MANUAL BOLTS,", bold="PERMITTED USES OF MANUAL BOLTS,"),
        381.1, 483.3, 520.6, 491.7)]


def test_a_tables_title_printed_on_two_lines_is_read_whole():
    # Table 1010.2.4's title was cut after its first line ("... FLUSH BOLTS AND")
    assert icc_sections._table_title(TITLE_1010_2_4) == (
        "MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND CONSTANT LATCHING BOLTS ON THE INACTIVE LEAF OF A PAIR OF DOORS")
    rows = _book()
    rows[rows.index(next(r for r in rows if r.get("line") == 9 and r["page"] == 2))] = TITLE_1010_2_4[0]
    rows[rows.index(next(r for r in rows if r.get("line") == 10 and r["page"] == 2))] = TITLE_1010_2_4[1]
    got = _pieces(icc_sections.split(rows, BROUGHT_IN, STYLE))["Table 1017.2"]
    assert got["title"].endswith("FLUSH BOLTS AND CONSTANT LATCHING BOLTS ON THE INACTIVE LEAF OF A PAIR OF DOORS")
    assert got["lines"] == [[2, 9, 10]]                       # the lines of the piece are as they were


def test_a_column_heading_under_a_title_is_never_part_of_it():
    first = TITLE_1010_2_4[0]
    # Table 1006.3.3 (p.316): a heading centred and bold under the title, but smaller and set further below
    heading = _at(_row(2, 10, "OCCUPANT LOAD PER MINIMUM NUMBER OF EXITS OR ACCESS",
                       bold="OCCUPANT LOAD PER MINIMUM NUMBER OF EXITS OR ACCESS"), 186.9, 474.7, 405.1, 483.1)
    assert icc_sections._table_title([first, heading]) == "MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND"
    second = TITLE_1010_2_4[1]
    assert icc_sections._table_title([first, {**second, "top": 473.3, "bottom": 482.3}]) == \
        "MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND"                          # set too far below
    assert icc_sections._table_title([first, {**second, "bottom": 476.6}]) == \
        "MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND"                          # smaller type
    assert icc_sections._table_title([first, {**second, "x0": 171.9, "x1": 460.1}]) == \
        "MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND"                          # not centred on it
    assert icc_sections._table_title([first, {k: v for k, v in second.items() if k != "bold"}]) == \
        "MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND"                          # roman, in a book that marks bold
    assert icc_sections._table_title([first, {**second, "line": 11}]) == \
        "MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND"                          # not the next line
    no_place = {k: v for k, v in second.items() if k not in ("x0", "x1", "top", "bottom")}
    assert icc_sections._table_title([first, no_place]) == "MANUAL BOLTS, AUTOMATIC FLUSH BOLTS AND"
    # a one-line title with its footnote marker, as before
    one = _at(_row(2, 9, "TABLE 1017.2—EXIT ACCESS TRAVEL DISTANCE[fna]", bold="TABLE 1017.2—EXIT ACCESS TRAVEL "
                   "DISTANCE[fna]"), 196.7, 300.0, 397.3, 309.3)
    assert icc_sections._table_title([one, TITLE_1010_2_4[2]]) == "EXIT ACCESS TRAVEL DISTANCE"


def test_a_two_column_books_title_under_its_number_is_read_with_it():
    from document_extraction import columns_sections
    ibc = columns_sections.STYLES["ibc_2009"].table
    lines = lambda *rows: icc_sections.joined_title(icc_sections.table_title_lines(list(rows), ibc))
    # the 2009 IBC prints the number, then the name under it (Table 508.2.5, p.112), then the column headings
    number = _at(_row(112, 43, "TABLE 508.2.5"), 290.0, 300.0, 342.8, 307.3)
    name = _at(_row(112, 44, "INCIDENTAL ACCESSORY OCCUPANCIES"), 252.0, 308.5, 381.2, 315.8)
    heading = _at(_row(112, 45, "ROOM OR AREA"), 170.0, 323.4, 221.4, 329.9)
    assert lines(number, name, heading) == "TABLE 508.2.5 INCIDENTAL ACCESSORY OCCUPANCIES"
    # past the title's footnote letter on a line of its own (Table 1016.1, p.267)
    number = _at(_row(267, 56, "TABLE 1016.1"), 399.0, 300.0, 448.8, 307.3)
    letter = _at(_row(267, 57, "a"), 484.0, 307.2, 487.8, 312.9)
    name = _at(_row(267, 58, "EXIT ACCESS TRAVEL DISTANCE"), 368.0, 308.7, 478.2, 316.0)
    heading = _at(_row(267, 59, "WITHOUT SPRINKLER WITH SPRINKLER"), 400.0, 322.4, 522.2, 328.9)
    assert lines(number, letter, name, heading) == "TABLE 1016.1 EXIT ACCESS TRAVEL DISTANCE"
    # a change bar the OCR joined to the name is no part of it (Table 1015.1, p.266)
    number = _at(_row(266, 18, "TABLE 1015.1"), 164.7, 298.5, 213.9, 305.8)
    name = _at(_row(266, 19, "I SPACES WITH ONE EXIT OR EXIT ACCESS DOORWAY"), 61.7, 304.4, 288.0, 315.1)
    heading = _at(_row(266, 20, "OCCUPANCY MAXIMUM OCCUPANT LOAD"), 110.3, 321.8, 293.8, 328.2)
    assert lines(number, name, heading) == "TABLE 1015.1 SPACES WITH ONE EXIT OR EXIT ACCESS DOORWAY"
    # NFPA 101 prints a mark above the title (Table 6.1.14.4.1(a), p.49): the title starts at its own line
    nfpa = columns_sections.STYLES["nfpa_101_2012"].table
    mark = _at(_row(49, 3, "†", bold="†"), 305.3, 300.0, 308.1, 305.5)
    title = _at(_row(49, 4, "Table 6.1.14.4.1(a) Required Separation of Occupancies (hours), Part 1",
                     bold="Table 6.1.14.4.1(a) Required Separation of Occupancies (hours), Part 1"), 50.0, 301.2, 333.4, 310.1)
    head = _at(_row(49, 5, "Lodging", bold="Lodging"), 476.0, 322.8, 502.8, 329.8)
    assert icc_sections.joined_title(icc_sections.table_title_lines([mark, title, head], nfpa)) == \
        "Table 6.1.14.4.1(a) Required Separation of Occupancies (hours), Part 1"
    # a hyphen ending a line runs on into the next ("SMOKE-" "PROTECTED")
    assert icc_sections.joined_title([_row(1, 1, "AISLES FOR SMOKE-"), _row(1, 2, "PROTECTED ASSEMBLY")]) == \
        "AISLES FOR SMOKE-PROTECTED ASSEMBLY"


def test_a_titles_second_line_ending_in_raised_note_letters_is_read_whole():
    """Review round 1 of Chapter 7 part e1: Table 705.5 (p.165) prints its title on two lines, the second ending in its
    raised note letters a, d and g, which make that line 0.8 point taller and are roman; its title stopped at the first
    line. Its own words are measured, never the marks; a line taller than the marks can make is still no title."""
    first = _at(_row(2, 9, "TABLE 705.5—FIRE-RESISTANCE RATING REQUIREMENTS FOR",
                     bold="TABLE 705.5—FIRE-RESISTANCE RATING REQUIREMENTS FOR"), 176.3, 48.9, 417.7, 57.9)
    text = "EXTERIOR WALLS BASED ON FIRE SEPARATION DISTANCE [fna,] [fnd,] [fng]"
    second = {**_at(_row(2, 10, text), 176.9, 58.1, 417.1, 67.9),
              "bold": [[0, 48], [52, 54], [59, 61], [66, 67]]}
    whole = "FIRE-RESISTANCE RATING REQUIREMENTS FOR EXTERIOR WALLS BASED ON FIRE SEPARATION DISTANCE"
    assert icc_sections._table_title([first, second]) == whole
    cut = "FIRE-RESISTANCE RATING REQUIREMENTS FOR"
    # taller than marks make: 1.9 points over the first line, more than 0.45 + 1.2 (review round 2: the gap kept
    # legal, 0.2 point, so only the height decides); 1.6 points over, within it, still the title
    assert icc_sections._table_title([first, {**second, "bottom": 69.0}]) == cut
    assert icc_sections._table_title([first, {**second, "bottom": 68.7}]) == whole
    unmarked = {**second, "text": "EXTERIOR WALLS BASED ON FIRE SEPARATION DISTANCE", "bold": [[0, 48]]}
    assert icc_sections._table_title([first, unmarked]) == cut                   # 0.8 taller with no marks: no title
    assert icc_sections._table_title([first, {**second, "bold": [[0, 20]]}]) == cut    # its words not bold throughout
