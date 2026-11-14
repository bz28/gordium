"""The start box's options (check.options: the districts, the uses and the questions per district and use) are worked
out once per exact input and kept (check._OPTIONS). These pin that what is kept is never stale and never shared:
the same answer as working it out afresh, for every district and every use; a changed, added or removed file, or a
changed code list, is worked out again; a caller can't change what the next one gets; an error is never kept; the
kept answers are bounded; and every file the answer reads is in the key."""
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
import yaml

from design_checker import check
from design_checker import rhino_logic as logic
from rule_format import formula, rulebook
from rule_format.rulebook import REPO, rulebook_for

CITY = "regulations/jurisdictions/new_york/ithaca_city"


def _clear():
    """Every cache options goes through: its own answers, the decoded rule files, the parsed formulas."""
    check._OPTIONS.clear()
    rulebook._KEPT.clear()
    formula.parse.cache_clear()
    formula._names.cache_clear()


def _fresh(j: Path) -> dict:
    """The options answer worked out the way it was before any cache (no snapshot, each helper on its own, _read_for
    worked out by follow_up_facts and implied_for themselves), by reading each file with yaml's own C reader
    directly (not rulebook.load): what the kept answer must equal."""
    folders = (j / "5_zoning_rules", j / "5_zoning_rules/drafted")
    zones = sorted({p.stem for f in folders if f.is_dir() for p in f.glob("*.yaml") if rulebook_for(j, p.stem)})
    uses_file = j / "4_term_definitions/uses.yaml"
    uses = (_yaml(uses_file) or {}) if uses_file.exists() else {}
    names = {k: v.get("name", k) for k, v in uses.items() if isinstance(v, dict)}
    out = {"zones": zones, "uses": names, "district_uses": {}, "follow_ups": {}, "implied": {}}
    for zone in zones:
        rules = _yaml(rulebook_for(j, zone))["rules"]
        out["district_uses"][zone] = check.use_choices(rules, names, zone)
        every = list(dict.fromkeys([u["id"] for u in out["district_uses"][zone]] + list(names)))
        out["follow_ups"][zone] = {u: check.follow_up_facts(rules, u, names) for u in every}
        out["implied"][zone] = {u: check.implied_for(rules, u, names) for u in every}
    return out


def _yaml(path: Path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))


def _city(tmp_path) -> Path:
    """A copy of the city's options inputs (its rulebooks and uses.yaml) to change."""
    src, j = REPO / CITY, tmp_path / "city"
    shutil.copytree(src / "5_zoning_rules", j / "5_zoning_rules")
    (j / "4_term_definitions").mkdir(parents=True)
    shutil.copy(src / "4_term_definitions/uses.yaml", j / "4_term_definitions/uses.yaml")
    return j


def test_every_district_and_use_is_the_same_kept_as_worked_out_afresh():
    """Every district x every use, on a first call (nothing kept), a second (the kept answer) and against the answer
    worked out as before the cache: the same, to the byte."""
    _clear()
    first = check.options(CITY)
    second = check.options(CITY)
    fresh = _fresh(REPO / CITY)
    assert len(fresh["zones"]) == 9 and len(fresh["uses"]) >= 20        # every district, every city use
    assert json.dumps(first, sort_keys=False) == json.dumps(second) == json.dumps(fresh)
    for zone in fresh["zones"]:                                          # said district by district, use by use
        for use in fresh["follow_ups"][zone]:
            assert second["follow_ups"][zone][use] == fresh["follow_ups"][zone][use], (zone, use)
            assert second["implied"][zone][use] == fresh["implied"][zone][use], (zone, use)
        assert second["district_uses"][zone] == fresh["district_uses"][zone], zone
    assert any(second["follow_ups"][z][u] for z in fresh["zones"] for u in fresh["uses"])   # not vacuously empty


def test_a_changed_added_or_removed_file_is_worked_out_again(tmp_path):
    j = _city(tmp_path)
    before = check.options(str(j))
    assert before == _fresh(j)
    # a rulebook changed: R-1a's rules dropped, so it asks nothing and lists every use unmarked
    r1a = j / "5_zoning_rules/R-1a.yaml"
    original = r1a.read_bytes()
    r1a.write_text(yaml.safe_dump({"rules": []}), encoding="utf-8")
    changed = check.options(str(j))
    assert changed == _fresh(j) and changed != before
    assert not any(changed["follow_ups"]["R-1a"].values())
    # the city's uses changed: a use renamed
    uses = j / "4_term_definitions/uses.yaml"
    data = yaml.safe_load(uses.read_text(encoding="utf-8"))
    first = next(k for k, v in data.items() if isinstance(v, dict))
    data[first]["name"] = "Renamed use"
    uses.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    renamed = check.options(str(j))
    assert renamed["uses"][first] == "Renamed use" and renamed == _fresh(j)
    # a rulebook added (an AI-drafted one in drafted/) and one removed
    (j / "5_zoning_rules/drafted").mkdir()
    shutil.copy(j / "5_zoning_rules/R-2a.yaml", j / "5_zoning_rules/drafted/Z-9.yaml")
    (j / "5_zoning_rules/RU.yaml").unlink()
    moved = check.options(str(j))
    assert "Z-9" in moved["zones"] and "RU" not in moved["zones"] and moved == _fresh(j)
    # a hand rulebook beside a drafted one of the same district: the hand one is read, and its change is seen
    shutil.copy(j / "5_zoning_rules/R-1b.yaml", j / "5_zoning_rules/drafted/R-1b.yaml")
    (j / "5_zoning_rules/R-1b.yaml").write_text(yaml.safe_dump({"rules": []}), encoding="utf-8")
    assert check.options(str(j)) == _fresh(j)
    assert not any(check.options(str(j))["follow_ups"]["R-1b"].values())
    # back to the first bytes: the first answer again
    r1a.write_bytes(original)
    assert check.options(str(j))["follow_ups"]["R-1a"] == before["follow_ups"]["R-1a"]


def test_a_changed_code_list_is_worked_out_again(monkeypatch):
    """The answer reads the code's own lists too (which facts are stated, which a use implies): a swapped one is
    never answered from what was kept under the old one."""
    before = check.options(CITY)
    zone, use, fact = next((z, u, f[0]) for z in before["zones"] for u, f in before["follow_ups"][z].items() if f)
    monkeypatch.setattr(logic, "STATED_FACTS", {k: v for k, v in logic.STATED_FACTS.items() if k != fact})
    after = check.options(CITY)
    assert fact not in after["follow_ups"][zone][use] and after == _fresh(REPO / CITY)
    monkeypatch.undo()
    monkeypatch.setattr(logic, "IMPLIED_BY_USE", {**logic.IMPLIED_BY_USE, use: {fact: 1}})
    implied = check.options(CITY)
    assert implied["implied"][zone][use] == {fact: 1} and fact not in implied["follow_ups"][zone][use]
    assert implied == _fresh(REPO / CITY)


@pytest.mark.parametrize("module,name,swap", [
    (check, "INTERIOR", lambda v: set(v) - {"parking_spaces"}),                     # an interior fact asked after all
    (logic, "DRAWN_FACTS", lambda v: tuple(x for x in v if x != "primary_buildings")),   # a drawn fact asked
    (check, "MEASURE_KINDS", lambda v: {**v, "conversion": "text"}),               # a measure typed otherwise
])
def test_every_other_code_list_is_in_the_key(monkeypatch, module, name, swap):
    """Review round 1: only two of the five lists were pinned. Each swap changes the answer (checked), and the
    answer after it is the one worked out afresh, never the one kept under the old list."""
    before = check.options(CITY)
    monkeypatch.setattr(module, name, swap(getattr(module, name)))
    after = check.options(CITY)
    assert after != before and after == _fresh(REPO / CITY)


def test_a_caller_cannot_change_what_the_next_caller_gets():
    pristine = json.dumps(check.options(CITY))
    got = check.options(CITY)
    got["zones"].append("X-1")
    got["uses"]["made_up"] = "Made up"
    zone = got["zones"][0]
    for facts in got["follow_ups"][zone].values():
        facts.append("made_up_fact")
    got["district_uses"][zone][0]["name"] = "changed"
    got["implied"][zone].clear()
    assert json.dumps(check.options(CITY)) == pristine


@pytest.mark.parametrize("gone", ["5_zoning_rules/R-1b.yaml", "5_zoning_rules/RU.yaml"])
def test_a_file_that_goes_while_the_options_are_worked_out_is_never_kept_under_its_old_bytes(tmp_path, monkeypatch,
                                                                                             gone):
    """Review round 1: which rulebook is a district's was looked up on the disk after the files were read, so a hand
    rulebook deleted in between gave the drafted one's questions (or a lone one's district went missing), kept under
    the key of the files with it there. Now the choice is made from what was read: deleted and put back in that
    moment, the answer is the one the files give."""
    j = _city(tmp_path)
    (j / "5_zoning_rules/drafted").mkdir()
    (j / "5_zoning_rules/drafted/R-1b.yaml").write_text(yaml.safe_dump({"rules": []}), encoding="utf-8")
    path = j / gone
    data = path.read_bytes()
    read_files = check._options_files

    def read_then_delete(where):
        files = read_files(where)
        path.unlink()                         # gone between the reading and the working out
        return files
    monkeypatch.setattr(check, "_options_files", read_then_delete)
    during = check.options(str(j))
    path.write_bytes(data)                    # back, the same bytes
    monkeypatch.undo()
    assert during == check.options(str(j)) == _fresh(j)
    assert any(during["follow_ups"]["R-1b"].values()) and "RU" in during["zones"]


def test_a_second_call_is_never_worked_out_again():
    """The kept answer is used: the same files, worked out once (counted, not timed)."""
    calls = []
    real = check._options

    def counted(*a):
        calls.append(1)
        return real(*a)
    check._OPTIONS.clear()
    try:
        check._options = counted
        check.options(CITY)
        check.options(CITY)
    finally:
        check._options = real
    assert len(calls) == 1


def test_an_error_is_never_kept(tmp_path):
    j = _city(tmp_path)
    broken = j / "5_zoning_rules/R-2b.yaml"
    good = broken.read_bytes()
    broken.write_text("rules:\n  - id: a\n    id: b\n", encoding="utf-8")          # a duplicate key: refused
    kept = len(check._OPTIONS)
    for _ in range(2):                                                               # the same error every time
        with pytest.raises(yaml.YAMLError):
            check.options(str(j))
    assert len(check._OPTIONS) == kept
    broken.write_bytes(good)
    assert check.options(str(j)) == _fresh(j)


def test_the_kept_answers_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "_OPTIONS_MAX", 3)
    j = _city(tmp_path)
    uses = j / "4_term_definitions/uses.yaml"
    text = uses.read_text(encoding="utf-8")
    for i in range(6):
        uses.write_text(text + f"\n# variant {i}\n", encoding="utf-8")
        check.options(str(j))
        assert len(check._OPTIONS) <= 3


def test_the_least_recently_used_answer_goes_first(tmp_path, monkeypatch):
    """Review round 2: the bound alone passed with everything dropped at once, or with an answer asked again still
    dropped first. Kept A, B, C; A asked again; D added: B goes, A and C stay (counted: kept ones aren't worked
    out again)."""
    monkeypatch.setattr(check, "_OPTIONS_MAX", 3)
    check._OPTIONS.clear()
    cities = {}
    for name in "ABCD":
        j = tmp_path / name
        (j / "4_term_definitions").mkdir(parents=True)
        (j / "4_term_definitions/uses.yaml").write_text(f"{name.lower()}_use: {{name: Use {name}}}\n",
                                                        encoding="utf-8")
        cities[name] = str(j)
    calls = []
    real = check._options
    monkeypatch.setattr(check, "_options", lambda *a: calls.append(Path(a[0]).name) or real(*a))
    for name in "ABCAD":
        check.options(cities[name])
    assert calls == ["A", "B", "C", "D"]                   # A's second ask was kept
    calls.clear()
    for name in "ACD":
        check.options(cities[name])
    assert calls == []                                    # A, C and D still kept
    check.options(cities["B"])
    assert calls == ["B"]                                 # B was the one dropped


_OPENED: list | None = None


def _audit(event, args):
    if _OPENED is not None and event == "open" and isinstance(args[0], (str, bytes, Path)):
        _OPENED.append(Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve())


sys.addaudithook(_audit)         # once per process (a hook can't be removed): records only inside _opened()


def _opened(call):
    global _OPENED
    _OPENED = []
    try:
        result = call()
    finally:
        got, _OPENED = _OPENED, None
    return result, got


@pytest.mark.parametrize("where", ["city", "copy"])
def test_every_file_the_answer_reads_is_in_its_key(tmp_path, where):
    """Nothing kept anywhere (so every file is really opened): options opens only the files of its key
    (_options_files), and the answer worked out from their bytes opens no file at all and is the answer worked out
    from disk. A new file read anywhere in the answer without being added to _options_files fails here (its change
    would never be seen), as does one dropped from it."""
    j = REPO / CITY if where == "city" else _city(tmp_path)
    if where == "copy":                       # a drafted rulebook too, so both folders are listed and read
        (j / "5_zoning_rules/drafted").mkdir()
        shutil.copy(j / "5_zoning_rules/R-2a.yaml", j / "5_zoning_rules/drafted/Z-9.yaml")
    _clear()
    answer, opened = _opened(lambda: check.options(str(j)))
    files = check._options_files(j)
    keyed = {(j / name).resolve() for name in files}
    assert opened and set(opened) <= keyed, sorted(set(opened) - keyed)
    assert {(j / n).resolve() for n, data in files.items() if data is not None} <= set(opened)
    def no_disk(*a, **k):
        raise AssertionError("the options looked at the disk after reading their files")
    with pytest.MonkeyPatch.context() as m:   # nor looks: no stat (is_file, exists), no listing (review round 1)
        m.setattr(Path, "stat", no_disk)
        m.setattr(os, "scandir", no_disk)
        m.setattr(os, "listdir", no_disk)
        from_bytes, inside = _opened(lambda: check._options(j, files))
    assert inside == []
    assert answer == from_bytes == _fresh(j)       # and those bytes are all it needs: the answer read from disk


def test_options_is_quick():
    """Loose bounds (the Mac measured ~3 ms kept and ~0.1 s worked out again with the rule files decoded; it was
    ~2 s before _read_for was worked out once per district and use): kept, well under 50 ms; worked out again,
    under 1 s. Warmed here first, whatever ran before (review round 2: a kept answer with the rule files no longer
    decoded made the "again" call a cold one)."""
    _clear()
    check.options(CITY)
    t = time.perf_counter()
    check.options(CITY)
    kept = time.perf_counter() - t
    check._OPTIONS.clear()
    t = time.perf_counter()
    check.options(CITY)
    again = time.perf_counter() - t
    assert kept < 0.05, kept
    assert again < 1.0, again


def test_a_uses_file_that_cannot_be_read_is_an_error_as_before(tmp_path):
    """Review round 1: a uses.yaml that is there but is no file (a folder) is an error, as it always was, never a
    city with no uses. Windows refuses to open a folder with PermissionError, macOS and Linux with IsADirectoryError."""
    j = _city(tmp_path)
    (j / "4_term_definitions/uses.yaml").unlink()
    (j / "4_term_definitions/uses.yaml").mkdir()
    with pytest.raises((IsADirectoryError, PermissionError)):
        check.options(str(j))
