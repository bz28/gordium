"""Every word the checker sends an architect is plain: no back-quoted field name, no identifier with an underscore,
no "name = value" (an engineer's words, which showed in the Revit pane's cause cards and details before 2026-11-23).

What an architect sees is the answer's `view` (the panel's rows, cards, groups, details, header and summary) and its
`sections`; each string there is read here, except the fields that are data the host reads, never shows (DATA, each
with its reason). Over every committed golden answer (test_data/goldens/: zoning, every scenario, the deep-run
sites, the stress lots), and over the egress answers of every interior house, as drawn and with its stairs left out
(the goldens have no interior). Each wording is fixed where it is made (each_part.not_sent_words,
rule_format.parts.reading_words, present's TAG); the few made in code another branch is changing are listed in
NOT_YET, each with its reason, and only those."""

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
    "refused": "keys of the floors the stories measuring left out (\"below_floors\"); the Revit pane doesn't show them",
    "gordium": "on `open`: Gordium's gap key",
    "kinds": "on `open`: part kinds' keys",
    "part": "on `part`: the part's kind key",
    "rules": "on `has_none`: rule ids (on a cause, a count in words: a string checked where it is words)",
}
# words still made in code the NY building code branch (feat/ny-building-code-in-check) is changing: egress.py.
# Fixed once it lands; listed in the report of 2026-11-23 with the wording each would get.
NOT_YET = {
    egress.NOT_PER_PART: "egress.py: \"(no for_each)\"",
}
NOT_YET_PARTS = ("(The list: ",)        # egress.NOT_YET_WHY ends with the coverage file's path (egress.py)


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
    for top in ("view", "sections"):
        for where, text in _strings(answer.get(top), (top,)):
            if text in NOT_YET or any(p in text for p in NOT_YET_PARTS):
                continue
            for name, pat in (("back-quote", BACK_QUOTE), ("identifier", IDENTIFIER), ("name = value", NAME_IS_VALUE)):
                if m := pat.search(text):
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
                 "if Door = with"):
        assert problems({"view": {"items": [{"reason": text}]}}), text
    assert not problems({"view": {"items": [{"reason": "Allowed: 25% × lot area 7,200 sf = 1,800 sf",
                                             "rule": "R-1b.lot_coverage"}]}})


def test_no_golden_answer_shows_an_architect_an_engineers_word():
    _, answers = goldens.stored()
    found = [f"{case}: {p}" for case, value in answers.items() for a in _answers(value) for p in problems(a)]
    assert not found, "\n".join(found[:40])


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
