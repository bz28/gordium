"""Golden outputs: what the checker answers today, kept so a change that should not change any answer (a tidy-up, a
move of code to another file) can prove it didn't, to the last character.

    python -m design_checker.goldens --check           CI: every case run again; each answer must equal its golden
    python -m design_checker.goldens --write           writes the goldens again (only when an answer SHOULD change)
    python -m design_checker.goldens --check --only scenarios/   only the cases whose name starts with this

The cases (`cases()`): the worker's `check` and `start` on both 106 Ithaca Rd models (and `start` with each of its
options), every hand-worked scenario as drawn and after its edit (`then`), the deep-run sites the same way, `start`
on each scenario's and site's lot, the stress test's six lots and STRESS_DESIGNS of its random designs from a fixed
seed (the stress generator's own designs: tests/stress/generate.py), and `options`, `sample_site` and `facts`.

Each answer is written as canonical JSON (`canonical_text`): keys sorted, ASCII only, every number rounded to
PLACES decimal places (a millionth of a foot: far below anything Gordium shows, far above the last-digit noise one
computer's maths library can give another's), -0.0 written 0.0, and any temporary folder or this checkout's own
folder replaced by a fixed word. The answers carry no clock time or date (checked: `check` and `start` have none).
The canonicalising is done here, never in the checker: what is golden is the checker's own answer.

The goldens (test_data/goldens/): `manifest.json`, one sha256 per case and per top-level part of its answer (which
part changed is readable in a diff), and `outputs.jsonl.xz`, every case's full canonical answer (compressed), so
`--check` can say exactly which values changed.

Shapes on another kind of computer (`same_shape`): the sha256 is the answer on the computer that wrote the goldens
(an Apple-chip Mac). An Intel or AMD computer (CI's Linux and Windows), with the very same library versions (pinned
in pyproject.toml), rounds a few sums differently in the last binary digit (other machine instructions for the
same maths), and where two curves of an outline nearly coincide (the round corners of two yards' offsets around
the same lot corner: the stress test's jog lot) the overlay can then keep a different few of the many
near-identical crossing points: the shape is the same, its list of points is not. (Seen on CI's Linux, and on the
Mac itself running an Intel build of Python: the same 34 jog-lot stress designs and nothing else.) So an answer
whose sha256 differs is still its golden when every value other than a shape's points is identical (every
verdict, status, word, id and number, to PLACES) and each list of plan points (x, y) under one of SHAPE_KEYS is
the same line as its golden's (same_line: from the same end to the same end, no point of either farther than
GEOMETRY_TOL from the other, the same length and enclosed area). `--check` says how many answers matched that
way. Any other difference fails as before."""

import argparse
import hashlib
import importlib.util
import json
import lzma
import math
import random
import sys
import tempfile
from pathlib import Path

from rule_format import published
from rule_format.place import plugin_place
from rule_format.rulebook import REPO, _jsonl_rows, utf8_console

PLACES = 6
# ft: how far a shape's points may be from its golden's line on another kind of computer (`same_shape`): a
# thousandth of the measuring's own "the same point" distance (model_measurement measure.TOL, 0.01 ft), and ten
# times the rounding step (a millionth of a foot), so the two sides' rounding (up to 0.71 millionths each) never
# trips it. Seen between an Apple-chip Mac and an Intel one: 0.76 millionths at most (the 34 jog-lot designs).
GEOMETRY_TOL = 1e-5
STRESS_SEED = 20261105
STRESS_DESIGNS = 200
FOLDER = REPO / "test_data" / "goldens"
MANIFEST = "manifest.json"
OUTPUTS = "outputs.jsonl.xz"
STRESS = REPO / "packages" / "design_checker" / "tests" / "stress" / "generate.py"
# start's options on the 106 Ithaca Rd models: (name, floor_to_floor, design_buffer, larger_side)
START_OPTIONS = [("start", None, 0.0, None), ("start_larger_side_left", None, 0.0, "left"),
                 ("start_larger_side_right", None, 0.0, "right"), ("start_buffer_1ft_floors_10ft", 10.0, 1.0, None)]


# ---- canonical JSON -------------------------------------------------------------------------------------------

def _scrubs() -> list[tuple[str, str]]:
    """(text, word) pairs: folders that differ from one computer or run to the next, each as it may be written
    (with / or \\), the longest first so a folder inside another is replaced whole."""
    out = []
    for folder, word in ((tempfile.gettempdir(), "<tmp>"), (str(REPO), "<repo>")):
        for p in {folder, str(Path(folder).resolve()), Path(folder).as_posix(), Path(folder).resolve().as_posix()}:
            out.append((p, word))
    return sorted(set(out), key=lambda pw: -len(pw[0]))


def canonical(value, scrubs=None):
    """`value` as plain JSON data, ready to compare: numbers rounded to PLACES places (-0.0 as 0.0; NaN and
    infinity as words), tuples as lists, keys as text, the folders in `scrubs` replaced."""
    scrubs = _scrubs() if scrubs is None else scrubs
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return repr(value)
        r = round(value, PLACES)
        return 0.0 if r == 0 else r
    if isinstance(value, str):
        for text, word in scrubs:
            if text in value:
                value = value.replace(text, word)
        return value
    if isinstance(value, dict):
        out = {str(k): canonical(v, scrubs) for k, v in value.items()}
        if len(out) != len(value):              # 1 and "1" would be one key: never merge two answers' parts
            raise ValueError(f"two keys written the same: {sorted(map(repr, value))}")
        return out
    if isinstance(value, (list, tuple)):
        return [canonical(v, scrubs) for v in value]
    raise TypeError(f"not JSON data: {type(value).__name__}")


def canonical_text(value) -> str:
    return json.dumps(canonical(value), sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def fingerprint(text: str) -> dict:
    """{"sha256": the whole answer's, "parts": each top-level part's} of an answer's canonical text."""
    data = json.loads(text)
    parts = {k: sha(canonical_text(v)) for k, v in data.items()} if isinstance(data, dict) else {}
    return {"sha256": sha(canonical_text(data)), "parts": parts}


# ---- the cases ------------------------------------------------------------------------------------------------

def stress_generator():
    """The stress test's generator (tests/stress/generate.py: its lots, starting houses and random edits)."""
    spec = importlib.util.spec_from_file_location("gordium_stress_generate", STRESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lot_file(points, folder: Path) -> Path:
    """A .3dm with only the lot, on the Site layer (as the stress generator writes one): what `start` reads."""
    path = Path(folder) / "lot.3dm"
    stress_generator()._lot_file({"points": [tuple(p[:2]) for p in points]}, path)
    return path


def _start_on(points, facts, **options) -> dict:
    from design_checker.check import start
    with tempfile.TemporaryDirectory() as tmp:
        return start(_lot_file(points, Path(tmp)), facts, **options)


def _sited(prefix: str, folder: Path) -> dict:
    """Each scenario (or deep-run site) in `folder`: check as drawn, check after its edit, start on its lot."""
    from design_checker import scenarios
    from design_checker.check import check_site
    out = {}
    for path in scenarios.paths(folder):
        sc = scenarios.load(path)
        name = f"{prefix}/{path.stem}"

        def checked(moved, sc=sc):
            site, facts, extras = scenarios.site(sc, moved)
            return check_site(site, facts, extras=extras)
        out[f"{name}/check_as_drawn"] = lambda checked=checked: checked(False)
        if sc.get("then"):
            out[f"{name}/check_then"] = lambda checked=checked: checked(True)
        out[f"{name}/start"] = lambda sc=sc: _start_on(sc["lot"]["points"], scenarios.facts(sc))
    return out


def stress_cases(designs: int = STRESS_DESIGNS, seed: int = STRESS_SEED) -> list[dict]:
    """The stress generator's random cases from the fixed seed (the same designs on every computer)."""
    gen = stress_generator()
    rng = random.Random(seed)
    return [gen.random_case(rng) for _ in range(designs)]


def cases() -> dict:
    """{case name: a function giving its answer}, in name order."""
    from model_measurement.project import fact_problems, load_facts
    from design_checker.check import check, check_site, options, sample_site, start
    place = plugin_place()
    out = {}
    sample = place.test_sites / "106_ithaca_rd"
    for model in ("model", "spreadsheet_design_model"):
        path, facts = sample / f"{model}.3dm", sample / f"{model}_facts.yaml"
        out[f"106_ithaca_rd/{model}/check"] = lambda path=path, facts=facts: check(path, load_facts(facts))
        for label, f2f, buffer, side in START_OPTIONS:
            out[f"106_ithaca_rd/{model}/{label}"] = (lambda path=path, facts=facts, f2f=f2f, buffer=buffer, side=side:
                                                     start(path, load_facts(facts), f2f, buffer, side))
        out[f"106_ithaca_rd/{model}/facts"] = lambda facts=facts: {"problems": fact_problems(load_facts(facts))}
    out["worker/options"] = lambda: options(place.jurisdiction)
    out["worker/sample_site"] = sample_site
    out.update(_sited("scenarios", place.test_sites / "scenarios"))
    out.update(_sited("deep_run", place.test_sites / "deep_run"))
    gen = stress_generator()
    for lot in gen.LOTS:
        out[f"stress/lot_{lot}/start"] = lambda lot=lot: _start_on(gen.lot(lot)["points"], gen.lot_facts(gen.lot(lot)))
    for k, case in enumerate(stress_cases()):
        def checked(case=case):
            design, done = gen.build(case["lot"], case["edits"])
            return {"lot": case["lot"], "edits": done,
                    "check": check_site(gen.gordium_site(design), gen.gordium_facts(design))}
        out[f"stress/design_{k:03d}"] = checked
    return dict(sorted(out.items()))


# ---- writing and checking -------------------------------------------------------------------------------------

def run(only: str = "") -> dict:
    """{case name: its canonical answer (text)} for every case whose name starts with `only`. A case that raises
    is golden too: its error (type and words)."""
    out = {}
    for name, fn in cases().items():
        if not name.startswith(only):
            continue
        try:
            value = fn()
        except Exception as e:                    # noqa: BLE001  (an error is an answer: it must stay the same)
            value = {"error": f"{type(e).__name__}: {e}"}
        out[name] = canonical_text(value)
    return out


def write(texts: dict, folder: Path = FOLDER) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"about": "python -m design_checker.goldens: every case's answer, canonical JSON, as sha256",
                "places": PLACES, "stress_seed": STRESS_SEED, "stress_designs": STRESS_DESIGNS,
                "cases": {name: fingerprint(t) for name, t in sorted(texts.items())}}
    (folder / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    # one line per case, {"answer", "case"} (keys in order), the answer its canonical text as it is
    lines = "".join('{"answer":%s,"case":%s}\n' % (t, json.dumps(n, ensure_ascii=True)) for n, t in sorted(texts.items()))
    (folder / OUTPUTS).write_bytes(lzma.compress(lines.encode("ascii"), preset=9))


def stored(folder: Path = FOLDER) -> tuple[dict, dict]:
    """(the manifest's cases, {case name: its stored answer}) of the committed goldens."""
    manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))["cases"]
    rows = _jsonl_rows(lzma.decompress((folder / OUTPUTS).read_bytes()))     # (rulebook.read_jsonl's reader)
    return manifest, {row["case"]: row["answer"] for row in rows}


# the answer's keys whose lists of (x, y) are shapes (lines and outlines in plan): only these may match as shapes
SHAPE_KEYS = frozenset({"outline", "holes", "buildable", "buildable_cautious", "footprint", "points",
                        "measured_points", "required_lines", "street_line", "lot"})


def _plan_points(v) -> bool:
    """Whether `v` is a list of plan points: two or more [x, y], each a number (never true or false)."""
    return isinstance(v, list) and len(v) >= 2 and all(
        isinstance(p, list) and len(p) == 2 and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in p)
        for p in v)


def same_line(a: list, b: list, tol: float = GEOMETRY_TOL) -> bool:
    """Whether two lists of plan points are the same line within `tol`, each the line through its points in order:
    - each end at the other's same end (a line drawn the other way round is not the same line);
    - every point of each line within `tol` of the other line (the Hausdorff distance at most `tol`, tested exactly:
      each line inside the other grown by `tol`, so a stretch one skips, however short, counts);
    - the same length, and the same area to the left of the line closed back to its start, each within `tol` (per
      foot of length, for the area): a line doubling back on itself, or a closed outline wound the other way, is
      not the same line though it covers the same ground.
    (Seen between an Apple-chip Mac and an Intel one: 0.76 millionths of a foot apart, lengths 1e-11 ft apart.)"""
    import shapely
    if math.dist(a[0], b[0]) > tol or math.dist(a[-1], b[-1]) > tol:
        return False
    la, lb = shapely.LineString(a), shapely.LineString(b)
    if abs(la.length - lb.length) > tol or abs(_area(a) - _area(b)) > tol * max(la.length, lb.length, 1.0):
        return False
    return bool(lb.buffer(tol).covers(la) and la.buffer(tol).covers(lb))


def _area(points) -> float:
    """The signed area the points enclose, closed back to the first (shoelace: positive anticlockwise)."""
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1])) / 2


def shape_distance(a: list, b: list) -> float:
    """How far apart two lists of plan points are, for the message when they are not the same line: the farther of
    their two ends from the other's same end, or the Hausdorff distance between them (shapely), if farther."""
    import shapely
    ends = max(math.dist(a[0], b[0]), math.dist(a[-1], b[-1]))
    return max(ends, shapely.hausdorff_distance(shapely.LineString(a), shapely.LineString(b), densify=0.01))


def same_shape(old, new, key: str = "") -> bool:
    """Whether two canonical answers are the same but for how a shape's points fall: every value identical, except
    that a list of plan points under one of SHAPE_KEYS may have other points (even another number of them) if it
    is the same line, within GEOMETRY_TOL (same_line; module docstring: shapes on another kind of computer).
    Verdicts, statuses, words, ids and every other number must be exactly as golden."""
    if key in SHAPE_KEYS and _plan_points(old) and _plan_points(new):
        return old == new or same_line(old, new)
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(same_shape(old[k], new[k], k) for k in old)
    if isinstance(old, list) and isinstance(new, list):          # (a list of shapes: each under its list's key)
        return len(old) == len(new) and all(same_shape(x, y, key) for x, y in zip(old, new))
    return type(old) is type(new) and old == new


def differences(old, new, path: str = "", limit: int = 8) -> list[str]:
    """Where two answers differ: up to `limit` lines "path: old -> new" (a shape only where it is farther than
    GEOMETRY_TOL from its golden's line: same_shape)."""
    out = []

    def walk(a, b, p):
        if len(out) >= limit:
            return
        if p.rsplit("/", 1)[-1].split("[")[0] in SHAPE_KEYS and _plan_points(a) and _plan_points(b):
            # a shape: shown only if it moved (how far), not its point list
            if a != b and not same_line(a, b):
                out.append(f"{p}: {len(a)} points -> {len(b)}, not the same line (up to {shape_distance(a, b):.3g} ft "
                           f"from the golden's): {_short(a)} -> {_short(b)}")
        elif isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                if k not in a or k not in b:
                    out.append(f"{p}/{k}: {'(none)' if k not in a else _short(a[k])} -> "
                               f"{'(none)' if k not in b else _short(b[k])}")
                else:
                    walk(a[k], b[k], f"{p}/{k}")
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{p}[{i}]")
        elif a != b:
            out.append(f"{p}: {_short(a)} -> {_short(b)}")
    walk(old, new, path)
    return out


def _short(v) -> str:
    t = json.dumps(v, ensure_ascii=True)
    return t if len(t) <= 100 else t[:97] + "..."


def check(texts: dict, folder: Path = FOLDER, only: str = "", shaped: list | None = None) -> list[str]:
    """Why the answers don't match the goldens, or [] when every one is the same: a case missing on either side,
    or an answer whose sha256 differs (with the parts and the values that changed), unless it is its golden but for
    how a shape's points fall (`same_shape`; its name is added to `shaped`, when given)."""
    manifest, answers = stored(folder)
    manifest = {n: m for n, m in manifest.items() if n.startswith(only)}
    problems = [f"{n}: no golden (a new case: --write)" for n in sorted(set(texts) - set(manifest))]
    problems += [f"{n}: in the goldens but not run (a case removed: --write)" for n in sorted(set(manifest) - set(texts))]
    for name in sorted(set(texts) & set(manifest)):
        if sha(texts[name]) == manifest[name]["sha256"]:
            continue
        new = json.loads(texts[name])
        if name in answers and same_shape(answers[name], new):
            if shaped is not None:
                shaped.append(name)
            continue
        parts = fingerprint(texts[name])["parts"]
        changed = sorted(k for k in set(parts) | set(manifest[name]["parts"]) if parts.get(k) != manifest[name]["parts"].get(k))
        problems.append(f"{name}: differs (parts: {', '.join(changed) or 'the whole answer'})")
        problems += ["    " + d for d in differences(answers.get(name), new)]
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m design_checker.goldens")
    parser.add_argument("--check", action="store_true", help="every answer must equal its golden")
    parser.add_argument("--write", action="store_true", help="write the goldens again")
    parser.add_argument("--only", default="", help="only the cases whose name starts with this")
    args = parser.parse_args(argv)
    if args.check == args.write:
        parser.error("give --check or --write")
    if args.write and args.only:
        parser.error("--write writes every case (no --only)")
    # a missing law certificate is published first (rule_format/published.py); before writing goldens a stale one too,
    # since a check reads no stale law (every row of it needs review) and those rows would be written as the goldens.
    # A law that can't be published stops a write: its rows would be written as needs review
    notes = published.ensure(missing_only=not args.write)
    for note in notes:
        print(f"– {note}")
    if args.write and notes:
        print("✗ not written: a law can't be published (above), so its rows would be written as needs review")
        return 1
    texts = run(args.only)
    if args.write:
        write(texts)
        print(f"wrote {len(texts)} golden answers to {FOLDER.relative_to(REPO).as_posix()}/")
        return 0
    shaped = []
    problems = check(texts, only=args.only, shaped=shaped)
    for p in problems:
        print("✗ " + p)
    if shaped:
        print(f"{len(shaped)} answers equal their goldens but for how a shape's points fall (every other value the "
              f"same; each shape within {GEOMETRY_TOL} ft of its golden's: another kind of computer's maths), e.g. "
              f"{shaped[0]}")
    same = "every answer equals its golden" + (f" ({len(shaped)} as shapes, above)" if shaped else "")
    print(f"{len(texts)} cases: " + (same if not problems else
                                     f"{sum(1 for p in problems if not p.startswith('    '))} differ"))
    return 1 if problems else 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
