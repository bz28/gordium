"""The words an architect reads in the results panel (the interior and route measuring's reasons), in plain words:
no field of Gordium's file format in back-quotes ("`exit`: true or false", "no `stairs` in the description"), no
raw coordinates ("the point (55.308, 78.082)"), no exit's id: the elements by their own names (a door by its name,
a room by its name and number). The field a reason asks the architect to state is data (interior.asked_field), never
words. Only the words change: every reason still stops the measure it stopped (never a verdict changed)."""

import re
import sys
from pathlib import Path

import pytest

from model_measurement.interior import KINDS, asked_field, measure
from model_measurement.interior.stops import STOPS as INTERIOR_STOPS
from model_measurement.interior.stops import Stop
from model_measurement.routes.stops import STOPS as ROUTE_STOPS

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from test_interior_measures import base  # noqa: E402

COORDINATES = re.compile(r"\{x\}|\{y\}|\(-?\d+(?:\.\d+)?, -?\d+(?:\.\d+)?\)")


@pytest.mark.parametrize("table,key", [("interior", k) for k in INTERIOR_STOPS] + [("routes", k) for k in ROUTE_STOPS])
def test_no_reason_names_a_file_field_in_back_quotes_or_a_point_by_its_coordinates(table, key):
    words = (INTERIOR_STOPS if table == "interior" else ROUTE_STOPS)[key]
    assert "`" not in words, key
    assert not COORDINATES.search(words), key
    assert "the description has" not in words and "in the description" not in words, key


@pytest.mark.parametrize("kind", [k for k, v in KINDS.items() if v[2]])
def test_an_entry_without_its_flag_names_the_field_to_state_and_says_it_plainly(kind):
    key, words, flag, question = KINDS[kind]
    d = base()
    entries = d.get(key) or []
    assert entries, key
    del entries[0][flag]
    got = measure(d)
    problem, = [p for p in got["problems"] if question in p]
    assert "`" not in problem and "true or false" not in problem
    assert problem.endswith(f"doesn't say whether it is {question} (yes or no)")
    assert asked_field(problem) == f"{key}[].{flag}"


@pytest.mark.parametrize("kind", list(KINDS))
def test_a_list_not_given_names_its_field(kind):
    key = KINDS[kind][0]
    d = base()
    d.pop(key, None)
    problem, = [p for p in measure(d)["problems"] if p.startswith(f"the {KINDS[kind][1]} weren't read")]
    assert asked_field(problem) == key
    assert "`" not in problem


@pytest.mark.parametrize("words", [
    "", "door D2 is marked twice", "the doors sent from the model can't be read (they aren't a list)",
    # a flag's words with nothing where the name is: no entry named, so no field
    Stop("flag_missing", what="door", question="it is the required exit door").reason,
    # a question the kind doesn't ask
    Stop("flag_missing", what="door D1", question="it is a sleeping room").reason, None, 3])
def test_any_other_words_name_no_field(words):
    assert asked_field(words) is None


def test_the_name_may_hold_anything_the_host_names_an_element_by():
    name = 'Single-Flush: Door 36" x 84" (LS1.0) (D01)'
    words = Stop("flag_missing", what=f"door {name}", question="it is the required exit door").reason
    assert words == f"door {name} doesn't say whether it is the required exit door (yes or no)"
    assert asked_field(words) == "doors[].exit"


# ---- review round 1: the reasons as the measuring gives them, not only the table's words --------------------------

def test_a_window_waiting_on_the_makers_size_names_every_part_of_it_it_needs():
    """A window's maker's clear opening needs its bottom too (Revit: Gordium: Clear offset), never only a door's three."""
    words = Stop("operation_needs_clear", n="n", operation="awning").reason
    assert "bottom" in words and "width" in words and "height" in words and "source" in words
    d = base()
    d["openings"][0].update(operation="awning", stated_clear="big")
    d["openings"][0].pop("frame", None)
    why = measure(d)["parts"]["emergency_escape_opening"][0]["not_measured"]["opening_net_clear_area"]
    assert "its clear width, height, bottom and source" in why


@pytest.mark.parametrize("kind", ["stairs", "guards", "rooms"])
def test_a_list_not_given_never_calls_the_building_a_house(kind):
    """The Children's Odyssey is a day care: "all of the house's stairs" wasn't true of it."""
    words = Stop("not_read", what=kind, key=kind).reason
    assert "house" not in words and words.endswith(f"the model doesn't say these are all the {kind} (or that there "
                                                   "are none)")


def _claims(*entries, **lists):
    d = base()
    d["has_none"] = list(entries)
    d.update(lists)
    return d


@pytest.mark.parametrize("entries, lists, words", [
    # a kind with a list of its own, the list not given: never said to be given
    ([{"kind": "stair", "source": "A-2"}], {}, "the model says the house has no stairs, but stairs have a list of "
                                               "their own in the model"),
    ([{"kind": "emergency_escape_opening", "source": "A-2"}], {}, "has no emergency escape openings, but openings"),
    # more than an entry has: said as more, never "values it doesn't know"
    ([{"kind": "ramp", "source": "A-2", "reding": True}], {}, "giving more than a kind, a source and, optionally, a "
                                                             "reading (also reding)"),
    # the text "yes" is no yes/no value: said so, never "isn't yes or no" of a "yes"
    ([{"kind": "ramp", "source": "A-2", "reading": "yes"}], {}, "gives whether that rests on a reading of the law as the text 'yes', not as a yes/no value"),
])
def test_a_claim_not_taken_says_why_truly_and_plainly(entries, lists, words):
    got = measure(_claims(*entries, **lists))
    said = [p for p in got["problems"] if words in p]
    assert said, got["problems"]
    assert all("`" not in p and "_" not in p for p in said), said


def test_the_door_makers_size_with_more_than_it_has_says_so():
    d = base()
    d["doors"][0]["stated_clear"] = {"width": 34, "height": 80, "source": "maker", "bottom": 0}
    m = measure(d)["parts"]["egress_door"][0]["not_measured"]
    assert "gives more than its width, height and source (also bottom)" in m["door_clear_width"]


def test_route_reasons_as_read_have_no_back_quotes_underscored_fields_or_coordinates():
    """The reasons the route reading gives for a description it can't read, as it gives them: the levels not a
    list, a room with no id, a list that isn't of entries, a story outline on no level given, a not-occupied mark
    given as text, obstructions not a list."""
    from model_measurement.routes import measure as routes_measure
    from model_measurement.routes.floor import read
    from routes_layouts import room_on_corridor
    cases = []
    d = room_on_corridor()
    d["levels"] = "x"
    cases.append(d)
    d = room_on_corridor()
    del d["rooms"][0]["id"]
    cases.append(d)
    d = room_on_corridor()
    d["passages"] = [1]
    cases.append(d)
    d = room_on_corridor()
    d["story_outlines"] = [{"level": "nowhere", "outer": [], "inner": []}]
    cases.append(d)
    d = room_on_corridor()
    d["rooms"][0]["not_occupied"] = "yes"
    cases.append(d)
    d = room_on_corridor()
    d["rooms"][0]["obstructions"] = "a desk"
    cases.append(d)
    d = room_on_corridor()                 # a corridor's stated facts given wrongly: said by their marks, never keys
    corridor = next(r for r in d["rooms"] if r.get("use") == "corridor")
    corridor.update(fire_rating_hours="1 HR", walls_smoke_partitions="yes")
    cases.append(d)
    said = []
    for d in cases:
        floor = read(d)
        said += list(floor.stops) + [r for s in floor.stories.values() for r in s.stops]
        said += [s.outline_stop for s in floor.stories.values() if getattr(s, "outline_stop", None)]
        for kind, parts in (routes_measure(d)["parts"] or {}).items():
            for p in parts or []:
                said += [w for w in (p.get("not_measured") or {}).values() if isinstance(w, str)]
    assert len({w for w in said}) >= 6, said
    for w in said:
        assert "`" not in w and not COORDINATES.search(w), w
        assert "description" not in w, w                            # the model, never Gordium's file
        assert not re.search(r"\b[a-z]+_[a-z_]+\b", w), w            # no field name of the file format
    assert any("the room r isn't read: it gives whether it is not occupied as the text 'yes', not as a yes/no value" in w for w in said), said
    assert any("story outline #1 isn't on one of the model's levels" in w for w in said), said
    # a reason naming what a host states names its mark (CORRIDOR_STATED), for every such fact
    from model_measurement.routes import CORRIDOR_STATED
    for _, _, mark in CORRIDOR_STATED.values():
        assert any(f"the room's {mark} mark" in w for w in said), (mark, said)


def test_a_dead_ends_door_off_its_legs_is_named_without_coordinates():
    from model_measurement.routes.stops import Stop as RouteStop
    words = RouteStop("door_off_legs", name="at one of its closed ends").reason
    assert not COORDINATES.search(words)
    import inspect
    from model_measurement.routes import dead_ends
    assert "at the closed end (" not in inspect.getsource(dead_ends)


@pytest.mark.parametrize("key, question", [("lockable", "it can be locked"),
                                           ("pass_through", "an exit route may pass through it"),
                                           ("not_occupied", "it is not occupied")])
def test_a_yes_no_mark_given_as_text_is_said_as_its_question(key, question):
    """"its lockable is 'no', not one of yes or no" named the field and contradicted itself: said as the question."""
    from model_measurement.routes.floor import read
    from routes_layouts import room_on_corridor
    d = room_on_corridor()
    d["rooms"][0][key] = "no"
    said = [r for s in read(d).stories.values() for r in s.stops]
    # the whole sentence, as it is said: lower case after "isn't read:", the room named once
    room = d["rooms"][0]["name"]
    whole = f"the room {room} isn't read: it gives whether {question} as the text 'no', not as a yes/no value"
    assert any(whole in r for r in said), said
    assert not any("not one of yes or no" in r or key in r or f"room {room} doesn't" in r for r in said), said
    d["rooms"][0][key] = 1
    assert any(f"it gives whether {question} as 1, not as a yes/no value" in r for s in read(d).stories.values()
               for r in s.stops)


def test_the_interiors_own_reasons_say_the_model_not_the_description():
    for key, blanks in (("not_a_description", {}), ("wrong_format", {"got": "x"}), ("units", {"units": "cubits"})):
        assert "description" not in Stop(key, **blanks).reason, key
    from model_measurement.routes.stops import Stop as RouteStop
    assert RouteStop("description", reason="r").reason.startswith("the model can't be read for escape routes")


# ---- review round 3: every yes/no mark one way; reasons lower case mid-sentence; no Python value in words -----

@pytest.mark.parametrize("path, value, whole", [
    (("rooms", 0, "sleeping"), "yes", "room Bedroom gives whether it is a sleeping room as the text 'yes', not as a "
                                      "yes/no value"),
    (("doors", 0, "exit"), "yes", "door Door gives whether it is the required exit door as the text 'yes', not as a "
                                  "yes/no value"),
    (("openings", 0, "escape"), 1, "opening Window gives whether it is an emergency escape and rescue opening as 1, "
                                   "not as a yes/no value"),
])
def test_a_flag_given_but_not_yes_or_no_is_said_so_never_as_not_given(path, value, whole):
    d = base()
    d[path[0]][path[1]][path[2]] = value
    problems = measure(d)["problems"]
    assert problems == [whole]
    assert asked_field(whole) == f"{path[0]}[].{path[2]}"       # still the field to state


def test_a_room_whose_sleeping_mark_isnt_given_is_named_once_in_the_route_reading():
    from model_measurement.routes.floor import read
    from routes_layouts import room_on_corridor
    d = room_on_corridor()
    del d["rooms"][0]["sleeping"]
    said = [r for s in read(d).stories.values() for r in s.stops]
    assert any("the room r isn't read: it doesn't say whether it is a sleeping room (yes or no)" in r
               for r in said), said
    d["rooms"][0]["sleeping"] = "no"
    said = [r for s in read(d).stories.values() for r in s.stops]
    assert any("the room r isn't read: it gives whether it is a sleeping room as the text 'no'" in r
               for r in said), said


def test_an_obstructions_fixed_and_a_flights_spiral_are_yes_no_marks_too():
    from model_measurement.routes.floor import read
    from routes_layouts import room_on_corridor
    d = room_on_corridor()
    d["rooms"][0]["obstructions"] = [{"outline": [[1, 1], [2, 1], [2, 2]], "kind": "casework", "fixed": "yes"}]
    said = [r for s in read(d).stories.values() for r in s.stops]
    assert any("obstruction #1 gives whether it is fixed as the text 'yes', not as a yes/no value" in r
               for r in said), said
    d = base()
    d["stairs"][0]["spiral"] = "no"
    why = measure(d)["parts"]["stair"][0]["not_measured"]["stair_spiral"]
    assert why == "the flight gives whether it is a spiral stairway as the text 'no', not as a yes/no value"


PROPER = re.compile(r"^(Gordium|IBC|NFPA|R\d|BF\d|Revit|Rhino)")


def _broken_reasons():
    """Every reason a set of broken inputs gives, as the reading gives it: interior and route."""
    from model_measurement.routes import measure as routes_measure
    from model_measurement.routes.floor import read
    from routes_layouts import room_on_corridor
    said = []
    for bad in ([], {"format": None}, {"format": "gordium.interior/1"}, {"format": "gordium.interior/1", "units": None},
                {"format": "gordium.interior/1", "units": True}, {"format": 3}):
        said += measure(bad)["problems"]
        try:
            read(bad)
        except Exception as e:                          # the route reading refuses the whole description
            said.append(getattr(e, "reason", str(e)))
    for path, value in ((("doors", 0, "exit"), None), (("doors", 0, "exit"), True),
                        (("openings", 0, "operation"), None), (("openings", 0, "operation"), True),
                        (("openings", 0, "operation"), [1]),
                        (("doors", 0, "stated_clear"), {"width": 34, "height": 80, "source": "m", True: 1}),
                        (("stairs", 0, "spiral"), [True])):
        d = base()
        d[path[0]][path[1]][path[2]] = value
        got = measure(d)
        said += got["problems"] + [w for parts in got["parts"].values() for p in parts or []
                                   for w in (p.get("not_measured") or {}).values()]
    d = base()
    d["has_none"] = [{"kind": "ramp", "source": "A-2", "reading": None},
                     {"kind": "basement", "source": "A", None: 1}, {"kind": None}]
    said += measure(d)["problems"]
    for path, value in ((("rooms", 0, "lockable"), None), (("rooms", 0, "lockable"), [True]),
                        (("rooms", 0, "use"), False), (("doors", 0, "sides"), None), (("levels",), None),
                        (("rooms", 0, "level"), True)):
        d = room_on_corridor()
        node = d
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
        floor = read(d)
        said += list(floor.stops) + [r for s in floor.stories.values() for r in s.stops]
        for parts in (routes_measure(d)["parts"] or {}).values():
            for p in parts or []:
                said += [w for w in (p.get("not_measured") or {}).values() if isinstance(w, str)]
    return [w for w in said if isinstance(w, str)]


def test_no_reason_shows_a_python_value():
    said = _broken_reasons()
    assert len(set(said)) >= 15, said
    for w in said:
        assert not re.search(r"\b(None|True|False)\b", w), w
        assert "Words(" not in w and "[1]" not in w and "{" not in w, w
    assert any("(no form named, not gordium.interior/1)" in w for w in said), said
    assert any("gives its sizes in no unit named" in w for w in said), said


def test_reasons_are_lower_case_mid_sentence():
    """A reason starts lower case (the presenter capitalises where one opens a sentence): after a colon, a semicolon
    or a parenthesis, and at its start, only a proper name (Gordium, a code section) is capitalised."""
    from model_measurement.routes.stops import STOPS as ROUTES
    said = _broken_reasons() + list(INTERIOR_STOPS.values()) + list(ROUTES.values())
    for w in said:
        for piece in [w] + re.split(r"(?:: |; |\()", w)[1:]:
            if piece[:1].isupper():
                assert PROPER.match(piece), (piece, w)



# ---- review round 4: a list said by what is in it where its shape is right; blank text as not given ------------

def _route_stops(d):
    from model_measurement.routes.floor import read
    try:
        floor = read(d)
    except Exception as e:
        return [getattr(e, "reason", str(e))]
    return list(floor.stops) + [r for s in floor.stories.values() for r in s.stops]


def test_a_list_of_the_right_shape_is_said_by_its_ids_and_blank_text_as_not_given():
    from routes_layouts import room_on_corridor
    said = []
    for fmt, units in (("", "in"), ("gordium.interior/1", ""), (" gordium.interior/1 ", "in"),
                       ("gordium.interior/1", "  ")):
        said += measure({"format": fmt, "units": units, "rooms": []})["problems"]
        said += _route_stops(dict(room_on_corridor(), format=fmt, units=units))
    d = room_on_corridor()
    d["passages"] = [{"rooms": ["r", "r"], "line": [[0, 15], [5, 15]]}]
    passage = _route_stops(d)
    d = room_on_corridor()
    d["doors"][0]["sides"] = ["r"]
    door = _route_stops(d)
    said += passage + door
    for w in said:
        assert "(, not" not in w and "in , not" not in w and "in   , not" not in w, w
        assert "is a list, not one of" not in w, w
    assert any("(no form named, not gordium.interior/1)" in w for w in said), said
    assert any("gives its sizes in no unit named, not in" in w for w in said), said
    assert any("(' gordium.interior/1 ', not gordium.interior/1)" in w for w in said), said    # the stray spaces
    assert any("passage #1 isn't read: the passage joins the room r to itself" in w for w in passage), passage
    assert any("the door d isn't read: the door gives 1 side: r, not 2 sides (two rooms, or a room and outside)" in w
               for w in door), door


def test_a_list_where_text_belongs_is_said_to_be_a_list():
    d = base()
    d["openings"][0]["operation"] = ["casement"]
    why = measure(d)["parts"]["emergency_escape_opening"][0]["not_measured"]["opening_net_clear_area"]
    assert "the opening's operation is a list, not one of" in why
    from model_measurement.interior.stops import said
    from model_measurement.interior.stops import counted, items
    assert said(["r", "r"]) == "a list" and said([]) == "an empty list" and said([["x"]]) == "a list"
    assert counted(["r"], "side", "sides") == "1 side: r" and counted(list("abcdefg"), "room", "rooms") == "7 rooms"
    assert items(["", 3, None]) == "a blank name, a number and nothing"



# ---- review round 5: the grid. Every slot a value comes from the model in, fed every kind of wrong value, through
# both readers; every reason it gives checked for gaps, Python's own words, self-contradiction, case and naming ----

GRID_VALUES = [None, "", "  ", [], ["x"], "RIGHT_IN_A_LIST", ["a", "b"], ["", "r"], 1, True, {}]


def _set(d, path, value):
    node = d
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value


def _handrail(side):
    return [{"side": side, "inner_edge": [[0, 32.5], [30, 32.5]]}]


def _passage(rooms):
    return [{"rooms": rooms, "line": [[0, 15], [5, 15]]}]


# slot: (reader, path, the right value, how the reason names the slot, how the value is set)
GRID = {
    "format": ("both", ("format",), "gordium.interior/1", "form", None),
    "units": ("both", ("units",), "in", "sizes", None),
    "sleeping": ("both", ("rooms", 0, "sleeping"), False, "sleeping room", None),
    "escape": ("interior", ("openings", 0, "escape"), True, "escape", None),
    "exit": ("interior", ("doors", 0, "exit"), True, "exit door", None),
    "spiral": ("interior", ("stairs", 0, "spiral"), False, "spiral", None),
    "handrail side": ("interior", ("stairs", 0, "handrails"), "left", "handrail", _handrail),
    "window operation": ("interior", ("openings", 0, "operation"), "casement", "operation", None),
    "door operation": ("interior", ("doors", 0, "operation"), "side_hinged", "operation", None),
    "has-none reading": ("interior", ("has_none",), False, "reading",
                         lambda v: [{"kind": "ramp", "source": "A-2", "reading": v}]),
    "room name": ("both", ("rooms", 0, "name"), "Bedroom", "room", None),        # with a room fault: ROOM_FAULT
    "lockable": ("routes", ("rooms", 0, "lockable"), False, "locked", None),
    "pass through": ("routes", ("rooms", 0, "pass_through"), False, "pass through", None),
    "not occupied": ("routes", ("rooms", 0, "not_occupied"), False, "occupied", None),
    "use": ("routes", ("rooms", 0, "use"), "day_care", "use", None),
    "door sides": ("routes", ("doors", 0, "sides"), ["r", "c"], "side", None),
    "passage rooms": ("routes", ("passages",), ["r", "c"], "passage", _passage),
    "levels": ("routes", ("levels",), [{"id": "L1", "name": "Level 1", "elevation": 0}], "level", None),
    "exit kind": ("routes", ("doors", 1, "exit_kind"), "exterior_at_discharge", "exit", None),
}


def _interior_reasons(d):
    got = measure(d)
    return set(got["problems"]) | {w for parts in got["parts"].values() for p in parts or []
                                   for w in (p.get("not_measured") or {}).values() if isinstance(w, str)}


def _route_reasons(d):
    from model_measurement.routes.floor import read
    try:
        floor = read(d)
    except Exception as e:
        return {getattr(e, "reason", str(e))}
    return set(floor.stops) | {r for st in floor.stories.values() for r in st.stops} | \
        {st.outline_stop for st in floor.stories.values() if st.outline_stop}


def _room_fault(d):
    """A second fault on the same room (its sleeping mark given as text), so a reason that names the room appears
    whatever its name is: a name alone is never a reason."""
    d["rooms"][0].update(sleeping="maybe", name="Bedroom")   # a name not its id: a name not read shows as the id


ROOM_FAULT = {"room name": _room_fault}
# a value a slot reads as right, or as not given where not given is allowed: no reason is due (checked: each gives
# none, never assumed; every other value must give one). None for lockable, pass through, not occupied and use:
# optional, "not given" makes the room one a route never crosses, never a reason. None for spiral: base() gives no
# spiral already, so its reason (spiral_not_said) is in the untouched reasons. True for a yes/no mark (and the
# has-none reading): a right value. A room name not text: it falls back to the id, shown in the room's reason.
NO_REASON_DUE = {
    "lockable": {None, True}, "pass through": {None, True}, "not occupied": {None},
    "use": {None}, "spiral": {None}, "has-none reading": {True},
    "sleeping": {True}, "escape": {True}, "exit": {True},
}


def _grid_reasons():
    from routes_layouts import room_on_corridor
    readers = {"interior": (base, _interior_reasons), "routes": (room_on_corridor, _route_reasons)}
    out = []
    for slot, (which, path, right, naming, wrap) in GRID.items():
        also = ROOM_FAULT.get(slot)
        for name, (make, reasons) in readers.items():
            if which not in (name, "both"):
                continue
            first = make()
            if also:
                also(first)
            plain = reasons(first)
            for value in GRID_VALUES:
                v = [right] if value == "RIGHT_IN_A_LIST" else value
                d = make()
                if also:
                    also(d)
                _set(d, path, wrap(v) if wrap else v)
                new = reasons(d) - plain
                for r in new:
                    out.append((slot, name, value, naming, r))
                if not new:
                    out.append((slot, name, value, naming, None))     # none: allowed only where NO_REASON_DUE
    return out


SELF_CONTRADICTION = re.compile(r"(?:^|[(: ])([\w'./ -]+?), not \1(?:[):;,]|$)")


def test_every_wrong_value_in_every_slot_is_said_plainly_and_truly():
    found = _grid_reasons()
    assert len(found) > 100, len(found)
    bad = []
    # the grid guards every slot: each gives a reason for some value, and each value with none is one stated above
    for slot in GRID:
        assert any(r for s, _, _, _, r in found if s == slot and r), f"{slot}: no value gave a reason"
    for slot, reader, value, naming, r in found:
        none_due = repr(value) in {repr(x) for x in NO_REASON_DUE.get(slot, set())}
        if r is None and not none_due:
            bad.append((slot, reader, value, ["gave no reason"], None))
        if r is not None and none_due:
            bad.append((slot, reader, value, ["a reason where none is due"], r))
    found = [f for f in found if f[4] is not None]
    for slot, reader, value, naming, r in found:
        problems = []
        if slot == "room name" and not re.search(r"(?:^| )room [br](?: |$)", r):
            problems.append("the room not named by its id")
        if re.search(r"gives \d+, not", r) and not isinstance(value, list):
            problems.append("a number given read as a count")
        if "(, " in r or " , not" in r or "in , not" in r or ": ," in r:
            problems.append("an empty gap")
        if re.search(r"\b(None|True|False)\b", r) or "[" in r or "{" in r:
            problems.append("Python's own words")
        if SELF_CONTRADICTION.search(r):
            problems.append("X, not X")
        m = re.search(r"gives (\d+) \w+.*?not (\d+)\b", r)
        if m and m.group(1) == m.group(2):
            problems.append("gives N, not N")
        if not (r[:1].islower() or PROPER.match(r)):
            problems.append("not lower case")
        if problems:
            bad.append((slot, reader, value, problems, r))
    # each wrong value is named by its slot in one reason at least (others may follow from it: "the door d opens
    # on 'r', which is a room that isn't read")
    groups = {}
    for slot, reader, value, naming, r in found:
        groups.setdefault((slot, reader, repr(value), naming), []).append(r)
    for (slot, reader, value, naming), rs in groups.items():
        if not any(naming in r.lower() for r in rs):
            bad.append((slot, reader, value, [f"no reason names the {naming}"], rs))
    assert not bad, "\n".join(map(repr, bad[:40])) + f"\n({len(bad)} in all)"



def test_a_room_name_that_isnt_text_is_said_by_the_rooms_id():
    from routes_layouts import room_on_corridor
    for name in (True, ["x"], [], {}):
        d = base()
        d["rooms"][0].update(name=name, sleeping="maybe")
        interior = measure(d)["problems"]
        assert interior == ["room b gives whether it is a sleeping room as the text 'maybe', not as a yes/no value"], \
            interior
        d = room_on_corridor()
        d["rooms"][0].update(name=name, sleeping="maybe")
        said = _route_reasons(d)
        assert any(r.startswith("the room r isn't read:") for r in said), said
        assert not any(re.search(r"\bTrue\b|\[|\{", r) for r in said), said


def test_a_number_given_where_a_list_belongs_is_said_as_a_number_never_a_count():
    from routes_layouts import room_on_corridor
    d = room_on_corridor()
    d["doors"][0]["sides"] = 1
    assert any("the door gives the number 1, not 2 sides" in r for r in _route_reasons(d))
    d = room_on_corridor()
    d["passages"] = [{"rooms": 2, "line": [[0, 15], [5, 15]]}]
    assert any("the passage gives the number 2, not 2 rooms" in r for r in _route_reasons(d))


@pytest.mark.parametrize("pid, shown", [(True, "(no name)"), (["b"], "(no name)"), ("  ", "(no name)"), (7, "7"),
                                        ("b", "b")])
def test_a_parts_id_is_its_name_only_when_it_is_text_or_a_number(pid, shown):
    from model_measurement.interior.read import name_of
    assert name_of({"name": [], "id": pid}) == shown
