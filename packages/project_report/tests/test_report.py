"""The 106 Ithaca Rd report against the architects' own spreadsheet, and each safeguard of the report."""

from pathlib import Path

import openpyxl
import pytest
import yaml

from project_report import report
from project_report.report import OUTPUT_EXTRA, OUTPUT_HEADERS, build, load_project, output_path, tables
from rule_export.workbook import contents, page_link
from rule_format.rulebook import REPO, Context, load, outcome, rulebook_for

SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/spreadsheet_design.yaml"
J = REPO / "regulations/jurisdictions/new_york/ithaca_city"
COL = {h: i for i, h in enumerate(OUTPUT_HEADERS + OUTPUT_EXTRA)}


@pytest.fixture(scope="module")
def t():
    return tables(SITE)


@pytest.fixture(scope="module")
def theirs():
    return openpyxl.load_workbook(REPO / load(SITE)["spreadsheet"], data_only=True)


def rows_by_id(t):
    return {r[COL["Rule id"]]: r for r in t["output"] + t["not_applicable"]}


def write_project(tmp_path, **changes):
    project = load(SITE)
    project.update(changes)
    path = tmp_path / "p.yaml"
    path.write_text(yaml.safe_dump(project, sort_keys=False))
    return path


def test_same_pass_fail_as_the_architects_on_all_11_rows(t, theirs):
    design, ours = load(SITE), rows_by_id(t)
    checked = 0
    for row in theirs["Output"].iter_rows(min_row=3):
        if row[0].value:
            rule = design["compare"][row[0].value]
            assert ours[rule][COL["Error"]] == row[6].value, f"{row[0].value}: they say {row[6].value}"
            checked += 1
    assert checked == 11


def test_tab_names_and_headers_are_theirs_with_ours_after(t, theirs):
    wb = build(t)
    assert wb.sheetnames == theirs.sheetnames == ["Inputs", "Output"]
    header = [c.value for c in wb["Output"][2]]
    assert header[:7] == [c.value for c in theirs["Output"][2]][:7]
    assert header[7:] == OUTPUT_EXTRA
    assert [c.value for c in wb["Inputs"][2]][:3] == [c.value for c in theirs["Inputs"][2]][:3]
    ws = wb["Inputs"]
    at = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "Table parameters")
    assert [c.value for c in ws[at]][:3] == [c.value for c in theirs["Inputs"][19]][:3]


def test_every_result_comes_from_outcome(t):
    ctx = Context.for_jurisdiction(J)
    values = {k: m["value"] for k, m in load(SITE)["measurements"].items()}
    rules = load(rulebook_for(J, "R-1b"))["rules"]
    ours = rows_by_id(t)
    assert set(ours) == {r["id"] for r in rules}                        # every rule, none dropped
    for r in rules:
        assert ours[r["id"]][COL["Error"]] == report.RESULT[outcome(r, values, {"use": ctx.uses})]


def test_every_row_cites_its_rules_first_source(t):
    documents = {d["file"]: d for d in load(J / "1_source_documents/sources.yaml")["documents"]}
    rules = {r["id"]: r for r in load(rulebook_for(J, "R-1b"))["rules"]}
    for rows, links in ((t["output"], t["output_links"]), (t["not_applicable"], t["not_applicable_links"])):
        for row, link in zip(rows, links, strict=True):
            s = rules[row[COL["Rule id"]]]["sources"][0]
            assert row[COL["PDF page"]] == s["page"]
            assert row[COL["Document"]] == s["file"]
            assert row[COL["City's exact words"]] == " ".join(s["quote"].split())
            assert link == page_link(J, documents, s["file"], s["page"])


def test_rear_yard_limit_is_worked_out_for_this_lot(t):
    row = rows_by_id(t)["R-1b.rear_yard"]
    assert (row[COL["Table limit"]], row[COL["Proposed"]], row[COL["Units"]], row[COL["Error"]]) == \
        ("≥ 22.5", 25, "ft", "PASS")
    assert row[COL["Formula"]] == "rear_yard >= max(min(0.25 * lot_depth, 50), 20)"


def test_says_which_rulebook_it_used(t):
    assert all(r[COL["Rulebook"]].startswith("R-1b.yaml (") for r in t["output"])


def test_hand_drafted_rulebook_is_preferred(tmp_path):
    rules = tmp_path / "5_zoning_rules"
    (rules / "drafted").mkdir(parents=True)
    (rules / "drafted/X.yaml").write_text("rules: []")
    assert rulebook_for(tmp_path, "X") == rules / "drafted/X.yaml"
    (rules / "X.yaml").write_text("rules: []")
    assert rulebook_for(tmp_path, "X") == rules / "X.yaml"
    assert rulebook_for(tmp_path, "Y") is None


def test_a_missing_measurement_needs_review_with_a_reason(tmp_path):
    measurements = load(SITE)["measurements"]
    del measurements["rear_yard"]
    rows = rows_by_id(tables(write_project(tmp_path, measurements=measurements)))
    for rid in ("R-1b.rear_yard", "R-1b.height"):
        assert rows[rid][COL["Error"]] == "NEEDS REVIEW"
        assert "rear_yard" in rows[rid][COL["Why it needs review"]]


def test_every_needs_review_row_has_a_reason(tmp_path):
    measurements = load(SITE)["measurements"]
    measurements["use"]["value"] = "not_a_city_use"         # whether rules apply can't be decided
    measurements["lot_width"]["value"] = -5                 # an unusable number
    t = tables(write_project(tmp_path, measurements=measurements))
    review = [r for r in t["output"] if r[COL["Error"]] == "NEEDS REVIEW"]
    assert len(review) >= 3
    assert all(r[COL["Why it needs review"]] for r in review)
    assert all(not r[COL["Why it needs review"]] for r in t["output"] if r[COL["Error"]] != "NEEDS REVIEW")


def test_the_reason_follows_the_checkers_order_and_names_the_value(tmp_path):
    measurements = load(SITE)["measurements"]
    del measurements["use"]                                  # every rule's applicability is now unknown
    measurements["stories"]["value"] = "3"                   # text, not a number
    rows = rows_by_id(tables(write_project(tmp_path, measurements=measurements)))
    # A flag whose applicability can't be decided says so, not "a person decides".
    assert rows["R-1b.parking_other_uses"][COL["Why it needs review"]] == \
        "Can't tell whether this rule applies: missing measurement: use."
    assert rows["R-1b.stories"][COL["Why it needs review"]] == "Can't check: unusable value: stories = '3'."
    assert rows["R-1b.stories"][COL["Proposed"]] == "'3'"   # shown as text, never as a usable number


def test_table_parameters_keep_the_formulas_brackets(t):
    params = {row[3]: row[1] for row in t["parameters"]}
    assert params["R-1b.parking_one_family"] == \
        "parking_spaces ≥ (1 if sleeping_rooms ≤ 3 else 2 + max(sleeping_rooms - 5, 0))"
    assert params["R-1b.rear_yard"] == "rear_yard ≥ max(min(0.25 * lot_depth, 50), 20)"


def test_the_reason_blames_only_what_the_checker_read():
    kinds = report.MEASURE_KINDS
    values = {"sleeping_rooms": 2, "lot_area": 5000, "parking_spaces": 1}       # lot_width not given
    branch = "(1000 if sleeping_rooms <= 3 else lot_width)"                    # lot_width: branch not taken
    rule = {"id": "x", "kind": "rule", "check": "parking_spaces >= 1",
            "review_when": [{"when": f"lot_area > {branch}", "reason": "big lot"}]}
    assert outcome(rule, values, {}) == "needs_review"
    assert report.needs_review_reason(rule, values, kinds) == "big lot"
    rule = {"id": "y", "kind": "flag", "applies_when": f"lot_area > {branch}"}
    assert outcome(rule, values, {}) == "needs_review"
    assert report.needs_review_reason(rule, values, kinds) == "A judgment call: a person decides (this rule is a flag)."


def test_the_reason_names_every_measure_the_checker_needs():
    kinds = report.MEASURE_KINDS
    rule = {"id": "x", "kind": "rule", "check": "side_yard_smaller >= 10 and side_yard_larger >= 10"}
    assert report.needs_review_reason(rule, {}, kinds) == \
        "Can't check: missing measurement: side_yard_smaller, side_yard_larger."
    rule = {"id": "x", "kind": "rule", "check": "rear_yard >= max(min(0.25 * lot_depth, 50), 20)"}
    assert report.needs_review_reason(rule, {"rear_yard": -1}, kinds) == \
        "Can't check: missing measurement: lot_depth; unusable value: rear_yard = -1."
    # An if-else whose test can't be worked out blames only the test, never either branch.
    rule = {"id": "x", "kind": "rule", "check": "parking_spaces >= (1 if sleeping_rooms <= 3 else lot_width)"}
    assert report.needs_review_reason(rule, {"parking_spaces": 1}, kinds) == \
        "Can't check: missing measurement: sleeping_rooms."
    # A test that isn't true/false: the checker reads neither branch, so neither is blamed.
    rule = {"id": "x", "kind": "rule", "check": "parking_spaces >= (1 if lot_width else sleeping_rooms)"}
    assert report.needs_review_reason(rule, {"lot_width": 50}, kinds) == \
        "Can't check: missing measurement: parking_spaces."


def test_every_shown_limit_uses_one_symbol_style():
    assert report.table_values("lot_area / 2 >= 100") == "lot_area / 2 ≥ 100"


def test_check_fails_when_a_report_is_missing(tmp_path, monkeypatch, capsys):
    from project_report import __main__ as cli
    project = write_project(tmp_path)
    monkeypatch.setattr(cli, "projects", lambda: [project])
    assert cli.main(["--check"]) == 1
    assert "missing" in capsys.readouterr().out
    assert cli.main([str(project)]) == 0 and cli.main(["--check"]) == 0


def test_rules_that_dont_apply_are_listed_not_dropped(t):
    assert {r[COL["Rule id"]] for r in t["not_applicable"]} == {
        "R-1b.lot_area_other_use", "R-1b.lot_width_other_use", "R-1b.parking_other_uses"}
    assert all(r[COL["Error"]] == "NOT APPLICABLE" for r in t["not_applicable"])
    assert all(r[COL["Error"]] != "NOT APPLICABLE" for r in t["output"])


@pytest.mark.parametrize("change, message", [
    ({"zone": "R-9z"}, "no rulebook"),
    ({"zoen": "R-1b"}, "unknown field"),
    ({"measurements": {"rear_yrd": {"value": 1, "from": "x"}}}, "isn't in measures.yaml"),
    ({"measurements": {"rear_yard": {"value": 1}}}, "where it comes from"),
    ({"measurements": {"rear_yard": {"value": 1, "from": None}}}, "where it comes from"),
    ({"measurements": {"rear_yard": {"value": 1, "from": "  "}}}, "where it comes from"),
    ({"measurements": {"rear_yard": {"value": [1], "from": "x"}}}, "number or text"),
    ({"measurements": {"rear_yard": {"value": True, "from": "x"}}}, "number or text"),
    ({"measurements": {"rear_yard": {"value": float("nan"), "from": "x"}}}, "number or text"),
    ({"measurements": {"rear_yard": {"value": float("inf"), "from": "x"}}}, "number or text"),
])
def test_a_bad_project_file_is_refused(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        load_project(write_project(tmp_path, **change))


def test_text_is_never_run_as_a_formula(tmp_path):
    measurements = load(SITE)["measurements"]
    measurements["lot_area"]["from"] = '=HYPERLINK("http://x")'
    wb = build(tables(write_project(tmp_path, measurements=measurements)))
    cell = next(c for row in wb["Inputs"].iter_rows() for c in row if c.value == '=HYPERLINK("http://x")')
    assert cell.data_type == "s"


def test_output_is_deterministic():
    assert contents(build(tables(SITE))) == contents(build(tables(SITE)))


def test_committed_example_matches_a_fresh_build():
    assert contents(openpyxl.load_workbook(output_path(SITE))) == contents(build(tables(SITE)))



@pytest.mark.parametrize("text, match", [("- title: x\n", "must be a mapping of fields"),
                                         ("title: x\njurisdiction: x\nzone: R-1b\nmeasurements:\n- lot_width\n",
                                          "measurements must be a mapping"),
                                         ("title: x\njurisdiction:\nzone: R-1b\nmeasurements: {}\n", "'jurisdiction' must be text"),
                                         ("title: x\njurisdiction: 5\nzone: R-1b\nmeasurements: {}\n", "'jurisdiction' must be text"),
                                         ("title: x\njurisdiction: a\nzone: 7\nmeasurements: {}\n", "'zone' must be text"),
                                         ("title: [x\n", "can't read the project file")])
def test_a_project_file_of_the_wrong_shape_gets_a_plain_message(tmp_path, text, match):
    from project_report.report import load_project
    path = tmp_path / "project.yaml"
    path.write_text(text)
    with pytest.raises(ValueError, match=match):
        load_project(path)



def test_a_folder_that_is_not_a_jurisdiction_gets_a_plain_message(tmp_path):
    from project_report.report import load_project
    j = tmp_path / "j"
    (j / "5_zoning_rules").mkdir(parents=True)
    (j / "5_zoning_rules/R-1b.yaml").write_text("district: R-1b\nrules: []\n")
    path = tmp_path / "project.yaml"
    path.write_text(f"title: x\njurisdiction: {j}\nzone: R-1b\nmeasurements: {{}}\n")
    with pytest.raises(ValueError, match="isn't a jurisdiction folder"):
        load_project(path)



def test_a_rulebook_that_fails_the_rule_checks_gives_no_report(monkeypatch):
    """A rule whose quote isn't the city's words (edited locally, never checked) must never give PASS."""
    def change(path, data):
        if path.parent.name == "5_zoning_rules":
            data["rules"][0]["sources"][0]["quote"] = "made up words not in the law"
        return data
    report = _patched_load(monkeypatch, change)
    with pytest.raises(ValueError, match="doesn't pass the rule checks"):
        report.tables(SITE)


def _patched_load(monkeypatch, change):
    """report.load and the rule checker's load, with `change(path, data)` applied to what they read."""
    import project_report.report as report
    import rule_format.rulebook as rulebook
    real = rulebook.load
    def load(path):
        return change(Path(path), real(path))
    monkeypatch.setattr(rulebook, "load", load)
    monkeypatch.setattr(report, "load", load)
    return report


def test_a_rulebook_whose_district_isnt_its_file_name_gives_no_report(monkeypatch):
    def change(path, data):
        if path.parent.name == "5_zoning_rules":
            data["district"] = "R-2"
            for rule in data["rules"]:
                rule["id"] = "R-2." + rule["id"].split(".", 1)[1]
        return data
    report = _patched_load(monkeypatch, change)
    with pytest.raises(ValueError, match="doesn't match the file name"):
        report.tables(SITE)


def test_a_uses_list_that_fails_its_checks_gives_no_report(monkeypatch):
    def change(path, data):
        if path.name == "uses.yaml":
            for entry in data.values():
                entry["sources"] = []
        return data
    report = _patched_load(monkeypatch, change)
    with pytest.raises(ValueError, match="needs at least one source"):
        report.tables(SITE)


def test_a_rulebook_that_isnt_valid_yaml_gives_a_plain_refusal(monkeypatch):
    def change(path, data):
        if path.parent.name == "5_zoning_rules":
            raise yaml.YAMLError("bad")
        return data
    report = _patched_load(monkeypatch, change)
    with pytest.raises(ValueError, match="can't read file"):
        report.tables(SITE)
