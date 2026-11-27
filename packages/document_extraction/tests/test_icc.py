"""An ICC code book (layout: icc): stacked fractions put back together (icc.py), the book cut into pieces at its own
bold headings with nothing skipped (icc_sections.py), and every number read with its limit words (numbers.py).
Built lines and characters, so each safeguard is tested on its own, without the copyrighted book."""

import pytest

from document_extraction import icc_sections
from document_extraction.icc import join_fractions, line_text
from document_extraction.numbers import comparison, comparisons, shown, statements

BODY = 9.48


def _char(text, x0, top, size=BODY, font="SourceSansPro-Regular"):
    return {"text": text, "x0": x0, "x1": x0 + size * 0.5, "top": top, "bottom": top + size, "size": size,
            "y0": 700 - top - size, "y1": 700 - top, "doctop": top, "fontname": "ABCDEF+" + font,
            "matrix": (size, 0, 0, size, x0, 700 - top)}


def _fraction(whole: str, num: str, den: str, x=100.0, top=60.0):
    """The way the book prints "8 1/4": a full-size 8, a small raised 1, a full-size slash, a small lowered 4."""
    chars, x0 = [], x
    for d in whole:
        chars.append(_char(d, x0, top))
        x0 = chars[-1]["x1"]
    for d in num:
        chars.append(_char(d, x0, top - 0.7, size=5.64))         # raised: its bottom well above the line's
        chars[-1]["bottom"] = top + 4.9
        x0 = chars[-1]["x1"]
    chars.append(_char("/", x0, top))
    x0 = chars[-1]["x1"]
    for d in den:
        chars.append(_char(d, x0, top + 5.4, size=5.64))         # lowered: its bottom below the line's
        chars[-1]["bottom"] = top + 11
        x0 = chars[-1]["x1"]
    return chars


@pytest.mark.parametrize("whole,num,den,expect", [("8", "1", "4", "8 1/4"), ("", "9", "16", "9/16"),
                                                   ("1", "3", "8", "1 3/8")])
def test_a_stacked_fraction_is_one_word_and_never_joins_its_whole_number(whole, num, den, expect):
    chars = _fraction(whole, num, den)
    assert join_fractions(chars, BODY) == 1
    assert {c["top"] for c in chars} == {60.0}                  # all on one line now
    line = {"text": "".join(c["text"] for c in chars), "chars": chars}
    text, _ = line_text(line, BODY)
    assert text == expect                                       # "8 1/4", never "81/4" or "8[fn1]/"


def test_a_raised_digit_that_is_no_numerator_stays_a_sealed_footnote_marker():
    chars = [_char("m", 100, 60), _char("2", 105, 59.3, size=5.64)]
    chars[1]["bottom"] = 64.9
    assert join_fractions(chars, BODY) == 0
    text, _ = line_text({"text": "m2", "chars": chars}, BODY)
    assert text == "m[fn2]"                                     # m², never "m2" (a number 2)


def test_italic_and_bold_runs_are_offsets_into_the_text_as_written():
    chars = [_char(c, 100 + 6 * i, 60, font="SourceSansPro-Bold") for i, c in enumerate("R1.")] + \
            [_char(c, 130 + 6 * i, 60, font="SourceSansPro-It") for i, c in enumerate("stair")]
    text, styles = line_text({"text": "R1. stair", "chars": chars}, BODY)
    assert text[slice(*styles["bold"][0])] == "R1." and text[slice(*styles["italic"][0])] == "stair"


# ---- cutting the book ---------------------------------------------------------------------------------------------

def _row(page, line, text, bold=None, italic=()):
    r = {"page": page, "line": line, "text": text}
    if bold:
        r["bold"] = [[0, len(bold)]]
    if italic:
        r["italic"] = [[text.index(w), text.index(w) + len(w)] for w in italic]
    return r


def _book(extra=()):
    """Two pages of a made-up book: definitions on p.1, a section on p.2, and the next section's heading."""
    rows = [{"file": "book.pdf", "sha256": "x", "extractor": "test"},
            _row(1, 1, "102102166"), _row(1, 2, "DEFINITIONS"),
            _row(1, 3, "SECTION R202—DEFINITIONS", bold="SECTION R202—DEFINITIONS"),
            _row(1, 4, "[RB] FLIGHT. A continuous run of treads.", bold="[RB] FLIGHT."),
            _row(1, 5, "[RB] PORCH. A roofed space.", bold="[RB] PORCH."),
            _row(1, 6, "[RB] STAIR. One or more risers.", bold="[RB] STAIR."),
            _row(1, 7, "2025 RESIDENTIAL CODE OF NEW YORK STATE 11"),
            _row(2, 1, "102102166"), _row(2, 2, "DEFINITIONS"),
            _row(2, 3, "SECTION R318—MEANS OF EGRESS", bold="SECTION R318—MEANS OF EGRESS"),
            _row(2, 4, "R318.1 Risers. Each flight shall have risers not more than 8 1/4 inches.", bold="R318.1 Risers.",
                 italic=["flight"]),
            _row(2, 5, "R318.1.1 Treads. The stair tread shall be 9 inches.", bold="R318.1.1 Treads.", italic=["stair"]),
            *extra,
            _row(2, 9, "SECTION R319—ESCAPE", bold="SECTION R319—ESCAPE"),
            _row(2, 10, "R319.1 General. Not brought in.", bold="R319.1 General."),
            _row(2, 11, "2025 RESIDENTIAL CODE OF NEW YORK STATE 12"), _row(2, 12, ".")]
    return rows


BROUGHT_IN = {"pages": "1-2", "sections": ["R318"]}


def test_every_line_of_the_pages_read_is_a_piece_furniture_or_named_as_not_brought_in():
    cut = icc_sections.split(_book(), BROUGHT_IN)
    assert cut["problems"] == []
    ids = [p["id"] for p in cut["pieces"]]
    assert ids == ["R202", "R202:flight", "R202:stair", "R318", "R318.1", "R318.1.1"]   # PORCH: used by none
    owned = {(pg, n) for p in cut["pieces"] for pg, a, b in p["lines"] for n in range(a, b + 1)}
    owned |= {tuple(f) for f in cut["furniture"]}
    owned |= {(pg, n) for pg, a, b, _ in cut["outside"] for n in range(a, b + 1)}
    assert owned == {(r["page"], r["line"]) for r in _book()[1:]}
    assert {o[3] for o in cut["outside"]} == {"R202:porch", "R319", "R319.1"}
    assert cut["pieces"][4]["uses"] == ["R202:flight"]          # by its italics (R201.1)


def test_a_definition_brought_in_by_roman_type_brings_in_the_definitions_it_uses():
    # review round 5: ACCESS (TO), brought in by roman type, uses READY ACCESS (TO), which was left out
    swap = {(1, 5): _row(1, 5, "[RB] PORCH. A roofed deck.", bold="[RB] PORCH.", italic=["deck"]),
            (2, 5): _row(2, 5, "R318.1.1 Treads. The stair tread at a porch shall be 9 inches.", bold="R318.1.1 Treads.",
                         italic=["stair"])}
    rows = [swap.get((r.get("page"), r.get("line")), r) for r in _book()]
    at = next(i for i, r in enumerate(rows) if r.get("text", "").startswith("[RB] FLIGHT"))
    rows.insert(at, _row(1, 31, "[RB] DECK. An open platform.", bold="[RB] DECK."))
    cut = icc_sections.split(rows, BROUGHT_IN)
    assert cut["problems"] == [], cut["problems"]
    ids = [p["id"] for p in cut["pieces"]]
    assert "R202:porch" in ids and "R202:deck" in ids, ids     # porch by roman type, deck by porch's italics


def test_a_defined_term_with_periods_in_its_parentheses_is_cut_on_its_own():
    rows = _book()
    rows.insert(5, _row(1, 51, "[MP] FIXTURE UNIT, DRAINAGE (d.f.u.). A measure.",    # on p.1, after FLIGHT
                        bold="[MP] FIXTURE UNIT, DRAINAGE (d.f.u.)."))
    cut = icc_sections.split(rows, BROUGHT_IN)
    assert cut["problems"] == []
    assert "R202:fixture_unit_drainage_d_f_u" in {o[3] for o in cut["outside"]}


def test_bold_capitals_the_cutter_cant_read_as_a_term_are_a_problem_never_merged_silently(monkeypatch):
    monkeypatch.setattr(icc_sections, "TERM", icc_sections.re.compile(r"^(?!)"))   # a cutter that reads no term
    assert any("'[RB] PORCH.' looks like a defined term but was not cut" in p
               for p in icc_sections.split(_book(), BROUGHT_IN)["problems"])


def test_a_wrapped_line_that_looks_like_a_heading_is_not_bold_so_never_cut():
    rows = _book([_row(2, 6, "R318.2 of this code applies.")])  # body text, not bold
    cut = icc_sections.split(rows, BROUGHT_IN)
    assert "R318.2" not in [p["id"] for p in cut["pieces"]] and cut["problems"] == []


def test_a_heading_out_of_order_is_reported_never_silently_skipped():
    rows = _book([_row(2, 6, "R318.5 Ramps. Out of order.", bold="R318.5 Ramps.")])
    assert any("R318.5 is out of order" in p for p in icc_sections.split(rows, BROUGHT_IN)["problems"])


def test_a_section_not_found_or_not_ended_on_the_pages_read_is_a_problem():
    assert any("R320: brought in, but no such heading" in p
               for p in icc_sections.split(_book(), {"pages": "1-2", "sections": ["R318", "R320"]})["problems"])
    assert any("R319: its end is not on the pages read" in p
               for p in icc_sections.split(_book(), {"pages": "1-2", "sections": ["R318", "R319"]})["problems"])


def test_a_fraction_left_apart_is_a_problem():
    rows = _book([_row(2, 6, "not more than 8[fn1]/"), _row(2, 7, "4")])
    assert any("fraction may not have been put back together" in p
               for p in icc_sections.split(rows, BROUGHT_IN)["problems"])


def test_a_page_after_a_gap_starts_outside_the_part_before_it():
    rows = _book() + [_row(5, 1, "continues R317 from p.4, not read"),
                      _row(5, 2, "R325.6 Lights. Not less than 1 footcandle.", bold="R325.6 Lights."),
                      _row(5, 3, "R325.7 Next.", bold="R325.7 Next.")]
    cut = icc_sections.split(rows, {"pages": "1-2, 5", "sections": ["R318", "R325.6"]})
    assert cut["problems"] == [] and [5, 1, 1, "before the first heading on p.5"] in cut["outside"]
    assert "R325.6" in [p["id"] for p in cut["pieces"]]


# ---- numbers ------------------------------------------------------------------------------------------------------

def test_each_number_keeps_its_limit_words_and_unit():
    got = [shown(s) for s in statements(
        "1. The riser height shall be not more than 8 1/4 inches (209 mm), not exceed the smallest by more than "
        "3/8 inch with three or fewer risers per Section R318.7.5 and Table R401.4.1(2) in one-family dwellings")]
    assert got == ["not more than 8 1/4 inch", "209 mm", "not exceed the smallest by more than 3/8 inch", "three or fewer",
                   "one"]


def test_a_misread_number_or_limit_word_reads_differently():
    right = [shown(s) for s in statements("not more than 8 1/4 inches")]
    assert right == ["not more than 8 1/4 inch"]
    for wrong in ("not more than 8 inches", "not less than 8 1/4 inches", "not more than 81/4 inches",
                  "not more than 8 3/4 inches"):
        assert [shown(s) for s in statements(wrong)] != right


def test_without_the_cache_a_kept_outside_book_is_skipped_and_said_so(monkeypatch, tmp_path, capsys):
    import document_extraction.__main__ as cli
    from rule_format.rulebook import CODE_CACHE_ENV, REPO, load
    monkeypatch.setenv(CODE_CACHE_ENV, str(tmp_path / "no_cache"))
    j = REPO / "regulations/jurisdictions/new_york/new_york_state"
    doc = load(j / "1_source_documents/sources.yaml")["documents"][0]
    assert cli._kept_outside(j, doc, check=True) is True
    assert "not in the code cache here; not extracted or checked" in capsys.readouterr().out


def test_a_comparison_word_after_a_conversion_in_brackets_is_kept():
    # R318.7.12's exception, p.101: "or less" read as "or more" must read differently (review round 5)
    right = [shown(s) for s in statements("areas of 200 gross square feet (18.6 m[fn2]) or less where")]
    assert right == ["200 gross square foot or less", "18.6 m or less"]
    assert [shown(s) for s in statements("areas of 200 gross square feet (18.6 m[fn2]) or more where")] != right
    assert [shown(s) for s in statements("not less than 36 inches (914 mm) measured")] == ["not less than 36 inch",
                                                                                           "914 mm"]
    # never across another number, a comma or an unclosed bracket (review round 5, second look)
    assert [shown(s) for s in statements("4 inches (102 mm), 6 or more")] == ["4 inch", "102 mm", "6 or more"]
    assert [shown(s) for s in statements("10 feet (unclosed. Where the area (x) or more")] == ["10 foot"]


@pytest.mark.parametrize("text,expect", [
    ("shall not be less than 7 feet", ["not be less than 7 foot"]),          # R315.3, p.56
    ("nor more than 80 inches", ["nor more than 80 inch"]),                  # BO107.2.2, p.971
    ("no more than five", ["no more than five"]), ("not be greater than one-half", ["not be greater than one-half"]),
    ("shall be not less than 36 inches", ["not less than 36 inch"]), ("and not within 3 feet", ["not within 3 foot"]),
    # review round 3: a verb between the "not" and the comparison (R320.3, R320.5, p.104)
    ("shall not project more than 4 1/2 inches", ["not project more than 4 1/2 inch"]),
    ("shall not form a gap more than 1/4 inch", ["not form a gap more than 1/4 inch"]),
    ("cannot be less than 3 feet", ["cannot be less than 3 foot"]), ("not to exceed 4 inches", ["not to exceed 4 inch"]),
    # review round 7 of step 1: five to seven words between (R318.7.2, R318.7.3, R318.7.5.2.1, R318.7.5.3, pp.100-101)
    ("shall not project horizontally into the required headroom more than 4 3/4 inches",
     ["not project horizontally into the required headroom more than 4 3/4 inch"]),
    ("shall not have a vertical rise greater than 12 feet", ["not have a vertical rise greater than 12 foot"]),
    ("shall not exceed the smallest winder tread by more than 3/8 inch",
     ["not exceed the smallest winder tread by more than 3/8 inch"]),
    ("shall not be required to be within 3/8 inch", ["not be required to be within 3/8 inch"])])
def test_a_comparison_keeps_the_not_printed_before_it(text, expect):
    # Review round 2 of step 1b: "shall not be less than 7 feet" was recorded "less than 7 foot", the law backwards,
    # so a second reading that dropped the "not" would still have agreed
    got = [shown(s) for s in statements(text)]
    assert got == expect
    assert got != [shown(s) for s in statements(text.replace("not ", "").replace("nor ", "").replace("no ", "")
                                                 .replace("cannot ", ""))]


@pytest.mark.parametrize("text,expect", [
    ("shall be not less than 36 inches", [">="]), ("shall be not more than 8 1/4 inches", ["<="]),
    ("where the stair has more than 3 risers", [">"]), ("less than 70 square feet", ["<"]),
    ("shall not have a vertical rise greater than 12 feet", ["<="]),                     # R318.7.3, p.100
    ("shall not project horizontally into the required headroom more than 4 3/4 inches", ["<="]),   # R318.7.2
    ("shall not exceed the smallest winder tread by more than 3/8 inch", ["<="]),       # R318.7.5.2.1
    ("shall not be required to be within 3/8 inch", ["none"]),                          # a limit lifted, not reversed
    ("not to exceed 4 inches", ["<="]), ("nor more than 80 inches", ["<="]), ("cannot be less than 3 feet", [">="]),
    ("not steeper than 1 unit", ["<="]), ("a minimum 36 inches", [">="]), ("up to ten", ["<="]),
    ("200 square feet (18.6 m[fn2]) or less", ["<=", "<="]), ("6 or more", [">="]), ("three or fewer", ["<="]),
    ("between 34 and 38 inches", ["between", "between"]), ("for one bedroom and one", ["none", "none"]),
    ("more than one and one third the nominal", [">"]), ("36 inches", ["none"])])
def test_a_recorded_number_says_which_way_its_limit_goes(text, expect):
    # Review round 8 of step 1: what the recorded words say, as a symbol, so a person's reading of the printed
    # sentence can check it; read from the recorded words alone, as text_verification.yaml holds them
    assert comparisons([shown(s) for s in statements(text)]) == expect


def test_a_dropped_not_reverses_the_recorded_comparison():
    # the two rounds' bug: with the "not" dropped the words read the other way round, which is what is checked
    assert comparison("greater than 12 foot") == ">" and comparison("not have a vertical rise greater than 12 foot") == "<="
    assert comparison("less than 7 foot") == "<" and comparison("not be less than 7 foot") == ">="


@pytest.mark.parametrize("text,reader", [
    ("Handrails are not required for stairs having more than 3 risers", [">"]),   # another verb's "not" taken
    ("Guards not located at the edge shall be at least 36 inches", [">="]),
    ("shall not have a rise or a run greater than 7 inches", ["<="]),             # a "not" lost across "or"
    ("shall not exceed 7 feet (2134 mm) for more than one-half of the floor", ["<=", "none", "<="])])   # R315.2
def test_where_the_words_kept_are_wrong_the_recorded_comparison_differs_from_the_printed_sentence(text, reader):
    # Review round 8 of step 1: numbers.py's reach is a rule of thumb; where it takes or drops the wrong "not", what
    # the recorded words say differs from a person's reading of the sentence, so text_verification.yaml needs a flag
    assert comparisons([shown(s) for s in statements(text)]) != reader


def test_a_not_eight_words_before_a_three_word_comparison_is_kept():
    # review round 8: the words looked at were ten, so after "by more than" only seven were searched
    assert [shown(s) for s in statements("shall not a b c d e f g by more than 3/8 inch")] == [
        "not a b c d e f g by more than 3/8 inch"]
    assert [shown(s) for s in statements("shall not a b c d e f g h by more than 3/8 inch")] == ["by more than 3/8 inch"]


def test_a_not_in_another_clause_is_not_taken_and_a_pound_is_a_unit():
    assert [shown(s) for s in statements("is not required where the stair has more than 3 risers")] == ["more than 3 riser"]
    assert [shown(s) for s in statements("not less than 36 inches, more than 2")] == ["not less than 36 inch", "more than 2"]
    assert [shown(s) for s in statements("a 300-pound (136 kg) load")] == ["300 pound", "136 kg"]     # R315.5.3.1
    # a "not" before another number is that number's ("not less than two occupants for one bedroom", p.708)
    assert [shown(s) for s in statements("not less than two occupants for one bedroom and one")] == [
        "not less than two", "one", "and one"]
    assert [shown(s) for s in statements("no more than five sleeping rooms for up to ten")] == ["no more than five",
                                                                                                "up to ten"]


def test_a_whole_number_and_a_part_in_words_is_one_number():
    # BO103 DANGEROUS item 3, p.966: "more than one and one third the nominal strength" is the number 1 1/3
    assert [shown(s) for s in statements("more than one and one third the nominal")] == ["more than one and one third"]
    assert [shown(s) for s in statements("between one and three")] == ["between one", "and three"]


@pytest.mark.parametrize("text,expect", [
    ("not less than that of a quarter circle", ["a quarter"]), ("not less than one-half of the area", ["not less than one-half"]),
    ("two-thirds of the width", ["two-thirds"]), ("thirteen risers", ["thirteen riser"]), ("one-family", ["one"]),
    ("three-fourths of", ["three-fourths"]), ("twenty-four inches", ["twenty-four inch"]), ("4-3/8 inches", ["4-3/8 inch"]),
    ("not less than 5.7 square feet", ["not less than 5.7 square foot"]), ("5.7 square inches", ["5.7 square inch"]),
    ("1 unit vertical in 12 units horizontal", ["1 unit vertical", "12 unit horizontal"])])
def test_parts_of_a_whole_and_larger_number_words_are_numbers_too(text, expect):
    assert [shown(s) for s in statements(text)] == expect          # "one-half" is never the number one


def test_a_brought_in_part_last_before_a_page_not_read_is_a_problem_never_cut_short_silently():
    rows = [r for r in _book() if not (r.get("page") == 2 and r.get("line") in (9, 10))]   # R319's heading on p.3
    rows += [_row(5, 1, "R325.6 Lights. Not less than 1 footcandle.", bold="R325.6 Lights."),
             _row(5, 2, "R325.7 Next.", bold="R325.7 Next.")]
    problems = icc_sections.split(rows, {"pages": "1-2, 5", "sections": ["R318", "R325.6"]})["problems"]
    assert any("R318.1.1: the last part on p.2 before a page not read" in p for p in problems), problems


def test_a_page_with_no_law_on_it_is_no_gap():
    rows = _book()[:8] + [_row(2, 1, "102102166"), _row(2, 2, "2025 RESIDENTIAL CODE OF NEW YORK STATE 12"),
                          _row(2, 3, ".")]
    rows += [_row(3, 1, "102102166"), _row(3, 2, "SECTION R318—MEANS OF EGRESS", bold="SECTION R318—MEANS OF EGRESS"),
             _row(3, 3, "R318.1 Risers. Each flight shall have risers.", bold="R318.1 Risers.", italic=["flight"]),
             _row(3, 4, "SECTION R319—ESCAPE", bold="SECTION R319—ESCAPE")]
    assert icc_sections.split(rows, {"pages": "1-3", "sections": ["R318"]})["problems"] == []


def test_a_new_chapters_title_and_user_notes_end_the_definitions_and_are_no_law():
    rows = _book()[:7] + [
        _row(2, 1, "102102166"), _row(2, 2, "Part III— Building Planning", bold="Part III— Building Planning"),
        _row(2, 3, "CHAPTER"), _row(2, 4, "3", bold="3"), _row(2, 5, "ICC user notes:", bold="ICC user notes:"),
        _row(2, 6, "About this chapter: risers and stairs."),
        _row(2, 7, "SECTION R318—MEANS OF EGRESS", bold="SECTION R318—MEANS OF EGRESS"),
        _row(2, 8, "R318.1 Risers. Each stair shall have risers.", bold="R318.1 Risers.", italic=["stair"]),
        _row(2, 9, "SECTION R319—ESCAPE", bold="SECTION R319—ESCAPE")]
    cut = icc_sections.split(rows, {"pages": "1-2", "sections": ["R318"]})
    assert cut["problems"] == []                                   # the big "3" is no fraction left apart
    stair = next(p for p in cut["pieces"] if p["id"] == "R202:stair")
    assert stair["lines"] == [[1, 6, 6]]                           # the chapter opening is not in the definition
    assert [2, 2, 6, "chapter opening on p.2"] in cut["outside"]


def test_a_defined_word_leading_a_hyphenated_compound_is_brought_in():
    rows = _book()
    rows.insert(5, _row(1, 52, "[RB] OWNER. Any person with an interest.", bold="[RB] OWNER."))   # after FLIGHT
    rows.insert(12, _row(2, 6, "Owner-occupied dwellings are exempt."))
    cut = icc_sections.split(rows, BROUGHT_IN)
    assert "R202:owner" in [p["id"] for p in cut["pieces"]]


def test_references_into_and_out_of_the_brought_in_sections_are_found_by_code():
    from document_extraction.icc_references import ways_in, ways_out
    rows = [{"page": 9, "line": 1, "text": "R315.5 Sleeping lofts shall comply with Section R318 as modified."},
            {"page": 9, "line": 2, "text": "R507.10 Guards shall meet R321.1."},
            {"page": 9, "line": 3, "text": "R322.1 Flood. See Section R322.2."},
            {"page": 16, "line": 1, "text": "R318—Means of Egress . . . 76"},          # the contents: left out
            {"page": 100, "line": 1, "text": "R318.1 shall comply with R318.2."}]       # a brought-in piece's own
    found = ways_in(rows, ["R318", "R321"], owned={(100, 1)}, skip={16})
    assert [(p, n, c) for p, n, c, _ in found] == [(9, 1, "R318"), (9, 2, "R321.1")]
    pieces = [{"id": "R319.7", "kind": "section", "lines": [[1, 1, 1]]}]
    lines = {(1, 1): "Existing basements shall comply with Appendix BO and ICC 500, not R319.1."}
    assert ways_out(pieces, lines, ["R319"]) == {"Appendix BO": ["R319.7"], "ICC 500": ["R319.7"]}


def test_an_italic_word_r202_doesnt_define_must_be_named_with_why():
    rows = _book([_row(2, 6, "R318.1.2 Doors. Each door shall be accessed.", bold="R318.1.2 Doors.", italic=["accessed"])])
    assert any("R318.1.2: italic 'accessed' is not defined in Section R202" in p
               for p in icc_sections.split(rows, BROUGHT_IN)["problems"])
    named = BROUGHT_IN | {"italic_not_defined": {"R318.1.2": {"accessed": "R201.3: another code's meaning"}}}
    assert icc_sections.split(rows, named)["problems"] == []
    elsewhere = BROUGHT_IN | {"italic_not_defined": {"R318.1": {"accessed": "named under another piece"}}}
    problems = icc_sections.split(rows, elsewhere)["problems"]
    assert any("R318.1.2: italic 'accessed'" in p for p in problems)            # a name covers its own piece only
    assert any("names 'accessed' under R318.1, which has no such italic word" in p for p in problems)   # stale


@pytest.mark.parametrize("lines,expect", [
    (["The landing shall be not less than 1.5. The tread"], ["not less than 1.5"]),     # a number ending a sentence
    (["shall be 36 inches.", "2. Where the stair is", "curved"], ["36 inch"]),           # a list item's own number
    (["area of 200 gross square feet"], ["200 gross square foot"]),
    # Chapter 4 part c's conversion walk (BCNYS 420.8, 407.5.3): a word after a sentence's end is never the number's
    # unit ("not be greater than", "30.", "2. In Group I-1" read as 30 inches), and "net" is read like "gross"
    (["shall not be greater than", "30.", "2. In Group I-1, Condition 2"], ["not be greater than 30", "2"]),
    (["installed in accordance with Section 907. In Group"], ["907"]),
    (["Not less than 30 net square feet (2.8 m[fn2]) per"], ["not less than 30 net square foot", "2.8 m"])])
def test_numbers_of_a_pieces_lines(lines, expect):
    from document_extraction.numbers import statements_of_lines
    assert [shown(s) for s in statements_of_lines(lines)] == expect


def test_a_defined_word_in_roman_type_is_brought_in_in_its_ies_plural_too():
    # review round 6: "stories" (roman) never brought in STORY; only "story", "storys", "storyes" did
    rows = _book()
    rows.insert(5, _row(1, 53, "[RB] STORY. A level of a building.", bold="[RB] STORY."))   # after FLIGHT
    rows.insert(12, _row(2, 6, "In houses of two stories the stair is enclosed."))
    cut = icc_sections.split(rows, BROUGHT_IN)
    assert "R202:story" in [p["id"] for p in cut["pieces"]]


def test_an_undefined_italic_word_beside_a_defined_one_in_one_phrase_must_be_named_too():
    # review round 6: in "nonhabitable flights", FLIGHT was found and "nonhabitable" was silently dropped
    rows = _book([_row(2, 6, "R318.1.2 Attics. Stairs to nonhabitable flights.", bold="R318.1.2 Attics.",
                       italic=["nonhabitable flights"])])
    problems = icc_sections.split(rows, BROUGHT_IN)["problems"]
    assert any("R318.1.2: italic 'nonhabitable' is not defined in Section R202" in p for p in problems), problems
    # a word joining two defined terms, or the "s" of "flight(s)", is no undefined word
    rows = _book([_row(2, 6, "R318.1.2 Runs. A flight(s) or stair.", bold="R318.1.2 Runs.",
                       italic=["flight(s) or stair"])])
    assert icc_sections.split(rows, BROUGHT_IN)["problems"] == []


# ---- appendices (egress step 1b: Appendix BO) ---------------------------------------------------------------------

def _appendix(extra=()):
    """The made-up book, then an appendix on p.3: its opening, its own definitions and two sections."""
    rows = _book()
    rows += [_row(3, 1, "102102166"), _row(3, 2, "APPENDIX", bold="APPENDIX"), _row(3, 3, "BO", bold="BO"),
             _row(3, 4, "User notes:", bold="User notes:"),
             _row(3, 5, "SECTION BO103—DEFINITIONS", bold="SECTION BO103—DEFINITIONS"),
             _row(3, 6, "BO103.1 General. The terms used in this appendix.", bold="BO103.1 General."),
             _row(3, 7, "[NY] HOME OCCUPATION. A use of a dwelling.", bold="[NY] HOME OCCUPATION."),
             _row(3, 8, "[NY] PORCH. An appendix porch.", bold="[NY] PORCH."),
             _row(3, 9, "[NY] WORK AREA. The altered part.", bold="[NY] WORK AREA."),
             _row(3, 10, "SECTION BO105—ALTERATIONS", bold="SECTION BO105—ALTERATIONS"),
             _row(3, 11, "BO105.1 General. In work areas each flight shall have a porch.", bold="BO105.1 General.",
                  italic=["work areas", "flight"]),
             _row(3, 12, "BO105.1.1 Level 1. Not egress.", bold="BO105.1.1 Level 1."),
             *extra,
             _row(3, 20, "BO105.2 Newly constructed. Not brought in.", bold="BO105.2 Newly constructed."),
             _row(3, 21, "2025 RESIDENTIAL CODE OF NEW YORK STATE 13")]
    return rows


APPENDIX = {"pages": "1-3", "sections": ["R318"], "alone": ["BO105.1"]}


def test_an_appendixs_own_definitions_apply_only_in_that_appendix():
    rows = _appendix()
    at = next(i for i, r in enumerate(rows) if r.get("text", "").startswith("R318.1.1"))
    rows.insert(at + 1, _row(2, 6, "R318.1.2 Work. In the work area a stair is kept.", bold="R318.1.2 Work.",
                             italic=["work area"]))
    cut = icc_sections.split(rows, APPENDIX | {"italic_not_defined": {"R318.1.2": {"work area": "R201.3"}}})
    assert cut["problems"] == [], cut["problems"]
    by = {p["id"]: p for p in cut["pieces"]}
    # BO105.1 uses the appendix's WORK AREA and Chapter 2's FLIGHT; its roman "porch" brings in both PORCH definitions
    assert by["BO105.1"]["uses"] == ["BO103:work_area", "R202:flight"]
    assert by["BO105.1"]["defined_terms_in_roman"] == ["BO103:porch", "R202:porch"]
    # the appendix's definitions never apply in the code itself: no R318 piece names BO103:porch
    assert not any(d.startswith("BO103:") for p in cut["pieces"] if p["id"].startswith("R318")
                   for d in p["uses"] + p["defined_terms_in_roman"])
    # the heading the appendix's definitions sit under comes in with them, and the part saying where they apply
    assert {"BO103", "BO103.1"} <= set(by)
    assert "BO103:home_occupation" not in by                     # used by none


def test_a_part_brought_in_alone_leaves_the_parts_under_it_out():
    cut = icc_sections.split(_appendix(), APPENDIX)
    ids = [p["id"] for p in cut["pieces"]]
    assert "BO105.1" in ids and "BO105.1.1" not in ids
    assert any(o[3] == "BO105.1.1" for o in cut["outside"])
    assert any("BO105.1: brought in, but no such heading" in p
               for p in icc_sections.split(_book(), APPENDIX | {"pages": "1-2"})["problems"])


def test_the_books_own_misnumbering_is_cut_only_where_sources_yaml_names_it():
    skip = [_row(3, 13, "BO105.1.4 Skipped. The book has no BO105.1.2.", bold="BO105.1.4 Skipped."),
            _row(3, 14, "BO112.1.1 Stray. Printed inside BO105.", bold="BO112.1.1 Stray."),
            _row(3, 15, "BO105.1.5 After. Goes on.", bold="BO105.1.5 After.")]
    problems = icc_sections.split(_appendix(skip), APPENDIX)["problems"]
    assert any("p.3 line 13: BO105.1.4 is out of order after BO105.1.1" in p for p in problems), problems
    assert any("p.3 line 14: BO112.1.1 is printed inside Section BO105" in p for p in problems), problems
    named = APPENDIX | {"printed_out_of_order": {"p.3 line 13": {"printed": "BO105.1.4", "why": "the book skips BO105.1.2"},
                                                 "p.3 line 14": {"printed": "BO112.1.1", "why": "a misprint"}}}
    cut = icc_sections.split(_appendix(skip), named)
    assert cut["problems"] == [], cut["problems"]
    outside = {o[3] for o in cut["outside"]}
    assert {"BO105.1.4", "BO112.1.1", "BO105.1.5"} <= outside          # each cut where printed, nothing merged
    stale = APPENDIX | {"printed_out_of_order": {"p.3 line 12": {"printed": "BO105.1.1", "why": "a heading in order"}}}
    assert any("names p.3 line 12 (printed_out_of_order)" in p for p in icc_sections.split(_appendix(), stale)["problems"])
    # review round 1: a name whose line prints another heading than it says is a problem, never applied
    wrong = APPENDIX | {"printed_out_of_order": {"p.3 line 13": {"printed": "BO105.1.9", "why": "stale"},
                                                 "p.3 line 14": {"printed": "BO112.1.1", "why": "a misprint"}}}
    problems = icc_sections.split(_appendix(skip), wrong)["problems"]
    assert any("names p.3 line 13 as printing 'BO105.1.9', but the book prints 'BO105.1.4'" in p for p in problems)


def test_a_term_new_yorks_rules_amend_is_cut_under_the_laws_term():
    # 19 NYCRR 1220.2(e)(4): the book prints HOME OCCUPATION twice; the second is LOAD-BEARING ELEMENT in law
    twice = [r if r.get("line") != 8 or r.get("page") != 3 else
             _row(3, 8, "[NY] HOME OCCUPATION. Any column or beam.", bold="[NY] HOME OCCUPATION.") for r in _appendix()]
    assert "BO103:home_occupation is cut twice" in icc_sections.split(twice, APPENDIX)["problems"]
    law = {"printed": "HOME OCCUPATION", "term": "LOAD-BEARING ELEMENT", "why": "19 NYCRR"}
    cut = icc_sections.split(twice, APPENDIX | {"amended_by_law": {"p.3 line 8": law}})
    assert cut["problems"] == [], cut["problems"]
    assert any(o[3] == "BO103:load_bearing_element" for o in cut["outside"])
    # review round 1: a stale line number never renames whatever term is printed there now (here PORCH)
    cut = icc_sections.split(_appendix(), APPENDIX | {"amended_by_law": {"p.3 line 8": law}})
    assert any("names p.3 line 8 as printing 'HOME OCCUPATION', but the book prints 'PORCH'" in p for p in cut["problems"])
    assert "BO103:porch" in next(p for p in cut["pieces"] if p["id"] == "BO105.1")["defined_terms_in_roman"]


def test_a_defined_term_with_a_plural_inside_it_is_found():
    # "changes of occupancy" is CHANGE OF OCCUPANCY, in italics and in roman type
    rows = _book([_row(2, 6, "R318.1.2 Uses. Changes of occupancy apply.", bold="R318.1.2 Uses.",
                       italic=["Changes of occupancy"])])
    rows.insert(4, _row(1, 52, "[RB] CHANGE OF OCCUPANCY. A change.", bold="[RB] CHANGE OF OCCUPANCY."))   # before FLIGHT
    cut = icc_sections.split(rows, BROUGHT_IN)
    assert cut["problems"] == [], cut["problems"]
    assert "R202:change_of_occupancy" in next(p for p in cut["pieces"] if p["id"] == "R318.1.2")["uses"]
    at = next(i for i, r in enumerate(rows) if r.get("text", "").startswith("R318.1.2"))
    rows[at] = _row(2, 6, "R318.1.2 Uses. Changes of occupancy apply.", bold="R318.1.2 Uses.")       # roman
    cut = icc_sections.split(rows, BROUGHT_IN)
    assert "R202:change_of_occupancy" in next(p for p in cut["pieces"] if p["id"] == "R318.1.2")["defined_terms_in_roman"]


def test_pages_that_only_list_section_numbers_are_found_by_their_running_head():
    from document_extraction.icc_references import lists_only, ways_out
    rows = [{"page": 21, "line": 2, "text": "CONTENTS"}, {"page": 859, "line": 2, "text": "REFERENCED STANDARDS"},
            {"page": 1070, "line": 2, "text": "INDEX"}, {"page": 98, "line": 2, "text": "BUILDING PLANNING"}]
    assert lists_only(rows) == {21, 859, 1070}
    # a part brought in alone: the parts under it are not brought in, so a pointer to one is listed
    pieces = [{"id": "BO102.6", "kind": "section", "lines": [[1, 1, 1]]}]
    lines = {(1, 1): "Replacement windows shall comply with BO102.6.1 and BO102.6."}
    assert ways_out(pieces, lines, [], alone=["BO102.6"]) == {"BO102.6.1": ["BO102.6"]}


def test_a_defined_term_with_an_ies_plural_inside_it_is_found_in_roman_type():
    # review round 1: "stories above grade plane" (roman) never named STORY ABOVE GRADE PLANE
    rows = _book([_row(2, 6, "R318.1.2 Height. Two stories above grade plane at most.", bold="R318.1.2 Height.")])
    rows.insert(7, _row(1, 53, "[RB] STORY ABOVE GRADE PLANE. A story.", bold="[RB] STORY ABOVE GRADE PLANE."))  # after STAIR
    cut = icc_sections.split(rows, BROUGHT_IN)
    assert cut["problems"] == [], cut["problems"]
    assert "R202:story_above_grade_plane" in next(p for p in cut["pieces"] if p["id"] == "R318.1.2")["defined_terms_in_roman"]


def _patio(extra=()):
    """The made-up book, then an appendix like BF on p.3: a section titled DEFINITION (singular), and a term printed
    under a numbered part titled "Definition" inside another section (BF106.2)."""
    rows = _book()
    rows += [_row(3, 1, "102102166"), _row(3, 2, "APPENDIX", bold="APPENDIX"), _row(3, 3, "BF", bold="BF"),
             _row(3, 4, "SECTION BF101—GENERAL", bold="SECTION BF101—GENERAL"),
             _row(3, 5, "BF101.1 Scope. Patio covers shall conform.", bold="BF101.1 Scope.", italic=["Patio covers"]),
             _row(3, 6, "SECTION BF102—DEFINITION", bold="SECTION BF102—DEFINITION"),
             _row(3, 7, "BF102.1 General. The following term.", bold="BF102.1 General."),
             _row(3, 8, "PATIO COVER. A structure with open walls.", bold="PATIO COVER."),
             _row(3, 9, "SECTION BF106—SCREENS", bold="SECTION BF106—SCREENS"),
             _row(3, 10, "BF106.1 General. Screen enclosures follow this section.", bold="BF106.1 General.",
                  italic=["Screen enclosures"]),
             _row(3, 11, "BF106.2 Definition. The following term.", bold="BF106.2 Definition."),
             _row(3, 12, "SCREEN ENCLOSURE. A building with screen walls.", bold="SCREEN ENCLOSURE."),
             _row(3, 13, "BF106.3 Screen enclosures. Not brought in.", bold="BF106.3 Screen enclosures."),
             *extra,
             _row(3, 19, "SECTION BF107—OTHER", bold="SECTION BF107—OTHER"),
             _row(3, 20, "2025 RESIDENTIAL CODE OF NEW YORK STATE 13")]
    return rows


def test_appendix_bfs_singular_definition_section_and_its_definition_part_cut_their_terms():
    # egress step 1c: Appendix BF titles its section of definitions "DEFINITION" and prints a second term under
    # "BF106.2 Definition."; read only as "DEFINITIONS", BF101.1's italic "Patio covers" matched no definition
    cut = icc_sections.split(_patio(), {"pages": "1-3", "sections": ["R318", "BF101", "BF106.1"]})
    assert cut["problems"] == [], cut["problems"]
    by = {p["id"]: p for p in cut["pieces"]}
    assert by["BF101.1"]["uses"] == ["BF102:patio_cover"] and by["BF106.1"]["uses"] == ["BF106.2:screen_enclosure"]
    assert by["BF102:patio_cover"]["kind"] == by["BF106.2:screen_enclosure"]["kind"] == "definition"
    # the part saying where the term applies comes in with it, the rest of its section does not; the definition
    # part ends at the next heading: BF106.3 is a numbered part again, never a term
    assert {"BF102", "BF102.1", "BF106.2"} <= set(by) and any(o[3] == "BF106.3" for o in cut["outside"])
    # a bold capitals line after a numbered part that is not "Definition(s)" is not a term
    plain = icc_sections.split(_patio([_row(3, 14, "NOT A TERM. Bold capitals.", bold="NOT A TERM.")]),
                               {"pages": "1-3", "sections": ["R318", "BF101", "BF106.1"]})
    assert plain["problems"] == [] and not any("not_a_term" in o[3] for o in plain["outside"])


def test_a_gap_in_the_pages_read_ends_a_definition_part():
    # review round 5 of egress step 1c: a gap reset the section but not the "Definition" part, so bold capitals at
    # the top of the next page read were cut as a term of BF106.2, a part on another page
    rows = [r for r in _patio() if not (r.get("page") == 3 and r.get("line") in (13, 19, 20))]
    rows += [_row(5, 1, "102102166"), _row(5, 2, "ZEBRA STRIPE. A line.", bold="ZEBRA STRIPE."),
             _row(5, 3, "2025 RESIDENTIAL CODE OF NEW YORK STATE 15")]
    cut = icc_sections.split(rows, {"pages": "1-3,5", "sections": ["R318", "BF101", "BF106.1"]})
    ids = {p["id"] for p in cut["pieces"]} | {o[3] for o in cut["outside"]}
    assert not any("zebra_stripe" in i for i in ids), ids
    assert any(o[0] == 5 and o[3] == "before the first heading on p.5" for o in cut["outside"]), cut["outside"]


def test_a_definitions_part_inside_a_section_of_definitions_leaves_its_terms_named_by_the_section():
    # review round 1 of egress step 1c: "BJ102.1 Definitions." printed under "SECTION BJ102—DEFINITIONS" (p.912) cut
    # its terms as "BJ102.1:term", silently leaving the section's heading out
    rows = _book()
    at = next(i for i, r in enumerate(rows) if r.get("text", "").startswith("SECTION R202"))
    rows.insert(at + 1, _row(1, 3, "R202.1 Definitions. The following words.", bold="R202.1 Definitions."))
    cut = icc_sections.split(rows, BROUGHT_IN)
    ids = {p["id"] for p in cut["pieces"]}
    assert cut["problems"] == [] and {"R202", "R202:flight", "R202:stair"} <= ids and not any(
        i.startswith("R202.1:") for i in ids)


# ---- the code cache's text: the whole book, the same for every branch (book_text.py) --------------------------------

ORDINANCE = "regulations/jurisdictions/new_york/ithaca_city/1_source_documents/ordinance_no_2025-12_southside_form_districts.pdf"


@pytest.fixture(scope="module")
def whole_book():
    """A PDF in the repo read as the code cache keeps a book: every page, each page's counts in the header."""
    from document_extraction.icc import read_book
    from rule_format.rulebook import REPO
    return REPO / ORDINANCE, read_book(REPO / ORDINANCE)


def test_a_branchs_pages_chosen_from_the_whole_book_are_a_fresh_extraction_of_them_byte_for_byte(whole_book):
    from document_extraction.book_text import select
    from document_extraction.extract import to_jsonl
    from document_extraction.icc import extract_icc
    pdf, book = whole_book
    assert book[0]["pages_read"] == "all" and len(book[0]["page_counts"]) == book[0]["pages"]
    for pages in ([1, 2, 3], [5, 30, 31, 37], [36, 4]):
        assert to_jsonl(select(book, pages)) == to_jsonl(extract_icc(pdf, pages))   # header and counts included
    with pytest.raises(ValueError):
        select(book, [38])                                                         # never a page short, silently
    with pytest.raises(ValueError):
        select(extract_icc(pdf, [1, 2]), [1])                                      # only a whole book is chosen from


def test_the_cached_texts_name_is_the_books_and_the_extractors_never_the_branchs(tmp_path, monkeypatch):
    import shutil
    from document_extraction import book_text
    a = {"file": "code.pdf", "sha256": "x", "brought_in": {"pages": "34-56"}}
    b = a | {"brought_in": {"pages": "34-56, 898"}}                  # another branch brings in one more page
    assert book_text.file_name(a) == book_text.file_name(b)
    copy = tmp_path / "code"
    copy.mkdir()
    for name in {n for names in book_text.TEXT_CODE.values() for n in names}:
        shutil.copy(book_text.HERE / name, copy / name)
    monkeypatch.setattr(book_text, "HERE", copy)
    before = book_text.file_name(a)
    icc = (copy / "icc.py").read_bytes()
    (copy / "icc.py").write_bytes(icc.replace(b"\n", b"\r\n"))       # a Windows checkout: the same extractor
    assert book_text.file_name(a) == before
    (copy / "icc.py").write_bytes(icc + b"\n# reads pages another way\n")
    assert book_text.file_name(a) != before                          # another extractor: a text of its own


def test_check_refuses_a_cached_book_whose_brought_in_pages_are_not_a_fresh_extraction(whole_book, tmp_path, capsys):
    import json
    import document_extraction.__main__ as cli
    from document_extraction.extract import to_jsonl
    from document_extraction.icc import extract_icc
    pdf, book = whole_book
    text = tmp_path / "book.text_k.jsonl"
    text.write_text(to_jsonl(book), encoding="utf-8")
    pages = [2, 3]
    fresh = extract_icc(pdf, pages)
    assert cli._same_as_cached(pdf, text, pages, fresh, check=True)
    edited = [dict(r) for r in book]
    next(r for r in edited if r.get("page") == 3)["text"] += " x"            # one brought-in line changed
    text.write_text(to_jsonl(edited), encoding="utf-8")
    assert not cli._same_as_cached(pdf, text, pages, fresh, check=True)
    assert text.read_text(encoding="utf-8") == to_jsonl(edited)              # --check writes nothing
    unchecked = [dict(r) for r in book]
    next(r for r in unchecked if r.get("page") == 9)["text"] += " x"         # a page this branch doesn't bring in
    text.write_text(to_jsonl(unchecked), encoding="utf-8")
    assert cli._same_as_cached(pdf, text, pages, fresh, check=True)
    text.write_text(to_jsonl(edited), encoding="utf-8")
    assert cli._same_as_cached(pdf, text, pages, fresh, check=False)         # written again, the whole book
    assert text.read_text(encoding="utf-8") == to_jsonl(book) and not list(tmp_path.glob("*.part*"))
    assert json.loads(text.read_text(encoding="utf-8").splitlines()[0])["page_counts"]


def test_a_selections_header_counts_only_its_own_pages():
    # The repo's PDFs have no rotated text or stacked fractions; the book has both, counted page by page.
    from document_extraction.book_text import header, select
    counts = {1: (2, 1), 2: (5, 0), 3: (0, 7)}
    book = [header("b.pdf", "s", 3, "e", counts, None) | {"page_counts": {str(p): list(c) for p, c in counts.items()}},
            {"page": 1, "line": 1, "text": "a"}, {"page": 2, "line": 1, "text": "b"}, {"page": 3, "line": 1, "text": "c"}]
    assert book[0]["rotated_chars_skipped"] == 7 and book[0]["fractions_joined"] == 8
    head, *rows = select(book, [3, 2])
    assert head == {"file": "b.pdf", "sha256": "s", "pages": 3, "extractor": "e", "rotated_chars_skipped": 5,
                    "fractions_joined": 7, "pages_read": [3, 2]}
    assert [r["text"] for r in rows] == ["c", "b"]                  # in the order the pages are named, as read
