"""The full egress check on each real house (test_data/real_houses/<house>/), against its hand-check.

hand_check.yaml was worked by hand for every rule of New York State's rulebook before the checker ran: `truth` (what
the code says about the house as drawn) and `predicted` (what the checker should say, given the description).
evaluation.md's table states the checker's answer and the truth for every rule. This test holds all three together:

  - the hand-check covers exactly the rulebook's rules (a rule added or removed must be worked by hand);
  - the checker's answer for every rule is the predicted one (a change in what the checker says shows up here);
  - never a false pass: no rule passes unless the hand-check's truth is "complies";
  - evaluation.md's table says what the checker and the hand-check say today, so the page can't go stale.

The lot is in the Town of Orangetown, so no zoning applies; the state rules are loaded the only way the checker
loads them, through a place that inherits them (Ithaca; egress.check runs only the inherited law, not its zoning).
"""

import re
from pathlib import Path

import pytest
import yaml

from design_checker import egress
from rule_format.rulebook import load

REPO = Path(__file__).parents[3]
REAL = REPO / "test_data" / "real_houses"
ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
STATE_BOOK = REPO / "regulations/jurisdictions/new_york/new_york_state/5_building_code_rules/drafted/general.yaml"
NAMES = sorted(p.name for p in REAL.iterdir() if (p / "hand_check.yaml").exists())
CHECKER = {"pass": "complies", "fail": "does not comply", "needs_review": "needs review",
           "not_applicable": "not applicable"}
TRUTH = {"complies": "complies", "does_not_comply": "does not comply", "needs_review": "needs review",
         "not_applicable": "not applicable"}
ROW = re.compile(r"^\| \d+ \| .*\(`([a-z0-9_]+)`\) \| [^|]* \| [^|]* \| ([a-z ]+) \| ([a-z ]+) \| (yes|no) \| ([A-Z]?) \|$")
COUNT = re.compile(r"^\| (complies|does not comply|needs review|not applicable) \| (\d+) \| (\d+) \| (\d+) \|$")
WHY = set("DFGMR")             # the evaluation's classes for a rule the checker is more cautious about
# truths corrected by review (each a "complies" or "not applicable" the drawings don't establish); a revert lets the
# false-pass guard accept a pass there
REVIEWED = {"general.r319_4_1_area_well_min_projection": "needs_review",
            "general.r318_7_6_stair_top_landing": "needs_review",
            "general.r318_7_6_deck_stair_bottom_landing_width": "needs_review",
            # review round 2: the step at the mudroom door onto the garage landing, its railing, the A-5 well
            "general.r318_7_6_garage_top_landing_drop": "needs_review",
            "general.r321_1_2_guard_height_open_side_not_stair": "needs_review",
            "general.r319_4_2_2_area_well_steps_requirements": "needs_review",
            "general.r318_7_6_stair_bottom_landing": "needs_review"}     # review round 4: the porch steps' bare grade
# classes the review loop corrected (round 5: the area well's `opening_below_grade` is a fact not yet measured, M,
# not a gap in the format, F: the format carries `ground_outside`)
CLASSES = {"general.r319_4_area_well_required": "M"}
# needs-review truths whose `why` leans to a fail or a reading: each names the open question that keeps it there, and
# the question records what was searched (round 5)
OPEN = {"general.r318_3_exterior_door_landing_each_side": "README question 9",
        "general.r318_7_6_stair_bottom_landing": "architect question 2"}
TOTALS = re.compile(r"^\| All egress rules \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$")


@pytest.fixture(scope="module")
def found():
    return egress.laws(ITHACA)


def load_yaml(name, file):
    return yaml.safe_load((REAL / name / file).read_text(encoding="utf-8"))


def run(found, name):
    house, hand = load_yaml(name, "house.yaml"), load_yaml(name, "hand_check.yaml")
    return egress.check(found, house, {"dwelling_units": 1}, {"use": set()}), hand


def test_the_houses_with_a_hand_check():
    assert NAMES == ["orangetown_ny_80_south_william"]


@pytest.mark.parametrize("name", NAMES)
def test_the_hand_check_covers_every_rule(name):
    hand = load_yaml(name, "hand_check.yaml")
    ids = [r["id"] for r in hand["rules"]]
    assert len(ids) == len(set(ids))
    assert set(ids) == {r["id"] for r in load(STATE_BOOK)["rules"]}
    for r in hand["rules"]:
        assert r["truth"] in TRUTH and r["predicted"] in CHECKER, r["id"]
        assert r["why"].strip() and r["because"].strip(), r["id"]


@pytest.mark.parametrize("name", NAMES)
def test_every_answer_is_the_predicted_one_and_never_a_false_pass(found, name):
    got, hand = run(found, name)
    assert [s["title"] for s in got["sections"]] == ["Egress (NY State Residential Code 2025)"]
    by_id = {r["id"]: r for r in hand["rules"]}
    assert set(got["results"]) == set(by_id)
    assert {k: v for k, v in got["results"].items()} == {k: r["predicted"] for k, r in by_id.items()}
    false_passes = [k for k, v in got["results"].items() if v == "pass" and by_id[k]["truth"] != "complies"]
    assert false_passes == []
    # nor a false "not applicable": such a rule makes no row in the panel, so an open question would vanish from it
    # (review round 3)
    hidden = [k for k, v in got["results"].items() if v == "not_applicable" and by_id[k]["truth"] != "not_applicable"]
    assert hidden == []
    # no item of the section is kinder than its rule's truth either (one row per part)
    for item in got["items"]:
        if item.get("rule") in by_id and item["status"] == "complies":
            assert by_id[item["rule"]]["truth"] == "complies", item["id"]
    assert got["sections"][0]["state"] == hand["predicted_section_state"]
    if got["sections"][0]["state"] == "complies":        # a section that complies only where every truth allows it
        assert all(r["truth"] in ("complies", "not_applicable") for r in hand["rules"])
    # the items besides the rules' rows: the interior drawing's one problem, and each marked escape opening not in a
    # sleeping room
    others = sorted(i["name"] for i in got["items"] if not i.get("rule"))
    assert others == sorted(hand["predicted_other_items"])
    # each item besides the rules' rows needs review, except what house.yaml says the house has none of: one item per
    # claim, not applicable, saying so with the claim's own source (or, a claim marked as a reading, needs review)
    claims = {c["kind"]: c for c in load_yaml(name, "house.yaml").get("has_none") or []}
    for i in got["items"]:
        if i.get("rule"):
            continue
        claim = claims.get((i.get("has_none") or {}).get("kind"))
        if claim is None:
            assert i["status"] == "needs_review", i["name"]
            continue
        assert i["status"] == ("needs_review" if claim.get("reading") else "not_applicable"), i["name"]
        assert " ".join(claim["source"].split()) in i["reason"], i["name"]
        assert "the model says the house has no" in i["reason"], i["name"]
    assert len([i for i in got["items"] if i.get("has_none")]) == len(claims)
    # every rule a claim sets aside is named in that claim's item, so a not applicable is never hidden; the rest are
    # not applicable from a fact the house gives (every escape opening a window), as the hand-check predicted
    set_aside = {k for i in got["items"] for k in (i.get("has_none") or {}).get("rules", [])}
    for k, v in got["results"].items():
        if v == "not_applicable":
            assert (k in set_aside) == ("has_none" in by_id[k]["because"]), k
    assert got["interior"]["problems"] == ["the stairs weren't read: the model doesn't say these are all the stairs (or that there are none)"]


@pytest.mark.parametrize("name", NAMES)
def test_the_evaluation_table_is_current(found, name):
    got, hand = run(found, name)
    truth = {r["id"]: r["truth"] for r in hand["rules"]}
    rows = {}
    for line in (REAL / name / "evaluation.md").read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            rid = "general." + m.group(1)
            assert rid not in rows, rid
            rows[rid] = m.groups()[1:]
    assert set(rows) == set(truth)
    for rid, (checker, hand_says, agree, why) in rows.items():
        assert checker == CHECKER[got["results"][rid]], rid
        assert hand_says == TRUTH[truth[rid]], rid
        assert agree == ("yes" if checker == hand_says else "no"), rid
        assert (why in WHY) if agree == "no" else why == "", rid
    assert {k: rows[k][3] for k in CLASSES} == CLASSES
    # the count tables are today's: the checker's totals, then (truth, rules, checker agrees, more cautious)
    counts, totals = {}, []
    for line in (REAL / name / "evaluation.md").read_text(encoding="utf-8").splitlines():
        if m := COUNT.match(line):
            counts[m.group(1)] = tuple(int(x) for x in m.groups()[1:])
        if m := TOTALS.match(line):
            totals.append(tuple(int(x) for x in m.groups()))
    text = (REAL / name / "evaluation.md").read_text(encoding="utf-8")
    assert f"The panel shows {len(got['items'])} items. {len(got['rows'])} are the rules' rows" in text
    cautious_rules = sum(CHECKER[got["results"][r]] != TRUTH[truth[r]] for r in truth)
    assert f"It is cautious in {cautious_rules} places" in text
    # of the rules it is cautious about, those the house meets (the rest don't apply to it)
    meets = sum(t == "complies" and got["results"][r] != "pass" for r, t in truth.items())
    assert f"{cautious_rules} rules: {meets} the house meets and {cautious_rules - meets} that don't apply" in text
    answers = list(got["results"].values())
    assert totals == [(len(answers), answers.count("pass"), answers.count("fail"), answers.count("needs_review"),
                       answers.count("not_applicable"))]
    assert set(counts) == set(TRUTH.values())
    for t, (n, same, cautious) in counts.items():
        mine = [rid for rid in truth if TRUTH[truth[rid]] == t]
        assert n == len(mine), t
        assert same == sum(CHECKER[got["results"][rid]] == t for rid in mine), t
        assert cautious == n - same, t


@pytest.mark.parametrize("name", NAMES)
def test_the_truths_review_corrected_stay_corrected(name):
    truth = {r["id"]: r["truth"] for r in load_yaml(name, "hand_check.yaml")["rules"]}
    assert {k: truth[k] for k in REVIEWED} == REVIEWED


@pytest.mark.parametrize("name", NAMES)
def test_each_open_truth_names_its_question(name):
    by_id = {r["id"]: r for r in load_yaml(name, "hand_check.yaml")["rules"]}
    for rid, question in OPEN.items():
        assert by_id[rid]["truth"] == "needs_review" and question in by_id[rid]["why"], rid
    text = (REAL / name / "evaluation.md").read_text(encoding="utf-8")
    grade = text.split('2. **Is bare grade a "floor or landing"', 1)
    assert len(grade) == 2 and "Searched:" in grade[1].split("\n\n", 1)[0]
    assert "common practice says yes" not in text
    fails = text.split("**Why no rule fails", 1)[1].split("\n", 1)[0]
    assert "README question 9" in fails and "architect question 1" in fails
    # a source is cited only if it was read (round 5, second pass: a cited link returned 404)
    assert "raymore.com/" not in text and "IRC 71-13" not in text
    # the area-well row (M) is explained by the basement windows, not the second-floor bedrooms
    assert "bedrooms are on the second floor, yet `opening_below_grade`" not in text and "`bsw1`, `bsw2`" in text
