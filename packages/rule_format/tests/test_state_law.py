"""A state's own law folder (regulations/jurisdictions/<state>/<name>/ with a state.yaml) and law kept outside the
repo (sources.yaml `kept_outside_repo: true`, its text in the code cache). Decided 2026-11-12:
docs/decisions/2026-11-12_building_code_text.md."""

import copy
import shutil
from pathlib import Path

import pytest
import yaml

from rule_format import place as registry
from rule_format.place import UnknownPlace, place, places, plugin_place
from document_extraction.book_text import file_name
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
             "kept_outside_repo": True, "layout": "icc", "brought_in": {"pages": "1", "sections": ["R318"]}}
    (j / "1_source_documents/sources.yaml").write_text(yaml.safe_dump({"documents": [entry]}), encoding="utf-8")
    cache = tmp_path / "cache" / sha
    cache.mkdir(parents=True)
    (cache / "code.pdf").write_bytes(pdf_bytes)
    _write_book(cache / file_name(entry), sha, {1: [quote_line], 2: ["R318.7.5.2 Elsewhere. Not more than 8 inches"]})
    return j, tmp_path / "cache"


def _write_book(path, sha, pages: dict[int, list[str]]):
    """A made-up whole book's cached text (document_extraction/book_text.py): every page, each page's counts."""
    import json
    from document_extraction.book_text import header
    counts = {p: (0, 0) for p in pages}
    rows = [header("code.pdf", sha, len(pages), "made up", counts, None) | {"page_counts": {str(p): [0, 0] for p in pages}},
            *({"page": p, "line": n, "text": t} for p, lines in pages.items() for n, t in enumerate(lines, 1))]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


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


def test_a_branch_reads_only_its_brought_in_pages_from_the_whole_cached_book(tmp_path, monkeypatch):
    # The cache keeps every page, the same for every branch (step 1c's page 898 came and went as branches were
    # extracted in turn); each branch reads its own brought-in pages, so a quote from a page it doesn't bring in is
    # still refused.
    j, cache = _state_folder(tmp_path)                       # brings in page 1 of a two-page book
    monkeypatch.setenv(CODE_CACHE_ENV, str(cache))
    ctx = Context.for_jurisdiction(j)
    assert ctx.problems == [] and set(ctx.pages["code.pdf"]) == {1}
    assert _source_problems([SOURCE], ctx) == []
    elsewhere = {"file": "code.pdf", "page": 2, "lines": [1, 1], "quote": "Not more than 8 inches"}
    assert _source_problems([elsewhere], ctx)
    from rule_format.rulebook import kept_text
    src = j / "1_source_documents/sources.yaml"
    listed = yaml.safe_load(src.read_text(encoding="utf-8"))
    assert [r.get("page") for r in kept_text(listed["documents"][0])] == [None, 1]
    # review round 1: a book kept outside the repo that names no pages it brings in was read whole (every page
    # quotable); now it is a problem, everywhere (CI too), and its text is never read in its stead
    for brought_in in (None, {"sections": ["R318"]}, {"pages": ""}, "34-56"):
        entry = listed["documents"][0] | {"brought_in": brought_in}
        if brought_in is None:
            del entry["brought_in"]
        src.write_text(yaml.safe_dump({"documents": [entry]}), encoding="utf-8")
        ctx = Context.for_jurisdiction(j)
        assert any("needs brought_in.pages" in p for p in ctx.problems) and "code.pdf" not in ctx.pages, brought_in
        assert _source_problems([elsewhere], ctx) and _source_problems([SOURCE], ctx)       # refused, never passed
        with pytest.raises(ValueError):
            kept_text(entry)


def test_every_test_reads_the_cache_code_cache_names():
    # Two tests removed $GORDIUM_CODE_CACHE and read the default cache whatever was set, so a branch run against
    # another cache (step 1c's private copy) failed them: every check reads the cache code_cache() names.
    removes, default = "delenv(" + "CODE_CACHE_ENV", "DEFAULT_" + "CODE_CACHE"
    found = [f.relative_to(REPO).as_posix() for f in sorted((REPO / "packages").glob("*/tests/*.py"))
             if removes in (t := f.read_text(encoding="utf-8")) or default in t or "gordium_" + "archive" in t]
    assert found == []


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
    # review round 8: a "not" dropped from both readings (both go through numbers.py) left them agreeing on the law
    # backwards; the comparison read from the printed sentence does not agree
    (lambda b: b["pieces"]["R318.7.3"].update(numbers=["greater than 12 foot", *b["pieces"]["R318.7.3"]["numbers"][1:]],
                                              second_reading_numbers=["greater than 12 foot",
                                                                      *b["pieces"]["R318.7.3"]["numbers"][1:]]),
     "R318.7.3: 'greater than 12 foot' is recorded as '>', but the printed sentence reads '<='"),
    (lambda b: b["pieces"]["R318.7.5.1"].pop("second_reading_comparisons"), "needs second_reading_comparisons"),
    (lambda b: b["pieces"]["R318.7.5.1"]["second_reading_comparisons"].pop(), "needs second_reading_comparisons"),
    (lambda b: b["pieces"]["R318.7.5.1"]["second_reading_comparisons"].__setitem__(0, "at most"),
     "needs second_reading_comparisons"),
    (lambda b: b["pieces"]["R319.2.2"].pop("flags"), "R319.2.2: '24 inch' is recorded as 'none', but the printed"),
    # review round 8 of step 1, on step 1b's pieces: R315.2's "more than one-half" is the law backwards ("shall not
    # exceed 7 feet for more than one-half of the floor"); only its flag says so
    (lambda b: b["pieces"]["R315.2"].pop("flags"),
     "R315.2: 'more than one-half' is recorded as '>', but the printed sentence reads '<='"),
])
def test_a_second_reading_that_doesnt_hold_is_refused(tmp_path, monkeypatch, change, problem):
    problems, _ = _copy_of_ny_state(tmp_path, monkeypatch, change)
    assert any(problem in p for p in problems), problems


def test_with_the_cache_a_recorded_number_must_be_the_texts(tmp_path, monkeypatch):
    from rule_format.rulebook import cached_text, load
    from rule_format.state_law import VERIFICATION, verification_problems
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    if not cached_text(entry).exists():         # the cache code_cache() names ($GORDIUM_CODE_CACHE), as every check
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
    from rule_format.rulebook import cached, cached_text, load
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    if not cached_text(entry).exists():         # the cache code_cache() names ($GORDIUM_CODE_CACHE), as every check
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    copy = tmp_path / "cache" / entry["sha256"]
    copy.mkdir(parents=True)
    (copy / entry["file"]).symlink_to(cached(entry))
    rows = [json.loads(x) for x in cached_text(entry).read_text(encoding="utf-8").splitlines()]
    assert Context.for_jurisdiction(NY_STATE).problems == []
    for r in rows[1:]:
        if (r.get("page"), r.get("line")) == (100, 43):
            r["text"] = r["text"].replace("shall not exceed", "may exceed")
    (copy / cached_text(entry).name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                encoding="utf-8")
    monkeypatch.setenv(CODE_CACHE_ENV, str(tmp_path / "cache"))
    assert any("words are not the ones its piece was cut from" in p for p in Context.for_jurisdiction(NY_STATE).problems)


# Every brought-in piece that points to law not brought in, as the pointer test finds it in the whole piece (where
# the code cache has the book). Kept here so CI, which has no cache and sees only the labels' quotes, still checks
# each one's label; with the cache, the test proves this list is exactly what the pieces say.
POINTING_OUT = {
    ("R102.6.1", "BO"), ("R102.6.2", "BO"), ("R314.3", "P2904"), ("R315.4", "P2904"), ("R316.2", "R312"),
    ("R316.3", "P2904"), ("R319.1", "P2904"), ("R319.7", "BO"), ("R320.7", "R507.2.2"), ("R321.1.4", "R507.2.2"),
    ("R325.6", "E3401.2.1"), ("R325.7", "E3401.2.1"), ("R507.10", "R301.5"), ("R507.10.3", "R507.2.2"),
    ("BO101.1", "R101.2"), ("BO102.6", "BO102.6.1"), ("BO105.1", "R301.1.3"), ("BO105.1.1", "BO105.2"),
    ("BO105.1.2", "BO105.2"), ("BO105.8", "702"), ("BO106.1", "R301.1.3"), ("BO106.1.2", "BO104"),
    ("BO106.1.2", "BO105"), ("BO107.1", "BO105"), ("BF103.1", "R324"),
}


def test_a_pointer_to_law_not_brought_in_is_flagged_never_a_silent_reference():
    # review round 5: R319.7 sends existing basements to Appendix BO, not brought in; as a reference nobody sees it.
    # Step 1b's review round 4: a pointer past the label's quote, or worded "the scoping requirements of", was missed.
    # Step 1b's review rounds 5 and 6: without the cache (CI) a pointer past the quote was never seen, so a rule
    # turned into a reference passed CI; POINTING_OUT checks those labels with or without the cache
    import re
    src = yaml.safe_load((NY_STATE / "1_source_documents/sources.yaml").read_text(encoding="utf-8"))["documents"][0]
    brought, alone = src["brought_in"]["sections"], src["brought_in"].get("alone") or []
    labels = yaml.safe_load((NY_STATE / "3_section_labels/gov.ny.residential.2025.yaml").read_text(encoding="utf-8"))["labels"]
    points = re.compile(r"(?:comply with|in accordance with|(?:scoping )?(?:requirements|provisions) of)"
                        r"(?: the (?:requirements|provisions) of)? "
                        r"(?:Sections?|Appendix|Chapter) ([A-Z]{0,2}\d[\w.]*\w|[A-Z]{1,2}\b)")
    from rule_format.rulebook import cached_text, kept_text, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    words = {pid: " ".join(s["quote"] for s in e["sources"]) for pid, e in labels.items()}
    whole = cached_text(entry).exists()
    if whole:                                   # the whole piece where the book is here, not only its quote
        text = {(r["page"], r["line"]): r["text"] for r in kept_text(entry)[1:]}
        for p in read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]:
            words[p["id"]] = " ".join(text[(pg, n)] for pg, a, b in p["lines"] for n in range(a, b + 1))
    found = {(pid, target) for pid in labels for target in (m[1] for m in points.finditer(" ".join(words[pid].split())))
             if not (target in alone or any(target == b or target.startswith(b + ".") for b in brought))}
    if whole:
        assert found == POINTING_OUT, (sorted(found - POINTING_OUT), sorted(POINTING_OUT - found))
    readme = (NY_STATE / "README.md").read_text(encoding="utf-8")
    wrong = []
    for pid, target in sorted(found | POINTING_OUT):
        label = labels[pid]["label"]
        # a definition sets no requirement, so it is no rule or flag; its pointer is named in the README instead,
        # since the pieces using the term never show it (review round 8: R202:sleeping_loft -> Section R315)
        if (label not in ("rule", "flag") if ":" not in pid else target not in readme):
            wrong.append((pid, target, label))
    assert wrong == []


def _readme_gaps(found: dict[str, list[str]], readme: str) -> tuple[list, list]:
    """(references the README's "not brought in" list never names, (reference, piece) pairs where the piece pointing
    to it is not named in the README's words about that reference)."""
    import re
    part = readme.split("## References in the brought-in sections that are not brought in")[1].split("\n## ")[0]
    bullets = [b for b in part.splitlines() if b.startswith("- ")]
    named = lambda code, text: re.search(rf"(?<![\w.]){re.escape(code)}(?!\w|\.\d)", text)
    misprinted = {"B0109": "BO109"}            # the book's zero for the letter O (README: the book's own misnumbering)
    spelled = lambda code: [code, misprinted.get(code)] + ([code.split()[1]] if code.startswith("Appendix ") else [])

    def said_for(code, bullet):
        """The bullet's words about this reference: from where it is named to the next reference, unless only words
        like "and" come between, so "R405.1 and Table R401.4.1(2) (...; from R319.4.3)" gives R319.4.3 to both, but
        "R301.5 (guard loads), R301.1.3 (...; from ...)" gives R301.5 nothing."""
        if code.startswith("Appendix ") and not bullet.startswith("- Appendices ") and not named(code, bullet):
            return []
        others = sorted(m.start() for c in found if c != code for s in spelled(c) if s
                        for m in re.finditer(rf"(?<![\w.]){re.escape(s)}(?!\w|\.\d)", bullet))
        said = []
        for s in filter(None, spelled(code)):
            for m in re.finditer(rf"(?<![\w.]){re.escape(s)}(?!\w|\.\d)", bullet):
                start = m.end()
                end = next((o for o in others if o > start and re.search(r"from |[;)]", bullet[start:o])), len(bullet))
                said.append(bullet[start:end])
        return said

    unlisted, missing = [], []
    for code, by in found.items():
        mine = [w for b in bullets for w in said_for(code, b)]
        if not mine:
            unlisted.append(code)
        missing += [(code, p) for p in by if mine and not any(named(p, w) for w in mine)]
    return unlisted, missing


def test_the_readmes_references_not_brought_in_name_every_piece_the_code_finds_pointing_to_them():
    # step 1b's review round 5: R507.10.3 also points to R507.2.2, but the README named only the step-1 pieces.
    # Round 6: the check read only references heading a bullet with "from", so 31 of 42 went unchecked.
    # Round 7: a piece named anywhere in a bullet passed for every reference in it; now only its own words count.
    # Round 8: a reference with no "from" of its own took the next one's, across a ";" or ")"
    from document_extraction.icc_references import ways_out
    from rule_format.rulebook import cached_text, kept_text, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    if not cached_text(entry).exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    lines = {(r["page"], r["line"]): r["text"] for r in kept_text(entry)[1:]}
    cut = read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]
    found = ways_out(cut, lines, entry["brought_in"]["sections"], entry["brought_in"].get("alone") or [])
    readme = (NY_STATE / "README.md").read_text(encoding="utf-8")
    assert len(found) >= 40 and _readme_gaps(found, readme) == ([], [])
    # a piece filed under the wrong reference is a gap: BO108.1 points to BO107, not BO109
    was = "BO107's other parts from BO108.1; BO109's other parts from BO107.1,"
    assert was in readme
    moved = readme.replace(was, "BO107's other parts; BO109's other parts from BO108.1, BO107.1,")
    assert ("BO107", "BO108.1") in _readme_gaps(found, moved)[1]


def test_the_readmes_chapter_2_count_is_the_r202_definitions_brought_in():
    # review round 7: Chapter 2 is not all brought in, only R201 and the R202 definitions the brought-in parts use.
    # Round 8: checked without the code cache (CI too), since it reads only files in the repo
    from rule_format.rulebook import read_jsonl
    cut = read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]
    used = sum(p["id"].startswith("R202:") for p in cut)
    readme = (NY_STATE / "README.md").read_text(encoding="utf-8")
    chapter_2 = next(b for b in readme.splitlines() if b.startswith("- Chapter 2 "))
    assert used > 0 and f"R201 and the {used} R202 definitions" in chapter_2, chapter_2


def test_a_range_of_sections_named_as_brought_in_has_every_section_in_it_brought_in():
    # step 1b's review round 5: "R314-R321" read as if R317 (garages and carports) were brought in; it is not
    import re
    src = yaml.safe_load((NY_STATE / "1_source_documents/sources.yaml").read_text(encoding="utf-8"))["documents"][0]
    brought = set(src["brought_in"]["sections"])
    files = [REPO / "docs/README.md", NY_STATE / "README.md", NY_STATE / "1_source_documents/sources.yaml",
             NY_STATE / "4_term_definitions/definitions.yaml"]
    ranges, wrong = 0, []
    for f in files:
        for a, b in re.findall(r"\bR(\d{3})[-\u2013]R(\d{3})\b", f.read_text(encoding="utf-8")):
            ranges += 1
            wrong += [(f.name, f"R{a}-R{b}", f"R{n}") for n in range(int(a), int(b) + 1) if f"R{n}" not in brought]
    assert ranges >= 3 and wrong == [], wrong


def test_every_term_definition_is_quoted_whole():
    # review round 1 of egress step 1b: CHANGE OF OCCUPANCY was quoted without its last words ("this code.")
    import json
    import re
    from rule_format.rulebook import cached, cached_text, kept_text, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    if not cached_text(entry).exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    text = {(r["page"], r["line"]): r["text"] for r in kept_text(entry)[1:]}
    pieces = {p["id"]: p for p in read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]}
    by_line = {(pg, a): p for p in pieces.values() if p["kind"] == "definition" for pg, a, _ in p["lines"][:1]}
    for key, d in load(NY_STATE / "4_term_definitions/definitions.yaml").items():
        first = d["sources"][0]
        piece = by_line[(first["page"], first["lines"][0])]
        whole = " ".join(text[(pg, n)] for pg, a, b in piece["lines"] for n in range(a, b + 1))
        quoted = " ".join(s["quote"] for s in d["sources"])
        assert re.sub(r"^\[[A-Z]{2}\] ", "", whole) == quoted, key


def test_an_allowance_for_an_existing_condition_is_a_flag_never_a_rule():
    # review round 1 of egress step 1b: BO107.2.2 (existing stairs may keep 9-inch risers) was a rule, so a rule drafted
    # from it could relax R318 for a new stair; whether a stair exists, and was lawful when built, isn't in the model
    import re
    from rule_format.rulebook import cached, cached_text, kept_text, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    if not cached_text(entry).exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    text = {(r["page"], r["line"]): r["text"] for r in kept_text(entry)[1:]}
    labels = load(NY_STATE / "3_section_labels/gov.ny.residential.2025.yaml")["labels"]
    allowance = re.compile(r"\bexisting\b.*\b(?:permitted to (?:remain|maintain|continue)|need not|not (?:be )?required|shall be "
                           r"accepted|shall be allowed|be allowed|may remain|are not required)", re.I | re.S)
    found = []
    for p in read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]:
        words = " ".join(text[(pg, n)] for pg, a, b in p["lines"] for n in range(a, b + 1))
        if p["kind"] != "definition" and allowance.search(words):
            found.append((p["id"], labels[p["id"]]["label"]))
    assert len(found) >= 6 and all(label == "flag" for _, label in found), found
    assert "R102.6" in dict(found)      # review round 2: "shall be permitted to continue" was missed


def _wrong_conversions(words: str) -> list[tuple[str, str]]:
    """Each "N inches (X mm)", "N-foot (X mm)" or "N feet M inches (X mm)" whose millimetres are not its length."""
    import re
    num = r"(\d+ \d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
    pair = re.compile(r"(?<![\d/.])" + num + r"[ -](feet|foot|inch|inches)(?: " + num + r" inch(?:es)?)? "
                      r"\((\d[\d,]*(?:\.\d+)?) mm\)")

    def inches(x):                                              # "31 1/2" -> 31.5
        return sum(int(a) / int(b) if b else float(a) for a, _, b in (q.partition("/") for q in x.split()))
    out = []
    for m in pair.finditer(words):
        value = inches(m[1]) * (12 if m[2] in ("feet", "foot") else 1) + (inches(m[3]) if m[3] else 0)
        mm = float(m[4].replace(",", ""))
        if abs(mm - value * 25.4) > max(2.0, 0.01 * mm):        # the book rounds; 1931 for 1930.4 is no error
            out.append((m[0], m[4]))
    return out


def _wrong_other_conversions(words: str) -> list[tuple[str, str]]:
    """Each "N degrees (X rad)", "N square feet (X m²)" or "N inches (X cm)" whose metric value, at the precision
    printed, is not its value: "30 degrees (0.51 rad)" (0.52), "9 square feet (0.9 m²)" (0.8)."""
    import math
    import re
    factor = {"degrees": math.pi / 180, "square feet": 0.09290304, "inches": 2.54}
    pair = re.compile(r"(?<![\d/.])(\d+(?:\.\d+)?) (degrees|square feet|inches) \((\d+(?:\.\d+)?) (rad|m\[fn2\]|m²|cm)\)")
    out = []
    for m in pair.finditer(words):
        if (m[2], m[4]) not in (("degrees", "rad"), ("square feet", "m[fn2]"), ("square feet", "m²"), ("inches", "cm")):
            continue
        places = len(m[3].partition(".")[2])
        if abs(float(m[3]) - float(m[1]) * factor[m[2]]) > 0.5 * 10 ** -places * 1.05:   # it rounds to its last digit
            out.append((m[0], f"{m[3]} {m[4].replace('m[fn2]', 'm²')}"))
    return out


def test_a_wrong_metric_value_is_found_in_degrees_areas_and_centimetres():
    # review round 7: R318.7.5.1 "30 degrees (0.51 rad)" and R319.4.1 "9 square feet (0.9 m²)" were not looked for
    assert _wrong_other_conversions("not more than 30 degrees (0.51 rad) and 90 degrees (1.57 rad)") == [
        ("30 degrees (0.51 rad)", "0.51 rad")]
    assert _wrong_other_conversions("9 square feet (0.9 m[fn2]), 5.7 square feet (0.530 m[fn2]), 35 square feet "
                                    "(3.3 m[fn2])") == [("9 square feet (0.9 m[fn2])", "0.9 m²")]
    assert _wrong_other_conversions("70 inches (178 cm) and 70 inches (168 cm)") == [("70 inches (168 cm)", "168 cm")]


def test_a_wrong_conversion_is_found_in_each_way_the_book_prints_one():
    assert _wrong_conversions("not less than 20 inches (610 mm) and 20 inches (508 mm)") == [("20 inches (610 mm)", "610")]
    assert _wrong_conversions("a 10-inch (300 mm) sill") == [("10-inch (300 mm)", "300")]
    assert _wrong_conversions("6 feet 8 inches (2134 mm), 6 feet 8 inches (2032 mm)") == [("6 feet 8 inches (2134 mm)", "2134")]
    assert _wrong_conversions("3/8 inch (9.5 mm), 1 1/2 inches (38 mm), 31 1/2 inches (787 mm)") == [
        ("31 1/2 inches (787 mm)", "787")]


def test_a_metric_conversion_that_is_not_its_inches_is_named_in_the_labels_notes():
    # review round 2 of egress step 1b: R318.7.1 prints "27 inches (698 mm)" (27 inches is 686 mm) and R315.5.2.1
    # "20 inches (610 mm)" (24 inches); a rule drafted from the millimetres would set another limit, unnoticed
    from rule_format.rulebook import cached_text, kept_text, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    if not cached_text(entry).exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    text = {(r["page"], r["line"]): r["text"] for r in kept_text(entry)[1:]}
    labels = load(NY_STATE / "3_section_labels/gov.ny.residential.2025.yaml")["labels"]
    wrong, unnamed = [], []
    for p in read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]:
        words = " ".join(text[(pg, n)] for pg, a, b in p["lines"] for n in range(a, b + 1))
        for printed, metric in [(a, f"{b} mm") for a, b in _wrong_conversions(words)] + _wrong_other_conversions(words):
            wrong.append((p["id"], printed))
            if f"({metric})" not in (labels[p["id"]].get("notes") or ""):
                unnamed.append((p["id"], printed))
    assert wrong and unnamed == [], unnamed


def test_no_label_reason_calls_a_brought_in_section_not_brought_in():
    # review round 2 of egress step 1b: BO106.1.2's reason said "BO104 (not brought in)" after BO104.1 came in
    import re
    src = yaml.safe_load((NY_STATE / "1_source_documents/sources.yaml").read_text(encoding="utf-8"))["documents"][0]
    brought = src["brought_in"]["sections"] + (src["brought_in"].get("alone") or [])
    labels = yaml.safe_load((NY_STATE / "3_section_labels/gov.ny.residential.2025.yaml").read_text(encoding="utf-8"))["labels"]
    said = [(pid, m[1]) for pid, e in labels.items()
            for m in re.finditer(r"\b([A-Z]{1,2}\d{3}(?:\.\d+)*) \(not brought in\b", " ".join(e["reason"].split()))]
    wrong = [(pid, t) for pid, t in said if any(b == t or b.startswith(t + ".") or t.startswith(b + ".") for b in brought)]
    assert wrong == [], wrong


def _transcript_numbers(folder: Path, name: str, pieces: dict) -> dict[str, list[str]]:
    """Each piece's numbers as a kept second-reading transcript has them: the transcript cut at each piece's heading
    within its crop, put through numbers.py (the same cutting as the tools beside it, `tools/compare.py`)."""
    import json
    import re
    from document_extraction.numbers import shown, statements_of_lines
    crops, cur = {}, None
    for line in (folder / f"{name}_transcript.txt").read_text(encoding="utf-8").splitlines():
        if m := re.match(r"=== (crop_\d+\.png)", line):
            cur = m[1]
            crops[cur] = []
        elif cur and line.strip():
            crops[cur].append(line.replace("m²", "m[fn2]").replace("ft²", "ft[fn2]").strip())

    def starts(pid, ln):
        p = pieces[pid]
        if p["kind"] == "section_heading":
            return ln.startswith(f"SECTION {pid}") or ln.startswith(f"[NY] SECTION {pid}")
        if p["kind"] == "definition":
            return bool(re.match(r"(\[[A-Z]{2}\] )?" + re.escape(p["title"].split(" ")[0]), ln))
        return bool(re.match(r"(\[[A-Z]{2}\] )?" + re.escape(pid) + r" ", ln))
    lines_of = {}
    for c in json.loads((folder / f"{name}_crops.json").read_text(encoding="utf-8")):
        lines, ids, at = crops[c["image"]], c["pieces"], []
        for pid in ids:
            if pieces[pid]["kind"] == "definition" and len(ids) == 1:
                at.append(0)
                continue
            k = next((i for i, ln in enumerate(lines) if starts(pid, ln) and (not at or i > at[-1])), None)
            at.append(0 if k is None and not at else k)
            assert at[-1] is not None, (name, c["image"], pid)
        for j, pid in enumerate(ids):
            lines_of.setdefault(pid, []).extend(lines[at[j]: at[j + 1] if j + 1 < len(ids) else len(lines)])
    return {pid: [shown(s) for s in statements_of_lines(ls)] for pid, ls in lines_of.items()}


def test_the_recorded_second_reading_is_the_kept_transcripts():
    # review round 3 of egress step 1b: second_reading_numbers could be edited by hand to agree; where a transcript is
    # kept (in the code cache, beside the book, since it holds the book's words), the list must be rebuilt from it
    import hashlib
    from rule_format.rulebook import cached, cached_text, kept_text, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    folder = cached(entry).parent / "second_reading"
    if not folder.exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    for line in (folder / "README.md").read_text(encoding="utf-8").splitlines():   # "    <sha256>  <file>"
        if len(parts := line.split()) == 2 and len(parts[0]) == 64:
            assert hashlib.sha256((folder / parts[1]).read_bytes()).hexdigest() == parts[0], parts[1]
    pieces = {p["id"]: p for p in read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]}
    recorded = load(NY_STATE / "text_verification.yaml")["pieces"]
    rebuilt = {}
    for name in ("step_1_round_3", "step_1b", "step_1b_round_1", "step_1c"):
        rebuilt.update(_transcript_numbers(folder, name, pieces))
    assert len(rebuilt) >= 110
    assert {pid: recorded[pid]["second_reading_numbers"] for pid in rebuilt} == rebuilt


def test_every_part_of_appendix_bo_is_brought_in_or_named_in_the_readme():
    # review round 3 of egress step 1b: the README's list of what is not brought in left out BO102.1.1, BO106.5 and others
    import re
    from rule_format.rulebook import cached, cached_text, kept_text, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    if not cached_text(entry).exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    readme = " ".join((NY_STATE / "README.md").read_text(encoding="utf-8").split())
    named = set(re.findall(r"\bBO\d{3}(?:\.\d+)*", readme))
    for a, b in re.findall(r"\b(BO\d{3}(?:\.\d+)*) (?:to|through) (BO\d{3}(?:\.\d+)*)", readme):
        *stem, first = a.split(".")
        if b.rsplit(".", 1)[0] == ".".join(stem):
            named |= {".".join(stem + [str(k)]) for k in range(int(first), int(b.rsplit(".", 1)[1]) + 1)}
    brought = {p["id"] for p in read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]}
    heads = {m[1] for r in kept_text(entry)[1:]
             if r.get("bold") and (m := re.match(r"(?:\[NY\] )?(BO1(?:0\d|1[0-3])(?:\.\d+)+) ", r["text"]))}

    def wholly_out(part):                  # a part named, none of it brought in: its own parts are named with it
        return part in named and not any(b == part or b.startswith(part + ".") for b in brought)

    def covered(pid):
        parts = pid.split(".")
        return pid in brought or pid in named or any(wholly_out(".".join(parts[:k])) for k in range(1, len(parts)))
    missing = sorted(h for h in heads if not covered(h) and not h.startswith("BO103."))
    assert len(heads) > 100 and missing == [], " ".join(missing)


def test_a_permission_to_exceed_is_flagged_as_no_minimum():
    # Review round 9 of step 1: "shall be permitted to exceed 38 inches" (R320.2, R318.7.5.3) lifts a maximum; the
    # recorded words read it as more than (>), a minimum the law does not set. Its flag must say the recorded
    # reading is wrong, never "either way", so no rule is drafted from the '>'
    from document_extraction.numbers import comparisons
    pieces = yaml.safe_load((NY_STATE / "text_verification.yaml").read_text(encoding="utf-8"))["pieces"]
    seen, unclear = 0, []
    for pid, e in pieces.items():
        nums = e.get("numbers") or []
        for n, c, r in zip(nums, comparisons(nums), e.get("second_reading_comparisons") or []):
            if n.startswith("exceed ") and c == ">" and r == "none":
                seen += 1
                said = [f for f in e.get("flags") or [] if f"'{n}'" in f]
                if not any("second reading (none) is right" in f and "wrong" in f for f in said):
                    unclear.append((pid, n))
    assert seen >= 2 and unclear == [], unclear


def test_every_part_of_appendix_bf_is_brought_in_or_named_in_the_readme():
    # egress step 1c: Appendix BF comes in only for egress (BF101 to BF103); its other parts must each be named as not
    # brought in, so a reader never takes the patio-cover height or structure limits as checked
    import re
    from rule_format.rulebook import cached, cached_text, kept_text, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    if not cached_text(entry).exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    readme = " ".join((NY_STATE / "README.md").read_text(encoding="utf-8").split())
    # only the README's own list of what is not brought in counts (BF101.1's "BF101 to BF106" names no part as out)
    named = set(re.findall(r"\bBF\d{3}(?:\.\d+)*", readme.split("Not brought in, being no egress:")[1].split(" BF101.1 ")[0]))
    brought = {p["id"] for p in read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]}
    heads = {m[1] for r in kept_text(entry)[1:]
             if r.get("bold") and (m := re.match(r"(?:\[NY\] )?(?:SECTION )?(BF1\d\d(?:\.\d+)*)\W", r["text"]))}

    def covered(pid):
        parts = pid.split(".")
        return pid in brought or any(".".join(parts[:k]) in named and not any(
            b.startswith(".".join(parts[:k])) for b in brought) for k in range(1, len(parts) + 1))
    missing = sorted(h for h in heads if not covered(h))
    assert {"BF101", "BF103.2", "BF106.4"} <= heads and missing == [], " ".join(missing)
    assert {"BF101", "BF101.1", "BF101.2", "BF102", "BF102.1", "BF102:patio_cover", "BF103", "BF103.1", "BF103.2"} <= brought


def test_a_label_that_calls_its_reading_an_open_question_records_it_as_one():
    # review round 1 of egress step 1c: BF103.2's "unenclosed" was called an open question in its notes only, so the
    # review list showed no open questions and nothing would block approving it
    import re
    labels = yaml.safe_load((NY_STATE / "3_section_labels/gov.ny.residential.2025.yaml").read_text(encoding="utf-8"))["labels"]
    said = [pid for pid, e in labels.items() if re.search(r"open question", " ".join(str(e.get(k, "")) for k in
                                                                                     ("reason", "notes")), re.I)]
    assert "BF103.2" in said and all(labels[pid].get("open_questions") for pid in said), said
    review = (NY_STATE / "3_section_labels/gov.ny.residential.2025.review.md").read_text(encoding="utf-8")
    listed = review.split("## Open questions for the architects")[1].split("\n## ")[0]
    assert all(f"| {pid} |" in listed for pid in said)


def test_a_label_with_readings_still_in_play_never_says_one_reading_decides():
    # review round 2 of egress step 1c: BF103.2 listed three readings of "unenclosed" but its notes (and the README)
    # said a screened porch "fails, never passes" under the stricter one; with readings in play a design fails only if
    # it fails under all of them, else needs review (docs/methods.md)
    import re
    labels = yaml.safe_load((NY_STATE / "3_section_labels/gov.ny.residential.2025.yaml").read_text(encoding="utf-8"))["labels"]
    open_ = [pid for pid, e in labels.items() if any(len(r.get("readings") or []) >= 2 for r in e.get("research") or [])]
    assert "BF103.2" in open_
    decides = re.compile(r"fails, never passes|until (?:it is )?answered,? Gordium takes|Gordium's reading until answered", re.I)
    readme = " ".join((NY_STATE / "README.md").read_text(encoding="utf-8").split())
    for pid in open_:
        e = labels[pid]
        assert not decides.search(yaml.safe_dump(e)) and "needs review" in e.get("notes", ""), pid
    # review round 4: BF103.1's reason (a piece the open question turns on) said it "says what makes a patio cover
    # enclosed", the stricter reading as settled
    assert "what makes a patio cover enclosed" not in labels["BF103.1"]["reason"]
    assert not decides.search(readme)
    # review round 3: the README's lead-in still said the notes give Gordium's reading of both undefined words
    assert "Two words are not defined, and the label's notes give Gordium's reading" not in readme


# ---- a book whose numbers could not be read a second time (Maine's 2009 IBC: not_verified) --------------------------
# Its page images are made from its own OCR, so no independent reading exists (docs/decisions/
# 2026-11-20_commercial_egress_maine.md). Its file records each piece's numbers only, says why in `not_verified`, and
# no rule may stand on its numbers: every IBC requirement is a flag, its check kept as the drafted test.

MAINE = REPO / "regulations/jurisdictions/maine/maine_state"
IBC = "icc.ibc.2009.pdf"
IBC_RECORD = "text_verification.icc.ibc.2009.yaml"
COMMON_PATH = {"file": IBC, "page": 265, "lines": [76, 78],
               "quote": "In occupancies other than Groups H-l, H-2 and H-3, the common path of egress travelshall not "
                        "exceed 75 feet (22 860 mm)."}


def _copy_of_maine(tmp_path, monkeypatch, change=None):
    """Maine's state folder, copied, with its IBC record changed by `change`; checked without the cache."""
    from rule_format.state_law import verification_problems
    from rule_format.rulebook import load
    j = tmp_path / "regulations/jurisdictions/maine/maine_state"
    shutil.copytree(MAINE, j)
    monkeypatch.setenv(CODE_CACHE_ENV, str(tmp_path / "no_cache"))
    if change:
        book = load(j / IBC_RECORD)
        change(book)
        (j / IBC_RECORD).write_text(yaml.safe_dump(book, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return verification_problems(j, Context.for_jurisdiction(j))


def test_a_book_not_verified_is_accepted_explicitly(tmp_path, monkeypatch):
    from rule_format.rulebook import load
    book = load(MAINE / IBC_RECORD)
    assert "OCR" in book["not_verified"] and "purchased ICC copy" in book["not_verified"]
    assert all(set(e) == {"piece_sha256", "numbers"} for e in book["pieces"].values())
    assert "not exceed 75 foot" in book["pieces"]["1014.3"]["numbers"]
    problems, _ = _copy_of_maine(tmp_path, monkeypatch)
    assert problems == [], problems


@pytest.mark.parametrize("change,problem", [
    (lambda b: b["pieces"]["1014.3"].update(second_reading="agrees"), "claim a second reading that was never made"),
    (lambda b: b["pieces"]["1014.3"].update(second_reading_numbers=["not exceed 75 foot"]),
     "claim a second reading that was never made"),
    (lambda b: b["pieces"]["1014.3"].update(second_reading_comparisons=["<="]), "claim a second reading"),
    (lambda b: b["pieces"]["1014.3"].pop("numbers"), "1014.3: a book not verified (not_verified) records only"),
    (lambda b: b["pieces"]["1014.3"].update(piece_sha256="0" * 64), "the piece changed since its numbers were recorded"),
    (lambda b: b["pieces"].pop("1014.3"), "1014.3: brought in but not in"),
    (lambda b: b.update(not_verified=" "), "not_verified must say, in words, why"),
    # without not_verified the file is held to the second reading, exactly as before
    (lambda b: b.pop("not_verified"), "1014.3: needs second_reading_numbers"),
])
def test_a_not_verified_record_that_claims_more_or_less_is_refused(tmp_path, monkeypatch, change, problem):
    problems, _ = _copy_of_maine(tmp_path, monkeypatch, change)
    assert any(problem in p for p in problems), problems


def test_with_the_cache_a_not_verified_number_must_still_be_the_texts(tmp_path, monkeypatch):
    from rule_format.rulebook import cached_text, load
    from rule_format.state_law import verification_problems
    entry = next(d for d in load(MAINE / "1_source_documents/sources.yaml")["documents"] if d["file"] == IBC)
    if not cached_text(entry).exists():
        pytest.skip("the code cache with the 2009 IBC is not on this machine (CI)")
    j = tmp_path / "regulations/jurisdictions/maine/maine_state"
    shutil.copytree(MAINE, j)
    book = load(j / IBC_RECORD)
    book["pieces"]["1014.3"]["numbers"][1] = "not exceed 57 foot"
    (j / IBC_RECORD).write_text(yaml.safe_dump(book, sort_keys=False, allow_unicode=True), encoding="utf-8")
    assert any("1014.3: the recorded numbers are not the extracted text's" in p
               for p in verification_problems(j, Context.for_jurisdiction(j))[0])


@pytest.fixture(scope="module")
def maine():
    return Context.for_jurisdiction(MAINE)


def test_a_rule_may_not_stand_on_a_number_of_a_book_not_verified(maine):
    from rule_format import code_numbers
    rule = {"kind": "rule", "check": "common_path_of_travel <= 75", "for_each": "story"}
    got = code_numbers.problems(rule, [COMMON_PATH], maine)
    assert any("never read a second time" in p and "make it a flag" in p for p in got), got
    assert any("number 75 in 'check' isn't one of the second-reading numbers" in p for p in got), got
    # a rule with no number still stands on the book's OCR words: refused too
    assert any("never read a second time" in p for p in
               code_numbers.problems({"kind": "rule", "check": "corridor_walls_smoke_partitions", "for_each": "corridor"},
                                     [COMMON_PATH], maine))


@pytest.mark.parametrize("check, words", [
    ("common_path_of_travel <= 75", None),                         # the extracted text's number, the law's way
    ("common_path_of_travel < 75", "needs < 75 to hold"),           # the edge moved
    ("common_path_of_travel <= 70", "isn't one of"),                # a number the text doesn't print
    ("common_path_of_travel <= 22860", "isn't one of"),             # the millimetres
])
def test_a_flags_drafted_check_uses_the_extracted_texts_numbers_the_laws_way(maine, check, words):
    from rule_format import code_numbers
    got = code_numbers.problems({"kind": "flag", "check": check, "for_each": "story"}, [COMMON_PATH], maine)
    assert (got == []) if words is None else any(words in p for p in got), got


TRAVEL_ROW = {"file": IBC, "page": 267, "lines": [81, 81], "quote": "1-2,1-3,1-4 Not Permitted 200"}


def test_a_table_cell_of_a_book_not_verified_backs_a_flags_drafted_length_only(maine):
    """Table 1016.1 prints its unit in the column head ("(feet)"), never by the cell, and its cells carry no
    comparison words: a flag's drafted check may compare the cell's 200 with a length (its direction proved by the
    examples' drafted_check); a rule never may, and a number the row doesn't print never backs anything."""
    from rule_format import code_numbers
    flag = {"kind": "flag", "check": "egress_travel_distance <= 200", "for_each": "story"}
    assert code_numbers.problems(flag, [TRAVEL_ROW], maine) == []
    assert any("isn't one of" in p for p in code_numbers.problems(dict(flag, check="egress_travel_distance <= 250"),
                                                                  [TRAVEL_ROW], maine))
    assert any("never read a second time" in p for p in code_numbers.problems(dict(flag, kind="rule"), [TRAVEL_ROW],
                                                                               maine))


def test_a_label_quote_repeated_on_its_page_counts_when_its_piece_pins_it_once(maine):
    """The IBC's "LOADS. See Section 1602.1." (p.43 line 100) is also the end of "LIVE LOADS. See Section 1602.1."
    (line 94), and a label's quote can't reach outside its piece; the piece pins it, so it counts. A quote at lines
    outside the piece, or the repeat at the other lines, still does not."""
    from rule_format.labels import load_pieces, piece_fingerprint, validate_labels
    header, pieces = load_pieces(MAINE / "2_extracted_text/icc.ibc.2009.sections.jsonl")
    if IBC not in maine.pages:
        pytest.skip("the code cache with the 2009 IBC is not on this machine (CI)")
    entry = {"label": "reference", "topic": "definitions", "reason": "A pointer.",
             "piece_sha256": piece_fingerprint(pieces["202:loads"], header["sha256"]), "drafted_by": "t",
             "status": "draft",
             "sources": [{"file": IBC, "page": 43, "lines": [100, 100], "quote": "LOADS. See Section 1602.1."}]}
    book = lambda e: {"document": IBC, "labels": {"202:loads": e}}
    assert validate_labels(book(entry), maine, header, pieces) == []
    other = copy.deepcopy(entry)
    other["sources"][0]["lines"] = [94, 94]
    assert validate_labels(book(other), maine, header, pieces)


def _flag(source, check="common_path_of_travel <= 75", drafted=("pass", "fail")):
    story = lambda length: {"story": [{"id": "s1", "measures": {"common_path_of_travel": length}}]}
    return {"id": "general.ibc_1014_3_common_path", "kind": "flag", "topic": "means_of_egress",
            "title": "Common path of egress travel (1014.3)", "check": check, "for_each": "story",
            "when_none": "needs_review", "sources": [source],
            "examples": [{"given": {}, "parts": story(48.5), "rows": [{"part": "s1", "outcome": "needs_review"}],
                          "expect": "needs_review", "drafted_check": drafted[0]},
                         {"given": {}, "parts": story(80), "rows": [{"part": "s1", "outcome": "needs_review"}],
                          "expect": "needs_review", "drafted_check": drafted[1]},
                         {"given": {}, "parts": {"story": []}, "rows": [{"outcome": "needs_review"}],
                          "expect": "needs_review"}],
            "drafted_by": "test", "status": "draft"}


def test_a_flag_keeps_its_drafted_check_only_where_its_book_is_not_verified(maine):
    from rule_format.rulebook import validate
    assert validate({"district": "general", "rules": [_flag(COMMON_PATH)]}, maine) == []
    wrong = validate({"district": "general", "rules": [_flag(COMMON_PATH, drafted=("pass", "pass"))]}, maine)
    assert any("the drafted check gives fail, not pass" in p for p in wrong), wrong
    assert any("drafted_check passes and fails" in p for p in wrong), wrong
    # a flag citing a verified book (New York's) has no check, as before
    ny = Context.for_jurisdiction(NY_STATE)
    risers = {"file": "gov.ny.residential.2025.pdf", "page": 100, "lines": [42, 42],
              "quote": "[NY] R318.7.5.1 Risers. The riser height shall be not more than 8 1/4 inches (209 mm)."}
    flag = _flag(risers, check="stair_riser_height <= 8.25") | {"for_each": "stair", "examples": [
        {"given": {}, "parts": {"stair": []}, "rows": [{"outcome": "needs_review"}], "expect": "needs_review"}]}
    assert any("a 'flag' must not have one" in p for p in validate({"district": "general", "rules": [flag]}, ny))
    # and drafted_check goes only with such a flag
    flag = dict(flag, examples=[dict(flag["examples"][0], drafted_check="pass")])
    flag.pop("check")
    assert any("drafted_check goes only with a flag" in p for p in validate({"district": "general", "rules": [flag]}, ny))
