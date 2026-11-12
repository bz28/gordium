"""A state's own law folder (regulations/jurisdictions/<state>/<name>/ with a state.yaml) and law kept outside the
repo (sources.yaml `kept_outside_repo: true`, its text in the code cache). Decided 2026-11-12:
docs/decisions/2026-11-12_building_code_text.md."""

import shutil
from pathlib import Path

import pytest
import yaml

from rule_format import place as registry
from rule_format.place import UnknownPlace, place, places, plugin_place
from rule_format.rulebook import (CODE_CACHE_ENV, REPO, STATE_SETTINGS, Context, _source_problems, jurisdictions,
                                  law_folders, state_folders)

NY_STATE = REPO / "regulations/jurisdictions/new_york/new_york_state"
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"


@pytest.fixture(autouse=True)
def fresh():
    registry.clear_cache()
    yield
    registry.clear_cache()


def test_a_state_law_folder_is_law_but_no_place():
    assert NY_STATE in state_folders() and NY_STATE in law_folders()
    assert NY_STATE not in jurisdictions()                     # the place loops never see it
    assert ITHACA in jurisdictions() and ITHACA not in state_folders()
    assert [p.folder for p in places()] == [ITHACA.resolve()]  # the plugin's "one place" is still Ithaca
    assert plugin_place().folder == ITHACA.resolve()


def test_ithaca_inherits_new_york_states_law():
    assert place("new_york/ithaca_city").inherits == (NY_STATE,)
    assert (NY_STATE / STATE_SETTINGS).is_file()


def _place_with(tmp_path, inherits, state_folder="new_york/new_york_state"):
    root = tmp_path / "repo/regulations/jurisdictions"
    town = root / "new_york/town"
    town.mkdir(parents=True)
    settings = yaml.safe_load((ITHACA / "jurisdiction.yaml").read_text(encoding="utf-8"))
    settings["inherits"] = inherits
    (town / "jurisdiction.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    if state_folder:
        (root / state_folder).mkdir(parents=True)
        (root / state_folder / STATE_SETTINGS).write_text("name: Somewhere\n", encoding="utf-8")
    return town


@pytest.mark.parametrize("inherits,problem", [
    (["new_york/nowhere"], "no state law folder there"),
    (["new_york/new_york_state", "new_york/new_york_state"], "names a folder twice"),
    (["new_york_state"], "name it as <state>/<name>"),
    ("new_york/new_york_state", "must be a list"),
    ([""], "must be a list"),
])
def test_an_inheritance_that_cant_be_followed_is_refused(tmp_path, inherits, problem):
    with pytest.raises(UnknownPlace, match=problem):
        place(_place_with(tmp_path, inherits))


@pytest.mark.parametrize("drop", [True, False])
def test_a_place_whose_state_has_law_must_inherit_it(tmp_path, drop):
    town = _place_with(tmp_path, [])
    if drop:                                   # no `inherits` at all
        settings = yaml.safe_load((town / "jurisdiction.yaml").read_text(encoding="utf-8"))
        settings.pop("inherits")
        (town / "jurisdiction.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    with pytest.raises(UnknownPlace, match="new_york/new_york_state is this state's: list it under inherits"):
        place(town)


def test_a_place_whose_state_has_no_law_folder_needs_no_inherits(tmp_path):
    town = _place_with(tmp_path, [], state_folder=None)
    assert place(town).inherits == ()


def test_a_place_inherits_only_its_own_states_law(tmp_path):
    town = _place_with(tmp_path, ["texas/texas_state"], state_folder="texas/texas_state")
    with pytest.raises(UnknownPlace, match="only its own state's law"):
        place(town)


def test_a_place_folder_wrongly_holding_a_state_yaml_is_no_longer_a_place(tmp_path):
    root = tmp_path / "regulations/jurisdictions/ny"
    (root / "a").mkdir(parents=True)
    (root / "law").mkdir()
    (root / "law" / STATE_SETTINGS).write_text("name: NY\n", encoding="utf-8")
    assert jurisdictions(tmp_path) == [root / "a"] and state_folders(tmp_path) == [root / "law"]


# ---- law kept outside the repo ------------------------------------------------------------------------------------

def _state_folder(tmp_path, quote_line="R318.7.5.1 Riser height. The riser height shall be not more than 8 1/4 inches"):
    """A made-up state folder whose one document is kept outside the repo, and a cache holding it."""
    pdf_bytes = b"%PDF-1.4 a made-up code book\n"
    import hashlib
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    j = tmp_path / "regulations/jurisdictions/test_state/test_state_law"
    (j / "1_source_documents").mkdir(parents=True)
    (j / STATE_SETTINGS).write_text("name: Test State\n", encoding="utf-8")
    entry = {"file": "code.pdf", "title": "A code", "publisher": "x", "url": "https://example.org", "sha256": sha,
             "kept_outside_repo": True, "layout": "icc"}
    (j / "1_source_documents/sources.yaml").write_text(yaml.safe_dump({"documents": [entry]}), encoding="utf-8")
    cache = tmp_path / "cache" / sha
    cache.mkdir(parents=True)
    (cache / "code.pdf").write_bytes(pdf_bytes)
    import json
    rows = [{"file": "code.pdf", "sha256": sha, "pages": 1}, {"page": 1, "line": 1, "text": quote_line}]
    (cache / "code.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return j, tmp_path / "cache"


SOURCE = {"file": "code.pdf", "page": 1, "lines": [1, 1], "quote": "not more than 8 1/4 inches"}


def test_with_the_cache_a_kept_outside_quote_is_checked_word_for_word(tmp_path, monkeypatch):
    j, cache = _state_folder(tmp_path)
    monkeypatch.setenv(CODE_CACHE_ENV, str(cache))
    ctx = Context.for_jurisdiction(j)
    assert ctx.problems == [] and not ctx.uncached
    assert _source_problems([SOURCE], ctx) == []
    wrong = SOURCE | {"quote": "not more than 8 inches"}         # 8 1/4 misread as 8: refused
    assert "quote isn't at lines 1-1" in _source_problems([wrong], ctx)[0]
    eleven = SOURCE | {"quote": "not more than 81/4 inches"}     # a fraction joined to its whole number: refused
    assert _source_problems([eleven], ctx)


def test_without_the_cache_a_quote_is_skipped_and_listed_never_passed_silently(tmp_path, monkeypatch):
    j, cache = _state_folder(tmp_path)
    monkeypatch.setenv(CODE_CACHE_ENV, str(tmp_path / "no_cache_here"))
    ctx = Context.for_jurisdiction(j)
    assert ctx.problems == [] and "code.pdf" in ctx.uncached
    assert _source_problems([SOURCE], ctx) == []
    assert len(ctx.skipped) == 1 and "quote not checked here" in ctx.skipped[0]


def test_a_changed_cached_book_or_a_copy_in_the_repo_is_a_problem(tmp_path, monkeypatch):
    j, cache = _state_folder(tmp_path)
    monkeypatch.setenv(CODE_CACHE_ENV, str(cache))
    sha = next(cache.iterdir()).name
    (cache / sha / "code.pdf").write_bytes(b"%PDF-1.4 another printing\n")
    assert "fingerprint does not match" in " ".join(Context.for_jurisdiction(j).problems)
    (cache / sha / "code.pdf").unlink()
    shutil.copy(__file__, j / "1_source_documents/code.pdf")
    assert "but a copy is in 1_source_documents" in " ".join(Context.for_jurisdiction(j).problems)


# ---- the second reading of the numbers (text_verification.yaml) ----------------------------------------------------

def _copy_of_ny_state(tmp_path, monkeypatch, change=None):
    """New York's state folder, copied, with its text_verification.yaml changed by `change`; checked without the cache."""
    from rule_format.state_law import VERIFICATION, verification_problems
    from rule_format.rulebook import load
    j = tmp_path / "regulations/jurisdictions/new_york/new_york_state"
    shutil.copytree(NY_STATE, j)
    monkeypatch.setenv(CODE_CACHE_ENV, str(tmp_path / "no_cache"))
    if change:
        book = load(j / VERIFICATION)
        change(book)
        (j / VERIFICATION).write_text(yaml.safe_dump(book, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return verification_problems(j, Context.for_jurisdiction(j))


def test_the_recorded_second_reading_covers_every_piece_and_needs_no_cache_to_be_checked(tmp_path, monkeypatch):
    problems, notes = _copy_of_ny_state(tmp_path, monkeypatch)
    assert problems == [] and "weren't compared with the book's text here" in notes[0]


@pytest.mark.parametrize("change,problem", [
    (lambda b: b["pieces"].pop("R318.7.5.1"), "R318.7.5.1: brought in but not in text_verification.yaml"),
    (lambda b: b["pieces"]["R318.7.5.1"].update(second_reading="differs"), "says the readings differ, but"),
    (lambda b: b["pieces"]["R318.7.5.1"].pop("second_reading_numbers"), "needs second_reading_numbers"),
    (lambda b: b["pieces"]["R318.7.5.1"].update(second_reading="differs", second_reading_numbers=["8 inch"]),
     "needs a flag saying which is right"),
    (lambda b: b["pieces"]["R318.7.5.1"].update(second_reading="looks fine"), "second_reading must be one of"),
    (lambda b: b["pieces"]["R318.7.5.1"].update(piece_sha256="0" * 64), "the piece changed since its numbers were read"),
    (lambda b: b["pieces"]["R318.7.5.1"].update(second_reading_numbers=["not more than 8 inch"]),
     "says the readings agree, but its two lists of numbers differ"),
    (lambda b: b.pop("copy_checked"), "must have"),
])
def test_a_second_reading_that_doesnt_hold_is_refused(tmp_path, monkeypatch, change, problem):
    problems, _ = _copy_of_ny_state(tmp_path, monkeypatch, change)
    assert any(problem in p for p in problems), problems


def test_with_the_cache_a_recorded_number_must_be_the_texts(tmp_path, monkeypatch):
    from rule_format.rulebook import cached, load
    from rule_format.state_law import VERIFICATION, verification_problems
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    monkeypatch.delenv(CODE_CACHE_ENV, raising=False)
    if not cached(entry, ".jsonl").exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    j = tmp_path / "regulations/jurisdictions/new_york/new_york_state"
    shutil.copytree(NY_STATE, j)
    book = load(j / VERIFICATION)
    assert "not more than 8 1/4 inch" in book["pieces"]["R318.7.5.1"]["numbers"]
    assert verification_problems(j, Context.for_jurisdiction(j))[0] == []
    book["pieces"]["R318.7.5.1"]["numbers"][0] = "not more than 8 inch"        # a misread riser limit
    (j / VERIFICATION).write_text(yaml.safe_dump(book, sort_keys=False, allow_unicode=True), encoding="utf-8")
    assert any("R318.7.5.1: the recorded numbers are not the extracted text's" in p
               for p in verification_problems(j, Context.for_jurisdiction(j))[0])


def test_an_edited_cache_is_a_problem_even_where_no_quote_covers_the_edit(tmp_path, monkeypatch):
    """Only document_extraction --check re-extracts; every other check reads the cache, so the cache must still be
    the text the pieces were cut from."""
    import json
    from rule_format.rulebook import cached, load
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    monkeypatch.delenv(CODE_CACHE_ENV, raising=False)
    if not cached(entry, ".jsonl").exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    copy = tmp_path / "cache" / entry["sha256"]
    copy.mkdir(parents=True)
    (copy / entry["file"]).symlink_to(cached(entry))
    rows = [json.loads(x) for x in cached(entry, ".jsonl").read_text(encoding="utf-8").splitlines()]
    assert Context.for_jurisdiction(NY_STATE).problems == []
    for r in rows[1:]:
        if (r.get("page"), r.get("line")) == (100, 43):
            r["text"] = r["text"].replace("shall not exceed", "may exceed")
    (copy / cached(entry, ".jsonl").name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                     encoding="utf-8")
    monkeypatch.setenv(CODE_CACHE_ENV, str(tmp_path / "cache"))
    assert any("words are not the ones its piece was cut from" in p for p in Context.for_jurisdiction(NY_STATE).problems)
