"""An ICC code book (layout: icc): stacked fractions put back together (icc.py), the book cut into pieces at its own
bold headings with nothing skipped (icc_sections.py), and every number read with its limit words (numbers.py).
Built lines and characters, so each safeguard is tested on its own, without the copyrighted book."""

import pytest

from document_extraction import icc_sections
from document_extraction.icc import join_fractions, line_text
from document_extraction.numbers import shown, statements

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
    assert got == ["not more than 8 1/4 inch", "209 mm", "by more than 3/8 inch", "three or fewer", "one"]


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


@pytest.mark.parametrize("text,expect", [
    ("not less than that of a quarter circle", ["a quarter"]), ("not less than one-half of the area", ["not less than one-half"]),
    ("two-thirds of the width", ["two-thirds"]), ("thirteen risers", ["thirteen riser"]), ("one-family", ["one"]),
    ("three-fourths of", ["three-fourths"]), ("twenty-four inches", ["twenty-four inch"]), ("4-3/8 inches", ["4-3/8 inch"]),
    ("not less than 5.7 square feet", ["not less than 5.7 square foot"]), ("5.7 square inches", ["5.7 square inch"]),
    ("1 unit vertical in 12 units horizontal", ["1 unit vertical", "12 unit horizontal"])])
def test_parts_of_a_whole_and_larger_number_words_are_numbers_too(text, expect):
    assert [shown(s) for s in statements(text)] == expect          # "one-half" is never the number one
