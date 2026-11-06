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
`--check` can say exactly which values changed."""

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

from rule_format.place import plugin_place
from rule_format.rulebook import REPO, _jsonl_rows, utf8_console

PLACES = 6
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


def differences(old, new, path: str = "", limit: int = 8) -> list[str]:
    """Where two answers differ: up to `limit` lines "path: old -> new"."""
    out = []

    def walk(a, b, p):
        if len(out) >= limit:
            return
        if isinstance(a, dict) and isinstance(b, dict):
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


def check(texts: dict, folder: Path = FOLDER, only: str = "") -> list[str]:
    """Why the answers don't match the goldens, or [] when every one is the same: a case missing on either side,
    or an answer whose sha256 differs (with the parts and the values that changed)."""
    manifest, answers = stored(folder)
    manifest = {n: m for n, m in manifest.items() if n.startswith(only)}
    problems = [f"{n}: no golden (a new case: --write)" for n in sorted(set(texts) - set(manifest))]
    problems += [f"{n}: in the goldens but not run (a case removed: --write)" for n in sorted(set(manifest) - set(texts))]
    for name in sorted(set(texts) & set(manifest)):
        if sha(texts[name]) == manifest[name]["sha256"]:
            continue
        new = json.loads(texts[name])
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
    texts = run(args.only)
    if args.write:
        write(texts)
        print(f"wrote {len(texts)} golden answers to {FOLDER.relative_to(REPO).as_posix()}/")
        return 0
    problems = check(texts, only=args.only)
    for p in problems:
        print("✗ " + p)
    print(f"{len(texts)} cases: " + ("every answer equals its golden" if not problems else
                                     f"{sum(1 for p in problems if not p.startswith('    '))} differ"))
    return 1 if problems else 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
