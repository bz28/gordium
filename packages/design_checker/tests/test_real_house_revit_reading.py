"""The real house as a host reads it back once drawn (model_measurement.interior.recordings: the house placed by its
layout.yaml), checked against its hand-check (test_data/real_houses/<house>/hand_check.yaml).

A host's reader sends only what it can read from the drawing: the rooms (outline, floor, ceilings), every marked window
(no clear opening: the drawings give none), the doors (exit mark, operation; no clear opening), and each of house.yaml's
`has_none` claims the architect ticked (step 6: the drawing ticks them; the reader sends each back only while nothing
of the kind is drawn and nothing could hide one). The stairs and guards aren't drawn. So the full egress check on that
reading must:

  - give exactly what it gives on house.yaml for every rule, when every claim came back; a claim that didn't come back
    may only leave the rules it sets aside needing review (more cautious, never kinder);
  - never pass a rule whose hand-worked truth isn't complies (never a false pass).

The same holds for the host's recording itself, once one is committed (test_data/interior_houses/recorded/<host>/).
"""

from pathlib import Path

import pytest
import yaml

from design_checker import egress
import sys as _sys  # noqa: E402
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))   # egress_house beside this file
import egress_house  # noqa: E402
from model_measurement.interior import recordings

REPO = Path(__file__).parents[3]
ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
NAME = "orangetown_ny_80_south_william"
FOLDER = REPO / "test_data" / "real_houses" / NAME


@pytest.fixture(scope="module")
def found():
    return egress.laws(ITHACA)


def load(file):
    return yaml.safe_load((FOLDER / file).read_text(encoding="utf-8"))


def as_read(drawing: dict) -> dict:
    """The interior a host's reader sends for the drawing (in feet): what is drawn, nothing more."""
    return {"format": "gordium.interior/1", "units": "ft",
            "rooms": [{k: x[k] for k in ("id", "name", "sleeping", "floor", "floor_elevation", "ceilings")}
                      for x in drawing["rooms"]],
            "openings": [{k: w[k] for k in ("id", "name", "room", "escape", "operation")} for w in drawing["windows"]]
            + [{"id": d["id"], "name": d["name"], "room": d["room"], "escape": False,
                "operation": {"side_hinged": "side_hinged_door", "sliding": "sliding_door"}[d["operation"]]}
               for d in drawing["doors"]],
            "doors": [{k: d[k] for k in ("id", "name", "exit", "operation")} for d in drawing["doors"]],
            # the ticks the drawing sets that are claims (not empty lists), as the reader sends them back
            "has_none": [{"kind": k, "source": f"ticked by the architect ({k}: Yes, on Project Information)"}
                         for k in drawing["has_none"] if k not in recordings.NONE_LISTS]}


def readings() -> list:
    """The reader's view of the drawing, and each committed host recording of the house."""
    out = [("drawn", as_read(recordings.drawing(NAME)))]
    for host, by in recordings.recordings().items():
        if NAME in by:
            out.append((host, by[NAME]["interior"]))
    return out


def compare(found, interior):
    house, hand = load("house.yaml"), {r["id"]: r for r in load("hand_check.yaml")["rules"]}
    want = egress.check(found, house, {"dwelling_units": 1, **egress_house.HOUSE}, {"use": set()})
    got = egress.check(found, interior, {"dwelling_units": 1, **egress_house.HOUSE}, {"use": set()})
    set_aside = {k for i in want["items"] for k in (i.get("has_none") or {}).get("rules", [])}
    return want["results"], got["results"], set_aside, hand


def test_the_revit_recording_is_among_the_readings():
    # the committed Revit recording is checked here, never quietly dropped when missing
    assert [source for source, _ in readings()] == ["drawn", "revit"]


@pytest.mark.parametrize("source, interior", readings(), ids=lambda x: x if isinstance(x, str) else "")
def test_the_reading_checks_as_house_yaml_does_but_for_the_architects_claims(found, source, interior):
    want, got, set_aside, hand = compare(found, interior)
    assert set(got) == set(want) == set(hand)
    differ = {k for k in want if got[k] != want[k]}
    assert differ <= set_aside, sorted(differ - set_aside)
    assert all(want[k] == "not_applicable" and got[k] == "needs_review" for k in differ)
    claims = {c["kind"] for c in load("house.yaml")["has_none"]}
    if {c["kind"] for c in interior.get("has_none") or []} == claims:     # every claim came back: the same answers
        assert differ == set()
    # the rules the drawing does carry come out as the hand-check predicted: the front door side-hinged (pass), the
    # bedrooms' escape windows and the door's clear opening needs review (no clear opening is given)
    for k, v in got.items():
        if k not in set_aside:
            assert v == hand[k]["predicted"], k
    assert got["general.r318_2_egress_door_side_hinged"] == "pass"
    assert got["general.r319_2_1_escape_opening_min_net_clear_area"] == "needs_review"


@pytest.mark.parametrize("source, interior", readings(), ids=lambda x: x if isinstance(x, str) else "")
def test_the_reading_never_passes_what_the_hand_check_doesnt(found, source, interior):
    _, got, _, hand = compare(found, interior)
    assert [k for k, v in got.items() if v == "pass" and hand[k]["truth"] != "complies"] == []
    assert [k for k, v in got.items() if v == "not_applicable" and hand[k]["truth"] != "not_applicable"] == []


def test_a_reading_that_said_more_than_the_drawing_would_be_caught(found):
    # a reader that sent a made-up clear opening on the bedrooms' windows (none is on the drawings) would pass the
    # escape-window rules the hand-check leaves open: the comparison with house.yaml catches it
    interior = as_read(recordings.drawing(NAME))
    for o in interior["openings"]:
        if o["room"] in ("master", "bed2", "bed3", "bed4"):
            o["stated_clear"] = {"width": 32 / 12, "height": 26 / 12, "bottom": 27 / 12, "source": "made up"}
    want, got, set_aside, hand = compare(found, interior)
    passed = {k for k, v in got.items() if v == "pass" and hand[k]["truth"] != "complies"}
    assert "general.r319_2_2_escape_opening_min_net_clear_height" in passed          # both guards fire
    assert passed <= {k for k in want if got[k] != want[k]} - set_aside
