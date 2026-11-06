"""The district coverage audit (district_audit.py): the saved table is current, and no decision can claim more than
the files show. A wrong "covered" would read as a false pass, so each check that refuses a decision is pinned here
with the decision it must refuse."""

import copy
import re
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


def test_the_key_names_every_test_that_earns_a_scenario_credit():
    """A deep-run lot (deep_run/, checked by test_sites.py) earns "scenario r1" etc. as the hand-worked scenarios do
    (scenarios/, test_scenarios.py); the key must say where each kind is checked, so a reader can find the test."""
    text = SAVED.read_text(encoding="utf-8")
    assert "scenario r1" in text
    assert "design_checker/tests/test_sites.py for the real lots in test_data/test_sites/…/deep_run" in text
    assert "design_checker/tests/test_scenarios.py for test_data/test_sites/…/scenarios" in text


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
    rule["sources"].append({"file": audit.Audit(ITHACA).law, "page": page, "lines": [line, line], "quote": "x"})
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
    assert problems(with_piece(decisions, "325-25D", [{"what": "x", "all": good}])) == []
    for link in ("docs/nope.md", "docs/questions_for_architects.md#9.99 no such heading"):
        found = problems(with_piece(decisions, "325-25D", [{"what": "x", "all": dict(good, link=link)}]))
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
    assert order == sorted(order) and ranked[0]["priority"] == min({m["priority"] for m in ranked},
                                                                    key=list(audit.PRIORITIES).index)
    for p in audit.PRIORITIES:
        same = [m["disclosed"] for m in ranked if m["priority"] == p]
        assert same == sorted(same), p                          # False (silent) before True (disclosed)
    garage = next(m for m in ranked if m["pieces"] == ["325-25D"])
    assert garage["priority"] == "low" and garage["districts"] == built.districts


def test_the_rules_added_after_the_audit_close_its_high_gaps(built):
    """§325-26 (streams, #44) and §325-8B(1) (each primary building's lot area, #42) were the high-priority gaps;
    the stream rule now checks §325-26 in every district, and no high-priority gap is left."""
    assert {built.status("325-26", d) for d in built.districts} == {"rulebook"}
    i = part_index(built, "325-8B", "(1)")
    assert {built.cells["325-8B"][d][i][1]["status"] for d in built.districts} == {"rulebook"}
    assert not [m for m in built.missing() if m["priority"] == "high"]


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
    """§325-9B in R-1a: home_occupation is a flag, so it is shown as flagged, never with a check mark."""
    short = built._short("325-9B", "R-1a")
    assert "partly flagged: use, home_occupation" in short and "✓" not in short


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


def test_a_cell_covered_only_by_a_mapping_says_so(built):
    """§325-17A: no rule cites it; the yard rules cover it by Gordium's mapping, shown in the cell and summary."""
    assert "(mapped)" in built._short("325-17A", "R-1b")
    assert "(mapped)" not in built._short("325-19C", "R-1b")                         # front_yard cites it
    assert "§325-17A (mapped)" in SAVED.read_text(encoding="utf-8").split("## The table")[0]


# Review round 4.


def test_mapped_is_shown_on_the_kind_of_part_that_is_mapped(built):
    """§325-8B in R-1a: use cites part (3) (✓, no label) and is only mapped onto part (4) (flagged, mapped)."""
    assert re.search(r"partly ✓ [^;]*\buse\b[^;]*;", built._short("325-8B", "R-1a"))
    assert "partly flagged: use (mapped)" in built._short("325-8B", "R-1a")


def test_a_district_decided_twice_through_an_alias_is_refused(decisions):
    x = {"status": "missing", "priority": "low", "why": "w"}
    y = {"status": "missing", "priority": "high", "why": "w2"}
    found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": x, "R-1a": x, "R-1a, R-1b": y}]))
    assert "325-26 part 1: R-1a decided twice" in found


# Review round 5.


def test_rooming_units_in_r1_r2_are_not_claimed_settled(built):
    for d in ("R-1a", "R-1b", "R-2a", "R-2b", "R-2c"):
        assert {dec["status"] for _, dec in built.cells["325-3B:rooming_unit"][d]} == {"missing"}


def test_bed_and_breakfasts_in_r1_r2_are_the_use_rules_special_permit(built):
    """The chart marks a bed-and-breakfast inn "-" in R-1 and R-2, but §325-9B(1)(p) lists it "in all districts"
    among the special-permit uses (2026-10-29: it was a fail, listed as missing). The law doesn't settle which
    governs (review round 1: §325-9B(1)'s list describes the chart, which cites the permit conditions beside its
    "-"), so the use rule says needs review, saying it may be prohibited, and records the open question with its
    research; the coverage table says so."""
    from rule_format.rulebook import REPO, load, outcome
    for d in ("R-1a", "R-1b", "R-2a", "R-2b", "R-2c"):
        for piece, words in (("325-10C", "Bed-and-breakfast"), ("325-9B", "(p) Bed-and-breakfast")):
            dec = built.cells[piece][d][part_index(built, piece, words)][1]
            assert dec["status"] == "flag" and dec["rules"] == ["use"], (d, piece, dec)
        rules = load(REPO / f"regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/{d}.yaml")["rules"]
        use = next(r for r in rules if r["id"] == f"{d}.use")
        allowed = {"use": {"bed_and_breakfast_inn", "dormitory"}}
        assert outcome(use, {"use": "bed_and_breakfast_inn"}, allowed) == "needs_review", d
        assert outcome(use, {"use": "dormitory"}, allowed) == "fail", d          # a "-" use still fails
        reason = next(w["reason"] for w in use["review_when"] if "bed_and_breakfast_inn" in w["when"])
        assert "may be prohibited" in reason and "open question" in reason, d
        assert not any(f["id"] == "bed_and_breakfast_by_special_permit" for f in use["findings"])   # not a reading
        assert [q for q in use["open_questions"] if "bed-and-breakfast" in q], d
        research = next(x for x in use["research"] if "bed-and-breakfast" in x["question"])
        assert {"325-9B", "325-8A", "325-10C"} <= set(research["searched"]) and "web search 2026-10-29" in \
            research["why_open"], d



# Review round 7.


def test_mapped_shows_when_any_named_rule_is_mapped(built):
    """§325-18A: the yard rules cite it; lot coverage is mapped."""
    assert built.mapped_only("325-18A", "R-1b") and "(mapped)" in built._short("325-18A", "R-1b")


def test_not_applicable_says_it_includes_pointers(built):
    """§325-7A and §325-8B(7)/(8)/(10) apply everywhere but add nothing of their own: the legend says so."""
    head = built.render().split("## The table")[0]
    assert "or it is a pointer with no requirement of its own" in head and "or are pointers" in head






# The provenance design (coordinator, after round 8): a decision resting on a reading (not applicable, parked, flag)
# quotes the law; code checks only that the quote is the law's words, exactly where it says; the table shows each
# quote beside its cell, and the summary counts the cells that rest on a reading.

@pytest.mark.parametrize("decision", [
    {"status": "not_applicable", "why": "w"},
    {"status": "parked", "item": "parking"},
    {"status": "flag", "rules": ["front_yard"], "mapped": "m"}])
def test_a_reading_must_quote_the_law(decisions, decision):
    found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": decision}]))
    assert any("gives the law's own words (`quote`)" in p for p in found)


def test_the_quote_must_be_the_laws_words_exactly_where_it_says(decisions):
    base = {"status": "not_applicable", "why": "w"}
    for extra in ({"quote": "across a common lot line by mutual agreement"},
                  {"quote": "in any U-1 District", "page": 47}, {"quote": "in any U-1 District", "piece": "325-16D"}):
        assert problems(with_piece(decisions, "325-25D", [{"what": "x", "all": dict(base, **extra)}])) == [], extra
    for extra in ({"quote": "across a common lot line by written agreement"},
                  {"quote": "in any U-1 District", "page": 48}, {"quote": "in any U-1 District", "piece": "325-26"},
                  {"quote": "in any U-1 District", "piece": "325-99Z"}):
        found = problems(with_piece(decisions, "325-25D", [{"what": "x", "all": dict(base, **extra)}]))
        assert any("quote not found at" in p for p in found), extra


def test_page_furniture_and_other_files_are_not_the_law(decisions):
    found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "page": 67, "quote": "City of Ithaca, NY"}}]))
    assert any("only page furniture" in p for p in found)
    found = problems(with_piece(decisions, "325-26", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "file": "ordinance_no_2025-12_southside_form_districts.pdf",
        "page": 1, "quote": "ORDINANCE"}}]))
    assert any("quote Chapter 325 or its chart, not ordinance_no_2025-12" in p for p in found)


def test_a_chart_quote_names_its_cell_and_the_cell_must_say_so_for_the_district(decisions):
    base = decisions["_multiple_not_permitted"]
    found = problems(with_piece(decisions, "325-3B:row_house", [{"what": "x", "all": base}]))
    assert any(p.startswith("325-3B:row_house part 1 (R-3a): the chart's R-3a cell") and "'•'" in p for p in found)
    assert not any("(R-1a): the chart's" in p for p in found)
    no_cell = {k: v for k, v in base.items() if k != "cell"}
    assert any("names its `cell`" in p for p in problems(with_piece(decisions, "325-3B:row_house",
                                                                     [{"what": "x", "all": no_cell}])))


def test_every_cell_resting_on_a_reading_points_to_its_quote(built):
    """Each n/a, parked and flag decision, and each mapped rule, is a reading listed with its quote; its cell says
    which reading."""
    readings = {e["id"]: e for e in built.readings()}
    for pid in built.rows:
        for d in built.districts:
            reading_parts = [dec for _, dec in built.cells[pid][d] if dec["status"] in audit.READINGS]
            marks = built._reading_ids(pid, d)
            assert bool(marks) >= bool(reading_parts), (pid, d)
            assert all(f"[{', '.join(marks)}]" in built._short(pid, d) for _ in [0] if marks)
    text = built.render()
    for e in readings.values():
        if e["status"] in audit.READINGS:
            assert e["dec"]["quote"] in text.split("## Decisions resting on a reading")[1].split("## Each piece")[0]


def test_the_summary_counts_cells_resting_on_a_reading(built):
    head = built.render().split("## The table")[0]
    rested = {(e["piece"], d) for e in built.readings() for d in e["cells"]}
    assert f"**Resting on a reading:** {len(rested)} of the 1476 cells" in head
    assert "code checks only that the quote is the law's words where it says" in head


# Provenance review round 1.

def test_each_reading_lists_exactly_the_rules_each_of_its_districts_maps(built):
    for e in built.readings():
        i = built._parts(e["piece"]).index(e["what"])
        for d in e["cells"]:
            dec = built.cells[e["piece"]][d][i][1]
            mapped = sorted({r for r in built._expand(d, dec.get("rules")) if dec.get("status") in ("rulebook", "flag")
                             and not built._reaches(d, r, e["piece"], built.part_lines[e["piece"]][i])})
            assert mapped == e["mapped"], (e["id"], d)


def test_a_quote_must_occur_exactly_once_where_it_says(decisions):
    found = problems(with_piece(decisions, "325-44A", [{"what": "x", "all": {
        "status": "not_applicable", "why": "w", "page": 126, "quote": "within the C-SU Zone"}}]))
    assert any("found 2 times" in p for p in found)


def test_unlisted_uses_quote_the_sentence_that_says_permitted_uses_are_listed(built):
    dec = built.cells["325-22A"]["R-1a"][0][1]
    assert dec["quote"] == "Uses which are permitted in each use district are listed" and dec["page"] == 24


def test_the_legend_says_a_mapping_gives_a_reason_not_a_quote(built):
    assert "a mapping gives its reason in words" in built.render().split("## The table")[0]


def test_a_readings_note_is_shown_in_the_readings_list(built):
    readings = built.render().split("## Decisions resting on a reading")[1].split("## Each piece")[0]
    assert "Whether §325-19E reaches R-3aa is an open question" in readings


def test_c_su_design_review_quotes_its_own_words(built):
    keys = built._quote_keys("325-44B", built.cells["325-44B"]["R-1a"][0][1])
    assert keys and all(built.owner[k] == "325-44B" for k in keys)


# Provenance review round 2.

def test_a_chart_quote_must_be_the_line_of_the_cell_it_names(decisions):
    """The multiple-dwelling line paired with the Dormitory row's '-' (R-3aa) is refused."""
    bad = dict(decisions["_multiple_not_permitted"], cell={"section": "Primary Uses", "row": "Dormitory"})
    data = with_piece(decisions, "325-3B:row_house", [{"what": "x", "all": {"status": "missing", "priority": "low",
                                                                            "why": "w"}, "R-3aa": bad}])
    assert any("the quote isn't the line of the cell it names" in p for p in problems(data))


def test_special_permit_primary_uses_are_flagged_in_every_district(built):
    i = part_index(built, "325-9B", "Primary uses that need a special permit")
    assert {built.cells["325-9B"][d][i][1]["status"] for d in built.districts} == {"flag"}


def test_parked_says_who_parked_it(built):
    head = built.render().split("## The table")[0]
    assert "or the brief that parked it" in head and built.parked["parking"]["decided"].startswith("Ben's later list")


# Provenance review round 3.

def test_a_chart_quote_is_exactly_its_cells_line(decisions):
    three = dict(decisions["_multiple_not_permitted"], quote="Two-family dwelling [fn4] - - • • • • • • • Multiple "
                 "family dwelling [fn4] - - - - - • • • •[fn5] Fraternity, sorority, or group house - -")
    found = problems(with_piece(decisions, "325-3B:row_house", [{"what": "x", "all": three}]))
    assert any("the quote isn't the line of the cell it names" in p for p in found)


def test_the_mapped_legend_says_at_least_one_rule(built):
    assert "at least one of these rules covers it only by Gordium's stated mapping" in built.render()



# Provenance review round 4.

def test_a_quote_on_any_decision_is_checked(decisions):
    """A mapped rulebook decision's quote is shown as the law's words too, so it must be the law's words."""
    data = with_piece(decisions, "325-17A", [{"what": "x", "all": {
        "status": "rulebook", "rules": ["front_yard", "side_yards", "rear_yard"], "mapped": "m",
        "quote": "Lots in residential districts may be reduced freely"}}])
    assert any("quote not found" in p for p in problems(data))


def test_the_summary_counts_every_flag_and_mapped_flags_apart(built):
    head = built.render().split("## The table")[0]
    flags = sum(len(e["cells"]) for e in built.readings() if e["status"] == "flag")
    assert f"flag {flags};" in head and "of them on flags" in head
