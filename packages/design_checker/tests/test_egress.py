"""Egress switched on (design_checker/egress.py): Ithaca's check also runs New York State's house-code rules on the
parts the interior measuring gives, one check with one result grouped by law.

What is pinned here:
- Ithaca's check includes the state's rules, loaded by place through `inherits` (the test the 2026-11-12 decision,
  item 6, promised), and a state folder is never checked on its own;
- no interior (or one with no rooms) -> egress waits: never a pass, never a fail, and the design never reads as all
  complying while it waits, though zoning's own section can;
- the worked example: a bedroom whose escape window's sill is 48 in fails R319.2.3, named, cited and quoted, with
  the change it needs;
- a measure left without a value, or given a reason, needs review with that reason, never a pass;
- rules that don't pass the rule checks are never used; the answer is the same every time.
"""

import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

from design_checker import each_part, egress, present
from design_checker.check import check_site, summary
from rule_format.place import place
from rule_format.rulebook import REPO, building_code_rulebook, load

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, box, lot  # noqa: E402

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
STATE = REPO / "regulations/jurisdictions/new_york/new_york_state"
SITE = {"units": "ft", "lot": lot([(0, 0), (60, 0), (60, 110), (0, 110)]),
        "buildings": [box(10, 25, 40, 75, 0, 30)], "problems": []}
RANCH = REPO / "test_data/interior_houses/1_ranch_compliant/house.yaml"
SILL = "general.r319_2_3_escape_opening_max_sill_height"


def ranch():
    return yaml.safe_load(RANCH.read_text(encoding="utf-8"))


def sill_too_high():
    """The worked example: the ranch's Bedroom 1 casement raised so the bottom of its clear opening is 48 in above
    the floor (R319.2.3 allows 44 in at most). Its opening stays 26 x 36 in (6.5 sq ft): only the sill fails."""
    house = ranch()
    w1 = next(o for o in house["openings"] if o["id"] == "w1")
    w1["frame"] = {"left": 0, "right": 26, "bottom": 48, "top": 84}
    return house


def law_items(result):
    return [i for i in result["view"]["items"] if i["group"] == present.LAW_GROUP]


def rows_of(result, rule_id):
    return [i for i in law_items(result) if i["rule"] == rule_id]


# ---- loading by place ----------------------------------------------------------------------------------------------

def test_ithacas_check_includes_the_state_rules():
    """The test the building-code decision (2026-11-12, item 6) promised: Ithaca inherits New York State's folder,
    and its check runs every one of that folder's rules."""
    book = building_code_rulebook(STATE)
    assert place(ITHACA).inherited_rulebooks() == ((STATE, book),)
    rules = load(book)["rules"]
    assert len(rules) >= 53                                   # the 53 drafted house egress rules, at least
    found = egress.laws(ITHACA)
    assert [law["key"] for law in found["laws"]] == ["new_york/new_york_state"]
    assert found["laws"][0]["problems"] == [] and found["laws"][0]["rules"] == rules
    result = check_site(SITE, dict(FACTS), interior=ranch())
    assert set(result["egress"]["results"]) == {r["id"] for r in rules}       # every state rule answered
    assert [s["title"] for s in result["sections"]] == ["Zoning (City of Ithaca)",
                                                        "Egress (NY State Residential Code 2025)"]


def test_a_state_folder_is_never_checked_on_its_own():
    with pytest.raises(ValueError, match="a state's law, not a place"):
        check_site(SITE, dict(FACTS, jurisdiction="regulations/jurisdictions/new_york/new_york_state"))
    with pytest.raises(ValueError, match="a state's law, not a place"):
        egress.laws(STATE)


def test_a_hand_written_state_rulebook_comes_before_the_drafted_one(tmp_path):
    (tmp_path / "5_building_code_rules/drafted").mkdir(parents=True)
    assert building_code_rulebook(tmp_path) is None
    (tmp_path / "5_building_code_rules/drafted/general.yaml").write_text("rules: []\n", encoding="utf-8")
    assert building_code_rulebook(tmp_path) == tmp_path / "5_building_code_rules/drafted/general.yaml"
    (tmp_path / "5_building_code_rules/general.yaml").write_text("rules: []\n", encoding="utf-8")
    assert building_code_rulebook(tmp_path) == tmp_path / "5_building_code_rules/general.yaml"


# ---- no interior: egress waits ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("interior", [None, "no rooms"])
def test_no_interior_egress_waits_and_is_never_a_pass(interior):
    if interior == "no rooms":
        interior = dict(ranch(), rooms=[])
    result = check_site(SITE, dict(FACTS), interior=interior)
    mine = law_items(result)
    assert [(i["id"], i["status"], i["name"]) for i in mine] == [
        ("egress.waiting", present.NOT_CHECKED, "Egress: waiting, no rooms drawn yet")]
    assert result["sections"][1]["state"] == egress.WAITING
    assert result["sections"][1]["summary"] == "waiting, no rooms drawn yet"
    assert result["egress"]["rows"] == [] and result["egress"]["results"] == {}
    assert (result["egress"]["interior_sha256"] is None) == (interior is None)
    assert result["view"]["summary"].endswith(" · Egress: waiting, no rooms drawn yet")
    assert result["view"]["state"] != present.COMPLIES and result["summary"]["state"] != "pass"


def test_zoning_may_comply_while_egress_waits_but_the_design_never_reads_as_complying():
    """Ben, 2026-11-12: two separate results; zoning can say complies before the interior exists. The design's own
    state and line stay short of complying while egress waits."""
    zoning = [{"id": "R-1b.rear_yard", "rule": "R-1b.rear_yard", "name": "Rear yard", "group": "building",
               "status": present.COMPLIES}]
    view = {"items": copy.deepcopy(zoning)}
    egress.add_to_view(view, egress.check(egress.laws(ITHACA), None, {}, {}), "City of Ithaca")
    assert view["sections"][0] == {"key": "zoning", "title": "Zoning (City of Ithaca)", "state": present.COMPLIES,
                                   "summary": "1 complies"}
    assert view["sections"][1]["state"] == egress.WAITING
    assert view["state"] == present.REVIEW                         # never complies while egress waits
    assert view["summary"] == "Zoning: 1 complies · Egress: waiting, no rooms drawn yet"
    passing = [{"Error": "PASS", "Requirement": "Rear yard", "Rule id": "R-1b.rear_yard"}]
    assert summary(passing, zoning)["state"] == "pass"              # zoning alone: a pass, as before
    assert summary(passing, view["items"])["state"] == "review"     # with egress waiting: never a pass
    assert [g["title"] for g in view["groups"]][-1] == "Egress (NY State Residential Code 2025)"


# ---- the worked example ------------------------------------------------------------------------------------------------

def test_worked_example_a_bedroom_whose_escape_window_sill_is_too_high():
    result = check_site(SITE, dict(FACTS), interior=sill_too_high())
    [row] = [i for i in rows_of(result, SILL) if i["status"] == present.FAILS]
    assert row["name"] == "Bedroom 1 › Window 1 · Escape opening bottom of clear opening max height (R319.2.3)"
    assert row["reason"] == "Bedroom 1 › Window 1: sill height 48 in, needs ≤ 44 in"      # the change it needs
    assert row["code"] == {"section": "R319.2.3", "quote": "Emergency escape and rescue openings shall have the "
                           "bottom of the clear opening not greater than 44 inches (1118 mm) above the floor."}
    assert row["detail"]["citation"].startswith("R319.2.3, 2025 Residential Code of New York State")
    assert row["part"]["id"] == "w1"
    others = [i for i in rows_of(result, SILL) if i is not row]
    assert [(i["part"]["id"], i["status"]) for i in others] == [("w2", present.COMPLIES)]
    assert result["egress"]["results"][SILL] == "fail"
    assert result["egress"]["interior_sha256"] == egress.fingerprint(sill_too_high())    # which interior it read
    assert result["egress"]["interior_sha256"] != egress.fingerprint(ranch())
    assert result["sections"][1]["state"] == present.FAILS
    assert result["view"]["state"] == present.FAILS and result["summary"]["state"] == "fail"
    assert "Egress: 1 does not comply" in result["view"]["summary"]
    # the same window, sill back at 30 in (the ranch as drawn): the rule's row complies
    assert [i["status"] for i in rows_of(check_site(SITE, dict(FACTS), interior=ranch()), SILL)] == [
        present.COMPLIES, present.COMPLIES]


def test_every_part_row_names_its_part_section_and_quote():
    result = check_site(SITE, dict(FACTS), interior=sill_too_high())
    rows = [i for i in law_items(result) if i["rule"]]
    assert rows and all(i["code"]["section"] and i["code"]["quote"] for i in rows)
    assert all(i["detail"]["quotes"] and i["detail"]["quotes"][0]["text"] == i["code"]["quote"] for i in rows)
    assert len({i["id"] for i in result["view"]["items"]}) == len(result["view"]["items"])      # ids unique


# ---- never a pass on a doubtful measure --------------------------------------------------------------------------------

def test_a_measure_not_measured_needs_review_with_its_reason():
    house = ranch()
    w1 = next(o for o in house["openings"] if o["id"] == "w1")
    w1["operation"] = "awning"                    # no maker's clear opening: the measuring gives no sill, with why
    result = check_site(SITE, dict(FACTS), interior=house)
    [row] = [i for i in rows_of(result, SILL) if i["part"]["id"] == "w1"]
    measured = next(p for p in result["egress"]["interior"]["parts"]["emergency_escape_opening"] if p["id"] == "w1")
    why = measured["not_measured"]["opening_sill_height"]
    assert row["status"] == present.REVIEW
    assert row["reason"] == f"Bedroom 1 › Window 1: sill height not measured: {why}"


def test_a_measure_its_measuring_doubts_is_never_used():
    """A part that carries a value and a reason for the same measure (a host's description, say): the reason wins,
    so the rule needs review, never the pass the value would give."""
    rule = next(r for r in load(building_code_rulebook(STATE))["rules"] if r["id"] == SILL)
    part = {"id": "w1", "name": "Window 1", "within": "bed1", "measures": {"opening_sill_height": 30},
            "not_measured": {"opening_sill_height": "the drawn and stated sills differ"}}
    given = {"sleeping_room": [{"id": "bed1", "name": "Bedroom 1", "measures": {}}],
             "emergency_escape_opening": [part]}
    got = each_part.check_parts([rule], given, {}, {"use": set()})
    assert got["results"] == {SILL: "needs_review"}
    assert got["items"][0]["reason"] == "Bedroom 1 › Window 1: sill height not measured: the drawn and stated " \
                                        "sills differ"
    clean = copy.deepcopy(given)
    del clean["emergency_escape_opening"][0]["not_measured"]
    assert each_part.check_parts([rule], clean, {}, {"use": set()})["results"] == {SILL: "pass"}


def test_rules_that_fail_the_rule_checks_are_never_used(monkeypatch):
    monkeypatch.setattr(egress, "rulebook_file_problems", lambda path, ctx: ["a quote isn't at its lines"])
    result = check_site(SITE, dict(FACTS), interior=sill_too_high())
    mine = law_items(result)
    assert [(i["id"], i["status"]) for i in mine] == [("egress.rules", present.REVIEW)]
    assert "a quote isn't at its lines" in mine[0]["reason"]
    assert result["egress"]["results"] == {} and result["sections"][1]["state"] == present.REVIEW


def test_an_unreadable_interior_needs_review_never_waits_or_passes():
    result = check_site(SITE, dict(FACTS), interior={"format": "gordium.interior/9", "rooms": [{"id": "r"}]})
    mine = law_items(result)
    assert not any(i.get("waiting") for i in mine)
    assert {i["status"] for i in mine} == {present.REVIEW}
    assert any(i["name"] == "Interior drawing" and "gordium.interior/1" in i["reason"] for i in mine)


def test_the_same_design_and_rules_give_the_same_answer():
    one = check_site(SITE, dict(FACTS), interior=sill_too_high())
    two = check_site(SITE, dict(FACTS), interior=sill_too_high())
    keep = lambda r: json.dumps([law_items(r), r["sections"], r["egress"]], sort_keys=True, default=str)
    assert keep(one) == keep(two)


def test_the_workers_fingerprint_of_a_place_follows_the_state_rules_it_inherits(tmp_path, monkeypatch):
    """The worker's `about` names the rules a check reads: an edit to the inherited state rules shows there, as an
    edit to the place's own does (protocol.rulebook_fingerprints)."""
    import shutil
    from design_checker import protocol
    from rule_format.place import Place
    ithaca = place(ITHACA)
    root = tmp_path / "new_york"
    for folder in (ithaca.folder, STATE):
        for f in protocol.place_files(folder):
            to = root / folder.name / f.relative_to(folder)
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, to)
    monkeypatch.setattr(protocol, "places", lambda: [Place(root / "ithaca_city", ithaca.settings)])
    before = protocol.rulebook_fingerprints()
    book = root / "new_york_state/5_building_code_rules/drafted/general.yaml"
    book.write_text(book.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    assert protocol.rulebook_fingerprints() != before


def test_a_description_that_leaves_out_its_rooms_needs_review_never_waits():
    """Review round 1 (F4): only an empty list of rooms is massing; a description without `rooms` wasn't read."""
    house = ranch()
    del house["rooms"]
    mine = law_items(check_site(SITE, dict(FACTS), interior=house))
    assert not any(i.get("waiting") for i in mine) and present.COMPLIES not in {i["status"] for i in mine} - {
        i["status"] for i in mine if i["rule"] and "door" in i["rule"]}
    assert any("rooms weren't read" in i["reason"] for i in mine if i["name"] == "Interior drawing")


def test_the_waiting_words_never_promise_parts_the_drawing_isnt_read_for():
    """Review round 1 (F1): guards, handrails and lofts aren't read yet; the waiting row says so."""
    assert "handrails, guards and sleeping lofts aren't read from the drawing yet" in egress.WAITING_WHY
    assert "handrails, guards and the exit door are checked" not in egress.WAITING_WHY


def test_a_check_validates_the_state_rules_the_same_with_or_without_the_code_cache(monkeypatch, tmp_path):
    """Review round 1 (F2): the book's quotes are checked by python -m rule_format where the cache is, never at a
    design's check, so the same design gets the same answer on every machine."""
    with_cache = egress.laws(ITHACA)
    monkeypatch.setenv("GORDIUM_CODE_CACHE", str(tmp_path / "none"))
    without = egress.laws(ITHACA)
    assert [(l["problems"], l["rules"]) for l in with_cache["laws"]] == [(l["problems"], l["rules"])
                                                                         for l in without["laws"]]
    from rule_format.rulebook import Context
    assert Context.for_jurisdiction(STATE, use_cache=False).pages == {}       # the book's text is never read
    asked = []
    real = Context.for_jurisdiction.__func__
    monkeypatch.setattr(Context, "for_jurisdiction",
                        classmethod(lambda cls, j, **kw: asked.append(kw) or real(cls, j, **kw)))
    egress.laws(ITHACA)
    assert asked == [{"use_cache": False}]                                  # a design's check never reads it


def test_a_law_whose_every_row_is_not_applicable_never_vanishes_from_the_answer():
    """Review round 1 (F3, confirmed by two sceptics): rows not applicable are left out of the panel, so a law whose
    every row is not applicable had no item, and the design read "complies" beside its needs-review section."""
    found = egress.laws(ITHACA)
    stairs = [r for r in found["laws"][0]["rules"] if r.get("for_each") == "stair"]
    found["laws"][0]["rules"] = stairs                          # a house with no stairs: every row not applicable
    house = dict(ranch(), stairs=[])
    got = egress.check(found, house, {}, {"use": set()})
    assert [(i["id"], i["status"]) for i in got["items"]] == [("egress.nothing_applied", present.REVIEW)]
    view = {"items": [{"id": "z", "rule": "z", "name": "Rear yard", "group": "building", "status": present.COMPLIES}]}
    egress.add_to_view(view, got, "City of Ithaca")
    assert view["state"] == present.REVIEW and "Egress: 1 needs review" in view["summary"]
    # and the design's state is never kinder than a section's, even given a section with no item at all
    view = {"items": [{"id": "z", "rule": "z", "name": "Rear yard", "group": "building", "status": present.COMPLIES}]}
    egress.add_to_view(view, dict(got, items=[]), "City of Ithaca")
    assert view["state"] == present.REVIEW


def test_an_interior_with_number_keys_is_fingerprinted_never_a_crash():
    """Review round 2 (F1): YAML allows `1: a`; the fingerprint once raised TypeError and took the check down."""
    house = ranch()
    house["rooms"][0][1] = "a"
    assert egress.fingerprint(house) != egress.fingerprint(dict(ranch(), rooms=[dict(ranch()["rooms"][0], **{"1": "a"})]
                                                            + ranch()["rooms"][1:]))
    result = check_site(SITE, dict(FACTS), interior=house)
    assert result["egress"]["interior_sha256"] and present.COMPLIES != result["view"]["state"]


def test_rules_that_cant_be_used_are_said_even_while_no_rooms_are_drawn(monkeypatch):
    """Review round 2 (F2): "waiting" would hide that the state's rules don't pass the rule checks."""
    monkeypatch.setattr(egress, "rulebook_file_problems", lambda path, ctx: ["a quote isn't at its lines"])
    result = check_site(SITE, dict(FACTS))
    assert [(i["id"], i["status"]) for i in law_items(result)] == [("egress.rules", present.REVIEW)]
    assert result["sections"][1]["state"] == present.REVIEW


def test_an_escape_opening_the_measuring_skips_is_shown_never_silent():
    """Review round 2 (F3): an escape window in a room that isn't a sleeping room is left out of the parts; the
    panel says so (it may be a basement's or an attic's, not read yet)."""
    house = ranch()
    next(o for o in house["openings"] if o["id"] == "w3")["escape"] = True
    [row] = [i for i in law_items(check_site(SITE, dict(FACTS), interior=house)) if i["id"] == "egress.skipped#1"]
    assert row["status"] == present.REVIEW and row["name"] == "Window 3: not checked"
    assert "in a room that isn't a sleeping room" in row["reason"]


def test_a_state_rule_not_written_for_each_part_needs_review_never_dropped():
    """Review round 3 (F1, confirmed by two sceptics): check_parts keeps only rules for each part, so a state rule
    without for_each got no row and no answer, and the section could read as complying with it unchecked."""
    found = egress.laws(ITHACA)
    whole = {k: v for k, v in copy.deepcopy(found["laws"][0]["rules"][0]).items() if k not in egress.part_rules.PART_FIELDS}
    whole["id"] = "general.whole_building"
    found["laws"][0]["rules"].append(whole)
    got = egress.check(found, ranch(), {}, {"use": set()})
    assert got["results"]["general.whole_building"] == "needs_review"
    [row] = [i for i in got["items"] if i["rule"] == "general.whole_building"]
    assert row["status"] == present.REVIEW and row["reason"] == egress.NOT_PER_PART
    assert row["code"]["section"]                               # still names its code section
    assert row["name"] == f"Egress · {whole['title']}"           # round 4: its title once, never twice


@pytest.mark.parametrize("settings", ["results_title: 5\n", "- a list\n", "name: [\n"])
def test_a_bad_state_settings_file_needs_review_never_takes_zoning_down(settings, tmp_path, monkeypatch):
    """Review round 3 (F2): state.yaml was read outside the guard: a results_title that isn't words, or a file that
    isn't a mapping, crashed the whole check (zoning's answer with it)."""
    real = egress.load
    monkeypatch.setattr(egress, "load", lambda p: yaml.safe_load(settings) if Path(p).name == "state.yaml"
                        else real(p))
    import rule_format.state_law as sl
    monkeypatch.setattr(sl, "load", lambda p: yaml.safe_load(settings) if Path(p).name == "state.yaml" else real(p))
    if settings == "name: [\n":
        bad = lambda p: (_ for _ in ()).throw(yaml.YAMLError("bad")) if Path(p).name == "state.yaml" else real(p)
        monkeypatch.setattr(egress, "load", bad)
        monkeypatch.setattr(sl, "load", bad)
    result = check_site(SITE, dict(FACTS), interior=sill_too_high())
    assert result["sections"][0]["key"] == "zoning"
    [only] = law_items(result)
    assert only["status"] == present.REVIEW and only["id"].endswith(".rules")
    assert result["egress"]["results"] == {}


def test_a_saved_report_names_the_interior_it_was_checked_against(tmp_path):
    """Review round 3 (F3): the report listed egress rows but not which interior they came from."""
    from openpyxl import load_workbook
    out = tmp_path / "report.xlsx"
    house = sill_too_high()
    check_site(SITE, dict(FACTS), interior=house, report_path=out)
    cells = [c.value for c in load_workbook(out)["Check"]["A"] if c.value]
    assert f"Interior checked: sha256 {egress.fingerprint(house)}" in cells
    check_site(SITE, dict(FACTS), report_path=out)
    assert "Interior: none drawn yet" in [c.value for c in load_workbook(out)["Check"]["A"] if c.value]
    # round 4: an interior with no rooms was fingerprinted but not checked: never said "checked"
    empty = dict(ranch(), rooms=[])
    check_site(SITE, dict(FACTS), interior=empty, report_path=out)
    cells = [c.value for c in load_workbook(out)["Check"]["A"] if c.value]
    assert f"Interior: sha256 {egress.fingerprint(empty)} (no rooms drawn yet, egress not checked)" in cells
