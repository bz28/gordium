"""Address type-ahead for the start box: the City of Ithaca addresses that start like what the architect has typed,
from the City's own address layer (endpoints.yaml `city_addresses`: City addresses only, so a Town of Ithaca or
Cayuga Heights address never appears). Used live, never kept. A suggestion is only a typing aid: the address picked
is looked up as any typed address is (the State geocoder, then the tax parcel's SWIS code decides City or Town), so
a suggestion can never stand for a fact about the lot."""

import re

from .sources import ENDPOINTS, _DIR, _SUFFIX

MIN_CHARS = 4                 # fewer typed: no suggestions (too many matches to be useful)
LIMIT = 8                     # suggestions shown at most
CITY_TAIL = ", Ithaca, NY"    # added to a suggestion: the lookup is asked for this City's address
UPPER_WORDS = set(_DIR.values())      # N, S, E, W stay capitals ("120 N Cayuga St")


MAX_SPELLINGS = 8             # spellings asked for at most (each word that may be shortened doubles them)
CITY_WORDS = {"ITHACA", "CITY", "OF", "NY", "NEW", "YORK", "USA", "US", "14850", "14851", "14852", "14853"}


def other_town(after_comma: str) -> bool:
    """Whether what follows the first comma names a place other than the City of Ithaca ("Dryden", "Cayuga
    Heights", a ZIP not the City's): then no suggestion is offered, so another town stays another town (review round
    2). Ithaca, "City of Ithaca", NY and the City's ZIP codes are the City's."""
    text = re.sub(r"[^A-Za-z0-9 ]", " ", after_comma or "").upper()
    words = text.split()

    def city(w, typing):                 # the last word may still be being typed ("Itha", "148")
        return any(c == w or (typing and c.startswith(w)) for c in CITY_WORDS)
    return any(not city(w, k == len(words) - 1 and not text.endswith(" ")) for k, w in enumerate(words))


def typed_prefixes(typed: str) -> list[str]:
    """What the City's layer is asked for: the typed address up to any town ("106 Ithaca Rd, Itha" -> "106 ITHACA
    RD"), in capitals as the layer writes it. A direction after the number and a whole street-type word may be the
    City's short form ("120 North Cayuga Street" -> "120 N CAYUGA ST") or part of the street's own name ("101 SOUTH
    ST", "102 E COURT ST", "106 SOUTH HILL TER": review round 1), so both spellings are asked for, as typed first.
    Only letters, digits, spaces, dots, hyphens and apostrophes are kept (never a % or _ that would widen the
    match). [] when fewer than MIN_CHARS are typed. A finished last word ends in a space."""
    head, _, town = str(typed or "").partition(",")
    if other_town(town):                            # another town typed: never the City's address in its place
        return []
    text = re.sub(r"(?<=[A-Za-z])\.", " ", head)    # "N." is "N" ("106.5" keeps its dot: the City's half numbers)
    text = re.sub(r"[^A-Za-z0-9 .'\-]", " ", text).upper()
    ends_word = text.endswith(" ") or "," in str(typed or "")
    words = text.split()
    if not words or len(text.lstrip()) < MIN_CHARS:          # characters typed (a finishing space counts)
        return []
    spellings = [[]]
    for i, w in enumerate(words):
        short = None
        # (a direction finished as the last word: "120 NORTH " asks for "120 N " too)
        if i == 1 and w in _DIR and words[0][:1].isdigit() and (len(words) > 2 or ends_word):
            short = _DIR[w]                          # "120 NORTH CAYUGA" -> "120 N CAYUGA" (or SOUTH HILL)
        elif i > 1 and w in _SUFFIX:                 # "106 ITHACA ROAD" -> "106 ITHACA RD" (or E COURT ST)
            short = _SUFFIX[w]
        forms = [w] if short is None else [w, short]
        spellings = [s + [f] for s in spellings for f in forms][:MAX_SPELLINGS]
    tail = " " if ends_word else ""
    return [" ".join(s) + tail for s in spellings]


def typed_prefix(typed: str) -> str | None:
    """The typed address as the layer writes it, as typed (typed_prefixes' first), or None when too little."""
    found = typed_prefixes(typed)
    return found[0] if found else None


def where(prefix) -> str:
    """The layer's query: addresses starting with the prefix, or any of the prefixes (an apostrophe doubled, as SQL
    quotes it). A prefix ending in a space (its last word finished: "106 ITHACA RD ") is that whole address or it
    followed by more words, never "106 ITHACA RDX"."""
    if not isinstance(prefix, str):
        parts = [where(p) for p in prefix]
        return parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"
    words = prefix.strip().replace("'", "''")
    if prefix.endswith(" "):
        return "(UPPER(FULL_ADDRE) = '" + words + "' OR UPPER(FULL_ADDRE) LIKE '" + words + " %')"
    return "UPPER(FULL_ADDRE) LIKE '" + words + "%'"


def pretty(full: str) -> str:
    """'120 N CAYUGA ST' -> '120 N Cayuga St'; '5TH' -> '5th'; the number as written."""
    out = []
    for w in str(full or "").split():
        if w in UPPER_WORDS or w[:1].isdigit() and not w[-2:].isalpha():
            out.append(w)
        elif w[:1].isdigit():
            out.append(w.lower())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def suggest(typed: str, http, limit: int = LIMIT) -> list[str]:
    """Up to `limit` City of Ithaca addresses starting like `typed`, each as the lookup is then asked for it
    ("106 Ithaca Rd, Ithaca, NY"), in the layer's order; [] when too little is typed. Raises site_lookup.http's
    Offline / ServiceError when the layer can't answer (the box then says suggestions are unavailable)."""
    prefixes = typed_prefixes(typed)
    if not prefixes:
        return []
    body, _ = http.post(ENDPOINTS["city_addresses"]["url"], {
        "where": where(prefixes), "outFields": "FULL_ADDRE", "returnDistinctValues": "true",
        "returnGeometry": "false", "orderByFields": "FULL_ADDRE", "resultRecordCount": str(limit)})
    seen, out = set(), []
    for f in (body or {}).get("features") or []:
        full = ((f or {}).get("attributes") or {}).get("FULL_ADDRE")
        if isinstance(full, str) and full.strip() and full.strip().upper() not in seen:
            seen.add(full.strip().upper())
            out.append(pretty(full.strip()) + CITY_TAIL)
    return out[:limit]
