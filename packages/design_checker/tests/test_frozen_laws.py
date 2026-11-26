"""A check reads each state law's validation frozen (rule_format/published.py: compile, then freeze), never validating
it again: the frozen answer equals a live compile_law by value, for every law Ithaca inherits and for Maine through
its stand-in place (the Odyssey eval's), and the rules a check uses are exactly the rulebook the certificate is of.
"""

import json
import sys

import yaml

from rule_format import published
from rule_format.place import place, stand_in
from rule_format.rulebook import REPO, load

from design_checker import egress, present
from design_checker.check import check_site

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, box, lot  # noqa: E402

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
MAINE = REPO / "regulations/jurisdictions/maine/maine_state"


def _places():
    return [place(REPO / ITHACA), stand_in(MAINE, "Portland, ME (a stand-in)", ["maine/maine_state"])]


def test_the_frozen_validation_equals_a_live_compile_for_ithaca_and_for_maine_through_its_stand_in():
    seen = 0
    for p in _places():
        for folder, book in p.inherited_rulebooks():
            live = published.compile_law(folder, book)
            got = published.frozen(folder, book)
            assert live["problems"] == [] and {k: got[k] for k in live} == live, folder
            assert got["book"] == book.read_bytes()
            seen += 1
    assert seen == 3                                       # New York's two books and Maine's


def test_a_check_takes_the_frozen_answer_and_the_very_rulebook_it_is_of(monkeypatch):
    """egress.laws, for Ithaca and for the Maine stand-in (as the Odyssey eval runs it): each law's documents and kinds
    are a live compile's, and its rules are its rulebook's."""
    found = egress.laws(ITHACA)["laws"]
    stand = _places()[1]
    monkeypatch.setattr(egress, "place_of", lambda folder: stand)
    monkeypatch.setattr(egress, "refuse_state_alone", lambda j: None)
    found += egress.laws(MAINE)["laws"]
    assert len(found) == 3
    for law in found:
        live = published.compile_law(law["folder"], law["rulebook"])
        assert law["problems"] == [] and not law["unpublished"], law["key"]
        assert (law["documents"], law["kinds"]) == (live["documents"], live["kinds"]), law["key"]
        assert law["rules"] == load(law["rulebook"])["rules"] and law["rules"], law["key"]


def _cert(folder, book):
    return published.certificate_path(folder, book).read_bytes()


def test_a_missing_stale_unknown_or_unusable_certificate_gives_that_law_a_problem_and_no_rules(monkeypatch, tmp_path):
    """No live fallback (principle 4: never a false pass): a law whose certificate is missing, of another format,
    unreadable, stale or without a usable result gives a problem saying so and how to publish, and no rules, so every
    row of that law needs review. Never a crash."""
    folder, book = place(REPO / ITHACA).inherited_rulebooks()[0]
    real = json.loads(_cert(folder, book))
    path = tmp_path / "general.published.json"
    monkeypatch.setattr(published, "certificate_path", lambda f, b: path)
    stale_book = dict(real, book={**real["book"], "sha256": "0" * 64})
    stale_input = dict(real, inputs={**real["inputs"], f"{folder.relative_to(REPO).as_posix()}/state.yaml": "0" * 64})
    new_file = dict(real, inputs={k: v for k, v in real["inputs"].items() if not k.endswith("/state.yaml")})
    stale_code = dict(real, validator={**real["validator"], "packages/rule_format/rule_format/rulebook.py": "0" * 64})
    refused = dict(real, result={**real["result"], "problems": ["a quote isn't at its lines"]})
    no_kinds = dict(real, result={k: v for k, v in real["result"].items() if k != "kinds"})
    cases = {None: "no certificate at", b"{": "isn't readable JSON", b"[]": "isn't a gordium.published_law/1",
             json.dumps(dict(real, format="gordium.published_law/2")).encode(): "isn't a gordium.published_law/1",
             json.dumps(stale_book).encode(): "the rulebook changed",
             json.dumps(stale_input).encode(): "input changed:",
             json.dumps(new_file).encode(): "new file:",
             json.dumps(stale_code).encode(): "validator file changed: packages/rule_format/rule_format/rulebook.py",
             json.dumps(refused).encode(): "its law has a problem: a quote isn't at its lines",
             json.dumps(no_kinds).encode(): "holds no usable result",
             json.dumps({k: v for k, v in real.items() if k != "listed"}).encode(): "can't be read as"}
    for data, said in cases.items():
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(data)
        got = published.frozen(folder, book)
        assert got["book"] is None and got["documents"] == {} and got["kinds"] == {}, said
        assert len(got["problems"]) >= 1 and all("python -m rule_format publish" in w for w in got["problems"]), said
        assert any(said in w for w in got["problems"]), (said, got["problems"])
        law = egress.laws(ITHACA)["laws"][0]
        assert law["unpublished"] and law["rules"] == [] and law["problems"] == got["problems"], said


def test_a_check_with_a_stale_certificate_needs_review_for_that_law_and_says_why(monkeypatch, tmp_path):
    """The whole check: the Residential Code's certificate gone, every row of that law is one needs-review item that
    says the frozen copy can't be used, and nothing of it passes; zoning is still checked."""
    folder, book = place(REPO / ITHACA).inherited_rulebooks()[0]
    real = published.certificate_path
    monkeypatch.setattr(published, "certificate_path",
                        lambda f, b: tmp_path / "gone.json" if f == folder else real(f, b))
    site = {"units": "ft", "lot": lot([(0, 0), (60, 0), (60, 110), (0, 110)]),
            "buildings": [box(10, 25, 40, 75, 0, 30)], "problems": []}
    house = yaml.safe_load((REPO / "test_data/interior_houses/1_ranch_compliant/house.yaml").read_text(encoding="utf-8"))
    result = check_site(site, dict(FACTS), interior=house)
    mine = [i for i in result["view"]["items"] if i["group"] == present.LAW_GROUP]
    assert [(i["id"], i["status"]) for i in mine] == [("egress.rules", present.REVIEW)]
    assert "frozen copy can't be used" in mine[0]["reason"] and "no certificate at" in mine[0]["reason"]
    assert result["egress"]["results"] == {} and result["sections"][0]["key"] == "zoning"
    assert result["view"]["state"] != present.COMPLIES


def test_a_checks_rules_are_parsed_from_the_very_bytes_the_certificate_was_checked_against(monkeypatch):
    """Review round 1 of PR 3: nothing failed if the checker went back to reading the rulebook from disk after the
    certificate's check, so a rulebook saved in between could be checked against rules no one validated. Any later
    read of the rulebook here gives no rules: the check's rules still come from the bytes frozen() hashed."""
    from pathlib import Path
    folder, book = place(REPO / ITHACA).inherited_rulebooks()[0]
    real = egress.load
    monkeypatch.setattr(egress, "load", lambda p: {"rules": []} if Path(p) == Path(book) else real(p))
    law = egress.laws(ITHACA)["laws"][0]
    assert law["rules"] and law["rules"] == load(book)["rules"]
