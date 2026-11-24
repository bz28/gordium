"""stops.code_of reads a measuring reason's words back into its key and blanks: for every reason in stops.STOPS,
stop(key, **blanks) read back gives that key and those blanks; words no reason gives, or two reasons give equally,
are refused, never guessed (the site description names every problem by its key: design_checker/site_json.py)."""

import pytest

from model_measurement import stops
from model_measurement.stops import STOPS, blanks, code_of, stop

# blanks as they are really filled (a layer's name, a count, a sentence), so the round trip is tried on real words
REAL = {"layer": "Site", "count": "2", "units": "UnitSystem.Miles", "path": "/tmp/a model.3dm", "what": "Garage (Block)",
        "kind": "a Surface", "id": "c41249d7-712a-44c1-b8ba-5dfae9ad3d7d", "question": "is the porch part of it?",
        "why": "edges 2 and 4 cross", "turn": "92", "limit": "12", "ground": "100.5", "bottom": "99", "top": "125",
        "off": "1", "bare": "2", "fall": "3.5", "typed": "1", "drawn": "2", "low": "10", "high": "12", "height": "30",
        "most": "4", "here": "2", "building": "3", "occupants": "5", "units_": "x", "unit_words": "units",
        "held": "4", "check": "the occupants", "with_": "2", "without": "3", "distance": "15", "reading": "eave_a",
        "entry": "eave.yaml", "reason": "no roof faces"}


@pytest.mark.parametrize("key", sorted(set(STOPS) - {stops.TOOL_WORDS}))
def test_every_reason_reads_back_as_itself(key):
    for fill in ({b: REAL.get(b, "some words") for b in blanks(key)}, {b: f"<{b}>" for b in blanks(key)}):
        words = stop(key, **fill)
        assert code_of(words) == (key, fill)
        assert stop(*[code_of(words)[0]], **code_of(words)[1]) == words


def test_the_reasons_one_could_also_give_read_as_the_one_with_more_fixed_words():
    # "no {layer} layer" could give both, with a long layer name: the reason meant is the more specific one
    assert code_of("no closed lot outline on the Site layer") == ("no_lot_outline", {"layer": "Site"})
    assert code_of("no building on the Building layer") == ("no_building", {})
    assert code_of("no Site layer") == ("no_lot_layer", {"layer": "Site"})


def test_words_no_reason_gives_are_refused():
    for words in ("", "a block (Garage)", "a building has a curved surface", "a building has a curved surface (not "
                  "measured yet) ", "A building has a curved surface (not measured yet)"):
        with pytest.raises(ValueError, match="no measuring reason gives"):
            code_of(words)


def test_two_reasons_giving_the_words_equally_are_refused(monkeypatch):
    patterns = dict(stops.PATTERNS, twin=stops._pattern("no {layer} layer"))
    monkeypatch.setitem(STOPS, "twin", "no {layer} layer")
    monkeypatch.setattr(stops, "PATTERNS", patterns)
    with pytest.raises(ValueError, match="more than one measuring reason .*no_lot_layer, twin|twin, no_lot_layer"):
        code_of("no Site layer")


def test_the_design_tools_own_words_are_never_read_back_from_words():
    # "{words}" fits any words: read back, every unknown sentence would become it, so only its code ever sends it
    assert stop(stops.TOOL_WORDS, words="a block (Garage)") == "a block (Garage)"
    with pytest.raises(ValueError, match="no measuring reason gives"):
        code_of("a block (Garage)")
    assert stops.TOOL_WORDS not in stops.PATTERNS


# ---- words_of: THE one way a problem becomes words (stops.py) ---------------------------------------------------

def test_words_of_says_every_kind_of_problem_in_words_and_never_raises():
    from model_measurement.stops import said, words_of
    assert words_of("no lot outline") == "no lot outline"
    assert words_of({"code": "no_lot_outline", "args": {"layer": "Site"}}) == stop("no_lot_outline", layer="Site")
    assert words_of({"code": "tool_words", "args": {"words": "a block (Garage)"}}) == "a block (Garage)"
    for bad in ({"code": "not_a_reason", "args": {}}, {"code": "no_lot_outline", "args": {}},
                {"code": "no_lot_outline", "args": {"layer": "Site", "more": 1}}, {"code": "no_lot_outline"},
                {"code": "no_lot_outline", "args": {"layer": ["Site"]}}, 42, None, ["no lot"], {1, 2}):
        assert words_of(bad).startswith("a problem sent with the drawing can't be read ("), bad
    assert said(["no lot outline", {"code": "no_lot", "args": {}}]) == "no lot outline; no lot outline"
