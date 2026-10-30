"""Each place's lookup is chosen by its settings (adapters/__init__.py, through rule_format's registry): a second
place gets its own adapter, never Ithaca's, and a place without settings or without its adapter is a plain error."""

import sys
import types
from pathlib import Path

import pytest

from rule_format.place import UnknownPlace, clear_cache
from site_lookup import adapter
from site_lookup.adapters import ithaca_city

FAKE = Path(__file__).parents[2] / "rule_format/tests/fixtures/places/regulations/jurisdictions/test_state/fake_town"


@pytest.fixture(autouse=True)
def fresh():
    clear_cache()
    yield
    clear_cache()


def test_ithaca_gets_its_own_lookup_and_its_settings():
    a = adapter("new_york/ithaca_city")
    assert a is ithaca_city
    assert a.sources.PLACE.name == "City of Ithaca" and a.sources.SR == 2261 and a.lookup.CITY_SWIS == ("500700",)
    assert a.suggest.CITY_TAIL == ", Ithaca, NY"
    assert {"ITHACA", "NY", "NEW", "YORK", "CITY", "OF", "USA", "14850", "14853"} <= a.suggest.CITY_WORDS


def test_a_second_place_gets_its_own_lookup_never_ithacas(monkeypatch):
    from rule_format.place import place
    own = types.ModuleType("site_lookup.adapters.fake_town")       # its own adapter, as its folder would give it
    own.sources = types.SimpleNamespace(PLACE=place(FAKE))         # serving its own place
    monkeypatch.setitem(sys.modules, "site_lookup.adapters.fake_town", own)
    assert adapter(FAKE) is own and adapter(FAKE) is not ithaca_city


def test_a_place_whose_lookup_isnt_written_yet_is_a_plain_error():
    with pytest.raises(UnknownPlace, match="its lookup adapter 'fake_town' isn't in site_lookup/adapters/"):
        adapter(FAKE)


def test_a_place_with_no_settings_has_no_lookup(tmp_path):
    with pytest.raises(UnknownPlace, match="jurisdiction.yaml is missing"):
        adapter(tmp_path)
    with pytest.raises(UnknownPlace, match="no place given"):
        adapter(None)


def test_the_outside_message_names_the_place_from_its_settings():
    src = (Path(ithaca_city.__file__).parent / "lookup.py").read_text(encoding="utf-8")
    assert "not the {PLACE.name}" in src and "City of Ithaca only" not in src


def test_nothing_names_the_lookup_or_measuring_by_its_old_shared_path():
    """Ithaca's lookup and measuring live in their place's folders: no code, test, doc or setting points a reader
    at the old shared paths (the lookup and measure modules directly under each package)."""
    import re
    repo = Path(__file__).resolve().parents[3]
    old = re.compile(r"model_measurement[./]measure(?![a-z_])|site_lookup[./]"
                     r"(?:lookup|sources|suggest|context|endpoints|names|amendments)(?![a-z_])")
    files = [repo / "pyproject.toml", repo / "CLAUDE.md"] + [p for top in ("packages", "apps", "docs")
             for p in (repo / top).rglob("*") if p.suffix in {".py", ".md", ".yaml", ".toml", ".json"}]
    found = [f"{p.relative_to(repo)}:{n}" for p in files if p.is_file()
             for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
             if old.search(line)]
    assert found == []


def test_a_place_naming_another_places_lookup_is_a_plain_error(tmp_path):
    """A lookup folder holds its own place's boundary codes and address ending: a second place that names Ithaca's
    folder would be looked up as Ithaca (its SWIS codes, its "outside the City" answer), so it is refused."""
    import yaml
    settings = yaml.safe_load((FAKE / "jurisdiction.yaml").read_text(encoding="utf-8"))
    settings["adapters"]["lookup"] = "ithaca_city"
    folder = tmp_path / "regulations/jurisdictions/test_state/borrower"
    folder.mkdir(parents=True)
    (folder / "jurisdiction.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    with pytest.raises(UnknownPlace, match="lookup adapter 'ithaca_city' serves new_york/ithaca_city, not .*borrower"):
        adapter(folder)


def test_the_command_line_names_an_unknown_place_in_one_line(capsys):
    from site_lookup.__main__ import main
    assert main(["--place", "nowhere/x", "106 Ithaca Rd"]) == 2
    out = capsys.readouterr().out
    assert out.startswith("no settings for") and "Traceback" not in out
