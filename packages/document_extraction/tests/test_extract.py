import json
import shutil
from pathlib import Path

import pytest

import document_extraction.__main__ as cli
from document_extraction.extract import extract, sha256, to_jsonl
from rule_format.rulebook import Context, quote_found

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
