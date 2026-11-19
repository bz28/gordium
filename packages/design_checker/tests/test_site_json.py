"""The site description, gordium.site/1 (design_checker/site_json.py, docs/protocol/): every site the tests and
goldens check (both 106 Ithaca Rd models, the recorded session's models, every scenario and deep-run site as drawn
and after its edit, 200 stress designs) goes to a description and back unchanged; anything not exactly a v1
description is refused whole, with its reason; the JSON Schema file lists exactly the fields the code reads; and the
worker's hello and read_model answer as documented, while the older commands need no protocol."""

import copy
import hashlib
import json
import math
import random
import re
from pathlib import Path

import pytest

from design_checker import goldens, protocol, scenarios, site_json
from design_checker.__main__ import answer
from design_checker.site_json import SiteRefused, from_read_site, from_site, problems_of, to_site, validate
from model_measurement.read_3dm import read_site
from rule_format.place import plugin_place
from rule_format.rulebook import REPO

DOCS = REPO / "docs/protocol"
SCHEMA_FILE = DOCS / "site_description_v1.schema.json"
PLACE = plugin_place()
SAMPLE = PLACE.test_sites / "106_ithaca_rd"
HOST = {"name": "test", "version": "0", "document": "test", "model_units": "Feet"}
NO_GRADE = {"source": "none", "points": []}


def _example() -> dict:
    """The description in the documentation's example (so the example is valid, and stays so)."""
    text = (DOCS / "site_description_v1.md").read_text(encoding="utf-8")
    return json.loads(re.search(r"```json\n(.*?)```", text, re.DOTALL)[1])


def _sites():
    """(name, site) for every site the goldens check, as the measuring reads it."""
    models = sorted(SAMPLE.glob("*.3dm")) + sorted((REPO / "test_data/sessions").rglob("*.3dm"))
    for path in models:
        yield path.relative_to(REPO).as_posix(), read_site(path, {})
    for folder in ("scenarios", "deep_run"):
        for path in scenarios.paths(PLACE.test_sites / folder):
            sc = scenarios.load(path)
            for moved in (False, True):
                yield f"{folder}/{path.stem}/{moved}", scenarios.site(sc, moved)[0]
    gen = goldens.stress_generator()
    for k, case in enumerate(goldens.stress_cases()):
        yield f"stress/{k}", gen.gordium_site(gen.build(case["lot"], case["edits"])[0])


def _plain(value):
    return json.loads(json.dumps(value))       # as JSON gives it back: tuples as lists


def test_every_fixture_goes_to_a_description_and_back_unchanged():
    names = []
    for name, site in _sites():
        doc = from_read_site(site, NO_GRADE, HOST)
        validate(doc)
        assert from_site(to_site(doc)) == doc, name                          # description -> site -> description
        assert from_site(to_site(_plain(doc))) == doc, name                  # through JSON text too
        back = to_site(doc)                                                  # site -> description -> site
        assert {k: back[k] for k in ("units", "lot", "problems")} == _plain({k: site[k] for k in ("units", "lot", "problems")}), name
        assert [{k: v for k, v in b.items() if k != "layer"} for b in back["buildings"]] == _plain(site["buildings"]), name
        names.append(name)
    assert len(names) >= 2 + 6 + 2 * 12 + 200
    assert any(n.startswith("test_data/sessions/") for n in names)


def test_problems_on_a_real_model_go_by_code_and_come_back_as_the_same_words(tmp_path):
    site = read_site(SAMPLE / "model.3dm", {})          # two lot outlines: the lot isn't picked
    doc = from_read_site(site, NO_GRADE, HOST)
    assert site["problems"] and doc["problems"] == [{"code": "several_lot_outlines",
                                                     "args": {"count": "2", "layer": "Site"}}]
    assert to_site(doc)["problems"] == site["problems"]
    broken = tmp_path / "broken.3dm"
    broken.write_bytes(b"not a Rhino file")
    doc = from_read_site(read_site(broken, {}), NO_GRADE, HOST)
    assert [p["code"] for p in doc["problems"]] == ["unreadable_file"]


def test_the_documented_example_is_valid_and_round_trips():
    doc = _example()
    validate(doc)
    assert from_site(to_site(doc)) == doc


def test_nothing_in_a_description_is_dropped_on_the_way_to_the_site():
    doc = _example()
    doc["left_out"] = [{"id": "shed", "layer": "Default", "could_be_building": True, "touching": None,
                        "ground_like": False, "context": False}]
    doc["unsent"] = [{"id": "block-1", "layer": "Building", "kind": "block",
                      "problem": {"code": "not_a_solid", "args": {"kind": "a block", "layer": "Building"}}}]
    doc["grade"] = {"source": "spot", "points": [[0, 0, 100.0], [50, 100, 98.5]]}
    doc["inventory_complete"] = False
    site = to_site(doc)
    assert site["left_out"] == doc["left_out"] and site["grade"] == doc["grade"] and site["inventory_complete"] is False
    assert site["unsent"] == [{"id": "block-1", "layer": "Building", "kind": "block",
                               "problem": "a block on the Building layer can't be measured yet (explode it or turn it "
                                          "into a solid)"}]
    assert from_site(site) == doc


# ---- refusals: each one refuses the whole description, saying why ----------------------------------------------

def _set(path, value):
    """A change to the example: `path` is keys and list positions; value DROP removes the field."""
    def change(doc):
        *parents, last = path
        at = doc
        for p in parents:
            at = at[p]
        if value is DROP:
            del at[last]
        else:
            at[last] = value
    return change


DROP = object()
B = ("buildings", 0)
REFUSED = {
    "unknown field at the top": (_set(("rooms",), 3), "site: unknown field 'rooms'"),
    "unknown field on a building": (_set(B + ("colour",), "red"), "buildings[0]: unknown field 'colour'"),
    "unknown field on a face": (_set(B + ("faces", 0, "normal"), [0, 0, 1]), "faces[0]: unknown field 'normal'"),
    "unknown field on the lot": (_set(("lot", "area"), 5000), "lot: unknown field 'area'"),
    "unknown field on a problem": (_set(("problems",), [{"code": "no_lot", "args": {}, "severity": "low"}]),
                                   "unknown field 'severity'"),
    "grade left out": (_set(("grade",), DROP), "missing field 'grade'"),
    "inventory_complete left out": (_set(("inventory_complete",), DROP), "missing field 'inventory_complete'"),
    "left_out left out": (_set(("left_out",), DROP), "missing field 'left_out'"),
    "a building's problems left out": (_set(B + ("problems",), DROP), "missing field 'problems'"),
    "inventory_complete not true or false": (_set(("inventory_complete",), "yes"), "should be true or false"),
    "unknown stop code": (_set(B + ("problems",), [{"code": "wall_is_wobbly", "args": {}}]),
                          "unknown problem code 'wall_is_wobbly'"),
    "a stop's blank missing": (_set(("problems",), [{"code": "no_lot_outline", "args": {}}]), "missing arg 'layer'"),
    "a stop's blank unknown": (_set(("problems",), [{"code": "no_lot", "args": {"why": "x"}}]), "unknown arg 'why'"),
    "a stop's blank not text": (_set(("problems",), [{"code": "several_lot_outlines", "args": {"count": 2, "layer": "Site"}}]),
                                "every arg should be text"),
    "a stop whose words read as another": (
        _set(("problems",), [{"code": "no_lot_layer", "args": {"layer": "closed lot outline on the Site"}}]),
        "read back as no_lot_outline"),
    "NaN in a face": (_set(B + ("faces", 0, "points", 0, 2), math.nan), "should be finite numbers"),
    "infinity in a lot line": (_set(("lot", "edges", 0, "points", 1, 0), math.inf), "should be finite numbers"),
    "a number as text": (_set(B + ("faces", 0, "points", 1, 0), "30"), "should be finite numbers"),
    "true as a number": (_set(B + ("faces", 0, "points", 1, 0), True), "should be finite numbers"),
    "a number too big for a float": (_set(B + ("faces", 0, "points", 0, 0), 10 ** 400), "should be finite numbers"),
    "a 2D point in a face": (_set(B + ("faces", 0, "points", 1), [30, 25]), "should be a point of 3 numbers"),
    "a face of 2 points": (_set(B + ("faces", 0, "points"), [[0, 0, 0], [1, 0, 0]]), "a face needs at least 3"),
    "a hole of 2 points": (_set(B + ("faces", 0, "holes"), [[[0, 0, 0], [1, 0, 0]]]), "a face needs at least 3"),
    "a lot line of 1 point": (_set(("lot", "edges", 0, "points"), [[0, 0]]), "a lot line needs at least 2 points"),
    "a lot of 2 corners": (_set(("lot", "edges"), [{"points": [[0, 0], [5, 0]], "curved": False},
                                                   {"points": [[5, 0], [0, 0]], "curved": False}]),
                           "a lot needs at least 3"),
    "NaN floor height": (_set(B + ("floor",), math.nan), "should be a finite number"),
    "two buildings with one id": (lambda d: d["buildings"].append(copy.deepcopy(d["buildings"][0])),
                                  "the id 'house-1' is used twice"),
    "a building with the lot's id": (_set(B + ("id",), "lot-1"), "the id 'lot-1' is used twice"),
    "a left-out object that was sent": (_set(("left_out",), [{"id": "house-1", "layer": None, "could_be_building": True,
                                                              "touching": True, "ground_like": False, "context": False}]),
                                        "the id 'house-1' is used twice"),
    "an empty id": (_set(B + ("id",), " "), "should not be empty"),
    "touching not true, false or null": (_set(("left_out",), [{"id": "shed", "layer": None, "could_be_building": True,
                                                               "touching": "yes", "ground_like": False, "context": False}]),
                                         "should be true or false or null"),
    "millimetres": (_set(("units",), "mm"), "the model's units (mm) aren't supported"),
    "another major version": (_set(("schema",), "gordium.site/2"), "a different major version is refused"),
    "a role other than building": (_set(B + ("role",), "context"), "should be 'building'"),
    "an unknown grade source": (_set(("grade",), {"source": "guess", "points": []}), "should be one of"),
    "grade points with source none": (_set(("grade",), {"source": "none", "points": [[0, 0, 0]]}),
                                      "source 'none' with no points"),
    "spot grades with no points": (_set(("grade",), {"source": "spot", "points": []}), "source 'none' with no points"),
    "not an object": (lambda d: d.clear() or d.update(buildings="x"), "missing field 'schema'"),
}


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_a_description_that_isnt_exactly_v1_is_refused_whole(name):
    change, reason = REFUSED[name]
    doc = _example()
    change(doc)
    with pytest.raises(SiteRefused) as e:
        to_site(doc)
    assert any(reason in r for r in e.value.reasons), e.value.reasons
    assert str(e.value).startswith("site description refused: ")


def test_every_refusal_case_is_valid_without_its_change():
    assert problems_of(_example()) == []


def test_a_description_of_any_shape_is_answered_with_reasons_never_a_crash():
    rng = random.Random(7)
    junk = [None, True, 0, 1.5, math.nan, "x", "", [], {}, [1, 2], {"a": 1}, [[0, 0, 0]]]

    def paths(v, at=()):
        yield at
        if isinstance(v, dict):
            for k, x in v.items():
                yield from paths(x, at + (k,))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                yield from paths(x, at + (i,))
    every = [p for p in paths(_example()) if p]
    for _ in range(600):
        doc = _example()
        for p in rng.sample(every, rng.randint(1, 3)):
            try:
                _set(p, rng.choice(junk))(doc)
            except (KeyError, IndexError, TypeError):
                pass
        reasons = problems_of(doc)
        assert isinstance(reasons, list)
        if reasons:
            with pytest.raises(SiteRefused):
                to_site(doc)
    assert problems_of("text") and problems_of(None) and problems_of([])


def test_a_site_holding_what_a_description_cant_say_is_refused_never_dropped():
    site = to_site(_example())
    site["unsent"] = [{"id": "block-1", "layer": "Building", "kind": "block",
                       "problem": "a block on the Building layer can't be measured yet (explode it or turn it into a solid)"}]
    site["left_out"] = [{"id": "shed", "layer": None, "could_be_building": True, "touching": None, "ground_like": False,
                         "context": False}]
    for change, reason in (
            (lambda s: s.update(colour="red"), "site: unknown field 'colour'"),
            (lambda s: s.pop("grade"), "site: missing field 'grade'"),
            (lambda s: s["buildings"][0].update(parts=[]), "buildings[0]: unknown field 'parts'"),
            (lambda s: s["buildings"][0].pop("layer"), "buildings[0]: missing field 'layer'"),
            (lambda s: s["buildings"][0]["faces"][0].update(normal=[0, 0, 1]), "faces[0]: unknown field 'normal'"),
            (lambda s: s["lot"].update(note="x"), "lot: unknown field 'note'"),
            (lambda s: s["lot"].pop("edges"), "lot: missing field 'edges'"),
            (lambda s: s["lot"]["edges"][0].update(arc=True), "lot.edges[0]: unknown field 'arc'"),
            (lambda s: s["grade"].update(warning="x"), "grade: unknown field 'warning'"),
            (lambda s: s["unsent"][0].update(severity="low"), "unsent[0]: unknown field 'severity'"),
            (lambda s: s["left_out"][0].update(size=3), "left_out[0]: unknown field 'size'"),
            (lambda s: s["host"].update(user="ben"), "host: unknown field 'user'"),
            (lambda s: s["buildings"][0]["problems"].append(""), "the tool's own words should not be empty"),
            (lambda s: s["buildings"][0]["faces"][0]["points"][0].__setitem__(2, math.nan), "should be finite numbers"),
            (lambda s: s["host"].update(version=object()), "site: not JSON data")):
        s = copy.deepcopy(site)
        change(s)
        with pytest.raises(SiteRefused) as e:
            from_site(s)
        assert any(reason in r for r in e.value.reasons), (reason, e.value.reasons)
    assert from_site(site)["unsent"][0]["problem"] == {"code": "not_a_solid", "args": {"kind": "a block",
                                                                                       "layer": "Building"}}
    with pytest.raises(SiteRefused, match="should be an object"):
        from_site(["not", "a", "site"])



def test_words_no_measuring_reason_gives_go_as_the_tools_own_words_never_dropped():
    site = to_site(_example())
    site["buildings"][0]["problems"].append("a block (Garage)")
    site["problems"].append("lot is odd")
    doc = from_site(site)
    assert doc["buildings"][0]["problems"] == [{"code": "tool_words", "args": {"words": "a block (Garage)"}}]
    assert doc["problems"] == [{"code": "tool_words", "args": {"words": "lot is odd"}}]
    assert to_site(doc) == site


@pytest.mark.parametrize("words, reason", [
    ("no Site layer", "are a measuring reason: send its code, no_lot_layer"),
    ("a building has a curved surface (not measured yet)", "send its code, curved_surface"),
    (" ", "the tool's own words should not be empty")])
def test_the_tools_own_words_are_never_a_measuring_reason_in_disguise(words, reason):
    doc = _example()
    doc["buildings"][0]["problems"] = [{"code": "tool_words", "args": {"words": words}}]
    with pytest.raises(SiteRefused) as e:
        to_site(doc)
    assert any(reason in r for r in e.value.reasons), e.value.reasons


def test_a_key_given_twice_is_refused_never_one_of_them_dropped():
    text = json.dumps(_example())
    assert site_json.loads(text) == _example()
    twice = text[:-1] + ', "inventory_complete": false}'
    with pytest.raises(SiteRefused, match="'inventory_complete' is given twice"):
        site_json.loads(twice)
    with pytest.raises(SiteRefused, match="'id' is given twice"):
        site_json.loads('{"buildings": [{"id": "a", "id": "b"}]}')
    import io
    from design_checker.__main__ import serve
    out = io.StringIO()
    serve(io.StringIO('{"id": 1, "cmd": "hello", "protocol": "1.0", "protocol": "2.0"}\n'), out)
    reply = json.loads(out.getvalue())
    assert reply["ok"] is False and "'protocol' is given twice" in reply["error"]


def test_the_worker_answers_every_line_even_one_it_cant_read():
    import io
    from design_checker.__main__ import serve
    lines = ['{"id": 1, "x": ' + "1" * 5000 + "}", "[" * 100000 + "]" * 100000, "[1]", "{not json", '"text"']
    out = io.StringIO()
    serve(io.StringIO("".join(line + "\n" for line in lines)), out)
    replies = [json.loads(r) for r in out.getvalue().splitlines()]
    assert len(replies) == len(lines) and all(r["ok"] is False and r["id"] is None for r in replies)
    assert replies[3]["error"].startswith("not JSON: Expecting property name")     # as before, word for word



def test_the_running_worker_answers_a_line_that_isnt_utf8_and_keeps_serving():
    import subprocess
    import sys
    run = subprocess.run([sys.executable, "-m", "design_checker", "serve"], input=b'\xff\xfe{"id": 1}\n{"id": 2, '
                         b'"cmd": "nope"}\n', capture_output=True, timeout=120, cwd=REPO)
    replies = [json.loads(r) for r in run.stdout.decode("utf-8").splitlines()]
    assert run.returncode == 0 and [r["id"] for r in replies] == [None, 2], run.stderr[-500:]
    assert "UnicodeDecodeError" in replies[0]["error"] and "unknown command" in replies[1]["error"]


# ---- the schema file and the code agree -------------------------------------------------------------------------

def test_the_schema_file_lists_exactly_the_fields_the_code_reads():
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    for kind, table in site_json.OBJECTS.items():
        obj = schema if kind == "site" else schema["$defs"][kind]
        assert obj["additionalProperties"] is False, kind
        assert set(obj["properties"]) == set(table), kind
        assert set(obj["required"]) == {k for k, required in table.items() if required}, kind
    assert schema["properties"]["schema"]["const"] == site_json.SCHEMA
    assert schema["properties"]["units"]["const"] == site_json.UNITS
    assert schema["$defs"]["grade"]["properties"]["source"]["enum"] == list(site_json.GRADE_SOURCES)


def test_the_schema_file_cant_change_without_a_changelog_line():
    text = SCHEMA_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    changelog = (DOCS / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"schema sha256 `{digest}`" in changelog, "the schema changed: bump its version and add a CHANGELOG line"
    assert f"protocol {protocol.PROTOCOL} · site description `{site_json.SCHEMA}`" in changelog


# ---- the worker's new commands ----------------------------------------------------------------------------------

def test_hello_says_the_protocol_the_schema_and_the_fingerprints():
    reply = answer({"id": 1, "cmd": "hello", "protocol": "1.0"})
    assert reply["ok"] and reply["result"] == reply["about"] == protocol.about()
    about = reply["result"]
    assert about["protocol"] == "1.2" and about["site_schema"] == "gordium.site/1"
    assert re.fullmatch(r"[0-9a-f]{64}", about["worker_fingerprint"])
    assert set(about["rulebook"]) >= {PLACE.key} and all(re.fullmatch(r"[0-9a-f]{64}", v) for v in about["rulebook"].values())
    assert answer({"id": 2, "cmd": "hello", "protocol": "1.3"})["ok"]        # a newer minor version: understood


def test_the_fingerprints_cover_what_a_check_reads_and_follow_a_rule_edited_while_the_worker_runs(tmp_path, monkeypatch):
    code = {f.relative_to(REPO).as_posix() for f in protocol.code_files()}
    assert {"packages/rule_format/rule_format/measures.yaml", "packages/project_report/project_report/report.py",
            "packages/model_measurement/model_measurement/stops.py", "packages/design_checker/design_checker/check.py",
            "packages/envelope_builder/envelope_builder/__init__.py"} <= code
    assert not any("/tests/" in f or "__pycache__" in f for f in code)
    place = {f.relative_to(PLACE.folder).as_posix() for f in protocol.place_files(PLACE.folder)}
    assert {"regulations/reviewers.yaml", "regulations/document_extraction_guide/vocabulary.yaml",
            "docs/research/2026-10-20_architect_questions.md"} <= code
    from rule_format import rulebook
    assert {rulebook.REVIEWERS_FILE, rulebook.VOCABULARY_FILE} <= set(protocol.code_files())
    assert {"jurisdiction.yaml", "not_checked_yet.yaml", "5_zoning_rules/R-1b.yaml",
            "1_source_documents/sources.yaml"} <= place
    assert not any(f.endswith(".pdf") for f in place)
    import shutil
    from rule_format.place import Place
    copy_ = tmp_path / "ithaca_city"
    for f in protocol.place_files(PLACE.folder):
        (copy_ / f.relative_to(PLACE.folder)).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(f, copy_ / f.relative_to(PLACE.folder))
    monkeypatch.setattr(protocol, "places", lambda: [Place(copy_, PLACE.settings)])
    before = protocol.about()["rulebook"]
    rule = copy_ / "5_zoning_rules/R-1b.yaml"
    rule.write_text(rule.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    assert protocol.about()["rulebook"] != before


@pytest.mark.parametrize("said", [None, "2.0", "0.9", 1, ""])
def test_a_new_command_without_protocol_1_is_refused(said):
    request = {"id": 3, "cmd": "hello"} if said is None else {"id": 3, "cmd": "hello", "protocol": said}
    reply = answer(request)
    assert reply == {"id": 3, "ok": False, "error": reply["error"]} and "not spoken" in reply["error"]


def test_the_older_commands_need_no_protocol():
    assert answer({"id": 4, "cmd": "facts", "facts": {}})["ok"]
    assert "about" not in answer({"id": 4, "cmd": "facts", "facts": {}})


def test_read_model_gives_a_valid_description_of_the_file_and_never_claims_the_lot_was_inventoried():
    path = SAMPLE / "spreadsheet_design_model.3dm"
    facts = {"grade_from": "spot", "grade_points": [[0, 0, 100.0], [10, 0, 100.0], [0, 10, 101.0]]}
    reply = answer({"id": 5, "cmd": "read_model", "protocol": "1.0", "model": str(path), "facts": facts})
    assert reply["ok"], reply
    doc = reply["result"]["site"]
    validate(doc)
    assert reply["about"] == protocol.about()
    assert doc == from_read_site(read_site(path, facts), {"source": "spot", "points": facts["grade_points"]},
                                 {"name": "rhino3dm", "version": doc["host"]["version"], "document": path.name,
                                  "model_units": "Feet"})
    assert doc["inventory_complete"] is False and doc["left_out"] == [] and doc["unsent"] == []
    said = answer({"id": 6, "cmd": "read_model", "protocol": "1.0", "model": str(path), "facts": {},
                   "inventory_complete": True})
    assert said["result"]["site"]["inventory_complete"] is True and said["result"]["site"]["grade"] == NO_GRADE
    bad = answer({"id": 7, "cmd": "read_model", "protocol": "1.0", "model": str(path), "facts": {},
                  "inventory_complete": "yes"})
    assert not bad["ok"] and "inventory_complete" in bad["error"]


def test_grade_points_with_no_source_named_are_spot_grades_as_the_measuring_reads_them():
    assert site_json.grade_of({"grade_points": [[0, 0, 100.0]]}) == {"source": "spot", "points": [[0, 0, 100.0]]}
    for named in ("flat", "", False, 0):
        with pytest.raises(SiteRefused, match=f"grade_from is {named!r}"):
            site_json.grade_of({"grade_from": named, "grade_points": [[0, 0, 100.0]]})
    assert site_json.grade_of({"grade_from": "terrain"}) == NO_GRADE
    assert site_json.grade_of({"grade_from": "finished_spots", "grade_points": [(1, 2, 3)]}) == \
        {"source": "finished_spots", "points": [[1, 2, 3]]}


def test_a_lot_sent_as_null_with_no_problem_still_leaves_every_lot_measure_needing_review():
    """The contract (lot: null, "problems should then say why"): a tool that doesn't say why isn't refused, and the
    check is the same as with Rhino's own reason, every lot measure needing review as "no lot outline" (review of PR
    72: the measuring's fallback is what makes this safe, so it is pinned here)."""
    from design_checker.check import check_site
    from model_measurement.stops import stop
    sc = scenarios.load(scenarios.paths()[0])
    site, facts, extras = scenarios.site(sc)
    facts = {k: v for k, v in facts.items() if k != "grade_points"}
    doc = from_read_site({**site, "lot": None}, site_json.grade_of(scenarios.facts(sc)), HOST)
    assert doc["lot"] is None and doc["problems"] == [] and problems_of(doc) == []       # accepted, as documented
    said = {"code": "no_lot_outline", "args": {"layer": "Site"}}
    got = {}
    for why in ([], [said]):
        view = check_site(to_site({**doc, "problems": why}), facts, extras=extras)["view"]
        got[bool(why)] = {i.get("rule"): (i.get("status"), i.get("reason")) for i in view["items"] if i.get("rule")}
    lot_rules = [k for k, (status, reason) in got[True].items() if reason == stop("no_lot_outline", layer="Site")]
    assert "R-1b.front_yard" in lot_rules and "R-1b.lot_area_one_family_detached" in lot_rules
    assert {k: s for k, (s, _) in got[False].items()} == {k: s for k, (s, _) in got[True].items()}
    for k in lot_rules:
        assert got[False][k] == ("needs_review", stop("no_lot"))
