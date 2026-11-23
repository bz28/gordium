"""Every word the checker sends an architect is plain: no back-quoted field name, no identifier with an underscore,
no "name = value" (an engineer's words, which showed in the Revit pane's cause cards and details before 2026-11-23).

What an architect sees is the answer's `view` (the panel's rows, cards, groups, details, header and summary), its
`sections` and its `which_code` (the line saying which NY code governs); each string there is read here, except the
fields that are data the host reads, never shows (DATA, each with its reason). Over every committed golden answer
(test_data/goldens/: zoning, every scenario, the deep-run sites, the stress lots), and over the egress answers of
every interior house, as drawn and with its stairs left out (the goldens have no interior). Each wording is fixed
where it is made (each_part.not_sent_words, code_scope's use in words,
rule_format.parts.reading_words, present.tag_pattern, egress.NOT_PER_PART and NOT_YET_WHY); any let through on
purpose would be listed in NOT_YET with its reason (none are)."""

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

from design_checker import egress, goldens
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))

BACK_QUOTE = re.compile(r"`")
IDENTIFIER = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
NAME_IS_VALUE = re.compile(r"\b[A-Za-z_]\w*\s=\s[A-Za-z_\"']")
SECTION_TAG = re.compile(r"\(\d{3}-\d+[A-Z]?(?:#\d+)?\)")       # a law question's bare key: "(325-28C#1)"
PYTHON_WORD = re.compile(r"\b(?:None|True|False)\b")               # a value said as code says it, not "blank", "Yes"
# the architect's own words, quoted exactly as typed (code_scope.value_words: “nfpa_13x”): never Gordium's to change
QUOTED = re.compile(r"“[^”]*”")

# the fields of `view` and `sections` that are data, never words shown (the host keys, finds or links by them)
DATA = {
    "id": "a row's, room's or part's id",
    "key": "the key rows sharing a cause or group share",
    "kind": "a cause's or part's kind, which picks the card's button",
    "field": "the mark's description field (\"facts.zone\"), which picks the mark",
    "fields": "the same, every one",
    "needs": "the measures or facts a row needs, which the start box asks for by their own words",
    "measure": "the measure's name, which the host matches",
    "questions": "the open questions' tags a card decides (its words name them)",
    "items": "the row ids a group or card holds (view.items, the rows themselves, is read)",
    "elements": "the element ids a card highlights",
    "objects": "the model's objects a row zooms to",
    "rule": "the rule id",
    "group": "the group a row is in",
    "mark": "the status glyph",
    "colour": "the colour a status shades",
    "status": "a status word the host reads",
    "state": "a state word the host reads",
    "sign": "a delta's sign",
    "margin": "a number",
    "approx": "a flag",
    "zoom": "the view a row zooms to",
    "tier": "a group line's tier the host sorts by",
    "law_key": "the law's folder",
    "_turns_on": "the measures a row's result turns on",
    "cited": "citations with their links (the citation text is `citation`, checked)",
    "links": "web or file addresses",
    "sources": "the source file a quote is from",
    "quotes": "the law's exact words, never Gordium's",
    "code": "on an item: the law's exact words and section",
    "outline": "plan points",
    "stop": "a room's stop key (its words are `why`, checked)",
    "unit": "a unit key",
    "facts": "on code_scope: the lot facts the code choice read, as their keys and stored values (never shown)",
    "refused": "keys of the floors the stories measuring left out (\"below_floors\"); the Revit pane doesn't show them",
    "gordium": "on `open`: Gordium's gap key",
    "kinds": "on `open`: part kinds' keys",
    "part": "on `part`: the part's kind key",
    "rules": "on `has_none`: rule ids (on a cause, a count in words: a string checked where it is words)",
}
# words let through on purpose, each with its reason: none (egress.py's two, deferred while the NY building code
# branch changed it, were made plain once it merged, 2026-11-23)
NOT_YET: dict = {}
NOT_YET_PARTS: tuple = ()


def _strings(x, path=()):
    """(path, text) of every string an architect may see under x."""
    if isinstance(x, dict):
        for k, v in x.items():
            rows = k == "items" and isinstance(v, list) and any(isinstance(e, dict) for e in v)    # view.items: rows
            if k in DATA and not rows and not (k == "rules" and isinstance(v, str)):
                continue
            yield from _strings(v, path + (k,))
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v, path)
    elif isinstance(x, str):
        yield ".".join(path), x


def problems(answer: dict) -> list[str]:
    out = []
    for top in ("view", "sections", "which_code"):
        for where, text in _strings(answer.get(top), (top,)):
            if text in NOT_YET or any(p in text for p in NOT_YET_PARTS):
                continue
            ours = QUOTED.sub("“…”", text)
            for name, pat in (("back-quote", BACK_QUOTE), ("identifier", IDENTIFIER), ("name = value", NAME_IS_VALUE),
                              ("section tag", SECTION_TAG), ("code value", PYTHON_WORD)):
                if m := pat.search(ours):
                    out.append(f"{where}: {name} {m.group(0)!r} in {text[:160]!r}")
    return out


def _answers(value):
    """Every check answer in a golden (a stress case holds its check's under "check")."""
    if isinstance(value, dict):
        if "view" in value:
            yield value
        for v in value.values():
            if isinstance(v, dict):
                yield from _answers(v)


def test_the_pin_finds_each_kind_of_engineers_word():
    for text in ("the stairs aren't in the interior drawing (no `stairs` list)", "complies if door_ends_dead_end",
                 "if Door = with", "the primary front yard is open (325-28C#1)"):
        assert problems({"view": {"items": [{"reason": text}]}}), text
    assert not problems({"view": {"items": [{"reason": "Allowed: 25% × lot area 7,200 sf = 1,800 sf",
                                             "rule": "R-1b.lot_coverage"}]}})


def test_the_egress_law_s_own_rows_are_in_plain_words():
    """Two of the law's own rows: a rule not written part by part, and the sections not checked yet (no file path)."""
    assert egress.NOT_PER_PART == ("this rule isn't written to be checked part by part (each room, door or stair), "
                                   "and a state law's rules are checked only that way: it isn't checked, so check it "
                                   "by hand")
    assert "{file}" not in egress.NOT_YET_WHY and "(The list" not in egress.NOT_YET_WHY
    assert egress.NOT_YET_WHY.endswith("Check each by hand: {all}.")


def test_which_code_says_the_use_in_words():
    from design_checker import code_scope
    assert code_scope.decide({"use": "retail_store_or_service_commercial"}, None)["why"] == (
        "its use (retail store or service commercial) is none of the dwellings R101.2 lists (101.2: every other "
        "building)")


def test_every_code_choice_says_itself_in_plain_words():
    """Not only the goldens' few: decide() over test_code_scope_property's walk of every fact it reads (every path
    it returns by), the first case of each different answer and every 100th besides, a few thousand; and the
    building block's own mistakes, which the walk doesn't make (a fact Gordium doesn't read, values of the wrong
    kind). Each answer as the pane shows it: which_code, and the egress law's line made from it (SCOPE_OPEN_WHY,
    SCOPE_WHY)."""
    from design_checker import code_scope
    from test_code_scope_property import decided, walk

    def shown(got):
        cites = ", ".join(c["section"] for c in got["cites"])
        line = (egress.SCOPE_OPEN_WHY.format(why=got["why"], cites=cites, ask=got["ask"]) if got["code"] is None
                else egress.SCOPE_WHY.format(book=got["title"], why=got["why"], cites=cites))
        return {"which_code": got, "view": {"items": [{"reason": line}]}}

    answers, shapes = [], set()
    for i, f in enumerate(walk()):
        got = decided(f)
        shape = re.sub(r"\d+", "N", got["why"])
        if shape not in shapes or i % 100 == 0:
            shapes.add(shape)
            answers.append(got)
    odd = {"stories_abvoe": 3, "sprinkler_system": "nfpa_13x", "occupancy_groups": ["R_3"], "townhouse_units": "no"}
    for building in ({k: v} for k, v in odd.items()):
        answers.append(code_scope.decide({"use": "one_family_detached", "dwelling_units": "two_units"}, building))
        answers.append(code_scope.decide({"use": "multiple_family", "stories": "three_up"}, building))
    answers.append(code_scope.decide({"use": "one_family_detached"}, ["not", "a_mapping"]))
    assert len(answers) > 3000 and len(shapes) > 50
    found = [p for got in answers for p in problems(shown(got))]
    assert not found, f"{len(found)} problems, e.g.\n" + "\n".join(found[:10])
    assert code_scope.use_words("one_family_detached") == "a detached one-family dwelling"


def test_the_code_choice_quotes_the_architects_value_as_typed_and_says_blank_yes_and_no():
    """Review round 4: a value Gordium can't read is the architect's own, quoted verbatim (the character that made it
    unreadable kept, as the add-in quotes it); blank, Yes and No never None, True or False; the facts Gordium reads
    named by their marks only (no host-only fact, no key); a use the facts disagree with named as the architect chose
    it, R101.2's "two-family dwelling" kept for the verdict lines."""
    from design_checker import code_scope
    why = code_scope.decide({"use": "one_family_detached"}, {"sprinkler_system": "nfpa_13x"})["why"]
    assert why == "the building's sprinkler system is “nfpa_13x”, which Gordium can't read"
    assert "[“R_3”]" in code_scope.decide({"use": "two_family"}, {"occupancy_groups": ["R_3"]})["why"]
    assert [code_scope.value_words(v) for v in (None, True, False, 3, ["R_3", None])] == [
        "blank", "Yes", "No", "3", "[“R_3”, blank]"]
    unknown = code_scope.decide({"use": "two_family"}, {"stories_abvoe": 3})["why"]
    assert unknown.startswith("the building block sends “stories_abvoe”, which is no fact Gordium reads (it reads "
                              "Gordium: Stories above grade plane, ")
    assert "Gordium: Sprinkler system" in unknown and "facts not sent" not in unknown and "atrium" not in unknown
    assert code_scope.decide({"use": "one_family_semi_detached", "dwelling_units": 2}, None)["why"] == (
        "the use is a one-family semi-detached dwelling (one of a pair, 1 dwelling unit on the lot) but 2 dwelling "
        "units are stated")
    semi = code_scope.decide({"use": "one_family_semi_detached", "dwelling_units": 1, "accessory_dwelling_unit": False,
                              "separate_means_of_egress": True, "stories": 2}, {"stories_above_grade_plane": 2})
    assert "a two-family dwelling (two semi-detached units in one building)" in semi["why"]      # the law's term
    for text in ("is None", "a value True here"):
        assert problems({"view": {"items": [{"reason": text}]}}), text
    assert not problems({"view": {"items": [{"reason": "the sprinkler system is “nfpa_13x”"}]}})


def test_no_golden_answer_shows_an_architect_an_engineers_word():
    _, answers = goldens.stored()
    found = [f"{case}: {p}" for case, value in answers.items() for a in _answers(value) for p in problems(a)]
    assert not found, "\n".join(found[:40])


def test_an_adu_on_a_corner_lot_shows_no_engineers_word():
    """No golden has a detached ADU on a corner lot, whose primary front yard is a law question ("(325-28C#1)",
    model_measurement's PRIMARY_QUESTION). A made-up one where the readings split: test_adu_measure's 50 x 100 ft
    corner lot (South St along y = 0, East St along x = 50), the house 0..12 x 30..60 (38 ft from East St), the ADU
    14..24 x 70..85: behind the house from South St (not in that front yard), nearer East St than the house (26 ft:
    in that one, yet clear of its 25 ft required yard). So which street is primary decides it: needs review, the
    question in its reason, in plain words."""
    from design_checker import present
    from design_checker.check import check_site
    from model_measurement.places.ithaca_city.measure import PRIMARY_QUESTION
    from test_adu_panel import ADU_FACTS
    from test_measure import RECT, box
    assert "(325-28C#1)" in PRIMARY_QUESTION and "(325-28C#1)" not in present._user_text(PRIMARY_QUESTION)
    corner = {"corner_lot": True, "street_line": [[[0, 0], [50, 0]], [[50, 0], [50, 100]]],
              "street_ids": ["South St", "East St"], "address_street_line": [[[0, 0], [50, 0]]], "adu_building": "adu"}
    buildings = [box(0, 30, 12, 60, id="house"), box(14, 70, 24, 85, 0, 18, id="adu")]
    answer = check_site({"units": "ft", "lot": RECT, "buildings": buildings, "problems": []}, {**ADU_FACTS, **corner})
    assert "(325-28C#1)" in answer["measurements"]["adu_in_primary_front_yard"]["reason"]
    row, = [i for i in answer["view"]["items"] if i["name"].startswith("Detached ADU: not in the primary front yard")]
    assert row["status"] == present.REVIEW
    assert row["reason"] == ("the readings give different values; which front yard is the primary front yard on a "
                             "corner lot isn't settled yet: confirm with the zoning office")
    assert not problems(answer), "\n".join(problems(answer)[:20])


def _houses():
    out = {p.parent.name: p for p in sorted((REPO / "test_data/interior_houses").glob("*/house.yaml"))}
    out.update({p.parent.name: p for p in sorted((REPO / "test_data/real_houses").glob("*/house.yaml"))})
    return out


@pytest.mark.parametrize("name", sorted(_houses()))
def test_no_egress_answer_shows_an_architect_an_engineers_word(name):
    from test_worker_interior import worker_check
    house = yaml.safe_load(_houses()[name].read_text(encoding="utf-8"))
    without = {k: v for k, v in house.items() if k != "stairs"}
    for interior in (house, without):
        result = json.loads(json.dumps(worker_check(interior=interior)))
        assert not problems(result), "\n".join(problems(result)[:40])


def test_a_list_left_out_is_said_in_plain_words():
    from test_worker_interior import worker_check
    ranch = REPO / "test_data/interior_houses/1_ranch_compliant/house.yaml"
    house = yaml.safe_load(ranch.read_text(encoding="utf-8"))
    result = worker_check(interior={k: v for k, v in house.items() if k != "stairs"})
    words = {c["words"] for i in result["view"]["items"] for c in i.get("causes") or []}
    assert "the stairs weren't sent from the model" in words
    titles = [ln["title"] for g in result["view"]["groups"] for ln in g.get("lines") or []]
    assert any(t.startswith("Stairs: ") and t.endswith(": to give: the stairs weren't sent from the model")
               for t in titles), titles
