"""The term index: every piece of the law that uses a defined term or one of its synonyms."""

from pathlib import Path

import pytest

from rule_format.labels import load_pieces
from rule_format.rulebook import load, read_jsonl
from section_labeling import coverage, term_index

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
LAW = "chapter_325_zoning_2026-10"
DEFINITIONS = load(ITHACA / "4_term_definitions/definitions.yaml")
SYNONYMS = load(term_index.SYNONYMS_FILE)


@pytest.fixture(scope="module")
def index():
    _, pieces = load_pieces(ITHACA / f"2_extracted_text/{LAW}.sections.jsonl")
    rows = read_jsonl(ITHACA / f"2_extracted_text/{LAW}.jsonl")
    return term_index.build(DEFINITIONS, SYNONYMS, [(f"{LAW}.pdf", pieces, rows)])


def ids(index, key):
    return [p["piece"] for p in index["terms"][key]["pieces"]]


def test_yard_lists_the_eaves_rule_that_was_missed(index):
    """§325-18B (eaves may project 2 ft into a yard) answers a question once sent to the architects."""
    assert "325-18B" in ids(index, "yard")


def test_height_lists_its_exceptions_and_the_bonus(index):
    assert {"325-16A", "325-16B", "325-16C"} <= set(ids(index, "height_of_building"))


def test_garages_and_sheds_find_the_accessory_structure_section(index):
    assert {"325-25A", "325-25B"} <= set(ids(index, "accessory_building"))


def test_a_synonym_alone_is_found():
    piece = {"id": "x", "title": "x", "lines": [[1, 1, 2]]}
    rows = [{}, {"page": 1, "line": 1, "text": "No building shall be within the front"},
            {"page": 1, "line": 2, "text": "setback."}]
    built = term_index.build({"yard": {"term": "YARD"}}, {"yard": {"forms": ["yard", "setback"]}},
                             [("law.pdf", {"x": piece}, rows)])
    assert built["terms"]["yard"]["pieces"] == [{"piece": "x", "title": "x", "at": [[1, 2]]}]


def test_a_phrase_split_across_a_line_break_is_found_at_its_first_line():
    piece = {"id": "x", "title": "x", "lines": [[3, 7, 8]]}
    rows = [{}, {"page": 3, "line": 7, "text": "the minimum side"}, {"page": 3, "line": 8, "text": "yards of the lot"}]
    rx = term_index.pattern(["side yard"])
    assert term_index.mentions([(3, 7, "the minimum side"), (3, 8, "yards of the lot")], rx) == [[3, 7]]
    assert not term_index.pattern(["yard"]).search("courtyard and backyards")      # whole words only


def test_every_definition_has_synonyms_and_every_concept_a_title():
    with pytest.raises(ValueError, match="no entry"):
        term_index.entries({"new_term": {"term": "NEW"}}, {})
    with pytest.raises(ValueError, match="needs a title"):
        term_index.entries({}, {"garage": {"forms": ["garage"]}})
    assert term_index.entries(DEFINITIONS, SYNONYMS).keys() >= DEFINITIONS.keys()


def test_related_sections_for_a_text(index):
    found = term_index.related(index, "Each required rear yard shall be at least 25% of the lot depth.")
    assert "325-18B" in found and len(found) == len(set(found))


def test_with_texts_the_densest_uses_come_first():
    """A short section about yards outranks a long one that mentions a yard once, so a size limit cuts the
    least relevant; sections without a text are left out."""
    index = {"terms": {"yard": {"forms": ["yard"], "pieces": [{"piece": "long"}, {"piece": "short"}, {"piece": "x"}]}}}
    texts = {"long": "yard " + "word " * 200, "short": "No projection into any required yard, front yard or side yard."}
    assert term_index.related(index, "the yard", texts) == ["short", "long"]


def test_the_committed_index_is_a_fresh_build_and_reads_back_as_built(index):
    saved = (ITHACA / "4_term_definitions" / term_index.INDEX_NAME).read_text(encoding="utf-8")
    assert saved == term_index.render(index)
    assert load(ITHACA / "4_term_definitions" / term_index.INDEX_NAME) == index      # the strict loader reads it whole


def test_the_review_list_reads_definitions_not_the_index(tmp_path):
    """cited_by reads definitions.yaml and uses.yaml only: the generated index is not a list of terms."""
    (tmp_path / "4_term_definitions").mkdir()
    (tmp_path / "5_zoning_rules").mkdir()
    (tmp_path / "4_term_definitions" / term_index.INDEX_NAME).write_text("documents: []\nterms: {}\n")
    assert coverage.cited_by(tmp_path, "law.pdf", {}) == {}
