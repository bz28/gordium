"""The golden permit sheets: every test house's sheets, built fresh and compared with the committed ones.

    python -m permit_sheets --check     # every golden matches a fresh build (a test runs this too)
    python -m permit_sheets --write     # record them again, only when an answer should change

Each house is checked with the same plain test lot (a 60 x 110 ft lot in Ithaca's R-1b, one box of a house: zoning
isn't what these sheets are about) through source.checked, the command's own fingerprint-guarded way in. The
fingerprints of the rules and of Gordium's code change with any change to either, so the goldens record the ones
they were made with (manifest.json) and a fresh build prints those, once the guard has passed with today's: every
other word, number and line must be the same.
"""

import hashlib
import json

import yaml
from openpyxl import load_workbook

from design_checker.check import check_site
from rule_export.workbook import contents
from rule_format.place import only_place
from rule_format.rulebook import REPO

from .build import files, workbook
from .source import checked

GOLDENS = REPO / "test_data/goldens/permit_sheets"
# the test lot's place comes from the registry (only Ithaca has settings today), never named in shared code
FACTS = {"jurisdiction": only_place("the permit-sheet goldens", "name the test lot's place first").jurisdiction,
         "street_line": [[[0, 0], [60, 0]]],
         "corner_lot": False, "lot_surveyed": True, "ground_is_flat": True, "grade_elevation": 0,
         "use": "one_family_detached", "stories": 2, "zone": "R-1b"}
DATE = "2026-11-15"
HOUSES = {     # golden folder: (interior description, or None for no rooms drawn yet; title block project)
    "0_no_rooms_yet": (None, "Made-up house: massing only, no rooms drawn yet"),
    "1_ranch_compliant": ("test_data/interior_houses/1_ranch_compliant/house.yaml", "Made-up house 1: ranch"),
    "2_two_story_small_window": ("test_data/interior_houses/2_two_story_small_window/house.yaml",
                                 "Made-up house 2: two-story, small window"),
    "3_tall_riser": ("test_data/interior_houses/3_tall_riser/house.yaml", "Made-up house 3: tall riser"),
    "4_loft": ("test_data/interior_houses/4_loft/house.yaml", "Made-up house 4: sleeping loft"),
    "5_basement_window_well": ("test_data/interior_houses/5_basement_window_well/house.yaml",
                               "Made-up house 5: basement window well"),
    "orangetown_ny_80_south_william": ("test_data/real_houses/orangetown_ny_80_south_william/house.yaml",
                                       "Bennington model (transcribed from public drawings)"),
}
# each house's own story count (Ithaca's Stories, as the architect types it): the test lot's FACTS give 2, the
# massing box's; a one-story house says 1, so its "no stairs" is taken (model_measurement.interior's
# _stairs_against_floors refuses it beside two or more stories) and the ranch is a compliant one-story example
STORIES = {"1_ranch_compliant": 1}
ADDRESS = {"orangetown_ny_80_south_william": "80 South William Street, Lot 2, Pearl River (Town of Orangetown), NY; "
                                             "checked as if in Ithaca's R-1b on a test lot"}


def _box(x0, y0, x1, y1, z0, z1):
    ring = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    walls = [{"points": [[*ring[i], z0], [*ring[(i + 1) % 4], z0], [*ring[(i + 1) % 4], z1], [*ring[i], z1]]}
             for i in range(4)]
    return {"id": "house", "faces": [{"points": [[x, y, z0] for x, y in ring]},
                                     {"points": [[x, y, z1] for x, y in ring]}, *walls], "problems": []}


def site() -> dict:
    """The test lot and its house box, in feet (the measuring's site form)."""
    pts = [(0, 0), (60, 0), (60, 110), (0, 110)]
    return {"units": "ft", "lot": {"id": "lot", "edges": [{"points": [list(pts[i]), list(pts[(i + 1) % 4])],
                                                           "curved": False} for i in range(4)]},
            "buildings": [_box(10, 25, 40, 75, 0, 30)], "problems": []}


def facts_of(name: str) -> dict:
    """The test lot's facts for one house: FACTS, with the house's own story count (STORIES) where it has one."""
    return {**FACTS, **({"stories": STORIES[name]} if name in STORIES else {})}


def interior_of(name: str):
    path = HOUSES[name][0]
    return None if path is None else yaml.safe_load((REPO / path).read_text(encoding="utf-8"))


def project_of(name: str) -> dict:
    return {"title": HOUSES[name][1], "address": ADDRESS.get(name, "Made-up house on a test lot"), "date": DATE}


def gathered(name: str, recorded: dict | None = None) -> dict:
    """The house checked (through the guarded way in) and gathered; with `recorded`, the fingerprints printed are
    the recorded ones (the guard has already passed with today's)."""
    house = interior_of(name)
    got = checked(lambda: check_site(site(), facts_of(name), name=name, today=DATE, interior=house), house)
    if recorded:
        got["worker_fingerprint"] = recorded["worker_fingerprint"]
        for law in got["laws"]:
            law["fingerprints"] = {k: recorded["rules_fingerprints"].get(k, v) for k, v in law["fingerprints"].items()}
    return got


def build(name: str, recorded: dict | None = None) -> tuple[dict, object, dict]:
    """(files, workbook, manifest) for one house."""
    got = gathered(name, recorded)
    out = files(got, project_of(name))
    manifest = {"worker_fingerprint": got["worker_fingerprint"],
                "rules_fingerprints": {k: v for law in got["laws"] for k, v in law["fingerprints"].items()},
                "files": {n: hashlib.sha256(b).hexdigest() for n, b in sorted(out.items())}}
    return out, workbook(got, project_of(name)), manifest


KEPT = ("permit_sheets.pdf", "code_analysis.csv", "escape_window_schedule.csv")   # committed; SVGs are the same marks


def write(name: str) -> None:
    folder = GOLDENS / name
    folder.mkdir(parents=True, exist_ok=True)
    out, wb, manifest = build(name)
    for n in KEPT:
        (folder / n).write_bytes(out[n])
    for n, b in out.items():
        if n.endswith(".svg") and n.split(".")[0] in ("G-001", "LS-101", "A-601"):
            (folder / n).write_bytes(b)          # one sample page of each sheet, to open in a browser
    wb.save(folder / "permit_sheets.xlsx")
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def differences(name: str) -> list[str]:
    """What differs between the committed golden and a fresh build (empty: the same)."""
    folder = GOLDENS / name
    if not (folder / "manifest.json").is_file():
        return [f"{name}: missing (python -m permit_sheets --write)"]
    recorded = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    out, wb, manifest = build(name, recorded)
    diffs = [f"{name}/{n}" for n in sorted(set(manifest["files"]) | set(recorded["files"]))
             if manifest["files"].get(n) != recorded["files"].get(n)]
    for n in KEPT + tuple(p.name for p in sorted(folder.glob("*.svg"))):
        if not (folder / n).is_file() or (folder / n).read_bytes() != out.get(n):
            diffs.append(f"{name}/{n}")
    if contents(load_workbook(folder / "permit_sheets.xlsx")) != contents(wb):
        diffs.append(f"{name}/permit_sheets.xlsx")
    return sorted(set(diffs))


def names() -> list[str]:
    return list(HOUSES)

