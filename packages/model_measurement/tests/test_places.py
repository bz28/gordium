"""Each lot is measured by its own place's measuring (places/__init__.py, chosen by the place's settings through
rule_format's registry): a second place's lot gets its own, never Ithaca's, and a lot naming no place, or a place
without settings or without its measuring, is a plain error."""

import sys
import types
from pathlib import Path

import pytest

from model_measurement import project
from model_measurement.places import ithaca_city, measuring
from model_measurement.places.ithaca_city import measure as ithaca
from rule_format.place import UnknownPlace, clear_cache

FAKE = Path(__file__).parents[2] / "rule_format/tests/fixtures/places/regulations/jurisdictions/test_state/fake_town"
SITE = {"lot": {"edges": []}, "buildings": []}


@pytest.fixture(autouse=True)
def fresh():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def fake_town(monkeypatch):
    """The made-up place's own measuring, as its folder would give it: it records what it was asked."""
    asked = []
    own = types.ModuleType("model_measurement.places.fake_town.measure")
    own.measure = lambda site, facts: asked.append(("measure", facts["jurisdiction"])) or {}
    own.fact_conflicts = lambda facts: asked.append(("fact_conflicts", facts["jurisdiction"])) or []
    folder = types.ModuleType("fake_town")
    folder.SERVES = ("test_state/fake_town",)
    monkeypatch.setitem(sys.modules, "model_measurement.places.fake_town", folder)
    monkeypatch.setitem(sys.modules, "model_measurement.places.fake_town.measure", own)
    return own, asked


def test_ithaca_lots_get_ithacas_measuring():
    assert measuring("regulations/jurisdictions/new_york/ithaca_city") is ithaca
    assert ithaca.__name__.startswith(ithaca_city.__name__)


def test_a_second_places_lot_gets_its_own_measuring_never_ithacas(fake_town, monkeypatch):
    own, asked = fake_town
    assert measuring(str(FAKE)) is own
    called_ithaca = []
    monkeypatch.setattr(ithaca, "measure", lambda *a: called_ithaca.append(a) or {})
    monkeypatch.setattr(ithaca, "fact_conflicts", lambda *a: called_ithaca.append(a) or [])
    monkeypatch.setattr(project, "read_site", lambda path, facts: SITE)
    facts = {"jurisdiction": str(FAKE), "zone": "T-1"}
    assert project.project(Path("lot.3dm"), facts)["measurements"] == {}
    assert project.fact_conflict_rows(facts) == []
    assert asked == [("measure", str(FAKE)), ("fact_conflicts", str(FAKE))] and called_ithaca == []


def test_a_place_whose_measuring_isnt_written_yet_is_a_plain_error():
    with pytest.raises(UnknownPlace, match="its measuring adapter 'fake_town' isn't in model_measurement/places/"):
        measuring(FAKE)


def test_a_lot_naming_no_place_or_an_unknown_one_is_a_plain_error(tmp_path, monkeypatch):
    monkeypatch.setattr(project, "read_site", lambda path, facts: SITE)
    with pytest.raises(UnknownPlace, match="no place given"):
        project.project(Path("lot.3dm"), {"zone": "R-1b"})
    with pytest.raises(UnknownPlace, match="jurisdiction.yaml is missing"):
        project.fact_conflict_rows({"jurisdiction": str(tmp_path)})


def test_a_place_naming_another_places_measuring_is_a_plain_error(tmp_path):
    """Measuring is a place's own law's definitions: a second place that names Ithaca's folder in its settings is
    refused until an engineer adds it to that folder's SERVES (citing both laws), never measured as Ithaca."""
    import yaml
    settings = yaml.safe_load((FAKE / "jurisdiction.yaml").read_text(encoding="utf-8"))
    settings["adapters"]["measurement"] = "ithaca_city"
    folder = tmp_path / "regulations/jurisdictions/test_state/borrower"
    folder.mkdir(parents=True)
    (folder / "jurisdiction.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    with pytest.raises(UnknownPlace, match="the measuring adapter 'ithaca_city' doesn't serve it"):
        measuring(folder)
