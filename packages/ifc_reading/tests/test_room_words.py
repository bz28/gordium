"""Which names make a room a sleeping room, one that isn't, or unknown (no ifcopenshell needed)."""

import unicodedata

import pytest
import yaml

from ifc_reading import rooms
from ifc_reading.rooms import name_words, sleeping_from_names


@pytest.mark.parametrize("name, expected", [
    ("Bedroom 2", True), ("MASTER BEDROOM", True), ("Bed 3", True), ("Schlafzimmer", True), ("Kinderzimmer", True),
    ("Bath 2", False), ("Küche", False), ("KÜCHE", False), ("Living Room", False), ("Hall/Stair", False),
    ("Wohnen", False),
    # unknown: an ask word, both kinds, or nothing listed
    ("Office", None), ("Buero", None), ("Galerie", None), ("Den", None), ("Loft", None), ("Guest Room", None),
    ("Bedroom closet", None), ("Living/Sleeping", None), ("Bedroom / Office", None), ("Room 12", None),
    ("4", None), ("", None),
    # whole words only: a listed word inside another word doesn't count
    ("Bedside nook", None), ("Bathtub alcove", None), ("Hallmark", None),
    # a word the table doesn't know, beside a not-sleeping word, may mean bedroom: unknown (review round 1)
    ("Elternzimmer + Bad", None), ("Primary Suite / Bath", None), ("Bunk room / Bath", None),
    ("Master Bath", None), ("Bath / Allgemeines", False), ("Bath No. 2", False), ("Walk-in Closet", False),
    # however an accent is stored (a decomposed "ä" is one letter)
    (unicodedata.normalize("NFD", "Gästezimmer / Bad"), None), (unicodedata.normalize("NFD", "Gästezimmer"), True),
    (unicodedata.normalize("NFD", "Küche"), False),
])
def test_a_name_decides_only_when_its_words_agree(name, expected):
    got, why = sleeping_from_names({"LongName": name})
    assert got is expected, why


def test_never_from_size_only_from_words():
    # the reader's only inputs are words and the flag: nothing else reaches the decision
    import inspect
    assert list(inspect.signature(sleeping_from_names).parameters) == ["texts", "flag"]


def test_every_name_source_counts_and_they_must_agree():
    assert sleeping_from_names({"LongName": "Bedroom", "Name": "101"})[0] is True
    assert sleeping_from_names({"LongName": "Bedroom", "ObjectType": "Office"})[0] is None
    assert sleeping_from_names({"LongName": "Space", "classification 13-55 11 13": "Bedroom"})[0] is True


@pytest.mark.parametrize("name, flag, expected", [
    ("Kitchen", True, True),          # the architect's true always counts
    ("Anything", False, False),
    ("Storage", False, False),
    ("Bedroom 2", False, None),       # a false against a bedroom name: unknown, never quietly not a bedroom
    ("Office", False, False),         # an ask word is what the flag answers
    ("Primary Suite / Bath", False, False),   # so is an unknown word
    ("Bedroom / Office", False, None),
    ("", None, None),
])
def test_the_architects_flag(name, flag, expected):
    assert sleeping_from_names({"LongName": name}, flag)[0] is expected


def test_words_are_cut_at_every_non_letter():
    assert name_words("Bed_2/Bath-3 (4)") == ["bed", "bath"]


def test_the_word_table_lists_each_word_once_in_lowercase():
    with open(rooms.Path(rooms.__file__).with_name("room_words.yaml"), encoding="utf-8") as f:
        table = yaml.safe_load(f)
    every = [w for k in rooms.KINDS for w in table[k]]
    assert len(every) == len(set(every)) == len(rooms.words())
    assert all(isinstance(w, str) and w == w.casefold() and name_words(w) == [w] for w in every)
