"""Real houses (test_data/real_houses/): transcribed by hand from public drawings into the interior description.

For each house:
  - every value carries a citation (sheet and callout), every key the drawings can't fill is listed as absent with
    a reason, and nothing is both (the transcription invents nothing);
  - the citation keys don't change what is measured (the measuring code ignores them);
  - the measuring code's numbers and its reasons for no number equal the hand-worked expected.yaml (written before
    the code ran on the house);
  - the hand-worked answer key is complete, and where it says a rule needs review, the checker with a SYNTHETIC
    rule never passes it.
"""

import copy
from pathlib import Path

import pytest
import yaml

from design_checker import each_part
from model_measurement.interior import KINDS, measure, measure_file
from model_measurement.interior.openings import SLIDING
from model_measurement.interior.stops import STOPS

# parts.yaml measures the measuring code gives no value yet (#100): checked on main, not by this house
NOT_YET = {STOPS["not_measured_yet"], STOPS["in_more_not_rules"]}

REAL = Path(__file__).parents[3] / "test_data" / "real_houses"
NAMES = sorted(p.name for p in REAL.iterdir() if (p / "house.yaml").exists())
TEST_PARTS = Path(__file__).parents[2] / "rule_format" / "tests" / "test_parts.py"

# the format's keys for each list (docs/interior/interior_description_format.md)
FORMAT_KEYS = {
    "rooms": {"sleeping", "floor", "floor_elevation", "ceiling_height", "ceilings"},
    "openings": {"room", "escape", "operation", "frame", "sashes", "hinged", "stated_clear", "ground_outside",
                 "area_well"},
    "stairs": {"bottom_elevation", "nosings", "sides", "handrails", "overhead"},
    "doors": {"exit", "operation", "hinge_side", "stops", "hinge_pin", "leaf_closed", "threshold_top",
              "head_stop_bottom"},
    "guards": {"walking_surface", "top", "extent", "members", "stair", "top_line"},
}
NOT_VALUES = {"id", "name", "cite", "absent"}
# parts of the house the answer key works that the interior description has no entry for
UNDESCRIBED = {"main stair", "basement stair", "bridge steps", "hallways", "garage steps"}


def required(key, part):
    """The format keys a part must either give or list as absent with a reason: what measuring it reads."""
    if key == "rooms":
        return {"floor", "floor_elevation", "ceiling_height"} if part.get("sleeping") else set()
    if key == "openings":
        by_kind = {"casement": {"hinged"}, "side_hinged_door": {"hinged"}}
        sashes = {"sashes"} if part.get("operation") in SLIDING else set()      # only sliding ones read `sashes`
        return {"frame", "stated_clear", "ground_outside"} | by_kind.get(part.get("operation"), sashes)
    if key == "doors":
        return FORMAT_KEYS["doors"] - {"exit"}
    if key == "guards":
        return {"stair", "top_line", "members"} if "stair" in part else {"walking_surface", "top", "extent",
                                                                          "members"}
    return FORMAT_KEYS[key]
OUTCOMES = {"complies", "fails", "needs_review"}


def load(name, file):
    return yaml.safe_load((REAL / name / file).read_text(encoding="utf-8"))


def test_the_real_houses():
    assert NAMES == ["orangetown_ny_80_south_william"]


@pytest.mark.parametrize("name", NAMES)
def test_every_value_is_cited_and_every_gap_has_a_reason(name):
    house = load(name, "house.yaml")
    assert house["source"]["url"].startswith("https://") and len(house["source"]["sha256"]) == 64
    for key, allowed in FORMAT_KEYS.items():
        for part in house.get(key) or []:
            given = set(part) - NOT_VALUES
            cite, absent = part.get("cite") or {}, part.get("absent") or {}
            assert given <= allowed, (part["id"], given - allowed)
            assert given == set(cite), (part["id"], "cited but not given or given but not cited",
                                        given ^ set(cite))
            assert set(absent) <= allowed and not set(absent) & given, (part["id"], set(absent))
            missing = required(key, part) - given - set(absent)
            assert not missing, (part["id"], "neither given nor absent with a reason", missing)
            assert all(isinstance(v, str) and v.strip() for v in [*cite.values(), *absent.values()]), part["id"]


@pytest.mark.parametrize("name", NAMES)
def test_the_citations_change_nothing_measured(name):
    house = load(name, "house.yaml")
    bare = copy.deepcopy(house)
    bare.pop("source")
    for key in FORMAT_KEYS:
        for part in bare.get(key) or []:
            part.pop("cite", None)
            part.pop("absent", None)
    assert measure(bare) == measure(house)


@pytest.mark.parametrize("name", NAMES)
def test_each_measure_is_the_hand_worked_one(name):
    got = measure_file(REAL / name / "house.yaml")
    expected = load(name, "expected.yaml")
    not_read = set(expected.get("not_read", []))
    assert {k for k, v in got["parts"].items() if v is None} == not_read
    by_id = {}
    for kind in KINDS:
        if kind in not_read:
            continue
        want = expected["parts"].get(kind, {})
        parts = {p["id"]: p for p in got["parts"][kind]}
        by_id.update(parts)
        assert set(parts) == set(want), kind
        for pid, w in want.items():
            p = parts[pid]
            assert p.get("within") == w.get("within"), pid
            assert set(p["measures"]) == set(w["measures"]), pid
            for m, v in w["measures"].items():
                assert p["measures"][m] == pytest.approx(v, abs=1e-6), (pid, m)
            assert {m for m, why in p["not_measured"].items() if why not in NOT_YET} == set(w.get("not_measured", [])), pid
            assert set(p["more"]) == set(w.get("more") or {}), pid
            for m, v in (w.get("more") or {}).items():
                assert p["more"][m] == pytest.approx(v, abs=1e-6), (pid, m)
    reasons = expected["reasons"]                  # every measure not taken has its hand-worked reason
    assert {w.split("/")[0] for w in reasons} <= set(by_id)
    for pid, p in by_id.items():
        for m, reason in p["not_measured"].items():
            if reason in NOT_YET:
                continue
            assert reason == reasons.get(f"{pid}/{m}", reasons.get(pid)), (pid, m)
    assert got["problems"] == expected["problems"]
    assert [n["id"] for n in got["not_checked"]] == expected["not_checked"]


@pytest.mark.parametrize("name", NAMES)
def test_the_answer_key_is_worked_for_every_part(name):
    key, house = load(name, "answer_key.yaml"), load(name, "house.yaml")
    assert set(key["outcomes"]) == OUTCOMES
    ids = {p["id"] for k in FORMAT_KEYS for p in house.get(k) or []}
    for area in key["areas"]:
        assert area["outcome"] in OUTCOMES, area["id"]
        for field in ("rule", "quote", "working", "measured"):
            assert isinstance(area.get(field), str) and area[field].strip(), (area["id"], field)
        assert all(p in ids | UNDESCRIBED for p in area["parts"]), area["id"]
        if area["outcome"] != "needs_review":         # a reading rests on assumptions: never under a verdict
            assert "reading" not in area, area["id"]
    measured = measure_file(REAL / name / "house.yaml")
    got = measured["parts"]["emergency_escape_opening"] or []
    unsized = {p["id"] for p in got if not p["measures"]} | {n["id"] for n in measured["not_checked"]}
    sized_rooms = {o["room"] for o in house["openings"] if o["id"] in {p["id"] for p in got} - unsized}
    unsized |= {r["id"] for r in house["rooms"] if r["sleeping"]} - sized_rooms
    openings = {o["id"] for o in house["openings"]}
    for area in key["areas"]:   # a rule over an opening the code can't size, or an escape rule over its room, never complies
        never = unsized & openings | (unsized if "R319" in area["rule"] else set())
        assert not (set(area["parts"]) & never and area["outcome"] == "complies"), area["id"]
    worked = {p for a in key["areas"] for p in a["parts"]}
    escape = {o["id"] for o in house["openings"] if o["escape"]}
    assert escape <= worked                       # every marked escape opening is worked in the key
    assert {r["id"] for r in house["rooms"] if r["sleeping"]} <= worked


def _synthetic_area_rule():
    import importlib.util
    spec = importlib.util.spec_from_file_location("synthetic_parts", TEST_PARTS)
    synthetic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(synthetic)
    return synthetic.AREA, synthetic.ALLOWED


@pytest.mark.parametrize("name", NAMES)
def test_an_escape_opening_the_drawings_dont_size_never_passes(name):
    """End to end with a SYNTHETIC rule (5.7 sf / 24 in, never the code's own text): the drawings give no clear
    opening for any bedroom window, so the checker must say needs review, as the hand answer key does."""
    area, allowed = _synthetic_area_rule()
    got = measure_file(REAL / name / "house.yaml")
    checked = each_part.check_parts([copy.deepcopy(area)], got["parts"], {"use": "one_family_detached"}, allowed)
    outcomes = {r["outcome"] for r in checked["rows"]}
    assert outcomes == {"needs_review"}
    assert checked["results"] == {area["id"]: "needs_review"}
    key = {a["id"]: a["outcome"] for a in load(name, "answer_key.yaml")["areas"]}
    assert key["escape_opening_area"] == "needs_review"
