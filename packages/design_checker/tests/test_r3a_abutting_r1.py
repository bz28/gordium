"""R-3a.abutting_r1 (§325-19E) through the whole checker: the stricter limits reach only a lot that "directly
abuts land in either the R-1a or R-1b Zoning District", so whether it does is a stated fact (abuts_r1_district,
asked the cautious way: any R-1a or R-1b land touching the lot (even at a corner), or across a street, alley, creek
or other waterway, railroad or other right-of-way from it). Unknown: needs review, asking for it; no: not
applicable (no row: the panel lists only rules that apply); yes: needs review (the flag: the reviewer applies the
stricter limits). A one-family or two-family dwelling is exempt either way: nothing to ask."""

import copy

import pytest

from design_checker import present, rhino_logic, scenarios
from design_checker.check import check_site

RULE = "R-3a.abutting_r1"


def _item(use, **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["use"] = use
    s, f, extras = scenarios.site(sc)
    res = check_site(s, {**f, **facts}, extras=extras)
    return next((i for i in res["view"]["items"] if i["rule"] == RULE), None)


def test_a_multiple_dwelling_waits_for_whether_the_lot_abuts_r1_land():
    item = _item("multiple_family")
    assert item["status"] == present.REVIEW, item
    assert item["needs"] == ["abuts_r1_district"], item
    assert rhino_logic.enter_words(item["needs"]) == "Enter whether the lot abuts R-1 land"


def test_a_lot_that_doesnt_abut_r1_land_is_not_reached_by_the_stricter_limits():
    assert _item("multiple_family", abuts_r1_district=False) is None
    assert _item("church", abuts_r1_district=False) is None


@pytest.mark.parametrize("use", ["multiple_family", "church"])
def test_a_lot_that_abuts_r1_land_needs_review(use):
    item = _item(use, abuts_r1_district=True)          # (so the "no" rows above are absent for the fact alone)
    assert item["status"] == present.REVIEW and not item.get("needs"), item


@pytest.mark.parametrize("abuts", [None, False, True])
def test_a_two_family_dwelling_is_exempt_whether_or_not_the_lot_abuts_r1_land(abuts):
    facts = {} if abuts is None else {"abuts_r1_district": abuts}
    assert _item("two_family", **facts) is None


def test_the_panel_asks_it_yes_or_no_and_a_skipped_answer_stays_unset():
    assert rhino_logic.STATED_FACTS["abuts_r1_district"][1] == "yes_no"
    assert rhino_logic.update_counts({}, {"abuts_r1_district": False}) == {"abuts_r1_district": False}
    assert rhino_logic.update_counts({"abuts_r1_district": True}, {"abuts_r1_district": None}) == \
        {"abuts_r1_district": True}


# every case a "no" must rule out (#20 review round 1, P1): R-1 land touching even at a corner, and across a street,
# an alley, a creek or other waterway, a railroad or other right-of-way (§325-9B(1)(j): "a street or waterway")
CASES = ("corner", "street", "alley", "creek", "waterway", "railroad", "right-of-way")


def test_every_place_the_question_is_asked_names_every_case_a_no_must_rule_out():
    """A truthful "no" for R-1 land across a creek or touching at a corner dropped §325-19E while R-3a's own limits
    passed. The prompt, the measures.yaml meaning, the stop and the recorded reading (why_open) each name every
    case, so "no" is right under every reading of open question 1."""
    import yaml
    from model_measurement.stops import STOPS
    from rule_format.rulebook import MEASURES_FILE, REPO, load
    rule = next(r for r in load(REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-3a.yaml")["rules"]
                if r["id"] == RULE)
    places = {"prompt": rhino_logic.STATED_FACTS["abuts_r1_district"][0],
              "measures.yaml": yaml.safe_load(MEASURES_FILE.read_text(encoding="utf-8"))["abuts_r1_district"]["meaning"],
              "stop": STOPS["no_abuts_r1"],
              "why_open": " ".join(rule["research"][0]["why_open"].split()),
              "this module's docstring": " ".join(__doc__.split())}
    for where, text in places.items():
        missing = [c for c in CASES if c not in text]
        assert not missing, (where, missing, text)


def test_the_rules_notes_and_the_architects_page_say_the_architect_states_it():
    """#20 review round 1, P2: the notes (exported to the rules workbook) and §5.5/§5.6 still said Gordium doesn't
    know the neighbouring zoning and always sends the lot to review."""
    from rule_format.rulebook import REPO, load
    rule = next(r for r in load(REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-3a.yaml")["rules"]
                if r["id"] == RULE)
    # in plain words (Ithaca's plain_words): the note names the fact by the field the architect fills in, not its key
    from design_checker.host_core.facts import ABOUT_LABELS
    label = ABOUT_LABELS["abuts_r1_district"]
    assert f"“{label}” in Setup" in rule["notes"] and "stated by the architect" in rule["notes"]
    assert "abuts_r1_district" not in rule["notes"] and "doesn't know the zoning" not in rule["notes"]
    doc = (REPO / "docs/questions_for_architects.md").read_text(encoding="utf-8")
    for tag in ("[R-3a.abutting_r1#1]", "[R-3a.abutting_r1#2]"):
        section = doc.split(tag, 1)[1].split("\n### ", 1)[0]
        assert "abuts_r1_district" in section and "doesn't know the zoning" not in section, tag


def _rule():
    from rule_format.rulebook import REPO, load
    return next(r for r in load(REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-3a.yaml")["rules"]
                if r["id"] == RULE)


def test_the_open_question_itself_asks_every_case_its_readings_answer():
    """#20 review round 2 (P2): the readings named the alley, waterway, railroad and corner cases while the question
    (in the rules and on the architects' page) asked only "across a street"; an answer to it as written would leave
    them open. The question, its research copy and §5.5's heading each ask every case."""
    from rule_format.rulebook import REPO
    rule = _rule()
    doc = (REPO / "docs/questions_for_architects.md").read_text(encoding="utf-8")
    heading = next(line for line in doc.splitlines() if line.startswith("### 5.5 "))
    assert rule["open_questions"][0] == rule["research"][0]["question"]
    for where, text in {"open_questions[0]": rule["open_questions"][0], "§5.5's heading": heading}.items():
        missing = [c for c in CASES if c not in " ".join(text.split())]
        assert not missing, (where, missing, text)


def test_the_railroad_and_waterway_reading_rests_on_quoted_law():
    """#20 review round 2 (P3): why_open says §325-6 treats rail and water boundaries as it does streets; §325-6D and
    §325-6E (p.23 lines 33-37) are quoted with it, and searched."""
    research = _rule()["research"][0]
    quotes = {(s["page"], tuple(s["lines"])): s["quote"] for s in research["sources"]}
    assert "railroad" in quotes[(23, (33, 34))] and "body of water" in quotes[(23, (35, 37))]
    assert {"325-6D", "325-6E"} <= set(research["searched"])


def test_no_two_worked_examples_of_a_rule_give_the_same_facts():
    """#20 review round 2 (P3): a repeated example checks nothing new and shows twice in the rules workbook."""
    from rule_format.rulebook import REPO, load
    for r in load(REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-3a.yaml")["rules"]:
        givens = [tuple(sorted(e["given"].items())) for e in r.get("examples") or []]
        assert len(givens) == len(set(givens)), r["id"]

