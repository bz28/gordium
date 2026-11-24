"""Plain words for the architect (rulebook.py plain_words_problems): where a law's settings say `plain_words: true`, a
rule's title, notes, review reasons and examples' notes carry no engineer's key (a snake_case name of a measure or
fact, a rule id with one). A state law folder says so in its state.yaml, a place for its own rulebooks in its
jurisdiction.yaml; the nearest settings file decides, and an answer key (test_data/, no settings) is never held to
it. Turned on for the City of Ithaca and Maine on 2026-11-24."""

from pathlib import Path

import pytest
import yaml

from rule_format import place as registry
from rule_format.place import settings_problems
from rule_format.rulebook import (REPO, _plain_words_law, load, plain_words_problems, rulebook_file_problems,
                                  rulebook_paths, rules_folder)

LAWS = REPO / "regulations/jurisdictions"
PLAIN = {"new_york/ithaca_city": "jurisdiction.yaml", "maine/maine_state": "state.yaml"}


@pytest.mark.parametrize("law, settings", PLAIN.items())
def test_ithaca_and_maine_ask_for_plain_words(law, settings):
    assert load(LAWS / law / settings)["plain_words"] is True


@pytest.mark.parametrize("law", PLAIN)
def test_every_rulebook_they_hold_is_in_plain_words(law):
    """Each rulebook is held to it (the nearest settings file is its law's) and shows the architect no key: 331
    notes, reasons and examples' notes were reworded, a fact by the field the add-in shows, a rule by its title."""
    books = rulebook_paths(rules_folder(LAWS / law))
    assert books
    for path in books:
        assert _plain_words_law(path), path
        assert plain_words_problems(load(path)) == [], path


def test_a_places_jurisdiction_yaml_turns_it_on_and_an_answer_key_is_never_held_to_it(tmp_path):
    town = tmp_path / "regulations/jurisdictions/x_state/x_town"
    (town / "5_zoning_rules").mkdir(parents=True)
    book = town / "5_zoning_rules/R-1.yaml"
    book.write_text(yaml.safe_dump({"district": "R-1", "rules": [
        {"id": "R-1.lot_area", "title": "Lot area", "notes": "Reads lot_area_hotel_motel (see R-1.side_yards)."}]}),
        encoding="utf-8")
    key = tmp_path / "test_data/answer_keys/x_state/x_town/R-1.yaml"
    key.parent.mkdir(parents=True)
    key.write_text(book.read_text(encoding="utf-8"), encoding="utf-8")
    (town / "jurisdiction.yaml").write_text("name: X Town\n", encoding="utf-8")
    assert not _plain_words_law(book)                        # not asked: the words aren't checked
    (town / "jurisdiction.yaml").write_text("name: X Town\nplain_words: true\n", encoding="utf-8")
    assert _plain_words_law(book) and not _plain_words_law(key)
    [got] = plain_words_problems(load(book))
    assert got.startswith("R-1.lot_area: ") and got.endswith("R-1.side_yards, lot_area_hotel_motel (say it in plain words)")


def test_the_real_check_refuses_a_key_in_ithacas_rulebook(tmp_path, monkeypatch):
    """Through rulebook_file_problems, as `python -m rule_format` runs it: a key put back into one of Ithaca's notes
    is refused, and the same file with the key said in words is clean."""
    from rule_format.rulebook import Context
    real = LAWS / "new_york/ithaca_city/5_zoning_rules/R-1b.yaml"
    ctx = Context.for_jurisdiction(LAWS / "new_york/ithaca_city")
    book = load(real)
    rule = next(r for r in book["rules"] if r["id"] == "R-1b.stream_setback")
    assert "“Gordium: Stream within 20 ft”" in rule["notes"]
    rule["notes"] = rule["notes"].replace("“Gordium: Stream within 20 ft”", "stream_near_lot")
    monkeypatch.setattr("rule_format.rulebook.load", lambda p: book if Path(p) == real else load(p))
    got = [p for p in rulebook_file_problems(real, ctx) if "engineer's key" in p]
    assert got == ["R-1b.stream_setback: its notes shows an engineer's key to the architect: stream_near_lot "
                   "(say it in plain words)"]


@pytest.mark.parametrize("value", [False, "yes", 1, None])
def test_a_place_can_only_ask_for_plain_words_or_leave_it_out(value):
    registry.clear_cache()
    settings = yaml.safe_load((LAWS / "new_york/ithaca_city/jurisdiction.yaml").read_text(encoding="utf-8"))
    assert settings_problems(settings) == []
    assert any("plain_words must be true" in p for p in settings_problems({**settings, "plain_words": value}))
    del settings["plain_words"]
    assert settings_problems(settings) == []


def test_a_district_rules_id_is_a_key_even_with_no_underscore():
    """Round 1 of the review: R-1a.height and RU.use are rule ids too; a section (§325-8A), a file name or a
    sentence's end (in R-1a. The) is not."""
    book = {"rules": [{"id": "R-1a.x", "title": "T", "notes": "When the bonus (R-1a.height) is used; RU.use fails "
                       "it; CBD-50.use too. In R-1a. The rest is §325-8A, see README.md and general.yaml."}]}
    [got] = plain_words_problems(book)
    assert got.endswith(": CBD-50.use, R-1a.height, RU.use (say it in plain words)")


def test_the_accessory_notes_say_whether_the_distances_apply_is_worked_out_not_that_they_apply():
    """Round 1 of the review: one reading of §325-25C's open question says the distances don't reach a building that
    isn't frame, so a note never says they are applied under every reading."""
    for path in rulebook_paths(rules_folder(LAWS / "new_york/ithaca_city")):
        for r in load(path)["rules"]:
            assert "distances are applied under every reading" not in (r.get("notes") or ""), r["id"]
            if r["id"].endswith(".accessory_buildings") and "325-25C#1" in (r.get("notes") or ""):
                assert "whether the distances apply is worked out under every reading" in r["notes"], r["id"]
