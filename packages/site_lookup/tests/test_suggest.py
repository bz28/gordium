"""Address type-ahead (site_lookup.suggest), offline: a stand-in for the City's address layer answers from a few
hand-written addresses (never the City's data: endpoints.yaml `city_addresses` is used live, never stored)."""
import re

import pytest

from site_lookup.http import Offline
from site_lookup.sources import ENDPOINTS
from site_lookup.suggest import CITY_TAIL, LIMIT, MIN_CHARS, pretty, suggest, typed_prefix, where

# City of Ithaca addresses, typed by hand as the City's layer writes them: the sample and its neighbour, one
# repeated (a building with units repeats), a longer number, two downtown, a half number, and ten "200 …" on
# different streets (more than the box shows)
STAND_IN_ADDRESSES = (["106 ITHACA RD", "106 ITHACA RD", "96 ITHACA RD", "1060 ITHACA RD", "120 N CAYUGA ST",
                       "120 S CAYUGA ST", "106.5 LINN ST", "O'NEIL CT"] +
                      ["200 %s ST" % s for s in ("ASH", "BIRCH", "CEDAR", "DOGWOOD", "ELM", "FIR", "GROVE", "HAZEL",
                                                 "IVY", "JUNIPER")])


class StandIn:
    """Answers the City's address layer query as its SQL would: the where clause's LIKE / = parts, distinct, in
    address order, at most resultRecordCount."""

    def __init__(self, offline=False):
        self.offline, self.asked = offline, []

    def post(self, url, params):
        self.asked.append((url, params))
        if self.offline:
            raise Offline(url)
        assert url == ENDPOINTS["city_addresses"]["url"]
        clause = params["where"]
        likes = [s.replace("''", "'") for s in re.findall(r"LIKE '((?:[^']|'')*)%'", clause)]
        equals = [s.replace("''", "'") for s in re.findall(r"= '((?:[^']|'')*)'", clause)]
        hits = sorted({a for a in STAND_IN_ADDRESSES if any(a.startswith(p) for p in likes) or a in equals})
        return {"features": [{"attributes": {"FULL_ADDRE": a}} for a in hits][:int(params["resultRecordCount"])]}, b""


def test_what_is_asked_is_the_typed_address_as_the_city_writes_it():
    assert typed_prefix("106 Itha") == "106 ITHA"
    assert typed_prefix("120 North Cayuga") == "120 N CAYUGA"          # a direction after the number
    assert typed_prefix("106 Ithaca Road") == "106 ITHACA RD"          # a whole street-type word, the last one too
    assert typed_prefix("120 North Cayuga Street ") == "120 N CAYUGA ST "
    assert typed_prefix("106 Ithaca Rd, Ithaca, NY") == "106 ITHACA RD "   # up to the town: the address is whole
    assert typed_prefix("North Cayuga") == "NORTH CAYUGA"              # no number: never a direction guessed
    assert typed_prefix("10%_6 It") == "10 6 IT"                       # never a wildcard that widens the match
    assert typed_prefix("106") is None and typed_prefix("") is None and typed_prefix(None) is None
    assert MIN_CHARS == 4 and typed_prefix("1 2") is None and typed_prefix("106 ") == "106 "


def test_the_query_quotes_safely_and_a_finished_word_is_whole():
    assert where("106 ITHA") == "UPPER(FULL_ADDRE) LIKE '106 ITHA%'"
    assert where("O'NEIL") == "UPPER(FULL_ADDRE) LIKE 'O''NEIL%'"
    assert where("106 ITHACA RD ") == ("(UPPER(FULL_ADDRE) = '106 ITHACA RD' OR UPPER(FULL_ADDRE) LIKE "
                                       "'106 ITHACA RD %')")


def test_suggestions_are_city_addresses_as_the_lookup_is_asked_for_them():
    http = StandIn()
    assert suggest("106 Itha", http) == ["106 Ithaca Rd" + CITY_TAIL]          # the repeated one said once
    assert suggest("106 ", http) == ["106 Ithaca Rd" + CITY_TAIL]              # a whole "106": never "1060 …"
    assert suggest("1060", http) == ["1060 Ithaca Rd" + CITY_TAIL]
    assert suggest("120 North Cayuga", http) == ["120 N Cayuga St" + CITY_TAIL]
    assert suggest("106 Ithaca Rd, Ithaca, NY", http) == ["106 Ithaca Rd" + CITY_TAIL]
    assert suggest("O'Neil", http) == ["O'neil Ct" + CITY_TAIL]
    assert suggest("999 Nowhere", http) == []
    asked = len(http.asked)
    assert suggest("106", http) == [] and len(http.asked) == asked             # too little typed: never asked


def test_at_most_the_limit_in_address_order_and_the_layers_request():
    got = suggest("200 ", StandIn())
    assert len(got) == LIMIT == 8 and got[0] == "200 Ash St" + CITY_TAIL and got[-1] == "200 Hazel St" + CITY_TAIL
    assert len(suggest("200 ", StandIn(), limit=3)) == 3
    http = StandIn()
    suggest("106 Itha", http)
    assert http.asked[0][1] == {"where": "UPPER(FULL_ADDRE) LIKE '106 ITHA%'", "outFields": "FULL_ADDRE",
                                "returnDistinctValues": "true", "returnGeometry": "false",
                                "orderByFields": "FULL_ADDRE", "resultRecordCount": str(LIMIT)}


def test_names_read_as_an_address_is_written():
    assert pretty("120 N CAYUGA ST") == "120 N Cayuga St"
    assert pretty("106.5 LINN ST") == "106.5 Linn St"
    assert pretty("401 W 5TH ST") == "401 W 5th St"
    assert pretty("106A ITHACA RD") == "106A Ithaca Rd"


def test_offline_is_for_the_caller_to_say_never_hidden():
    with pytest.raises(Offline):
        suggest("106 Itha", StandIn(offline=True))


def test_the_citys_layer_is_used_live_and_credited():
    e = ENDPOINTS["city_addresses"]
    assert e["store"] == "none" and "GIS Program, City of Ithaca" in e["attribution"]
    assert e["url"].endswith("/Address_Labels/FeatureServer/0/query")
