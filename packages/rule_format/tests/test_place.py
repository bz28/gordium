"""The registry of places (rule_format/place.py): each place's settings come from its own jurisdiction.yaml, a
place with no settings file is a plain error, and no code outside a place's own files names the place."""

import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

from rule_format import place as registry
from rule_format.place import UnknownPlace, place, places, plugin_place
from rule_format.rulebook import REPO, jurisdictions
from host_source import CORE_DIR, host_path

FIXTURES = Path(__file__).parent / "fixtures/places"          # a made-up repo with one made-up place in it
FAKE = FIXTURES / "regulations/jurisdictions/test_state/fake_town"
ITHACA = "new_york/ithaca_city"


@pytest.fixture(autouse=True)
def fresh():
    registry.clear_cache()
    yield
    registry.clear_cache()


def test_ithaca_by_any_of_its_names_is_its_own_settings():
    by_key, by_folder, by_path = place(ITHACA), place("regulations/jurisdictions/new_york/ithaca_city"), \
        place(REPO / "regulations/jurisdictions/new_york/ithaca_city")
    assert by_key == by_folder == by_path
    p = by_key
    assert p.key == ITHACA and p.jurisdiction == "regulations/jurisdictions/new_york/ithaca_city"
    assert p.name == "City of Ithaca" and p.swis == ("500700",) and p.epsg == 2261
    assert p.neighbours == {"503089": "Town of Ithaca", "503000": "Town of Ithaca"}
    assert p.law_file("zoning_code") == "chapter_325_zoning_2026-10.pdf"
    assert p.law_file("zoning_chart") == "zoning_charts_2026-04.pdf"
    assert p.adapter("lookup") == "ithaca_city" and p.adapter("measurement") == "ithaca_city"
    assert p.test_sites == REPO / "test_data/test_sites/new_york/ithaca_city"
    assert p.sample_site["folder"].is_dir() and p.sample_site["address"] == "106 Ithaca Rd, Ithaca, NY"


def test_the_laws_it_names_are_the_places_own_documents():
    p = place(ITHACA)
    for role in ("zoning_code", "zoning_chart"):
        assert (p.folder / "1_source_documents" / p.law_file(role)).is_file(), role


def test_a_second_place_gets_its_own_settings_never_ithacas():
    fake, ithaca = place(FAKE), place(ITHACA)
    assert fake.name == "Town of Testville" and fake.key == "test_state/fake_town"
    assert fake.swis == ("999901", "999902") and fake.epsg == 2262
    assert fake.law_file("zoning_code") == "testville_zoning_code.pdf"
    assert fake.adapter("lookup") == fake.adapter("measurement") == "fake_town"
    assert fake.district_column.fullmatch("T-1") and not fake.district_column.fullmatch("R-1B")
    assert ithaca.district_column.fullmatch("R-1B") and not ithaca.district_column.fullmatch("T-1")
    # every value the code asks for differs, so nothing of Ithaca's could have stood in for it
    for attr in ("name", "swis", "neighbours", "epsg", "addresses", "time_zone", "folder", "key", "jurisdiction"):
        assert getattr(fake, attr) != getattr(ithaca, attr), attr
    assert fake.sample_site is None                       # it has none: never Ithaca's 106 Ithaca Rd


def test_the_places_of_a_repo_are_the_folders_with_settings():
    assert [p.key for p in places(FIXTURES)] == ["test_state/fake_town"]
    assert plugin_place(FIXTURES).name == "Town of Testville"      # the one place of that repo, not Ithaca
    assert [p.key for p in places()] == [ITHACA] and plugin_place().key == ITHACA


def test_every_jurisdiction_in_the_repo_has_settings():
    assert [p.folder for p in places()] == [j.resolve() for j in jurisdictions()]


def test_a_place_with_no_settings_file_is_a_plain_error(tmp_path):
    bare = tmp_path / "regulations/jurisdictions/test_state/no_settings"
    bare.mkdir(parents=True)
    (bare / "README.md").write_text("a place with documents but no jurisdiction.yaml", encoding="utf-8")
    with pytest.raises(UnknownPlace, match=r"no settings for .*no_settings: .*jurisdiction\.yaml is missing"):
        place(bare)
    with pytest.raises(UnknownPlace, match="jurisdiction.yaml is missing"):
        place("new_york/nowhere")                          # a place Gordium has never heard of
    for nothing in (None, "", "."):
        with pytest.raises(UnknownPlace, match="no place given"):
            place(nothing)
    assert places(tmp_path) == []                          # a folder without settings is not a place
    with pytest.raises(UnknownPlace, match="0 have settings"):
        plugin_place(tmp_path)                             # never Ithaca in its stead


def test_two_places_need_a_picker_never_the_first_one(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES, root)
    shutil.copytree(REPO / "regulations/jurisdictions/new_york/ithaca_city", root / "regulations/jurisdictions/new_york/ithaca_city",
                    ignore=lambda d, names: [n for n in names if n != "jurisdiction.yaml"])
    state = root / "regulations/jurisdictions/new_york/new_york_state"   # the state law Ithaca inherits
    state.mkdir(parents=True)
    shutil.copy(REPO / "regulations/jurisdictions/new_york/new_york_state/state.yaml", state)
    assert len(places(root)) == 2
    with pytest.raises(UnknownPlace, match="the plugin reads one place, and 2 have settings .*place picker"):
        plugin_place(root)


@pytest.mark.parametrize("change,problem", [
    (lambda s: s.pop("name"), "no name"),
    (lambda s: s["boundary"].update(swis=[]), "boundary names no swis codes"),
    (lambda s: s["coordinates"].update(epsg="2261"), "coordinates.epsg must be a whole number"),
    (lambda s: s["time_zone"].update(daylight_saving="eu"), "time_zone.daylight_saving must be one of"),
    (lambda s: s["districts"].update(chart_column="R-("), "districts.chart_column isn't a pattern"),
    (lambda s: s["law"].pop("zoning_code"), "law names no zoning_code"),
    (lambda s: s["adapters"].pop("measurement"), "adapters names no measurement"),
    (lambda s: s["addresses"].update(tail=""), "addresses.tail is missing"),
    (lambda s: s["addresses"].pop("shares_mail_as"), "addresses.shares_mail_as is missing"),
    (lambda s: s["addresses"].pop("own_words"), "addresses.own_words must be a list of words"),
    (lambda s: s["addresses"].pop("also_written"), "addresses.also_written must be a list of words"),
    (lambda s: s["addresses"].update(zip_codes=[14850]), "addresses.zip_codes must be a list of words"),
    (lambda s: s["addresses"].pop("state_words"), "addresses.state_words must be a list of words"),
    (lambda s: s["addresses"].pop("county_words"), "addresses.county_words must be a list of words"),
    (lambda s: s["addresses"].update(nearby_places="lansing"), "addresses.nearby_places must be a list of words"),
    (lambda s: s["addresses"].update(shares_mail_with=[]), "addresses.shares_mail_with names none"),
    (lambda s: s.update(sample_site={"address": "1 Main St"}), "sample_site must give a folder and an address"),
    (lambda s: s["addresses"].update(nearby_places=["Elsewhere"]), "addresses.nearby_places must be lowercase"),
    (lambda s: s["addresses"].update(own_words=["Testville"]), "addresses.own_words must be lowercase"),
    (lambda s: s["coordinates"].update(epsg=True), "coordinates.epsg must be a whole number"),
    (lambda s: s["addresses"].update(tail="Testville TS"), 'addresses.tail must start with ", "'),
    (lambda s: s["law"].update(zoning_chart=None), "law.zoning_chart must name a file"),
    (lambda s: s["districts"].update(chart_column="(T-1)|"), "districts.chart_column matches an empty heading"),
    (lambda s: s["districts"].update(shared_columns={"Central": []}), "districts.shared_columns must map"),
    (lambda s: s["districts"].update(shared_columns={"Central": ["T-1", "T-1"]}), "districts.shared_columns must map"),
    (lambda s: s["addresses"].update(nearby_places=["cayuga heights"]), "addresses.nearby_places must be single words"),
    (lambda s: s["time_zone"].update(standard_utc_offset_hours=False), "standard_utc_offset_hours must be a number"),
])
def test_settings_that_cant_be_used_are_refused_with_what_is_wrong(tmp_path, change, problem):
    import yaml
    settings = yaml.safe_load((FAKE / "jurisdiction.yaml").read_text(encoding="utf-8"))
    change(settings)
    folder = tmp_path / "regulations/jurisdictions/test_state/broken"
    folder.mkdir(parents=True)
    (folder / "jurisdiction.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    with pytest.raises(UnknownPlace, match=re.escape(problem)):
        place(folder)


def test_a_missing_law_or_adapter_is_named_not_guessed():
    with pytest.raises(UnknownPlace, match="names no zoning_ordinance_map under law"):
        place(ITHACA).law_file("zoning_ordinance_map")
    with pytest.raises(UnknownPlace, match="names no design adapter"):
        place(ITHACA).adapter("design")


def test_the_plugins_copy_is_current_and_is_what_rhino_logic_reads():
    assert registry.PLUGIN_FILE.read_text(encoding="utf-8") == registry.plugin_file_text()
    from design_checker import rhino_logic
    copy = json.loads(registry.PLUGIN_FILE.read_text(encoding="utf-8"))
    assert {k: v for k, v in copy.items() if not k.startswith("_")} == registry.plugin_settings(plugin_place())
    assert rhino_logic.PLACE == copy


def test_the_places_day_follows_its_time_zone_through_the_year():
    """rhino_logic.city_day (no time-zone database in Rhino) against Python's own for the place's zone, every hour
    of 2026 and 2027 around both changes (skipped where the zone database isn't installed: Windows)."""
    zoneinfo = pytest.importorskip("zoneinfo")
    from design_checker import rhino_logic
    try:
        zone = zoneinfo.ZoneInfo(rhino_logic.PLACE["time_zone"]["name"])
    except zoneinfo.ZoneInfoNotFoundError:
        pytest.skip("no time-zone database here")
    for year in (2026, 2027):
        for month, day in ((3, 6), (11, 0)):
            start = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=day)
            for hour in range(24 * 10):
                now = start + dt.timedelta(hours=hour)
                assert rhino_logic.city_day(now) == now.astimezone(zone).date().isoformat(), now


def _code_strings(text: str) -> list[str]:
    """The text values a file's code uses: every string but docstrings and usage examples ("e.g. …"); comments
    aren't strings."""
    import ast
    tree = ast.parse(text)
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs and "e.g." not in n.value]


def test_no_code_outside_a_places_own_files_names_the_place():
    """Shared code asks the registry: Ithaca's folder is named only in its settings, in tests, and in its own lookup
    and measuring folders (adapters/ithaca_city, places/ithaca_city)."""
    own = ("/tests/", "/adapters/ithaca_city/", "/places/ithaca_city/", "/evals/")
    found = []
    for path in sorted([*(REPO / "packages").rglob("*.py"), *(REPO / "apps").rglob("*.py")]):
        rel = "/" + path.relative_to(REPO).as_posix()
        if any(o in rel for o in own):
            continue
        found += [(rel, v[:80]) for v in _code_strings(path.read_text(encoding="utf-8"))
                  if re.search(r"ithaca_city|chapter_325|zoning_charts_20", v)]
    assert found == [], found


def test_the_check_above_finds_a_place_named_in_code():
    assert _code_strings('X = "regulations/jurisdictions/new_york/ithaca_city"\n') == [
        "regulations/jurisdictions/new_york/ithaca_city"]
    assert _code_strings('"""Docs: new_york/ithaca_city."""\nY = 1  # new_york/ithaca_city\n') == []


def test_the_plugin_loads_with_the_fewest_address_words_the_check_accepts(tmp_path, monkeypatch):
    """The check above and the plugin agree: settings it lets through (here every list it allows to be empty is
    empty, and one place shares the mail) make a place.json rhino_logic loads and reads addresses with."""
    import importlib.util
    import yaml
    settings = yaml.safe_load((FAKE / "jurisdiction.yaml").read_text(encoding="utf-8"))
    settings["addresses"].update(also_written=[], county_words=[], nearby_places=[], shares_mail_with=["Elsewhere"])
    root = tmp_path / "repo"
    folder = root / "regulations/jurisdictions/test_state/fewest"
    folder.mkdir(parents=True)
    (folder / "jurisdiction.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    shutil.copy(host_path("rhino", "logic"), plugin)
    shutil.copytree(CORE_DIR, plugin / "host_core", ignore=shutil.ignore_patterns("__pycache__"))  # what it re-exports
    (plugin / "place.json").write_text(registry.plugin_file_text(root), encoding="utf-8")
    monkeypatch.syspath_prepend(str(plugin))        # as in Rhino: host_core imported from beside rhino_logic.py
    for name in [n for n in sys.modules if n == "host_core" or n.startswith("host_core.")]:
        monkeypatch.delitem(sys.modules, name)      # put back after the test (rhino_logic forgets any it finds)
    spec = importlib.util.spec_from_file_location("rhino_logic_fewest", plugin / host_path("rhino", "logic").name)
    logic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(logic)
    assert "may instead be in the Elsewhere, which" in logic.IN_CITY_QUESTION
    assert logic.CITY_SUFFIX == ", Testville, TS"
    assert logic.HOST_CORE[0].__file__ == str(plugin / "host_core" / "place.py")    # the copy's own, not the repo's


def test_a_law_file_named_by_no_value_is_a_plain_error_never_none(tmp_path):
    import yaml
    settings = yaml.safe_load((FAKE / "jurisdiction.yaml").read_text(encoding="utf-8"))
    p = registry.Place(FAKE, settings | {"law": {"zoning_code": "code.pdf", "zoning_chart": None}})
    with pytest.raises(UnknownPlace, match="names no zoning_chart under law"):
        p.law_file("zoning_chart")
