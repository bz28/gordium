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
            "general.r319_4_2_2_area_well_steps_requirements": "needs_review"}
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
    # no item of the section is kinder than its rule's truth either (one row per part)
    for item in got["items"]:
        if item.get("rule") in by_id and item["status"] == "complies":
            assert by_id[item["rule"]]["truth"] == "complies", item["id"]
    assert got["sections"][0]["state"] == hand["predicted_section_state"]
    # the items besides the rules' rows: the interior drawing's one problem, and each marked escape opening not in a
    # sleeping room
    others = sorted(i["name"] for i in got["items"] if not i.get("rule"))
    assert others == sorted(hand["predicted_other_items"])
    assert all(i["status"] == "needs_review" for i in got["items"] if not i.get("rule"))
    assert got["interior"]["problems"] == ["the stairs weren't read (no `stairs` in the description)"]


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
