import json
import shutil
from pathlib import Path

import pytest

import document_extraction.__main__ as cli
from document_extraction.extract import extract, sha256, to_jsonl
from rule_format.rulebook import Context, locate, tokenize


def quote_found(quote, page):
    """Is the quote anywhere on the page ({line: tokens})?"""
    return bool(locate(quote, page))

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
CHARTS = ITHACA / "1_source_documents/zoning_charts_2026-04.pdf"


@pytest.fixture(scope="module")
def charts():
    return extract(CHARTS)


def test_header_identifies_the_exact_pdf(charts):
    header = charts[0]
    assert header["file"] == CHARTS.name
    assert header["sha256"] == sha256(CHARTS)
    assert header["pages"] == 17


def test_every_page_is_accounted_for_in_order(charts):
    pages = [r["page"] for r in charts[1:]]
    assert pages == sorted(pages)
    assert set(pages) == set(range(1, 18))
    assert all(r["text"].strip() and r["x0"] < r["x1"] and r["top"] < r["bottom"] for r in charts[1:])


def test_doubled_bold_text_is_read_once(charts):
    page_3 = [r["text"] for r in charts[1:] if r["page"] == 3]
    assert page_3[0] == "RESIDENTIAL DISTRICTS BULK +"          # not "RREESSIIDDEENNTTIIAALL..."
    assert any("125 ft" in t for t in page_3)                  # not "12 5 f t"


def test_same_pdf_gives_identical_output(charts):
    assert to_jsonl(extract(CHARTS)) == to_jsonl(charts)


@pytest.mark.parametrize("file, page, quote", [
    ("zoning_charts_2026-04.pdf", 3, "Rear (minimum, % of depth or feet, 25%/ 25%/"),
    ("zoning_charts_2026-04.pdf", 3, "One-family dwelling, detached 10,000 sf 6,000 sf"),
    ("chapter_325_zoning_2026-10.pdf", 11, "GRADE PLANE — A reference plane representing the average of finished ground level"),
    ("chapter_325_zoning_2026-10.pdf", 49, "All porches, attached or freestanding decks, balconies projecting more than"),
    ("ordinance_no_2025-12_southside_form_districts.pdf", 1, "AUTHENTICATION OF ORDINANCE NO. 2025-12"),
])
def test_saved_text_finds_known_quotes_on_the_right_page(file, page, quote):
    ctx = Context.for_jurisdiction(ITHACA)
    assert ctx.problems == []
    assert quote_found(quote, ctx.pages[file][page])
    assert not quote_found(quote, ctx.pages[file][page + 1])


def _jurisdiction(tmp_path, sha=None):
    src = tmp_path / "regulations/jurisdictions/ny/town/1_source_documents"
    src.mkdir(parents=True)
    shutil.copy(CHARTS, src / CHARTS.name)
    (src / "sources.yaml").write_text(f"documents:\n  - file: {CHARTS.name}\n    sha256: {sha or sha256(CHARTS)}\n")
    return src.parent / "2_extracted_text" / f"{CHARTS.stem}.jsonl"


def test_check_catches_a_hand_edited_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO", tmp_path)
    out = _jurisdiction(tmp_path)
    assert cli.main([]) == 0 and cli.main(["--check"]) == 0
    rows = out.read_text().splitlines()
    edited = json.loads(rows[5]) | {"text": "25%/ 50 ft"}
    out.write_text("\n".join([*rows[:5], json.dumps(edited), *rows[6:]]) + "\n")
    assert cli.main(["--check"]) == 1


def test_refuses_a_pdf_whose_fingerprint_changed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "REPO", tmp_path)
    out = _jurisdiction(tmp_path, sha="0" * 64)
    assert cli.main([]) == 1
    assert not out.exists()
    assert "fingerprint doesn't match" in capsys.readouterr().out


def test_footnote_markers_are_marked_not_read_as_values(charts):
    page_3 = [r["text"] for r in charts[1:] if r["page"] == 3]
    stories = next(t for t in page_3 if t.startswith("Number of stories"))
    assert "3/2 [fn11] 4" in stories                                 # R-3aa: 3/2 stories, footnote 11
    page = {1: tokenize(" ".join(page_3))}
    for misreading in ("3/2 11 4", "11 4 3 Height in feet", "4 5,000 sf 5,000 sf",
                       "Number of stories 3 3 3 3 3 4 … 11 4 3"):     # footnote read as a value
        assert not quote_found(misreading, page)
    assert any("2,500 sf [fn4] 5,000 sf" in t for t in page_3)


def test_sideways_text_is_left_out_and_counted():
    rows = extract(ITHACA / "1_source_documents/ordinance_no_2025-12_southside_form_districts.pdf")
    assert rows[0]["rotated_chars_skipped"] == 345                    # vertical and angled diagram labels
    texts = [r["text"] for r in rows[1:]]
    assert not any(t == "kcabteS" for t in texts)                       # "Setback" read backwards (vertical)
    assert not any("requ s" in t for t in texts)                        # angled label read scrambled


def test_almost_vertical_map_labels_are_left_out():
    rows = extract(ITHACA / "1_source_documents/zoning_maps_2026-05.pdf")
    assert rows[0]["rotated_chars_skipped"] > 7000                       # street labels at 1°-92°, 30°, 60°
    assert not any("D V L B" in r["text"] for r in rows[1:])             # "BLVD" read backwards


def test_unknown_arguments_are_rejected_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO", tmp_path)
    out = _jurisdiction(tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["--chek"])                                          # typo of --check
    assert e.value.code == 2 and not out.exists()


def _mark(text, sizes, bottoms, body=10):
    chars = [{"size": z, "bottom": b} for z, b in zip(sizes, bottoms)]
    from document_extraction.extract import _mark_superscripts
    return _mark_superscripts({"text": text, "chars": chars}, body)


@pytest.mark.parametrize("text, sizes, bottoms, expected", [
    ("5 10", [10, 6, 6], [100, 95, 95], "5 [fn10]"),                       # footnotes are most of the line
    ("Height 5 10", [10] * 7 + [6, 6], [100] * 7 + [95, 95], "Height 5 [fn10]"),
    ("19th 2025", [10, 10, 7, 7, 10, 10, 10, 10], [100, 100, 95, 95, 100, 100, 100, 100], "19th 2025"),  # ordinal
    ("R-1b", [6, 6, 6, 6], [100, 100, 100, 100], "R-1b"),                   # small but not raised: a label
    ("x 3", [10, 6], [100, 100], "x 3"),                                     # small but level: not a footnote
])
def test_footnote_is_small_and_raised(text, sizes, bottoms, expected):
    assert _mark(text, sizes, bottoms) == expected


@pytest.mark.parametrize("file, page, quote", [
    ("ordinance_no_2025-12_southside_form_districts.pdf", 21, "Height (stories), max 3 A Length of blank wall"),  # two columns mixed
    ("zoning_maps_2026-05.pdf", 1, "City of Ithaca Zoning Map May 2026"),
])
def test_real_not_quotable_documents_are_refused(file, page, quote):
    from rule_format.rulebook import _source_problems
    ctx = Context.for_jurisdiction(ITHACA)
    assert quote_found(quote, ctx.pages[file][page])                     # the words really are there…
    assert any("isn't quotable yet" in p for p in _source_problems([{"file": file, "page": page, "quote": quote}], ctx))


def test_docs_describe_the_extraction_check_ci_runs():
    """CI re-extracts every PDF (document_extraction --check); no doc may still say that's to come."""
    from rule_format.rulebook import REPO
    assert "python -m document_extraction --check" in (REPO / ".github/workflows/ci.yml").read_text()
    files = [p for p in REPO.rglob("*") if p.suffix in (".md", ".py") and p.is_file()
             and not {".git", ".claude", ".venv"} & set(p.relative_to(REPO).parts) and p.name != "test_extract.py"]
    stale = [p.relative_to(REPO) for p in files if "text-extraction step is merged" in p.read_text(errors="ignore")]
    assert not stale, stale
