"""The check's results grouped for an architect (docs/decisions/2026-11-16_results_grouping.md): failures first,
then what the architect can act on, then one line per cause for what Gordium can't read yet, then what complies,
folded. Presentation only. What is pinned here, each failing if its fix is undone:

- no failure is ever folded out of the headline (every failing item is in the fails tier and counted, even one
  whose `open` says Gordium's gap);
- folded items keep their statuses (grouping never changes an item);
- every item is reachable: in exactly one line, and a row of the panel's list exactly once;
- the state is unchanged (each golden house's state, independently known, and present.state over the items);
- the waiting state is unchanged (no rooms: the same headline, group and grey as before);
- a likely failure Gordium can't settle (the tall riser) is shown to the architect, never folded with the gaps;
- the headline never reads as a pass while anything needs review.
"""

import copy
import sys

import pytest

from design_checker import egress, grouping, present
from design_checker import rhino_logic as logic
from design_checker.check import check_site
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/permit_sheets"))
from permit_sheets import goldens  # noqa: E402

HOUSES = [n for n in goldens.names() if n != "0_no_rooms_yet"]
# each house's state, known from its own description (its README / the design of the made-up house), not from code
STATE = {"1_ranch_compliant": present.REVIEW, "2_two_story_small_window": present.FAILS,
         "3_tall_riser": present.REVIEW, "4_loft": present.FAILS, "5_basement_window_well": present.FAILS,
         "orangetown_ny_80_south_william": present.REVIEW}
# 5_basement_window_well: its window's net clear area, its well's ladder, and (since the door's operation is read,
# #112) its only exit door, a sliding one, against R318.2's "shall be side-hinged"
FAILING = {"2_two_story_small_window": 1, "4_loft": 2, "5_basement_window_well": 4}


@pytest.fixture(scope="module")
def checked():
    out = {}
    for name in goldens.names():
        out[name] = check_site(goldens.site(), goldens.facts_of(name), name=name, today=goldens.DATE,
                               interior=goldens.interior_of(name))
    return out


def law_items(result):
    return [i for i in result["view"]["items"] if i["group"] == present.LAW_GROUP]


def every_line(got):
    return [ln for t in grouping.TIERS for ln in got[t]]


@pytest.mark.parametrize("name", HOUSES)
def test_no_failure_is_ever_folded_out_of_the_headline(checked, name):
    items = law_items(checked[name])
    got = grouping.lines(items)
    fails = [i["id"] for i in items if i["status"] == present.FAILS]
    assert [x for ln in got[grouping.FAILS_T] for x in ln["items"]] == fails
    assert all(ln["status"] == present.FAILS for ln in got[grouping.FAILS_T])
    assert len(fails) == FAILING.get(name, 0)
    head = grouping.summary(items)
    if fails:
        assert head.startswith(f"{len(fails)} {'does not comply' if len(fails) == 1 else 'do not comply'}")
    else:
        assert "not comply" not in head


def test_a_fail_that_also_says_gordiums_gap_is_still_a_fail():
    item = {"id": "a", "group": present.LAW_GROUP, "status": present.FAILS, "open": {"gordium": grouping.NOT_READ, "kinds": ["stair"]},
            "name": "Stairs · rule", "element": "Stairs", "reason": "Stairs: no stair"}
    got = grouping.lines([item])
    assert got[grouping.FAILS_T][0]["items"] == ["a"] and not got[grouping.BY_HAND_T]
    assert grouping.summary([item]) == "1 does not comply"


@pytest.mark.parametrize("name", goldens.names())
def test_grouping_never_changes_an_item(checked, name):
    items = law_items(checked[name])
    before = copy.deepcopy(items)
    grouping.lines(items)
    grouping.summary(items)
    present.grouped(checked[name]["view"]["items"])
    logic.list_tree(checked[name]["view"])
    assert items == before


@pytest.mark.parametrize("name", HOUSES)
def test_every_item_is_in_exactly_one_line(checked, name):
    items = law_items(checked[name])
    ids = [x for ln in every_line(grouping.lines(items)) for x in ln["items"]]
    assert sorted(ids) == sorted(i["id"] for i in items)
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("name", goldens.names())
def test_every_item_is_a_row_of_the_panels_list_exactly_once(checked, name):
    view = checked[name]["view"]
    rows = [c["item"] for g in logic.list_tree(view) for c in g["children"] if c.get("item")] + \
        [x["item"] for g in logic.list_tree(view) for c in g["children"] for x in c.get("children") or []]
    assert sorted(rows) == sorted(i["id"] for i in view["items"])
    assert len(rows) == len(set(rows))


@pytest.mark.parametrize("name", goldens.names())
def test_the_state_is_unchanged(checked, name):
    view = checked[name]["view"]
    assert view["state"] == STATE.get(name, present.REVIEW)
    assert view["state"] == min([present.state(view["items"])] + [
        present.REVIEW if s["state"] == egress.WAITING else s["state"] for s in view["sections"][1:]],
        key=[present.FAILS, present.REVIEW, present.COMPLIES].index)
    for s in checked[name]["sections"][1:]:
        if s["state"] != egress.WAITING:
            assert s["state"] == present.state(law_items(checked[name]))


def test_the_waiting_state_is_unchanged(checked):
    view = checked["0_no_rooms_yet"]["view"]
    assert view["summary"].endswith("Egress waiting: no rooms drawn yet")
    law = [g for g in view["groups"] if g["key"] == "new_york/new_york_state"]
    assert len(law) == 1 and law[0]["title"] == "Egress (NY State Residential Code 2025)"
    assert law[0]["items"] == [i["id"] for i in law_items(checked["0_no_rooms_yet"])]
    assert "lines" not in law[0]
    assert checked["0_no_rooms_yet"]["sections"][1]["summary"] == egress.WAITING_WORDS


def test_a_likely_failure_gordium_cant_settle_is_shown_never_folded(checked):
    items = {i["id"]: i for i in law_items(checked["3_tall_riser"])}
    riser = items["general.r318_7_5_1_stair_riser_height_max@-/s"]
    assert riser["status"] == present.REVIEW            # unsettled: whether the stair serves a sleeping loft
    assert riser["open"]["concern"] == "riser height 9 in, needs ≤ 8.25 in"
    assert grouping.tier(riser) == grouping.REVIEW_T
    got = grouping.lines(list(items.values()))
    first = got[grouping.REVIEW_T][0]
    assert riser["id"] in first["items"] and "may not comply: riser height 9 in" in first["title"]


def test_a_rule_reading_something_measured_stays_with_the_architect(checked):
    items = law_items(checked["2_two_story_small_window"])
    for i in items:
        o = i.get("open") or {}
        if grouping.tier(i) == grouping.BY_HAND_T and o.get("gordium") == grouping.NOT_MEASURED:
            assert i["status"] == present.REVIEW
            assert not o.get("concern")
    headroom = next(i for i in items if i["id"].startswith("general.r318_7_2_stair_headroom@"))
    assert grouping.tier(headroom) == grouping.REVIEW_T     # it reads the measured headroom


def test_a_missing_value_the_drawing_can_give_is_to_review_not_by_hand(checked):
    items = law_items(checked["orangetown_ny_80_south_william"])
    frames = [i for i in items if "the opening's frame isn't given" in (i.get("reason") or "")]
    assert frames and all(grouping.tier(i) == grouping.REVIEW_T for i in frames)


def test_the_headline_counts_what_an_architect_counts(checked):
    items = law_items(checked["2_two_story_small_window"])
    # 10 comply: the front door's "shall be side-hinged" among them, its operation read since #112
    assert grouping.summary(items) == ("1 does not comply · 2 to review · 10 comply · 13 parts not read yet · "
                                       "86 sections not checked yet")
    got = grouping.lines(items)
    assert [ln["title"] for ln in got[grouping.FAILS_T]] == [
        "Bedroom 3 › Window 5: 1 does not comply (net clear area 5.12 sq ft, needs ≥ 5.7 sq ft: R319.2.1)"]
    assert got[grouping.BY_HAND_T][0]["title"].startswith("Not read from the model yet: handrails (10 rules), ")
    assert got[grouping.BY_HAND_T][-1]["title"] == "Not checked yet by Gordium: 86 code sections: check by hand"


def test_only_gordiums_gaps_left_says_needs_review_first_never_a_pass():
    items = [{"id": "c", "group": present.LAW_GROUP, "status": present.COMPLIES, "element": "W", "name": "W · r", "reason": ""},
             {"id": "g", "group": present.LAW_GROUP, "status": present.REVIEW, "open": {"gordium": grouping.NOT_READ, "kinds": ["handrail"]},
              "element": "Handrails", "name": "Handrails · r2", "reason": "Handrails: the handrails aren't read yet"}]
    assert grouping.summary(items) == "needs review · 1 complies · 1 part not read yet"


def test_an_unknown_status_is_shown_to_review_never_folded():
    item = {"id": "u", "group": present.LAW_GROUP, "status": "something_new", "name": "X", "reason": "why"}
    assert grouping.tier(item) == grouping.REVIEW_T
    assert grouping.lines([item])[grouping.REVIEW_T][0]["items"] == ["u"]


def test_not_applicable_is_folded_with_what_complies_and_never_counted_as_complying():
    part = {"part": "stair", "id": "s", "name": "Stairs", "within": None}
    items = [{"id": "n", "group": present.LAW_GROUP, "status": grouping.NOT_APPLICABLE, "part": part, "element": "Stairs", "name": "Stairs · r",
              "reason": "Stairs: the description says the house has no stairs"},
             {"id": "c", "group": present.LAW_GROUP, "status": present.COMPLIES, "part": part, "element": "Stairs", "name": "Stairs · r2", "reason": ""}]
    got = grouping.lines(items)
    assert got[grouping.COMPLIES_T][0]["title"] == "Stairs: 1 complies · 1 doesn't apply"
    assert grouping.counts(items)["complies"] == 1


def test_the_panel_groups_put_egress_failures_right_after_zonings(checked):
    keys = [g["key"] for g in checked["2_two_story_small_window"]["view"]["groups"]]
    law = "new_york/new_york_state"
    assert keys.index(f"{law}:fails") < keys.index(f"{law}:review") < keys.index(f"{law}:by_hand") \
        < keys.index(f"{law}:complies")
    assert keys.index(f"{law}:fails") < keys.index("review")


# ---- review round 1 on the plan: a value Gordium works out (but doesn't give the rules yet) is never a gap ----------

@pytest.mark.parametrize("name, item_id, words", [
    ("3_tall_riser", "general.r318_7_5_1_stair_riser_variation_max@-/s", "riser variation 1.5 in"),
    ("5_basement_window_well", "general.r318_7_8_stair_handrail_one_side@-/bs", "handrail sides 0, needs ≥ 1"),
    ("4_loft", "general.r318_7_1_stair_clear_width_at_handrail@-/ls", "clear width at handrail 21 in")])
def test_a_likely_failure_in_a_worked_out_value_is_shown_never_folded(checked, name, item_id, words):
    items = law_items(checked[name])
    [item] = [i for i in items if i["id"] == item_id]
    assert item["status"] == present.REVIEW and words in item["open"]["concern"]
    assert grouping.tier(item) == grouping.REVIEW_T
    [line] = [ln for ln in grouping.lines(items)[grouping.REVIEW_T] if item_id in ln["items"]]
    assert "may not comply: " in line["title"] and words in line["title"]


@pytest.mark.parametrize("name", HOUSES)
def test_nothing_folded_by_hand_fails_on_what_was_measured_or_worked_out(checked, name):
    from design_checker import each_part
    from rule_format.rulebook import load
    parts_ = checked[name]["egress"]["interior"]["parts"]
    more = {(k, p["id"]): p.get("more") or {} for k, ps in parts_.items() if isinstance(ps, list) for p in ps}
    rules = {r["id"]: r for law in egress.laws(goldens.FACTS["jurisdiction"])["laws"] for r in law["rules"]}
    rows = {(r["rule"], r.get("part"), r.get("id")): r for r in checked[name]["egress"]["rows"]}
    for i in law_items(checked[name]):
        if grouping.tier(i) != grouping.BY_HAND_T or not i.get("part") or not i["part"].get("id") \
                or not isinstance(rules[i["rule"]].get("check"), str):      # a flag has no check to fail
            continue
        p = i["part"]
        row = rows[(i["rule"], p["part"], p["id"])]
        known = {**(row.get("values") or {}), **{k: v for k, v in more[(p["part"], p["id"])].items()
                                                 if k in (row.get("values") or {})}}
        assert each_part._first_failing(rules[i["rule"]], known, {"use": set()}, if_it_applies=True) is None, i["id"]


def test_a_list_the_description_left_out_is_the_drawings_to_give_never_gordiums_gap(checked):
    items = law_items(checked["orangetown_ny_80_south_william"])
    got = grouping.lines(items)
    causes = [c["words"] for ln in got[grouping.BY_HAND_T] for c in ln.get("causes") or []]
    assert not any(c.startswith("stairs") for c in causes)
    [stairs] = [ln for ln in got[grouping.REVIEW_T] if ln["title"].startswith("Stairs: ")]
    assert len(stairs["items"]) == 30 and stairs["title"].endswith(": to give: the stairs weren't sent from the model")


def test_the_panel_list_shows_a_part_of_several_rules_as_one_folded_line(checked):
    view = checked["2_two_story_small_window"]["view"]
    tree = {g["tag"]: g for g in logic.list_tree(view)}
    fails = tree["group:new_york/new_york_state:fails"]
    assert not fails["folded"] and fails["children"][0]["item"] and fails["children"][0]["title"].startswith(
        "Bedroom 3 › Window 5: 1 does not comply")
    by_hand = tree["group:new_york/new_york_state:by_hand"]
    first = by_hand["children"][0]
    assert first["tag"].startswith("line:") and first["folded"] and first["status"] == present.REVIEW
    assert first["title"].startswith("Not read from the model yet: handrails")
    assert tree["group:new_york/new_york_state:complies"]["folded"]


def test_the_rhino_panel_draws_the_lines_and_never_selects_one():
    from host_source import host_text
    ui = host_text("rhino", "ui", purpose="wiring")
    assert "logic.list_tree(view)" in ui
    assert 'tag.startswith(("group:", "line:"))' in ui


def test_a_rule_reading_a_worked_out_value_stays_with_the_architect_even_when_it_passes(checked):
    """The main stair's tread variation (0 in, worked out, not given to the rules yet) is something Gordium read:
    its rule is the architect's to look at, never folded with what Gordium can't read. (The riser variation was
    this example until it was given to the rules, 2026-11-20.)"""
    [item] = [i for i in law_items(checked["2_two_story_small_window"])
              if i["id"] == "general.r318_7_5_2_stair_tread_variation_max@-/s1"]
    assert not item["open"].get("concern") and "tread variation 0 in" in item["open"]["worked"]
    assert grouping.tier(item) == grouping.REVIEW_T


def test_a_waiting_item_among_others_is_never_dropped():
    items = [{"id": "w", "group": present.LAW_GROUP, "status": present.NOT_CHECKED, "waiting": "no rooms drawn yet",
              "name": "Egress: waiting", "reason": "why"},
             {"id": "r", "group": present.LAW_GROUP, "status": present.REVIEW, "name": "Egress rules",
              "reason": "refused"}]
    ids = [x for ln in every_line(grouping.lines(items)) for x in ln["items"]]
    assert sorted(ids) == ["r", "w"]


# ---- review round 1 on #111 -----------------------------------------------------------------------------------------

def test_a_fact_the_measuring_found_about_a_part_keeps_its_rules_with_the_architect(checked):
    """The basement house's only exit door is sliding: the measuring said "this door is sliding" (its clear width,
    measured open 90 degrees, isn't asked of it). Its rules are never folded as something Gordium can't read: the
    clear-width rule stays to review with that reason, and the "shall be side-hinged" rule, which reads the door's
    operation (#112), does not comply."""
    items = law_items(checked["5_basement_window_well"])
    [hinged] = [i for i in items if i["id"] == "general.r318_2_egress_door_side_hinged@-/de"]
    assert hinged["status"] == present.FAILS and grouping.tier(hinged) == grouping.FAILS_T
    width = [i for i in items if i["id"].endswith("@-/de") and i["status"] == present.REVIEW
             and "this door is sliding" in str(i.get("open"))]
    assert width and all(grouping.tier(i) == grouping.REVIEW_T for i in width)
    [line] = [ln for ln in grouping.lines(items)[grouping.REVIEW_T] if width[0]["id"] in ln["items"]]
    assert "this door is sliding" in line["title"]


def test_a_window_is_no_door_is_no_fact_that_keeps_its_rules_from_check_by_hand(checked):
    """A window's "whether it is a side-hinged or sliding door is asked only of a door" (#112) is neither Gordium's
    gap nor a fact about the window: the rules on what Gordium doesn't measure of it yet stay in "Check by hand",
    never moved to "Needs review" by it (the 2-story house's two windows, as before #112)."""
    items = law_items(checked["2_two_story_small_window"])
    review = [ln["title"] for ln in grouping.lines(items)[grouping.REVIEW_T]]
    assert not any(t.startswith(("Bedroom 3 › Window 5:", "Bedroom 4 › Window 6:")) for t in review), review


def test_a_parts_failures_are_shown_open_and_its_line_keeps_its_key_when_lines_reorder(checked):
    view = checked["5_basement_window_well"]["view"]
    fails = {g["tag"]: g for g in logic.list_tree(view)}["group:new_york/new_york_state:fails"]
    several = [c for c in fails["children"] if c["tag"].startswith("line:")]
    assert several and not any(c["folded"] for c in several)
    items = law_items(checked["5_basement_window_well"])
    keys = {ln["key"]: ln["items"] for ln in every_line(grouping.lines(items))}
    keys_reversed = {ln["key"]: ln["items"] for ln in every_line(grouping.lines(list(reversed(items))))}
    assert set(keys) == set(keys_reversed) and all(sorted(keys[k]) == sorted(keys_reversed[k]) for k in keys)


# ---- review round 2 on #111 -----------------------------------------------------------------------------------------

def test_an_out_of_date_list_shows_each_lines_name_never_its_result(checked):
    """While a check runs, or after an edit, the panel blanks each row's result; a line's words carry its result
    ("4 comply"), so an out-of-date list shows the line's name alone (gordium_ui reads `name` when stale)."""
    for name in ("2_two_story_small_window", "5_basement_window_well"):
        for g in logic.list_tree(checked[name]["view"]):
            for c in g["children"]:
                if c.get("title"):
                    assert c["name"] and not any(w in c["name"] for w in ("comply", "need review", "needs review"))
    from host_source import host_text
    ui = host_text("rhino", "ui", purpose="wiring")
    assert '(c.get("name") or "") if parts["stale"]' in ui and 'name if stale_row else' in ui


def test_everything_the_architect_has_to_give_is_named_never_shortened(checked):
    items = law_items(checked["orangetown_ny_80_south_william"])
    [door] = [ln for ln in grouping.lines(items)[grouping.REVIEW_T] if ln["title"].startswith("Front entry door")]
    given = [w for i in items if i["id"] in door["items"] for w in (i.get("open") or {}).get("inputs") or []]
    assert len(set(given)) >= 3 and all(w in door["title"] for w in given)


# ---- review round 3 on #111 -----------------------------------------------------------------------------------------

def test_an_out_of_date_list_names_each_cause_and_each_laws_heading_without_its_result(checked):
    items = law_items(checked["1_ranch_compliant"])
    assert [ln["name"] for ln in grouping.lines(items)[grouping.BY_HAND_T]] == [
        "Not read from the model yet", "Not measured from the model yet", "Not checked yet by Gordium"]
    heads = [g for g in logic.list_tree(checked["2_two_story_small_window"]["view"]) if g.get("name")]
    assert heads and all(g["name"] == "Egress" for g in heads)
    from host_source import host_text
    assert 'g.get("name") if parts["stale"] and g.get("name") else g["title"]' in \
        host_text("rhino", "ui", purpose="wiring")


def test_every_decision_is_named_never_shortened():
    items = [{"id": f"r{n}", "group": present.LAW_GROUP, "status": present.REVIEW, "name": f"Rule {n}",
              "element": "Front door", "part": {"part": "egress_door", "id": "d", "name": "Front door"},
              "rule": f"rule_{n}", "open": {"gordium": None, "decide": True}} for n in range(4)]
    [line] = grouping.lines(items)[grouping.REVIEW_T]
    assert "more" not in line["title"] and line["title"].count("Rule") == 4


# ---- review round 4 on #111: a part measured under another kind is never "not read" -------------------------------

def test_a_measured_guard_that_fails_is_shown_never_folded_as_not_read():
    import copy
    from permit_sheets import goldens as sheet_goldens
    from design_checker.check import check_site
    house = copy.deepcopy(sheet_goldens.interior_of("4_loft"))
    g = house["guards"][0]
    g["top"] = 3505.2                                   # 30 in above the loft floor (needs ≥ 36 in)
    g["members"][0] = {"left": 0, "right": 1219.2, "bottom": 3467.1, "top": 3505.2}
    for m in g["members"][2:]:
        m["top"] = 3467.1
    r = check_site(sheet_goldens.site(), dict(sheet_goldens.FACTS), name="4_loft", today=sheet_goldens.DATE,
                   interior=house)
    items = law_items(r)
    got = grouping.lines(items)
    height = [i["id"] for i in items if i["rule"] == "general.r321_1_2_guard_height_open_side_not_stair"]
    assert height and not any(x in ln["items"] for ln in got[grouping.BY_HAND_T] for x in height)
    assert any("may not comply" in ln["title"] and "guard height 30 in, needs ≥ 36 in" in ln["title"]
               for ln in got[grouping.REVIEW_T])


# ---- review round 5 on #111: anything the measuring found on a guard is shown, never folded as "not read" ---------

def _loft(change):
    import copy
    from permit_sheets import goldens as sheet_goldens
    from design_checker.check import check_site
    house = copy.deepcopy(sheet_goldens.interior_of("4_loft"))
    for g in change(house):
        house["guards"].append(g)
    r = check_site(sheet_goldens.site(), dict(sheet_goldens.FACTS), name="4_loft", today=sheet_goldens.DATE,
                   interior=house)
    items = law_items(r)
    guards = [i["id"] for i in items if "r321" in (i.get("rule") or "")]
    return items, grouping.lines(items), guards


def test_a_guard_the_measuring_could_not_measure_keeps_its_rules_to_review_with_its_reason():
    def no_top_rail(house):           # its balusters stop at 30 in: "the guard's members don't reach its stated top"
        house["guards"][0]["members"] = house["guards"][0]["members"][1:]
        return []
    items, got, guards = _loft(no_top_rail)
    assert len(guards) == 7 and not any(x in ln["items"] for ln in got[grouping.BY_HAND_T] for x in guards)
    assert any("stated top" in ln["title"] for ln in got[grouping.REVIEW_T])
    assert all(i["status"] == present.REVIEW for i in items if i["id"] in guards)     # statuses unchanged


def test_a_guard_value_the_rule_does_not_read_yet_is_shown_on_its_rules():
    def two_balusters(house):         # a 31 in gap (the 4 in sphere rule doesn't read the sphere yet: a flag)
        house["guards"][0]["members"] = house["guards"][0]["members"][:3]
        return []
    items, got, guards = _loft(two_balusters)
    sphere = [i["id"] for i in items if i.get("rule") == "general.r321_1_3_guard_opening_4_inch_sphere"]
    assert sphere and not any(x in ln["items"] for ln in got[grouping.BY_HAND_T] for x in sphere)
    assert any("guard opening sphere 31 in" in ln["title"] for ln in got[grouping.REVIEW_T])


def test_every_guard_is_named_on_the_line_the_measured_and_the_one_not_measured():
    def second_guard(house):
        import copy
        g = copy.deepcopy(house["guards"][0])
        g.update(id="g2", name="Second guard", members=g["members"][1:])
        return [g]
    items, got, guards = _loft(second_guard)
    titles = " ".join(ln["title"] for ln in got[grouping.REVIEW_T])
    assert "Loft guard: guard height 36 in" in titles and "Second guard: guard height and guard opening sphere not measured" in titles


def test_a_concern_from_a_rule_that_may_not_apply_to_the_guard_says_which_rule():
    import yaml
    from rule_format.rulebook import REPO
    from design_checker import each_part
    rules = yaml.safe_load((REPO / "regulations/jurisdictions/new_york/new_york_state/5_building_code_rules/drafted/"
                                   "general.yaml").read_text(encoding="utf-8"))
    [rule] = [r for r in rules["rules"] if r["id"] == "general.r321_1_2_guard_height_open_side_not_stair"]
    given = {"guard": [{"id": "sg", "name": "Stair guard", "measures": {"guard_height": 35.0}, "not_measured": {}}]}
    got = each_part._stand_ins(rule, ["open_side"], given, {})
    assert got["concern"] == "Stair guard: guard height 35 in, needs ≥ 36 in, if Guard height, open sides other " \
                             "than stairs (R321.1.2) applies to it"


# ---- review round 6 on #111: a guard's reasons, each said once, each where it belongs; a host's bad part is no value

def _height_rule():
    import yaml
    from rule_format.rulebook import REPO
    rules = yaml.safe_load((REPO / "regulations/jurisdictions/new_york/new_york_state/5_building_code_rules/drafted/"
                                   "general.yaml").read_text(encoding="utf-8"))
    [rule] = [r for r in rules["rules"] if r["id"] == "general.r321_1_2_guard_height_open_side_not_stair"]
    return rule


def test_a_guard_reason_for_two_measures_is_said_once():
    def no_top_rail(house):
        house["guards"][0]["members"] = house["guards"][0]["members"][1:]
        return []
    items, got, guards = _loft(no_top_rail)
    [line] = [ln for ln in got[grouping.REVIEW_T] if "stated top" in ln["title"]]
    assert line["title"].count("stated top") == 1 and "guard height and guard opening sphere not measured" \
        in line["title"]


def test_a_stair_guard_opening_gordium_does_not_measure_yet_is_listed_as_not_read_never_as_to_fix():
    from design_checker import each_part
    from model_measurement.interior.stops import STOPS
    given = {"guard": [{"id": "sg", "name": "Stair guard", "measures": {"guard_height": 35.25},
                        "not_measured": {"guard_opening_sphere": STOPS["stair_guard_openings"]}}]}
    got = each_part._stand_ins(_height_rule(), ["open_side"], given, {})
    assert got["gordium"] is None and got["gaps"] == ["Stair guard: guard opening sphere"]
    assert not any("openings" in n for n in got["notes"])


def test_a_guard_part_a_host_sends_malformed_is_no_value_never_a_crash():
    from design_checker import each_part
    bad = [{"id": "a", "measures": [1], "not_measured": {5: "x"}},
           {"id": "b", "measures": {"guard_height": True, 7: 30.0, "guard_opening_sphere": "30"}}]
    got = each_part._stand_ins(_height_rule(), ["open_side"], {"guard": bad}, {})
    assert got["notes"] == ["a: 5 not measured (x)"] and "concern" not in got
