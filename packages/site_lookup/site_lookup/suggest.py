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


def typed_prefix(typed: str) -> str | None:
    """What the City's layer is asked for: the typed address up to any town ("106 Ithaca Rd, Itha" -> "106 ITHACA
    RD"), in capitals as the layer writes it, a direction after the number and every whole street-type word
    abbreviated as the City does ("120 North Cayuga Street" -> "120 N CAYUGA ST"). Only letters, digits, spaces,
    dots, hyphens and apostrophes are kept (never a % or _ that would widen the match). None when fewer than
    MIN_CHARS are typed."""
    text = str(typed or "").split(",", 1)[0]
    text = re.sub(r"[^A-Za-z0-9 .'\-]", " ", text).upper()
    ends_word = text.endswith(" ") or "," in str(typed or "")
    words = text.split()
    if not words or len(text.lstrip()) < MIN_CHARS:          # characters typed (a finishing space counts)
        return None
    for i, w in enumerate(words):
        # a direction only right after the number and before the street's name ("120 NORTH CAYUGA")
        if i == 1 and w in _DIR and words[0][:1].isdigit() and len(words) > 2:
            words[i] = _DIR[w]
        elif i > 1 and w in _SUFFIX:             # a whole street-type word, the last one too ("106 ITHACA ROAD")
            words[i] = _SUFFIX[w]
    return " ".join(words) + (" " if ends_word else "")


def where(prefix: str) -> str:
    """The layer's query: addresses starting with the prefix (an apostrophe doubled, as SQL quotes it). A prefix
    ending in a space (its last word finished: "106 ITHACA RD ") is that whole address or it followed by more words,
    never "106 ITHACA RDX"."""
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
    prefix = typed_prefix(typed)
    if prefix is None:
        return []
    body, _ = http.post(ENDPOINTS["city_addresses"]["url"], {
        "where": where(prefix), "outFields": "FULL_ADDRE", "returnDistinctValues": "true",
        "returnGeometry": "false", "orderByFields": "FULL_ADDRE", "resultRecordCount": str(limit)})
    seen, out = set(), []
    for f in (body or {}).get("features") or []:
        full = ((f or {}).get("attributes") or {}).get("FULL_ADDRE")
        if isinstance(full, str) and full.strip() and full.strip().upper() not in seen:
            seen.add(full.strip().upper())
            out.append(pretty(full.strip()) + CITY_TAIL)
    return out[:limit]
