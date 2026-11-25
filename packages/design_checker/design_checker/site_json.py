"""The site description, gordium.site/1: the lot and buildings a design tool (Rhino today, Revit later) sends the
checker, as plain JSON, so any tool can be checked the same way. The contract is docs/protocol/site_description_v1.md
(the fields, in words) and its JSON Schema, docs/protocol/site_description_v1.schema.json (the same fields, for a
tool's own tests: tests/test_site_json.py proves the two agree).

    validate(doc)        refuses (SiteRefused, every reason listed) anything that isn't exactly a v1 description
    to_site(doc)         a valid description as the site the measuring reads (problems in words, as stop() gives)
    from_site(site)      that site back as a description (each problem's words read back into its code)
    loads(text)          JSON text read strictly (a key given twice in one object is refused)
    read_model(path, facts)   a .3dm's lot and Building layers as a description (the worker's read_model)

Strict, never forgiving: a field this version doesn't know, a problem code the measuring doesn't know, a number
that isn't finite, a face or hole with fewer than 3 points, or an id used twice refuses the whole description. A
field silently dropped is exactly how a newer tool's warning would be ignored and a design pass that shouldn't.
"""

import json
import math
from pathlib import Path

from model_measurement.read_3dm import LAYERS
from model_measurement.stops import STOPS, TOOL_WORDS, blanks, code_of, stop, words_of

SCHEMA = "gordium.site/1"
UNITS = "ft"
GRADE_SOURCES = ("spot", "finished_spots", "terrain", "none")

# Each object's fields: name -> required? (True) or optional (False). The JSON Schema file lists the same.
TOP = {"schema": True, "units": True, "host": True, "lot": True, "buildings": True, "unsent": True,
       "left_out": True, "grade": True, "inventory_complete": True, "problems": True}
HOST = {"name": True, "version": True, "document": True, "model_units": True}
LOT = {"id": True, "edges": True}
EDGE = {"points": True, "curved": True}
BUILDING = {"id": True, "role": True, "layer": True, "name": False, "floor": False, "faces": True, "problems": True}
FACE = {"points": True, "holes": False}
UNSENT = {"id": True, "layer": True, "kind": True, "problem": True}
LEFT_OUT = {"id": True, "layer": True, "could_be_building": True, "touching": True, "ground_like": True,
            "context": True, "slab": False, "name": False}
# What a site slab left out is (left_out[].slab, protocol 1.3): a slab on the ground the tool can't tell is part of a
# building (Revit: a Floor under none of the house's walls or roofs), by what the architect marked it. A porch, deck,
# landing or ramp is part of the building in the yards and lot coverage (§325-18A), so it is sent as a building, never
# as a slab. "unmarked": not marked, so it may be one (every lot coverage and yard row it could change needs review);
# "patio": a patio, terrace or walk, exempt from lot coverage, but one above grade may not be in a required yard
# (§325-3B BUILDING AREA, TERRACE OR PATIO), and its height above the ground isn't measured, so the yards need
# review; "parking": a parking area, parking space or driveway, which building area "shall not include" (§325-3B).
SLAB_KINDS = ("unmarked", "patio", "parking")
SLABS_EXEMPT = ("patio", "parking")       # not buildings: never in lot coverage, never "an object not measured"
SITE_SLABS = "site_slabs"                 # extras: the description's slabs, as for_measuring hands them to the view
# extras: the left-out objects standing apart from the building (touching false) that could be a structure
# (could_be_building true), each {id, name}, as for_measuring hands them to the view. A freestanding deck, porch,
# landing or ramp is part of the building in the yards (§325-18A), and no other building or structure may stand in a
# yard (§325-3B YARD), so each keeps every required yard at needs review (present._cautious_for_left_out). Given
# whenever an object is left out, so an empty list says none stands apart (absent, the view counts every object not
# touching).
STANDING_APART = "standing_apart"
GRADE = {"source": True, "points": True}
PROBLEM = {"code": True, "args": True}
OBJECTS = {"site": TOP, "host": HOST, "lot": LOT, "edge": EDGE, "building": BUILDING, "face": FACE,
           "unsent": UNSENT, "left_out": LEFT_OUT, "grade": GRADE, "problem": PROBLEM}


class SiteRefused(ValueError):
    """A site description that isn't exactly gordium.site/1: the whole request is refused, every reason listed."""

    def __init__(self, reasons: list[str]):
        self.reasons = list(reasons)
        super().__init__("site description refused: " + "; ".join(self.reasons))


# ---- validating ----------------------------------------------------------------------------------------------

def _number(x) -> bool:
    """A finite number (not true/false, which Python counts as numbers; not a whole number too big for a float)."""
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return False
    try:
        return math.isfinite(x)
    except OverflowError:
        return False


class _Checker:
    def __init__(self):
        self.reasons = []

    def no(self, where: str, why: str) -> None:
        self.reasons.append(f"{where}: {why}")

    def fields(self, value, kind: str, where: str) -> bool:
        """`value` is an object holding exactly `kind`'s fields (every required one, none it doesn't know)."""
        if not isinstance(value, dict):
            self.no(where, f"should be an object, not {_kind(value)}")
            return False
        table = OBJECTS[kind]
        for k in sorted(set(value) - set(table), key=repr):
            self.no(where, f"unknown field {k!r}")
        for k in (k for k, required in table.items() if required and k not in value):
            self.no(where, f"missing field {k!r}")
        return True

    def text(self, value, where: str, empty: bool = True) -> None:
        if not isinstance(value, str):
            self.no(where, f"should be text, not {_kind(value)}")
        elif not empty and not value.strip():
            self.no(where, "should not be empty")

    def flag(self, value, where: str, null: bool = False) -> None:
        if not (isinstance(value, bool) or (null and value is None)):
            self.no(where, f"should be true or false{' or null' if null else ''}, not {_kind(value)}")

    def items(self, value, where: str) -> list:
        if not isinstance(value, list):
            self.no(where, f"should be a list, not {_kind(value)}")
            return []
        return value

    def point(self, value, n: int, where: str) -> bool:
        if not (isinstance(value, list) and len(value) == n):
            self.no(where, f"should be a point of {n} numbers")
            return False
        bad = [i for i, x in enumerate(value) if not _number(x)]
        if bad:
            self.no(where, "should be finite numbers (no NaN, no infinity, no text)")
            return False
        return True

    def ring(self, value, where: str) -> None:
        """A face's outline or hole: at least 3 points, each [x, y, z]."""
        points = self.items(value, where)
        for i, p in enumerate(points):
            self.point(p, 3, f"{where}[{i}]")
        if isinstance(value, list) and len(points) < 3:
            self.no(where, f"has {len(points)} point{'s' if len(points) != 1 else ''}: a face needs at least 3")

    def problem(self, value, where: str) -> None:
        if not self.fields(value, "problem", where):
            return
        code, args = value.get("code"), value.get("args")
        if not isinstance(code, str) or code not in STOPS:
            self.no(where, f"unknown problem code {code!r} (the codes are model_measurement/stops.py's)")
            return
        if not isinstance(args, dict):
            self.no(where, f"args should be an object, not {_kind(args)}")
            return
        want = set(blanks(code))
        for k in sorted(set(args) - want):
            self.no(where, f"unknown arg {k!r} for {code}")
        for k in sorted(want - set(args)):
            self.no(where, f"missing arg {k!r} for {code}")
        if any(not isinstance(v, str) for v in args.values()):
            self.no(where, "every arg should be text")
            return
        if set(args) == want:
            words = stop(code, **args)
            try:
                back = code_of(words)
            except ValueError as e:
                back = None
                if code != TOOL_WORDS:
                    self.no(where, str(e))
                    return
            if code == TOOL_WORDS:      # the tool's own words: never empty, never words the table has a code for
                if not words.strip():
                    self.no(where, "the tool's own words should not be empty")
                elif back is not None:
                    self.no(where, f"the words {words!r} are a measuring reason: send its code, {back[0]}")
            elif back != (code, args):   # its words would read back as another problem: never a mix-up
                self.no(where, f"its words {words!r} read back as {back[0]} {back[1]}, not as given")


def _kind(value) -> str:
    return {dict: "an object", list: "a list", str: "text", bool: "true/false", type(None): "null"}.get(
        type(value), "a number" if _number(value) else type(value).__name__)


def problems_of(doc) -> list[str]:
    """Every reason `doc` isn't a valid gordium.site/1 description ([] when it is)."""
    c = _Checker()
    if not c.fields(doc, "site", "site"):
        return c.reasons
    if doc.get("schema") != SCHEMA:
        c.no("schema", f"should be {SCHEMA!r}, not {doc.get('schema')!r} (a different major version is refused)")
    if "units" in doc and doc["units"] != UNITS:
        c.no("units", stop("units", units=doc["units"]) + f" (send {UNITS!r}: convert at the tool's boundary)")
    if "host" in doc and c.fields(doc["host"], "host", "host"):
        for k in HOST:
            if k in doc["host"]:
                c.text(doc["host"][k], f"host.{k}")
    ids = []
    lot = doc.get("lot")
    if lot is not None and "lot" in doc and c.fields(lot, "lot", "lot"):
        c.text(lot.get("id"), "lot.id", empty=False)
        ids.append(("lot.id", lot.get("id")))
        edges = c.items(lot.get("edges"), "lot.edges")
        corners = set()
        for i, e in enumerate(edges):
            w = f"lot.edges[{i}]"
            if not c.fields(e, "edge", w):
                continue
            c.flag(e.get("curved"), f"{w}.curved")
            pts = c.items(e.get("points"), f"{w}.points")
            if isinstance(e.get("points"), list) and len(pts) < 2:
                c.no(f"{w}.points", "a lot line needs at least 2 points")
            for k, p in enumerate(pts):
                if c.point(p, 2, f"{w}.points[{k}]"):
                    corners.add(tuple(p))
        if "edges" in lot and isinstance(lot.get("edges"), list) and len(corners) < 3:
            c.no("lot.edges", f"the lot outline has {len(corners)} different points: a lot needs at least 3")
    for i, b in enumerate(c.items(doc.get("buildings", []), "buildings")):
        w = f"buildings[{i}]"
        if not c.fields(b, "building", w):
            continue
        c.text(b.get("id"), f"{w}.id", empty=False)
        ids.append((f"{w}.id", b.get("id")))
        if "role" in b and b["role"] != "building":
            c.no(f"{w}.role", f"should be 'building', not {b['role']!r}")
        c.text(b.get("layer"), f"{w}.layer")
        if "name" in b:
            c.text(b["name"], f"{w}.name")
        if b.get("floor") is not None and not _number(b["floor"]):
            c.no(f"{w}.floor", "should be a finite number (the floor block's height drawn, ft) or null")
        for k, f in enumerate(c.items(b.get("faces"), f"{w}.faces")):
            fw = f"{w}.faces[{k}]"
            if not c.fields(f, "face", fw):
                continue
            c.ring(f.get("points"), f"{fw}.points")
            for h, hole in enumerate(c.items(f.get("holes", []), f"{fw}.holes")):
                c.ring(hole, f"{fw}.holes[{h}]")
        for k, p in enumerate(c.items(b.get("problems"), f"{w}.problems")):
            c.problem(p, f"{w}.problems[{k}]")
    for i, u in enumerate(c.items(doc.get("unsent", []), "unsent")):
        w = f"unsent[{i}]"
        if not c.fields(u, "unsent", w):
            continue
        c.text(u.get("id"), f"{w}.id", empty=False)
        ids.append((f"{w}.id", u.get("id")))
        c.text(u.get("layer"), f"{w}.layer")
        c.text(u.get("kind"), f"{w}.kind", empty=False)
        if "problem" in u:
            c.problem(u["problem"], f"{w}.problem")
    for i, o in enumerate(c.items(doc.get("left_out", []), "left_out")):
        w = f"left_out[{i}]"
        if not c.fields(o, "left_out", w):
            continue
        c.text(o.get("id"), f"{w}.id", empty=False)
        ids.append((f"{w}.id", o.get("id")))
        if o.get("layer") is not None:
            c.text(o["layer"], f"{w}.layer")
        for k in ("could_be_building", "ground_like", "context"):
            c.flag(o.get(k), f"{w}.{k}")
        c.flag(o.get("touching"), f"{w}.touching", null=True)
        if "slab" in o and o["slab"] not in SLAB_KINDS:
            c.no(f"{w}.slab", f"should be one of {', '.join(SLAB_KINDS)}, not {o['slab']!r}")
        if "name" in o:
            c.text(o["name"], f"{w}.name")
    if "grade" in doc and c.fields(doc["grade"], "grade", "grade"):
        g = doc["grade"]
        if g.get("source") not in GRADE_SOURCES:
            c.no("grade.source", f"should be one of {', '.join(GRADE_SOURCES)}, not {g.get('source')!r}")
        pts = c.items(g.get("points"), "grade.points")
        for k, p in enumerate(pts):
            c.point(p, 3, f"grade.points[{k}]")
        if isinstance(g.get("points"), list) and (g.get("source") == "none") != (not pts):
            c.no("grade", "no points goes with source 'none', and source 'none' with no points")
    if "inventory_complete" in doc:
        c.flag(doc["inventory_complete"], "inventory_complete")
    for k, p in enumerate(c.items(doc.get("problems", []), "problems")):
        c.problem(p, f"problems[{k}]")
    seen = {}
    for where, i in ids:
        if isinstance(i, str):
            if i in seen:
                c.no(where, f"the id {i!r} is used twice (also {seen[i]}): every id must be unique")
            seen.setdefault(i, where)
    return c.reasons


def loads(text: str):
    """JSON text read strictly: a key given twice in one object is refused (Python's reader would keep the last one
    without a word, so one of the two would be dropped unseen)."""
    def pairs(items):
        seen, twice = {}, []
        for k, v in items:
            if k in seen:
                twice.append(k)
            seen[k] = v
        if twice:
            raise SiteRefused([f"the key {k!r} is given twice in one object" for k in twice])
        return seen
    return json.loads(text, object_pairs_hook=pairs)


def validate(doc) -> None:
    """Refuse (SiteRefused) anything that isn't exactly a gordium.site/1 description."""
    reasons = problems_of(doc)
    if reasons:
        raise SiteRefused(reasons)


# ---- converting ----------------------------------------------------------------------------------------------

def _words(problem: dict) -> str:
    return words_of(problem)            # THE one way a problem becomes words (stops.py)


def _coded(words, where: str, reasons: list):
    """A problem's words as {code, args}: the measuring reason that gives them, else the design tool's own words
    (TOOL_WORDS: words the site came with that no reason gives, such as an older Rhino plugin's own sentence for a
    block it couldn't send). Words two reasons give equally are a refusal reason (never a guess, never dropped)."""
    if not isinstance(words, str):
        return words                            # not words: the description's own check refuses it
    try:
        code, args = code_of(words)
    except ValueError as e:
        if not str(e).startswith("no "):
            reasons.append(f"{where}: {e}")
            return words
        code, args = TOOL_WORDS, {"words": words}
    return {"code": code, "args": args}


def _each_problem(value, where: str, change) -> None:
    """Every problem list in a site or description (the site's, each building's, each unsent object's one), each
    problem replaced by change(problem, where) in place."""
    if not isinstance(value, dict):
        return
    if isinstance(value.get("problems"), list):
        value["problems"] = [change(p, f"{where}problems[{k}]") for k, p in enumerate(value["problems"])]
    for i, b in enumerate(value.get("buildings") if isinstance(value.get("buildings"), list) else []):
        if isinstance(b, dict) and isinstance(b.get("problems"), list):
            b["problems"] = [change(p, f"buildings[{i}].problems[{k}]") for k, p in enumerate(b["problems"])]
    for i, u in enumerate(value.get("unsent") if isinstance(value.get("unsent"), list) else []):
        if isinstance(u, dict) and "problem" in u:
            u["problem"] = change(u["problem"], f"unsent[{i}].problem")


def _copy(value):
    """A deep copy as JSON data (tuples as lists); a value JSON can't hold is a refusal, never dropped."""
    try:
        return json.loads(json.dumps(value, allow_nan=True))
    except (TypeError, ValueError) as e:
        raise SiteRefused([f"site: not JSON data ({e})"]) from None


def to_site(doc: dict) -> dict:
    """A valid description (refused otherwise) as the site the measuring reads: the description itself, without
    `schema` and each building's `role` (always "building"), each problem in words as stop() gives them. Every
    other field is kept as it is (grade, unsent, left_out, inventory_complete, host, each building's layer; a
    building's name and floor and a face's holes exactly when given), so nothing in a description is dropped."""
    validate(doc)
    site = _copy({k: v for k, v in doc.items() if k != "schema"})
    for b in site["buildings"]:
        del b["role"]
    _each_problem(site, "", lambda p, where: _words(p))
    return site


def from_site(site: dict) -> dict:
    """A site (as to_site gives it, or read_site's with the rest added: grade, unsent, left_out,
    inventory_complete, host, each building's layer) as a gordium.site/1 description: the site itself with
    `schema` and each building's role added, and each problem's words read back into its code. Whatever else the
    site holds stays in, so the description's own check refuses it (SiteRefused): a key it doesn't know, words no
    measuring reason gives, a value that isn't JSON. Never a part dropped."""
    if not isinstance(site, dict):
        raise SiteRefused([f"site: should be an object, not {_kind(site)}"])
    doc = {"schema": SCHEMA, **_copy(site)}
    if isinstance(doc.get("buildings"), list):
        doc["buildings"] = [{"id": b.get("id"), "role": "building", **b} if isinstance(b, dict) else b
                            for b in doc["buildings"]]
    reasons = []
    _each_problem(doc, "", lambda p, where: _coded(p, where, reasons))
    reasons += problems_of(doc)
    if reasons:
        raise SiteRefused(reasons)
    return doc


def from_read_site(site: dict, grade: dict, host: dict, inventory_complete: bool = False,
                   left_out: list | None = None, unsent: list | None = None) -> dict:
    """read_site's answer (model_measurement/read_3dm.py) as a description: each building on the Building layer
    (read_site reads that layer and the layers under it), with the grade, the host and what else the caller knows.
    `inventory_complete` is False unless the caller has itself looked at everything else on the lot (read_site reads
    only the lot and Building layers, so on its own it can't say nothing else is there)."""
    return from_site({**site, "buildings": [{"layer": LAYERS["building"], **b} for b in site["buildings"]],
                      "grade": grade, "host": host, "inventory_complete": inventory_complete,
                      "left_out": list(left_out or []), "unsent": list(unsent or [])})


def grade_of(facts: dict) -> dict:
    """The site description's grade from lot facts as the Rhino command sends them: the spot grades (or terrain
    points) it read, `grade_points`, under the source the facts name, `grade_from`; no points, source "none".
    Points with no source named are spot grades, as the measuring has always read them (it measures grade_points
    whatever grade_from says, and the panel calls them spot grades; facts files may leave grade_from out:
    model_measurement.project.fact_problems). A source the facts name that isn't one is refused."""
    points = facts.get("grade_points") or []
    if not points:
        return {"source": "none", "points": []}
    source = "spot" if facts.get("grade_from") is None else facts["grade_from"]
    if source not in GRADE_SOURCES[:-1]:
        raise SiteRefused([f"grade: {len(points)} grade points given, but grade_from is {source!r} "
                           f"(one of {', '.join(GRADE_SOURCES[:-1])})"])
    return {"source": source, "points": [list(p) for p in points]}


def read_model(path, facts: dict, inventory_complete: bool = False) -> dict:
    """A .3dm (the lot and Building layers, read_site) as a site description, for recording fixtures and for a
    tool that sends a file: its grade from the facts (grade_of), the host its file. Nothing else on the lot is
    looked at, so `inventory_complete` stays False (every building's measuring then needs review) unless the caller
    says it has looked itself."""
    import rhino3dm as r
    from model_measurement.read_3dm import read_site
    model = r.File3dm.Read(str(path))
    units = str(model.Settings.ModelUnitSystem).split(".")[-1] if model is not None else "unreadable"
    host = {"name": "rhino3dm", "version": r.__version__, "document": Path(path).name, "model_units": units}
    return from_read_site(read_site(Path(path), facts), grade_of(facts), host, inventory_complete)


# ---- the checker's own requests through the description -----------------------------------------------------
# Since PR 4 of the tidy-up, check() and start() send what they read through a description and back (JSON text and
# all), so Rhino's check takes the path another design tool's will: check_site / start_site in the worker.

LEFT_OUT_EXTRAS = ("not_included", "touching", "ground_like", "context_left_out")   # check()'s extras, before
ADVICE = "left_out_advice"     # extras: {left-out object id: what the architect can do so it can be measured}, the
                                # host's own words (Rhino: a linked file to reload, rhino_logic.linked_file_advice)
UNSENT_BUILDING = "Building layer"   # the building every unsent object's problem is measured on (check()'s, before)


def legacy_description(site: dict, facts: dict, building_problems=None, extras=None, host=None) -> dict:
    """check()'s request as a description: the model as read_site read it, the facts' grade (grade_of), what the
    Rhino command couldn't send (`building_problems`, its words, each an unsent object) and the objects on the lot
    it left out (`extras`: not_included, and which of them touch the building, look like the ground, are on the
    neighbourhood's layers). The left-out list is taken as the whole of it (inventory_complete), as check() always
    has: the Rhino command looks at everything on the lot; a file checked from the command line has only its lot
    and Building layers read. Ids in the extras' sub-lists that aren't left out are refused, never dropped."""
    extras = extras or {}
    ids = list(extras.get("not_included") or [])
    stray = sorted({str(i) for k in LEFT_OUT_EXTRAS[1:] for i in (extras.get(k) or [])} - {str(i) for i in ids})
    if stray:
        raise SiteRefused([f"extras: {', '.join(stray)} named as touching, ground-like or on the neighbourhood's "
                           "layers, but not among the objects left out (not_included)"])
    touching = extras.get("touching")
    left_out = [{"id": i, "layer": None, "could_be_building": True,
                 "touching": None if touching is None else i in touching,       # not known: counts as touching
                 "ground_like": i in (extras.get("ground_like") or []),
                 "context": i in (extras.get("context_left_out") or [])} for i in ids]
    unsent = [{"id": f"{UNSENT_BUILDING}#{k}", "layer": LAYERS["building"], "kind": "unknown", "problem": words}
              for k, words in enumerate(building_problems or [], 1)]
    return from_read_site(site, grade_of(facts), host or {"name": "", "version": "", "document": "", "model_units": ""},
                          inventory_complete=True, left_out=left_out, unsent=unsent)


def for_measuring(site: dict, facts: dict, extras: dict | None = None) -> tuple[dict, dict, dict]:
    """A description's site (to_site) as check_site reads it: (the site the measuring reads, the facts with the
    description's grade, the extras with its left-out objects). Every unsent object's problem goes on one building
    (UNSENT_BUILDING), so every building measure needs review; inventory_complete false puts a problem on every
    building. The grade and the left-out objects come from the description only: facts naming grade points, a
    grade_from other than the description's grade source, or extras naming left-out objects or slabs are refused
    (two sources for one thing), never merged. A left-out slab marked a patio or a driveway (SLABS_EXEMPT) is not an
    object that may be a building, so it is in none of the left-out lists; every slab (each {id, slab, name}) is
    handed to the view as extras[SITE_SLABS], only when there is one. The left-out objects standing apart that could
    be a structure (each {id, name}) are handed to it as extras[STANDING_APART] whenever one is left out."""
    extras = dict(extras or {})
    reasons = [f"extras: {k} belongs in the site description (left_out), not the extras" for k in LEFT_OUT_EXTRAS
               + (SITE_SLABS, STANDING_APART) if k in extras]
    if "grade_points" in facts:
        reasons.append("facts: grade_points belong in the site description (grade), not the facts")
    grade = site["grade"]
    if grade["source"] != "none" and facts.get("grade_from") not in (None, grade["source"]):
        reasons.append(f"facts: grade_from is {facts['grade_from']!r} but the site's grade is {grade['source']!r}")
    if reasons:
        raise SiteRefused(reasons)
    buildings = [{k: v for k, v in b.items() if k != "layer"} for b in site["buildings"]]
    if site["unsent"]:
        buildings.append({"id": UNSENT_BUILDING, "faces": [], "problems": [u["problem"] for u in site["unsent"]]})
    if not site["inventory_complete"]:
        buildings = [{**b, "problems": b["problems"] + [stop("inventory_incomplete")]} for b in buildings]
        if not buildings:                    # none sent: what wasn't could still be a building (never "0 stories")
            buildings = [{"id": UNSENT_BUILDING, "faces": [], "problems": [stop("inventory_incomplete")]}]
    facts = dict(facts)
    if grade["source"] != "none":
        facts["grade_points"] = grade["points"]
        if grade["source"] != "spot":            # spot grades are what grade points are when no source is named
            facts["grade_from"] = grade["source"]
    left_out = site["left_out"]
    # a patio or a driveway marked so is not a building: listed in the description (traced), never measured nor
    # counted as an object that may be one; an unmarked slab is both left out and named (SITE_SLABS) for its rows
    measured_out = [o for o in left_out if o.get("slab") not in SLABS_EXEMPT]
    advice = extras.get(ADVICE)
    if advice is not None:                   # words for the architect, by left-out object: never a decision's input
        if not isinstance(advice, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip()
                                                   for k, v in advice.items()):
            raise SiteRefused([f"extras: {ADVICE} is {{object id: the words saying what to do about it}}"])
        stray = sorted(set(advice) - {o["id"] for o in left_out})
        if stray:
            raise SiteRefused([f"extras: {', '.join(stray)} given advice ({ADVICE}) but not among the objects left "
                               "out (the site description's left_out)"])
    extras.update(not_included=[o["id"] for o in measured_out],
                  touching=[o["id"] for o in measured_out if o["touching"] is not False],
                  ground_like=[o["id"] for o in measured_out if o["ground_like"]],
                  context_left_out=sorted(o["id"] for o in measured_out if o["context"]))
    if measured_out:                         # absent when nothing is left out: every request without one as before
        extras[STANDING_APART] = [{"id": o["id"], "name": o.get("name")} for o in measured_out
                                  if o["touching"] is False and o["could_be_building"]]
    slabs = [{"id": o["id"], "slab": o["slab"], "name": o.get("name")} for o in left_out if o.get("slab")]
    if slabs:                                # absent when there are none: every request without one as before
        extras[SITE_SLABS] = slabs
    return {"units": site["units"], "lot": site["lot"], "buildings": buildings, "problems": site["problems"]}, facts, extras


def through_json(doc: dict) -> dict:
    """A description as another design tool would send it: written as JSON text and read back strictly."""
    return loads(json.dumps(doc, allow_nan=False))
