"""host_core/left_out.py: which objects a check leaves out, decided once for every host (the Rhino command in its own
Python, the reference adapter and the Revit add-in through the worker's objects.left_out).

What must stay true (principle 4, never a false pass): an object with no box that covers all of it (no box given;
a block whose definition, at any depth, is missing, empty, linked to a file not known to be the design, or holds a
part with no box) is left out and counts as touching, never dropped; an object is told off the lot only by its
footprint; touching is its box within 0.1 ft of a building's, edges meeting included; a far object is never
outlined; and anything a host sends that isn't what the worker reads is refused, never guessed. The same answer
comes back in-process and as JSON through the worker.
"""
import io
import json

import pytest

from design_checker import protocol
from design_checker import rhino_logic as logic
from design_checker.__main__ import serve
from design_checker.host_core import left_out as lo

LOT = {"ring": [[0, 0], [60, 0], [60, 120], [0, 120]], "box": [0, 0, 60, 120]}
HOUSE = [15, 30, 0, 45, 80, 20]


def _square(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _obj(oid, box, **more):
    x0, y0, _, x1, y1, _ = box if box is not None else (0, 0, 0, 0, 0, 0)
    return dict({"id": oid, "box": box, "points": _square(x0, y0, x1, y1)}, **more)


SHED = [48, 90, 0, 56, 98, 8]                    # on the lot, apart from the house
AGAINST = [7, 40, 0, 15, 48, 8]                  # on the lot, against the house's west wall
FAR = [500, 0, 0, 510, 10, 8]


def _whole_def(*parts, status="NotALinkedInstanceDefinition"):
    return {"status": status, "parts": list(parts)}


# ---- no box that covers all of it --------------------------------------------------------------------------------

def test_a_block_whose_linked_file_is_not_known_at_any_depth_has_no_box():
    """A shed placed in a block placed in a block: the innermost linked file not found (or not readable, or changed
    since it was read) is no box for every block holding it, however whole the outer ones look."""
    defs = {"outer": _whole_def({"box": SHED, "definition": "middle"}),
            "middle": _whole_def({"box": SHED, "definition": "inner"}),
            "inner": _whole_def({"box": [52, 94, 4, 52, 94, 4]}, status="LinkedFileNotFound")}
    for status, why in [("LinkedFileNotFound", "contents_not_known"), ("LinkedFileNotReadable", "contents_not_known"),
                        ("LinkedFileIsNewer", "contents_not_known"), (None, "contents_not_known"),
                        ("LinkedFileIsUpToDate", None), ("NotALinkedInstanceDefinition", None)]:
        defs["inner"]["status"] = status
        got = lo.no_box_reasons([_obj("shed", SHED, definition="outer")], defs)
        assert got == [{"id": "shed", "why": why}], status


@pytest.mark.parametrize("seen, defs, why", [
    ({"box": None}, {}, "no_box"),                                          # the host gave none
    ({"box": [10, 0, 0, 9, 5, 5]}, {}, "no_box"),                           # low corner above the high one
    ({"box": SHED, "definition": None}, {}, "block_not_found"),             # a block with no definition
    ({"box": SHED, "definition": "gone"}, {}, "block_not_found"),           # not among those sent
    ({"box": SHED, "definition": "d"}, {"d": _whole_def()}, "block_empty"),
    ({"box": SHED, "definition": "d"}, {"d": _whole_def({"box": SHED}, {"box": None})}, "no_box"),   # a part
    ({"box": SHED, "definition": "d"}, {"d": _whole_def({"box": SHED}, {"box": SHED, "definition": None})},
     "block_not_found"),
    ({"box": [5, 5, 5, 5, 5, 5]}, {}, None),                                # a box of one point is a box
    ({"box": SHED, "definition": "d"}, {"d": _whole_def({"box": SHED})}, None)],
    ids=["null", "inverted", "no_definition", "unknown_definition", "empty", "part_without_box",
         "part_block_without_definition", "point", "whole"])
def test_why_an_object_has_no_box(seen, defs, why):
    assert lo.no_box_reasons([dict(seen, id="x")], defs) == [{"id": "x", "why": why}]


def test_blocks_nested_past_the_limit_have_no_box_and_each_definition_is_walked_once():
    defs = {f"d{k}": _whole_def({"box": SHED, "definition": f"d{k + 1}"}) for k in range(lo.MAX_BLOCK_DEPTH + 1)}
    defs[f"d{lo.MAX_BLOCK_DEPTH + 1}"] = _whole_def({"box": SHED})
    assert lo.no_box_reasons([_obj("deep", SHED, definition="d0")], defs)[0]["why"] == "block_not_found"
    assert lo.no_box_reasons([_obj("ok", SHED, definition="d1")], defs)[0]["why"] is None   # 32 deep: looked into
    walked = []

    class Counting(dict):
        def __getitem__(self, k):
            walked.append(k)
            return dict.__getitem__(self, k)
    many = Counting({"facade": _whole_def(*[{"box": SHED, "definition": "window"}] * 100), "window": _whole_def({"box": SHED})})
    got = lo.no_box_reasons([_obj(f"f{k}", SHED, definition="facade") for k in range(20)], many)
    assert all(g["why"] is None for g in got) and sorted(walked) == ["facade", "window"]


def test_a_block_nested_too_deep_has_no_box_whichever_object_is_sent_first():
    """Review round 4: each definition's answer was kept from the depth it was first met at, so a block placed 5
    deep into a chain 40 long had a box when a block placed higher up the same chain was sent first, and none when
    sent alone: the same model, two answers. Now the depth is counted at each placement."""
    defs = {f"D{k}": _whole_def({"box": SHED, "definition": f"D{k + 1}"}) for k in range(39)}
    defs["D39"] = _whole_def({"box": SHED})
    a, b = _obj("A", SHED, definition="D10"), _obj("B", SHED, definition="D5")
    for order in ([a, b], [b, a], [b]):
        got = {g["id"]: g["why"] for g in lo.no_box_reasons(order, defs)}
        assert got["B"] == "block_not_found", order
        assert got.get("A") is None, order                      # 30 blocks deep: looked into, whole
    on = {g["id"]: g["left_out"] for g in lo.left_out_decisions(LOT, [a, b], defs)}
    assert on == {"A": True, "B": True}
    assert [g["touching"] for g in lo.touching_decisions([a, b], [HOUSE], defs)] == [False, None]


def test_blocks_nested_too_deep_to_read_are_refused_never_answered():
    """Review round 5: a chain of blocks thousands deep (only a malformed request) ran out of Python's stack; it is
    refused with the worker's words (ValueError), never a crash read as an answer, here and through the protocol."""
    defs = {f"d{k}": _whole_def({"box": SHED, "definition": f"d{k + 1}"}) for k in range(5000)}
    defs["d5000"] = _whole_def({"box": SHED})
    deep = _obj("deep", SHED, definition="d0")
    with pytest.raises(ValueError, match="blocks nested too deep to read"):
        lo.no_box_reasons([deep], defs)
    with pytest.raises(ValueError, match="blocks nested too deep to read"):
        lo.touching_decisions([deep], [HOUSE], defs)
    reply = _served({"lot": LOT, "objects": [deep], "definitions": defs, "buildings": [HOUSE]})
    assert reply["result"] == {"refused": {k: "objects: blocks nested too deep to read"
                                           for k in ("left_out", "touching", "no_box")}}, reply


def test_a_block_holding_itself_is_not_found_never_a_hang():
    defs = {"loop": _whole_def({"box": SHED, "definition": "loop"})}
    assert lo.no_box_reasons([_obj("x", SHED, definition="loop")], defs)[0]["why"] == "block_not_found"


# ---- left out: on the lot, or no box to tell ----------------------------------------------------------------------

def test_an_object_with_no_box_is_left_out_wherever_its_points_are():
    far_points = _square(500, 0, 510, 10)
    objects = [dict(_obj("linked", SHED, definition="d"), points=far_points), dict(_obj("empty", None)),
               _obj("shed", SHED), _obj("far", FAR)]
    defs = {"d": _whole_def({"box": [500, 0, 0, 500, 0, 0]}, status="LinkedFileNotFound")}
    got = lo.left_out_decisions(LOT, objects, defs)
    assert [(g["id"], g["left_out"], g["why"]) for g in got] == [
        ("linked", True, "contents_not_known"), ("empty", True, "no_box"), ("shed", True, "on_lot"),
        ("far", False, "far_from_lot")]


def test_an_object_is_told_off_the_lot_by_its_footprint_and_a_far_one_is_never_outlined():
    asked = []

    def points(name, pts):
        return lambda: asked.append(name) or pts
    sloped = {"ring": [[0, 0], [60, 0], [60, 120], [0, 60]], "box": [0, 0, 60, 120]}
    objects = [{"id": "past_the_line", "box": [2, 100, 0, 12, 110, 8], "points": points("past", _square(2, 100, 12, 110))},
               {"id": "inside", "box": [2, 40, 0, 12, 50, 8], "points": points("inside", _square(2, 40, 12, 50))},
               {"id": "far", "box": FAR, "points": points("far", _square(500, 0, 510, 10))},
               {"id": "a_hair_over", "box": [-5, 10, 0, 0.05, 20, 8], "points": points("hair", _square(-5, 10, 0.05, 20))}]
    got = lo.left_out_decisions(sloped, objects)
    assert [(g["left_out"], g["why"]) for g in got] == [(False, "off_lot"), (True, "on_lot"), (False, "far_from_lot"),
                                                        (False, "off_lot")]
    assert asked == ["past", "inside", "hair"]                          # the far one: never outlined


def test_no_lot_leaves_nothing_out():
    assert lo.left_out_decisions(None, [_obj("shed", SHED), _obj("x", None)]) == [
        {"id": "shed", "left_out": False, "why": "no_lot"}, {"id": "x", "left_out": False, "why": "no_lot"}]


def test_the_reach_and_the_gap_are_in_feet_whatever_the_model_units():
    """In millimetres (0.00328084 ft each) the 0.1 ft reach is 30.48 mm: a fin 25 mm in is off the lot, 35 mm in on
    it; a shed 25 mm from the house touches it, 35 mm doesn't."""
    mm = 1 / 304.8
    lot = {"ring": _square(0, 0, 18000, 36000), "box": [0, 0, 18000, 36000]}
    fins = [{"id": f"in_{d}", "box": [-1000, 5000, 0, d, 5010, 2000], "points": _square(-1000, 5000, d, 5010)}
            for d in (25, 35)]
    assert [g["left_out"] for g in lo.left_out_decisions(lot, fins, feet_per_unit=mm)] == [False, True]
    house = [4500, 9000, 0, 13500, 24000, 6000]
    sheds = [{"id": f"gap_{d}", "box": [13500 + d, 9000, 0, 16000, 11000, 2400]} for d in (25, 35)]
    assert [g["touching"] for g in lo.touching_decisions(sheds, [house], feet_per_unit=mm)] == [True, False]


@pytest.mark.parametrize("ring", [[], [[0, 0], [60, 0]], [[0, 0], [30, 0], [60, 0]], [[0, 0], [60, 0], [0, 0], [60, 0]]],
                         ids=["empty", "two_points", "in_a_line", "back_and_forth"])
def test_a_lot_with_no_outline_is_refused_never_read_as_everything_off_it(ring):
    """Review round 1: a ring with no area made every object "off_lot", a shed in the middle too."""
    with pytest.raises(ValueError, match="lot: its ring is an outline"):
        lo.left_out_decisions({"ring": ring, "box": [0, 0, 60, 120]}, [_obj("shed", SHED)])


def test_a_lot_box_sent_too_small_grows_to_hold_the_ring():
    """Review round 1: a lot box smaller than its outline made a shed on the lot "far_from_lot", never outlined."""
    got = lo.left_out_decisions({"ring": LOT["ring"], "box": [0, 0, 1, 1]}, [_obj("shed", SHED), _obj("far", FAR)])
    assert [(g["left_out"], g["why"]) for g in got] == [(True, "on_lot"), (False, "far_from_lot")]


# ---- touching ----------------------------------------------------------------------------------------------------

def test_touching_is_a_box_within_a_tenth_of_a_foot_edges_meeting_included():
    objects = [_obj("against", AGAINST), _obj("gap_0.1", [7, 40, 0, 14.9, 48, 8]), _obj("gap_0.11", [7, 40, 0, 14.89, 48, 8]),
               _obj("above", [20, 40, 20.1, 30, 50, 25]), _obj("higher", [20, 40, 20.2, 30, 50, 25]),
               _obj("apart", SHED), _obj("no_box", None), _obj("empty_block", SHED, definition="d")]
    got = lo.touching_decisions(objects, [HOUSE, None], {"d": _whole_def()})
    assert [g["touching"] for g in got] == [True, True, False, True, False, False, None, None]


def test_with_no_building_box_nothing_with_a_box_touches():
    got = lo.touching_decisions([_obj("shed", SHED), _obj("x", None)], [None])
    assert [g["touching"] for g in got] == [False, None]


# ---- what a host sends is read exactly, or refused ---------------------------------------------------------------

@pytest.mark.parametrize("fn, kwargs", [
    (lo.no_box_reasons, {"objects": [{"id": "x", "box": SHED, "layer": "Default"}]}),          # a field not read
    (lo.no_box_reasons, {"objects": [{"id": "x", "box": [0, 0, 0, 1, 1]}]}),                  # 5 numbers
    (lo.no_box_reasons, {"objects": [{"id": "x", "box": [0, 0, 0, 1, 1, True]}]}),            # a yes, not a number
    (lo.no_box_reasons, {"objects": [{"id": "x", "box": [0, 0, 0, 1, 1, float("nan")]}]}),
    (lo.no_box_reasons, {"objects": [{"box": SHED}]}),                                         # no id
    (lo.no_box_reasons, {"objects": [_obj("x", SHED, definition="d")], "definitions": {"d": {"status": 1}}}),
    (lo.no_box_reasons, {"objects": [_obj("x", SHED, definition="d")],
                         "definitions": {"d": {"status": None, "parts": [], "linked": True}}}),
    (lo.left_out_decisions, {"lot": LOT, "objects": [{"id": "x", "box": SHED}]}),              # near: points needed
    (lo.left_out_decisions, {"lot": LOT, "objects": [{"id": "x", "box": SHED, "points": [[1, 2, 3]]}]}),
    (lo.left_out_decisions, {"lot": {"ring": LOT["ring"]}, "objects": []}),
    (lo.left_out_decisions, {"lot": LOT, "objects": [], "feet_per_unit": 0}),
    (lo.touching_decisions, {"objects": [], "buildings": [[0, 0, 0, 1, 1]]})],
    ids=["unread_field", "short_box", "bool", "nan", "no_id", "status_number", "definition_field",
         "near_without_points", "points_3d", "lot_without_box", "zero_units", "short_building_box"])
def test_anything_not_read_exactly_is_refused(fn, kwargs):
    with pytest.raises(ValueError):
        fn(**kwargs)


# ---- one copy: Rhino's names, and the worker's command -----------------------------------------------------------

def test_rhino_logic_offers_the_moved_geometry_as_the_same_objects():
    for name in ("reaches_into_lot", "box_near_lot", "block_contents_known", "ON_LOT_REACH", "BLOCK_CONTENTS_KNOWN",
                 "left_out_decisions", "touching_decisions", "no_box_reasons"):
        assert getattr(logic, name) is getattr(lo, name), name
    assert logic._inside is lo._inside and logic._ring_area is lo._ring_area


def _served(fields):
    out = io.StringIO()
    serve(io.StringIO(json.dumps({"id": 1, "cmd": "objects.left_out", "protocol": "1.1", **fields}) + "\n"), out)
    return json.loads(out.getvalue())


def test_the_worker_answers_what_the_functions_answer():
    defs = {"d": _whole_def({"box": [52, 94, 4, 52, 94, 4]}, status="LinkedFileNotFound")}
    objects = [_obj("linked", SHED, definition="d"), _obj("shed", SHED), _obj("against", AGAINST), _obj("far", FAR)]
    fields = {"lot": LOT, "objects": objects, "definitions": defs, "buildings": [HOUSE], "feet_per_unit": 1.0}
    reply = _served(fields)
    assert "error" not in reply, reply
    assert reply["result"] == {"left_out": lo.left_out_decisions(LOT, objects, defs, 1.0),
                               "touching": lo.touching_decisions(objects, [HOUSE], defs, 1.0),
                               "no_box": lo.no_box_reasons(objects, defs)}
    assert [g["left_out"] for g in reply["result"]["left_out"]] == [True, True, True, False]
    assert [g["touching"] for g in reply["result"]["touching"]] == [None, False, True, False]
    assert reply["result"]["no_box"][0]["why"] == "contents_not_known"


def test_the_worker_refuses_an_object_field_it_doesnt_read():
    reply = _served({"objects": [{"id": "x", "box": SHED, "category": "Walls"}]})
    assert reply["result"] == {"refused": {"no_box": "objects: an object has no field category (it has: id, box, "
                                                     "points, definition)"}}, reply


def test_a_1_0_request_is_still_answered():
    """Protocol 1.1 adds a command: a host that names 1.0 is still answered (a minor version)."""
    out = io.StringIO()
    serve(io.StringIO(json.dumps({"id": 1, "cmd": "objects.left_out", "protocol": "1.0",
                                  "objects": [_obj("x", None)]}) + "\n"), out)
    assert json.loads(out.getvalue())["result"]["no_box"] == [{"id": "x", "why": "no_box"}]
    assert protocol.PROTOCOL == "1.1"


# ---- what to tell the architect about a linked file (words only) ------------------------------------------------

@pytest.mark.parametrize("status, problem", [
    ("LinkedFileNotFound", "missing"), ("LinkedFileNotReadable", "unreadable"), ("LinkedFileIsNewer", "changed"),
    ("LinkedFileIsOlder", "changed"), ("LinkedFileIsDifferent", "changed"), (None, "not_known"),
    ("SomeStatusRhinoAddsLater", "not_known"),
    ("Rhino.DocObjects.InstanceDefinitionArchiveFileStatus.LinkedFileNotFound", "missing"),
    ("LinkedFileIsUpToDate", None), ("NotALinkedInstanceDefinition", None)])
def test_a_linked_file_problem_names_the_innermost_definition_whose_file_it_is(status, problem):
    """A shed placed in a block placed in a block, its innermost definition linked to a file: the problem names that
    innermost definition (the file to put right), not the outer blocks the architect placed, for each status that
    gives no box; a block whose contents are known has none."""
    defs = {"outer": _whole_def({"box": SHED, "definition": "middle"}),
            "middle": _whole_def({"box": SHED, "definition": "inner"}),
            "inner": _whole_def({"box": [52, 94, 4, 52, 94, 4]}, status=status)}
    got = lo.linked_file_problems([_obj("shed", SHED, definition="outer"), _obj("plain", SHED)], defs)
    assert got == [{"id": "shed", "definition": None if problem is None else "inner", "problem": problem},
                   {"id": "plain", "definition": None, "problem": None}]


def test_a_linked_file_problem_follows_the_part_that_decides_and_nothing_else():
    """The first part with no box decides why a block has none (no_box_reasons): a block holding an empty block
    before a linked one has no box because of the empty block, so no file is named; with the linked one first,
    it is. A block past the depth limit, or a definition that isn't there, names no file either."""
    linked = _whole_def({"box": SHED}, status="LinkedFileIsNewer")
    defs = {"empty_first": _whole_def({"box": SHED, "definition": "empty"}, {"box": SHED, "definition": "linked"}),
            "linked_first": _whole_def({"box": SHED, "definition": "linked"}, {"box": SHED, "definition": "empty"}),
            "empty": _whole_def(), "linked": linked}
    objects = [_obj("a", SHED, definition="empty_first"), _obj("b", SHED, definition="linked_first"),
               _obj("c", SHED, definition="gone")]
    assert [p["definition"] for p in lo.linked_file_problems(objects, defs)] == [None, "linked", None]
    assert [r["why"] for r in lo.no_box_reasons(objects, defs)] == ["block_empty", "contents_not_known",
                                                                    "block_not_found"]


def test_every_object_with_a_linked_file_problem_is_left_out_and_touching_and_no_other_is_named():
    """The words never stand in for the decision: each object linked_file_problems names is one no_box_reasons
    gives "contents_not_known", so left out and touching (None), and every such object is named."""
    defs = {"d": _whole_def({"box": [52, 94, 4, 52, 94, 4]}, status="LinkedFileNotFound"),
            "ok": _whole_def({"box": SHED}), "newer": _whole_def({"box": SHED}, status="LinkedFileIsNewer")}
    objects = [_obj("linked", SHED, definition="d"), _obj("whole", SHED, definition="ok"),
               _obj("against", AGAINST, definition="newer"), _obj("far", FAR)]
    named = [p["id"] for p in lo.linked_file_problems(objects, defs) if p["problem"]]
    assert named == [r["id"] for r in lo.no_box_reasons(objects, defs) if r["why"] == "contents_not_known"]
    assert named == ["linked", "against"]
    assert [t["touching"] for t in lo.touching_decisions(objects, [HOUSE], defs)] == [None, False, None, False]
    assert [d["left_out"] for d in lo.left_out_decisions(LOT, objects, defs)] == [True, True, True, False]


def test_the_words_say_the_file_the_problem_and_the_fix_with_the_host_s_own_menu_words():
    assert lo.linked_file_words("garage.3dm", "changed", "Edit > Blocks > Block Definitions, then Update") == (
        "Linked file 'garage.3dm' has changed since it was loaded: reload it (Edit > Blocks > Block Definitions, "
        "then Update) so Gordium can see where it is")
    assert lo.linked_file_words("garage.3dm", "missing", path="/Users/me/site/garage.3dm") == (
        "Linked file 'garage.3dm' can't be found at /Users/me/site/garage.3dm: relink it to where the file is now "
        "so Gordium can see where it is")
    assert lo.linked_file_words("garage.3dm", "changed", path="/Users/me/site/garage.3dm").startswith(
        "Linked file 'garage.3dm' has changed since it was loaded: reload it so")       # where only when not found
    with pytest.raises(ValueError, match="problem: one of"):
        lo.linked_file_words("garage.3dm", "on_lot")


def test_host_core_has_no_host_s_menu_words():
    """Where to click is the host's (Rhino: rhino_logic.LINK_HOW): host_core's words name no menu or command."""
    import inspect
    text = inspect.getsource(lo).split("# ---- what to tell the architect")[1]
    for word in ("Block Definitions", "BlockManager", "Edit \u25b8", "Manage Links", "Reload From"):
        assert word not in "".join(lo.LINK_WORDS.values()) + "".join(lo.LINK_FIX.values()), word
    for problem in lo.LINK_WORDS:                       # nor the sentence itself, without the host's words
        said = lo.linked_file_words("garage.3dm", problem, path="/site/garage.3dm")
        for word in ("Block Definitions", "BlockManager", "\u25b8", "Manage Links", "Reload From", "Rhino", "Revit"):
            assert word not in said, (problem, word)
    assert "Rhino's are in rhino_logic.LINK_HOW" in text


@pytest.mark.parametrize("path, name, shown", [
    ("/Users/me/site/garage.3dm", "Garage", "garage.3dm"), ("C:\\site\\garage.3dm", "Garage", "garage.3dm"),
    ("", "Garage", "Garage"), (None, "", "(no name)")])
def test_rhino_s_advice_names_the_file_by_its_own_name_and_says_where_to_click(path, name, shown):
    problems = [{"id": "g", "definition": "d", "problem": "missing"}, {"id": "s", "definition": None, "problem": None}]
    advice = logic.linked_file_advice(problems, {"d": (path or "", name)})
    assert list(advice) == ["g"]
    assert advice["g"].startswith("Linked file '%s' can't be found%s: relink it to where the file is now (Edit "
                                  "\u25b8 Blocks \u25b8 Block Definitions, select it, then Properties \u25b8 Filename: "
                                  "Browse to the file)" % (shown, " at " + path if path else ""))
    assert set(logic.LINK_HOW) == set(lo.LINK_WORDS)


def test_rhino_gives_no_advice_for_a_block_whose_status_couldn_t_be_read_and_has_no_file():
    """Review round 2: a block whose status Rhino couldn't give (None: "not_known") and which names no file may not
    be linked at all, so it isn't called a linked file; with a file, it is told to reload it."""
    problems = [{"id": "b", "definition": "d", "problem": "not_known"}]
    assert logic.linked_file_advice(problems, {"d": ("", "Garage")}) == {}
    assert logic.linked_file_advice(problems, {"d": ("/site/garage.3dm", "Garage")}) == {"b": (
        "Linked file 'garage.3dm' may have changed since it was loaded (Gordium can't tell whether it is up to "
        "date): reload it (Edit \u25b8 Blocks \u25b8 Block Definitions, select it, then Update) so Gordium can see "
        "where it is")}


def test_a_linked_block_with_no_box_of_its_own_still_names_its_file():
    """Review round 3: a placed linked block whose file can't be read and holds nothing has no box of its own, so
    its reason is "no_box" (the host gave none), and no file was named; its file is the one to put right, so it is
    named, directly or placed inside another block. An empty block that isn't linked names none."""
    defs = {"unreadable": _whole_def(status="LinkedFileNotReadable"),
            "holder": _whole_def({"box": None, "definition": "unreadable"}), "empty": _whole_def()}
    objects = [_obj("a", None, definition="unreadable"), _obj("b", SHED, definition="holder"),
               _obj("c", None, definition="empty"), _obj("d", None)]
    assert [r["why"] for r in lo.no_box_reasons(objects, defs)] == ["no_box", "no_box", "no_box", "no_box"]
    assert lo.linked_file_problems(objects, defs) == [
        {"id": "a", "definition": "unreadable", "problem": "unreadable"},
        {"id": "b", "definition": "unreadable", "problem": "unreadable"},
        {"id": "c", "definition": None, "problem": None}, {"id": "d", "definition": None, "problem": None}]
