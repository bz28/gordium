"""The district coverage audit (district_audit.py): the saved table is current, and no decision can claim more than
the files show. A wrong "covered" would read as a false pass, so each check that refuses a decision is pinned here
with the decision it must refuse."""

import copy
from pathlib import Path

import pytest
import yaml

from document_extraction.sections import piece_keys
from rule_format.rulebook import load
from section_labeling import __main__ as cli
from section_labeling import district_audit as audit

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
SAVED = ITHACA / audit.OUTPUT


@pytest.fixture(scope="module")
def decisions():
    return load(ITHACA / audit.DECISIONS)


@pytest.fixture(scope="module")
def built():
    return audit.Audit(ITHACA)


def problems(data, **kw):
    return audit.Audit(ITHACA, data=data, **kw).problems


def with_piece(decisions, pid, parts):
    data = copy.deepcopy(decisions)
    data["pieces"][pid] = parts
    return data


def test_saved_audit_is_current(capsys):
    """The staleness check CI runs: a rulebook or decision changed without regenerating fails here."""
    assert cli.main(["audit", "--check"]) == 0, capsys.readouterr().out


def test_a_rulebook_change_not_regenerated_differs_from_the_saved_table(tmp_path):
    book = load(ITHACA / "5_zoning_rules/R-1b.yaml")
    book["rules"] = [r for r in book["rules"] if r["id"] != "R-1b.parking_other_uses"]   # cites no piece of Ch. 325
    path = tmp_path / "R-1b.yaml"
    path.write_text(yaml.safe_dump(book, sort_keys=False, allow_unicode=True), encoding="utf-8")
    text, found = audit.build(ITHACA, books={"R-1b": path})
    assert found == [] and text != SAVED.read_text(encoding="utf-8")
    assert "R-1b.parking_other_uses" in SAVED.read_text(encoding="utf-8") and "R-1b.parking_other_uses" not in text


def test_a_rule_removed_from_a_rulebook_stops_every_decision_naming_it(tmp_path):
    book = load(ITHACA / "5_zoning_rules/R-1a.yaml")
    book["rules"] = [r for r in book["rules"] if r["id"] != "R-1a.lot_coverage"]
    path = tmp_path / "R-1a.yaml"
    path.write_text(yaml.safe_dump(book, sort_keys=False, allow_unicode=True), encoding="utf-8")
    text, found = audit.build(ITHACA, books={"R-1a": path})
    assert text is None and any("R-1a.lot_coverage isn't in the rulebook" in p for p in found)


def test_a_new_citation_must_be_named_so_a_stale_missing_cant_stand_beside_it(tmp_path):
    """A rule that starts citing §325-26 (decided MISSING) must be named in §325-26's decisions."""
    page, line = next(iter(piece_keys(audit.Audit(ITHACA).pieces["325-26"])))
    book = load(ITHACA / "5_zoning_rules/R-1b.yaml")
    rule = next(r for r in book["rules"] if r["id"] == "R-1b.front_yard")
    rule["sources"].append({"file": audit.LAW, "page": page, "lines": [line, line], "quote": "x"})
    path = tmp_path / "R-1b.yaml"
    path.write_text(yaml.safe_dump(book, sort_keys=False, allow_unicode=True), encoding="utf-8")
    found = audit.Audit(ITHACA, books={"R-1b": path}).problems
    assert any(p.startswith("325-26 part 1 (R-1b): R-1b.front_yard cited but this part doesn't name it") for p in found)


def test_the_saved_decisions_have_no_problems(built):
    assert built.problems == []


def test_every_rule_and_flag_piece_is_a_row_with_every_district(built):
    labels = load(ITHACA / "3_section_labels/chapter_325_zoning_2026-10.yaml")["labels"]
    wanted = [p for p, e in labels.items() if e["label"] in ("rule", "flag")]
    assert sorted(built.rows) == sorted(wanted) and len(wanted) == 164
    assert built.districts == ["R-1a", "R-1b", "R-2a", "R-2b", "R-2c", "R-3a", "R-3aa", "R-3b", "RU"]
    table = SAVED.read_text(encoding="utf-8").split("## The table")[1].split("## Each piece")[0]
    assert sum(1 for line in table.splitlines() if line.startswith("| §")) == 164


def test_a_piece_without_decisions_is_refused(decisions):
    data = copy.deepcopy(decisions)
    del data["pieces"]["325-26"]
    assert "325-26: no decisions (a list of parts, each with `what`)" in problems(data)


def test_a_district_left_undecided_is_refused(decisions):
    data = with_piece(decisions, "325-19E", [{"what": "x", "R-3a": {"status": "flag", "rules": ["abutting_r1"]}}])
    assert "325-19E part 1: no decision for R-1a" in problems(data)


def test_covered_by_a_rule_that_doesnt_cite_the_piece_needs_a_stated_mapping(decisions):
    """§325-26 (streams) is cited by no rule: calling it covered by the front yard rule is refused unless the
    mapping is said, and then the table says it is a mapping, not a citation."""
    data = with_piece(decisions, "325-26", [{"what": "x", "all": {"status": "rulebook", "rules": ["front_yard"]}}])
    assert any("front_yard don't cite the piece: say why in `mapped`" in p for p in problems(data))


def test_a_mapping_where_every_rule_cites_is_refused(decisions):
    data = with_piece(decisions, "325-19C", [{"what": "x", "all": {"status": "rulebook", "rules": ["front_yard"],
                                                                     "mapped": "because"}}])
    assert any("every rule named cites the piece; drop `mapped`" in p for p in problems(data))


def test_a_rule_that_isnt_in_the_rulebook_is_refused(decisions):
    data = with_piece(decisions, "325-19C", [{"what": "x", "all": {"status": "rulebook",
                                                                     "rules": ["front_yard", "no_such_rule"]}}])
    assert any("R-1b.no_such_rule isn't in the rulebook" in p for p in problems(data))


def test_in_the_rulebook_must_be_a_rule_not_a_flag(decisions):
    data = with_piece(decisions, "325-3B:green_space", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "quote": "Where a minimum green space requirement applies"},
        "RU": {"status": "rulebook", "rules": ["green_space"]}}])
    assert any("RU.green_space is a flag, not a rule" in p for p in problems(data))


def test_a_flag_must_name_something_that_says_needs_review(decisions):
    data = with_piece(decisions, "325-19C", [{"what": "x", "all": {"status": "flag", "rules": ["front_yard"]}}])
    assert any("none of front_yard ever says needs review" in p for p in problems(data))


def test_not_applicable_needs_the_laws_own_words_found_where_it_says(decisions):
    base = {"status": "not_applicable", "why": "w"}
    for quote, extra in (("in any U-1 District", {}), ("in any U-1 District", {"page": 47})):
        ok = with_piece(decisions, "325-16D", [{"what": "x", "all": dict(base, quote=quote, **extra)}])
        assert problems(ok) == []
    for quote, extra in (("in any U-2 District", {}), ("in any U-1 District", {"page": 48}),
                         ("in any U-1 District", {"piece": "325-26"}), ("", {})):
        bad = with_piece(decisions, "325-16D", [{"what": "x", "all": dict(base, quote=quote, **extra)}])
        assert any("quote not found" in p or "give the law's own words" in p for p in problems(bad)), (quote, extra)


def test_a_quote_may_run_across_a_page_break_inside_its_piece(built):
    """§325-21B's scope sentence runs from p.63 onto p.64: found inside the piece, not on either page alone."""
    quote = "shall apply to all business and industrial land uses and multiple dwelling structures"
    assert built._quote_found("325-21B", {"quote": quote})
    assert built._quote_found("325-21A", {"quote": quote, "piece": "325-21B"})
    assert not built._quote_found("325-21A", {"quote": quote})                    # not in §325-21A itself
    assert not any(built._quote_found("325-21B", {"quote": quote, "page": pg}) for pg in (63, 64))
    assert not built._quote_found("325-21A", {"quote": quote, "piece": "325-99Z"})


def test_parked_must_be_on_the_later_list_and_missing_needs_a_priority_and_why(decisions):
    data = with_piece(decisions, "325-26", [{"what": "x", "all": {"status": "parked", "item": "streams"}}])
    assert any("parked item must be one of" in p for p in problems(data))
    data = with_piece(decisions, "325-26", [{"what": "x", "all": {"status": "missing", "why": "w"}}])
    assert any("priority must be one of" in p for p in problems(data))
    data = with_piece(decisions, "325-26", [{"what": "x", "all": {"status": "missing", "priority": "low"}}])
    assert any("say why" in p for p in problems(data))


def test_an_open_question_must_link_a_real_question(decisions):
    good = {"status": "open_question", "why": "w", "link": "docs/questions_for_architects.md#5.11"}
    assert problems(with_piece(decisions, "325-26", [{"what": "x", "all": good}])) == []
    for link in ("docs/nope.md", "docs/questions_for_architects.md#9.99 no such heading"):
        found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": dict(good, link=link)}]))
        assert any("link" in p or "has no" in p for p in found), link


def test_also_must_really_cite_the_piece(decisions):
    data = with_piece(decisions, "325-26", [{"what": "x", "all": {"status": "missing", "priority": "high", "why": "w",
                                                                    "also": ["front_yard"]}}])
    assert any("`also` names R-1a.front_yard, which doesn't cite the piece" in p for p in problems(data))


def test_a_cell_takes_its_worst_part(decisions):
    """§325-18B: eaves are in the rulebook, other projections are missing: the cell is MISSING, never covered."""
    a = audit.Audit(ITHACA)
    statuses = [dec["status"] for _, dec in a.cells["325-18B"]["R-1b"]]
    assert statuses == ["rulebook", "missing"] and a.status("325-18B", "R-1b") == "missing"
    assert a._short("325-18B", "R-1b").startswith("**MISSING** (partly ✓ yard_projections")


def test_the_worst_status_order_puts_missing_first_and_not_applicable_last():
    assert audit.STATUSES == ("missing", "open_question", "parked", "flag", "rulebook", "not_applicable")


def test_already_disclosed_means_the_section_is_on_every_results_not_checked_list():
    assert audit.is_disclosed("325-28C", ["325-28"]) and audit.is_disclosed("325-16A", ["325-16A"])
    assert not audit.is_disclosed("325-28C", ["325-2"]) and not audit.is_disclosed("325-16", ["325-16A"])
    assert "325-18B" in audit.disclosed_sections(ITHACA)


def test_the_missing_list_is_ranked_high_first_then_silent_before_disclosed(built):
    ranked = built.missing()
    order = [list(audit.PRIORITIES).index(m["priority"]) for m in ranked]
    assert order == sorted(order) and ranked[0]["priority"] == "high"
    for p in audit.PRIORITIES:
        same = [m["disclosed"] for m in ranked if m["priority"] == p]
        assert same == sorted(same), p                          # False (silent) before True (disclosed)
    streams = next(m for m in ranked if m["pieces"] == ["325-26"])
    assert streams["priority"] == "high" and streams["districts"] == built.districts


def test_measures_say_where_each_value_comes_from_and_none_when_nothing_fills_it(built):
    model, stated = audit.measure_sources()
    assert {"lot_area", "front_yard", "building_height"} <= model and {"stories", "use", "district"} <= stated
    text = "\n".join(built._rules_section())
    assert "| `R-1b.stories` | rule |" in text and "lot_area (model)" in text
    assert "stories (model or stated)" in text and "stories (stated)" not in text    # floor blocks are counted


def test_tested_on_a_model_comes_from_test_sites():
    tests = audit.model_tests(ITHACA)
    assert any(t.startswith("real model 106_ithaca_rd") for t in tests["R-1b.rear_yard"])
    assert "scenario 12" in tests["R-3a.height"] and "scenario 11" in tests["R-1a.lot_coverage"]
    assert "R-2a.height" not in tests                            # no R-2 model yet: the table says none


def test_the_cli_refuses_to_write_when_a_decision_isnt_backed(monkeypatch, capsys):
    written = []
    monkeypatch.setattr(audit, "build", lambda j: (None, ["a problem"]))
    monkeypatch.setattr(cli, "_write_or_check", lambda *a: written.append(a) or True)
    assert cli.main(["audit"]) == 1
    assert "✗ new_york/ithaca_city: a problem" in capsys.readouterr().out and written == []


# Review round 1 (cold reviewer + 2 sceptics each): every confirmed finding pinned.

def test_rules_or_mapped_on_a_decision_that_isnt_covered_are_refused(decisions):
    """A `rules` list on not_applicable or missing would silence the check that a citing rule is named."""
    data = with_piece(decisions, "325-19C", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "quote": "Corner lot transition", "rules": ["front_yard"]}}])
    found = problems(data)
    assert any("`rules` only goes with rulebook or flag" in p for p in found)
    assert any("R-1a.front_yard cited but this part doesn't name it" in p for p in found)
    data = with_piece(decisions, "325-26", [{"what": "x", "all": {"status": "missing", "priority": "low", "why": "w",
                                                                    "mapped": "m"}}])
    assert any("`mapped` only goes with rulebook or flag" in p for p in problems(data))


def test_a_chart_not_applicable_checks_the_districts_own_cell(decisions):
    """Multiple dwellings are • in R-3a: "not permitted" there is refused; a chart quote without a cell too."""
    base = decisions["_multiple_not_permitted"]
    data = with_piece(decisions, "325-3B:row_house", [{"what": "x", "all": base}])
    found = problems(data)
    assert any(p.startswith("325-3B:row_house part 1 (R-3a): the chart's R-3a cell") and "'•'" in p for p in found)
    assert not any("(R-1a): the chart's" in p for p in found)                  # "-" in R-1a: fine
    no_cell = {k: v for k, v in base.items() if k != "cell"}
    data = with_piece(decisions, "325-3B:row_house", [{"what": "x", "all": no_cell}])
    assert any("a chart quote needs `cell`" in p for p in problems(data))


def test_the_omission_quote_needs_a_use_on_no_residential_list(decisions):
    base = {"status": "not_applicable", "why": "w", "page": 26, "quote": "except where otherwise indicated by "
            "specific prohibition or omission"}
    assert problems(with_piece(decisions, "325-22A", [{"what": "x", "all": dict(base, unlisted_use="motel")}])) == []
    found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": base}]))
    assert any("needs `unlisted_use`" in p for p in found)
    listed = audit.Audit(ITHACA)
    for use in ("two-family", "school", "dormitory"):
        assert any("is a residential use" in p for p in listed._unlisted_problems("R-1a", {"unlisted_use": use}, "w")), use


def test_a_definition_link_on_a_piece_of_several_parts_needs_mapped(decisions):
    """`height` reaches §325-8A only through the lot_depth definition (8A(14)); naming it for Columns 8 and 9
    without saying why is refused."""
    parts = copy.deepcopy(decisions["pieces"]["325-8A"])
    i = next(k for k, part in enumerate(parts) if part["what"].startswith("Columns 8 and 9"))
    parts[i]["all"] = {"status": "rulebook", "rules": ["stories", "height"]}
    found = problems(with_piece(decisions, "325-8A", parts))
    assert any("325-8A part" in p and "height don't cite the piece" in p for p in found)


def test_loading_for_nonresidential_uses_is_missing_in_every_district(built):
    """Chart p.14's "Allowed by variance" row has no rule or flag in any district (each rulebook header says so)."""
    i = next(k for k, w in enumerate(built._parts("325-8A")) if w.startswith("Column 5"))
    assert {d: built.cells["325-8A"][d][i][1]["status"] for d in built.districts} == {d: "missing" for d in built.districts}


def test_compliance_with_district_regulations_is_not_counted_as_covered(built, decisions):
    assert {built.status("325-7A", d) for d in built.districts} == {"not_applicable"}
    data = with_piece(decisions, "325-7A", [{"what": "x", "all": {"status": "rulebook", "rules": ["*"], "mapped": "m"}}])
    assert any("name the rules" in p for p in problems(data))           # "*" matches no rule


def test_a_flagged_part_is_never_shown_with_a_check_mark(built):
    """§325-8B in R-3a: abutting_r1 and lot_size_zero_lot_line are flags, the use part a flag too."""
    short = built._short("325-8B", "RU")
    assert "partly flagged: primary_structures" in short and "✓ primary_structures" not in short


def test_the_table_is_the_same_whatever_python_hashes_sets_with():
    """Definitions cite pieces as a set: iterated sorted, so two runs (different hash seeds) write the same table."""
    import os
    import subprocess
    import sys
    code = ("import hashlib; from section_labeling import district_audit as a; from pathlib import Path; "
            f"print(hashlib.sha256(a.build(Path({str(ITHACA)!r}))[0].encode()).hexdigest())")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(str(p) for p in sorted((REPO / "packages").iterdir())))
    runs = {subprocess.run([sys.executable, "-c", code], env=dict(env, PYTHONHASHSEED=seed), capture_output=True,
                           text=True, encoding="utf-8", check=True).stdout for seed in ("1", "2", "3")}
    assert len(runs) == 1


# Review round 2: citations are matched part by part (each part of a piece gives its lines).

def part_index(built, pid, prefix):
    return next(k for k, w in enumerate(built._parts(pid)) if w.startswith(prefix))


def test_a_rule_citing_a_part_must_be_named_on_that_part(decisions, built):
    """R-3aa.stories cites §325-8A(15) (Column 16) and is named under Columns 8 and 9: Column 16 can't say N/A."""
    parts = copy.deepcopy(decisions["pieces"]["325-8A"])
    i = part_index(built, "325-8A", "Column 16")
    parts[i] = {k: v for k, v in parts[i].items() if k != "R-3aa"}
    found = problems(with_piece(decisions, "325-8A", parts))
    assert any(p.startswith(f"325-8A part {i + 1} (R-3aa): R-3aa.stories cited but this part doesn't name it")
               for p in found)
    assert {built.cells["325-8A"][d][i][1]["status"] for d in ["R-3aa"]} == {"rulebook"}


def test_a_rule_counts_as_citing_a_part_only_through_that_parts_lines(decisions, built):
    """use cites §325-8B only on p.26 line 20, part (3): naming it on part (4) without `mapped` is refused."""
    parts = copy.deepcopy(decisions["pieces"]["325-8B"])
    i = part_index(built, "325-8B", "(4)")
    parts[i]["all"] = {"status": "flag", "rules": ["use"]}
    found = problems(with_piece(decisions, "325-8B", parts))
    assert any(p.startswith(f"325-8B part {i + 1} (R-1a): use don't cite the piece") for p in found)


def test_a_piece_of_several_parts_needs_lines_on_each_covering_the_whole_piece(decisions):
    parts = copy.deepcopy(decisions["pieces"]["325-18B"])
    del parts[1]["lines"]
    assert any("325-18B part 2: a piece of several parts gives each part its `lines`" in p
               for p in problems(with_piece(decisions, "325-18B", parts)))
    parts = copy.deepcopy(decisions["pieces"]["325-18B"])
    parts[0]["lines"] = parts[1]["lines"] = [[49, 13, 15]]
    assert any("325-18B: lines in no part: [(49, 16)]" in p for p in problems(with_piece(decisions, "325-18B", parts)))
    parts[0]["lines"] = [[49, 13, 17]]
    assert any("lines outside the piece" in p for p in problems(with_piece(decisions, "325-18B", parts)))


def test_any_quote_from_the_omission_sentence_needs_an_unlisted_use(decisions):
    for quote in ("by specific prohibition or omission", "Regulations, standards and permitted uses are generally cumulative"):
        found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": {
            "status": "not_applicable", "why": "w", "page": 26, "quote": quote}}]))
        assert any("needs `unlisted_use`" in p for p in found), quote


def test_loading_for_a_use_allowed_by_variance_is_missing_everywhere_and_agrees_with_column_5(built):
    col5 = part_index(built, "325-8A", "Column 5")
    for pid in ("325-21A", "325-21B"):
        i = part_index(built, pid, "Loading for a nonresidential use allowed by variance")
        for d in built.districts:
            assert built.cells[pid][d][i][1]["status"] == built.cells["325-8A"][d][col5][1]["status"] == "missing"
            assert built.status(pid, d) == "missing", (pid, d)


def test_an_attached_buildings_party_walls_and_doors_are_not_claimed_covered(built):
    i = part_index(built, "325-3B:one_family_attached_dwelling", "Each dwelling shares")
    assert built.cells["325-3B:one_family_attached_dwelling"]["R-2c"][i][1]["status"] == "missing"
    assert built.status("325-3B:one_family_attached_dwelling", "R-2c") == "missing"


# Review round 3.

def test_the_two_family_definition_is_covered_wherever_two_family_houses_are_permitted(built):
    """Chart p.2: two-family is • from R-2a to RU, so the definition's own sentence is never 'not applicable' there."""
    pid = "325-3B:dwelling_two_family"
    i = part_index(built, pid, "What a two-family dwelling is")
    for d in built.districts:
        status = built.cells[pid][d][i][1]["status"]
        assert status == ("not_applicable" if d in ("R-1a", "R-1b") else "rulebook"), d


def test_the_omission_sentence_placed_by_piece_also_needs_an_unlisted_use(decisions):
    found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "piece": "325-8B", "quote": audit.OMISSION}}]))
    assert any("needs `unlisted_use`" in p for p in found)


@pytest.mark.parametrize("use", ["home occupation", "neighborhood garden", "accessory dwelling unit", "private garage",
                                 "rooming house", "boarding house", "row house", "cooperative household",
                                 "day care center"])
def test_a_use_the_chart_or_the_multiple_dwelling_list_names_is_never_unlisted(built, use):
    assert built._unlisted_problems("R-1a", {"unlisted_use": use}, "w")


def test_the_unlisted_uses_the_decisions_rely_on_are_on_no_list(built):
    for use in ("motel", "junkyard", "travel trailer", "gasoline service station", "large beverage producer"):
        assert built._unlisted_problems("R-3a", {"unlisted_use": use}, "w") == [], use


def test_a_cell_covered_only_by_a_mapping_says_so(built):
    """§325-17A: no rule cites it; the yard rules cover it by Gordium's mapping, shown in the cell and summary."""
    assert built._short("325-17A", "R-1b").endswith("(mapped)")
    assert not built._short("325-19C", "R-1b").endswith("(mapped)")                  # front_yard cites it
    assert "§325-17A (mapped)" in SAVED.read_text(encoding="utf-8").split("## The table")[0]


# Review round 4.

@pytest.mark.parametrize("pid", ["325-26", "325-3B:home_occupation"])
def test_the_unlisted_use_must_be_what_the_piece_is_about(decisions, pid):
    """A motel is unlisted, but §325-26 (streams) and home occupations aren't about motels."""
    found = problems(with_piece(decisions, pid, [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "page": 26, "quote": audit.OMISSION, "unlisted_use": "motel"}}]))
    assert any("isn't what this piece is about" in p for p in found)


def test_motels_in_every_part_of_section_22_are_what_their_pieces_are_about(built):
    """§325-22B to H don't say 'motel' themselves; §325-22A, in the same section, does."""
    assert all("motel" in built._piece_words(f"325-22{x}") for x in "ABCDEFGH")


def test_a_listed_use_with_a_word_added_is_still_listed(built):
    assert built._unlisted_problems("R-1a", {"unlisted_use": "home occupation business"}, "w")
    assert built._unlisted_problems("R-1a", {"unlisted_use": "rooming house annex"}, "w")


def test_the_column_2_sentence_is_the_same_argument_and_needs_an_unlisted_use(decisions):
    found = problems(with_piece(decisions, "325-3B:home_occupation", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "page": 24,
        "quote": "Uses which are permitted in each use district are listed"}}]))
    assert any("needs `unlisted_use`" in p for p in found)


def test_mapped_is_shown_on_the_kind_of_part_that_is_mapped(built):
    """§325-8B in R-1a: use cites part (3) (✓, no label) and is only mapped onto part (4) (flagged, mapped)."""
    assert "partly ✓ use;" in built._short("325-8B", "R-1a")
    assert "partly flagged: use (mapped)" in built._short("325-8B", "R-1a")


def test_a_district_decided_twice_through_an_alias_is_refused(decisions):
    x = {"status": "missing", "priority": "low", "why": "w"}
    y = {"status": "missing", "priority": "high", "why": "w2"}
    found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": x, "R-1a": x, "R-1a, R-1b": y}]))
    assert "325-26 part 1: R-1a decided twice" in found


# Review round 5.

def test_a_sibling_subsections_words_dont_make_a_use_this_pieces(decisions):
    """§325-15C (unsanitary storage) never mentions a junkyard; §325-15E does."""
    found = problems(with_piece(decisions, "325-15C", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "page": 26, "quote": audit.OMISSION, "unlisted_use": "junkyard"}}]))
    assert any("isn't what this piece is about" in p for p in found)


def test_a_chart_row_must_be_about_the_piece(decisions):
    """The multiple-dwelling row says nothing about streams (§325-26)."""
    data = with_piece(decisions, "325-26", [{"what": "x", "all": {"status": "missing", "priority": "high", "why": "w"},
                                             "R-1a, R-1b": decisions["_multiple_not_permitted"]}])
    assert any("doesn't name 'New structures along streams" in p for p in problems(data))
    other = dict(decisions["_multiple_not_permitted"], quote="RESIDENTIAL DISTRICTS USE LIST")
    other.pop("via_piece")
    data = with_piece(decisions, "325-26", [{"what": "x", "all": {"status": "missing", "priority": "high", "why": "w"},
                                             "R-1a": other}])
    assert any("isn't about this piece" in p for p in problems(data))


def test_a_via_piece_must_name_this_piece(decisions):
    """DWELLING, MULTIPLE lists the rooming house but not the rooming unit."""
    data = with_piece(decisions, "325-3B:rooming_unit", [{"what": "x", "all": decisions["_multiple_not_permitted"]}])
    assert any("doesn't name 'ROOMING UNIT'" in p for p in problems(data))


def test_page_furniture_is_not_the_law(decisions):
    found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "page": 2, "quote": "City of Ithaca"}}]))
    assert any("from another section of the law (front_matter)" in p for p in found)    # p.2's text, not this piece
    found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "page": 67, "quote": "City of Ithaca, NY"}}]))
    assert any("only page furniture" in p for p in found)                                # p.67's running header


def test_rooming_units_and_bed_and_breakfasts_in_r1_r2_are_not_claimed_settled(built):
    for d in ("R-1a", "R-1b", "R-2a", "R-2b", "R-2c"):
        assert {dec["status"] for _, dec in built.cells["325-3B:rooming_unit"][d]} == {"missing"}
        assert built.cells["325-10C"][d][part_index(built, "325-10C", "Bed-and-breakfast")][1]["status"] == "missing"
        assert built.cells["325-9B"][d][part_index(built, "325-9B", "(p) Bed-and-breakfast")][1]["status"] == "missing"
