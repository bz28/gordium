"""The rules workbook says exactly what the rule files say: every source of every rule, definition and use
name, every open question and every piece of the law once, each attributed to where it came from and
linked to the right document and page."""

import datetime

import pytest
from openpyxl import load_workbook

import rule_export.__main__ as cli
import rule_export.workbook as wbk
from rule_export.workbook import (FIELDS, HIDDEN, SHOWN, build, contents, output_path, page_link, pdf_url, rulebooks,
                                  tables)
from rule_format.labels import load_pieces
from rule_format.rulebook import REPO, load

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
LAW = "chapter_325_zoning_2026-10.pdf"
DOCUMENTS = {d["file"]: d for d in load(ITHACA / "1_source_documents/sources.yaml")["documents"]}
LABELS = load(ITHACA / "3_section_labels/chapter_325_zoning_2026-10.yaml")["labels"]


@pytest.fixture(scope="module")
def data():
    return tables(ITHACA)


def column(t, header):
    i = [h for h, _ in t["columns"]].index(header)
    return [row[i] for row in t["rows"]]


def link(s):
    return page_link(ITHACA, DOCUMENTS, s["file"], s["page"])


def test_every_field_of_every_format_is_shown_or_left_out_on_purpose():
    for kind, fields in FIELDS.items():
        assert SHOWN[kind] | (fields & HIDDEN.keys()) == fields, kind          # nothing silently missing
        assert SHOWN[kind] <= fields, kind                                    # nothing shown that doesn't exist


def test_every_rule_source_is_one_row_with_its_rulebook_words_and_link(data):
    t = data["Rules"]
    expected = [(path, r["id"], r.get("drafted_by"), s["page"], s["quote"], link(s))
                for path, book in rulebooks(ITHACA) for r in book["rules"] for s in r["sources"]]
    got = list(zip(column(t, "Rulebook"), column(t, "Rule id"), column(t, "Drafted by"), column(t, "Page"),
                   column(t, "City's exact words"), t["links"]["Link"]))
    assert got == expected and got                                             # each once, in order, attributed


def test_rules_show_their_worked_examples(data):
    t = data["Rules"]
    first = {rid: ex for rid, ex, src in zip(column(t, "Rule id"), column(t, "Worked examples"), column(t, "Source"))
             if src.startswith("1 of")}
    assert "rear_yard = 20, lot_depth = 94.8 → fail" in first["R-1b.rear_yard"]


def test_two_rulebooks_with_the_same_rule_id_stay_apart(monkeypatch):
    rule = {"id": "R-1b.height", "title": "Height", "drafted_by": "claude", "status": "draft",
            "sources": [{"file": LAW, "page": 47, "lines": [6, 6], "quote": "a"},
                        {"file": LAW, "page": 47, "lines": [8, 8], "quote": "b"}]}
    drafted = rule | {"drafted_by": "rule_drafting/claude-sonnet-5-5"}
    monkeypatch.setattr(wbk, "rulebooks", lambda j: [("R-1b.yaml", {"district": "R-1b", "rules": [rule]}),
                                                     ("drafted/R-1b.yaml", {"district": "R-1b", "rules": [drafted]})])
    t = tables(ITHACA)["Rules"]
    rows = list(zip(column(t, "Rulebook"), column(t, "Rule id"), column(t, "Drafted by"), column(t, "Source")))
    assert len(set(rows)) == len(rows) == 4                                    # every row says which book it's from
    assert ("drafted/R-1b.yaml", "R-1b.height", "rule_drafting/claude-sonnet-5-5", "2 of 2") in rows


def test_every_definition_and_use_source_is_one_row_with_its_link(data):
    for tab, schema, label in [("Definitions", "definitions", "term"), ("Uses", "uses", "name")]:
        entries = load(ITHACA / f"4_term_definitions/{schema}.yaml")
        expected = [(k, s["page"], s["quote"], link(s)) for k, e in entries.items() for s in e["sources"]]
        t = data[tab]
        assert list(zip(column(t, "Id"), column(t, "Page"), column(t, "City's exact words"), t["links"]["Link"])) == expected


def test_every_open_question_is_listed_once_where_it_was_asked(data):
    expected = []
    for path, book in rulebooks(ITHACA):
        for r in book["rules"]:
            expected += [("Rule", f"5_zoning_rules/{path}", r["id"], q, link(r["sources"][0])) for q in r.get("open_questions", [])]
    for schema in ("definitions", "uses"):
        for k, d in load(ITHACA / f"4_term_definitions/{schema}.yaml").items():
            expected += [(schema.rstrip("s").capitalize(), f"4_term_definitions/{schema}.yaml", k, " ".join(q.split()),
                          link(d["sources"][0])) for q in d.get("open_questions", [])]
    for pid, e in LABELS.items():
        expected += [("Section label", LAW, pid, " ".join(q.split()), link(e["sources"][0])) for q in e.get("open_questions", [])]
    t = data["Questions"]
    got = list(zip(column(t, "About"), column(t, "In"), column(t, "Id"), column(t, "Question"), t["links"]["Link"]))
    assert got == [(a, b, c, " ".join(d.split()), e) for a, b, c, d, e in expected] and got


def test_every_piece_of_the_law_is_one_coverage_row_with_its_label_and_link(data):
    _, pieces = load_pieces(ITHACA / "2_extracted_text/chapter_325_zoning_2026-10.sections.jsonl")
    t = data["Coverage"]
    assert list(zip(column(t, "Document"), column(t, "Piece"), column(t, "Label"), t["links"]["Link"])) == [
        (LAW, p, LABELS.get(p, {}).get("label", "unlabeled"), page_link(ITHACA, DOCUMENTS, LAW, piece["lines"][0][0]))
        for p, piece in pieces.items()]
    changes = dict(zip(column(t, "Piece"), column(t, "Changed after the AI")))
    assert "reference → rule (Claude" in changes["325-3B:dwelling_one_family"]  # who changed it, from what, to what


def test_a_chain_of_label_changes_reads_in_order():
    revised = [{"from": "reference", "by": "A", "date": datetime.date(2026, 1, 1), "why": "x"},
               {"from": "rule", "by": "B", "date": datetime.date(2026, 1, 2), "why": "y"}]
    text = wbk._revisions(revised, "flag")
    assert "reference → rule (A, 2026-01-01): x" in text and "rule → flag (B, 2026-01-02): y" in text


def test_links_open_the_city_pdf_or_the_fingerprinted_copy():
    assert pdf_url(ITHACA, DOCUMENTS, "zoning_charts_2026-04.pdf").startswith("https://www.cityofithacany.gov/DocumentCenter/View/")
    # Chapter 325's official page is HTML (eCode360), where our page numbers mean nothing: link the exact copy.
    assert pdf_url(ITHACA, DOCUMENTS, LAW) == (
        "https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/" + LAW)


def test_text_is_never_a_formula_and_odd_characters_dont_crash(tmp_path):
    t = {"T": {"title": "t", "columns": [("A", 10)], "rows": [["=HYPERLINK(\"x\")"], ["bad\x07char"]], "links": {}}}
    path = tmp_path / "t.xlsx"
    build(t).save(path)
    ws = load_workbook(path)["T"]
    assert ws["A3"].value == '=HYPERLINK("x")' and ws["A3"].data_type == "s"   # shown as the words, never run
    assert ws["A4"].value == "bad�char"


def test_the_workbook_lays_out_every_table_with_working_links(data):
    wb = build(data)
    assert wb.sheetnames == ["Rules", "Definitions", "Uses", "Questions", "Coverage", "Sources"]
    for name, t in data.items():
        ws = wb[name]
        assert ws.freeze_panes == "A3" and [c.value for c in ws[2]] == [h for h, _ in t["columns"]]
        for header, urls in t["links"].items():                              # each link sits in its own column
            c = [h for h, _ in t["columns"]].index(header) + 1
            assert [ws.cell(row=r, column=c).hyperlink.target if ws.cell(row=r, column=c).hyperlink else None
                    for r in range(3, 3 + len(urls))] == urls


def test_the_committed_workbook_is_current_and_check_catches_a_stale_one(tmp_path, monkeypatch, capsys):
    assert contents(load_workbook(output_path(ITHACA))) == contents(build(tables(ITHACA)))
    assert cli.main(["--check"]) == 0
    stale = build(tables(ITHACA))
    stale["Rules"]["Q3"] = "words the city never wrote"
    path = tmp_path / "stale.xlsx"
    stale.save(path)
    monkeypatch.setattr(cli, "output_path", lambda j: path)
    assert cli.main(["--check"]) == 1 and "differs from a fresh build" in capsys.readouterr().out
