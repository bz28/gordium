"""The Revit marks for building facts the Building Code's rules read (docs/decisions/2026-11-28_revit_marks_building_facts.md):
each mark's tooltip quotes the law in its exact words (every quoted passage is found in the BCNYS labels' own quotes,
read from the page), each feeds a fact Gordium reads, and blank sends nothing (code_scope reads a fact not sent as not
stated, never as No)."""

import re
from pathlib import Path

import pytest
import yaml

from design_checker import code_scope

REPO = Path(__file__).resolve().parents[3]
MARKS = REPO / "apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs"
LABELS = REPO / "regulations/jurisdictions/new_york/new_york_state_building/3_section_labels/gov.ny.building.2025.yaml"

# PR A's four: the facts the rules already read, each with its mark
PR_A = {"stages_or_platforms": "Gordium: Stages or platforms",
        "aircraft_related_occupancy": "Gordium: Aircraft-related occupancy",
        "service_corridors": "Gordium: Service corridors", "assembly_spaces": "Gordium: Assembly spaces"}


def _description(name: str) -> str:
    """A mark's tooltip, its C# string literals joined (escaped quotes read as quotes)."""
    text = MARKS.read_text(encoding="utf-8")
    at = text.index(f'"{name}", new(')
    block = text[at:text.index(");", at)]
    literals = re.findall(r'"((?:[^"\\]|\\.)*)"', block)
    # the name, then the feeds field, then the description's parts (after the categories)
    feeds_at = next(i for i, s in enumerate(literals) if s.startswith(("building.", "facts.")))
    return "".join(s.replace('\\"', '"') for s in literals[feeds_at + 1:])


def _law_words() -> str:
    """Every label quote, its whitespace made single and its line-break hyphens joined ("communi- cations")."""
    labels = yaml.safe_load(LABELS.read_text(encoding="utf-8"))
    quotes = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "quote" and isinstance(v, str):
                    quotes.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(labels)
    return " ".join(_plain(q) for q in quotes)


def _plain(s: str) -> str:
    return re.sub(r"(\w)- (\w)", r"\1\2", re.sub(r"\s+", " ", s)).strip()


@pytest.mark.parametrize("key", sorted(PR_A))
def test_each_mark_feeds_its_fact_and_is_the_one_the_asks_name(key):
    assert code_scope.FACTS[key] == "yes_no"
    assert code_scope.MARK[key] == PR_A[key]
    assert code_scope.field_of(key) == f"building.{key}"
    assert f'"building.{key}"' in MARKS.read_text(encoding="utf-8")


@pytest.mark.parametrize("key", sorted(PR_A))
def test_every_passage_a_mark_quotes_is_the_laws_own_words(key):
    words = _description(PR_A[key])
    quoted = re.findall(r'"([^"]+)"', words)
    assert quoted, f"{PR_A[key]} quotes no law"
    law = _law_words()
    for q in quoted:
        assert _plain(q) in law, (PR_A[key], q)


@pytest.mark.parametrize("key", sorted(PR_A))
def test_blank_is_not_stated_and_no_is_read_only_as_stated(key):
    # a fact not sent is left out of the measures (its rules need review); false only where the block states it
    assert key not in code_scope.building_measures({"occupancy_groups": ["B"]})
    assert code_scope.building_measures({"occupancy_groups": ["B"], key: False})[key] is False
    assert code_scope.building_measures({"occupancy_groups": ["B"], key: True})[key] is True


def test_a_rooms_assembly_function_outranks_the_mark():
    # the tooltip says so: a Table 1004.5 Assembly row makes it Yes whatever the mark, a function that may be assembly
    # leaves a No unread (code_scope.assembly_spaces_from_rooms)
    assembly = {"rooms": [{"id": "r", "function": "assembly_unconcentrated"}]}
    maybe = {"rooms": [{"id": "r", "function": "courtroom"}]}
    assert code_scope.building_measures({"assembly_spaces": False}, assembly)["assembly_spaces"] is True
    assert "assembly_spaces" not in code_scope.building_measures({"assembly_spaces": False}, maybe)
    assert "makes it Yes, whatever this says" in _description(PR_A["assembly_spaces"])
