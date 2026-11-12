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


def test_a_pointer_to_law_not_brought_in_is_flagged_never_a_silent_reference():
    # review round 5: R319.7 sends existing basements to Appendix BO, not brought in; as a reference nobody sees it.
    # Step 1b's review round 4: a pointer past the label's quote, or worded "the scoping requirements of", was missed
    import re
    src = yaml.safe_load((NY_STATE / "1_source_documents/sources.yaml").read_text(encoding="utf-8"))["documents"][0]
    brought = src["brought_in"]["sections"]
    labels = yaml.safe_load((NY_STATE / "3_section_labels/gov.ny.residential.2025.yaml").read_text(encoding="utf-8"))["labels"]
    points = re.compile(r"(?:comply with|in accordance with|(?:scoping )?(?:requirements|provisions) of)"
                        r"(?: the (?:requirements|provisions) of)? "
                        r"(?:Sections?|Appendix|Chapter) ([A-Z]{0,2}\d[\w.]*\w|[A-Z]{1,2}\b)")
    from rule_format.rulebook import cached, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    words = {pid: " ".join(s["quote"] for s in e["sources"]) for pid, e in labels.items()}
    if cached(entry, ".jsonl").exists():        # the whole piece where the book is here, not only its quote
        text = {(r["page"], r["line"]): r["text"] for r in read_jsonl(cached(entry, ".jsonl"))[1:]}
        for p in read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]:
            words[p["id"]] = " ".join(text[(pg, n)] for pg, a, b in p["lines"] for n in range(a, b + 1))
    readme = (NY_STATE / "README.md").read_text(encoding="utf-8")
    seen, wrong = 0, []
    for pid, e in labels.items():
        for target in (m[1] for m in points.finditer(" ".join(words[pid].split()))):
            inside = any(target == b or target.startswith(b + ".") for b in brought)
            seen += not inside
            # a definition sets no requirement, so it is no rule or flag; its pointer is named in the README instead,
            # since the pieces using the term never show it (review round 8: R202:sleeping_loft -> Section R315)
            if not inside and (e["label"] not in ("rule", "flag") if ":" not in pid else target not in readme):
                wrong.append((pid, target, e["label"]))
    assert seen >= 3 and wrong == []          # R319.7 (Appendix BO), R320.7 and R321.1.4 (R507.2.2)


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
    from rule_format.rulebook import cached, load, read_jsonl
    entry = load(NY_STATE / "1_source_documents/sources.yaml")["documents"][0]
    if not cached(entry, ".jsonl").exists():
        pytest.skip("the code cache with New York's Residential Code is not on this machine (CI)")
    text = {(r["page"], r["line"]): r["text"] for r in read_jsonl(cached(entry, ".jsonl"))[1:]}
    labels = load(NY_STATE / "3_section_labels/gov.ny.residential.2025.yaml")["labels"]
    wrong, unnamed = [], []
    for p in read_jsonl(NY_STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl")[1:]:
        words = " ".join(text[(pg, n)] for pg, a, b in p["lines"] for n in range(a, b + 1))
        for printed, metric in [(a, f"{b} mm") for a, b in _wrong_conversions(words)] + _wrong_other_conversions(words):
            wrong.append((p["id"], printed))
            if f"({metric})" not in (labels[p["id"]].get("notes") or ""):
                unnamed.append((p["id"], printed))
    assert wrong and unnamed == [], unnamed
