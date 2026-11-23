"""The golden answers (design_checker/goldens.py; test_data/goldens/): the canonical form is the same on every
computer and for every run, the committed goldens cover every case, and a changed answer is caught and shown. CI
compares every case (`python -m design_checker.goldens --check`, a step of its own); here, the 106 Ithaca Rd and
worker cases, which are quick."""
import json
import lzma
import shutil
import tempfile
from pathlib import Path

from design_checker import goldens
from rule_format.place import plugin_place
from rule_format.rulebook import REPO


def test_canonical_rounds_numbers_sorts_keys_and_replaces_temporary_and_checkout_folders():
    tmp = tempfile.gettempdir()
    value = {"b": [1.23456749, -0.0000001, (2, 3.0)], "a": True, "n": None, "i": 7, 3: "x",
             "path": str(Path(tmp) / "gordium_live_1.3dm"), "repo": str(REPO / "regulations"),
             "posix": (Path(tmp) / "a.3dm").as_posix(), "inf": float("inf")}
    text = goldens.canonical_text(value)
    data = json.loads(text)
    assert list(data) == sorted(data)
    assert data["b"] == [1.234567, 0.0, [2, 3.0]] and "-0.0" not in text
    assert data["a"] is True and data["n"] is None and data["i"] == 7 and data["3"] == "x"
    assert data["path"].startswith("<tmp>") and data["path"].endswith("gordium_live_1.3dm")
    assert data["posix"] == "<tmp>/a.3dm"
    assert data["repo"].startswith("<repo>") and data["inf"] == "inf"
    assert text.isascii()
    assert goldens.canonical_text({"x": "§ 325"}).isascii()


def test_numbers_closer_than_a_millionth_of_a_foot_give_the_same_golden_and_farther_ones_do_not():
    a, b, c = 12.3456781234, 12.3456781234 + 3e-14, 12.3456791234      # last-digit noise; a hundred-thousandth
    assert goldens.sha(goldens.canonical_text(a)) == goldens.sha(goldens.canonical_text(b))
    assert goldens.canonical_text(a) != goldens.canonical_text(c)


def test_the_goldens_cover_every_case_and_every_case_has_a_stored_answer():
    manifest, answers = goldens.stored()
    place = plugin_place()
    scenarios = sorted(p.stem for p in (place.test_sites / "scenarios").glob("*.yaml"))
    sites = sorted(p.stem for p in (place.test_sites / "deep_run").glob("*.yaml"))
    assert set(manifest) == set(answers) == set(goldens.cases())
    assert len([n for n in manifest if n.startswith("stress/design_")]) == goldens.STRESS_DESIGNS == 200
    assert len([n for n in manifest if n.startswith("stress/lot_")]) == 6
    for model in ("model", "spreadsheet_design_model"):
        assert {f"106_ithaca_rd/{model}/{k}" for k in ("check", "facts", *[o[0] for o in goldens.START_OPTIONS])} \
            <= set(manifest)
    for prefix, names in (("scenarios", scenarios), ("deep_run", sites)):
        for name in names:
            assert {f"{prefix}/{name}/check_as_drawn", f"{prefix}/{name}/start"} <= set(manifest)
    thens = [n for n in manifest if n.endswith("/check_then")]
    assert len(scenarios) == 18 and len(sites) == 3 and len(thens) == 3      # three B (13 to 15) since 2026-11-22, three CBD (16 to 18) since 2026-11-23
    assert not [n for n, a in answers.items() if isinstance(a, dict) and set(a) == {"error"}], \
        "a golden is a crash: the case is broken, not golden"
    # each stored answer is the one its sha256 names
    assert all(goldens.sha(goldens.canonical_text(answers[n])) == m["sha256"] for n, m in manifest.items())


def test_the_quick_cases_still_give_their_golden_answers():
    sample, worker = goldens.run("106_ithaca_rd/"), goldens.run("worker/")
    assert len(sample) == 12 and len(worker) == 2
    assert goldens.check(sample, only="106_ithaca_rd/") == goldens.check(worker, only="worker/") == []


def test_a_changed_answer_is_caught_and_says_which_part_and_value_changed(tmp_path):
    folder = tmp_path / "goldens"
    shutil.copytree(goldens.FOLDER, folder)
    texts = goldens.run("106_ithaca_rd/model/check")
    assert goldens.check(texts, folder, only="106_ithaca_rd/model/check") == []
    answer = json.loads(texts["106_ithaca_rd/model/check"])
    answer["envelope"]["height"] = 99.5
    changed = {"106_ithaca_rd/model/check": goldens.canonical_text(answer)}
    problems = goldens.check(changed, folder, only="106_ithaca_rd/model/check")
    assert problems[0].startswith("106_ithaca_rd/model/check: differs (parts: envelope")
    assert any("/envelope/height:" in p and "-> 99.5" in p for p in problems)
    # a case missing from either side is caught too
    assert goldens.check({}, folder, only="106_ithaca_rd/model/check") == [
        "106_ithaca_rd/model/check: in the goldens but not run (a case removed: --write)"]
    assert goldens.check({**texts, "new/case": "{}"}, folder, only="")[0] == "new/case: no golden (a new case: --write)"


def test_written_goldens_are_read_back_as_written(tmp_path):
    texts = {"b/case": goldens.canonical_text({"x": 1.5, "y": [1, "z"]}), "a/case": goldens.canonical_text({"e": None})}
    goldens.write(texts, tmp_path)
    manifest, answers = goldens.stored(tmp_path)
    assert list(manifest) == ["a/case", "b/case"] and answers == {n: json.loads(t) for n, t in texts.items()}
    assert goldens.check(texts, tmp_path) == []
    assert lzma.decompress((tmp_path / goldens.OUTPUTS).read_bytes()).decode("ascii").count("\n") == 2


def test_the_compressed_goldens_are_stored_as_binary_so_no_checkout_changes_their_line_endings():
    import subprocess
    out = subprocess.run(["git", "check-attr", "binary", "--", "test_data/goldens/outputs.jsonl.xz"], cwd=REPO,
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert out.strip().endswith("binary: set")


def test_two_keys_that_would_be_written_the_same_are_refused_never_merged():
    import pytest
    with pytest.raises(ValueError, match="two keys written the same"):
        goldens.canonical({1: "a", "1": "b"})


# ---- shapes on another kind of computer (goldens.same_shape) -------------------------------------------------

def _jog_design():
    """A stored stress design on the jog lot (the lot whose outline's points differ on an Intel computer)."""
    _, answers = goldens.stored()
    name = next(n for n, a in sorted(answers.items()) if n.startswith("stress/design_") and a["lot"] == "jog")
    return name, json.loads(json.dumps(answers[name]))


def _another_computers(points):
    """The same line with other points, as an Intel computer gave it: a corner's neighbours nudged by under a
    millionth of a foot, and a point that lies on the line between its neighbours dropped (182 -> 181 points)."""
    out = [list(p) for p in points]
    out[1] = [out[1][0] + 4e-7, out[1][1] - 3e-7]
    mid = next(i for i in range(1, len(out) - 1) if goldens.shape_distance(out[i - 1:i + 2:2], out[i - 1:i + 2]) < 1e-7)
    return out[:mid] + out[mid + 1:]


def test_an_answer_whose_shapes_have_other_points_on_the_same_lines_is_still_its_golden(tmp_path):
    name, answer = _jog_design()
    plan = answer["check"]["plan"]
    answer["check"]["envelope"]["outline"] = _another_computers(answer["check"]["envelope"]["outline"])
    plan["buildable"] = _another_computers(plan["buildable"])
    assert len(plan["buildable"]) == len(goldens.stored()[1][name]["check"]["plan"]["buildable"]) - 1
    text = goldens.canonical_text(answer)
    manifest, _ = goldens.stored()
    assert goldens.sha(text) != manifest[name]["sha256"]           # not the same text: the shapes' points differ
    shaped = []
    assert goldens.check({name: text}, only=name, shaped=shaped) == [] and shaped == [name]


def test_a_shape_moved_farther_than_the_tolerance_or_any_other_value_changed_still_fails():
    name, golden = _jog_design()
    moved = json.loads(json.dumps(golden))
    moved["check"]["plan"]["buildable"][5][0] += 3 * goldens.GEOMETRY_TOL        # one corner 3/100,000 ft over
    problems = goldens.check({name: goldens.canonical_text(moved)}, only=name)
    assert problems and problems[0].startswith(f"{name}: differs (parts: check)")
    assert any("/check/plan/buildable:" in p and "not the same line" in p for p in problems)
    # every value outside a shape's points must be exactly the golden's, however the shapes fall
    def verdict(a):
        rule = next(iter(sorted(a["check"]["statuses"])))
        a["check"]["statuses"][rule] = "complies" if a["check"]["statuses"][rule] != "complies" else "needs_review"

    for change in (verdict, lambda a: a.__setitem__("lot", "narrow"),
                   lambda a: a["check"]["envelope"].__setitem__("height", a["check"]["envelope"]["height"] + 1e-6)):
        other = json.loads(json.dumps(golden))
        other["check"]["plan"]["buildable"] = _another_computers(other["check"]["plan"]["buildable"])
        change(other)
        assert not goldens.same_shape(golden, other)
        assert goldens.check({name: goldens.canonical_text(other)}, only=name) != []


def test_the_same_line_is_tested_all_along_it_not_only_at_its_points():
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert goldens.same_line(square, [[0, 0], [5, 0], [10, 0], [10, 10], [0, 10]])        # a point on a side
    assert not goldens.same_line([[0, 0], [10, 0]], [[0, 0], [5, 0.001], [10, 0]])        # a thousandth of a foot
    assert not goldens.same_line([[0, 0], [10, 0], [10, 10]], [[0, 0], [10, 10]])         # a corner cut off
    # a short stretch left out (a 0.09 ft side, the line going up and back down each side instead: review round 2)
    notch = [[0, 0.5], [0, 0], [0.09, 0], [0.09, 0.5]]
    assert not goldens.same_line(notch, [[0, 0.5], [0, 0], [0, 0.045], [0.09, 0.045], [0.09, 0], [0.09, 0.5]])
    # only plan points (x, y) are shapes: 3D points, and true/false, are compared exactly
    assert not goldens.same_shape({"points": [[0, 0, 1], [1, 0, 1]]}, {"points": [[0, 0, 1], [1, 1e-7, 1]]})
    assert not goldens.same_shape({"points": [[0, True], [1, 0]]}, {"points": [[0, 1], [1, 0]]})


def test_a_line_drawn_the_other_way_round_or_doubling_back_or_a_list_that_is_not_a_shape_must_be_exact():
    line = [[47.5, 90.0], [47.5, 66.6]]
    assert goldens.same_shape({"points": line}, {"points": [[47.5, 90.0], [47.5, 70.0], [47.5, 66.6]]})
    assert not goldens.same_shape({"points": line}, {"points": line[::-1]})                    # its ends swapped
    assert not goldens.same_shape({"points": [[0, 0], [10, 0]]}, {"points": [[0, 0], [10, 0], [3, 0]]})   # back
    assert not goldens.same_line([[0, 0], [10, 0]], [[0, 0], [10, 0], [5, 0], [10, 0]])    # back and forth again
    ring = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]                                     # closed: its ends one point
    assert not goldens.same_line(ring, ring[::-1])                                           # wound the other way
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert not goldens.same_shape({"outline": square}, {"outline": square[:1] + square[1:][::-1]})   # other way round
    # pairs of numbers under any other key are not a shape: exact, even a point between two others
    assert not goldens.same_shape({"ranges": [[0, 0], [10, 0]]}, {"ranges": [[0, 0], [5, 0], [10, 0]]})
    assert goldens.same_shape({"footprint": [square]}, {"footprint": [square[:1] + [[5, 0]] + square[1:]]})


def _rows_with_margins(x, path=""):
    """Every row (a dict with a status, a measure and a worked-out margin) anywhere in an answer, with its path."""
    if isinstance(x, dict):
        if {"status", "measure", "margin"} <= set(x) and isinstance(x["margin"], str) and x["margin"]:
            yield path, x
        for k, v in x.items():
            yield from _rows_with_margins(v, f"{path}/{k}")
    elif isinstance(x, list):
        for n, v in enumerate(x):
            yield from _rows_with_margins(v, f"{path}[{n}]")


def _nested_rules() -> set:
    """Every rule, in every rulebook, whose check nests an and inside an or (or the reverse): the height bonus, the
    accessory buildings, the CBD eaves, R-2c's lot sizes, R-1's occupancy (the sweep of the CBD branch's review, P2)."""
    import ast
    import yaml
    from rule_format import formula
    out = set()
    for f in (REPO / "regulations/jurisdictions").rglob("5_*rules/*.yaml"):
        for rule in (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("rules") or []:
            body = formula.parse(rule["check"]).body if rule.get("check") else None
            if isinstance(body, ast.BoolOp) and any(isinstance(n, ast.BoolOp) for v in body.values for n in ast.walk(v)):
                out.add(rule["id"])
    return out


def test_every_golden_row_shows_a_limit_its_verdict_agrees_with():
    """In every stored answer (the scenarios, the sites, the 200 stress designs): a row of a rule whose check nests
    and/or never fails while showing a limit it meets, and any row whose verdict and shown limit disagree (a yard with
    room on a lot the building crosses) says why in its reason. Review of the CBD branch, P2: a failing CBD-60 eaves
    row showed its rear eave's +28'-0" with no reason, and an R-1b accessory building its front yard's room."""
    nested = _nested_rules()
    assert {"CBD-60.yard_projections", "R-1b.height", "R-1b.accessory_buildings"} <= nested
    _, answers = goldens.stored()
    wrong = []
    for case, answer in answers.items():
        for path, row in _rows_with_margins(answer):
            if row["status"] not in ("does_not_comply", "complies"):
                continue
            short = row["margin"].lstrip().startswith(("−", "-"))
            if (row["status"] == "does_not_comply") != short and (not row.get("reason") or row.get("rule") in nested):
                wrong.append((case + path, row.get("rule"), row["status"], row["margin"]))
    assert wrong == []
