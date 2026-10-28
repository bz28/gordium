"""Files are worked out once per exact content (rulebook._kept): load() and the extracted text Context reads.
The cache must never change an answer: never stale (a changed file is read again), never shared (a caller that
edits what it got can't change what the next caller gets), errors never kept, and it must be what makes the
second read fast."""
import os
import time

import pytest
import yaml

from rule_format import rulebook
from rule_format.rulebook import REPO, Context, _StrictLoader, jurisdictions, load, rulebook_paths


def fresh(path):
    """The reading before the cache: the strict loader on the file's text, nothing kept."""
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)


def every_yaml():
    """Every rulebook and term file of every jurisdiction, and every answer key: all the YAML a check reads."""
    out = []
    for j in jurisdictions():
        out += rulebook_paths(j / "5_zoning_rules")
        out += sorted((j / "4_term_definitions").glob("*.yaml"))
        out += [j / "1_source_documents/sources.yaml"]
    out += rulebook_paths(REPO / "test_data/answer_keys")
    return [p for p in out if p.is_file()]


@pytest.fixture(autouse=True)
def empty_cache():
    rulebook._KEPT.clear()
    yield
    rulebook._KEPT.clear()


@pytest.mark.parametrize("path", every_yaml(), ids=lambda p: p.relative_to(REPO).as_posix())
def test_every_rulebook_and_term_file_reads_the_same_cold_warm_and_fresh(path):
    want = fresh(path)
    cold = load(path)                       # parsed and kept
    warm = load(path)                       # from the cache
    assert cold == want and warm == want
    assert type(warm) is type(want)


def test_there_are_rulebooks_to_compare():
    assert any(p.parent.name == "5_zoning_rules" for p in every_yaml())


def test_a_changed_file_is_read_again_even_with_the_same_size_and_date(tmp_path):
    f = tmp_path / "R-1b.yaml"
    f.write_text("district: R-1b\nlimit: 10\n", encoding="utf-8")
    stat = f.stat()
    assert load(f)["limit"] == 10
    f.write_text("district: R-1b\nlimit: 20\n", encoding="utf-8")       # same length
    os.utime(f, ns=(stat.st_atime_ns, stat.st_mtime_ns))                # and the same date
    assert f.stat().st_size == stat.st_size
    assert load(f)["limit"] == 20


def test_what_a_caller_gets_is_its_own_copy_at_every_level(tmp_path):
    f = tmp_path / "R-1b.yaml"
    f.write_text("district: R-1b\nrules:\n  - id: R-1b.a\n    check: height <= 35\n    sources: [{page: 3}]\n",
                 encoding="utf-8")
    first = load(f)
    first["rules"][0]["check"] = "True"            # a caller edits what it got, deep down
    first["rules"][0]["sources"][0]["page"] = 99
    first["rules"].append({"id": "R-1b.extra"})
    first["district"] = "R-9"
    again = load(f)
    assert again == fresh(f)
    assert again["rules"][0]["check"] == "height <= 35" and len(again["rules"]) == 1
    third = load(f)
    assert third is not again and third["rules"] is not again["rules"]
    assert third["rules"][0]["sources"][0] is not again["rules"][0]["sources"][0]


def test_a_real_rulebook_edited_by_a_caller_never_reaches_the_next(tmp_path):
    path = next(p for p in every_yaml() if p.parent.name == "5_zoning_rules")
    got = load(path)
    for rule in got["rules"]:
        rule["check"] = "True"                  # would turn every rule into a pass if it leaked
        rule.pop("review_when", None)
    assert load(path) == fresh(path)


def test_a_file_that_fails_to_parse_is_never_kept(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("a: 1\na: 2\n", encoding="utf-8")          # a duplicate key: the strict loader refuses it
    for _ in range(2):
        with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key"):
            load(f)
    assert not rulebook._KEPT
    f.write_text("a: 1\nb: 2\n", encoding="utf-8")
    assert load(f) == {"a": 1, "b": 2}
    f.write_bytes(b"a: \xff\n")                             # not UTF-8: the same error as read_text gives
    with pytest.raises(UnicodeDecodeError):
        load(f)


def test_windows_line_endings_read_exactly_as_before(tmp_path):
    f = tmp_path / "crlf.yaml"
    f.write_bytes(b'quote: "Rear yard\r\n  25 ft"\r\nblock: |\r\n  one\r\n  two\r\nold_mac: "a\rb"\r\n')
    assert load(f) == fresh(f)


def test_the_cache_stays_bounded(tmp_path):
    for i in range(rulebook._KEPT_MAX + 20):
        f = tmp_path / f"f{i}.yaml"
        f.write_text(f"n: {i}\n", encoding="utf-8")
        assert load(f) == {"n": i}
    assert len(rulebook._KEPT) == rulebook._KEPT_MAX
    assert load(tmp_path / "f0.yaml") == {"n": 0}          # dropped, then read again


def test_a_jurisdictions_context_is_the_same_cold_and_warm_and_its_own_copy():
    for j in jurisdictions():
        cold = Context.for_jurisdiction(j)
        warm = Context.for_jurisdiction(j)
        assert cold == warm
        name = next(iter(warm.pages), None)
        if name is None:
            continue
        page = next(iter(warm.pages[name]))
        warm.pages[name][page].clear()                      # a caller wipes a page: quotes would stop matching
        warm.uses.clear()
        third = Context.for_jurisdiction(j)
        assert third == cold and third.pages[name][page]


def test_extracted_text_from_another_pdf_version_is_still_refused(tmp_path):
    j = next(iter(jurisdictions()))
    name, entry = next((n, e) for n, e in Context.for_jurisdiction(j).sources.items()
                       if (j / "2_extracted_text" / f"{os.path.splitext(n)[0]}.jsonl").exists())
    real = j / "2_extracted_text" / f"{os.path.splitext(name)[0]}.jsonl"
    ctx = Context(measures=set(), uses=set(), topics=set(), sources={})
    ctx._load_extracted(name, entry["sha256"], real)        # right version: read, and kept
    assert ctx.pages[name] and not ctx.problems
    other = Context(measures=set(), uses=set(), topics=set(), sources={})
    other._load_extracted(name, "0" * 64, real)             # same bytes, a different PDF expected: refused
    assert name not in other.pages and "different version" in other.problems[0]
    copy = tmp_path / real.name
    data = real.read_bytes()
    copy.write_bytes(data.replace(entry["sha256"].encode(), b"f" * 64, 1))   # the header changed: read again
    third = Context(measures=set(), uses=set(), topics=set(), sources={})
    third._load_extracted(name, entry["sha256"], copy)
    assert name not in third.pages and "different version" in third.problems[0]


def test_reading_a_rulebook_again_is_much_faster_than_parsing_it():
    path = max((p for p in every_yaml() if p.parent.name == "5_zoning_rules"), key=lambda p: p.stat().st_size)
    t = time.perf_counter()
    for _ in range(5):
        fresh(path)
    parse = (time.perf_counter() - t) / 5
    load(path)
    t = time.perf_counter()
    for _ in range(5):
        load(path)
    again = (time.perf_counter() - t) / 5
    assert again < parse / 3, (again, parse)                # ~50x in practice; 3x leaves room for a busy machine
