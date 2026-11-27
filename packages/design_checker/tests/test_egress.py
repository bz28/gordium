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
import sys as _sys  # noqa: E402
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))   # egress_house beside this file
import egress_house  # noqa: E402
from design_checker.check import check_site, summary
from rule_format import published
from rule_format.place import place
from rule_format.rulebook import REPO, Context, building_code_rulebook, load

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, box, lot  # noqa: E402

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
STATE = REPO / "regulations/jurisdictions/new_york/new_york_state"
BUILDING = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
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
    and its check runs every one of that folder's rules. Since 2026-11-22 it inherits the Building Code's folder too,
    and a house the Residential Code covers is checked against the house code alone, its sections as before."""
    book = building_code_rulebook(STATE)
    assert place(ITHACA).inherited_rulebooks() == ((STATE, book), (BUILDING, building_code_rulebook(BUILDING)))
    rules = load(book)["rules"]
    assert len(rules) >= 53                                   # the 53 drafted house egress rules, at least
    found = egress.laws(ITHACA)
    assert [(law["key"], law["scope"]) for law in found["laws"]] == [
        ("new_york/new_york_state", "residential_code"), ("new_york/new_york_state_building", "building_code")]
    assert found["laws"][0]["problems"] == [] and found["laws"][0]["rules"] == rules
    assert found["laws"][1]["problems"] == []
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
    assert result["view"]["summary"].endswith(" · Egress waiting: no rooms drawn yet")
    assert result["view"]["state"] != present.COMPLIES and result["summary"]["state"] != "pass"


def test_zoning_may_comply_while_egress_waits_but_the_design_never_reads_as_complying():
    """Ben, 2026-11-12: two separate results; zoning can say complies before the interior exists. The design's own
    state and line stay short of complying while egress waits."""
    zoning = [{"id": "R-1b.rear_yard", "rule": "R-1b.rear_yard", "name": "Rear yard", "group": "building",
               "status": present.COMPLIES}]
    view = {"items": copy.deepcopy(zoning)}
    egress.add_to_view(view, egress.check(egress.laws(ITHACA), None, dict(egress_house.HOUSE), {}), "City of Ithaca")
    assert view["sections"][0] == {"key": "zoning", "title": "Zoning (City of Ithaca)", "state": present.COMPLIES,
                                   "summary": "1 complies"}
    assert view["sections"][1]["state"] == egress.WAITING
    assert view["state"] == present.REVIEW                         # never complies while egress waits
    assert view["summary"] == "Zoning complies · Egress waiting: no rooms drawn yet"      # choice B (2026-11-15)
    assert view["waiting_only"] is True and view["state"] == present.REVIEW       # shown grey, still needs review
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


EVERY_BEDROOM = "general.r319_1_sleeping_room_escape_opening_operable"     # when_none: fail


def test_a_space_whose_use_isnt_known_keeps_every_bedroom_rule_from_passing_and_the_drawn_rooms_are_checked():
    """An enclosed space with no room drawn in it (a Revit plan circuit with no Room) may be a bedroom: R319.1's
    "every sleeping room has an escape opening" never passes, and never fails on it, while the rooms drawn are still
    checked exactly as before (house 1's windows: the sill rule's rows, a bedroom's failing window)."""
    space = [{"id": "area-1", "name": "Enclosed area on L1 with no Room (331.4 sq ft)"}]
    house = ranch() | {"unknown_spaces": space}
    got = check_site(SITE, dict(FACTS), interior=house)
    [row] = [i for i in rows_of(got, EVERY_BEDROOM) if i["part"]["within"] and i["part"]["within"]["id"] == "area-1"]
    assert row["status"] == present.REVIEW and "its use isn't known, so it may be a sleeping room" in row["reason"]
    assert got["egress"]["results"][EVERY_BEDROOM] != "pass"
    # the drawn bedrooms' windows are checked as before: the sill rule, which a room with no opening doesn't reach
    assert [i["status"] for i in rows_of(got, SILL)] == [present.COMPLIES, present.COMPLIES]
    bad = sill_too_high() | {"unknown_spaces": space}
    assert check_site(SITE, dict(FACTS), interior=bad)["egress"]["results"][SILL] == "fail"
    # a house with no bedroom drawn: "every bedroom" is not applicable, but not beside a space that may be one
    six = yaml.safe_load((REPO / "test_data/interior_houses/6_door_stated_clear/house.yaml").read_text(encoding="utf-8"))
    assert check_site(SITE, dict(FACTS), interior=six)["egress"]["results"][EVERY_BEDROOM] == "not_applicable"
    six["unknown_spaces"] = space
    assert check_site(SITE, dict(FACTS), interior=six)["egress"]["results"][EVERY_BEDROOM] == "needs_review"


def test_rules_that_fail_the_rule_checks_are_never_used(monkeypatch):
    _refuse_rule_checks(monkeypatch)
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


def _compiled():
    """compile_law of each law Ithaca inherits, live (what publish freezes)."""
    return [published.compile_law(f, b) for f, b in place(ITHACA).inherited_rulebooks()]


def _refuse_rule_checks(monkeypatch, problem="a quote isn't at its lines"):
    """A rulebook that fails the rule checks: such a law is never published (publish refuses it), so the check reads
    what compile_law says of it, live, here (rule_format/published.py)."""
    monkeypatch.setattr(published, "rulebook_file_problems", lambda path, ctx: [problem])
    monkeypatch.setattr(egress, "frozen", lambda f, b: {**published.compile_law(f, b), "book": None})


def test_a_law_is_validated_the_same_with_or_without_the_code_cache_and_a_check_validates_nothing(monkeypatch,
                                                                                                 tmp_path):
    """Review round 1 (F2): the book's quotes are checked by python -m rule_format where the cache is, never in the
    validation a check's answer rests on (compile_law, frozen by publish), so the same design gets the same answer on
    every machine. And a check itself validates nothing: it reads the frozen answer."""
    with_cache = _compiled()
    monkeypatch.setenv("GORDIUM_CODE_CACHE", str(tmp_path / "none"))
    assert _compiled() == with_cache
    from rule_format.rulebook import Context
    assert Context.for_jurisdiction(STATE, use_cache=False).pages == {}       # the book's text is never read
    asked = []
    real = Context.for_jurisdiction.__func__
    monkeypatch.setattr(Context, "for_jurisdiction",
                        classmethod(lambda cls, j, **kw: asked.append(kw) or real(cls, j, **kw)))
    _compiled()
    assert asked == [{"use_cache": False}] * 2       # the validation never reads it (both of New York's books)
    asked.clear()
    assert all(law["rules"] for law in egress.laws(ITHACA)["laws"]) and asked == []    # a check validates nothing


def test_a_laws_validation_reads_no_book_text_from_the_code_cache_even_where_the_cache_has_it(monkeypatch, tmp_path):
    """The open finding of docs/decisions/2026-11-23_laws_validation_speed.md: with use_cache=False the state book's
    text was still read from the code cache wherever the cache had it (so a laptop with the cache and CI without it
    could differ). A code cache holding the Residential Code's text, built here so this fails on any machine: the
    validation reads none of it, and gives exactly the answer it gives with no cache at all."""
    from rule_format.rulebook import Context, cached_text
    monkeypatch.setenv("GORDIUM_CODE_CACHE", str(tmp_path / "none"))
    without = _compiled()
    (entry,) = [d for d in load(STATE / "1_source_documents/sources.yaml")["documents"] if d.get("kept_outside_repo")]
    monkeypatch.setenv("GORDIUM_CODE_CACHE", str(tmp_path / "cache"))
    text = cached_text(entry)
    text.parent.mkdir(parents=True)
    rows = [{"file": entry["file"], "sha256": entry["sha256"]}, {"page": 1, "line": 1, "text": "SECTION R101 GENERAL"}]
    text.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert Context.for_jurisdiction(STATE, use_cache=False).pages == {}           # never read by the validation
    assert _compiled() == without


def test_a_check_takes_the_frozen_validation_as_it_is_and_compile_law_never_raises(monkeypatch):
    """laws() takes frozen()'s answer (the certificate's compile_law result) as it is: a problem there means no rules
    (needs review, never a row), said as the frozen copy being unusable. compile_law (what is frozen) gives the
    problems, documents and kinds, and sources that can't be read are a problem, never a crash."""
    folder, book = place(ITHACA).inherited_rulebooks()[0]
    good = published.compile_law(folder, book)
    assert set(good) == {"problems", "documents", "kinds"} and good["problems"] == [] and good["documents"]
    found = egress.laws(ITHACA)["laws"][0]
    assert {k: found[k] for k in good} == good and found["rules"] and found["section_of"] and not found["unpublished"]
    stale = "regulations/x/general.published.json is stale (input changed: y): run python -m rule_format publish"
    monkeypatch.setattr(egress, "frozen", lambda f, b: {"problems": [stale], "documents": {}, "kinds": {}, "book": None})
    refused = egress.laws(ITHACA)["laws"][0]
    assert refused["problems"] == [stale] and refused["rules"] == [] and refused["section_of"] is None
    assert refused["unpublished"] and refused["documents"] == {} and refused["kinds"] == {}
    mine = law_items(check_site(SITE, dict(FACTS), interior=sill_too_high()))
    assert [(i["id"], i["status"]) for i in mine] == [("egress.rules", present.REVIEW)]   # a house: one law runs
    assert all("frozen copy can't be used" in i["reason"] and stale in i["reason"] for i in mine)
    monkeypatch.undo()
    from rule_format.rulebook import Context

    def broken(cls, j, **kw):
        raise OSError("disk gone")
    monkeypatch.setattr(Context, "for_jurisdiction", classmethod(broken))
    assert published.compile_law(folder, book) == {"problems": ["its sources can't be read (OSError: disk gone)"],
                                                   "documents": {}, "kinds": {}}
    monkeypatch.undo()

    def bad_kinds(self):        # e.g. a proposed measure's unit that isn't a word: its sources were read, then this
        raise TypeError("bad unit")
    monkeypatch.setattr(Context, "allowed", bad_kinds)
    late = published.compile_law(folder, book)       # as before the split: the sources kept, no kinds, no rules
    assert late == {"problems": ["its sources can't be read (TypeError: bad unit)"], "documents": good["documents"],
                    "kinds": {}}


def test_a_law_whose_every_row_is_not_applicable_never_vanishes_from_the_answer():
    """Review round 1 (F3, confirmed by two sceptics): rows not applicable are left out of the panel, so a law whose
    every row is not applicable had no item, and the design read "complies" beside its needs-review section."""
    found = egress.laws(ITHACA)
    stairs = [r for r in found["laws"][0]["rules"] if r.get("for_each") == "stair"]
    found["laws"][0]["rules"] = stairs                          # a house with no stairs: every row not applicable
    house = dict(ranch(), stairs=[])
    one_story = dict(egress_house.HOUSE, stories_above_grade_plane=1)   # "no stairs" is never beside two or more
    got = egress.check(found, house, one_story, egress_house.ALLOWED)
    assert [(i["id"], i["status"]) for i in got["items"]] == [("egress.nothing_applied", present.REVIEW),
                                                              ("egress.not_checked_yet", present.REVIEW)]
    found["laws"][0]["not_checked_yet"] = []     # this pin is about nothing_applied alone: every section checked
    got = egress.check(found, house, one_story, egress_house.ALLOWED)
    assert [(i["id"], i["status"]) for i in got["items"]] == [("egress.nothing_applied", present.REVIEW)]
    view = {"items": [{"id": "z", "rule": "z", "name": "Rear yard", "group": "building", "status": present.COMPLIES}]}
    egress.add_to_view(view, got, "City of Ithaca")
    assert view["state"] == present.REVIEW and "Egress: 1 to review" in view["summary"]   # results grouping
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
    _refuse_rule_checks(monkeypatch)
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
    got = egress.check(found, ranch(), dict(egress_house.HOUSE), egress_house.ALLOWED)
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
    # a state.yaml edited so is a changed input: its law is refused (its certificate is stale, or never published:
    # the validation, compile_law, finds the problem), so here the check reads what compile_law says, live
    monkeypatch.setattr(egress, "frozen", lambda f, b: {**published.compile_law(f, b), "book": None})
    result = check_site(SITE, dict(FACTS), interior=sill_too_high())
    assert result["sections"][0]["key"] == "zoning"
    # every state.yaml is the bad one here, so neither says which buildings it covers: both run, each refused
    items = law_items(result)
    assert [(i["status"], i["id"].split("#")[0].endswith(".rules")) for i in items] == [(present.REVIEW, True)] * 2
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


def test_no_stairs_beside_rooms_on_two_floors_leaves_every_stair_row_to_review():
    """"No stairs" (an empty list) on a house whose rooms are on two floors is a contradiction (a stair or a ramp
    joins them, or each floor has its own way out at grade, none of which the model shows): the stairs aren't read,
    so every stair row needs review naming nothing as complying, never not applicable as for a one-floor house; the
    reason is said among the interior's problems."""
    found = egress.laws(ITHACA)
    stair_rules = {r["id"] for r in found["laws"][0]["rules"] if r.get("for_each") == "stair"}
    assert stair_rules

    def results(house, stories=1):
        values = dict(egress_house.HOUSE, stories_above_grade_plane=stories)
        got = egress.check(found, house, values, egress_house.ALLOWED)
        return got, {k: v for k, v in got["results"].items() if k in stair_rules}

    flat = dict(ranch(), stairs=[], guards=[])
    _, one_floor = results(flat)
    assert set(one_floor) == stair_rules and set(one_floor.values()) == {"not_applicable"}, one_floor
    two = copy.deepcopy(flat)
    two["rooms"][-1]["floor_elevation"] = 108                     # one room 9 ft up: a second floor
    got, two_floors = results(two)
    assert set(two_floors) == stair_rules and set(two_floors.values()) == {"needs_review"}, two_floors
    assert any(p.startswith("the model says there are no stairs, yet its rooms' floors are at different heights")
               for p in got["interior"]["problems"]), got["interior"]["problems"]
    assert any("no stairs, yet" in (i.get("reason") or "") for i in got["items"])       # said to the architect
    # round 2 (skeptic B): each stair row says the model's "no stairs" wasn't taken, never that it wasn't sent
    stair_items = [i for i in got["items"] if i.get("rule") in stair_rules]
    assert stair_items and all(each_part.NOT_TAKEN in " ".join((i.get("open") or {}).get("inputs") or [])
                               for i in stair_items), stair_items[0].get("open")
    assert not any(each_part.NOT_SENT in " ".join((i.get("open") or {}).get("inputs") or []) for i in stair_items)
    asks = {c["words"] for i in stair_items for c in i.get("causes") or []}
    assert 'the model\'s "no stairs" isn\'t taken: the interior drawing says why' in asks, asks
    # skeptic A, round 1: a house stated as 3 stories, drawn with its ground floor alone, never sets them aside
    got, stated = results(flat, stories=3)
    assert set(stated.values()) == {"needs_review"}, stated
    assert any("the architect states 3 stories above grade plane" in p for p in got["interior"]["problems"])


def test_the_building_codes_stairs_none_is_read_against_its_rooms_levels():
    """The Building Code's stairs and guards are measured with the description's rooms left out
    (egress._stairs_and_guards): "no stairs" is still read against those rooms' levels, so a building of two stories
    stated with no stairs has its stairs not read (their rules need review), while one of a single story keeps it."""
    one = {"format": "gordium.interior/1", "units": "in", "stairs": [], "guards": [],
           "rooms": [{"id": "a", "level": "L1"}, {"id": "b", "level": "L1"}]}
    assert egress._stairs_and_guards(one)["parts"]["stair"] == []
    two = copy.deepcopy(one)
    two["rooms"][1]["level"] = "L2"
    two["levels"] = [{"id": "L2", "name": "Level 2", "elevation": 120}, {"id": "L1", "name": "Level 1", "elevation": 0}]
    got = egress._stairs_and_guards(two)
    assert got["parts"]["stair"] is None
    assert any("its rooms are on 2 levels (Level 1 and Level 2)" in p for p in got["problems"]), got["problems"]
    undrawn = dict(one, unknown_spaces=[{"id": "u", "level": "L2"}])     # skeptic A/B: an upper floor, no room drawn
    assert egress._stairs_and_guards(undrawn)["parts"]["stair"] is None
    assert egress._stairs_and_guards(one, stated_stories=2)["parts"]["stair"] is None
    above = "the architect states {n} stories above grade plane"
    assert egress._stated_stories({"building": {"stories_above_grade_plane": 2}}, {"stories": 1}) == (2, above)
    assert egress._stated_stories({}, {"stories": True}) is None                     # a yes/no is no count
    assert egress._stated_stories(None, None) is None
    # round 2: the count the architect typed for the place, kept where the place's own count is an open question
    from design_checker import code_scope
    typed = egress._stated_stories({}, {code_scope.STORIES_TYPED: 3, "stories": None})
    assert typed == (3, "the architect gives the building {n} stories")
    assert egress._stated_stories({}, {"stories": 2})[1].startswith("the building's stories, as the place counts")


def test_the_architects_typed_story_count_reaches_egress_whether_or_not_the_place_settles_it():
    """Review round 2 (skeptic A): Ithaca's count is None wherever its readings disagree or it is refused (a floor
    block over the ground's, no grade given), so "no stairs" was taken under a typed 3; the typed count now reaches
    egress on its own (code_scope.STORIES_TYPED), never a guess from the height."""
    from design_checker import code_scope
    from design_checker.check import _with_stories_bound
    got = _with_stories_bound({"stories": None}, {"stories": {"objects": []}}, {"stories": 3})
    assert got[code_scope.STORIES_TYPED] == 3
    for odd in ({}, {"stories": "3"}, {"stories": float("nan")}, {"stories": True}):
        assert code_scope.STORIES_TYPED not in _with_stories_bound({}, {}, odd), odd


def test_the_building_codes_stated_stories_reach_its_stairs_through_its_reading():
    """Review rounds 2 and 3 (skeptic A's test gap): the Building Code's reading (egress._measured, for a law with a
    rule over stairs: the drafted rulebook has none yet, so a law that has one stands in) passes the check's stated
    stories to its stairs' measuring: the stairs aren't read, its `refused` says why, and so do its problems."""
    sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
    import make_ny_build_data as build
    from design_checker import code_scope
    desc = build.interior_of()
    desc["stairs"] = []
    for r in desc["rooms"] + (desc.get("unknown_spaces") or []):
        r["level"] = desc["rooms"][0]["level"]                     # every room on one level, one floor height:
        r.pop("floor_elevation", None)                             # only the count tells
    law = {"scope": code_scope.BUILDING, "folder": str(REPO / "regulations/jurisdictions/new_york/new_york_state_building"),
           "rules": [{"id": "x", "for_each": "stair"}]}
    assert egress._reads_interior(law)
    for stated, refused in ((2, True), (1, False)):
        readings = {}
        got = egress._measured(law, desc, readings, None, {"stories_above_grade_plane": stated})
        assert (got["parts"].get("stair") is None) is refused, stated
        assert bool(got.get("refused")) is refused, stated
        assert any("the architect states 2 stories above grade plane" in p for p in got["problems"]) is refused
