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
    assert len(scenarios) == 12 and len(sites) == 3 and len(thens) == 3
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
                         capture_output=True, text=True, check=True).stdout
    assert out.strip().endswith("binary: set")


def test_two_keys_that_would_be_written_the_same_are_refused_never_merged():
    import pytest
    with pytest.raises(ValueError, match="two keys written the same"):
        goldens.canonical({1: "a", "1": "b"})
