"""The rules workbook says exactly what the rule files say: every source of every rule, definition and use
name, every open question and every piece of the law once, each attributed to where it came from and
linked to the right document and page."""

import datetime

import pytest
from openpyxl import load_workbook

import rule_export.__main__ as cli
import rule_export.workbook as wbk
from rule_export.workbook import (COLUMNS, FIELDS, HIDDEN, build, contents, entry_rows, output_path, page_link,
                                  pdf_url, rulebooks, shown, tables)
from rule_format.labels import load_pieces
from rule_format.rulebook import REPO, Context, _cell, load

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
LAW = "chapter_325_zoning_2026-10.pdf"
ITHACA_TITLES = {d["file"]: d.get("title") or d["file"] for d in load(ITHACA / "1_source_documents/sources.yaml")["documents"]}
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
    assert FIELDS.keys() == COLUMNS.keys()
    for kind, fields in FIELDS.items():
        assert shown(COLUMNS[kind]) | (fields & HIDDEN.keys()) == fields, kind  # nothing silently missing
        assert shown(COLUMNS[kind]) <= fields, kind                            # nothing shown that doesn't exist


# One value of each field, in its format's shape, for checking that each column really shows its field.
SAMPLE = {"review_when": [{"when": "W", "reason": "R"}], "examples": [{"given": {"a": 1}, "expect": "pass"}],
          "open_questions": ["Q"], "answers": [{"question": "Q", "answer": "A"}], "measures": ["M"],
          "sources": [{"file": LAW, "page": 3, "lines": [1, 2], "quote": "W"}], "quotable": False,
          "revised": [{"from": "rule", "by": "B", "date": "D", "why": "Y"}],
          "research": [{"question": "Q", "searched": ["325-18B"], "why_open": "W"}],
          "findings": [{"question": "Q", "kind": "law", "answer": "A", "sources": []}]}


def test_every_column_shows_the_field_it_names():
    # Filling a field must change its column's cell: a column that forgot its field, or a field's column
    # removed, fails here or above.
    for kind, cols in COLUMNS.items():
        fixed = {c.header: "" for c in cols if c.value is None}
        for i, c in enumerate(cols):
            for field in c.fields:
                filled = entry_rows({field: SAMPLE.get(field, "X")}, cols, fixed)[0][i]
                assert filled != entry_rows({}, cols, fixed)[0][i], (kind, c.header, field)


def test_the_real_files_use_only_known_fields():
    sources = load(ITHACA / "1_source_documents/sources.yaml")
    for d in sources["documents"] + sources.get("not_yet_downloaded", []):
        assert d.keys() <= FIELDS["source"], d.keys() - FIELDS["source"]


def test_every_rule_source_is_one_row_with_its_rulebook_words_and_link(data):
    t = data["Rules"]
    ctx = Context.for_jurisdiction(ITHACA)
    words = lambda s: s["quote"] if "quote" in s else _cell(s, ctx)["value"]   # a quote, or the cell's value
    expected = [(path, r["id"], r.get("drafted_by"), s["page"], words(s), link(s))
                for path, book in rulebooks(ITHACA) for r in book["rules"] for s in r["sources"]]
    assert any("cell" in s for _, book in rulebooks(ITHACA) for r in book["rules"] for s in r["sources"])
    got = list(zip(column(t, "Rulebook"), column(t, "Rule id"), column(t, "Drafted by"), column(t, "Page"),
                   column(t, "City's exact words"), t["links"]["Link"]))
    assert got == expected and got                                             # each once, in order, attributed
    # what readers filter on repeats on every row, so a filter keeps all of a rule's quotes
    kinds = [(path, r["id"], r["kind"], r["topic"]) for path, book in rulebooks(ITHACA) for r in book["rules"]
             for _ in r["sources"]]
    assert list(zip(column(t, "Rulebook"), column(t, "Rule id"), column(t, "Kind"), column(t, "Topic"))) == kinds


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
        expected += [("Section label", "3_section_labels/chapter_325_zoning_2026-10.yaml", pid, " ".join(q.split()), link(e["sources"][0])) for q in e.get("open_questions", [])]
    t = data["Questions"]
    got = list(zip(column(t, "About"), column(t, "In"), column(t, "Id"), column(t, "Question"), t["links"]["Link"]))
    assert got == [(a, b, c, " ".join(d.split()), e) for a, b, c, d, e in expected] and got


def test_every_piece_of_the_law_is_one_coverage_row_with_its_label_and_link(data):
    _, pieces = load_pieces(ITHACA / "2_extracted_text/chapter_325_zoning_2026-10.sections.jsonl")
    t = data["Coverage"]
    first_page = lambda p, piece: ((LABELS.get(p, {}).get("sources") or [{}])[0].get("page") or piece["lines"][0][0])
    assert list(zip(column(t, "Document"), column(t, "Piece"), column(t, "Label"), t["links"]["Link"])) == [
        (LAW, p, LABELS.get(p, {}).get("label", "unlabeled"), page_link(ITHACA, DOCUMENTS, LAW, first_page(p, piece)))
        for p, piece in pieces.items()]
    # each quote says its own page and lines (a piece may start a page before its quote)
    quotes = dict(zip(column(t, "Piece"), column(t, "Quote(s)")))
    for p, e in LABELS.items():
        for s in e.get("sources") or []:
            assert f"p.{s['page']} l.{wbk._lines(s)}: " in quotes[p], p
    home = LABELS["325-3B:home_occupation"]["sources"][0]
    assert home["page"] == 13 and "Open p.13" in column(t, "Link")[column(t, "Piece").index("325-3B:home_occupation")]
    changes = dict(zip(column(t, "Piece"), column(t, "Changed after the AI")))
    assert "reference → rule (Claude" in changes["325-3B:dwelling_one_family"]  # who changed it, from what, to what


def test_every_source_document_and_missing_one_is_listed_with_its_details(data):
    sources = load(ITHACA / "1_source_documents/sources.yaml")
    t = data["Sources"]
    got = list(zip(column(t, "File"), column(t, "Title"), column(t, "Adopted"), column(t, "Created"),
                   column(t, "Quotable"), column(t, "Why not quotable / not downloaded"), column(t, "Contents"),
                   column(t, "Notes"), t["links"]["Official URL"]))
    text = lambda v: " ".join(str(v).split()) if v not in (None, "") else ""
    assert got == [(d["file"], d["title"], text(d.get("adopted_on")), text(d.get("created_on")),
                    "no" if d.get("quotable") is False else "yes", text(d.get("not_quotable_because")),
                    text(d.get("contents")), text(d.get("notes")), d["url"]) for d in sources["documents"]] + [
        ("", d["title"], "", "", "not downloaded", text(d["why_missing"]), "", "", d["url"])
        for d in sources["not_yet_downloaded"]]


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
    assert wb.sheetnames == ["Rules", "Definitions", "Uses", "Questions", "Findings", "Coverage", "Sources"]
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


def test_every_source_has_a_citation_people_can_read(data):
    """The document by its title, the section the quote is in (for a document cut into sections), page, lines."""
    cite = wbk.citer(ITHACA, DOCUMENTS)
    law = "City of Ithaca Code, Chapter 325 Zoning (full text)"
    assert cite({"file": LAW, "page": 24, "lines": [15, 16]}) == f"{law}, §325-8A, p.24, lines 15–16"
    assert cite({"file": LAW, "page": 5, "lines": [23, 25]}) == f"{law}, §325-3B (BUILDING AREA), p.5, lines 23–25"
    assert cite({"file": LAW, "page": 1, "lines": [10, 10]}) == f"{law}, Table of contents and history, p.1, line 10"
    _, pieces = load_pieces(ITHACA / "2_extracted_text/chapter_325_zoning_2026-10.sections.jsonl")
    page, first, _ = pieces["editors_note_1"]["lines"][0]
    assert cite({"file": LAW, "page": page, "lines": [first, first]}) == \
        f"{law}, {pieces['editors_note_1']['title']}, p.{page}, line {first}"   # no § for an unnumbered piece
    assert cite({"file": "zoning_charts_2026-04.pdf", "page": 3, "lines": [31, 31]}) == \
        "City of Ithaca Zoning Charts (April 2026), p.3, line 31"                 # no sections: page and line
    for tab in ("Rules", "Definitions", "Uses"):
        t = data[tab]
        sources = [s for _, e in ([(None, r) for _, b in rulebooks(ITHACA) for r in b["rules"]] if tab == "Rules" else
                                  load(ITHACA / f"4_term_definitions/{tab.lower()}.yaml").items()) for s in e["sources"]]
        assert column(t, "Citation") == [cite(s) for s in sources] and all(column(t, "Citation")), tab


def test_text_is_in_the_architects_ink_color(data):
    ws = build(data)["Rules"]
    assert ws["A1"].font.color.rgb.endswith(wbk.INK) and ws["A2"].font.color.rgb.endswith(wbk.INK)
    assert ws["A3"].font.color.rgb.endswith(wbk.INK) and ws["A3"].font.name == "Arial"



def test_check_also_catches_a_change_in_how_the_workbook_looks(tmp_path, data):
    """A saved workbook with the right words but old formatting is stale too (the look is part of the format)."""
    wb = build(data)
    path = tmp_path / "w.xlsx"
    wb.save(path)
    assert contents(load_workbook(path)) == contents(build(data))       # a saved copy reads back the same
    wb["Rules"]["A3"].font = wbk.Font(name="Calibri", size=11)
    wb.save(path)
    assert contents(load_workbook(path)) != contents(build(data))
    wb = build(data)
    wb["Rules"].column_dimensions["A"].width = 99
    wb.save(path)
    assert contents(load_workbook(path)) != contents(build(data))



def test_write_block_stacks_tables_keeps_widths_and_fills_only_its_cells():
    """The shared table writer, as the project report uses it: a second table under the first keeps the first's
    widths (width None), fills land on the named column's cells only, and the next free row is returned."""
    from openpyxl import Workbook
    ws = Workbook().active
    end = wbk.write_block(ws, 2, [("A", 30), ("B", 12)], [["x", "y"], ["z", "w"]])
    assert end == 5
    end2 = wbk.write_block(ws, end + 1, [("Col", None), ("B", None)], [["p", "q"], ["r", "s"]],
                           fills={"Col": ["FFC7CE", None]})
    assert end2 == 9 and ws.column_dimensions["A"].width == 30 and ws.column_dimensions["B"].width == 12
    assert ws["A7"].fill.fgColor.rgb == "00FFC7CE" or ws["A7"].fill.fgColor.rgb.endswith("FFC7CE")
    assert ws["A8"].fill.fill_type is None and ws["B7"].fill.fill_type is None
    assert ws["A6"].font.bold and ws["A6"].font.color.rgb.endswith(wbk.INK)
    with pytest.raises(ValueError):                             # a fill for a column that isn't there
        wbk.write_block(ws, 20, [("A", None)], [["x"]], fills={"Nope": ["FFC7CE"]})


def test_questions_cite_where_each_question_points(data):
    t = data["Questions"]
    cite = wbk.citer(ITHACA, DOCUMENTS)
    first = {}
    for path, book in rulebooks(ITHACA):
        for r in book["rules"]:
            first[r["id"]] = r["sources"][0]
    for ident, citation in zip(column(t, "Id"), column(t, "Citation")):
        if ident in first:
            assert citation == cite(first[ident])
    assert all(column(t, "Citation"))


def test_a_chart_cell_source_shows_its_cell_and_value(data):
    """A rule citing a chart cell (no quote) shows where the cell is (section · row · district) and its value."""
    t = data["Rules"]
    ctx = Context.for_jurisdiction(ITHACA)
    cells = [(r["id"], s) for _, book in rulebooks(ITHACA) for r in book["rules"] for s in r["sources"] if "cell" in s]
    rows = list(zip(column(t, "Rule id"), column(t, "Citation"), column(t, "City's exact words")))
    for rid, s in cells:
        c = s["cell"]
        assert (rid, f"{ITHACA_TITLES[s['file']]}, p.{s['page']}, {c['section']} · {c['row']} · {c['column']}",
                _cell(s, ctx)["value"]) in rows


def test_an_unverified_chart_cell_says_so_instead_of_a_blank(monkeypatch):
    rule = {"id": "R-1b.x", "title": "X", "sources": [{"file": "zoning_charts_2026-04.pdf", "page": 3,
                                                        "cell": {"section": "Nope", "row": "x", "column": "R-1B"}}]}
    monkeypatch.setattr(wbk, "rulebooks", lambda j: [("R-1b.yaml", {"district": "R-1b", "rules": [rule]})])
    t = tables(ITHACA)["Rules"]
    assert column(t, "City's exact words") == [wbk.NOT_VERIFIED]
    assert "Nope · x · R-1B" in column(t, "Citation")[0]


def test_the_readme_says_how_chart_cells_are_cited():
    readme = (REPO / "packages/rule_export/README.md").read_text(encoding="utf-8")
    assert "section, row and district column" in readme and "(not verified" in readme


def _at(t, header):
    return [h for h, _ in t["columns"]].index(header)


def test_related_sections_come_from_the_term_index(data):
    """A definition lists every section that uses its word; a rule, the requirement sections that use the words
    it quotes (not its own). The yard definition and the rear-yard rule both reach §325-18B, the eaves rule."""
    t = data["Definitions"]
    yard = next(r for r in t["rows"] if r[_at(t, "Id")] == "yard" and r[_at(t, "Related sections")])
    assert "325-18B" in yard[_at(t, "Related sections")].split(", ")
    t = data["Rules"]
    rule = next(r for r in t["rows"] if r[_at(t, "Rule id")] == "R-1b.rear_yard" and r[_at(t, "Related sections")])
    assert "325-18B" in rule[_at(t, "Related sections")].split(", ")
    assert "325-8A" not in rule[_at(t, "Related sections")].split(", ")              # its own section


def test_an_entry_without_sources_still_shows_its_related_sections(monkeypatch):
    rule = {"id": "R-1b.x", "title": "Rear yard", "kind": "rule"}
    monkeypatch.setattr(wbk, "rulebooks", lambda j: [("R-1b.yaml", {"district": "R-1b", "rules": [rule]})])
    t = tables(ITHACA)["Rules"]
    assert "325-18B" in t["rows"][0][_at(t, "Related sections")].split(", ")


def test_open_questions_show_their_research_and_findings_have_a_tab(data):
    q = data["Questions"]
    lot = next(r for r in q["rows"] if r[2] == "lot")
    assert "325-3B:lot" in lot[_at(q, "Searched")] and "survey" in lot[_at(q, "Why still open")]
    assert "tax_map_area" in lot[_at(q, "Readings in play")]
    f = data["Findings"]
    rows = {r[_at(f, "Finding")]: r for r in f["rows"]}
    assert rows["yards_to_nearest_part"][_at(f, "Answer")].startswith("The law: ")
    assert "p.49" in rows["yards_to_nearest_part"][_at(f, "Sources")]
    assert rows["perpendicular_lot_depth"][_at(f, "Answer")].startswith(
        "Gordium's reading (city practice) · confirm with the City zoning office")
    assert len(f["rows"]) == len(f["links"]["Link"])


def test_a_rule_for_each_parts_examples_show_its_parts_and_rows():
    """SYNTHETIC (rule_format/tests/test_parts.py): a per-part example is a small design, so the sheet shows the
    parts and the rows it expects, not just its answer; a zoning example reads exactly as before."""
    ex = {"given": {}, "parts": {"sleeping_room": [{"id": "br1"}, {"id": "br2"}],
                                 "emergency_escape_opening": [{"id": "w1", "within": "br1",
                                                               "measures": {"opening_net_clear_area": 6}}]},
          "rows": [{"part": "w1", "within": "br1", "outcome": "pass"}, {"within": "br2", "outcome": "fail"}],
          "expect": "fail"}
    assert wbk._examples([ex]) == wbk._bullets([
        " · parts: sleeping_room br1; sleeping_room br2; emergency_escape_opening w1 in br1 "
        "(opening_net_clear_area = 6) · rows: pass for w1 in br1; fail in br2 → fail"])
    assert wbk._examples([{"given": {"a": 1}, "expect": "pass"}]) == wbk._bullets(["a = 1 → pass"])


def test_a_part_rules_own_limit_is_its_own_column():
    """Section group 8d: a per-part rule's `limit` (its part's own requirement, apart from whether the law asks it of
    this part) is shown, so a person reading the rules sees the opening's own requirement beside the check."""
    col = next(c for c in wbk.COLUMNS["rule"] if "limit" in c.fields)
    rule = {"id": "x", "limit": "opening_net_clear_area >= 5.7", "check": "(opening_net_clear_area >= 5.7) or y"}
    assert col.value(rule, None, 0, 1) == "opening_net_clear_area >= 5.7"
