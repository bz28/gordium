"""Rooms: each IfcSpace as a room of the interior description (whether it is a sleeping room, its floor outline,
floor elevation and ceiling height). Every value comes from the model as stated, or is left out with its reason.

Sleeping room or not: only what the model says in words (room_words.yaml) or by the Gordium_Egress.Sleeping flag,
never from a room's size or shape. Floor, ceiling: from the space's body and its base quantities
(Qto_SpaceBaseQuantities, IFC4: Height is "from base slab without flooring to ceiling without suspended ceiling";
FinishFloorHeight "from base slab without flooring to the flooring height"; FinishCeilingHeight "from top of
flooring to the bottom of the suspended ceiling"). The README's "Rooms" section says why each is read so.
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

from ifc_reading.model import EPS, FLAT, normals, tidy

GORDIUM_SET = "Gordium_Egress"
KINDS = ("sleeping", "not_sleeping", "ask", "neutral")


@lru_cache(maxsize=1)
def words() -> dict:
    with open(Path(__file__).with_name("room_words.yaml"), encoding="utf-8") as f:
        table = yaml.safe_load(f)
    out = {}
    for kind in KINDS:
        for w in table[kind]:
            w = w.casefold()
            if w in out:
                raise ValueError(f"room_words.yaml lists {w!r} twice")
            out[w] = kind
    return out


def name_words(text) -> list[str]:
    """The text's words: Unicode-normalised (NFKC, so a decomposed "ä" is one letter), cut at every character that
    isn't a letter, casefolded."""
    if not isinstance(text, str):
        return []
    return [w.casefold() for w in re.split(r"[\W\d_]+", unicodedata.normalize("NFKC", text)) if w]


def sleeping_from_names(texts: dict, flag=None):
    """(sleeping: True | False | None, why). texts: {where: text}; flag: the model's Gordium_Egress.Sleeping."""
    table = words()
    hits = {}
    for where, text in texts.items():
        for w in name_words(text):
            hits.setdefault(table.get(w, "unlisted"), []).append(f"{where} {text!r} ({w})")
    hits.pop("neutral", None)                       # "room", "Zimmer": say nothing either way
    said = "; ".join(f"{k.replace('_', ' ')}: {', '.join(v)}" for k, v in hits.items())
    if flag is True:
        return True, f"{GORDIUM_SET}.Sleeping is true"
    if flag is False:
        if "sleeping" in hits:              # an ask word is what the flag answers; a bedroom's name it can't
            return None, f"{GORDIUM_SET}.Sleeping is false, but its name says otherwise ({said}): the architect says"
        return False, f"{GORDIUM_SET}.Sleeping is false"
    if "ask" in hits or ("sleeping" in hits and "not_sleeping" in hits) or ("not_sleeping" in hits and
                                                                           "unlisted" in hits):
        return None, f"its name doesn't settle it ({said}): the architect says (Gordium_Egress.Sleeping)"
    if "sleeping" in hits:
        return True, f"named a sleeping room: {said}"
    if "not_sleeping" in hits:
        return False, f"named a room that isn't a sleeping room: {said}"
    shown = ", ".join(f"{k} {v!r}" for k, v in texts.items() if v) or "nothing"
    return None, f"nothing in its name says what it is ({shown}): the architect says (Gordium_Egress.Sleeping)"


def names_of(model, space) -> dict:
    texts = {"LongName": space.LongName, "Name": space.Name, "ObjectType": space.ObjectType}
    for rel in getattr(space, "HasAssociations", []) or []:
        if rel.is_a("IfcRelAssociatesClassification"):
            ref = rel.RelatingClassification
            texts[f"classification {getattr(ref, 'Identification', None) or getattr(ref, 'ItemReference', '')}"
                  .strip()] = getattr(ref, "Name", None)
    return {k: v for k, v in texts.items() if isinstance(v, str) and v.strip()}


def display_name(space) -> str:
    long, short = space.LongName, space.Name
    if long and short and long != short:
        return f"{long} ({short})"
    return long or short or space.GlobalId


def read_room(model, space) -> dict:
    room = {"id": space.GlobalId, "name": display_name(space)}
    missing = {}
    info = {"entity": space.is_a(), "step_id": space.id(), "global_id": space.GlobalId}
    storey = model.storey_of(space)
    if storey is not None:
        info["storey"] = storey.Name

    texts = names_of(model, space)
    flag, where = model.prop(space, [GORDIUM_SET], "Sleeping")
    if flag is not None and not isinstance(flag, bool):     # a flag that can't be read is never left to the name
        sleeping, why = None, f"{where} is {flag!r}, not true or false: the architect says"
    else:
        sleeping, why = sleeping_from_names(texts, flag)
    info["sleeping_from"] = why
    if sleeping is None:
        missing["sleeping"] = why
    else:
        room["sleeping"] = sleeping

    tris = model.triangles(space)
    if tris is None:
        for k in ("floor", "floor_elevation", "ceiling_height"):
            missing[k] = "the space has no body shape to read"
        return _done(room, missing, info)
    n, size = normals(tris)
    real = size > 1e-12
    down = real & (n[:, 2] < -1e-9)
    up = real & (n[:, 2] > 1e-9)
    base = float(tris[:, :, 2].min())
    info["base_elevation"] = tidy(base)

    finish, where, bad = model.quantity(space, "FinishFloorHeight")
    if finish is None:
        missing["floor_elevation"] = bad or ("the space's flooring height (FinishFloorHeight) isn't given: its base "
                                             "is the slab without flooring, so the finished floor is unknown")
        floor = None
    elif finish < 0:                       # review round 5: flooring below the slab would raise the ceiling cap
        missing["floor_elevation"] = (f"{where} is {tidy(finish)} m: a flooring thickness can't be negative, so "
                                      "the finished floor is unknown")
        floor = None
    else:
        floor = base + finish
        room["floor_elevation"] = tidy(floor)
        info["floor_elevation_from"] = f"the space's base {tidy(base)} m + {where} {tidy(finish)} m"

    outline, why = _floor_outline(model, space, tris[down], base)
    if outline is None:
        missing["floor"] = why
    else:
        room["floor"] = outline
        info["floor_from"] = why

    ceiling, why = _ceiling(model, space, tris[up], floor, float(tris[:, :, 2].max()))
    if ceiling is None:
        missing["ceiling_height"] = why
    else:
        room["ceiling_height"] = ceiling
        info["ceiling_from"] = why
    return _done(room, missing, info)


def _done(room, missing, info):
    if missing:
        room["not_given"] = missing
    room["ifc"] = info
    return room


def _floor_outline(model, space, below, base):
    """The outline of the space's underside, if it is one level outline no bigger than the space's net floor area."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if not len(below):
        return None, "the space's body has no underside"
    heights = below[:, :, 2]
    if abs(float(heights.min()) - base) > FLAT:
        return None, "the space's body faces the wrong way (its underside isn't its lowest part): not read"
    if float(heights.max() - heights.min()) > FLAT:
        return None, "the space's underside isn't at one level (a step or a slope in the floor): not read yet"
    shape = unary_union([Polygon(t[:, :2]) for t in below if Polygon(t[:, :2]).area > 1e-12]).buffer(0)
    if shape.geom_type != "Polygon" or len(shape.interiors):
        return None, "the space's underside isn't one outline without holes: not read yet"
    shape = shape.simplify(EPS)
    area = shape.area
    net, where, bad = model.quantity(space, "NetFloorArea", "AREAUNIT")
    if net is None:
        return None, bad or ("the space's net floor area (NetFloorArea) isn't given, so whether its outline is inside the "
                      "finished walls (not to the rough wall or a wall's centre) can't be told")
    if area > net * (1 + 1e-6) + 1e-6:
        return None, (f"the space's outline ({tidy(area)} m²) is bigger than its stated net floor area ({where} "
                      f"{tidy(net)} m²): it may run to the rough wall, not the finished face, so it isn't the floor")
    coords = [[tidy(x), tidy(y)] for x, y in list(shape.exterior.coords)[:-1]]
    return coords, f"the space's underside at {tidy(base)} m ({tidy(area)} m², within {where} {tidy(net)} m²)"


def _ceiling(model, space, above, floor, top_of_body):
    """A flat ceiling's height above the finished floor: the model's FinishCeilingHeight, if the space's top is level
    (the lower of the two, if its top is lower)."""
    if floor is None:
        return None, "the finished floor isn't known (FinishFloorHeight), so no height above it is"
    if not len(above):
        return None, "the space's body has no top"
    tops = above[:, :, 2]
    if abs(float(tops.max()) - top_of_body) > FLAT:
        return None, "the space's body faces the wrong way (its top isn't its highest part): not read"
    if float(tops.max() - tops.min()) > FLAT:
        return None, (f"the space's top isn't level ({tidy(tops.min())} to {tidy(tops.max())} m): a sloped or "
                      "stepped ceiling isn't read yet")
    stated, where, bad = model.quantity(space, "FinishCeilingHeight")
    if stated is None:
        return None, bad or ("the finished ceiling's height (FinishCeilingHeight) isn't given: the space's top is the slab "
                      "above, without its finish, so the finished ceiling is unknown")
    top = float(tops.min()) - floor
    if stated <= 0 or top <= 0:
        return None, (f"{where} is {tidy(stated)} m and the space's top is {tidy(top)} m above the finished floor: "
                      "a ceiling must be above the floor, so it is unknown")
    height = min(stated, top)
    return tidy(height), (f"{where} {tidy(stated)} m" + (f", lowered to the space's top {tidy(top)} m above the floor"
                                                         if top < stated else ""))
