"""A code book in two columns read from its text layer (layout: two_column): the 2009 IBC scan and NFPA 101 2012.
Reading order, words, fractions and the scan's marks (columns.py); cutting at the book's own headings, its tables and
its definitions (columns_sections.py); the OCR's misreads put right by name (book_text.as_printed). Built characters
and lines, so each safeguard is tested without the copyrighted books."""

from document_extraction import book_text, columns, columns_sections

BODY = 9.0


def _word(text, x0, top, size=BODY, font="Times-Roman", gap=0.0):
    """A word's characters, each 0.5 of its size wide, `gap` points apart."""
    out, x = [], x0
    for t in text:
        out.append({"text": t, "x0": x, "x1": x + size * 0.5, "top": top, "bottom": top + size, "size": size,
                    "fontname": font, "matrix": (size, 0, 0, size, x, 700 - top)})
        x = out[-1]["x1"] + gap
    return out


def _line(words, x0, top, **kw):
    out, x = [], x0
    for w in words.split():
        out += _word(w, x, top, **kw)
        x = out[-1]["x1"] + 3.0                       # a word space: far over WORD_GAP of the size
    return out


def _texts(lines):
    """Each line's text as the extractor writes it (icc.line_text: a space between a whole number and its fraction)."""
    from document_extraction.icc import line_text
    return [line_text(line, BODY)[0] for line in lines]


def test_the_left_column_is_read_before_the_right_and_a_line_across_the_gutter_is_a_band_of_its_own():
    chars = (_line("TABLE ACROSS THE WHOLE PAGE", 60, 50) + _line("left one", 60, 70) + _line("right one", 330, 70)
             + _line("left two", 60, 82) + _line("right two", 330, 82))
    assert _texts(columns.read_in_columns(chars, 612, BODY)) == ["TABLE ACROSS THE WHOLE PAGE", "left one", "left two",
                                                                  "right one", "right two"]


def test_a_large_stamp_across_the_middle_is_read_last_and_never_parts_the_columns():
    chars = (_line("left one", 60, 70) + _line("right one", 330, 70) + _word("{LICENCE-NUMBER-ACROSS}", 100, 76, size=24)
             + _line("left two", 60, 100) + _line("right two", 330, 100))
    assert _texts(columns.read_in_columns(chars, 612, BODY)) == ["left one", "left two", "right one", "right two",
                                                                  "{LICENCE-NUMBER-ACROSS}"]


def test_words_are_parted_at_gaps_and_letters_close_together_stay_one_word():
    chars = _word("exit", 60, 70, gap=0.1) + _word("access", 60 + 4 * 4.5 + 0.4 + 1.2, 70, gap=0.1)
    assert _texts(columns.read_in_columns(chars, 612, BODY)) == ["exit access"]     # 1.2 pt: over 0.08 of 9 pt


def test_a_tall_change_bar_in_the_margin_is_a_line_of_its_own_never_joined_to_the_lines_beside_it():
    chars = _line("first line", 60, 70) + _word("I", 50, 66, size=30) + _line("second line", 60, 82)
    got = _texts(columns.read_in_columns(chars, 612, BODY))
    assert "first line" in got and "second line" in got and "I" in got


def test_a_small_stacked_fraction_is_put_back_on_its_line_after_its_whole_number():
    chars = _word("children", 60, 70) + _word("2", 100, 70)
    chars += [dict(_word("1", 105, 67, size=5)[0]), dict(_word("/", 107.6, 69, size=5)[0]), dict(_word("2", 110, 72, size=5)[0])]
    chars += _word("years", 116, 70)
    assert columns.join_small_fractions(chars, BODY) == 1
    assert _texts(columns.read_in_columns(chars, 612, BODY)) == ["children 2 1/2 years"]   # never "21/2" or "2 2"


def test_a_glyph_fraction_is_written_in_digits():
    chars, written = columns.spelled(_word("2½", 60, 70))
    assert written == 1 and _texts(columns.read_in_columns(chars, 612, BODY)) == ["2 1/2"]


# ---- cutting --------------------------------------------------------------------------------------------------------

def _rows(page_lines: dict[int, list[str]], bold=()):
    rows = [{"file": "book.pdf", "sha256": "x"}]
    for page, lines in page_lines.items():
        for n, text in enumerate(lines, 1):
            r = {"page": page, "line": n, "text": text}
            if text in bold:
                r["bold"] = [[0, len(text.split(". ")[0]) + 1]]
            rows.append(r)
    return rows


IBC_PAGE = ["SECTION 1015", "EXIT AND EXIT ACCESS DOORWAYS", "1015.1 Exits from spaces. Two exits shall be",
            "provided where one of the following", "TABLE 1015.1", "SPACES WITH ONE EXIT", "S 29",
            "conditions exists.", "1015.2 Arrangement. Exits shall be obvious.", "1015.2.1 and 1015.2.2.",
            "1015.3 Boiler rooms. Two exit access doorways."]


def test_a_table_is_its_own_piece_and_the_text_after_it_goes_on_with_the_part_it_interrupts():
    got = columns_sections.split(_rows({266: IBC_PAGE}), {"pages": "266", "sections": ["1015.1", "Table 1015.1"],
                                                         "tables": {"Table 1015.1": "p.266 lines 5-7"}}, "ibc_2009")
    pieces = {p["id"]: p for p in got["pieces"]}
    assert pieces["1015.1"]["lines"] == [[266, 3, 4], [266, 8, 8]]
    assert pieces["Table 1015.1"]["lines"] == [[266, 5, 7]] and pieces["Table 1015.1"]["kind"] == "table"
    assert got["problems"] == []


def test_a_tables_title_with_no_lines_named_is_a_problem_never_cut_by_guess():
    got = columns_sections.split(_rows({266: IBC_PAGE}), {"pages": "266", "sections": ["1015.1"]}, "ibc_2009")
    assert any("a table's title, but brought_in.tables names no lines" in p for p in got["problems"])


def test_a_wrapped_line_of_section_numbers_is_no_heading_without_bold():
    got = columns_sections.split(_rows({266: IBC_PAGE}), {"pages": "266", "sections": ["1015.2"],
                                                         "tables": {"Table 1015.1": "p.266 lines 5-7"}}, "ibc_2009")
    pieces = {p["id"]: p for p in got["pieces"]}
    assert pieces["1015.2"]["lines"] == [[266, 9, 10]]      # "1015.2.1 and 1015.2.2." is its text: lower-case "and"


def test_a_heading_out_of_order_is_a_problem_unless_named_as_no_heading():
    page = ["SECTION 1015", "EXITS", "1015.1 Exits. Two exits.", "1015.4 Refrigeration. Two exits.", "1015.2 Arrangement. Obvious.",
            "1015.3 Boiler. Two doors."]
    got = columns_sections.split(_rows({266: page}), {"pages": "266", "sections": ["1015.1"]}, "ibc_2009")
    assert any("1015.4 is out of order" in p for p in got["problems"])
    got = columns_sections.split(_rows({266: page}), {"pages": "266", "sections": ["1015.1"],
                                                     "not_headings": {"p.266 line 4": "body text (checked on the image)"}},
                                 "ibc_2009")
    assert not any("out of order" in p for p in got["problems"])


def test_a_definitions_title_that_is_also_the_running_head_is_the_sections_title():
    pages = {38: ["SECTION 202", "DEFINITIONS", "EXIT. That portion of a means of egress system."],
             39: ["DEFINITIONS", "STORY. That portion of a building."],
             40: ["DEFINITIONS", "WINDER. A tread."]}
    got = columns_sections.split(_rows(pages), {"pages": "38-40", "sections": []}, "ibc_2009")
    ids = {o[3] for o in got["outside"]}
    assert {"202:exit", "202:story", "202:winder"} <= ids
    assert [39, 1] in got["furniture"] and [38, 2] not in got["furniture"]


def test_an_italic_phrase_the_ocr_ran_together_still_names_its_definition():
    pages = {244: ["SECTION 1002", "DEFINITIONS", "MEANS OF EGRESS. A path.", "1003.1 Applicability. The general"],
             245: ["SECTION 1004", "LOAD", "1004.1 Design. In determining means ofegress requirements."]}
    rows = _rows(pages)
    line = next(r for r in rows[1:] if r["text"].startswith("1004.1"))
    a = line["text"].index("means ofegress")
    line["italic"] = [[a, a + len("means ofegress")]]
    got = columns_sections.split(rows, {"pages": "244-245", "sections": ["1004.1"]}, "ibc_2009")
    pieces = {p["id"]: p for p in got["pieces"]}
    assert pieces["1004.1"]["uses"] == ["1002:means_of_egress"] and "1002:means_of_egress" in pieces


def test_an_nfpa_definition_is_a_numbered_part_of_3_3_and_a_term_printed_in_roman_is_used():
    pages = {29: ["Chapter 3 Definitions", "3.1 General. The definitions apply.", "3.2 Official Definitions.",
                  "3.3 General Definitions.",
                  "3.3.1 Common Path of Travel. The portion of exit access.", "3.3.2 Exit Access. That portion."],
             174: [
                   "16.2.5.3 Limitations on common path of travel shall be met.", "16.2.5.4 Other Limits."]}
    bold = {t for lines in pages.values() for t in lines}
    rows = _rows(pages, bold=bold)
    got = columns_sections.split(rows, {"pages": "29, 174", "sections": ["16.2.5.3"]}, "nfpa_101_2012")
    pieces = {p["id"]: p for p in got["pieces"]}
    assert pieces["3.3.1"]["kind"] == "definition" and "3.3.1" in pieces["16.2.5.3"]["uses"]
    assert "3.3.2" in pieces["3.3.1"]["uses"]              # the definitions a definition prints come in too


# ---- the OCR's misreads, put right by name --------------------------------------------------------------------------

def test_a_named_misread_is_put_right_and_one_that_doesnt_match_is_a_problem_never_applied():
    rows = [{"file": "b"}, {"page": 266, "line": 23, "text": "H-4, H-5, 1-1, 1-3, 1-4, R 10", "italic": [[24, 28]]}]
    fixed, problems = book_text.as_printed(rows, {"p.266 line 23": [{"ocr": "1-1, 1-3, 1-4", "printed": "I-1, I-3, I-4",
                                                                    "why": "the scan's I read as 1"}]})
    assert fixed[1]["text"] == "H-4, H-5, I-1, I-3, I-4, R 10" and problems == [] and rows[1]["text"].startswith("H-4, H-5, 1")
    _, problems = book_text.as_printed(rows, {"p.266 line 23": [{"ocr": "1-2", "printed": "I-2", "why": "x"}]})
    assert problems and "not applied" in problems[0]
    _, problems = book_text.as_printed(rows, {"p.266 line 99": [{"ocr": "1-4", "printed": "I-4", "why": "x"}]})
    assert problems == ["brought_in.misread names p.266 line 99, which is not a line read"]
